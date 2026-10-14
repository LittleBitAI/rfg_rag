"""A · B · C 생성 방식 비교 보고서. 같은 계획으로 만든 run 들을 방식별로 모아 지표마다 분자와 분모를 함께 남긴다.

C 는 사람이 웹에서 만들어 생성 토큰 · 비용을 관측할 수 없다. 0 으로 채우면 C 가 공짜처럼 보이고
유효 문항당 비용이 왜곡되므로 unobserved 로 두고, 그 값이 든 합계도 unobserved 로 둔다.
"""
import json
from collections import Counter

from golden_pipeline import improvement, plan, storage
from golden_pipeline.generation import UNOBSERVED

# 근거와 답이 맞지 않아 거절된 실패 코드. 출처 정확성의 분자에서 빠진다.
SOURCE_MISMATCH = ("table_relation", "unanswerable", "answer_mismatch")
# 근거 대조를 마치기 전에 걸릴 수 있는 거절. 출처를 판정하지 못했으므로 출처 정확성의 분모에서 빠진다.
SOURCE_UNCHECKED = ("type_mismatch", "missing_condition", "duplicate")
# 주제 구조 검사까지 간 뒤 항목이 되지 못한 생성 출력의 실패 코드. 유형 준수의 분모에 든다.
STRUCTURE_CHECKED = ("type_mismatch", "evidence_owned")
VERDICTS = ("auto_validated", "held", "rejected")
LEVELS = ("easy", "medium", "hard")


