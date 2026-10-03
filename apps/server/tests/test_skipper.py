import random
from dataclasses import replace

import pytest

from magical_athlete.athletes import ATHLETE_BY_ID
from magical_athlete.game import GamePhase, MagsimGameEngine, Player
from magsim.core.events import MainMoveSkippedEvent
from magsim.engine.scenario import GameScenario, RacerConfig


def test_skipper_extra_turn_resumes_the_interrupted_order():
    scenario = GameScenario([
        RacerConfig(0, "Banana"), RacerConfig(1, "Blimp"),
        RacerConfig(2, "Skipper"), RacerConfig(3, "Coach"),
    ], dice_rolls=[1, 2, 3, 4], seed=0)
    events = []
    scenario.engine.on_event_processed = lambda _, event: events.append(event)
    scenario.run_turn()
    assert scenario.engine.state.current_racer_idx == 2
    scenario.run_turn()
    assert scenario.engine.state.current_racer_idx == 1
    scenario.run_turn()
    assert scenario.engine.state.current_racer_idx == 2  # Its normal turn is still due.
    scenario.run_turn()
    assert scenario.engine.state.current_racer_idx == 3
    assert not any(isinstance(event, MainMoveSkippedEvent) and event.source == "SkipperTurn" for event in events)


def test_copycat_and_skipper_both_keep_their_extra_turns():
    scenario = GameScenario([
        RacerConfig(0, "Copycat"), RacerConfig(1, "Banana"),
        RacerConfig(2, "Skipper", start_pos=10), RacerConfig(3, "Coach"),
    ], dice_rolls=[1, 2, 3, 4], seed=0)
    scenario.engine.state.current_racer_idx = 1
    scenario.run_turn()
    assert "SkipperTurn" in scenario.get_racer(0).abilities
    assert scenario.engine.state.current_racer_idx == 2
    scenario.run_turn()
    assert scenario.engine.state.current_racer_idx == 0
    scenario.run_turn()
    assert scenario.engine.state.current_racer_idx == 2
    scenario.run_turn()
    assert scenario.engine.state.current_racer_idx == 3


def test_nested_ones_preserve_every_awarded_extra_turn():
    scenario = GameScenario([
        RacerConfig(0, "Copycat"), RacerConfig(1, "Banana"),
        RacerConfig(2, "Skipper", start_pos=10), RacerConfig(3, "Coach"),
    ], dice_rolls=[1, 1, 2, 2, 2], seed=0)
    scenario.engine.state.current_racer_idx = 1
    order = []
    for _ in range(5):
        scenario.run_turn()
        order.append(scenario.engine.state.current_racer_idx)
    assert order == [2, 0, 2, 0, 2]
    assert scenario.engine.state.interrupted_turn_idx is None


def test_skipper_rolling_one_on_its_own_turn_gets_an_extra_turn():
    scenario = GameScenario([
        RacerConfig(0, "Banana"), RacerConfig(1, "Blimp"),
        RacerConfig(2, "Skipper"), RacerConfig(3, "Coach"),
    ], dice_rolls=[1, 2], seed=0)
    scenario.engine.state.current_racer_idx = 2
    scenario.run_turn()
    assert scenario.engine.state.current_racer_idx == 2
    scenario.run_turn()
    assert scenario.engine.state.current_racer_idx == 3


def test_copycat_keeps_an_awarded_turn_after_losing_the_copied_power():
    scenario = GameScenario([
        RacerConfig(0, "Copycat", start_pos=9), RacerConfig(1, "Blimp"),
        RacerConfig(2, "Skipper", start_pos=10), RacerConfig(3, "Coach", start_pos=9),
    ], dice_rolls=[1, 2, 3], seed=0)
    scenario.run_turn()
    assert "SkipperTurn" not in scenario.get_racer(0).abilities  # The move made it the sole leader.
    assert scenario.engine.state.current_racer_idx == 0
    scenario.run_turn()
    assert scenario.engine.state.current_racer_idx == 2
    scenario.run_turn()
    assert scenario.engine.state.current_racer_idx == 1


def test_finished_bonus_recipient_is_skipped_without_losing_resume_position():
    scenario = GameScenario([
        RacerConfig(0, "Banana"), RacerConfig(1, "Blimp"),
        RacerConfig(2, "Skipper"), RacerConfig(3, "Coach"),
    ], dice_rolls=[1], seed=0)
    scenario.engine.run_turn()
    scenario.get_racer(2).finish_position = 1
    scenario.engine.advance_turn()
    assert scenario.engine.state.current_racer_idx == 1
    assert scenario.engine.state.extra_turn_queue == []
    assert scenario.engine.state.interrupted_turn_idx is None


def test_wrapped_interrupt_resumes_at_first_racer():
    scenario = GameScenario([
        RacerConfig(0, "Banana"), RacerConfig(1, "Skipper"),
        RacerConfig(2, "Blimp"), RacerConfig(3, "Coach"),
    ], dice_rolls=[1, 2], seed=0)
    scenario.engine.state.current_racer_idx = 3
    round_before = scenario.engine.log_context.total_turn
    scenario.run_turn()
    assert scenario.engine.state.current_racer_idx == 1
    assert scenario.engine.log_context.total_turn == round_before
    scenario.run_turn()
    assert scenario.engine.state.current_racer_idx == 0
    assert scenario.engine.log_context.total_turn == round_before + 1


@pytest.mark.parametrize("player_count", [2, 4])
def test_online_rolls_keep_copycat_bonus_and_normal_turns(player_count):
    engine = MagsimGameEngine(random.Random(3))
    players = tuple(Player(f"p{i}", f"P{i}") for i in range(player_count))
    cards = ["blimp", "copycat", "skipper", "coach"]
    count = 4 // player_count
    teams = {p.id: tuple(ATHLETE_BY_ID[card] for card in cards[i * count:(i + 1) * count])
             for i, p in enumerate(players)}
    state = replace(engine.create_game(players), phase=GamePhase.CHARACTER_SELECTION,
                    teams=teams, first_turn_player_id="p0")
    for player in players:
        state = engine.select_racers(state, player.id, tuple(card.id for card in teams[player.id])).state
    while state.pending_decision:
        decision = state.pending_decision
        choice = next((option for option in decision["options"] if "Skipper" in option["label"]), None)
        assert choice is not None, str(decision["options"])
        state = engine.resolve_decision(state, decision["playerId"], decision["id"], choice["id"]).state
    state.magsim_engine.get_racer(2).position = 10
    dice = iter([1, 2, 3, 4])
    state.magsim_engine.rng.randint = lambda *_: next(dice)
    roll_ids, order = [], []
    for _ in range(4):
        transition = engine.roll_dice(state, state.active_player_id)
        state = transition.state
        public = engine.public_state(state, state.active_player_id)
        order.append(public["activeAthleteId"])
        assert public["resolutionStatus"] == "WAITING_FOR_ROLL"
        assert state.pending_decision is None
        roll_ids.extend(event["rollResultId"] for event in transition.events if event["type"] == "DICE_ROLLED")
        assert not any(event["type"] == "MAIN_MOVE_SKIPPED" and event.get("source") == "SkipperTurn" for event in transition.events)
    assert len(set(roll_ids)) == 4
    assert set(order[:2]) == {"skipper", "copycat"}
    assert order[2:] == ["copycat", "skipper"]

