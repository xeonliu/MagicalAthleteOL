from dataclasses import replace

import pytest

from magical_athlete.game import GamePhase, Player
from magical_athlete.protocol import JoinRoomIntent, LeaveRoomIntent, RollDiceIntent, StartGameIntent, AddBotIntent
from magical_athlete.rooms import InMemoryRoomRepository, RoomManager, RoomPlayer, RoomError, SPECTATOR_LIMIT
from test_rooms import RecordingSocket


@pytest.fixture
def anyio_backend():
    return 'asyncio'


async def watching_room():
    repository = InMemoryRoomRepository()
    room = await repository.create(4)
    players = tuple(Player(str(i), f'Player {i}') for i in range(6))
    room.players = {p.id: RoomPlayer(p, f'token-{p.id}', socket=RecordingSocket()) for p in players}
    room.game_state = replace(room.engine.create_game(players), phase=GamePhase.RACING)
    return room, RoomManager(repository, local_timers=False)


@pytest.mark.anyio
async def test_spectator_joins_full_started_room_and_receives_public_updates():
    room, manager = await watching_room()
    original = room.game_state
    socket = RecordingSocket()
    _, spectator_id = await manager.join(socket, JoinRoomIntent(type='JOIN_ROOM', roomId=room.id, playerName='Watcher', role='spectator'))
    assert room.game_state is original
    assert len(room.players) == 6
    assert spectator_id in room.spectators
    welcome = socket.messages[0]
    assert welcome['viewerRole'] == 'spectator'
    assert welcome['game']['hand'] == []
    assert len(welcome['game']['players']) == 6
    assert welcome['spectators'][0]['name'] == 'Watcher'
    await manager._broadcast_locked(room, {'type': 'STATE_UPDATED', 'events': [{'type': 'TEST'}], 'rollResults': []})
    assert socket.messages[-1]['events'] == [{'type': 'TEST'}]
    assert socket.messages[-1]['viewerRole'] == 'spectator'
    assert room.players['0'].socket.messages[-1]['viewerRole'] == 'player'


@pytest.mark.anyio
@pytest.mark.parametrize('intent', [RollDiceIntent(type='ROLL_DICE', actionId='roll'),
                                   StartGameIntent(type='START_GAME', actionId='start'),
                                   AddBotIntent(type='ADD_BOT', actionId='bot')])
async def test_spectator_cannot_send_game_actions(intent):
    room, manager = await watching_room()
    socket = RecordingSocket()
    _, member_id = await manager.join(socket, JoinRoomIntent(type='JOIN_ROOM', roomId=room.id, playerName='Watcher', role='spectator'))
    state, revision = room.game_state, room.revision
    await manager.handle_intent(room, member_id, intent)
    assert socket.messages[-1]['code'] == 'SPECTATOR_READ_ONLY'
    assert room.game_state is state and room.revision == revision


@pytest.mark.anyio
async def test_spectator_reconnect_and_leave_during_a_race():
    room, manager = await watching_room()
    original = RecordingSocket()
    _, member_id = await manager.join(original, JoinRoomIntent(type='JOIN_ROOM', roomId=room.id, playerName='Watcher', role='spectator'))
    token = original.messages[0]['reconnectToken']
    await manager.disconnect(room, member_id, original)
    replacement = RecordingSocket()
    intent = JoinRoomIntent(type='JOIN_ROOM', roomId=room.id, playerName='Watcher', playerId=member_id, reconnectToken=token, role='spectator')
    await manager.join(replacement, intent)
    assert len(room.spectators) == 1 and room.spectators[member_id].connected
    with pytest.raises(RoomError, match='重连凭证无效'):
        await manager.join(RecordingSocket(), intent.model_copy(update={'role': 'player'}))
    before = room.game_state
    await manager.handle_intent(room, member_id, LeaveRoomIntent(type='LEAVE_ROOM', actionId='leave'))
    assert replacement.messages[-1]['type'] == 'ROOM_LEFT'
    assert member_id not in room.spectators
    assert room.game_state is before and len(room.players) == 6


@pytest.mark.anyio
async def test_spectator_seat_limit_is_independent_of_player_seats():
    room, manager = await watching_room()
    for i in range(SPECTATOR_LIMIT):
        await manager.join(RecordingSocket(), JoinRoomIntent(type='JOIN_ROOM', roomId=room.id, playerName=f'Watcher {i}', role='spectator'))
    with pytest.raises(RoomError) as error:
        await manager.join(RecordingSocket(), JoinRoomIntent(type='JOIN_ROOM', roomId=room.id, playerName='Overflow', role='spectator'))
    assert error.value.code == 'SPECTATORS_FULL'
    assert len(room.players) == 6
