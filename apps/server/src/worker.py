from __future__ import annotations

import json
import secrets
import string
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

from pydantic import TypeAdapter, ValidationError
from js import WebSocketPair
from workers import DurableObject, Request, Response, WorkerEntrypoint

from magical_athlete.game import MagsimGameEngine
from magical_athlete.protocol import ClientIntent, ErrorMessage, JoinRoomIntent
from magical_athlete.rooms import (
    InMemoryRoomRepository,
    Room,
    RoomError,
    RoomManager,
    RoomPlayer,
)
from magical_athlete.snapshots import (
    IncompatibleSnapshotError,
    RoomSnapshot,
    SnapshotPlayer,
    decode_snapshot,
    encode_snapshot,
)

ALLOWED_ORIGINS = {
    "https://xeonliu.github.io",
    "https://magical-athlete.pages.dev",
    "https://html-classic.itch.zone",
    "http://localhost:5173",
    "http://localhost:8080",
}
ROOM_TTL = timedelta(hours=24)
intent_adapter = TypeAdapter(ClientIntent)


def json_response(data: dict, status: int = 200, origin: str | None = None) -> Response:
    headers = {"content-type": "application/json"}
    if origin in ALLOWED_ORIGINS:
        headers.update({
            "access-control-allow-origin": origin,
            "vary": "Origin",
            "access-control-allow-methods": "GET, POST, OPTIONS",
            "access-control-allow-headers": "content-type",
        })
    return Response(json.dumps(data), status=status, headers=headers)


class WorkerSocket:
    def __init__(self, websocket) -> None:
        self.websocket = websocket

    async def send_json(self, message: dict) -> None:
        self.websocket.send(json.dumps(message))

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.websocket.close(code, reason)


class Default(WorkerEntrypoint):
    async def fetch(self, request):
        parsed = urlparse(request.url)
        origin = request.headers.get("origin")
        if request.method == "OPTIONS":
            return json_response({}, origin=origin)
        if parsed.path == "/api/health" and request.method == "GET":
            return json_response({"status": "ok"}, origin=origin)
        if parsed.path == "/api/rooms" and request.method == "POST":
            if origin and origin not in ALLOWED_ORIGINS:
                return json_response({"error": "origin not allowed"}, 403)
            for _ in range(20):
                room_id = "".join(secrets.choice(string.ascii_uppercase) for _ in range(4))
                stub = self.env.ROOMS.getByName(room_id)
                response = await stub.fetch(
                    Request(f"https://room/init?roomId={room_id}", method="POST")
                )
                if response.status == 201:
                    return json_response({"roomId": room_id}, 201, origin)
            return json_response({"error": "room code exhausted"}, 503, origin)
        if parsed.path == "/ws" and request.method == "GET":
            if origin not in ALLOWED_ORIGINS:
                return json_response({"error": "origin not allowed"}, 403)
            room_id = parse_qs(parsed.query).get("roomId", [""])[0].upper()
            if len(room_id) != 4 or not room_id.isalpha():
                return json_response({"error": "invalid room id"}, 400, origin)
            stub = self.env.ROOMS.getByName(room_id)
            return await stub.fetch(request)
        return json_response({"error": "not found"}, 404, origin)


