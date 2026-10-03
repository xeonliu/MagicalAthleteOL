from collections import Counter

import pytest

from magsim.core.events import AbilityTriggeredEvent, MoveCmdEvent, Phase
from magsim.core.state import GameRules
from magsim.engine.game_engine import TurnProgress
from magsim.engine.scenario import GameScenario, RacerConfig


def watch_scooches(engine):
    moves = Counter()
    processed = 0

    def record(_engine, event):
        nonlocal processed
        processed += 1
        assert processed < 80, "Scoocher reactions must settle instead of chaining indefinitely"
        if isinstance(event, MoveCmdEvent) and event.source == "ScoochStep":
            moves[event.target_racer_idx] += 1

    engine.on_event_processed = record
    return moves


@pytest.mark.parametrize("mode", ["FLAT", "BFS", "DFS"])
def test_copycat_copying_scoocher_reacts_once_each_then_waits_for_dice(mode):
    scenario = GameScenario([
        RacerConfig(0, "Copycat", start_pos=0),
        RacerConfig(1, "Scoocher", start_pos=8),
    ], rules=GameRules(timing_mode=mode), dice_rolls=[1])
    engine = scenario.engine
    moves = watch_scooches(engine)
    engine.start_turn()

    assert engine.continue_turn() is TurnProgress.WAITING_FOR_ROLL
    assert [r.position for r in engine.state.racers] == [1, 9]
    assert moves == {0: 1, 1: 1}
    assert not engine.state.queue
    assert engine.bug_reason is None


def test_legacy_queued_ability_event_still_gets_a_bounded_reaction_chain():
    scenario = GameScenario([
        RacerConfig(0, "Scoocher", start_pos=0),
        RacerConfig(1, "Banana", start_pos=12),
        RacerConfig(2, "Scoocher", start_pos=0),
    ], dice_rolls=[1])
    engine = scenario.engine
    engine.start_turn()
    assert engine.continue_turn() is TurnProgress.WAITING_FOR_ROLL
    moves = watch_scooches(engine)
    event = AbilityTriggeredEvent(responsible_racer_idx=1, source="BananaTrip", phase=Phase.REACTION, target_racer_idx=1)
    object.__delattr__(event, "scooch_reactors")
    engine.push_event(event)
    assert engine.continue_turn() is TurnProgress.WAITING_FOR_ROLL
    assert moves == {0: 1, 2: 1}
    assert [r.position for r in engine.state.racers] == [1, 12, 1]


def test_online_copycat_scoocher_pair_settles_and_can_roll_dice():
    import random
    from dataclasses import replace

    from magical_athlete.athletes import ATHLETE_BY_ID
    from magical_athlete.game import GamePhase, MagsimGameEngine, Player

    adapter = MagsimGameEngine(random.Random(3))
    state = replace(adapter.create_game((Player("a", "A"), Player("b", "B"), Player("c", "C"))),
                    phase=GamePhase.CHARACTER_SELECTION, first_turn_player_id="a",
                    teams={"a": (ATHLETE_BY_ID["copycat"],), "b": (ATHLETE_BY_ID["scoocher"],), "c": (ATHLETE_BY_ID["blimp"],)})
    state = adapter.select_racers(state, "a", ("copycat",)).state
    state = adapter.select_racers(state, "b", ("scoocher",)).state
    state = adapter.select_racers(state, "c", ("blimp",)).state
    decision = state.pending_decision
    assert decision and decision["abilityName"] == "CopyLead"
    target = next(option["id"] for option in decision["options"] if "Scoocher" in option["label"])
    transition = adapter.resolve_decision(state, "a", decision["id"], target)
    state = transition.state
    public = adapter.public_state(state, "a")
    assert [p["position"] for p in public["players"]] == [1, 1, 0]
    assert public["resolutionStatus"] == "WAITING_FOR_ROLL"
    assert public["activePlayerId"] == "a"
    assert sum(event["type"] == "ABILITY_TRIGGERED" and event.get("abilityName") == "ScoochStep" for event in transition.events) == 2
    rolled = adapter.roll_dice(state, "a")
    assert any(event["type"] == "DICE_ROLLED" for event in rolled.events)
    assert rolled.state.phase is GamePhase.RACING
    assert rolled.state.magsim_engine.bug_reason is None


@pytest.mark.parametrize("mode", ["FLAT", "BFS", "DFS"])
def test_multiple_copied_scoochers_react_once_per_new_ability_event(mode):
    scenario = GameScenario([
        RacerConfig(0, "Scoocher", start_pos=0),
        RacerConfig(1, "Copycat", start_pos=0),
        RacerConfig(2, "Egg", start_pos=0),
        RacerConfig(3, "Coach", start_pos=12),
    ], rules=GameRules(timing_mode=mode), dice_rolls=[1], defer_setup=True)
    engine = scenario.engine
    engine.replace_core_abilities(1, engine.instantiate_racer_abilities("Scoocher"))
    engine.replace_core_abilities(2, engine.instantiate_racer_abilities("Scoocher"))
    assert engine.continue_setup()
    engine.start_turn()
    assert engine.continue_turn() is TurnProgress.WAITING_FOR_ROLL
    moves = watch_scooches(engine)

    for expected_position in [1, 2]:
        engine.push_event(AbilityTriggeredEvent(responsible_racer_idx=3, source="CoachBoost", phase=Phase.REACTION, target_racer_idx=3))
        assert engine.continue_turn() is TurnProgress.WAITING_FOR_ROLL
        assert [r.position for r in engine.state.racers[:3]] == [expected_position] * 3
    assert moves == {0: 2, 1: 2, 2: 2}
    assert engine.bug_reason is None
