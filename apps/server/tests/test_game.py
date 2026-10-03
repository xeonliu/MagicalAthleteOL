import random
import subprocess
import sys
from dataclasses import replace
from unittest.mock import MagicMock

import pytest

from magical_athlete.athletes import ATHLETE_BY_ID, ATHLETE_CATALOG
from magical_athlete.game import GamePhase, GameRuleError, MagsimGameEngine, Player


def make_players(count: int) -> tuple[Player, ...]:
    return tuple(Player(f"p{index}", f"Player {index}") for index in range(count))


def complete_roll_off(engine: MagsimGameEngine, state):
    while state.phase in (GamePhase.DRAFT_ROLL, GamePhase.RACE_ROLL):
        for player_id in state.roll_candidates:
            if player_id not in state.roll_values:
                state = engine.roll_start(state, player_id).state
    return state


def complete_draft(engine: MagsimGameEngine, state):
    while state.phase == GamePhase.DRAFTING:
        state = engine.draft_athlete(
            state, state.active_player_id, state.draft_pool[0].id
        ).state
    return state


def test_complete_catalog_matches_vendored_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    import pkgutil

    from magsim.core.registry import RACER_ABILITIES
    from magsim.racers import get_ability_classes

    assert len(ATHLETE_CATALOG) == 36
    assert {card.engine_name for card in ATHLETE_CATALOG} == set(RACER_ABILITIES)

    monkeypatch.setattr(
        pkgutil,
        "iter_modules",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("ability registration must not scan the runtime filesystem")
        ),
    )
    get_ability_classes.cache_clear()
    ability_classes = get_ability_classes()

    assert set().union(*RACER_ABILITIES.values()) <= set(ability_classes)


def test_core_engine_import_does_not_require_rich() -> None:
    code = """
import builtins

original_import = builtins.__import__

def import_without_rich(name, *args, **kwargs):
    if name == "rich" or name.startswith("rich."):
        raise ModuleNotFoundError("rich is unavailable in the Worker runtime")
    return original_import(name, *args, **kwargs)

builtins.__import__ = import_without_rich
from magsim.engine.game_engine import GameEngine
assert GameEngine is not None
"""
    subprocess.run([sys.executable, "-c", code], check=True)


@pytest.mark.parametrize(
    ("player_count", "expected_team_size", "expected_picks"),
    ((2, 8, 16), (3, 4, 12), (4, 4, 16), (5, 4, 20), (6, 4, 24)),
)
def test_formal_draft_sizes(player_count: int, expected_team_size: int, expected_picks: int) -> None:
    engine = MagsimGameEngine(random.Random(5))
    players = make_players(player_count)
    state = engine.start(engine.create_game(players), players[0].id).state
    state = complete_roll_off(engine, state)
    picks = 0
    seen: set[str] = set()
    while state.phase == GamePhase.DRAFTING:
        picked = state.draft_pool[0]
        assert picked.id not in seen
        seen.add(picked.id)
        state = engine.draft_athlete(state, state.active_player_id, picked.id).state
        picks += 1

    assert state.phase == GamePhase.RACE_ROLL
    assert picks == expected_picks
    assert all(len(state.teams[player.id]) == expected_team_size for player in players)


def test_two_player_first_draft_uses_abbaabba_order() -> None:
    engine = MagsimGameEngine(random.Random(2))
    players = make_players(2)
    state = complete_roll_off(engine, engine.start(engine.create_game(players), "p0").state)
    a, b = state.draft_order[0], state.draft_order[1]
    assert state.draft_order == (a, b, b, a, a, b, b, a)


def test_three_player_double_racer_variant_drafts_eight_each() -> None:
    engine = MagsimGameEngine(random.Random(11))
    players = make_players(3)
    state = engine.set_variant(engine.create_game(players), "p0", True).state
    state = complete_draft(engine, complete_roll_off(engine, engine.start(state, "p0").state))

    assert all(len(state.teams[player.id]) == 8 for player in players)
    assert engine.public_state(state)["doubleRacerVariant"] is True


