from dataclasses import replace

import pytest
from pydantic import TypeAdapter, ValidationError

from magical_athlete.game import GamePhase
from magical_athlete.protocol import ClientIntent, JoinRoomIntent, ThrowPropIntent
from test_rooms import RecordingSocket
from test_spectators import watching_room


@pytest.fixture
def anyio_backend():
    return "asyncio"


def throw(action="prop-1", target="1", item="egg"):
    return ThrowPropIntent(type="THROW_PROP", actionId=action, targetPlayerId=target, item=item)


@pytest.mark.anyio
async def test_props_broadcast_without_changing_game_state_or_private_snapshots():
    room, manager = await watching_room()
    socket = RecordingSocket()
    _, spectator = await manager.join(socket, JoinRoomIntent(type="JOIN_ROOM", roomId=room.id, playerName="Watcher", role="spectator"))
    state, revision, roll_deadline, decision_deadline = room.game_state, room.revision, room.roll_deadline, room.decision_deadline
    await manager.handle_intent(room, "0", throw())
    for member in (room.players | room.spectators).values():
        message = member.socket.messages[-1]
        assert message["type"] == "PROP_THROWN"
        assert message["actorId"] == "0" and message["targetPlayerId"] == "1"
        assert message["item"] == "egg" and message["cooldownMs"] == 4000
        assert "game" not in message and "revision" not in message
    assert room.game_state is state and room.revision == revision
    assert room.roll_deadline is roll_deadline and room.decision_deadline is decision_deadline
    await manager.handle_intent(room, spectator, throw("watcher-prop", item="tomato"))
    assert room.players["1"].socket.messages[-1]["actorName"] == "Watcher"
    assert room.game_state is state and room.revision == revision


@pytest.mark.anyio
async def test_prop_retry_is_deduplicated_and_cooldown_is_per_sender():
    room, manager = await watching_room()
    await manager.handle_intent(room, "0", throw())
    recipient = room.players["1"].socket
    count = len(recipient.messages)
    await manager.handle_intent(room, "0", throw())
    assert room.players["0"].socket.messages[-1]["type"] == "ACTION_ACK"
    assert len(recipient.messages) == count
    await manager.handle_intent(room, "0", throw("too-soon"))
    assert room.players["0"].socket.messages[-1]["code"] == "TAUNT_COOLDOWN"
    assert len(recipient.messages) == count
    await manager.handle_intent(room, "2", throw("other-sender"))
    assert recipient.messages[-1]["actorId"] == "2"
    room.players["0"].taunt_ready_at = 0
    await manager.handle_intent(room, "0", throw("after-cooldown"))
    assert recipient.messages[-1]["actorId"] == "0"


@pytest.mark.anyio
@pytest.mark.parametrize("target", ["0", "missing"])
async def test_invalid_target_cannot_broadcast_or_spend_cooldown(target):
    room, manager = await watching_room()
    await manager.handle_intent(room, "0", throw(target=target))
    assert room.players["0"].socket.messages[-1]["code"] == "INVALID_TAUNT_TARGET"
    assert room.players["0"].taunt_ready_at == 0
    assert not room.players["1"].socket.messages


@pytest.mark.anyio
@pytest.mark.parametrize("phase", [GamePhase.LOBBY, GamePhase.RACE_RESULTS, GamePhase.FINISHED])
async def test_props_only_work_during_a_race(phase):
    room, manager = await watching_room()
    room.game_state = replace(room.game_state, phase=phase)
    await manager.handle_intent(room, "0", throw())
    assert room.players["0"].socket.messages[-1]["code"] == "TAUNT_NOT_RACING"
    assert not room.players["1"].socket.messages


def test_only_supported_props_are_accepted_by_protocol():
    adapter = TypeAdapter(ClientIntent)
    with pytest.raises(ValidationError):
        adapter.validate_python({"type": "THROW_PROP", "actionId": "invalid", "targetPlayerId": "1", "item": "unknown"})
