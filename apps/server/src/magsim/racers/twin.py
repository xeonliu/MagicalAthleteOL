from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, override

from magsim.core.abilities import Ability, copied_racer_repr
from magsim.core.agent import (
    Agent,
    SelectionDecisionContext,
    SelectionDecisionMixin,
    SelectionInteractive,
)
from magsim.core.events import TurnStartEvent
from magsim.core.mixins import SetupPhaseMixin
from magsim.core.types import RacerName, RacerStat
from magsim.racers import get_all_racer_stats

if TYPE_CHECKING:
    from magsim.core.events import (
        AbilityTriggeredEventOrSkipped,
        GameEvent,
    )
    from magsim.core.state import ActiveRacerState
    from magsim.core.types import AbilityName
    from magsim.engine.game_engine import GameEngine


@dataclass
class TwinCopyAbility(Ability, SetupPhaseMixin, SelectionDecisionMixin[RacerStat]):
    name: AbilityName = "TwinCopy"
    triggers: tuple[type[GameEvent], ...] = (TurnStartEvent,)

    copied_racer: RacerName | None = None

    def _copied_racer_repr(self, owner: ActiveRacerState) -> str:
        return copied_racer_repr(self, owner)

    @override
    def execute(
        self,
        event: GameEvent,
        owner: ActiveRacerState,
        engine: GameEngine,
        agent: Agent,
    ) -> AbilityTriggeredEventOrSkipped:
        if (
            isinstance(event, TurnStartEvent)
            and owner.idx == event.target_racer_idx
            and self.copied_racer is not None
        ):
            engine.log_info(
                f"{owner.repr} acts as {self._copied_racer_repr(owner)}.",
            )
        return "skip_trigger"

    @override
    def on_setup(
        self,
        engine: GameEngine,
        owner: ActiveRacerState,
        agent: Agent,
    ) -> None:
        stats = get_all_racer_stats()
        winners = [stats[name] for name in dict.fromkeys(getattr(engine.state, "previous_winners", ()))
                   if name in stats and name != "Twin"]
        if not winners:
            engine.log_info(f"{owner.repr} has no previous race winner to copy.")
            return

        picked_racer = agent.make_selection_decision(
            engine,
            ctx=SelectionDecisionContext[
                SelectionInteractive[RacerStat],
                RacerStat,
            ](
                source=self,
                event=None,
                game_state=engine.state,
                source_racer_idx=owner.idx,
                options=winners,
            ),
        )
        if picked_racer is None:
            raise AssertionError(
                "Twin should always have a target to pick.",
            )

        engine.log_info(f"{owner.repr} picked {picked_racer.racer_name}!")
        self.copied_racer = picked_racer.racer_name
        engine.state.remove_racers([picked_racer.racer_name])

        # Instantiate fresh abilities
        new_core = engine.instantiate_racer_abilities(picked_racer.racer_name)
        # Keep Twin ability
        new_core.append(self)

        engine.replace_core_abilities(owner.idx, new_core)

    @override
    def get_baseline_selection_decision(
        self,
        engine: GameEngine,
        ctx: SelectionDecisionContext[Self, RacerStat],
    ) -> RacerStat | None:
        return max(ctx.options, key=lambda r: r.avg_vp)

    @override
    def get_auto_selection_decision(
        self,
        engine: GameEngine,
        ctx: SelectionDecisionContext[Self, RacerStat],
    ) -> RacerStat | None:
        return self.get_baseline_selection_decision(engine, ctx)