@pytest.mark.parametrize(
    ("player_count", "expected_team_size"),
    ((2, 8), (3, 4), (4, 4), (5, 4), (6, 4)),
)
def test_auto_deal_hands_every_player_their_cards_without_drafting(
    player_count: int, expected_team_size: int
) -> None:
    engine = MagsimGameEngine(random.Random(3))
    players = make_players(player_count)
    state = engine.set_auto_deal(engine.create_game(players), players[0].id, True).state
    transition = engine.start(state, players[0].id)
    state = transition.state

    assert state.phase == GamePhase.RACE_ROLL
    assert state.draft_pool == () and state.draft_order == () and state.draft_pick_index == 0
    assert [event["type"] for event in transition.events] == [
        "TEAM_DEALT",
    ] * player_count + ["RACE_ROLL_STARTED"]

    dealt = [card.id for player in players for card in state.teams[player.id]]
    assert len(dealt) == expected_team_size * player_count
    assert len(set(dealt)) == len(dealt)
    assert all(len(state.teams[player.id]) == expected_team_size for player in players)
    assert engine.public_state(state, players[0].id)["autoDeal"] is True
    assert engine.public_state(state, players[0].id)["cardsPerPlayer"] == expected_team_size


def test_auto_deal_reaches_character_selection_after_the_opening_roll() -> None:
    engine = MagsimGameEngine(random.Random(4))
    players = make_players(3)
    state = engine.set_auto_deal(engine.create_game(players), "p0", True).state
    state = complete_roll_off(engine, engine.start(state, "p0").state)

    assert state.phase == GamePhase.CHARACTER_SELECTION
    assert state.first_turn_player_id in {player.id for player in players}


def test_three_player_double_racer_variant_auto_deals_eight_each() -> None:
    engine = MagsimGameEngine(random.Random(11))
    players = make_players(3)
    state = engine.set_variant(engine.create_game(players), "p0", True).state
    state = engine.set_auto_deal(state, "p0", True).state
    state = engine.start(state, "p0").state

    assert state.phase == GamePhase.RACE_ROLL
    assert all(len(state.teams[player.id]) == 8 for player in players)


def test_auto_deal_is_a_host_only_lobby_setting() -> None:
    engine = MagsimGameEngine(random.Random(1))
    players = make_players(3)

    with pytest.raises(GameRuleError) as error:
        engine.set_auto_deal(engine.create_game(players), "p1", True)
    assert error.value.code == "ONLY_HOST_CAN_CONFIGURE"

    started = engine.start(
        engine.set_auto_deal(engine.create_game(players), "p0", True).state, "p0"
    ).state
    with pytest.raises(GameRuleError) as error:
        engine.set_auto_deal(started, "p0", False)
    assert error.value.code == "GAME_ALREADY_STARTED"


def test_selection_is_secret_and_requires_two_unique_racers_for_two_players() -> None:
    engine = MagsimGameEngine(random.Random(7))
    players = make_players(2)
    teams = {
        "p0": (ATHLETE_BY_ID["banana"], ATHLETE_BY_ID["skipper"]),
        "p1": (ATHLETE_BY_ID["coach"], ATHLETE_BY_ID["alchemist"]),
    }
    state = replace(
        engine.create_game(players),
        phase=GamePhase.CHARACTER_SELECTION,
        teams=teams,
        first_turn_player_id="p0",
    )

    with pytest.raises(GameRuleError) as error:
        engine.select_racers(state, "p0", ("banana",))
    assert error.value.code == "INVALID_RACER_COUNT"

    state = engine.select_racers(state, "p0", ("banana", "skipper")).state
    assert engine.public_state(state, "p1")["players"][0]["activeRacers"] == []
    assert engine.public_state(state, "p1")["players"][0]["selectionLocked"] is True

    state = engine.select_racers(state, "p1", ("coach", "alchemist")).state
    assert state.phase == GamePhase.RACING
    assert len(state.magsim_engine.state.racers) == 4
    assert [state.racer_owner_by_index[index] for index in range(4)] == ["p0", "p0", "p1", "p1"]
    assert all(engine.public_state(state, "p1")["players"][index]["activeRacers"] for index in range(2))
    assert state.resolution_status == "WAITING_FOR_ROLL"
    assert state.magsim_engine.state.roll_state.serial_id == 0
    assert engine.public_state(state)["activeAthleteId"] == "banana"

    next_turn = engine.roll_dice(state, "p0").state
    public = engine.public_state(next_turn)
    assert public["activePlayerId"] == "p0"
    assert public["activeAthleteId"] == "skipper"
    assert public["players"][0]["activeRacers"][0]["id"] == "banana"


