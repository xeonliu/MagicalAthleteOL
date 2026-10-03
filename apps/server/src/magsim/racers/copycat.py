from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Self, override

from magsim.core.abilities import (
    Ability,
    CopyAbilityProtocol,
    copied_racer_repr,
)
from magsim.core.agent import (
    Agent,
    SelectionDecisionContext,
    SelectionDecisionMixin,
    SelectionInteractive,
)
from magsim.core.events import (
    AbilityTriggeredEvent,
    AbilityTriggeredEventOrSkipped,
    GameEvent,
    PostMoveEvent,
    PostWarpEvent,
    RacerEliminatedEvent,
    RacerFinishedEvent,
    TurnStartEvent,
)
from magsim.core.state import ActiveRacerState, RacerState, is_active
from magsim.racers import get_all_racer_stats

if TYPE_CHECKING:
    from magsim.core.types import AbilityName, RacerName, RacerStat
    from magsim.engine.game_engine import GameEngine


@dataclass
class AbilityCopyLead(Ability, SelectionDecisionMixin[ActiveRacerState]):
    name: AbilityName = "CopyLead"
    triggers: tuple[type[GameEvent], ...] = (
        TurnStartEvent,
        PostMoveEvent,
        PostWarpEvent,
        RacerFinishedEvent,
        RacerEliminatedEvent,
    )

    current_copied_racer: RacerState | Literal["start_of_game"] | None = "start_of_game"

    @property
    def copied_racer(self) -> RacerName | None:
        """Expose the current target through the shared copy-ability contract."""
        if isinstance(self.current_copied_racer, RacerState):
            return self.current_copied_racer.name
        return None

    @property
    def _current_copied_racer_repr(self) -> str:
        if not isinstance(self.current_copied_racer, RacerState):
            msg = f"Unexpected type for self.current_copied_racer {type(self.current_copied_racer)}"
            raise TypeError(msg)

        # first check if the copied racer has a copy ability
        try:
            deep_copying_ability = next(
                a
                for a in self.current_copied_racer.active_abilities
                if isinstance(a, CopyAbilityProtocol)
            )
        except StopIteration:
            # if the racer doesn't copy anyone, just return his repr
            return self.current_copied_racer.repr

        return f"{self.current_copied_racer.repr} ({copied_racer_repr(copying_ability=deep_copying_ability, copying_racer=self.current_copied_racer)})"

    @override
    def execute(
        self,
        event: GameEvent,
        owner: ActiveRacerState,
        engine: GameEngine,
        agent: Agent,
    ) -> AbilityTriggeredEventOrSkipped:
        if not isinstance(
            event,
            (
                TurnStartEvent,
                PostWarpEvent,
                PostMoveEvent,
                RacerFinishedEvent,
                RacerEliminatedEvent,
            ),
        ):
            return "skip_trigger"

        # Only for logging at start of own turn
        if isinstance(event, TurnStartEvent) and owner.idx == event.target_racer_idx:
            if self.current_copied_racer is None:
                engine.log_info(
                    f"{owner.repr} is in the sole lead and doesn't copy anyone.",
                )
            elif self.current_copied_racer == "start_of_game":
                pass
            else:
                engine.log_info(
                    f"{owner.repr} currently copies the behaviour of {self._current_copied_racer_repr}.",
                )

        # 1. Determine leaders
        active = [r for r in engine.state.racers if is_active(r)]
        max_pos = max(r.position for r in active)
        valid_targets = engine.get_racers_at_position(
            max_pos,
            except_racer_idx=owner.idx,
        )

        # 2. If Copycat leads, they lose abilities
        if not valid_targets:
            if (
                self.current_copied_racer is None
                or self.current_copied_racer == "start_of_game"
            ):
                # We are already in the correct state. Do nothing.
                return "skip_trigger"

            engine.replace_core_abilities(owner.idx, [self])
            engine.log_info(
                f"{owner.repr} is in the sole lead and loses {self._current_copied_racer_repr} ability.",
            )
            self.current_copied_racer = None
            return "skip_trigger"

        # Sort for deterministic behavior
        valid_targets.sort(key=lambda r: r.idx)

        # 3. Ask the Agent which leader to copy, unless there is no real choice.
        if len(valid_targets) == 1:
            target = valid_targets[0]
        else:
            target = agent.make_selection_decision(
                engine,
                SelectionDecisionContext[
                    SelectionInteractive[ActiveRacerState],
                    ActiveRacerState,
                ](
                    source=self,
                    event=event,
                    game_state=engine.state,
                    source_racer_idx=owner.idx,
                    options=valid_targets,
                ),
            )

        # Nothing new to copy
        if target is None:
            engine.log_warning(
                f"{owner.repr} did not copy anyone.",
            )
            return "skip_trigger"

        if target.abilities == owner.abilities.difference(
            {self.name},
        ):
            return "skip_trigger"

        self.current_copied_racer = engine.get_racer(target.idx)

        engine.log_info(
            f"{owner.repr} decided to copy {self._current_copied_racer_repr} using {self.name}!",
        )

        # 4. Perform the Update
        # Get fresh instances for the target
        new_core = engine.instantiate_racer_abilities(target.name)
        # Add Self (Copycat ability)
        new_core.append(self)

        # Update
        engine.replace_core_abilities(owner.idx, new_core)

        return AbilityTriggeredEvent(
            responsible_racer_idx=owner.idx,
            source=self.name,
            phase=event.phase,
            target_racer_idx=target.idx,
        )

    @override
    def get_baseline_selection_decision(
        self,
        engine: GameEngine,
        ctx: SelectionDecisionContext[Self, ActiveRacerState],
    ) -> ActiveRacerState:
        # Always return the first option (deterministic tie-break)
        # options are already sorted by idx in execute()
        return ctx.options[0]

    @override
    def get_auto_selection_decision(
        self,
        engine: GameEngine,
        ctx: SelectionDecisionContext[Self, ActiveRacerState],
    ) -> ActiveRacerState:
        if len(ctx.options) == 1:
            return ctx.options[0]
        candidates: list[RacerStat] = [
            stats
            for name, stats in get_all_racer_stats().items()
            if name in [r.name for r in ctx.options]
        ]
        highest_winrate_racer: RacerName = max(
            candidates,
            key=lambda r: r.winrate,
        ).racer_name
        return next(r for r in ctx.options if r.name == highest_winrate_racer)
