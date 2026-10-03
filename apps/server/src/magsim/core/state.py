from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Protocol, TypeGuard, runtime_checkable

from magsim.core.registry import RACER_ABILITIES

if TYPE_CHECKING:
    import random

    from magsim.core.abilities import Ability
    from magsim.core.events import ScheduledEvent
    from magsim.core.modifiers import RacerModifier
    from magsim.core.types import AbilityName, D6Values, RacerName
    from magsim.engine.board import Board

TimingMode = Literal["FLAT", "DFS", "BFS"]


@dataclass(slots=True)
class GameRules:
    winner_vp: tuple[int, int] = (4, 2)
    timing_mode: TimingMode = "DFS"
    count_0_moves_for_ability_triggered: bool = False
    hr_mastermind_steal_1st: bool = False


@dataclass(slots=True)
class RollState:
    serial_id: int = 0
    dice_value: D6Values | None = None
    base_value: int = 0
    final_value: int = 0
    dice_values: tuple[D6Values, ...] = ()
    dice_result_ids: tuple[str, ...] = ()
    roll_session_id: str | None = None
    roll_result_id: str | None = None


@runtime_checkable
class ActiveRacerState(Protocol):
    idx: int
    name: RacerName
    position: int  # NARROWED: Must be int
    victory_points: int
    tripped: bool
    tripping_racers: list[int | None]
    main_move_consumed: bool
    roll_override: tuple[AbilityName, int] | None
    can_reroll: bool
    modifiers: list[RacerModifier]
    active_abilities: list[Ability]

    @property
    def repr(self) -> str: ...
    @property
    def abilities(self) -> set[AbilityName]: ...

    def eliminate(self) -> None: ...


@dataclass(slots=True)
class RacerState:
    idx: int
    name: RacerName

    # game state
    position: int | None = 0
    victory_points: int = 0
    tripped: bool = False
    tripping_racers: list[int | None] = field(default_factory=list)

    # rolls
    main_move_consumed: bool = False
    roll_override: tuple[AbilityName, int] | None = None
    can_reroll: bool = True

    # finished
    finish_position: int | None = None
    eliminated: bool = False

    # abilities and modifiers
    modifiers: list[RacerModifier] = field(default_factory=list)
    active_abilities: list[Ability] = field(default_factory=list)

    @property
    def repr(self) -> str:
        return f"{self.position if self.position else ''}•{self.name}"

    @property
    def abilities(self) -> set[AbilityName]:
        """Derive from active instances."""
        return {a.name for a in self.active_abilities}

    @property
    def finished(self) -> bool:
        return self.finish_position is not None

    @property
    def active(self) -> bool:
        return not self.finished and not self.eliminated and self.position is not None

    def eliminate(self) -> None:
        self.position = None
        self.eliminated = True


def is_active(racer_state: RacerState) -> TypeGuard[ActiveRacerState]:
    """
    Runtime check that guarantees position is not None.
    Use this in 'if' conditions to narrow the type.
    """
    return (
        racer_state.position is not None
        and not racer_state.eliminated
        and not racer_state.finished
    )


@dataclass(slots=True)
class GameState:
    racers: list[RacerState]
    board: Board
    rules: GameRules = field(default_factory=GameRules)
    current_racer_idx: int = 0
    next_turn_override: int | None = None
    roll_state: RollState = field(default_factory=RollState)

    queue: list[ScheduledEvent] = field(default_factory=list)
    serial: int = 0
    race_active: bool = False
    history: set[int] = field(default_factory=set)
    _drawn_racers: set[RacerName] = field(default_factory=set)
    _removed_racers: set[RacerName] = field(default_factory=set)
    previous_winners: tuple[RacerName, ...] = ()

    @property
    def unavailable_racers(self) -> frozenset[RacerName]:
        active_names: set[RacerName] = {r.name for r in self.racers}
        return (
            frozenset(active_names)
            .union(self._drawn_racers)
            .union(self._removed_racers)
        )

    @property
    def available_racers(self) -> frozenset[RacerName]:
        """Available = every racer - unavailable racers"""
        return frozenset(RACER_ABILITIES.keys()).difference(self.unavailable_racers)

    def draw_racers(self, k: int, *, rng: random.Random) -> frozenset[RacerName]:
        """Draw k racers that are available"""
        drawn_racers = rng.sample(
            sorted(self.available_racers),  # sort for pseudo RNG
            k=k,
        )
        self._drawn_racers = self._drawn_racers.union(set(drawn_racers))
        return frozenset(drawn_racers)

    def remove_racers(self, racers_to_remove: list[RacerName]) -> None:
        """Remove racers from the game (e.g. by picking them via ability)"""
        self._removed_racers = self._removed_racers.union(set(racers_to_remove))

    def shuffle(self) -> None:
        """Shuffle deck of drawn racers back to pile"""
        self._drawn_racers = set()

    def get_state_hash(self) -> int:
        """Hash entire game state including racers, board, and semantic queue content."""
        racer_data = tuple(
            (
                r.idx,
                r.position,
                r.tripped,
                r.finish_position,
                r.eliminated,
                r.victory_points,
                frozenset(r.abilities),
                frozenset(m.name for m in r.modifiers),
            )
            for r in self.racers
        )

        board_data = frozenset(
            (tile, frozenset(m.name for m in mods))
            for tile, mods in self.board.dynamic_modifiers.items()
        )

        roll_data = (self.roll_state.serial_id, self.roll_state.base_value)

        queue_data = tuple(
            sorted((se.event.phase, se.priority, repr(se.event)) for se in self.queue),
        )

        return hash((racer_data, board_data, roll_data, queue_data))


@dataclass(frozen=True)
class TurnOutcome:
    """Result of simulating exactly one turn for a specific racer."""

    vp_delta: list[int]  # per racer: final_vp - start_vp
    position: list[int]  # per racer final positions
    tripped: list[bool]  # per racer tripped flags at end of turn
    eliminated: list[bool]  # per racer eliminated flags at end of turn
    start_position: list[int]  # per racer start positions


@dataclass(slots=True)
class LogContext:
    """Per-game logging state."""

    engine_id: int
    engine_level: int

    total_turn: int = 0
    turn_log_count: int = 0
    current_racer_repr: str = "_"

    parent_engine_id: int | None = None

    def new_round(self):
        self.total_turn += 1

    def start_turn_log(self, racer_repr: str):
        self.turn_log_count = 0
        self.current_racer_repr = racer_repr

    def inc_log_count(self):
        self.turn_log_count += 1
