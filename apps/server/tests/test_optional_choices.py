from types import SimpleNamespace

import pytest

from magsim.core.interactive import DecisionBroker, PendingChoice


def pending(ability):
    return PendingChoice("choice", 0, ability, "选择目标", "RACER", ("target",), ("目标",))


@pytest.mark.parametrize("ability", ["DuelistDuel", "FlipFlopSwap", "HypnotistWarp", "ThirdWheelJoin"])
def test_optional_target_can_be_declined_and_replayed(ability):
    broker = DecisionBroker(pending=pending(ability))
    assert {"id": "skip", "label": "skip"} in broker.pending.public_options()
    broker.choose("choice", "skip")
    ctx = SimpleNamespace(source_racer_idx=0, source=SimpleNamespace(name=ability))
    assert broker.request(ctx, ("target",), ("目标",), "RACER") is None
    assert broker.pending is None
    assert broker.last_resolved.auto_answer is False
    broker.rewind()
    assert broker.request(ctx, ("target",), ("目标",), "RACER") is None
    broker.commit()
    assert broker.last_resolved is None


def test_required_die_choice_cannot_be_skipped():
    broker = DecisionBroker(pending=pending("GeniusPrediction"))
    assert all(option["id"] != "skip" for option in broker.pending.public_options())
    with pytest.raises(ValueError, match="INVALID_DECISION_OPTION"):
        broker.choose("choice", "skip")


def test_replay_remembers_multiple_choices_in_one_action():
    from magsim.core.interactive import DecisionRequired

    broker = DecisionBroker()
    def ctx(name):
        return SimpleNamespace(source_racer_idx=0, source=SimpleNamespace(name=name),
                               game_state=SimpleNamespace(roll_state=None), event=SimpleNamespace())
    a, b = ctx("CopyLead"), ctx("HypnotistWarp")
    with pytest.raises(DecisionRequired):
        broker.request(a, ("first", "second"), ("first", "second"), "RACER")
    broker.choose(broker.pending.id, "1")
    broker.rewind()
    assert broker.request(a, ("first", "second"), ("first", "second"), "RACER") == "second"
    with pytest.raises(DecisionRequired):
        broker.request(b, ("victim",), ("victim",), "RACER")
    broker.choose(broker.pending.id, "skip")
    broker.rewind()
    assert broker.request(a, ("first", "second"), ("first", "second"), "RACER") == "second"
    assert broker.request(b, ("victim",), ("victim",), "RACER") is None
    broker.commit()
    assert not broker.resolved_choices


def test_older_persisted_broker_can_resume():
    broker = DecisionBroker()
    del broker.resolved_choices
    del broker.replay_index
    broker.rewind()
    assert broker.resolved_choices == []
    assert broker.replay_index == 0
