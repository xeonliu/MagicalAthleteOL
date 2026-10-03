from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Self, override

from magsim.core.abilities import Ability
from magsim.core.agent import (
    SelectionDecisionContext,
    SelectionDecisionMixin,
    SelectionInteractive,
)
from magsim.core.events import (
    AbilityTriggeredEvent,
    AbilityTriggeredEventOrSkipped,
    GameEvent,
    MainMoveSkippedEvent,
    RollResultEvent,
    TurnStartEvent,
)

if TYPE_CHECKING:
    from magsim.core.agent import Agent
    from magsim.core.state import ActiveRacerState
    from magsim.core.types import AbilityName, D6VAlueSet
    from magsim.engine.game_engine import GameEngine


@dataclass
class AbilityGenius(Ability, SelectionDecisionMixin[int]):
    name: AbilityName = "GeniusPrediction"
    triggers: tuple[type[GameEvent], ...] = (
        TurnStartEvent,
        RollResultEvent,
    )
    preferred_dice: D6VAlueSet = frozenset([6])

    # Persistent State
    prediction: int | None = None

    @override
    def execute(
        self,
        event: GameEvent,
        owner: ActiveRacerState,
        engine: GameEngine,
        agent: Agent,
    ) -> AbilityTriggeredEventOrSkipped:
        if (
            not isinstance(event, (TurnStartEvent, RollResultEvent))
            or event.target_racer_idx != owner.idx
        ):
            return "skip_trigger"

        # 1. Prediction Phase (Turn Start)
        if isinstance(event, TurnStartEvent):
            if owner.main_move_consumed or engine.state.current_racer_idx != owner.idx:
                self.prediction = None
                return "skip_trigger"

            self.prediction = agent.make_selection_decision(
                engine,
                ctx=SelectionDecisionContext[
                    SelectionInteractive[int],
                    int,
                ](
                    source=self,
                    event=event,
                    game_state=engine.state,
                    source_racer_idx=owner.idx,
                    options=list(range(1, 7)),
                ),
            )

            engine.log_info(f"{owner.repr} predicts a roll of {self.prediction}.")
            return AbilityTriggeredEvent(
                responsible_racer_idx=owner.idx,
                source=self.name,
                phase=event.phase,
                target_racer_idx=owner.idx,
            )

        # Check the resolved die face, after any rerolls. Movement bonuses and
        # overrides are not dice results; a skipped roll has dice_value=None.
        elif self.prediction is not None and event.dice_value == self.prediction:
            engine.log_info(
                f"{self.name}: Prediction correct! {owner.repr} gets an extra turn.",
            )

            # Set the override.
            engine.state.next_turn_override = owner.idx

            # Track dice manipulation
            if engine.on_event_processed is not None:
                for skipped_racer_idx in [
                    r.idx
                    for r in engine.state.racers
                    if r.active and r.idx != owner.idx
                ]:
                    engine.on_event_processed(
                        engine,
                        MainMoveSkippedEvent(
                            target_racer_idx=skipped_racer_idx,
                            source=self.name,
                            responsible_racer_idx=owner.idx,
                        ),
                    )

            # predicting = using the power
            # https://boardgamegeek.com/thread/3595157/article/46761348#46761348
            return "skip_trigger"

        return "skip_trigger"

    @override
    def get_baseline_selection_decision(
        self,
        engine: GameEngine,
        ctx: SelectionDecisionContext[Self, int],
    ) -> int:
        self.preferred_dice = frozenset([6])
        return 6

    @override
    def get_auto_selection_decision(
        self,
        engine: GameEngine,
        ctx: SelectionDecisionContext[Self, int],
    ) -> int:
        
        if (owner := engine.get_active_racer(ctx.source_racer_idx)) is None:
            return 6  # Fallback

        # Find out if we are in the lead
        active_racers = engine.get_active_racers()
        max_pos = max((r.position for r in active_racers), default=0)

        skipper_ability: AbilityName = "SkipperTurn"
        if owner.position >= max_pos:
            if any(skipper_ability in r.abilities for r in active_racers if r.idx != owner.idx):
                # Conservative, but avoiding Skipper
                prediction = 2
                self.preferred_dice = frozenset([2, 4, 5, 6])
            else:
                # Standard conservative hedge
                prediction = 1
                self.preferred_dice = frozenset([1, 4, 5, 6])
        else:
            # Aggressive catch-up
            prediction = 6
            self.preferred_dice = frozenset([6])

        return prediction