def test_roll_serial_increases_across_turns() -> None:
    engine = MagsimGameEngine(random.Random(13))
    players = make_players(4)
    teams = {
        "p0": (ATHLETE_BY_ID["banana"],),
        "p1": (ATHLETE_BY_ID["blimp"],),
        "p2": (ATHLETE_BY_ID["hare"],),
        "p3": (ATHLETE_BY_ID["lovable_loser"],),
    }
    state = replace(
        engine.create_game(players),
        phase=GamePhase.CHARACTER_SELECTION,
        teams=teams,
        first_turn_player_id="p0",
    )
    for player in players:
        state = engine.select_racers(state, player.id, (teams[player.id][0].id,)).state

    first = engine.roll_dice(state, state.active_player_id)
    first_roll = next(event for event in first.events if event["type"] == "DICE_ROLLED")
    second = engine.roll_dice(first.state, first.state.active_player_id)
    second_roll = next(event for event in second.events if event["type"] == "DICE_ROLLED")

    assert second_roll["rollSerial"] > first_roll["rollSerial"]


def test_race_uses_schedule_rewards_and_accumulates_score() -> None:
    engine = MagsimGameEngine(random.Random(3))
    players = make_players(4)
    teams = {
        "p0": (ATHLETE_BY_ID["banana"],),
        "p1": (ATHLETE_BY_ID["skipper"],),
        "p2": (ATHLETE_BY_ID["coach"],),
        "p3": (ATHLETE_BY_ID["alchemist"],),
    }
    state = replace(
        engine.create_game(players),
        phase=GamePhase.CHARACTER_SELECTION,
        teams=teams,
        first_turn_player_id="p0",
        race_number=2,
    )
    for player in players:
        state = engine.select_racers(state, player.id, (teams[player.id][0].id,)).state

    assert state.magsim_engine.state.rules.winner_vp == (4, 2)
    assert engine.public_state(state)["trackName"] == "WildWilds"
    # Force two ordinary racers across the line, preserving the authoritative turn flow.
    while state.phase == GamePhase.RACING:
        current_index = state.magsim_engine.state.current_racer_idx
        state.magsim_engine.get_racer(current_index).position = 29
        state = engine.roll_dice(state, state.active_player_id).state

    assert state.phase == GamePhase.RACE_RESULTS
    assert sum(state.scores.values()) >= 6
    assert len(state.used_athlete_ids) == 4


def test_only_host_can_start_or_advance() -> None:
    engine = MagsimGameEngine()
    state = engine.create_game(make_players(2))
    with pytest.raises(GameRuleError) as error:
        engine.start(state, "p1")
    assert error.value.code == "ONLY_HOST_CAN_START"


