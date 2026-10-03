from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, override
from uuid import uuid4

from magsim.core.agent import Agent, DecisionContext, SelectionDecisionContext


class DecisionRequired(Exception):
    """Control-flow signal used to pause resolution at an interactive choice."""


class RollRequired(Exception):
    """Control-flow signal used to pause resolution until the next die is thrown."""


RollKind = Literal["MAIN_ROLL", "ABILITY_ROLL"]


@dataclass(slots=True)
class CompletedRoll:
    id: str
    kind: RollKind
    ability_name: str | None
    participants: tuple[int, ...]
    values: tuple[int, ...]

    def result_id(self, index: int) -> str:
        return f"{self.id}:throw:{index}"


@dataclass(slots=True)
class SubmittedRoll:
    session_id: str
    result_id: str
    kind: RollKind
    ability_name: str | None
    participant_racer_idx: int
    throw_index: int
    throw_count: int
    value: int


@dataclass(slots=True)
class PendingRoll:
    id: str
    key: tuple[Any, ...]
    kind: RollKind
    ability_name: str | None
    participants: tuple[int, ...]
    values: list[int] = field(default_factory=list)

    @property
    def next_index(self) -> int:
        return len(self.values)

    @property
    def complete(self) -> bool:
        return len(self.values) == len(self.participants)


@dataclass(slots=True)
class RollBroker:
    pending: PendingRoll | None = None

    def request(
        self,
        *,
        key: tuple[Any, ...],
        kind: RollKind,
        participants: tuple[int, ...],
        ability_name: str | None = None,
    ) -> CompletedRoll:
        if self.pending is None:
            self.pending = PendingRoll(
                id=uuid4().hex,
                key=key,
                kind=kind,
                ability_name=ability_name,
                participants=participants,
            )
            raise RollRequired

        pending = self.pending
        if pending.key != key:
            raise RuntimeError("a different roll session is already pending")
        if not pending.complete:
            raise RollRequired
        return CompletedRoll(
            id=pending.id,
            kind=pending.kind,
            ability_name=pending.ability_name,
            participants=pending.participants,
            values=tuple(pending.values),
        )

    def submit(self, value: int) -> SubmittedRoll:
        pending = self.pending
        if pending is None or pending.complete:
            raise ValueError("NO_PENDING_ROLL")
        index = pending.next_index
        pending.values.append(value)
        return SubmittedRoll(
            session_id=pending.id,
            result_id=f"{pending.id}:throw:{index}",
            kind=pending.kind,
            ability_name=pending.ability_name,
            participant_racer_idx=pending.participants[index],
            throw_index=index,
            throw_count=len(pending.participants),
            value=value,
        )

    def commit(self) -> None:
        if self.pending is not None and self.pending.complete:
            self.pending = None


def _choice_label(value: Any) -> str:
    for attribute in ("racer_name", "name", "repr"):
        label = getattr(value, attribute, None)
        if label:
            return str(label)
    return str(value)


# These target-selection abilities explicitly support returning None to decline.
OPTIONAL_SELECTION_ABILITIES = frozenset({
    "DuelistDuel", "FlipFlopSwap", "HypnotistWarp", "ThirdWheelJoin",
})


@dataclass(slots=True)
class PendingChoice:
    id: str
    racer_idx: int
    ability_name: str
    prompt: str
    choice_type: str
    options: tuple[Any, ...]
    option_labels: tuple[str, ...]
    roll_preview: dict[str, Any] | None = None
    answer_index: int | None = None
    auto_answer: bool = False
    effect_preview: dict[str, Any] | None = None

    def public_options(self) -> list[dict[str, str]]:
        options = [
            {"id": str(index), "label": label}
            for index, label in enumerate(self.option_labels)
        ]
        if self.ability_name in OPTIONAL_SELECTION_ABILITIES:
            options.append({"id": "skip", "label": "skip"})
        return options


