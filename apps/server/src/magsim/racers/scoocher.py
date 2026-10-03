from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, override

from magsim.core.abilities import Ability
from magsim.core.events import (
    AbilityTriggeredEvent,
    AbilityTriggeredEventOrSkipped,
    GameEvent,
)
from magsim.engine.movement import push_move

if TYPE_CHECKING:
    from magsim.core.agent import Agent
    from magsim.core.state import ActiveRacerState, RacerState
    from magsim.core.types import AbilityName
    from magsim.engine.game_engine import GameEngine


@dataclass
class AbilityScoochStep(Ability):
    name: AbilityName = "ScoochStep"
    triggers: tuple[type[GameEvent], ...] = (AbilityTriggeredEvent,)

    @override
    def execute(
        self,
        event: GameEvent,
        owner: ActiveRacerState,
        engine: GameEngine,
        agent: Agent,
    ) -> AbilityTriggeredEventOrSkipped:
        # React to other racers, once each within the same ScoochStep chain.
        if (
            not isinstance(event, AbilityTriggeredEvent)
            or event.responsible_racer_idx == owner.idx
        ):
            return "skip_trigger"

        reactors = getattr(event, "scooch_reactors", None)
        if reactors is None:
            # Queued events saved before this field was added can still resume.
            reactors = set()
            object.__setattr__(event, "scooch_reactors", reactors)
        if owner.idx in reactors:
            return "skip_trigger"
        reactors.add(owner.idx)

        source_racer: RacerState = engine.get_racer(event.responsible_racer_idx)

        target_msg = (
            ""
            if event.target_racer_idx is None
            or event.target_racer_idx == event.responsible_racer_idx
            else f" on {engine.get_racer(event.target_racer_idx).repr}"
        )

        engine.log_info(
            f"{owner.repr} saw {source_racer.repr} use {event.source}{target_msg} -> Queue Moving 1",
        )
        push_move(
            engine,
            1,
            phase=event.phase,
            moved_racer_idx=owner.idx,
            source=self.name,
            responsible_racer_idx=owner.idx,
            emit_ability_triggered="after_resolution",
            scooch_reactors=reactors,
        )
        return "skip_trigger"