def test_egg_setup_pauses_and_only_owner_can_resolve() -> None:
    engine = MagsimGameEngine(random.Random(17))
    players = make_players(2)
    teams = {
        "p0": (ATHLETE_BY_ID["egg"], ATHLETE_BY_ID["blimp"]),
        "p1": (ATHLETE_BY_ID["banana"], ATHLETE_BY_ID["coach"]),
    }
    state = replace(
        engine.create_game(players),
        phase=GamePhase.CHARACTER_SELECTION,
        teams=teams,
        first_turn_player_id="p0",
    )
    state = engine.select_racers(state, "p0", ("egg", "blimp")).state
    transition = engine.select_racers(state, "p1", ("banana", "coach"))
    state = transition.state

    assert state.phase == GamePhase.RACING
    assert state.pending_decision is not None
    assert state.pending_decision["playerId"] == "p0"
    assert len(state.pending_decision["options"]) == 3
    assert any(event["type"] == "DECISION_REQUIRED" for event in transition.events)

    with pytest.raises(GameRuleError) as error:
        engine.resolve_decision(state, "p1", state.pending_decision["id"], "0")
    assert error.value.code == "NOT_DECIDING_PLAYER"

    with pytest.raises(GameRuleError) as error:
        engine.resolve_decision(state, "p0", state.pending_decision["id"], "99")
    assert error.value.code == "INVALID_DECISION_OPTION"

    transition = engine.resolve_decision(
        state, "p0", state.pending_decision["id"], "", timed_out=True
    )
    assert transition.state.pending_decision is None
    assert transition.state.magsim_engine._setup_complete is True
    assert transition.state.resolution_status == "WAITING_FOR_ROLL"
    assert transition.events[0]["type"] == "DECISION_TIMED_OUT"


def test_event_choice_rolls_back_and_reuses_same_die() -> None:
    engine = MagsimGameEngine(random.Random(21))
    players = make_players(2)
    teams = {
        "p0": (ATHLETE_BY_ID["alchemist"], ATHLETE_BY_ID["blimp"]),
        "p1": (ATHLETE_BY_ID["banana"], ATHLETE_BY_ID["coach"]),
    }
    state = replace(
        engine.create_game(players),
        phase=GamePhase.CHARACTER_SELECTION,
        teams=teams,
        first_turn_player_id="p0",
    )
    state = engine.select_racers(state, "p0", ("alchemist", "blimp")).state
    state = engine.select_racers(state, "p1", ("banana", "coach")).state
    state.magsim_engine.rng = random.Random(2)  # First d6 is 1.

    transition = engine.roll_dice(state, "p0")
    paused = transition.state
    assert paused.pending_decision is not None
    assert paused.positions["alchemist"] == 0
    assert not any(event["type"] == "DICE_ROLLED" for event in transition.events)

    transition = engine.resolve_decision(
        paused, "p0", paused.pending_decision["id"], "1"
    )
    assert transition.state.pending_decision is None
    roll = next(event for event in transition.events if event["type"] == "DICE_ROLLED")
    assert roll["value"] == 1
    assert roll["baseValue"] == 4
    assert roll["finalValue"] == 5  # Coach contributes +1 at the starting tile.
    assert transition.state.positions["alchemist"] == 5


