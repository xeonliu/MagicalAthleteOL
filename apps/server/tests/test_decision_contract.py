"""Adversarial checks for user choices, replay and timeout recovery."""
from types import SimpleNamespace

import pytest

from magsim.core.agent import SelectionDecisionContext
from magsim.core.interactive import DecisionBroker, DecisionRequired, InteractiveAgent


def context(source, options):
    return SelectionDecisionContext(source, None, SimpleNamespace(roll_state=None), 0, options)


def test_timeout_for_repeated_ability_uses_second_context_not_replayed_first():
    source = SimpleNamespace(name='GeniusPrediction', choice_type='DIE',
                             get_auto_selection_decision=lambda engine, ctx: max(ctx.options))
    broker = DecisionBroker()
    agent = InteractiveAgent(broker)
    first = context(source, (6, 1))
    second = context(source, (1, 6))
    with pytest.raises(DecisionRequired):
        agent.make_selection_decision(None, first)
    broker.choose(broker.pending.id, '0')
    broker.rewind()
    assert agent.make_selection_decision(None, first) == 6
    with pytest.raises(DecisionRequired):
        agent.make_selection_decision(None, second)
    broker.choose_smart(None)
    broker.rewind()
    assert agent.make_selection_decision(None, first) == 6
    assert agent.make_selection_decision(None, second) == 6


def test_boolean_timeout_is_not_evaluated_against_an_earlier_replayed_choice():
    from magsim.core.agent import DecisionContext
    source = SimpleNamespace(name='SuckerfishRide',
        get_auto_boolean_decision=lambda engine, ctx: ctx.event.end_tile > 5)
    broker = DecisionBroker()
    agent = InteractiveAgent(broker)
    first = DecisionContext(source, SimpleNamespace(end_tile=2, start_tile=0, target_racer_idx=1), SimpleNamespace(roll_state=None), 0)
    second = DecisionContext(source, SimpleNamespace(end_tile=8, start_tile=0, target_racer_idx=1), SimpleNamespace(roll_state=None), 0)
    with pytest.raises(DecisionRequired):
        agent.make_boolean_decision(None, first)
    broker.choose(broker.pending.id, '0')
    broker.rewind()
    assert agent.make_boolean_decision(None, first) is False
    with pytest.raises(DecisionRequired):
        agent.make_boolean_decision(None, second)
    broker.choose_smart(None)
    broker.rewind()
    assert agent.make_boolean_decision(None, first) is False
    assert agent.make_boolean_decision(None, second) is True


def selection_game(first='hypnotist', second='coach', seed=3, winners=()):
    import random
    from dataclasses import replace
    from magical_athlete.athletes import ATHLETE_BY_ID
    from magical_athlete.game import GamePhase, MagsimGameEngine, Player
    engine = MagsimGameEngine(random.Random(seed))
    state = replace(engine.create_game((Player('a', 'A'), Player('b', 'B'))),
        phase=GamePhase.CHARACTER_SELECTION, first_turn_player_id='a',
        race_winner_ids=tuple(winners),
        teams={'a': (ATHLETE_BY_ID[first], ATHLETE_BY_ID['blimp']),
               'b': (ATHLETE_BY_ID[second], ATHLETE_BY_ID['banana'])})
    state = engine.select_racers(state, 'a', (first, 'blimp')).state
    state = engine.select_racers(state, 'b', (second, 'banana')).state
    return engine, state


@pytest.mark.parametrize('option', ['99', '-1', 'skip'])
def test_required_prediction_rejects_invalid_options_without_consuming_choice(option):
    from magical_athlete.game import GameRuleError
    engine, state = selection_game('genius')
    choice = state.pending_decision
    with pytest.raises(GameRuleError) as error:
        engine.resolve_decision(state, 'a', choice['id'], option)
    assert error.value.code == 'INVALID_DECISION_OPTION'
    assert state.pending_decision == choice
    state = engine.resolve_decision(state, 'a', choice['id'], '4').state
    ability = next(a for a in state.magsim_engine.get_racer(0).active_abilities if a.name == 'GeniusPrediction')
    assert ability.prediction == 5