@dataclass(slots=True)
class DecisionBroker:
    pending: PendingChoice | None = None
    last_resolved: PendingChoice | None = None
    resolved_choices: list[PendingChoice] = field(default_factory=list)
    replay_index: int = 0

    def rewind(self) -> None:
        # Older persisted brokers kept only one resolved answer.
        if not hasattr(self, "resolved_choices"):
            self.resolved_choices = [self.last_resolved] if self.last_resolved else []
        self.replay_index = 0

    def request(
        self,
        ctx: DecisionContext[Any],
        options: tuple[Any, ...],
        labels: tuple[str, ...],
        choice_type: str,
    ) -> Any:
        ability_name = str(getattr(ctx.source, "name", type(ctx.source).__name__))
        signature = (ctx.source_racer_idx, ability_name, choice_type)
        if self.replay_index < len(self.resolved_choices):
            resolved = self.resolved_choices[self.replay_index]
            if signature != (resolved.racer_idx, resolved.ability_name, resolved.choice_type):
                raise RuntimeError("decision replay order changed")
            self.replay_index += 1
            return None if resolved.answer_index == -2 else options[resolved.answer_index]
        if self.pending is None:
            roll_state = ctx.game_state.roll_state
            roll_serial = getattr(ctx.event, "roll_serial", None)
            roll_preview = None
            if roll_serial is not None and (
                getattr(ctx.event, "current_roll_val", None) is not None
                or getattr(ctx.event, "dice_value", None) is not None
            ):
                roll_preview = {
                    "rollSerial": roll_serial,
                    "value": roll_state.dice_value or roll_state.base_value,
                    "baseValue": roll_state.base_value,
                    "finalValue": roll_state.final_value,
                    "rollSessionId": roll_state.roll_session_id,
                    "rollResultId": roll_state.roll_result_id,
                }
            self.pending = PendingChoice(
                id=uuid4().hex,
                racer_idx=ctx.source_racer_idx,
                ability_name=ability_name,
                # Keep this field for wire compatibility; the client translates
                # the stable ability_name instead of receiving display text here.
                prompt="",
                choice_type=choice_type,
                options=options,
                option_labels=labels,
                roll_preview=roll_preview,
                effect_preview={
                    "racerIndex": ctx.event.target_racer_idx,
                    "from": ctx.event.start_tile,
                    "to": ctx.event.end_tile,
                } if ability_name == "SuckerfishRide" and ctx.event is not None else None,
            )
            raise DecisionRequired

        current = self.pending
        if signature != (current.racer_idx, current.ability_name, current.choice_type):
            raise DecisionRequired
        if current.answer_index is None:
            raise DecisionRequired

        index = current.answer_index
        if index == -2:
            self.last_resolved = current
            self.resolved_choices.append(current)
            self.replay_index += 1
            self.pending = None
            return None
        auto = current.auto_answer
        resolved = PendingChoice(
            id=current.id,
            racer_idx=current.racer_idx,
            ability_name=current.ability_name,
            prompt=current.prompt,
            choice_type=current.choice_type,
            options=options,
            option_labels=labels,
            roll_preview=current.roll_preview,
            answer_index=index,
            auto_answer=auto,
            effect_preview=getattr(current, "effect_preview", None),
        )
        self.last_resolved = resolved
        self.resolved_choices.append(resolved)
        self.replay_index += 1
        self.pending = None
        return options[index]

    def commit(self) -> None:
        self.last_resolved = None
        self.resolved_choices.clear()
        self.replay_index = 0

    def choose(self, decision_id: str, option_id: str) -> PendingChoice:
        pending = self.pending
        if pending is None or pending.id != decision_id:
            raise ValueError("STALE_DECISION")
        if option_id == "skip" and pending.ability_name in OPTIONAL_SELECTION_ABILITIES:
            pending.answer_index = -2
            return pending
        try:
            index = int(option_id)
        except ValueError as error:
            raise ValueError("INVALID_DECISION_OPTION") from error
        if not 0 <= index < len(pending.options):
            raise ValueError("INVALID_DECISION_OPTION")
        pending.answer_index = index
        return pending

    def choose_smart(self, engine: Any) -> PendingChoice:
        pending = self.pending
        if pending is None:
            raise ValueError("NO_PENDING_DECISION")
        source = pending.options  # Keep the public pending object stable while evaluating.
        _ = source
        # Replaying with this marker lets the interactive agent evaluate against the
        # restored engine and context, rather than stale objects from the first attempt.
        pending.answer_index = -1
        pending.auto_answer = True
        return pending


@dataclass(slots=True)
class InteractiveAgent(Agent):
    broker: DecisionBroker = field(default_factory=DecisionBroker)

    def __deepcopy__(self, memo: dict[int, Any]) -> InteractiveAgent:
        # The broker is an out-of-transaction control channel. Engine rollback must
        # not erase the pending choice or a submitted answer.
        return self

    @override
    def make_boolean_decision(self, engine: Any, ctx: DecisionContext[Any]) -> bool:
        pending = self.broker.pending
        if (self.broker.replay_index == len(self.broker.resolved_choices)
            and pending is not None and pending.answer_index == -1
            and pending.racer_idx == ctx.source_racer_idx
            and pending.ability_name == str(ctx.source.name)):
            result = ctx.source.get_auto_boolean_decision(engine, ctx)
            pending.answer_index = 1 if result else 0
        return bool(
            self.broker.request(
                ctx,
                (False, True),
                ("skip", "use"),
                "BOOLEAN",
            )
        )

    @override
    def make_selection_decision(self, engine: Any, ctx: SelectionDecisionContext[Any, Any]) -> Any:
        options = tuple(ctx.options)
        if not options:
            return None
        pending = self.broker.pending
        if (self.broker.replay_index == len(self.broker.resolved_choices)
            and pending is not None and pending.answer_index == -1
            and pending.racer_idx == ctx.source_racer_idx
            and pending.ability_name == str(ctx.source.name)):
            recommended = ctx.source.get_auto_selection_decision(engine, ctx)
            if recommended is None:
                pending.answer_index = -2
                return self.broker.request(
                    ctx, options, tuple(_choice_label(option) for option in options), pending.choice_type
                )
            try:
                pending.answer_index = options.index(recommended)
            except ValueError:
                pending.answer_index = 0
        choice_type = str(getattr(ctx.source, "choice_type", "RACER"))
        if options and all(isinstance(option, int) for option in options):
            choice_type = str(
                getattr(
                    ctx.source,
                    "choice_type",
                    "DIE" if "Genius" in str(getattr(ctx.source, "name", "")) else "TILE",
                )
            )
        return self.broker.request(
            ctx,
            options,
            tuple(_choice_label(option) for option in options),
            choice_type,
        )