def test_magician_reveals_each_roll_before_reroll_decision() -> None:
    engine = MagsimGameEngine(random.Random(21))
    players = make_players(2)
    teams = {
        "p0": (ATHLETE_BY_ID["magician"], ATHLETE_BY_ID["banana"]),
        "p1": (ATHLETE_BY_ID["skipper"], ATHLETE_BY_ID["blimp"]),
    }
    state = replace(
        engine.create_game(players),
        phase=GamePhase.CHARACTER_SELECTION,
        teams=teams,
        first_turn_player_id="p0",
    )
    state = engine.select_racers(state, "p0", ("magician", "banana")).state
    state = engine.select_racers(state, "p1", ("skipper", "blimp")).state
    state.magsim_engine.rng = random.Random(1)  # Rolls 2, then 5.

    transition = engine.roll_dice(state, "p0")
    first = transition.state.pending_decision
    assert first is not None
    assert first["abilityName"] == "MagicalReroll"
    assert {
        key: first["rollPreview"][key]
        for key in ("rollSerial", "value", "baseValue", "finalValue")
    } == {
        "rollSerial": 1,
        "value": 2,
        "baseValue": 2,
        "finalValue": 2,
    }
    assert first["rollPreview"]["rollResultId"].startswith(first["rollPreview"]["rollSessionId"])

    transition = engine.resolve_decision(
        transition.state, "p0", first["id"], "1"
    )
    assert transition.state.pending_roll is not None
    assert transition.state.pending_roll["nextPlayerId"] == "p0"

    transition = engine.roll_dice(transition.state, "p0")
    second = transition.state.pending_decision
    assert second is not None
    assert {
        key: second["rollPreview"][key]
        for key in ("rollSerial", "value", "baseValue", "finalValue")
    } == {
        "rollSerial": 3,
        "value": 5,
        "baseValue": 5,
        "finalValue": 5,
    }
    assert second["rollPreview"]["rollResultId"].startswith(second["rollPreview"]["rollSessionId"])

    transition = engine.resolve_decision(
        transition.state, "p0", second["id"], "0"
    )
    assert transition.state.pending_decision is None
    roll = next(event for event in transition.events if event["type"] == "DICE_ROLLED")
    assert roll["value"] == 5
    assert roll["rollSerial"] == second["rollPreview"]["rollSerial"]


def test_long_legs_jog_skips_the_roll_and_moves_five() -> None:
    engine = MagsimGameEngine(random.Random(31))
    players = make_players(2)
    teams = {
        "p0": (ATHLETE_BY_ID["legs"], ATHLETE_BY_ID["banana"]),
        "p1": (ATHLETE_BY_ID["skipper"], ATHLETE_BY_ID["blimp"]),
    }
    state = replace(
        engine.create_game(players),
        phase=GamePhase.CHARACTER_SELECTION,
        teams=teams,
        first_turn_player_id="p0",
    )
    state = engine.select_racers(state, "p0", ("legs", "banana")).state
    state = engine.select_racers(state, "p1", ("skipper", "blimp")).state

    decision = state.pending_decision
    assert decision is not None
    assert decision["abilityName"] == "LongLegs"
    assert decision["choiceType"] == "BOOLEAN"
    assert [option["label"] for option in decision["options"]] == ["skip", "use"]
    with pytest.raises(GameRuleError, match="先完成当前技能选择"):
        engine.roll_dice(state, "p0")

    # Accepting the jog skips the die entirely: the move happens with no throw.
    jogged = engine.resolve_decision(state, "p0", decision["id"], "1")
    assert jogged.state.pending_decision is None
    assert any(
        event["type"] == "ABILITY_TRIGGERED" and event["abilityName"] == "LongLegs"
        for event in jogged.events
    )
    assert not any(event["type"] == "DIE_ROLLED" for event in jogged.events)
    roll = next(event for event in jogged.events if event["type"] == "DICE_ROLLED")
    assert roll["values"] == []
    assert roll["noDice"] is True
    assert roll["baseValue"] == 5
    step = next(
        event
        for event in jogged.events
        if event["type"] == "RACER_MOVED" and event["athleteId"] == "legs"
    )
    assert (step["from"], step["to"]) == (0, 5)
    assert jogged.state.positions["legs"] == 5