@pytest.mark.parametrize('athlete', ['egg', 'twin'])
@pytest.mark.parametrize('option', [0, 1, 2])
def test_each_setup_candidate_copies_the_displayed_racer(athlete, option):
    engine, state = selection_game(athlete, winners=('coach', 'legs', 'genius'))
    choice = state.pending_decision
    expected = choice['options'][option]['label']
    expected_card = choice['options'][option]['athlete']
    state = engine.resolve_decision(state, 'a', choice['id'], str(option)).state
    ability = next(a for a in state.magsim_engine.get_racer(0).active_abilities
                   if a.name == ('EggCopy' if athlete == 'egg' else 'TwinCopy'))
    assert ability.copied_racer == expected
    if athlete == 'twin':
        public = engine.public_state(state, 'a')['players'][0]['activeRacers'][0]
        assert public['id'] == 'twin'
        assert public['copiedAthlete'] == expected_card
    else:
        public = engine.public_state(state, 'a')['players'][0]['activeRacers'][0]
        assert public['id'] == 'egg'
        assert public['copiedAthlete'] == expected_card


def test_twin_has_no_invented_champions_in_the_first_race():
    engine, state = selection_game('twin')
    assert not state.pending_decision or state.pending_decision['abilityName'] != 'TwinCopy'
    twin = state.magsim_engine.get_racer(0)
    assert next(a for a in twin.active_abilities if a.name == 'TwinCopy').copied_racer is None
    assert 'copiedAthlete' not in engine.public_state(state)['players'][0]['activeRacers'][0]


def test_twin_candidates_are_exactly_the_unique_actual_previous_winners():
    engine, state = selection_game('twin', winners=('legs', 'genius', 'legs'))
    assert [option['athlete']['id'] for option in state.pending_decision['options']] == ['legs', 'genius']
    state = engine.resolve_decision(state, 'a', state.pending_decision['id'], '1').state
    assert any(a.name == 'GeniusPrediction' for a in state.magsim_engine.get_racer(0).active_abilities)


def test_champions_survive_advancing_to_the_next_race():
    from dataclasses import replace
    engine, state = selection_game('coach', 'skipper')
    racer = state.magsim_engine.get_racer(0)
    racer.finish_position = 1
    racer.victory_points = 3
    finished = engine._finish_race(state, []).state
    assert finished.race_winner_ids == ('coach',)
    next_race = engine.advance_race(finished, 'a').state
    assert not next_race.race_results
    assert next_race.race_winner_ids == ('coach',)
    from magical_athlete.athletes import ATHLETE_BY_ID
    next_race = replace(next_race, first_turn_player_id='a', selections={'a': (ATHLETE_BY_ID['twin'], ATHLETE_BY_ID['legs']),
                                             'b': (ATHLETE_BY_ID['egg'], ATHLETE_BY_ID['genius'])})
    next_race = engine._create_race(next_race)
    assert [o['athlete']['id'] for o in next_race.pending_decision['options']] == ['coach']


@pytest.mark.parametrize('option', ['0', '1', '2', 'skip'])
def test_hypnotist_resolves_each_target_or_declines(option):
    engine, state = selection_game()
    choice = state.pending_decision
    for racer in state.magsim_engine.state.racers:
        racer.position = racer.idx * 3
    broker = state.magsim_engine.agents[0].broker
    expected_idx = None if option == 'skip' else broker.pending.options[int(option)].idx
    result = engine.resolve_decision(state, 'a', choice['id'], option)
    warps = [e for e in result.events if e['type'] == 'RACER_WARPED' and e['source'] == 'HypnotistWarp']
    if expected_idx is None:
        assert not warps
    else:
        assert len(warps) == 1
        assert warps[0]['athleteId'] == state.racer_athlete_by_index[expected_idx].id


def test_stale_timeout_cannot_resolve_a_new_question():
    from magical_athlete.game import GameRuleError
    engine, state = selection_game('genius')
    choice = state.pending_decision
    with pytest.raises(GameRuleError) as error:
        engine.resolve_decision(state, 'a', 'previous-question', '', timed_out=True)
    assert error.value.code == 'STALE_DECISION'
    assert state.pending_decision == choice


def test_target_options_include_owner_and_current_position():
    engine, state = selection_game()
    assert [(o.get('ownerName'), o.get('position')) for o in state.pending_decision['options']] == [
        ('A', 0), ('B', 0), ('B', 0), (None, None),
    ]


