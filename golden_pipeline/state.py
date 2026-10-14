"""항목 상태 전이. 허용된 전이만 받고, 지나온 전이를 state_history 에 남긴다."""
from datetime import datetime, timezone

# 보류(held)는 사람이 검토해 출시하거나 거절한다. 출시·거절은 끝 상태다.
TRANSITIONS = {
    "candidate": ("auto_validated", "held", "rejected"),
    "auto_validated": ("held", "rejected", "released"),
    "held": ("released", "rejected"),
    "rejected": (),
    "released": (),
}


class StateError(ValueError):
    pass


def transition(item, to, reason):
    """전이를 적용한 새 항목을 돌려준다. 원래 항목은 바꾸지 않는다."""
    if to not in TRANSITIONS[item["state"]]:
        raise StateError(f"허용되지 않는 전이: {item['state']} -> {to}")
    step = {
        "from": item["state"],
        "to": to,
        "reason": reason,
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return {**item, "state": to, "state_history": [*item["state_history"], step]}
