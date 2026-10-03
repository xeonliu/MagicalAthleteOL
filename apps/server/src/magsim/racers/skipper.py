from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from magsim.core.abilities import Ability
from magsim.core.events import (
    AbilityTriggeredEvent,
    AbilityTriggeredEventOrSkipped,
    GameEvent,
    RollResultEvent,
)

if TYPE_CHECKING:
    from magsim.core.agent import Agent
    from magsim.core.state import ActiveRacerState
    from magsim.core.types import AbilityName, D6VAlueSet
    from magsim.engine.game_engine import GameEngine


@dataclass
class AbilitySkipper(Ability):
    name: AbilityName = "SkipperTurn"
    triggers: tuple[type[GameEvent], ...] = (RollResultEvent,)
    preferred_dice: D6VAlueSet = frozenset([1, 5, 6])

    @override
    def execute(
        self,
        event: GameEvent,
        owner: ActiveRacerState,
        engine: GameEngine,
        agent: Agent,
    ) -> AbilityTriggeredEventOrSkipped:
        if not isinstance(event, RollResultEvent):
            return "skip_trigger"

        if event.dice_value == 1:
            engine.state.extra_turn_queue.append(owner.idx)
            engine.log_info(
                f"{owner.repr} saw a 1 and gains an immediate extra turn using {self.name}!",
            )

            return AbilityTriggeredEvent(
                responsible_racer_idx=owner.idx,
                source=self.name,
                phase=event.phase,
                target_racer_idx=owner.idx,
            )

        return "skip_trigger"