def test_rocket_choice_includes_roll_preview_before_committing_movement():
    engine, state = selection_game('rocket_scientist')
    result = engine.roll_dice(state, 'a')
    choice = result.state.pending_decision
    assert choice['abilityName'] == 'RocketScientistBoost'
    preview = choice['rollPreview']
    assert 1 <= preview['value'] <= 6
    assert preview['rollResultId']
    assert not any(e['type'] == 'RACER_MOVED' for e in result.events)


@pytest.fixture
def anyio_backend():
    return 'asyncio'


class ChoiceSocket:
    def __init__(self):
        self.messages = []

    async def send_json(self, message):
        self.messages.append(message)

    async def close(self, **kwargs):
        pass


@pytest.mark.anyio
@pytest.mark.parametrize('timeout_first', [False, True])
async def test_user_submit_and_timeout_resolve_once_and_duplicate_click_is_safe(timeout_first):
    from datetime import timedelta
    from magical_athlete.protocol import ResolveDecisionIntent
    from magical_athlete.rooms import InMemoryRoomRepository, RoomManager, RoomPlayer
    engine, state = selection_game('genius')
    repository = InMemoryRoomRepository()
    room = await repository.create(4, engine)
    room.game_state = state
    room.players = {p.id: RoomPlayer(p, 'token', socket=ChoiceSocket()) for p in state.players}
    manager = RoomManager(repository, local_timers=False)
    manager._sync_decision_timer_locked(room)
    expired = room.decision_deadline + timedelta(seconds=1)
    choice = state.pending_decision
    intent = ResolveDecisionIntent(type='RESOLVE_DECISION', actionId='click',
                                    decisionId=choice['id'], optionId='4')
    if timeout_first:
        assert await manager.resolve_expired_decision(room, expired)
    await manager.handle_intent(room, 'a', intent)
    if not timeout_first:
        assert not await manager.resolve_expired_decision(room, expired)
    assert room.revision == 1
    await manager.handle_intent(room, 'a', intent)
    assert room.revision == 1
    assert room.players['a'].socket.messages[-1]['type'] == 'ACTION_ACK'
    resolved = [e for message in room.players['a'].socket.messages for e in message.get('events', [])
                if e['type'] in ('DECISION_RESOLVED', 'DECISION_TIMED_OUT')]
    assert len(resolved) == 1
    assert resolved[0]['decisionId'] == choice['id']


@pytest.mark.anyio
async def test_reconnect_preserves_question_options_and_deadline():
    from magical_athlete.protocol import JoinRoomIntent
    from magical_athlete.rooms import InMemoryRoomRepository, RoomManager, RoomPlayer
    engine, state = selection_game('egg')
    repository = InMemoryRoomRepository()
    room = await repository.create(4, engine)
    room.game_state = state
    room.players = {p.id: RoomPlayer(p, 'token', socket=ChoiceSocket()) for p in state.players}
    manager = RoomManager(repository, local_timers=False)
    manager._sync_decision_timer_locked(room)
    expected = room.public_state('a')['game']['pendingDecision']
    new_socket = ChoiceSocket()
    await manager.join(new_socket, JoinRoomIntent(type='JOIN_ROOM', roomId=room.id,
                       playerId='a', reconnectToken='token', playerName='A'))
    assert new_socket.messages[0]['game']['pendingDecision'] == expected
    choice = state.pending_decision
    result = engine.resolve_decision(state, 'a', choice['id'], '0')
    assert result.state.pending_decision is None or result.state.pending_decision['id'] != choice['id']


@pytest.mark.parametrize('player_count,double,expected', [(2, False, 2), (3, False, 1), (3, True, 2), (6, False, 1), (6, True, 1)])
def test_lineup_single_and_multiple_selection_counts(player_count, double, expected):
    from dataclasses import replace
    from magical_athlete.athletes import ATHLETE_BY_ID
    from magical_athlete.game import GamePhase, GameRuleError, MagsimGameEngine, Player
    engine = MagsimGameEngine()
    players = tuple(Player(str(i), str(i)) for i in range(player_count))
    state = replace(engine.create_game(players), phase=GamePhase.CHARACTER_SELECTION,
                    double_racer_variant=double,
                    teams={'0': (ATHLETE_BY_ID['coach'], ATHLETE_BY_ID['banana'])})
    assert engine.public_state(state)['selectionCount'] == expected
    for selection in [(), ('coach', 'coach'), ('missing',) * expected,
                      ('coach',) if expected == 2 else ('coach', 'banana')]:
        with pytest.raises(GameRuleError):
            engine.select_racers(state, '0', selection)
        assert not state.selections
    selected = ('coach', 'banana')[:expected]
    state = engine.select_racers(state, '0', selected).state
    assert tuple(a.id for a in state.selections['0']) == selected
    with pytest.raises(GameRuleError) as error:
        engine.select_racers(state, '0', selected)
    assert error.value.code == 'ATHLETE_ALREADY_LOCKED'