class RoomDurableObject(DurableObject):
    def __init__(self, ctx, env) -> None:
        super().__init__(ctx, env)
        self.ctx = ctx
        self.room: Room | None = None
        self.last_active_at = datetime.now(UTC)
        self.repository = InMemoryRoomRepository()
        self.manager = RoomManager(self.repository, local_timers=False)

    async def _load(self, room_id: str) -> Room | None:
        if self.room is not None:
            return self.room
        raw = await self.ctx.storage.get("snapshot")
        if raw is None:
            return None
        try:
            snapshot = decode_snapshot(bytes(raw))
        except IncompatibleSnapshotError:
            # Stale schema from an older deploy; the room is disposable.
            await self.ctx.storage.deleteAll()
            return None
        room = Room(
            id=snapshot.room_id,
            engine=MagsimGameEngine(),
            game_state=snapshot.game_state,
            revision=snapshot.revision,
            decision_deadline=snapshot.decision_deadline,
            roll_deadline=snapshot.roll_deadline,
            bot_deadline=snapshot.bot_deadline,
            players={
                player_id: RoomPlayer(
                    player=item.player,
                    reconnect_token=item.reconnect_token,
                    connected=False,
                    seen_action_ids=set(item.seen_action_ids),
                    is_bot=item.is_bot,
                    auto_play=item.auto_play,
                )
                for player_id, item in snapshot.players.items()
            },
            spectators={
                member_id: RoomPlayer(player=item.player, reconnect_token=item.reconnect_token,
                                      connected=False, seen_action_ids=set(item.seen_action_ids))
                for member_id, item in snapshot.spectators.items()
            },
        )
        self.room = room
        self.last_active_at = snapshot.last_active_at
        self.repository._rooms[room.id] = room
        self._restore_connections()
        return room

    def _restore_connections(self) -> None:
        if self.room is None:
            return
        for websocket in self.ctx.getWebSockets():
            player_id = websocket.deserializeAttachment()
            if not player_id:
                continue
            member = self.room.member(player_id)
            if member is not None:
                member.connected = True
                member.socket = WorkerSocket(websocket)

    async def _save(self) -> None:
        if self.room is None:
            return
        snapshot = RoomSnapshot(
            room_id=self.room.id,
            players={
                player_id: SnapshotPlayer(
                    player=member.player,
                    reconnect_token=member.reconnect_token,
                    seen_action_ids=set(member.seen_action_ids),
                    is_bot=member.is_bot,
                    auto_play=member.auto_play,
                )
                for player_id, member in self.room.players.items()
            },
            game_state=self.room.game_state,
            revision=self.room.revision,
            decision_deadline=self.room.decision_deadline,
            roll_deadline=self.room.roll_deadline,
            last_active_at=self.last_active_at,
            bot_deadline=self.room.bot_deadline,
            spectators={member_id: SnapshotPlayer(member.player, member.reconnect_token, set(member.seen_action_ids))
                        for member_id, member in self.room.spectators.items()},
        )
        await self.ctx.storage.put("snapshot", encode_snapshot(snapshot))
        expiry = self.last_active_at + ROOM_TTL
        deadlines = [expiry]
        if self.room.decision_deadline is not None:
            deadlines.append(self.room.decision_deadline)
        if self.room.roll_deadline is not None:
            deadlines.append(self.room.roll_deadline)
        if self.room.bot_deadline is not None:
            deadlines.append(self.room.bot_deadline)
        alarm_at = min(deadlines)
        await self.ctx.storage.setAlarm(int(alarm_at.timestamp() * 1000))

    async def fetch(self, request):
        parsed = urlparse(request.url)
        room_id = parse_qs(parsed.query).get("roomId", [""])[0].upper()
        room = await self._load(room_id)
        if parsed.path == "/init" and request.method == "POST":
            if room is not None:
                return Response("exists", status=409)
            self.room = Room(id=room_id, engine=MagsimGameEngine())
            self.repository._rooms[room_id] = self.room
            self.last_active_at = datetime.now(UTC)
            await self._save()
            return Response("created", status=201)
        if room is None:
            return Response("room not found", status=404)
        client, server = WebSocketPair.new().object_values()
        self.ctx.acceptWebSocket(server)
        self.last_active_at = datetime.now(UTC)
        await self._save()
        return Response(status=101, web_socket=client)

    async def webSocketMessage(self, websocket, message) -> None:
        room_id = self.room.id if self.room else ""
        room = await self._load(room_id)
        if room is None:
            websocket.close(1008, "room not found")
            return
        socket = WorkerSocket(websocket)
        try:
            raw = json.loads(message.decode() if isinstance(message, bytes) else message)
            intent = intent_adapter.validate_python(raw)
            player_id = websocket.deserializeAttachment()
            # An unset attachment is JavaScript `undefined`, not Python `None`.
            if not player_id:
                if not isinstance(intent, JoinRoomIntent):
                    await socket.send_json(ErrorMessage(code="JOIN_REQUIRED", message="第一条消息必须加入房间").model_dump(by_alias=True))
                    await socket.close(1008, "join required")
                    return
                _, player_id = await self.manager.join(socket, intent)
                websocket.serializeAttachment(player_id)
            elif isinstance(intent, JoinRoomIntent):
                await socket.send_json(ErrorMessage(code="ALREADY_JOINED", message="已经加入房间").model_dump(by_alias=True))
            else:
                member = room.member(player_id)
                if member is None:
                    raise RoomError("INVALID_RECONNECT_TOKEN", "重连凭证无效")
                member.connected = True
                member.socket = socket
                await self.manager.handle_intent(room, player_id, intent)
            self.last_active_at = datetime.now(UTC)
            await self._save()
        except (ValidationError, json.JSONDecodeError):
            await socket.send_json(ErrorMessage(code="INVALID_MESSAGE", message="消息格式无效").model_dump(by_alias=True))
        except RoomError as error:
            await socket.send_json(ErrorMessage(code=error.code, message=str(error)).model_dump(by_alias=True))
            await socket.close(1008, str(error))
        except Exception as error:
            print(json.dumps({
                "level": "error",
                "message": "websocket intent failed",
                "error": repr(error),
                "roomId": room_id,
            }))
            await socket.send_json(
                ErrorMessage(code="INTERNAL_ERROR", message="服务器处理行动失败，请重试").model_dump(by_alias=True)
            )

    async def webSocketClose(self, websocket, code, reason, was_clean) -> None:
        if self.room is None:
            return
        player_id = websocket.deserializeAttachment()
        if player_id:
            member = self.room.member(player_id)
            if (
                member is not None
                and isinstance(member.socket, WorkerSocket)
                and member.socket.websocket is websocket
            ):
                await self.manager.disconnect(self.room, player_id, member.socket)
            self.last_active_at = datetime.now(UTC)
            await self._save()

    async def webSocketError(self, websocket, error) -> None:
        await self.webSocketClose(websocket, 1011, str(error), False)

    async def alarm(self) -> None:
        if self.room is None:
            raw = await self.ctx.storage.get("snapshot")
            if raw is None:
                return
            if await self._load("") is None:
                return
        assert self.room is not None
        now = datetime.now(UTC)
        await self.manager.resolve_bot_action(self.room, now)
        await self.manager.resolve_expired_decision(self.room, now)
        await self.manager.resolve_expired_roll(self.room, now)
        if (
            not self.ctx.getWebSockets()
            and self.room.decision_deadline is None
            and self.room.roll_deadline is None
            and self.room.bot_deadline is None
            and now >= self.last_active_at + ROOM_TTL
        ):
            await self.ctx.storage.deleteAll()
            self.room = None
            return
        await self._save()
