import pytest

from magsim.core.events import MoveCmdEvent, Phase
from magsim.core.interactive import RollRequired
from magsim.engine.movement import handle_move_cmd
from magsim.engine.scenario import GameScenario, RacerConfig


def _move(racer_idx: int, distance: int) -> MoveCmdEvent:
    return MoveCmdEvent(
        target_racer_idx=racer_idx,
        distance=distance,
        source="System",
        phase=Phase.MOVE_EXEC,
        responsible_racer_idx=None,
    )


def test_duelist_does_not_retrigger_from_unrelated_move_while_already_sharing() -> None:
    scenario = GameScenario(
        [
            RacerConfig(0, "Duelist", start_pos=2),
            RacerConfig(1, "Legs", start_pos=2),
            RacerConfig(2, "Banana", start_pos=0),
        ],
        dice_rolls=[6, 1],
        defer_setup=True,
    )

    handle_move_cmd(scenario.engine, _move(racer_idx=2, distance=1))

    assert all(
        getattr(scheduled.event, "source", None) != "DuelistDuel"
        for scheduled in scenario.engine.state.queue
    )


def test_duelist_triggers_when_racer_moves_onto_duelist_space() -> None:
    scenario = GameScenario(
        [
            RacerConfig(0, "Duelist", start_pos=2),
            RacerConfig(1, "Legs", start_pos=0),
        ],
        dice_rolls=[6, 1],
        defer_setup=True,
    )

    with pytest.raises(RollRequired):
        handle_move_cmd(scenario.engine, _move(racer_idx=1, distance=2))

    pending = scenario.engine.roll_broker.pending
    assert pending is not None
    assert pending.ability_name == "DuelistDuel"
    assert pending.participants == (0, 1)


def test_landing_is_visible_before_duel_choice_and_is_not_replayed():
    import random
    from dataclasses import replace
    from magical_athlete.athletes import ATHLETE_BY_ID
    from magical_athlete.game import MagsimGameEngine, GamePhase, Player

    engine = MagsimGameEngine(random.Random(3))
    players = tuple(Player(str(i), str(i)) for i in range(3))
    ids = ('coach', 'duelist', 'blimp')
    state = replace(engine.create_game(players), phase=GamePhase.CHARACTER_SELECTION,
                    first_turn_player_id='0', teams={p.id: (ATHLETE_BY_ID[a],) for p, a in zip(players, ids)})
    for player, athlete in zip(players, ids):
        state = engine.select_racers(state, player.id, (athlete,)).state
    state = engine.resolve_decision(state, '1', state.pending_decision['id'], 'skip').state
    for racer, position in zip(state.magsim_engine.state.racers, (0, 3, 12)):
        racer.position = position
    state.magsim_engine.rng.randint = lambda *_: 2  # Coach moves 3.
    landing = engine.roll_dice(state, '0')
    assert landing.state.pending_decision['abilityName'] == 'DuelistDuel'
    types = [e['type'] for e in landing.events]
    assert types.index('RACER_MOVED') < types.index('DECISION_REQUIRED')
    assert engine.public_state(landing.state)['players'][0]['activeRacers'][0]['position'] == 3
    choice = landing.state.pending_decision
    duel = engine.resolve_decision(landing.state, '1', choice['id'], '0')
    assert not any(e['type'] == 'RACER_MOVED' for e in duel.events)
    assert duel.state.pending_roll['abilityName'] == 'DuelistDuel'
    first_roll = engine.roll_dice(duel.state, '1')
    second_roll = engine.roll_dice(first_roll.state, '0')
    landings = [e for e in second_roll.state.race_log if e['type'] == 'RACER_MOVED'
                and e['athleteId'] == 'coach' and e['from'] == 0 and e['to'] == 3]
    assert len(landings) == 1