def interactive_scenario(names, positions):
    from magsim.engine.scenario import GameScenario, RacerConfig
    broker = DecisionBroker()
    agent = InteractiveAgent(broker)
    scenario = GameScenario([RacerConfig(i, name, start_pos=pos, agent=agent)
                             for i, (name, pos) in enumerate(zip(names, positions))],
                            seed=3, defer_setup=True)
    assert scenario.engine.continue_setup()
    scenario.engine.start_turn()
    scenario.engine.continue_turn()
    return scenario.engine, broker


@pytest.mark.parametrize('option,destination', [('0', 4), ('1', 8), ('skip', 0)])
def test_third_wheel_picks_one_of_multiple_pairs(option, destination):
    engine, broker = interactive_scenario(
        ['ThirdWheel', 'Coach', 'Blimp', 'Legs', 'Inchworm'], [0, 4, 4, 8, 8])
    assert broker.pending.ability_name == 'ThirdWheelJoin'
    assert broker.pending.public_options() == [
        {'id': '0', 'label': '4'}, {'id': '1', 'label': '8'}, {'id': 'skip', 'label': 'skip'}]
    broker.choose(broker.pending.id, option)
    engine.continue_turn()
    assert engine.get_racer(0).position == destination
    assert [r.position for r in engine.state.racers[1:]] == [4, 4, 8, 8]


@pytest.mark.parametrize('option,target', [('0', 1), ('1', 2), ('skip', None)])
def test_flip_flop_swaps_only_selected_target_and_consumes_main_move(option, target):
    from magsim.engine.game_engine import TurnProgress
    engine, broker = interactive_scenario(['FlipFlop', 'Blimp', 'Legs'], [1, 5, 9])
    assert broker.pending.ability_name == 'FlipFlopSwap'
    broker.choose(broker.pending.id, option)
    progress = engine.continue_turn()
    expected = [1, 5, 9]
    if target is not None:
        expected[0], expected[target] = expected[target], expected[0]
        assert progress is TurnProgress.TURN_COMPLETE
        assert engine.get_racer(0).main_move_consumed
    else:
        assert progress is TurnProgress.WAITING_FOR_ROLL
        assert not engine.get_racer(0).main_move_consumed
    assert [r.position for r in engine.state.racers] == expected


@pytest.mark.parametrize('option,positions', [('0', [3, 0, 0, 6]), ('1', [4, 2, 2, 6])])
def test_cheerleader_applies_to_all_tied_last_racers_not_a_single_target(option, positions):
    engine, broker = interactive_scenario(['Cheerleader', 'Blimp', 'Legs', 'Coach'], [3, 0, 0, 6])
    assert broker.pending.ability_name == 'CheerleaderSupport'
    assert broker.pending.choice_type == 'BOOLEAN'
    broker.choose(broker.pending.id, option)
    engine.continue_turn()
    assert [r.position for r in engine.state.racers] == positions


def test_resolved_decision_reports_the_label_the_player_saw():
    engine, state = selection_game('genius')
    choice = state.pending_decision
    expected = next(option['label'] for option in choice['options'] if option['id'] == '4')

    transition = engine.resolve_decision(state, 'a', choice['id'], '4')
    resolved = [event for event in transition.events if event['type'] == 'DECISION_RESOLVED']

    assert len(resolved) == 1
    assert resolved[0]['optionLabel'] == expected == '5'
    assert resolved[0]['athleteName'] == 'Genius'
    assert resolved[0]['athleteId'] == 'genius'
    assert any(event.get('optionLabel') == '5' for event in transition.state.race_log)