def write_report(topic, report_id, runs):
    """compare 결과를 goldens/{topic}/reports/{report_id}.json 에 쓴다. 이미 있는 보고서는 덮어쓰지 않는다."""
    report = compare(topic, runs)
    path = storage._child(storage._topic_dir(topic) / "reports", f"{report_id}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as f:
        f.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return path, report


def compare(topic, runs):
    """runs 는 {"A": [run_id, ...], "B": [...], "C": [...]} 이다. A 는 자기 개선 loop 의 round run 들이다.

    세 방식은 같은 계획(같은 근거 묶음 · 목표 분포)으로 만든 run 이어야 견줄 수 있어, 계획이 다르면 멈춘다.
    """
    runs = {method: list(run_ids) for method, run_ids in runs.items() if run_ids}
    collected = {method: _collect(topic, method, run_ids) for method, run_ids in runs.items()}
    plans = {pinned for data in collected.values() for pinned in data["plans"]}
    if len(plans) != 1:
        raise ValueError(f"같은 계획으로 만든 run 만 견줄 수 있습니다: {sorted(plans)}")
    [(plan_id, plan_sha)] = plans
    planned, current_sha = plan.load_plan(plan_id)
    if current_sha != plan_sha:
        raise ValueError(f"계획 {plan_id} 가 run 을 만든 뒤 바뀌었습니다")
    bundles = {bundle["bundle_id"] for bundle in planned["bundles"] if bundle["topic"] == topic}
    methods = {}
    for method, data in collected.items():
        quality = _quality(data["outputs"], bundles)
        methods[method] = {**quality, **_cost(data, quality["valid_rate"]["numerator"])}
    return {"topic": topic, "plan_id": plan_id, "plan_sha256": plan_sha, "created_at": storage._now(),
            "runs": runs, "methods": methods}


def _collect(topic, method, run_ids):
    """run 들의 생성 출력마다 판정 결과와, 생성 기록(매니페스트의 generation) · 검증 기록."""
    data = {"plans": set(), "outputs": [], "generation": [], "validation": []}
    for run_id in run_ids:
        run_dir = storage.run_path(topic, method, run_id)
        generated = storage._read_json(run_dir / "manifest.json")["generation"]
        data["plans"].add((generated["plan_id"], generated["plan_sha256"]))
        data["generation"].append(generated)
        data["validation"] += [storage._read_json(path) for path in storage.validation_records(run_dir)]
        data["outputs"] += _outputs(topic, method, run_id, run_dir)
    return data


def _outputs(topic, method, run_id, run_dir):
    """생성 출력 한 줄마다 {state, code, bundle_id, difficulty}. 항목이 되지 못한 출력의 state 는 not_item 이다.

    검증한 run 은 read_validated 로 상태 파일이 검증 기록과 같은지 먼저 본다.
    """
    verdicts = {}
    if storage.validation_records(run_dir):
        accepted, held = storage.read_validated(topic, method, run_id)
        verdicts = {item["candidate_id"]: item for item in accepted + held}
    outputs = []
    for row in storage._read_jsonl(run_dir / "rejected.jsonl"):
        if "candidate_id" in row:
            verdicts[row["candidate_id"]] = row
        else:
            outputs.append({"state": "not_item", "code": _code(row["reason"]), "bundle_id": row["bundle_id"],
                            "difficulty": None})
    for item in storage._read_jsonl(run_dir / "candidates.jsonl"):
        judged = verdicts.get(item["candidate_id"], item)
        rejected = judged["state"] == "rejected"
        outputs.append({"state": judged["state"], "code": _code(judged["state_history"][-1]["reason"]) if rejected else None,
                        "bundle_id": item["bundle_id"], "difficulty": judged["difficulty"]})
    return outputs


def _code(reason):
    # 계획에 없는 근거 묶음은 C 가져오기에만 있는 거절이라 A 의 실패 코드 표에 없다.
    return "unplanned_bundle" if reason.startswith("계획에 없는") else improvement.failure_code(reason)


def _quality(outputs, bundles):
    """문항 품질 지표. 분모: 생성 출력 수(유효 · 보류), 검증한 항목 수(중복), 계획의 근거 묶음 수(커버리지),
    유효 문항 수(난도). 출처 정확성 · 유형 준수의 분모는 그 검사까지 간 수다 (README 의 비교 보고서)."""
    states = Counter(output["state"] for output in outputs)
    validated = [output for output in outputs if output["state"] in VERDICTS]
    rejected = Counter(output["code"] for output in validated if output["state"] == "rejected")
    not_items = Counter(output["code"] for output in outputs if output["state"] == "not_item")
    valid = [output for output in outputs if output["state"] == "auto_validated"]
    checked = len(validated) - states["held"] - sum(rejected[code] for code in SOURCE_UNCHECKED)
    mismatched = sum(rejected[code] for code in SOURCE_MISMATCH)
    structured = len(outputs) - states["not_item"] + sum(not_items[code] for code in STRUCTURE_CHECKED)
    return {
        "outputs": len(outputs),
        "validated": len(validated),
        "pending": states["candidate"],
        "valid_rate": _ratio(len(valid), len(outputs)),
        "hold_rate": _ratio(states["held"], len(outputs)),
        "source_accuracy": _ratio(checked - mismatched, checked),
        "type_compliance": _ratio(structured - rejected["type_mismatch"] - not_items["type_mismatch"], structured),
        "duplicates": _ratio(rejected["duplicate"], len(validated)),
        "coverage": _ratio(len({output["bundle_id"] for output in valid} & bundles), len(bundles)),
        "difficulty": {level: _ratio(sum(output["difficulty"] == level for output in valid), len(valid))
                       for level in LEVELS},
    }


def _cost(data, valid):
    """생성 · 검증의 토큰과 비용, 총비용, 유효 문항당 비용. 생성 기록에 호출이 없으면(C) 생성 쪽은 unobserved 다."""
    observed = all("calls" in generated for generated in data["generation"])
    generation = _usage(data["generation"]) if observed else dict.fromkeys(_usage([]), UNOBSERVED)
    validation = _usage(data["validation"])
    total = generation["cost_usd"] + validation["cost_usd"] if observed else UNOBSERVED
    per_valid = _ratio(total, valid) if observed else {"numerator": UNOBSERVED, "denominator": valid,
                                                       "value": UNOBSERVED}
    return {"generation": generation, "validation": validation, "total_cost_usd": total,
            "cost_per_valid_item": per_valid}


def _usage(records):
    calls = [call for record in records for call in record["calls"]]
    return {
        "input_tokens": sum(call["input_tokens"] for call in calls),
        "output_tokens": sum(call["output_tokens"] for call in calls),
        "cost_usd": sum((record["cost_usd"] for record in records), 0.0),
    }


def _ratio(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


ROWS = (
    ("생성 출력", lambda m: m["outputs"]),
    ("검증하지 않은 후보 (pending)", lambda m: m["pending"]),
    ("유효 문항률", lambda m: m["valid_rate"]),
    ("보류율", lambda m: m["hold_rate"]),
    ("출처 정확성", lambda m: m["source_accuracy"]),
    ("유형 준수", lambda m: m["type_compliance"]),
    ("중복", lambda m: m["duplicates"]),
    ("커버리지 (근거 묶음)", lambda m: m["coverage"]),
    ("난도 easy", lambda m: m["difficulty"]["easy"]),
    ("난도 medium", lambda m: m["difficulty"]["medium"]),
    ("난도 hard", lambda m: m["difficulty"]["hard"]),
    ("생성 토큰 (입력 / 출력)", lambda m: (m["generation"]["input_tokens"], m["generation"]["output_tokens"])),
    ("검증 토큰 (입력 / 출력)", lambda m: (m["validation"]["input_tokens"], m["validation"]["output_tokens"])),
    ("생성 비용 USD", lambda m: m["generation"]["cost_usd"]),
    ("검증 비용 USD", lambda m: m["validation"]["cost_usd"]),
    ("총비용 USD", lambda m: m["total_cost_usd"]),
    ("유효 문항당 비용 USD", lambda m: m["cost_per_valid_item"]),
)


def render(report):
    """보고서를 마크다운 표로. 비율은 분자/분모 = 값, unobserved 는 그대로 적는다."""
    methods = list(report["methods"])
    lines = [f"주제 {report['topic']} · 계획 {report['plan_id']}", "",
             "| 지표 | " + " | ".join(methods) + " |", "|---" * (len(methods) + 1) + "|"]
    for label, pick in ROWS:
        lines.append(f"| {label} | " + " | ".join(_cell(pick(report["methods"][m])) for m in methods) + " |")
    return "\n".join(lines)


def _cell(value):
    if isinstance(value, tuple):
        return " / ".join(_cell(part) for part in value)
    if isinstance(value, dict):
        return f"{_cell(value['numerator'])}/{value['denominator']} = {_shown(value)}"
    return f"{value:.6f}" if isinstance(value, float) else str(value)


def _shown(ratio):
    """비율의 값: 개수의 비율은 백분율, 비용의 비율(유효 문항당 비용)은 USD, 분모가 0 이면 -."""
    value = ratio["value"]
    if value is None:
        return "-"
    if value == UNOBSERVED:
        return UNOBSERVED
    return f"{value:.1%}" if isinstance(ratio["numerator"], int) else f"{value:.6f}"

