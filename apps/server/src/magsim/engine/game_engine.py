from __future__ import annotations

import heapq
import logging
import copy
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

from magsim.ai.smart_agent import SmartAgent
from magsim.core.events import (
    AbilityTriggeredEvent,
    AbilityRollResultEvent,
    EmitsAbilityTriggeredEvent,
    ExecuteMainMoveEvent,
    GameEvent,
    MainMoveSkippedEvent,
    MoveCmdEvent,
    PassingEvent,
    PerformMainRollEvent,
    PreTurnStartEvent,
    RacerEliminatedEvent,
    RacerFinishedEvent,
    ResolveMainMoveEvent,
    RollModificationWindowEvent,
    RollResultEvent,
    ScheduledEvent,
    SimultaneousMoveCmdEvent,
    SimultaneousWarpCmdEvent,
    TripCmdEvent,
    TripRecoveryEvent,
    TurnEndEvent,
    TurnStartEvent,
    WarpCmdEvent,
)
from magsim.core.mixins import (
    ExternalAbilityMixin,
    LifecycleManagedMixin,
    SetupPhaseMixin,
)
from magsim.core.registry import (
    RACER_ABILITIES,
)
from magsim.core.state import ActiveRacerState, RollState, is_active
from magsim.core.interactive import (
    CompletedRoll,
    DecisionRequired,
    RollBroker,
    RollKind,
    RollRequired,
    SubmittedRoll,
)
from magsim.engine.log_context import ContextFilter
from magsim.engine.loop_detection import LoopDetector
from magsim.engine.movement import (
    handle_move_cmd,
    handle_simultaneous_move_cmd,
    handle_simultaneous_warp_cmd,
    handle_trip_cmd,
    handle_warp_cmd,
)
from magsim.engine.roll import (
    handle_execute_main_move,
    handle_perform_main_roll,
    resolve_main_move,
)
from magsim.racers import get_ability_classes, get_all_racer_stats

if TYPE_CHECKING:
    import random

    from magsim.core.abilities import Ability
    from magsim.core.agent import Agent
    from magsim.core.state import (
        GameState,
        LogContext,
        RacerState,
    )
    from magsim.core.types import (
        ErrorCode,
        RacerName,
        RacerStat,
        Source,
    )

AbilityCallback = Callable[[GameEvent, int, "GameEngine"], None]


class TurnProgress(Enum):
    WAITING_FOR_DECISION = auto()
    WAITING_FOR_ROLL = auto()
    TURN_COMPLETE = auto()


@dataclass
class Subscriber:
    callback: AbilityCallback
    owner_idx: int


