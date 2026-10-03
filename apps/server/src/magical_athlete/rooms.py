from __future__ import annotations

import asyncio
import random
import secrets
import string
import time
from datetime import UTC, datetime, timedelta
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import uuid4

from .game import (
    GameEngine,
    GamePhase,
    GameRuleError,
    GameState,
    GameTransition,
    MagsimGameEngine,
    Player,
)
from .protocol import (
    AddBotIntent,
    AdvanceRaceIntent,
    DraftAthleteIntent,
    ErrorMessage,
    JoinRoomIntent,
    KickPlayerIntent,
    LeaveRoomIntent,
    RollDiceIntent,
    RollStartIntent,
    ResolveDecisionIntent,
    SelectRacersIntent,
    SetAutoDealIntent,
    SetAutoPlayIntent,
    SetVariantIntent,
    StartGameIntent,
    ThrowPropIntent,
)


ROLL_ANIMATION_LEAD_SECONDS = 0.35
# Bots pause briefly before acting so their moves read as deliberate on every client.
BOT_ACTION_DELAY_SECONDS = 1.1
ACTION_TIME_LIMIT_SECONDS = 60
SPECTATOR_LIMIT = 20
TAUNT_COOLDOWN_SECONDS = 4


class RoomError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class RoomSocket(Protocol):
    async def send_json(self, message: dict[str, Any]) -> None: ...

    async def close(self, code: int = 1000, reason: str = "") -> None: ...


@dataclass(slots=True)
class RoomPlayer:
    player: Player
    reconnect_token: str
    connected: bool = True
    socket: RoomSocket | None = None
    seen_action_ids: set[str] = field(default_factory=set)
    is_bot: bool = False
    auto_play: bool = False
    taunt_ready_at: float = 0


@dataclass(slots=True)
class Room:
    id: str
    engine: GameEngine
    players: dict[str, RoomPlayer] = field(default_factory=dict)
    spectators: dict[str, RoomPlayer] = field(default_factory=dict)
    game_state: GameState | None = None
    revision: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    decision_task: asyncio.Task[None] | None = None
    decision_deadline: datetime | None = None
    roll_task: asyncio.Task[None] | None = None
    roll_deadline: datetime | None = None
    bot_task: asyncio.Task[None] | None = None
    bot_deadline: datetime | None = None

    def member(self, member_id: str) -> RoomPlayer | None:
        return self.players.get(member_id) or self.spectators.get(member_id)

    def public_state(self, viewer_id: str | None = None) -> dict[str, Any]:
        if self.game_state is None:
            game = self.engine.public_state(self.engine.create_game(tuple()), viewer_id)
        else:
            game = self.engine.public_state(self.game_state, viewer_id)
        if game.get("pendingDecision") is not None and self.decision_deadline is not None:
            game["pendingDecision"] = {
                **game["pendingDecision"],
                "deadlineAt": self.decision_deadline.isoformat(),
            }
        if game.get("pendingRoll") is not None and self.roll_deadline is not None:
            game["pendingRoll"] = {
                **game["pendingRoll"],
                "deadlineAt": self.roll_deadline.isoformat(),
            }
        connected = {player_id: member.connected for player_id, member in self.players.items()}
        for player in game["players"]:
            player["connected"] = connected.get(player["id"], False)
            member = self.players.get(player["id"])
            player["isBot"] = member.is_bot if member is not None else False
            player["autoPlay"] = member.auto_play if member is not None else False
        return {"roomId": self.id, "revision": self.revision, "game": game,
                "viewerRole": "spectator" if viewer_id in self.spectators else "player",
                "spectators": [{"id": member.player.id, "name": member.player.name, "connected": member.connected}
                               for member in self.spectators.values()]}


class InMemoryRoomRepository:
    """Process-local repository. Replace this boundary with Redis for multi-instance deploys."""

    def __init__(self) -> None:
        self._rooms: dict[str, Room] = {}
        self._lock = asyncio.Lock()

    async def create(self, code_length: int, engine: GameEngine | None = None) -> Room:
        async with self._lock:
            for _ in range(20):
                room_id = "".join(secrets.choice(string.ascii_uppercase) for _ in range(code_length))
                if room_id not in self._rooms:
                    room = Room(id=room_id, engine=engine or MagsimGameEngine())
                    self._rooms[room_id] = room
                    return room
        raise RoomError("ROOM_CODE_EXHAUSTED", "暂时无法创建房间，请重试")

    async def get(self, room_id: str) -> Room | None:
        return self._rooms.get(room_id.upper())


