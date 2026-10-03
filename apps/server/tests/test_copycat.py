from magsim.core.interactive import DecisionBroker, InteractiveAgent
from magsim.engine.game_engine import TurnProgress
from magsim.engine.scenario import GameScenario, RacerConfig


def test_copycat_auto_copies_sole_leader_without_interactive_choice() -> None:
    broker = DecisionBroker()
    agent = InteractiveAgent(broker)
    scenario = GameScenario(
        [
            RacerConfig(0, "Copycat", start_pos=0, agent=agent),
            RacerConfig(1, "Banana", start_pos=5),
            RacerConfig(2, "Coach", start_pos=3),
        ],
        dice_rolls=[1],
    )

    scenario.engine.start_turn()

    assert scenario.engine.continue_turn() is TurnProgress.WAITING_FOR_ROLL
    assert broker.pending is None
    assert "BananaTrip" in scenario.engine.get_racer(0).abilities
    assert scenario.engine.state.roll_state.serial_id == 0


def test_copycat_still_prompts_for_tied_leaders() -> None:
    broker = DecisionBroker()
    agent = InteractiveAgent(broker)
    scenario = GameScenario(
        [
            RacerConfig(0, "Copycat", start_pos=0, agent=agent),
            RacerConfig(1, "Banana", start_pos=5),
            RacerConfig(2, "Coach", start_pos=5),
        ],
        dice_rolls=[1],
    )

    scenario.engine.start_turn()

    assert scenario.engine.continue_turn() is TurnProgress.WAITING_FOR_DECISION
    assert broker.pending is not None
    assert broker.pending.ability_name == "CopyLead"
    assert scenario.engine.state.roll_state.serial_id == 0


def test_copycat_exposes_its_current_target_through_the_copy_contract() -> None:
    import random
    from dataclasses import replace

    from magical_athlete.athletes import ATHLETE_BY_ID
    from magical_athlete.game import GamePhase, MagsimGameEngine, Player

    engine = MagsimGameEngine(random.Random(3))
    state = replace(
        engine.create_game((Player("a", "A"), Player("b", "B"))),
        phase=GamePhase.CHARACTER_SELECTION,
        first_turn_player_id="a",
        teams={
            "a": (ATHLETE_BY_ID["copycat"], ATHLETE_BY_ID["blimp"]),
            "b": (ATHLETE_BY_ID["coach"], ATHLETE_BY_ID["banana"]),
        },
    )
    state = engine.select_racers(state, "a", ("copycat", "blimp")).state
    state = engine.select_racers(state, "b", ("coach", "banana")).state
    state.magsim_engine.get_racer(1).position = 5

    state.magsim_engine.start_turn()
    assert state.magsim_engine.continue_turn() is TurnProgress.WAITING_FOR_ROLL

    public = engine.public_state(state, "a")["players"][0]["activeRacers"][0]
    assert public["id"] == "copycat"
    assert public["copiedAthlete"] == {"id": "blimp", "name": "Blimp"}
