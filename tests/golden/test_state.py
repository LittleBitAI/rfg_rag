import pytest

from golden_pipeline.schema import validate_item
from golden_pipeline.state import StateError, transition


def test_transitions_keep_history_in_order_and_every_step_stays_valid(make_item):
    # 첫 전이가 validator_version 을 비워 둔 채 끝나 스키마가 거절하던 결함을 막는다: 매 단계를 validate_item 으로 확인한다.
    item = make_item()
    validated = transition(item, "auto_validated", "검증기 통과", validator_version="val-0.1")
    held = transition(validated, "held", "근거 표 격자 미확인")
    released = transition(held, "released", "사람 검토 승인")

    for step in (item, validated, held, released):
        validate_item(step)
    assert released["state"] == "released"
    assert released["validator_version"] == "val-0.1"
    assert [(s["from"], s["to"], s["reason"]) for s in released["state_history"]] == [
        ("candidate", "auto_validated", "검증기 통과"),
        ("auto_validated", "held", "근거 표 격자 미확인"),
        ("held", "released", "사람 검토 승인"),
    ]
    assert item["state_history"] == []
    assert item["validator_version"] is None


@pytest.mark.parametrize("to", ["auto_validated", "held", "rejected"])
def test_leaving_candidate_needs_validator_version(make_item, to):
    with pytest.raises(StateError, match="validator_version"):
        transition(make_item(), to, "통과")
    validate_item(transition(make_item(), to, "통과", validator_version="val-0.1"))


def test_validator_version_is_not_replaced_after_candidate(make_item):
    validated = transition(make_item(), "auto_validated", "통과", validator_version="val-0.1")
    with pytest.raises(StateError, match="validator_version"):
        transition(validated, "released", "출시", validator_version="val-9")


@pytest.mark.parametrize("start, to", [
    ("candidate", "released"),
    ("candidate", "candidate"),
    ("held", "auto_validated"),
    ("rejected", "auto_validated"),
    ("released", "rejected"),
])
def test_illegal_transition_is_rejected_and_history_untouched(make_item, start, to):
    history = [{"from": "candidate", "to": start, "reason": "준비", "at": "2026-10-14T00:00:00+00:00"}]
    item = make_item(state=start, state_history=history)
    with pytest.raises(StateError):
        transition(item, to, "잘못된 전이")
    assert item["state"] == start
    assert item["state_history"] == history