class RoomManager:
    def __init__(
        self,
        repository: InMemoryRoomRepository,
        *,
        local_timers: bool = True,
        rng: random.Random | None = None,
    ) -> None:
        self.repository = repository
        self.local_timers = local_timers
        self._rng = rng or random.Random()

    async def join(self, websocket: RoomSocket, intent: JoinRoomIntent) -> tuple[Room, str]:
        room = await self.repository.get(intent.room_id)
        if room is None:
            raise RoomError("ROOM_NOT_FOUND", "房间不存在")

        async with room.lock:
            members = room.spectators if intent.role == "spectator" else room.players
            if intent.player_id:
                member = members.get(intent.player_id)
                if member is None or not secrets.compare_digest(
                    member.reconnect_token, intent.reconnect_token or ""
                ):
                    raise RoomError("INVALID_RECONNECT_TOKEN", "重连凭证无效")
                if member.socket and member.socket is not websocket:
                    await member.socket.close(code=4001, reason="connected elsewhere")
                member.connected = True
                member.socket = websocket
                player_id = member.player.id
            else:
                if intent.role == "player" and room.game_state and room.game_state.phase != "LOBBY":
                    raise RoomError("GAME_ALREADY_STARTED", "比赛已开始，不能加入新玩家")
                if intent.role == "player" and len(room.players) >= 6:
                    raise RoomError("ROOM_FULL", "房间已满")
                if intent.role == "spectator" and len(room.spectators) >= SPECTATOR_LIMIT:
                    raise RoomError("SPECTATORS_FULL", "旁观席已满")
                player_id = uuid4().hex
                member = RoomPlayer(
                    player=Player(id=player_id, name=intent.player_name.strip()),
                    reconnect_token=secrets.token_urlsafe(24),
                    socket=websocket,
                )
                members[player_id] = member
                if intent.role == "player":
                    room.game_state = room.engine.create_game(
                        tuple(item.player for item in room.players.values())
                    )
                room.revision += 1

            await websocket.send_json(
                {
                    "type": "WELCOME",
                    "playerId": player_id,
                    "reconnectToken": member.reconnect_token,
                    **room.public_state(player_id),
                }
            )
            await self._broadcast_locked(
                room,
                {
                    "type": "STATE_UPDATED",
                    "events": [{"type": "SPECTATOR_JOINED" if intent.role == "spectator" else "PLAYER_JOINED", "playerId": player_id}],
                    "rollResults": [],
                },
                exclude=websocket,
            )
            self._sync_bot_timer_locked(room)
            return room, player_id

    async def handle_intent(
        self,
        room: Room,
        player_id: str,
        intent: StartGameIntent
        | LeaveRoomIntent
        | KickPlayerIntent
        | AddBotIntent
        | SetVariantIntent
        | SetAutoDealIntent
        | SetAutoPlayIntent
        | ThrowPropIntent
        | RollStartIntent
        | DraftAthleteIntent
        | SelectRacersIntent
        | RollDiceIntent
        | ResolveDecisionIntent
        | AdvanceRaceIntent,
    ) -> None:
        async with room.lock:
            member = room.member(player_id)
            if member is None:
                return
            if isinstance(intent, ThrowPropIntent):
                await self._throw_prop_locked(room, member, intent)
                return
            if player_id in room.spectators:
                if isinstance(intent, LeaveRoomIntent):
                    room.spectators.pop(player_id)
                    room.revision += 1
                    await member.socket.send_json({"type": "ROOM_LEFT"})
                    await self._broadcast_locked(room, {"type": "STATE_UPDATED", "events": [{"type": "SPECTATOR_LEFT", "playerId": player_id}], "rollResults": []})
                    await member.socket.close()
                else:
                    await member.socket.send_json(ErrorMessage(code="SPECTATOR_READ_ONLY", message="旁观者不能进行游戏操作", actionId=intent.action_id).model_dump(by_alias=True))
                return
            if isinstance(intent, LeaveRoomIntent):
                if not self._lobby_open(room):
                    await member.socket.send_json(ErrorMessage(
                        code="GAME_ALREADY_STARTED", message="游戏已开始，不能退出房间",
                        actionId=intent.action_id,
                    ).model_dump(by_alias=True))
                    return
                removed = self._remove_member_locked(room, player_id)
                await member.socket.send_json({"type": "ROOM_LEFT"})
                await self._announce_player_left_locked(room, removed)
                await member.socket.close()
                self._sync_bot_timer_locked(room)
                return
            if isinstance(intent, KickPlayerIntent):
                await self._kick_player_locked(room, member, intent)
                self._sync_bot_timer_locked(room)
                return
            if isinstance(intent, AddBotIntent):
                await self._add_bot_locked(room, member, intent)
                return
            if intent.action_id in member.seen_action_ids:
                await member.socket.send_json(
                    {"type": "ACTION_ACK", "actionId": intent.action_id, "revision": room.revision}
                )
                return
            member.seen_action_ids.add(intent.action_id)
            if len(member.seen_action_ids) > 500:
                member.seen_action_ids = {intent.action_id}
            if isinstance(intent, SetAutoPlayIntent):
                member.auto_play = intent.enabled
                room.revision += 1
                state = room.game_state
                if state and state.pending_decision and state.pending_decision.get("playerId") == player_id:
                    self._sync_decision_timer_locked(room)
                if state and state.pending_roll and state.pending_roll.get("nextPlayerId") == player_id:
                    self._sync_roll_timer_locked(room)
                self._sync_bot_timer_locked(room)
                await self._broadcast_locked(room, {
                    "type": "STATE_UPDATED", "actionId": intent.action_id,
                    "events": [{"type": "AUTO_PLAY_CHANGED", "playerId": player_id, "enabled": intent.enabled}],
                    "rollResults": [],
                })
                return
            await self._apply_intent_locked(room, member, intent)

    async def _throw_prop_locked(self, room: Room, member: RoomPlayer, intent: ThrowPropIntent) -> None:
        if intent.action_id in member.seen_action_ids:
            await member.socket.send_json({"type": "ACTION_ACK", "actionId": intent.action_id, "revision": room.revision})
            return
        target = room.players.get(intent.target_player_id)
        now = time.monotonic()
        code = None
        if room.game_state is None or room.game_state.phase != GamePhase.RACING:
            code, message = "TAUNT_NOT_RACING", "比赛开始后才能使用互动道具"
        elif target is None or target.player.id == member.player.id:
            code, message = "INVALID_TAUNT_TARGET", "请选择房间里的其他玩家"
        elif now < member.taunt_ready_at:
            code, message = "TAUNT_COOLDOWN", "道具正在冷却，请稍等片刻"
        if code:
            await member.socket.send_json(ErrorMessage(code=code, message=message, actionId=intent.action_id).model_dump(by_alias=True))
            return
        member.seen_action_ids.add(intent.action_id)
        if len(member.seen_action_ids) > 500:
            member.seen_action_ids = {intent.action_id}
        member.taunt_ready_at = now + TAUNT_COOLDOWN_SECONDS
        # Cosmetic room traffic never advances the game revision or touches
        # pending rolls, decisions, timers, or private snapshots.
        await self._broadcast_locked(room, {
            "type": "PROP_THROWN", "id": str(uuid4()), "actionId": intent.action_id,
            "actorId": member.player.id, "actorName": member.player.name,
            "targetPlayerId": target.player.id, "targetName": target.player.name,
            "item": intent.item, "cooldownMs": TAUNT_COOLDOWN_SECONDS * 1000,
        }, include_state=False)

    async def _apply_intent_locked(
        self, room: Room, member: RoomPlayer, intent: Any, *, automated: bool = False
    ) -> bool:
        try:
            transition = await self._execute_intent_locked(
                room, member.player.id, intent, bot=member.is_bot or automated
            )
        except GameRuleError as error:
            if member.socket is not None:
                await member.socket.send_json(
                    ErrorMessage(
                        code=error.code,
                        message=str(error),
                        actionId=intent.action_id,
                    ).model_dump(by_alias=True)
                )
            return False
        await self._commit_transition_locked(room, transition, action_id=intent.action_id)
        return True

    async def _execute_intent_locked(
        self, room: Room, player_id: str, intent: Any, *, bot: bool = False
    ) -> GameTransition:
        assert room.game_state is not None
        if isinstance(intent, StartGameIntent):
            return room.engine.start(room.game_state, player_id)
        if isinstance(intent, SetVariantIntent):
            return room.engine.set_variant(room.game_state, player_id, intent.double_racer)
        if isinstance(intent, SetAutoDealIntent):
            return room.engine.set_auto_deal(room.game_state, player_id, intent.auto_deal)
        if isinstance(intent, RollStartIntent):
            return room.engine.roll_start(room.game_state, player_id)
        if isinstance(intent, DraftAthleteIntent):
            return room.engine.draft_athlete(room.game_state, player_id, intent.athlete_id)
        if isinstance(intent, SelectRacersIntent):
            return room.engine.select_racers(room.game_state, player_id, intent.athlete_ids)
        if isinstance(intent, RollDiceIntent):
            pending_roll = room.game_state.pending_roll
            rolling_player_id = (
                pending_roll.get("nextPlayerId")
                if pending_roll is not None
                else room.game_state.active_player_id
            )
            if (
                room.game_state.phase == "RACING"
                and rolling_player_id == player_id
                and room.game_state.magsim_engine is not None
                and room.game_state.pending_decision is None
                and room.game_state.resolution_status == "WAITING_FOR_ROLL"
            ):
                await self._broadcast_locked(
                    room,
                    {
                        "type": "ROLL_STARTED",
                        "actionId": intent.action_id,
                        "playerId": player_id,
                    },
                )
                # Keep the start signal visible long enough for background tabs and
                # slower WebGL clients to commit the first animation frame.
                await asyncio.sleep(ROLL_ANIMATION_LEAD_SECONDS)
            return room.engine.roll_dice(room.game_state, player_id)
        if isinstance(intent, ResolveDecisionIntent):
            return room.engine.resolve_decision(
                room.game_state,
                player_id,
                intent.decision_id,
                intent.option_id,
                bot=bot,
            )
        return room.engine.advance_race(room.game_state, player_id)

    async def _commit_transition_locked(
        self, room: Room, transition: GameTransition, *, action_id: str | None = None
    ) -> None:
        room.game_state = transition.state
        room.revision += 1
        self._sync_decision_timer_locked(room)
        self._sync_roll_timer_locked(room)
        envelope: dict[str, Any] = {
            "type": "STATE_UPDATED",
            "events": list(transition.events),
            "rollResults": self._roll_results(transition, room.revision),
        }
        if action_id is not None:
            envelope["actionId"] = action_id
        await self._broadcast_locked(room, envelope)
        self._sync_bot_timer_locked(room)

    @staticmethod
    def _lobby_open(room: Room) -> bool:
        return room.game_state is not None and room.game_state.phase == "LOBBY"

    @staticmethod
    def _host_id(room: Room) -> str | None:
        return next(iter(room.players), None)

    def _remove_member_locked(self, room: Room, player_id: str) -> RoomPlayer:
        member = room.players.pop(player_id)
        room.game_state = room.engine.create_game(
            tuple(item.player for item in room.players.values())
        )
        room.revision += 1
        return member

    async def _announce_player_left_locked(
        self, room: Room, member: RoomPlayer, *, reason: str | None = None
    ) -> None:
        event: dict[str, Any] = {
            "type": "PLAYER_LEFT",
            "playerId": member.player.id,
            "playerName": member.player.name,
        }
        if reason is not None:
            event["reason"] = reason
        await self._broadcast_locked(
            room,
            {"type": "STATE_UPDATED", "events": [event], "rollResults": []},
        )

    async def _kick_player_locked(
        self, room: Room, member: RoomPlayer, intent: KickPlayerIntent
    ) -> None:
        async def reject(code: str, message: str) -> None:
            await member.socket.send_json(
                ErrorMessage(
                    code=code, message=message, actionId=intent.action_id
                ).model_dump(by_alias=True)
            )

        if not self._lobby_open(room):
            await reject("GAME_ALREADY_STARTED", "游戏已开始，不能移出玩家")
            return
        if member.player.id != self._host_id(room):
            await reject("NOT_HOST", "只有房主可以移出玩家")
            return
        if intent.target_player_id == member.player.id:
            await reject("CANNOT_KICK_SELF", "不能移出自己，请使用退出房间")
            return
        target = room.players.get(intent.target_player_id)
        if target is None:
            await reject("PLAYER_NOT_FOUND", "该玩家不在房间中")
            return

        kicked = self._remove_member_locked(room, target.player.id)
        if kicked.socket is not None:
            await kicked.socket.send_json({"type": "KICKED"})
        await self._announce_player_left_locked(room, kicked, reason="KICKED")
        if kicked.socket is not None:
            await kicked.socket.close(code=4002, reason="removed by host")

    async def _add_bot_locked(
        self, room: Room, member: RoomPlayer, intent: AddBotIntent
    ) -> None:
        async def reject(code: str, message: str) -> None:
            await member.socket.send_json(
                ErrorMessage(
                    code=code, message=message, actionId=intent.action_id
                ).model_dump(by_alias=True)
            )

        if not self._lobby_open(room):
            await reject("GAME_ALREADY_STARTED", "游戏已开始，不能添加机器人")
            return
        if member.player.id != self._host_id(room):
            await reject("NOT_HOST", "只有房主可以添加机器人")
            return
        if len(room.players) >= 6:
            await reject("ROOM_FULL", "房间已满")
            return

        bot_number = sum(1 for item in room.players.values() if item.is_bot) + 1
        player_id = uuid4().hex
        room.players[player_id] = RoomPlayer(
            player=Player(id=player_id, name=f"Bot {bot_number}"),
            reconnect_token=secrets.token_urlsafe(24),
            socket=None,
            is_bot=True,
        )
        room.game_state = room.engine.create_game(
            tuple(item.player for item in room.players.values())
        )
        room.revision += 1
        await self._broadcast_locked(
            room,
            {
                "type": "STATE_UPDATED",
                "events": [{"type": "PLAYER_JOINED", "playerId": player_id, "bot": True}],
                "rollResults": [],
            },
        )
        self._sync_bot_timer_locked(room)

    def _sync_decision_timer_locked(self, room: Room) -> None:
        pending = room.game_state.pending_decision if room.game_state else None
        if room.decision_task is not None:
            room.decision_task.cancel()
            room.decision_task = None
        room.decision_deadline = None
        if pending is None:
            return
        if not self._is_automated(room, pending.get("playerId")):
            room.decision_deadline = datetime.now(UTC) + timedelta(seconds=ACTION_TIME_LIMIT_SECONDS)
        if not self.local_timers:
            return
        room.decision_task = asyncio.create_task(
            self._decision_timeout(room, pending["id"]),
            name=f"decision-timeout-{room.id}",
        )

    def _sync_roll_timer_locked(self, room: Room) -> None:
        pending = room.game_state.pending_roll if room.game_state else None
        if room.roll_task is not None:
            room.roll_task.cancel()
            room.roll_task = None
        room.roll_deadline = None
        if pending is None:
            return
        if not self._is_automated(room, pending.get("nextPlayerId")):
            room.roll_deadline = datetime.now(UTC) + timedelta(seconds=ACTION_TIME_LIMIT_SECONDS)
        if not self.local_timers:
            return
        room.roll_task = asyncio.create_task(
            self._roll_timeout(room, pending["id"], pending["throwIndex"]),
            name=f"roll-timeout-{room.id}",
        )

    def _is_automated(self, room: Room, player_id: str | None) -> bool:
        member = room.players.get(player_id) if player_id else None
        return member is not None and (member.is_bot or member.auto_play)

    def _bot_pending_action(self, room: Room) -> tuple[str, str] | None:
        """Return (action kind, actor player id) for the next bot obligation, if any."""
        state = room.game_state
        bots = {player_id for player_id, member in room.players.items() if member.is_bot or member.auto_play}
        if state is None or not bots:
            return None
        if state.phase in (GamePhase.DRAFT_ROLL, GamePhase.RACE_ROLL):
            for candidate in state.roll_candidates:
                if candidate in bots and candidate not in state.roll_values:
                    return ("ROLL_START", candidate)
            return None
        if state.phase == GamePhase.DRAFTING:
            active = state.active_player_id
            return ("DRAFT_ATHLETE", active) if active in bots else None
        if state.phase == GamePhase.CHARACTER_SELECTION:
            for player_id in bots:
                if player_id not in state.selections:
                    return ("SELECT_RACERS", player_id)
            return None
        if state.phase == GamePhase.RACING:
            pending_decision = state.pending_decision
            if pending_decision is not None:
                owner = pending_decision.get("playerId")
                return ("RESOLVE_DECISION", owner) if owner in bots else None
            pending_roll = state.pending_roll
            if pending_roll is not None:
                roller = pending_roll.get("nextPlayerId")
                return ("ROLL_DICE", roller) if roller in bots else None
            if state.resolution_status == "WAITING_FOR_ROLL" and state.active_player_id in bots:
                return ("ROLL_DICE", state.active_player_id)
            return None
        if state.phase == GamePhase.RACE_RESULTS:
            host_id = self._host_id(room)
            return ("ADVANCE_RACE", host_id) if host_id in bots else None
        return None

    def _build_bot_intent(self, room: Room, kind: str, player_id: str) -> Any | None:
        state = room.game_state
        if state is None:
            return None
        if kind == "ROLL_START":
            return RollStartIntent(type="ROLL_START", actionId=uuid4().hex)
        if kind == "DRAFT_ATHLETE":
            pool = [card.id for card in state.draft_pool]
            if not pool:
                return None
            return DraftAthleteIntent(
                type="DRAFT_ATHLETE",
                actionId=uuid4().hex,
                athleteId=self._rng.choice(pool),
            )
        if kind == "SELECT_RACERS":
            count = room.engine.public_state(state, player_id)["selectionCount"]
            team = [
                card.id
                for card in state.teams.get(player_id, ())
                if card.id not in state.used_athlete_ids
            ]
            if len(team) < count:
                return None
            return SelectRacersIntent(
                type="SELECT_RACERS",
                actionId=uuid4().hex,
                athleteIds=tuple(self._rng.sample(team, count)),
            )
        if kind == "ROLL_DICE":
            return RollDiceIntent(type="ROLL_DICE", actionId=uuid4().hex)
        if kind == "RESOLVE_DECISION":
            decision = state.pending_decision
            options = list(decision.get("options", ())) if decision else []
            if decision is None or not options:
                return None
            return ResolveDecisionIntent(
                type="RESOLVE_DECISION",
                actionId=uuid4().hex,
                decisionId=decision["id"],
                optionId=str(options[0]["id"]),
            )
        if kind == "ADVANCE_RACE":
            return AdvanceRaceIntent(type="ADVANCE_RACE", actionId=uuid4().hex)
        return None

    def _sync_bot_timer_locked(self, room: Room) -> None:
        if room.bot_task is not None:
            room.bot_task.cancel()
            room.bot_task = None
        room.bot_deadline = None
        action = self._bot_pending_action(room)
        if action is None:
            return
        room.bot_deadline = datetime.now(UTC) + timedelta(seconds=BOT_ACTION_DELAY_SECONDS)
        if not self.local_timers:
            return
        room.bot_task = asyncio.create_task(
            self._bot_turn(room, action), name=f"bot-turn-{room.id}"
        )

    async def _bot_turn(self, room: Room, action: tuple[str, str]) -> None:
        try:
            await asyncio.sleep(BOT_ACTION_DELAY_SECONDS)
            async with room.lock:
                room.bot_task = None
                if self._bot_pending_action(room) == action:
                    await self._take_bot_action_locked(room, action)
                else:
                    self._sync_bot_timer_locked(room)
        except asyncio.CancelledError:
            return
        except Exception:  # noqa: BLE001 - a stalled bot must not break the room loop.
            room.bot_deadline = None

    async def resolve_bot_action(self, room: Room, now: datetime | None = None) -> bool:
        async with room.lock:
            if room.bot_deadline is None or room.bot_deadline > (now or datetime.now(UTC)):
                return False
            action = self._bot_pending_action(room)
            room.bot_deadline = None
            if action is None:
                return False
            await self._take_bot_action_locked(room, action)
            return True

    async def _take_bot_action_locked(self, room: Room, action: tuple[str, str]) -> None:
        kind, player_id = action
        member = room.players.get(player_id)
        if member is None or not (member.is_bot or member.auto_play):
            room.bot_deadline = None
            return
        intent = self._build_bot_intent(room, kind, player_id)
        if intent is None:
            room.bot_deadline = None
            return
        if not await self._apply_intent_locked(room, member, intent, automated=True):
            room.bot_deadline = None

    async def _roll_timeout(
        self,
        room: Room,
        roll_id: str,
        throw_index: int,
    ) -> None:
        try:
            await asyncio.sleep(ACTION_TIME_LIMIT_SECONDS)
            async with room.lock:
                state = room.game_state
                pending = state.pending_roll if state else None
                if (
                    state is None
                    or pending is None
                    or pending["id"] != roll_id
                    or pending["throwIndex"] != throw_index
                ):
                    return
                transition = room.engine.roll_dice(
                    state,
                    pending["nextPlayerId"],
                    timed_out=True,
                )
                room.game_state = transition.state
                room.revision += 1
                room.roll_task = None
                room.roll_deadline = None
                self._sync_decision_timer_locked(room)
                self._sync_roll_timer_locked(room)
                self._sync_bot_timer_locked(room)
                await self._broadcast_locked(
                    room,
                    {
                        "type": "STATE_UPDATED",
                        "events": list(transition.events),
                        "rollResults": self._roll_results(transition, room.revision),
                    },
                )
        except asyncio.CancelledError:
            return

    async def _decision_timeout(self, room: Room, decision_id: str) -> None:
        try:
            await asyncio.sleep(ACTION_TIME_LIMIT_SECONDS)
            async with room.lock:
                state = room.game_state
                if state is None or state.pending_decision is None or state.pending_decision["id"] != decision_id:
                    return
                player_id = state.pending_decision["playerId"]
                transition = room.engine.resolve_decision(
                    state, player_id, decision_id, "", timed_out=True
                )
                room.game_state = transition.state
                room.revision += 1
                room.decision_task = None
                room.decision_deadline = None
                if transition.state.pending_decision is not None:
                    self._sync_decision_timer_locked(room)
                self._sync_roll_timer_locked(room)
                self._sync_bot_timer_locked(room)
                await self._broadcast_locked(
                    room,
                    {
                        "type": "STATE_UPDATED",
                        "events": list(transition.events),
                        "rollResults": self._roll_results(transition, room.revision),
                    },
                )
        except asyncio.CancelledError:
            return

    async def resolve_expired_decision(self, room: Room, now: datetime | None = None) -> bool:
        async with room.lock:
            state = room.game_state
            current_time = now or datetime.now(UTC)
            if (
                state is None
                or state.pending_decision is None
                or room.decision_deadline is None
                or room.decision_deadline > current_time
            ):
                return False
            decision_id = state.pending_decision["id"]
            player_id = state.pending_decision["playerId"]
            transition = room.engine.resolve_decision(state, player_id, decision_id, "", timed_out=True)
            room.game_state = transition.state
            room.revision += 1
            room.decision_deadline = None
            if transition.state.pending_decision is not None:
                self._sync_decision_timer_locked(room)
            self._sync_roll_timer_locked(room)
            self._sync_bot_timer_locked(room)
            await self._broadcast_locked(room, {
                "type": "STATE_UPDATED",
                "events": list(transition.events),
                "rollResults": self._roll_results(transition, room.revision),
            })
            return True

    async def resolve_expired_roll(self, room: Room, now: datetime | None = None) -> bool:
        async with room.lock:
            state = room.game_state
            current_time = now or datetime.now(UTC)
            if (
                state is None
                or state.pending_roll is None
                or room.roll_deadline is None
                or room.roll_deadline > current_time
            ):
                return False
            pending = state.pending_roll
            transition = room.engine.roll_dice(
                state,
                pending["nextPlayerId"],
                timed_out=True,
            )
            room.game_state = transition.state
            room.revision += 1
            room.roll_deadline = None
            self._sync_decision_timer_locked(room)
            self._sync_roll_timer_locked(room)
            self._sync_bot_timer_locked(room)
            await self._broadcast_locked(room, {
                "type": "STATE_UPDATED",
                "events": list(transition.events),
                "rollResults": self._roll_results(transition, room.revision),
            })
            return True

    async def disconnect(self, room: Room, player_id: str, websocket: RoomSocket) -> None:
        async with room.lock:
            member = room.member(player_id)
            if member is None or member.socket is not websocket:
                return
            member.connected = False
            member.socket = None
            room.revision += 1
            await self._broadcast_locked(
                room,
                {
                    "type": "STATE_UPDATED",
                    "events": [{"type": "SPECTATOR_DISCONNECTED" if player_id in room.spectators else "PLAYER_DISCONNECTED", "playerId": player_id}],
                    "rollResults": [],
                },
            )

    async def _broadcast_locked(
        self,
        room: Room,
        envelope: dict[str, Any],
        exclude: RoomSocket | None = None,
        *, include_state: bool = True,
    ) -> None:
        failed: list[RoomPlayer] = []
        for recipient_id, member in (room.players | room.spectators).items():
            if not member.connected or member.socket is None or member.socket is exclude:
                continue
            try:
                message = {**envelope, **room.public_state(recipient_id)} if include_state else dict(envelope)
                await member.socket.send_json(message)
            except RuntimeError:
                failed.append(member)
        for member in failed:
            member.connected = False
            member.socket = None

    @staticmethod
    def _roll_results(transition: GameTransition, revision: int) -> list[dict[str, Any]]:
        race_number = transition.state.race_number
        results: list[dict[str, Any]] = []
        results_by_id: dict[str, dict[str, Any]] = {}
        seen_serials: set[int] = set()
        for index, event in enumerate(transition.events):
            if event.get("type") == "START_DICE_ROLLED":
                result = {
                    "id": f"revision:{revision}:event:{index}",
                    "kind": "ROLL_OFF",
                    "playerId": event.get("playerId"),
                    "values": list(event.get("values", [])),
                }
                results.append(result)
                results_by_id[result["id"]] = result
            elif event.get("type") in {"DIE_ROLLED", "ABILITY_DICE_ROLLED"}:
                result_id = event.get("rollResultId") or f"revision:{revision}:event:{index}"
                participant = {
                    "playerId": event.get("playerId"),
                    "athleteId": event.get("athleteId"),
                }
                result = {
                    "id": result_id,
                    "kind": event.get("kind"),
                    "playerId": event.get("playerId"),
                    "athleteId": event.get("athleteId"),
                    "values": [event["value"]],
                    "participants": [participant],
                    "abilityName": event.get("abilityName"),
                    "rollSessionId": event.get("rollSessionId"),
                    "throwIndex": event.get("throwIndex"),
                    "throwCount": event.get("throwCount"),
                }
                results.append(result)
                results_by_id[result_id] = result
            elif event.get("type") == "DICE_ROLLED" and isinstance(event.get("value"), int):
                serial = event.get("rollSerial")
                result_id = event.get("rollResultId")
                if not result_id:
                    result_id = (
                        f"race:{race_number}:serial:{serial}"
                        if isinstance(serial, int)
                        else f"revision:{revision}:event:{index}"
                    )
                if isinstance(serial, int):
                    seen_serials.add(serial)
                no_dice = bool(event.get("noDice"))
                result = results_by_id.get(result_id)
                if result is None:
                    result = {
                        "id": result_id,
                        "kind": "MAIN_ROLL",
                        "playerId": event.get("playerId"),
                        "athleteId": event.get("athleteId"),
                        # An overridden main move (Legs' jog) rolls no die, so it
                        # must not push a face onto the table.
                        "values": [] if no_dice else [event["value"]],
                        "noDice": no_dice,
                        "rollSessionId": event.get("rollSessionId"),
                    }
                    results.append(result)
                    results_by_id[result_id] = result
                result.update({
                    "baseValue": event.get("baseValue"),
                    "finalValue": event.get("finalValue"),
                    "rollSerial": serial,
                })

        pending = transition.state.pending_decision
        preview = pending.get("rollPreview") if pending else None
        if preview and preview["rollSerial"] not in seen_serials:
            result_id = preview.get("rollResultId") or f"race:{race_number}:serial:{preview['rollSerial']}"
            if result_id not in results_by_id:
                results.append({
                    "id": result_id,
                    "kind": "MAIN_ROLL",
                    "playerId": pending.get("playerId"),
                    "athleteId": pending.get("athleteId"),
                    "values": [preview["value"]],
                    **preview,
                })
        return results