@dataclass
class GameEngine:
    state: GameState
    rng: random.Random
    log_context: LogContext
    current_processing_event: ScheduledEvent | None = None
    subscribers: dict[type[GameEvent], list[Subscriber]] = field(default_factory=dict)
    agents: dict[int, Agent] = field(default_factory=dict)
    defer_setup: bool = False
    roll_broker: RollBroker = field(default_factory=RollBroker)

    # Errors and loop detection
    bug_reason: ErrorCode | None = None
    loop_detector: LoopDetector = field(default_factory=LoopDetector)

    # Callback for external observers
    on_event_processed: Callable[[GameEngine, GameEvent], None] | None = None
    verbose: bool = True
    _logger: logging.Logger = field(init=False, repr=False)
    _setup_completed: set[tuple[int, str]] = field(default_factory=set, init=False)
    _setup_complete: bool = field(default=False, init=False)
    _turn_in_progress: bool = field(default=False, init=False)
    _turn_end_triggered: bool = field(default=False, init=False)
    _main_roll_requested: bool = field(default=False, init=False)
    # An interactive landing may replay internally. Its already-visible prefix
    # remains on the board while the player chooses, and is emitted only once.
    preview_events: tuple[GameEvent, ...] = ()
    _preview_serial: int | None = None

    def __post_init__(self) -> None:
        """Assigns starting abilities to all racers and fires on_gain hooks."""
        base = logging.getLogger("magical_athlete")
        self._logger = base.getChild(f"engine.{id(self)}")

        if self.verbose:
            self._logger.addFilter(ContextFilter(self))

        for racer in self.get_active_racers():
            # 1. Initial Identity (e.g. "Egg", "Copycat")
            initial_core = self.instantiate_racer_abilities(racer.name)
            self.replace_core_abilities(racer.idx, initial_core)

            _ = self.agents.setdefault(racer.idx, SmartAgent())

        if not self.defer_setup:
            if not self.continue_setup():
                raise RuntimeError("Interactive setup requires defer_setup=True")

    def _transaction_snapshot(self) -> tuple[Any, Any, Any, Any, Any]:
        state, subscribers, detector, current = copy.deepcopy(
            (self.state, self.subscribers, self.loop_detector, self.current_processing_event)
        )
        return state, subscribers, detector, current, self.rng.getstate()

    def _restore_transaction(self, snapshot: tuple[Any, Any, Any, Any, Any]) -> None:
        state, subscribers, detector, current, rng_state = snapshot
        self.state = state
        self.subscribers = subscribers
        self.loop_detector = detector
        self.current_processing_event = current
        self.rng.setstate(rng_state)

    def continue_setup(self) -> bool:
        """Run setup abilities until complete or an interactive choice pauses them."""
        if self._setup_complete:
            return True
        while True:
            task: tuple[int, Any] | None = None
            for racer in self.get_active_racers():
                for ability in racer.active_abilities:
                    key = (racer.idx, type(ability).__qualname__)
                    if isinstance(ability, SetupPhaseMixin) and key not in self._setup_completed:
                        task = (racer.idx, ability)
                        break
                if task is not None:
                    break
            if task is None:
                self._setup_complete = True
                self.state.race_active = True
                return True

            racer_idx, ability = task
            snapshot = self._transaction_snapshot()
            self._rewind_interactions()
            try:
                ability.on_setup(self, self.get_active_racer(racer_idx), self.agents[racer_idx])
            except DecisionRequired:
                self._restore_transaction(snapshot)
                return False
            self._commit_interactions()
            self._setup_completed.add((racer_idx, type(ability).__qualname__))

    # --- Main Loop ---
    def run_race(self):
        while self.state.race_active:
            self.run_turn()
            self.advance_turn()

    def run_turn(self):
        self.start_turn()
        while True:
            progress = self.continue_turn()
            if progress is TurnProgress.WAITING_FOR_ROLL:
                if self.roll_broker.pending is not None:
                    self.submit_pending_roll()
                else:
                    self.request_main_roll()
                continue
            if progress is TurnProgress.WAITING_FOR_DECISION:
                raise RuntimeError("run_turn cannot pause; use start_turn/continue_turn")
            return

    def start_turn(self) -> None:
        if self._turn_in_progress:
            return
        # 1. Reset detector for the new turn
        self.loop_detector.reset_for_turn()
        self.state.history.clear()

        cr = self.state.current_racer_idx
        racer = self.state.racers[cr]

        # Reset per-turn values while preserving the race-wide roll identity.
        self.state.roll_state = RollState(serial_id=self.state.roll_state.serial_id)
        racer.roll_override = None
        racer.can_reroll = True
        racer.main_move_consumed = False

        self.log_context.start_turn_log(f"{racer.idx}•{racer.name}")
        self.log_info(f"=== START TURN: {racer.repr} ===")
        self._turn_in_progress = True
        self._turn_end_triggered = False
        self._main_roll_requested = False

        # --- Pre-Turn Recording (for Heckler) ---
        self.push_event(
            PreTurnStartEvent(
                responsible_racer_idx=None,
                source="System",
            ),
        )

        if racer.tripped:
            self.log_info(f"{racer.repr} recovers from Trip.")
            racer.tripped = False
            tripping_racers = racer.tripping_racers.copy()
            racer.tripping_racers = []
            racer.main_move_consumed = True
            self.push_event(
                TripRecoveryEvent(
                    target_racer_idx=cr,
                    tripping_racers=tripping_racers,
                    responsible_racer_idx=None,
                    source="System",
                ),
            )
            self.push_event(
                TurnStartEvent(
                    target_racer_idx=cr,
                    responsible_racer_idx=None,
                    source="System",
                ),
            )
        else:
            self.push_event(
                TurnStartEvent(
                    target_racer_idx=cr,
                    responsible_racer_idx=None,
                    source="System",
                ),
            )

    def request_main_roll(self) -> None:
        """Resume a prepared turn by scheduling its authoritative main roll."""
        if not self._turn_in_progress:
            raise RuntimeError("start_turn must be called before request_main_roll")
        racer = self.state.racers[self.state.current_racer_idx]
        if self.state.queue or self._main_roll_requested or racer.main_move_consumed:
            raise RuntimeError("main roll is not currently available")
        self._main_roll_requested = True
        self.push_event(
            PerformMainRollEvent(
                target_racer_idx=racer.idx,
                responsible_racer_idx=None,
                source="System",
            ),
        )

    def continue_turn(self) -> TurnProgress:
        """Resolve queued events until the turn ends or input is required."""
        if not self._turn_in_progress:
            raise RuntimeError("start_turn must be called before continue_turn")
        while self.state.race_active:
            if not self.state.queue:
                racer = self.state.racers[self.state.current_racer_idx]
                if not self._main_roll_requested and not racer.main_move_consumed:
                    return TurnProgress.WAITING_FOR_ROLL
                # If done with normal events, inject TurnEndEvent ONCE
                if not self._turn_end_triggered:
                    self.push_event(
                        TurnEndEvent(
                            responsible_racer_idx=None,
                            source="System",
                        ),
                    )
                    self._turn_end_triggered = True
                    continue  # Restart loop to process TurnEndEvent

                # If already triggered and still empty, we are truly done
                self._turn_in_progress = False
                return TurnProgress.TURN_COMPLETE
            # -------------------------------

            # The detector mutates while checking. Include it in the event
            # transaction so replay after a decision is not mistaken for a loop.
            snapshot = self._transaction_snapshot()

            # Prepare hashes for checks
            current_board_hash = self._calculate_board_hash()
            current_system_hash = self.state.get_state_hash()

            # --- Layer 1: Exact State Cycle (Least Harmful) ---
            if self.loop_detector.check_exact_cycle(current_system_hash):
                skipped = heapq.heappop(self.state.queue)
                self.loop_detector.forget_event(skipped.serial)
                self.log_warning(
                    f"Infinite loop detected (Exact State Cycle). Dropping recursive event: {skipped.event}",
                )
                continue

            # Peek/Pop the next event
            sched = heapq.heappop(self.state.queue)

            # --- Layer 2: Heuristic Detection (Surgical Fix) ---
            if self.loop_detector.check_heuristic_loop(
                current_board_hash,
                len(self.state.queue),
                sched,
            ):
                self.log_warning(
                    f"MINOR_LOOP_DETECTED (Heuristic/Exploding). Dropping: {sched.event}",
                )
                self.bug_reason = (
                    "MINOR_LOOP_DETECTED"
                    if self.bug_reason != "CRITICAL_LOOP_DETECTED"
                    else self.bug_reason
                )
                continue

            # --- Layer 3: Global Sanity Check (Nuclear Option) ---
            if self.loop_detector.check_global_sanity(current_board_hash):
                self.log_error(
                    "CRITICAL_LOOP_DETECTED: Board state oscillation limit exceeded. Aborting turn.",
                )
                self.state.queue.clear()
                self.bug_reason = "CRITICAL_LOOP_DETECTED"
                break

            self.current_processing_event = sched
            self._rewind_interactions()
            callback = self.on_event_processed
            committed_events: list[GameEvent] = []
            if callback is not None:
                self.on_event_processed = lambda _engine, event: committed_events.append(event)
            try:
                self._handle_event(sched.event)
            except DecisionRequired:
                self._restore_transaction(snapshot)
                self._publish_event_prefix(sched.serial, committed_events, callback)
                return TurnProgress.WAITING_FOR_DECISION
            except RollRequired:
                self._restore_transaction(snapshot)
                self._publish_event_prefix(sched.serial, committed_events, callback)
                return TurnProgress.WAITING_FOR_ROLL
            finally:
                self.on_event_processed = callback
            self._publish_event_prefix(sched.serial, committed_events, callback)
            self.preview_events = ()
            self._preview_serial = None
            self._commit_interactions()
        self._turn_in_progress = False
        return TurnProgress.TURN_COMPLETE

    def _publish_event_prefix(self, serial, events, callback) -> None:
        previous = self.preview_events if self._preview_serial == serial else ()
        if callback is not None:
            for event in events[len(previous):]:
                callback(self, event)
        self.preview_events = tuple(events)
        self._preview_serial = serial

    def request_roll_sequence(
        self,
        *,
        key: tuple[Any, ...],
        kind: RollKind,
        participants: tuple[int, ...],
        ability_name: str | None = None,
    ) -> CompletedRoll:
        return self.roll_broker.request(
            key=key,
            kind=kind,
            participants=participants,
            ability_name=ability_name,
        )

    def submit_pending_roll(self) -> SubmittedRoll:
        return self.roll_broker.submit(self.rng.randint(1, 6))

    def _rewind_interactions(self) -> None:
        for agent in self.agents.values():
            broker = getattr(agent, "broker", None)
            if broker is not None:
                broker.rewind()

    def _commit_interactions(self) -> None:
        self.roll_broker.commit()
        seen_brokers: set[int] = set()
        for agent in self.agents.values():
            broker = getattr(agent, "broker", None)
            if broker is not None and id(broker) not in seen_brokers:
                broker.commit()
                seen_brokers.add(id(broker))

    def _calculate_board_hash(self) -> int:
        racer_states = tuple(
            (
                r.position,
                r.active,
                r.tripped,
                r.main_move_consumed,
                tuple(sorted(a.name for a in r.active_abilities)),
            )
            for r in self.state.racers
        )
        return hash((self.state.current_racer_idx, racer_states))

    def advance_turn(self):
        if not self.state.race_active:
            return

        if self.state.next_turn_override is not None:
            next_idx = self.state.next_turn_override
            self.state.next_turn_override = None
            self.state.current_racer_idx = next_idx
            self.log_info(
                f"Turn Order Override: {self.get_racer(next_idx).repr} takes the next turn!",
            )
            return

        curr = self.state.current_racer_idx
        n = len(self.state.racers)
        next_idx = (curr + 1) % n

        start_search = next_idx
        while not self.state.racers[next_idx].active:
            next_idx = (next_idx + 1) % n
            if next_idx == start_search:
                self.state.race_active = False
                return

        if next_idx < curr:
            self.log_context.new_round()

        self.state.current_racer_idx = next_idx

    # --- Event Management ---
    def push_event(self, event: GameEvent, priority: int | None = None):
        if priority is not None:
            _priority = priority
        elif event.responsible_racer_idx is None:
            if (
                isinstance(event, EmitsAbilityTriggeredEvent)
                and event.emit_ability_triggered != "never"
            ):
                msg = f"Received a {event.__class__.__name__} with no responsible racer ID..."
                raise ValueError(msg)
            _priority = 0
        else:
            curr = self.state.current_racer_idx
            count = len(self.state.racers)
            _priority = 1 + ((event.responsible_racer_idx - curr) % count)

        if (
            self.current_processing_event
            and self.current_processing_event.event.phase == event.phase
        ):
            if self.current_processing_event.priority == 0:
                new_depth = self.current_processing_event.depth
            else:
                new_depth = self.current_processing_event.depth + 1
        else:
            new_depth = 0

        self.state.serial += 1
        sched = ScheduledEvent(
            new_depth,
            _priority,
            self.state.serial,
            event,
            mode=self.state.rules.timing_mode,
        )

        # Notify loop detector of the board state at creation time
        self.loop_detector.record_event_creation(
            sched.serial,
            self._calculate_board_hash(),
        )

        self.log_debug(f"{sched}")
        heapq.heappush(self.state.queue, sched)

        if (
            isinstance(event, EmitsAbilityTriggeredEvent)
            and event.emit_ability_triggered == "immediately"
        ):
            self.push_event(AbilityTriggeredEvent.from_event(event))

    def _rebuild_subscribers(self):
        self.subscribers.clear()
        for racer in self.state.racers:
            for ability in racer.active_abilities:
                ability.register(self, racer.idx)

    def subscribe(
        self,
        event_type: type[GameEvent],
        callback: AbilityCallback,
        owner_idx: int,
    ):
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        self.subscribers[event_type].append(Subscriber(callback, owner_idx))

    def _update_abilities(self, racer_idx: int, desired_list: list[Ability]) -> None:
        """
        Low-level reconciler. Makes racer.active_abilities (list[Ability]) match desired_list.
        Handles Lifecycle hooks and Subscription updates.
        """
        racer = self.get_racer(racer_idx)
        current_list = (
            racer.active_abilities.copy()
        )  # Make a copy to avoid stale references

        to_keep: list[Ability] = []
        to_add = list(desired_list)
        to_remove: list[Ability] = []

        # Diff Logic
        for current_ab in current_list:
            found = False
            for i, desired_ab in enumerate(to_add):
                if current_ab.matches_identity(desired_ab):
                    to_keep.append(
                        current_ab,
                    )  # Keep existing instance (preserves state)
                    to_add.pop(i)  # Consume this requirement
                    found = True
                    break
            if not found:
                to_remove.append(current_ab)

        # CRITICAL: Commit the new state BEFORE calling lifecycle hooks
        # This ensures nested _update_abilities calls see the correct state
        final_list = to_keep + to_add
        racer.active_abilities = final_list

        # 1. Process Removal (AFTER committing state)
        for ab in to_remove:
            if isinstance(ab, LifecycleManagedMixin):
                ab.on_loss(self, racer_idx)

            # Unsubscribe Logic
            for event_type in self.subscribers:
                self.subscribers[event_type] = [
                    sub
                    for sub in self.subscribers[event_type]
                    if not (
                        sub.owner_idx == racer_idx
                        and getattr(sub.callback, "__self__", None) == ab
                    )
                ]

        # 2. Process Addition (AFTER committing state)
        for ab in to_add:
            ab.register(self, racer_idx)
            if isinstance(ab, LifecycleManagedMixin):
                ab.on_gain(self, racer_idx)
                # Note: on_gain may call grant_ability, which calls _update_abilities again
                # But that's fine because we already committed the state above

        # 3. Subscriber Safety Net
        if to_remove or to_add:
            self._rebuild_subscribers()

    def publish_to_subscribers(self, event: GameEvent):
        if type(event) not in self.subscribers:
            return

        subs = self.subscribers[type(event)]
        curr = self.state.current_racer_idx
        count = len(self.state.racers)
        ordered_subs = sorted(subs, key=lambda s: (s.owner_idx - curr) % count)

        for sub in ordered_subs:
            sub.callback(event, sub.owner_idx, self)

    def dispatch_immediately(self, event: GameEvent) -> None:
        """Publish to subscribers immediately (PostMoveEvent, PostWarpEvent), bypassing the queue"""
        self.publish_to_subscribers(event)

        if self.on_event_processed:
            self.on_event_processed(self, event)

    def _handle_event(self, event: GameEvent):
        match event:
            case (
                AbilityTriggeredEvent()
                | AbilityRollResultEvent()
                | PreTurnStartEvent()
                | TurnStartEvent()
                | TurnEndEvent()
                | PassingEvent()
                | RollModificationWindowEvent()
                | RollResultEvent()
                | RacerFinishedEvent()
                | RacerEliminatedEvent()
            ):
                self.publish_to_subscribers(event)
            case TripCmdEvent():
                handle_trip_cmd(self, event)
            case MoveCmdEvent():
                handle_move_cmd(self, event)
            case SimultaneousMoveCmdEvent():
                handle_simultaneous_move_cmd(self, event)
            case WarpCmdEvent():
                handle_warp_cmd(self, event)
            case SimultaneousWarpCmdEvent():
                handle_simultaneous_warp_cmd(self, event)

            case PerformMainRollEvent():
                handle_perform_main_roll(self, event)

            case ResolveMainMoveEvent():
                self.publish_to_subscribers(event)
                resolve_main_move(self, event)
            case ExecuteMainMoveEvent():
                handle_execute_main_move(self, event)

            case _:
                pass

        if self.on_event_processed:
            self.on_event_processed(self, event)

    # -- Getters --
    def get_agent(self, racer_idx: int) -> Agent:
        return self.agents[racer_idx]

    def get_racer(self, idx: int) -> RacerState:
        return self.state.racers[idx]

    def get_active_racer(self, idx: int) -> ActiveRacerState | None:
        if is_active(racer := self.get_racer(idx)):
            return racer
        self.log_debug(
            f"Attempted to get position of {racer.repr} but they were already eliminated.",
        )
        return None

    def get_active_racers(
        self,
        except_racer_idx: int | None = None,
    ) -> list[ActiveRacerState]:
        return [
            r for r in self.state.racers if is_active(r) and r.idx != except_racer_idx
        ]

    def get_racer_pos(self, idx: int) -> int | None:
        if is_active(racer := self.state.racers[idx]):
            return racer.position
        return None

    def get_racers_at_position(
        self,
        tile_idx: int,
        except_racer_idx: int | None = None,
    ) -> list[ActiveRacerState]:
        if except_racer_idx is None:
            return [
                r for r in self.state.racers if is_active(r) and r.position == tile_idx
            ]
        else:
            return [
                r
                for r in self.state.racers
                if is_active(r) and r.position == tile_idx and r.idx != except_racer_idx
            ]

    def skip_main_move(
        self,
        *,
        responsible_racer_idx: int,
        source: Source,
        skipped_racer_idx: int,
    ) -> None:
        """
        Marks the racer's main move as consumed and emits a notification event.
        Does nothing if the move was already consumed.
        """
        racer = self.get_racer(skipped_racer_idx)
        if not racer.main_move_consumed:
            racer.main_move_consumed = True
            self.log_info(
                f"{racer.repr} has their main move skipped (Source: {source}).",
            )
            self.push_event(
                MainMoveSkippedEvent(
                    responsible_racer_idx=responsible_racer_idx,
                    source=source,
                    target_racer_idx=skipped_racer_idx,
                ),
            )

    def draw_racers(self, k: int) -> tuple[RacerStat, ...]:
        if k > len(self.state.available_racers):
            self.state.shuffle()  # shuffle cards back in pile

        drawn_racers = self.state.draw_racers(k, rng=self.rng)
        return tuple(
            stat
            for _, stat in get_all_racer_stats(self.log_error).items()
            if stat.racer_name in drawn_racers
        )

    # -- Abilities --

    def instantiate_racer_abilities(self, racer_name: RacerName) -> list[Ability]:
        """
        Factory that creates fresh instances of a racer's default abilities.
        """

        ability_names = RACER_ABILITIES.get(racer_name, set())
        instances: list[Ability] = []
        classes = get_ability_classes()

        for name in ability_names:
            cls = classes.get(name)
            if cls:
                instances.append(cls(name=name))

        return instances

    def replace_core_abilities(
        self,
        racer_idx: int,
        new_core_instances: list[Ability],
    ) -> None:
        """
        Updates the racer's Intrinsic (Identity) abilities.
        Preserves any ability that inherits from ExternalAbilityMixin.
        """
        racer = self.get_racer(racer_idx)

        # 1. Keep the buffs (The ones that opt-in to being External)
        external_abilities = [
            ab for ab in racer.active_abilities if isinstance(ab, ExternalAbilityMixin)
        ]

        # 2. Combine with new identity
        final_list = external_abilities + new_core_instances

        # 3. Reconcile
        self._update_abilities(racer_idx, final_list)

    def grant_ability(self, target_idx: int, ability_instance: Ability) -> None:
        """Adds an external ability instance."""
        racer = self.get_racer(target_idx)
        new_list = [*racer.active_abilities, ability_instance]
        self._update_abilities(target_idx, new_list)

    def revoke_ability(self, target_idx: int, ability_instance: Ability) -> None:
        """Removes a specific external ability instance."""
        racer = self.get_racer(target_idx)
        # Filter out THIS specific instance using matches_identity
        new_list = [
            ab
            for ab in racer.active_abilities
            if not ab.matches_identity(ability_instance)
        ]
        self._update_abilities(target_idx, new_list)

    def clear_all_abilities(self, racer_idx: int) -> None:
        """Removes ALL abilities."""
        self._update_abilities(racer_idx, [])

    # -- Logging --
    def _log(self, level: int, msg: str, *args: Any, **kwargs: Any) -> None:
        if not self.verbose:
            return
        self._logger.log(level, msg, *args, **kwargs)

    def log_debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.DEBUG, msg, *args, **kwargs)

    def log_info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.INFO, msg, *args, **kwargs)

    def log_warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.WARNING, msg, *args, **kwargs)

    def log_error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        self._log(logging.ERROR, msg, *args, **kwargs)
