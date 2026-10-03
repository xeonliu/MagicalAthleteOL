from magsim.core.events import MoveCmdEvent, Phase
from magsim.engine.movement import handle_move_cmd
from magsim.engine.scenario import GameScenario, RacerConfig
from magsim.ai.baseline_agent import BaselineAgent


def test_follow_move_preserves_the_actual_leading_racer():
    scenario = GameScenario([
        RacerConfig(0, "Suckerfish", start_pos=0, agent=BaselineAgent()),
        RacerConfig(1, "Coach", start_pos=0),
    ])
    recorded = []
    scenario.engine.on_event_processed = lambda _, event: recorded.append(event)
    handle_move_cmd(scenario.engine, MoveCmdEvent(
        responsible_racer_idx=1, source="System", phase=Phase.MOVE_EXEC,
        emit_ability_triggered="never", target_racer_idx=1, distance=3,
    ))
    follow = next(s.event for s in scenario.engine.state.queue if s.event.source == "SuckerfishRide")
    assert follow.trigger_racer_idx == 1
    handle_move_cmd(scenario.engine, follow)
    movement = next(e for e in recorded if e.__class__.__name__ == "PostMoveEvent" and e.source == "SuckerfishRide")
    assert movement.target_racer_idx == 0
    assert movement.trigger_racer_idx == 1
    assert (movement.start_tile, movement.end_tile) == (0, 3)


def test_leader_lands_before_follow_choice_without_replaying_its_move():
    import random
    from dataclasses import replace
    from magical_athlete.athletes import ATHLETE_BY_ID
    from magical_athlete.game import MagsimGameEngine, GamePhase, Player

    engine = MagsimGameEngine(random.Random(5))
    state = replace(engine.create_game((Player("a", "小明"), Player("b", "小红"))),
                    phase=GamePhase.CHARACTER_SELECTION, first_turn_player_id="b",
                    teams={"a": tuple(ATHLETE_BY_ID[x] for x in ("suckerfish", "leaptoad")),
                           "b": tuple(ATHLETE_BY_ID[x] for x in ("coach", "duelist"))})
    state = engine.select_racers(state, "a", ("suckerfish", "leaptoad")).state
    state = engine.select_racers(state, "b", ("coach", "duelist")).state
    state = engine.resolve_decision(state, "b", state.pending_decision["id"], "skip").state
    roll = engine.roll_dice(state, "b")
    assert roll.state.pending_decision["abilityName"] == "SuckerfishRide"
    assert roll.state.pending_decision["effectPreview"]["athleteName"] == "Coach"
    assert roll.state.pending_decision["effectPreview"]["from"] == 0
    assert roll.state.pending_decision["effectPreview"]["to"] == 6
    leader_moves = [e for e in roll.events if e["type"] == "RACER_MOVED"]
    assert [(e['athleteId'], e['to']) for e in leader_moves] == [('coach', 6)]
    public = engine.public_state(roll.state)
    assert public['players'][1]['activeRacers'][0]['position'] == 6
    resumed = engine.resolve_decision(roll.state, "a", roll.state.pending_decision["id"], "1")
    moves = [e for e in resumed.events if e["type"] == "RACER_MOVED"]
    assert not any(e["athleteId"] == "coach" for e in moves)
    follow = next(e for e in moves if e["athleteId"] == "suckerfish")
    assert follow["triggerAthleteId"] == "coach"
    assert follow["triggerPlayerId"] == "b"
    assert (follow["from"], follow["to"]) == (0, 6)
