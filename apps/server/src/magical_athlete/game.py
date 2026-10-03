from __future__ import annotations

import random
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any, Protocol

from .athletes import ATHLETE_BY_ID, ATHLETE_CATALOG, AthleteCard


RACE_REWARDS = ((3, 1), (4, 2), (4, 2), (5, 3))
TRACK_SCHEDULE = ("Standard", "Standard", "WildWilds", "WildWilds")


class GameRuleError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class GamePhase(StrEnum):
    LOBBY = "LOBBY"
    DRAFT_ROLL = "DRAFT_ROLL"
    DRAFTING = "DRAFTING"
    RACE_ROLL = "RACE_ROLL"
    CHARACTER_SELECTION = "CHARACTER_SELECTION"
    RACING = "RACING"
    RACE_RESULTS = "RACE_RESULTS"
    FINISHED = "FINISHED"


@dataclass(frozen=True, slots=True)
class Player:
    id: str
    name: str


@dataclass(frozen=True, slots=True)
class GameState:
    phase: GamePhase
    players: tuple[Player, ...]
    teams: dict[str, tuple[AthleteCard, ...]] = field(default_factory=dict)
    used_athlete_ids: frozenset[str] = frozenset()
    selections: dict[str, tuple[AthleteCard, ...]] = field(default_factory=dict)
    scores: dict[str, int] = field(default_factory=dict)
    double_racer_variant: bool = False
    auto_deal: bool = False
    race_number: int = 0
    positions: dict[str, int] = field(default_factory=dict)
    active_player_id: str | None = None
    roll_values: dict[str, tuple[int, int]] = field(default_factory=dict)
    roll_candidates: tuple[str, ...] = ()
    draft_initial_player_id: str | None = None
    draft_round: int = 0
    draft_pool: tuple[AthleteCard, ...] = ()
    draft_order: tuple[str, ...] = ()
    draft_pick_index: int = 0
    remaining_athlete_ids: tuple[str, ...] = ()
    first_turn_player_id: str | None = None
    racer_owner_by_index: dict[int, str] = field(default_factory=dict)
    racer_athlete_by_index: dict[int, AthleteCard] = field(default_factory=dict)
    race_results: tuple[dict[str, Any], ...] = ()
    magsim_engine: Any | None = None
    pending_decision: dict[str, Any] | None = None
    pending_roll: dict[str, Any] | None = None
    race_log: tuple[dict[str, Any], ...] = ()
    resolution_status: str = "IDLE"
    # Append fields to preserve the positional state used by frozen dataclass pickles.
    race_winner_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GameTransition:
    state: GameState
    events: tuple[dict[str, Any], ...]


class GameEngine(Protocol):
    def create_game(self, players: tuple[Player, ...]) -> GameState: ...
    def start(self, state: GameState, player_id: str) -> GameTransition: ...
    def set_variant(self, state: GameState, player_id: str, double_racer: bool) -> GameTransition: ...
    def set_auto_deal(self, state: GameState, player_id: str, auto_deal: bool) -> GameTransition: ...
    def roll_start(self, state: GameState, player_id: str) -> GameTransition: ...
    def draft_athlete(self, state: GameState, player_id: str, athlete_id: str) -> GameTransition: ...
    def select_racers(self, state: GameState, player_id: str, athlete_ids: tuple[str, ...]) -> GameTransition: ...
    def roll_dice(self, state: GameState, player_id: str, timed_out: bool = False) -> GameTransition: ...
    def resolve_decision(self, state: GameState, player_id: str, decision_id: str, option_id: str, timed_out: bool = False, bot: bool = False) -> GameTransition: ...
    def advance_race(self, state: GameState, player_id: str) -> GameTransition: ...
    def public_state(self, state: GameState, viewer_id: str | None = None) -> dict[str, Any]: ...


