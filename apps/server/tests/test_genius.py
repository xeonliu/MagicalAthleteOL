"""Genius predicts the resolved die, not movement distance or a skipped roll."""
import pytest

from magsim.engine.scenario import GameScenario, RacerConfig
from magsim.racers.genius import AbilityGenius
from magsim.racers.legs import LegsMoveAbility
from magsim.racers.magician import AbilityMagicalReroll


@pytest.mark.parametrize("modifier,die,prediction,extra_turn,distance", [
    ("Coach", 5, 6, False, 6),
    ("Coach", 5, 5, True, 6),
    ("Gunk", 6, 5, False, 5),
    ("Gunk", 6, 6, True, 5),
])
def test_prediction_uses_die_face_with_movement_modifiers(monkeypatch, modifier, die, prediction, extra_turn, distance):
    scenario = GameScenario([
        RacerConfig(0, "Genius"), RacerConfig(1, modifier),
    ], dice_rolls=[die], seed=0)
    monkeypatch.setattr(scenario.engine.agents[0], "make_selection_decision", lambda *args, **kwargs: prediction)
    scenario.engine.run_turn()
    assert scenario.get_racer(0).position == distance
    assert (scenario.engine.state.next_turn_override == 0) is extra_turn


@pytest.mark.parametrize("dice,extra_turn", [([6, 2], False), ([2, 6], True)])
def test_prediction_uses_only_the_kept_reroll(monkeypatch, dice, extra_turn):
    scenario = GameScenario([
        RacerConfig(0, "Genius"),
        RacerConfig(1, "Banana", start_pos=10),
    ], dice_rolls=dice, seed=0)
    scenario.engine.replace_core_abilities(0, [AbilityGenius(), AbilityMagicalReroll()])
    monkeypatch.setattr(scenario.engine.agents[0], "make_boolean_decision",
                        lambda engine, ctx: ctx.source.reroll_count == 0)
    scenario.engine.run_turn()
    assert scenario.engine.state.roll_state.dice_value == dice[-1]
    assert (scenario.engine.state.next_turn_override == 0) is extra_turn


def test_jog_distance_is_not_a_die_result(monkeypatch):
    scenario = GameScenario([
        RacerConfig(0, "Genius"),
        RacerConfig(1, "Banana", start_pos=10),
    ], seed=0)
    scenario.engine.replace_core_abilities(0, [AbilityGenius(), LegsMoveAbility()])
    monkeypatch.setattr(scenario.engine.agents[0], "make_selection_decision", lambda *args, **kwargs: 5)
    scenario.engine.run_turn()
    assert scenario.get_racer(0).position == 5
    assert scenario.engine.state.roll_state.dice_value is None
    assert scenario.engine.state.next_turn_override is None


def test_skipper_still_takes_the_next_turn_after_a_correct_one():
    scenario = GameScenario([
        RacerConfig(0, "Genius"), RacerConfig(1, "Banana", start_pos=10),
        RacerConfig(2, "Skipper", start_pos=12),
    ], dice_rolls=[1], seed=0)
    scenario.engine.agents[0].make_selection_decision = lambda *args, **kwargs: 1
    scenario.engine.run_turn()
    assert scenario.engine.state.next_turn_override == 0
    assert scenario.engine.state.extra_turn_queue == [2]
    scenario.engine.advance_turn()
    assert scenario.engine.state.current_racer_idx == 2
    scenario.set_dice_rolls([2])
    scenario.run_turn()
    assert scenario.engine.state.current_racer_idx == 0
    scenario.run_turn()
    assert scenario.engine.state.current_racer_idx == 1
