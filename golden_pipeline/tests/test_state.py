import pytest

from golden_pipeline.state import StateError, transition


def test_transitions_keep_history_in_order(make_item):
    item = make_item()
    validated = transition(item, "auto_validated", "검증기 통과")
    held = transition(validated, "held", "근거 표 격자 미확인")
    released = transition(held, "released", "사람 검토 승인")

    assert released["state"] == "released"
    assert [(s["from"], s["to"], s["reason"]) for s in released["state_history"]] == [
        ("candidate", "auto_validated", "검증기 통과"),
        ("auto_validated", "held", "근거 표 격자 미확인"),
        ("held", "released", "사람 검토 승인"),
    ]
    assert item["state_history"] == []


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
