from typing import Annotated

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import TypeAdapter, ValidationError

from .config import settings
from .protocol import ClientIntent, ErrorMessage, JoinRoomIntent
from .rooms import InMemoryRoomRepository, RoomError, RoomManager


app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

repository = InMemoryRoomRepository()
rooms = RoomManager(repository)
intent_adapter = TypeAdapter(ClientIntent)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/rooms", status_code=201)
async def create_room() -> dict[str, str]:
    room = await repository.create(settings.room_code_length)
    return {"roomId": room.id}


@app.websocket("/ws")
async def room_socket(websocket: WebSocket) -> None:
    origin = websocket.headers.get("origin")
    if origin not in settings.allowed_origins:
        await websocket.close(code=1008, reason="origin not allowed")
        return
    await websocket.accept()
    room = None
    player_id = None
    try:
        raw = await websocket.receive_json()
        intent = intent_adapter.validate_python(raw)
        if not isinstance(intent, JoinRoomIntent):
            await websocket.send_json(
                ErrorMessage(code="JOIN_REQUIRED", message="第一条消息必须加入房间").model_dump(
                    by_alias=True
                )
            )
            await websocket.close(code=1008)
            return

        room, player_id = await rooms.join(websocket, intent)
        while True:
            raw = await websocket.receive_json()
            intent = intent_adapter.validate_python(raw)
            if isinstance(intent, JoinRoomIntent):
                await websocket.send_json(
                    ErrorMessage(code="ALREADY_JOINED", message="已经加入房间").model_dump(
                        by_alias=True
                    )
                )
                continue
            await rooms.handle_intent(room, player_id, intent)
            if room.member(player_id) is None:
                break
    except ValidationError:
        await websocket.send_json(
            ErrorMessage(code="INVALID_MESSAGE", message="消息格式无效").model_dump(by_alias=True)
        )
    except RoomError as error:
        await websocket.send_json(
            ErrorMessage(code=error.code, message=str(error)).model_dump(by_alias=True)
        )
        await websocket.close(code=1008)
    except WebSocketDisconnect:
        pass
    finally:
        if room is not None and player_id is not None:
            await rooms.disconnect(room, player_id, websocket)