def test_long_legs_can_decline_and_roll_one_die() -> None:
    engine = MagsimGameEngine(random.Random(33))
    players = make_players(2)
    teams = {
        "p0": (ATHLETE_BY_ID["legs"], ATHLETE_BY_ID["banana"]),
        "p1": (ATHLETE_BY_ID["skipper"], ATHLETE_BY_ID["blimp"]),
    }
    state = replace(
        engine.create_game(players),
        phase=GamePhase.CHARACTER_SELECTION,
        teams=teams,
        first_turn_player_id="p0",
    )
    state = engine.select_racers(state, "p0", ("legs", "banana")).state
    state = engine.select_racers(state, "p1", ("skipper", "blimp")).state
    rng = MagicMock(wraps=random.Random(0))
    rng.randint.side_effect = [4]
    state.magsim_engine.rng = rng

    decision = state.pending_decision
    assert decision is not None
    declined = engine.resolve_decision(state, "p0", decision["id"], "0")
    assert not any(event["type"] == "ABILITY_TRIGGERED" for event in declined.events)

    rolled = engine.roll_dice(declined.state, "p0")
    assert [event["value"] for event in rolled.events if event["type"] == "DIE_ROLLED"] == [4]
    roll = next(event for event in rolled.events if event["type"] == "DICE_ROLLED")
    assert roll["values"] == [4]
    assert roll["noDice"] is False
    step = next(
        event
        for event in rolled.events
        if event["type"] == "RACER_MOVED" and event["athleteId"] == "legs"
    )
    assert (step["from"], step["to"]) == (0, 4)


def test_duelist_hands_the_second_throw_to_target_and_wins_ties() -> None:
    engine = MagsimGameEngine(random.Random(32))
    players = make_players(2)
    teams = {
        "p0": (ATHLETE_BY_ID["duelist"], ATHLETE_BY_ID["banana"]),
        "p1": (ATHLETE_BY_ID["skipper"], ATHLETE_BY_ID["blimp"]),
    }
    state = replace(
        engine.create_game(players),
        phase=GamePhase.CHARACTER_SELECTION,
        teams=teams,
        first_turn_player_id="p0",
    )
    state = engine.select_racers(state, "p0", ("duelist", "banana")).state
    state = engine.select_racers(state, "p1", ("skipper", "blimp")).state
    decision = state.pending_decision
    assert decision is not None
    target_option = next(
        option["id"] for option in decision["options"] if "Skipper" in option["label"]
    )
    rng = MagicMock(wraps=random.Random(0))
    rng.randint.side_effect = [4, 4]
    state.magsim_engine.rng = rng

    started = engine.resolve_decision(state, "p0", decision["id"], target_option)
    assert started.state.pending_roll is not None
    assert started.state.pending_roll["nextPlayerId"] == "p0"

    challenger = engine.roll_dice(started.state, "p0")
    assert challenger.state.pending_roll is not None
    assert challenger.state.pending_roll["nextPlayerId"] == "p1"
    with pytest.raises(GameRuleError) as error:
        engine.roll_dice(challenger.state, "p0")
    assert error.value.code == "NOT_ROLLING_PLAYER"

    target = engine.roll_dice(challenger.state, "p1")
    result = next(
        event for event in target.events if event["type"] == "ABILITY_ROLL_RESOLVED"
    )
    assert [participant["value"] for participant in result["participants"]] == [4, 4]
    assert result["winnerAthleteId"] == "duelist"
    assert target.state.positions["duelist"] == 2


def test_movement_event_identifies_skill_source_and_victim() -> None:
    from types import SimpleNamespace
    from magsim.core.events import Phase, PostMoveEvent

    engine = MagsimGameEngine(random.Random(1))
    state = SimpleNamespace(
        racer_owner_by_index={0: "p0", 1: "p1"},
        racer_athlete_by_index={0: ATHLETE_BY_ID["centaur"], 1: ATHLETE_BY_ID["banana"]},
    )
    event = PostMoveEvent(
        responsible_racer_idx=0, source="CentaurTrample", phase=Phase.REACTION,
        target_racer_idx=1, start_tile=4, end_tile=2,
    )
    events = []
    engine._append_public_event(events, state, event)
    assert events[0]["sourcePlayerId"] == "p0"
    assert events[0]["sourceAthleteId"] == "centaur"
    assert events[0]["playerId"] == "p1"
    assert events[0]["athleteId"] == "banana"
    assert (events[0]["from"], events[0]["to"]) == (4, 2)