class MagsimGameEngine:
    finish_line = 30

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.SystemRandom()

    def create_game(self, players: tuple[Player, ...]) -> GameState:
        return GameState(
            phase=GamePhase.LOBBY,
            players=players,
            teams={player.id: () for player in players},
            scores={player.id: 0 for player in players},
        )

    @staticmethod
    def _is_double_variant(state: GameState) -> bool:
        return len(state.players) == 2 or (len(state.players) == 3 and state.double_racer_variant)

    def set_variant(
        self, state: GameState, player_id: str, double_racer: bool
    ) -> GameTransition:
        if state.phase != GamePhase.LOBBY:
            raise GameRuleError("GAME_ALREADY_STARTED", "开局后不能修改游戏模式")
        if not state.players or state.players[0].id != player_id:
            raise GameRuleError("ONLY_HOST_CAN_CONFIGURE", "只有房主可以修改游戏模式")
        if len(state.players) != 3 and double_racer:
            raise GameRuleError("VARIANT_REQUIRES_THREE", "该双赛车手开关仅用于 3 人游戏")
        return GameTransition(
            replace(state, double_racer_variant=double_racer),
            ({"type": "VARIANT_CHANGED", "doubleRacerVariant": double_racer},),
        )

    def set_auto_deal(
        self, state: GameState, player_id: str, auto_deal: bool
    ) -> GameTransition:
        if state.phase != GamePhase.LOBBY:
            raise GameRuleError("GAME_ALREADY_STARTED", "开局后不能修改游戏模式")
        if not state.players or state.players[0].id != player_id:
            raise GameRuleError("ONLY_HOST_CAN_CONFIGURE", "只有房主可以修改游戏模式")
        return GameTransition(
            replace(state, auto_deal=auto_deal),
            ({"type": "AUTO_DEAL_CHANGED", "autoDeal": auto_deal},),
        )

    def start(self, state: GameState, player_id: str) -> GameTransition:
        if state.phase != GamePhase.LOBBY:
            raise GameRuleError("GAME_ALREADY_STARTED", "游戏已经开始")
        if not 2 <= len(state.players) <= 6:
            raise GameRuleError("INVALID_PLAYER_COUNT", "游戏需要 2 至 6 名玩家")
        if state.players[0].id != player_id:
            raise GameRuleError("ONLY_HOST_CAN_START", "只有房主可以开始游戏")
        player_ids = tuple(player.id for player in state.players)
        ready = replace(
            state,
            roll_candidates=player_ids,
            remaining_athlete_ids=tuple(card.id for card in ATHLETE_CATALOG),
        )
        if state.auto_deal:
            next_state, events = self._deal_teams(replace(ready, phase=GamePhase.RACE_ROLL))
            return GameTransition(next_state, tuple(events))
        return GameTransition(
            replace(ready, phase=GamePhase.DRAFT_ROLL),
            ({"type": "DRAFT_ROLL_STARTED"},),
        )

    def _cards_per_player(self, state: GameState) -> int:
        if not state.players:
            return 0
        return self._draft_round_count(state) * self._draft_pool_size(state) // len(state.players)

    def _deal_teams(self, state: GameState) -> tuple[GameState, list[dict[str, Any]]]:
        deal_size = self._cards_per_player(state)
        pool_ids = self._rng.sample(
            list(state.remaining_athlete_ids), deal_size * len(state.players)
        )
        teams = dict(state.teams)
        events: list[dict[str, Any]] = []
        for offset, player in enumerate(state.players):
            dealt = tuple(
                ATHLETE_BY_ID[athlete_id]
                for athlete_id in pool_ids[offset * deal_size : (offset + 1) * deal_size]
            )
            teams[player.id] = dealt
            events.append({
                "type": "TEAM_DEALT",
                "playerId": player.id,
                "athleteIds": [card.id for card in dealt],
            })
        remaining = tuple(
            athlete_id for athlete_id in state.remaining_athlete_ids if athlete_id not in pool_ids
        )
        events.append({"type": "RACE_ROLL_STARTED", "raceNumber": state.race_number + 1})
        return replace(state, teams=teams, remaining_athlete_ids=remaining), events

    def roll_start(self, state: GameState, player_id: str) -> GameTransition:
        if state.phase not in (GamePhase.DRAFT_ROLL, GamePhase.RACE_ROLL):
            raise GameRuleError("ROLL_OFF_NOT_ACTIVE", "当前不需要掷起始骰")
        if player_id not in state.roll_candidates:
            raise GameRuleError("NOT_IN_ROLL_OFF", "你不在本轮掷骰名单中")
        if player_id in state.roll_values:
            raise GameRuleError("ALREADY_ROLLED", "你已经掷过本轮起始骰")

        values = tuple(sorted((self._rng.randint(1, 6), self._rng.randint(1, 6)), reverse=True))
        rolls = {**state.roll_values, player_id: values}
        events: list[dict[str, Any]] = [
            {"type": "START_DICE_ROLLED", "playerId": player_id, "values": list(values)}
        ]
        if not all(candidate in rolls for candidate in state.roll_candidates):
            return GameTransition(replace(state, roll_values=rolls), tuple(events))

        best = max(rolls[candidate] for candidate in state.roll_candidates)
        tied = tuple(candidate for candidate in state.roll_candidates if rolls[candidate] == best)
        if len(tied) > 1:
            events.append({"type": "ROLL_OFF_TIED", "playerIds": list(tied)})
            return GameTransition(
                replace(state, roll_values={}, roll_candidates=tied), tuple(events)
            )

        winner = tied[0]
        events.append({"type": "ROLL_OFF_WON", "playerId": winner})
        if state.phase == GamePhase.DRAFT_ROLL:
            next_state = self._start_draft_round(
                replace(state, draft_initial_player_id=winner, roll_values={}), 0
            )
            events.append({"type": "DRAFT_STARTED", "playerId": winner})
        else:
            next_state = replace(
                state,
                phase=GamePhase.CHARACTER_SELECTION,
                first_turn_player_id=winner,
                active_player_id=None,
                roll_values={},
                roll_candidates=(),
                selections={},
                positions={},
                race_results=(),
            )
            events.append({"type": "RACER_SELECTION_STARTED", "raceNumber": state.race_number + 1})
        return GameTransition(next_state, tuple(events))

    def _draft_round_count(self, state: GameState) -> int:
        return 4 if len(state.players) == 3 and self._is_double_variant(state) else 2

    def _draft_pool_size(self, state: GameState) -> int:
        return 8 if len(state.players) == 2 else len(state.players) * 2

    def _start_draft_round(self, state: GameState, round_index: int) -> GameState:
        player_ids = [player.id for player in state.players]
        initial_index = player_ids.index(state.draft_initial_player_id or player_ids[0])
        if len(player_ids) == 2:
            start_index = (initial_index + round_index) % 2
            a, b = player_ids[start_index], player_ids[(start_index + 1) % 2]
            order = (a, b, b, a, a, b, b, a)
        else:
            start_index = (initial_index + round_index) % len(player_ids)
            forward = tuple(player_ids[(start_index + offset) % len(player_ids)] for offset in range(len(player_ids)))
            order = forward + tuple(reversed(forward))

        pool_ids = self._rng.sample(list(state.remaining_athlete_ids), self._draft_pool_size(state))
        pool = tuple(ATHLETE_BY_ID[athlete_id] for athlete_id in pool_ids)
        remaining = tuple(athlete_id for athlete_id in state.remaining_athlete_ids if athlete_id not in pool_ids)
        return replace(
            state,
            phase=GamePhase.DRAFTING,
            draft_round=round_index,
            draft_pool=pool,
            draft_order=order,
            draft_pick_index=0,
            remaining_athlete_ids=remaining,
            active_player_id=order[0],
            roll_candidates=(),
        )

    def draft_athlete(self, state: GameState, player_id: str, athlete_id: str) -> GameTransition:
        if state.phase != GamePhase.DRAFTING:
            raise GameRuleError("NOT_DRAFTING", "当前不在招募阶段")
        if state.active_player_id != player_id:
            raise GameRuleError("NOT_YOUR_PICK", "还没轮到你招募")
        athlete = next((card for card in state.draft_pool if card.id == athlete_id), None)
        if athlete is None:
            raise GameRuleError("ATHLETE_NOT_IN_POOL", "该赛车手不在公开招募区")

        teams = {**state.teams, player_id: (*state.teams[player_id], athlete)}
        pool = tuple(card for card in state.draft_pool if card.id != athlete_id)
        pick_index = state.draft_pick_index + 1
        events: list[dict[str, Any]] = [
            {"type": "ATHLETE_DRAFTED", "playerId": player_id, "athleteId": athlete_id}
        ]
        if pick_index < len(state.draft_order):
            next_player = state.draft_order[pick_index]
            next_state = replace(
                state,
                teams=teams,
                draft_pool=pool,
                draft_pick_index=pick_index,
                active_player_id=next_player,
            )
        elif state.draft_round + 1 < self._draft_round_count(state):
            next_state = self._start_draft_round(replace(state, teams=teams, draft_pool=pool), state.draft_round + 1)
            events.append({"type": "DRAFT_ROUND_STARTED", "round": next_state.draft_round + 1})
        else:
            candidates = tuple(player.id for player in state.players)
            next_state = replace(
                state,
                phase=GamePhase.RACE_ROLL,
                teams=teams,
                draft_pool=(),
                draft_order=(),
                active_player_id=None,
                roll_candidates=candidates,
                roll_values={},
            )
            events.append({"type": "DRAFT_FINISHED"})
            events.append({"type": "RACE_ROLL_STARTED", "raceNumber": 1})
        return GameTransition(next_state, tuple(events))

    def select_racers(
        self, state: GameState, player_id: str, athlete_ids: tuple[str, ...]
    ) -> GameTransition:
        if state.phase != GamePhase.CHARACTER_SELECTION:
            raise GameRuleError("NOT_SELECTING_ATHLETES", "当前不在选将阶段")
        expected = 2 if self._is_double_variant(state) else 1
        if len(athlete_ids) != expected or len(set(athlete_ids)) != expected:
            raise GameRuleError("INVALID_RACER_COUNT", f"本场必须选择 {expected} 名不同赛车手")
        if player_id in state.selections:
            raise GameRuleError("ATHLETE_ALREADY_LOCKED", "本场阵容已经锁定")
        team_by_id = {card.id: card for card in state.teams.get(player_id, ())}
        if any(athlete_id not in team_by_id for athlete_id in athlete_ids):
            raise GameRuleError("ATHLETE_NOT_IN_TEAM", "所选赛车手不在你的队伍中")
        if any(athlete_id in state.used_athlete_ids for athlete_id in athlete_ids):
            raise GameRuleError("ATHLETE_ALREADY_USED", "赛车手整局只能上场一次")

        selections = {
            **state.selections,
            player_id: tuple(team_by_id[athlete_id] for athlete_id in athlete_ids),
        }
        events: list[dict[str, Any]] = [{"type": "RACERS_LOCKED", "playerId": player_id}]
        if len(selections) == len(state.players):
            next_state = self._create_race(replace(state, selections=selections))
            events.extend(({"type": "RACERS_REVEALED"}, {"type": "RACE_STARTED", "raceNumber": state.race_number + 1}))
            if next_state.pending_decision is not None:
                events.append({"type": "DECISION_REQUIRED", **next_state.pending_decision})
        else:
            next_state = replace(state, selections=selections)
        if next_state.phase == GamePhase.RACING:
            if next_state.pending_decision is None:
                return self._advance_turn_flow(next_state, events, start_turn=True)
            return self._transition_with_log(next_state, events)
        return GameTransition(next_state, tuple(events))

    def _create_race(self, state: GameState) -> GameState:
        from magsim.core.state import GameRules
        from magsim.engine.board import BOARD_DEFINITIONS
        from magsim.engine.scenario import GameScenario, RacerConfig
        from magsim.core.interactive import DecisionBroker, InteractiveAgent

        player_ids = [player.id for player in state.players]
        start = player_ids.index(state.first_turn_player_id or player_ids[0])
        ordered_players = [player_ids[(start + offset) % len(player_ids)] for offset in range(len(player_ids))]
        configs: list[RacerConfig] = []
        owners: dict[int, str] = {}
        athletes: dict[int, AthleteCard] = {}
        broker = DecisionBroker()
        agent = InteractiveAgent(broker)
        for player_id in ordered_players:
            for athlete in state.selections[player_id]:
                index = len(configs)
                configs.append(RacerConfig(idx=index, name=athlete.engine_name, agent=agent))
                owners[index] = player_id
                athletes[index] = athlete

        scenario = GameScenario(
            racers_config=configs,
            board=BOARD_DEFINITIONS[TRACK_SCHEDULE[state.race_number]](),
            rules=GameRules(winner_vp=RACE_REWARDS[state.race_number]),
            seed=self._rng.randrange(0, 2**63),
            defer_setup=True,
        )
        scenario.engine.verbose = False
        scenario.state.previous_winners = tuple(ATHLETE_BY_ID[athlete_id].engine_name
                                               for athlete_id in state.race_winner_ids)
        scenario.engine.continue_setup()
        pending = self._pending_decision(state, scenario.engine, owners, athletes)
        return replace(
            state,
            phase=GamePhase.RACING,
            active_player_id=owners[scenario.engine.state.current_racer_idx],
            racer_owner_by_index=owners,
            racer_athlete_by_index=athletes,
            positions={athlete.id: 0 for athlete in athletes.values()},
            magsim_engine=scenario.engine,
            pending_decision=pending,
            resolution_status="WAITING_FOR_DECISION" if pending else "IDLE",
            race_log=(),
        )

    def roll_dice(
        self,
        state: GameState,
        player_id: str,
        timed_out: bool = False,
    ) -> GameTransition:
        if state.phase != GamePhase.RACING or state.magsim_engine is None:
            raise GameRuleError("GAME_NOT_RUNNING", "比赛尚未开始")
        if state.pending_decision is not None:
            raise GameRuleError("DECISION_PENDING", "请先完成当前技能选择")
        if state.resolution_status != "WAITING_FOR_ROLL":
            raise GameRuleError("ROLL_NOT_AVAILABLE", "当前不能掷骰")

        engine = state.magsim_engine
        events: list[dict[str, Any]] = []
        pending = engine.roll_broker.pending
        if pending is None:
            if state.active_player_id != player_id:
                raise GameRuleError("NOT_YOUR_TURN", "还没轮到你")
            previous_callback = engine.on_event_processed
            engine.on_event_processed = (
                lambda _engine, event: self._append_public_event(events, state, event)
            )
            try:
                engine.request_main_roll()
                progress = engine.continue_turn()
            finally:
                engine.on_event_processed = previous_callback
            pending = engine.roll_broker.pending
            if pending is None:
                return self._advance_turn_flow(
                    replace(state, pending_roll=None),
                    events,
                    initial_progress=progress,
                )
        else:
            next_racer_idx = pending.participants[pending.next_index]
            if state.racer_owner_by_index[next_racer_idx] != player_id:
                raise GameRuleError("NOT_ROLLING_PLAYER", "当前应由另一位玩家掷骰")

        submitted = engine.submit_pending_roll()
        events.append(self._submitted_roll_event(state, submitted, timed_out=timed_out))
        return self._advance_turn_flow(replace(state, pending_roll=None), events)

    def _submitted_roll_event(
        self,
        state: GameState,
        submitted: Any,
        *,
        timed_out: bool,
    ) -> dict[str, Any]:
        racer_idx = submitted.participant_racer_idx
        athlete = state.racer_athlete_by_index[racer_idx]
        return {
            "type": "ABILITY_DICE_ROLLED" if submitted.kind == "ABILITY_ROLL" else "DIE_ROLLED",
            "playerId": state.racer_owner_by_index[racer_idx],
            "athleteId": athlete.id,
            "value": submitted.value,
            "kind": submitted.kind,
            "abilityName": submitted.ability_name,
            "rollSessionId": submitted.session_id,
            "rollResultId": submitted.result_id,
            "throwIndex": submitted.throw_index,
            "throwCount": submitted.throw_count,
            "automatic": timed_out,
        }

    def resolve_decision(
        self,
        state: GameState,
        player_id: str,
        decision_id: str,
        option_id: str,
        timed_out: bool = False,
        bot: bool = False,
    ) -> GameTransition:
        if state.magsim_engine is None or state.pending_decision is None:
            raise GameRuleError("NO_PENDING_DECISION", "当前没有待处理的技能选择")
        if state.pending_decision["playerId"] != player_id and not (timed_out or bot):
            raise GameRuleError("NOT_DECIDING_PLAYER", "只有对应玩家可以提交这个选择")
        if state.pending_decision["id"] != decision_id:
            raise GameRuleError("STALE_DECISION", "选择已失效或候选项无效")
        engine = state.magsim_engine
        broker = next(iter(engine.agents.values())).broker
        smart_choice = None
        try:
            if timed_out or bot:
                smart_choice = broker.choose_smart(engine)
            else:
                broker.choose(decision_id, option_id)
        except ValueError as error:
            code = str(error)
            raise GameRuleError(code, "选择已失效或候选项无效") from error

        resolved = state.pending_decision
        option_label = next(
            (
                option.get("label")
                for option in resolved.get("options", ())
                if str(option.get("id")) == str(option_id)
            ),
            None,
        )
        events: list[dict[str, Any]] = [{
            "type": "DECISION_TIMED_OUT" if timed_out else "DECISION_RESOLVED",
            "decisionId": decision_id,
            "playerId": resolved["playerId"],
            "athleteId": resolved.get("athleteId"),
            "athleteName": resolved.get("athleteName"),
            "abilityName": resolved["abilityName"],
            "optionId": option_id,
            "optionLabel": option_label,
            "automatic": timed_out,
            "bot": bot,
        }]

        def finish(transition: GameTransition) -> GameTransition:
            if bot:
                return self._record_bot_choice(
                    transition,
                    decision_id,
                    resolved,
                    None if smart_choice is None else smart_choice.answer_index,
                )
            return transition

        if not engine._setup_complete:
            complete = engine.continue_setup()
            if not complete:
                pending = self._pending_decision(state, engine)
                if pending is not None:
                    events.append({"type": "DECISION_REQUIRED", **pending})
                next_state = replace(
                    state,
                    pending_decision=pending,
                    resolution_status="WAITING_FOR_DECISION",
                )
                return finish(self._transition_with_log(next_state, events))
            next_state = replace(state, pending_decision=None, resolution_status="IDLE")
            return finish(self._advance_turn_flow(next_state, events, start_turn=True))
        return finish(
            self._advance_turn_flow(replace(state, pending_decision=None), events)
        )

    @staticmethod
    def _record_bot_choice(
        transition: GameTransition,
        decision_id: str,
        resolved: dict[str, Any],
        index: int | None,
    ) -> GameTransition:
        """Fill in the concrete option a bot's smart agent picked for the broadcast,
        so the table sees which skill the bot used instead of an empty "automatic"."""
        options = resolved.get("options", ())
        if index is None or not (-2 <= index < len(options)):
            return transition
        option_id = "skip" if index == -2 else str(index)
        option_label = next(
            (
                option.get("label")
                for option in options
                if str(option.get("id")) == option_id
            ),
            None,
        )
        for event in transition.events:
            if event.get("decisionId") == decision_id:
                event["optionId"] = option_id
                event["optionLabel"] = option_label
        log = [
            {**entry, "optionId": option_id, "optionLabel": option_label}
            if entry.get("decisionId") == decision_id else entry
            for entry in transition.state.race_log
        ]
        return GameTransition(
            replace(transition.state, race_log=tuple(log)), transition.events
        )

    def _pending_decision(
        self,
        state: GameState,
        engine: Any,
        owners: dict[int, str] | None = None,
        athletes: dict[int, AthleteCard] | None = None,
    ) -> dict[str, Any] | None:
        broker = next(iter(engine.agents.values())).broker
        pending = broker.pending
        if pending is None:
            return None
        owner_map = owners or state.racer_owner_by_index
        athlete_map = athletes or state.racer_athlete_by_index
        athlete = athlete_map[pending.racer_idx]
        public = {
            "id": pending.id,
            "playerId": owner_map[pending.racer_idx],
            "athleteId": athlete.id,
            "athleteName": athlete.name,
            "abilityName": pending.ability_name,
            "prompt": pending.prompt,
            "choiceType": pending.choice_type,
            "options": pending.public_options(),
        }
        for option, value in zip(public["options"], pending.options):
            candidate_name = getattr(value, "racer_name", None)
            candidate = next((card for card in ATHLETE_CATALOG if card.engine_name == candidate_name), None)
            if candidate is not None:
                option["athlete"] = candidate.public_data()
            target_idx = getattr(value, "idx", None)
            if target_idx in athlete_map:
                target_owner = owner_map[target_idx]
                owner_name = next(p.name for p in state.players if p.id == target_owner)
                option["ownerName"] = owner_name
                option["position"] = value.position
        effect_preview = getattr(pending, "effect_preview", None)
        if effect_preview is not None:
            target_idx = effect_preview["racerIndex"]
            public["effectPreview"] = {
                "athleteId": athlete_map[target_idx].id,
                "athleteName": athlete_map[target_idx].name,
                "from": effect_preview["from"],
                "to": effect_preview["to"],
            }
        if pending.roll_preview is not None:
            public["rollPreview"] = pending.roll_preview
        return public

    def _pending_roll(self, state: GameState, engine: Any) -> dict[str, Any] | None:
        pending = engine.roll_broker.pending
        if pending is None or pending.complete:
            return None
        participants = []
        for index, racer_idx in enumerate(pending.participants):
            athlete = state.racer_athlete_by_index[racer_idx]
            participant = {
                "playerId": state.racer_owner_by_index[racer_idx],
                "athleteId": athlete.id,
                "athleteName": athlete.name,
            }
            if index < len(pending.values):
                participant["value"] = pending.values[index]
            participants.append(participant)
        next_racer_idx = pending.participants[pending.next_index]
        next_athlete = state.racer_athlete_by_index[next_racer_idx]
        return {
            "id": pending.id,
            "kind": pending.kind,
            "abilityName": pending.ability_name,
            "participants": participants,
            "values": list(pending.values),
            "nextPlayerId": state.racer_owner_by_index[next_racer_idx],
            "nextAthleteId": next_athlete.id,
            "nextAthleteName": next_athlete.name,
            "throwIndex": pending.next_index,
            "throwCount": len(pending.participants),
        }

    def _transition_with_log(self, state: GameState, events: list[dict[str, Any]]) -> GameTransition:
        log = list(state.race_log)
        for event in events:
            if event.get("type") in {
                "DICE_ROLLED", "DIE_ROLLED", "ABILITY_DICE_ROLLED",
                "ABILITY_ROLL_RESOLVED", "RACER_MOVED", "RACER_WARPED", "RACERS_SWAPPED",
                "RACER_TRIPPED", "TRIP_RECOVERED", "RACER_FINISHED", "RACER_ELIMINATED",
                "ABILITY_TRIGGERED",
                "DECISION_REQUIRED", "DECISION_RESOLVED", "DECISION_TIMED_OUT",
                "RACE_FINISHED",
            }:
                log.append({"sequence": len(log) + 1, **event})
        return GameTransition(replace(state, race_log=tuple(log)), tuple(events))

    def _positions(self, state: GameState) -> dict[str, int]:
        engine = state.magsim_engine
        preview = self._preview_positions(engine)
        return {
            state.racer_athlete_by_index[racer.idx].id: preview.get(racer.idx, racer.position or 0)
            for racer in engine.state.racers
        }

    @staticmethod
    def _preview_positions(engine: Any) -> dict[int, int]:
        return {event.target_racer_idx: event.end_tile
                for event in getattr(engine, "preview_events", ())
                if event.__class__.__name__ in {"PostMoveEvent", "PostWarpEvent"}}

    def _finish_race(
        self, state: GameState, events: list[dict[str, Any]]
    ) -> GameTransition:
        engine = state.magsim_engine
        positions = self._positions(state)
        results = []
        race_points = {player.id: 0 for player in state.players}
        for racer in engine.state.racers:
            owner_id = state.racer_owner_by_index[racer.idx]
            athlete = state.racer_athlete_by_index[racer.idx]
            race_points[owner_id] += racer.victory_points
            results.append({"playerId": owner_id, "athlete": athlete.public_data(), "finishPosition": racer.finish_position, "points": racer.victory_points, "position": racer.position, "eliminated": racer.eliminated})
        scores = {player.id: state.scores[player.id] + race_points[player.id] for player in state.players}
        used = state.used_athlete_ids.union(athlete.id for selected in state.selections.values() for athlete in selected)
        events.append({"type": "RACE_FINISHED", "raceNumber": state.race_number + 1})
        winners = tuple(result["athlete"]["id"] for result in results if result["finishPosition"] == 1)
        next_state = replace(state, phase=GamePhase.FINISHED if state.race_number == 3 else GamePhase.RACE_RESULTS, positions=positions, scores=scores, used_athlete_ids=frozenset(used), active_player_id=None, race_results=tuple(results), race_winner_ids=state.race_winner_ids + winners, pending_decision=None, pending_roll=None, resolution_status="IDLE")
        return self._transition_with_log(next_state, events)

    def _advance_turn_flow(
        self,
        state: GameState,
        events: list[dict[str, Any]],
        *,
        start_turn: bool = False,
        initial_progress: Any | None = None,
    ) -> GameTransition:
        from magsim.engine.game_engine import TurnProgress

        engine = state.magsim_engine
        previous_callback = engine.on_event_processed
        engine.on_event_processed = (
            lambda _engine, event: self._append_public_event(events, state, event)
        )
        try:
            if start_turn:
                engine.start_turn()
            while True:
                if initial_progress is None:
                    progress = engine.continue_turn()
                else:
                    progress = initial_progress
                    initial_progress = None
                positions = self._positions(state)
                if progress is TurnProgress.WAITING_FOR_DECISION:
                    pending = self._pending_decision(state, engine)
                    if pending is not None:
                        events.append({"type": "DECISION_REQUIRED", **pending})
                    next_state = replace(
                        state,
                        positions=positions,
                        pending_decision=pending,
                        pending_roll=None,
                        resolution_status="WAITING_FOR_DECISION",
                    )
                    return self._transition_with_log(next_state, events)
                if progress is TurnProgress.WAITING_FOR_ROLL:
                    racer = engine.state.racers[engine.state.current_racer_idx]
                    if racer.roll_override is not None and engine.roll_broker.pending is None:
                        # Overrides (Legs' jog) stand in for the die, and the player
                        # already chose to skip it, so the move runs right away.
                        engine.request_main_roll()
                        continue
                    pending_roll = self._pending_roll(state, engine)
                    next_state = replace(
                        state,
                        positions=positions,
                        pending_decision=None,
                        pending_roll=pending_roll,
                        resolution_status="WAITING_FOR_ROLL",
                    )
                    return self._transition_with_log(next_state, events)

                engine.advance_turn()
                if not engine.state.race_active:
                    return self._finish_race(state, events)
                active_player_id = state.racer_owner_by_index[
                    engine.state.current_racer_idx
                ]
                events.append({"type": "TURN_CHANGED", "playerId": active_player_id})
                state = replace(
                    state,
                    positions=positions,
                    active_player_id=active_player_id,
                    pending_decision=None,
                    pending_roll=None,
                    resolution_status="IDLE",
                )
                engine.start_turn()
        finally:
            engine.on_event_processed = previous_callback

    def advance_race(self, state: GameState, player_id: str) -> GameTransition:
        if state.phase != GamePhase.RACE_RESULTS:
            raise GameRuleError("NO_RACE_TO_ADVANCE", "当前没有可继续的比赛")
        if state.players[0].id != player_id:
            raise GameRuleError("ONLY_HOST_CAN_ADVANCE", "只有房主可以进入下一场")

        race_points = {player.id: 0 for player in state.players}
        for result in state.race_results:
            race_points[result["playerId"]] += result["points"]
        if self._is_double_variant(state):
            worst = min(race_points.values())
            candidates = tuple(player.id for player in state.players if race_points[player.id] == worst)
        else:
            unfinished = [result for result in state.race_results if result["finishPosition"] is None]
            if unfinished:
                last_position = min((result["position"] if result["position"] is not None else -1) for result in unfinished)
                candidates = tuple(dict.fromkeys(result["playerId"] for result in unfinished if (result["position"] if result["position"] is not None else -1) == last_position))
            else:
                candidates = tuple(player.id for player in state.players)

        next_race = state.race_number + 1
        base = replace(
            state,
            race_number=next_race,
            selections={},
            positions={},
            racer_owner_by_index={},
            racer_athlete_by_index={},
            magsim_engine=None,
            race_results=(),
            roll_values={},
        )
        if len(candidates) == 1:
            next_state = replace(
                base,
                phase=GamePhase.CHARACTER_SELECTION,
                first_turn_player_id=candidates[0],
                roll_candidates=(),
            )
            events = ({"type": "RACER_SELECTION_STARTED", "raceNumber": next_race + 1},)
        else:
            next_state = replace(base, phase=GamePhase.RACE_ROLL, roll_candidates=candidates)
            events = ({"type": "RACE_ROLL_STARTED", "raceNumber": next_race + 1},)
        return GameTransition(next_state, events)

    def _append_public_event(self, events: list[dict[str, Any]], state: GameState, event: Any) -> None:
        name = event.__class__.__name__
        index = getattr(event, "target_racer_idx", None)
        owner_id = state.racer_owner_by_index.get(index)
        athlete = state.racer_athlete_by_index.get(index)
        base = {"playerId": owner_id, "athleteId": athlete.id if athlete else None}
        source_index = getattr(event, "responsible_racer_idx", None)
        source_athlete = state.racer_athlete_by_index.get(source_index)
        if source_athlete:
            base.update({
                "sourcePlayerId": state.racer_owner_by_index.get(source_index),
                "sourceAthleteId": source_athlete.id,
                "sourceAthleteName": source_athlete.name,
            })
        trigger_index = getattr(event, "trigger_racer_idx", None)
        trigger_athlete = state.racer_athlete_by_index.get(trigger_index)
        if trigger_athlete:
            base.update({
                "triggerPlayerId": state.racer_owner_by_index.get(trigger_index),
                "triggerAthleteId": trigger_athlete.id,
                "triggerAthleteName": trigger_athlete.name,
            })
        if name == "RollResultEvent":
            events.append({
                "type": "DICE_ROLLED",
                **base,
                "value": event.dice_value or event.base_value,
                "values": list(event.dice_values),
                "baseValue": event.base_value,
                "finalValue": event.final_value,
                "rollSerial": event.roll_serial,
                "rollSessionId": event.roll_session_id,
                "rollResultId": event.roll_result_id,
                "noDice": event.dice_value is None,
            })
        elif name == "AbilityRollResultEvent":
            participants = [
                {
                    "playerId": state.racer_owner_by_index[racer_idx],
                    "athleteId": state.racer_athlete_by_index[racer_idx].id,
                    "value": value,
                }
                for racer_idx, value in zip(
                    event.participant_racer_indices,
                    event.values,
                    strict=True,
                )
            ]
            winner_idx = event.winner_racer_idx
            events.append({
                "type": "ABILITY_ROLL_RESOLVED",
                "abilityName": str(event.source),
                "rollSessionId": event.roll_session_id,
                "participants": participants,
                "winnerPlayerId": state.racer_owner_by_index[winner_idx],
                "winnerAthleteId": state.racer_athlete_by_index[winner_idx].id,
            })
        elif name == "PostMoveEvent":
            kind = "PUSH" if str(event.source) in {"CentaurTrample", "HugeBabyPush"} else ("FORWARD" if event.end_tile >= event.start_tile else "BACKWARD")
            events.append({"type": "RACER_MOVED", **base, "from": event.start_tile, "to": event.end_tile, "movementKind": kind, "source": str(event.source)})
        elif name == "PostWarpEvent":
            source = str(event.source)
            kind = "SWAP" if source == "FlipFlopSwap" else ("PUSH" if source == "HugeBabyPush" else "WARP")
            events.append({"type": "RACER_WARPED", **base, "from": event.start_tile, "to": event.end_tile, "movementKind": kind, "source": source})
            if kind == "SWAP" and len(events) >= 2 and events[-2].get("source") == source:
                events.append({"type": "RACERS_SWAPPED", "source": source})
        elif name == "PostTripEvent":
            events.append({"type": "RACER_TRIPPED", **base, "source": str(event.source)})
        elif name == "AbilityTriggeredEvent":
            source_index = getattr(event, "responsible_racer_idx", None)
            source_athlete = state.racer_athlete_by_index.get(source_index)
            events.append({
                "type": "ABILITY_TRIGGERED",
                **base,
                "sourcePlayerId": state.racer_owner_by_index.get(source_index),
                "sourceAthleteId": source_athlete.id if source_athlete else None,
                "sourceAthleteName": source_athlete.name if source_athlete else None,
                "abilityName": str(event.source),
                "movementDistance": getattr(event, "movement_distance", 0),
            })
        elif name == "RacerFinishedEvent":
            events.append({"type": "RACER_FINISHED", **base, "finishPosition": event.finishing_position})
        elif name == "RacerEliminatedEvent":
            events.append({"type": "RACER_ELIMINATED", **base})
        elif name == "TripRecoveryEvent":
            events.append({"type": "TRIP_RECOVERED", **base})

    def public_state(self, state: GameState, viewer_id: str | None = None) -> dict[str, Any]:
        from magsim.core.abilities import CopyAbilityProtocol

        revealed = state.phase in (GamePhase.RACING, GamePhase.RACE_RESULTS, GamePhase.FINISHED)
        active_racers_by_owner: dict[str, list[dict[str, Any]]] = {player.id: [] for player in state.players}
        if state.magsim_engine is not None:
            preview_positions = self._preview_positions(state.magsim_engine)
            for racer in state.magsim_engine.state.racers:
                owner = state.racer_owner_by_index[racer.idx]
                athlete = state.racer_athlete_by_index[racer.idx]
                copied_name = next((
                    ability.copied_racer for ability in racer.active_abilities
                    if isinstance(ability, CopyAbilityProtocol) and ability.copied_racer is not None
                ), None)
                copied_athlete = next((card for card in ATHLETE_CATALOG if card.engine_name == copied_name), None)
                active_racers_by_owner[owner].append({
                    **athlete.public_data(),
                    **({"copiedAthlete": copied_athlete.public_data()} if copied_athlete is not None else {}),
                    "position": preview_positions.get(racer.idx, racer.position or 0),
                    "points": racer.victory_points,
                    "finished": racer.finished,
                    "finishPosition": racer.finish_position,
                    "eliminated": racer.eliminated,
                    "tripped": racer.tripped,
                })
        players = []
        for player in state.players:
            team = state.teams.get(player.id, ())
            selections = state.selections.get(player.id, ())
            active_racers = active_racers_by_owner[player.id] if revealed else []
            players.append({
                "id": player.id,
                "name": player.name,
                "position": active_racers[0]["position"] if active_racers else 0,
                "score": state.scores.get(player.id, 0),
                "selectionLocked": player.id in state.selections,
                "selectedAthlete": active_racers[0] if active_racers else None,
                "activeRacers": active_racers,
                "team": [card.public_data() for card in team],
                "usedAthleteIds": [card.id for card in team if card.id in state.used_athlete_ids],
                "rollValues": list(state.roll_values[player.id]) if player.id in state.roll_values else None,
            })
        score_max = max(state.scores.values(), default=0)
        winner_ids = [player.id for player in state.players if state.phase == GamePhase.FINISHED and state.scores[player.id] == score_max]
        return {
            "phase": state.phase,
            "finishLine": state.magsim_engine.state.board.length if state.magsim_engine else self.finish_line,
            "players": players,
            "hand": [card.public_data() for card in state.teams.get(viewer_id or "", ())],
            "activePlayerId": state.active_player_id,
            "activeAthleteId": (
                state.racer_athlete_by_index[state.magsim_engine.state.current_racer_idx].id
                if state.phase == GamePhase.RACING and state.magsim_engine is not None
                else None
            ),
            "winnerId": winner_ids[0] if len(winner_ids) == 1 else None,
            "winnerIds": winner_ids,
            "raceNumber": state.race_number + 1,
            "trackName": TRACK_SCHEDULE[state.race_number],
            "raceRewards": list(RACE_REWARDS[state.race_number]),
            "doubleRacerVariant": self._is_double_variant(state),
            "autoDeal": state.auto_deal,
            "cardsPerPlayer": self._cards_per_player(state),
            "selectionCount": 2 if self._is_double_variant(state) else 1,
            "draftPool": [card.public_data() for card in state.draft_pool],
            "draftRound": state.draft_round + 1,
            "draftRoundCount": self._draft_round_count(state),
            "rollCandidateIds": list(state.roll_candidates),
            "raceResults": list(state.race_results),
            "previousWinners": [ATHLETE_BY_ID[athlete_id].public_data() for athlete_id in state.race_winner_ids],
            "pendingDecision": state.pending_decision,
            "pendingRoll": state.pending_roll,
            "raceLog": list(state.race_log),
            "resolutionStatus": state.resolution_status,
        }
