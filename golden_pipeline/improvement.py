"""A 의 자기 개선. round 마다 A 생성 → 독립 검증 → 거절을 실패 기록(failure_memory)으로 남기고, 다음 round 의 A 프롬프트에 그 예방 규칙을 붙인다.

실패 기록에는 고친 답을 사실로 넣지 않는다. 검증하지 않은 답이 다음 후보에 사실처럼 들어가면 오염되기 때문이다.
그래서 기록 항목은 실패 코드, 보존된 실패(rejected.jsonl 의 한 줄)를 가리키는 참조, 코드마다 정해 둔 예방 규칙과 그 버전만 갖는다.
B · C 는 실패 기록을 읽지 않는다. 이 모듈은 A run 만 다룬다.
기준(주제 명세, 검증기 프롬프트 · 버전, 난도 규칙)은 바꾸지 않는다. 목표에 못 미치면 모자란 수를 보고한다.
"""
import hashlib
import json
import threading

from golden_pipeline import generation, plan, storage, validation

PREVENTION_VERSION = "prevention-4"
# 거절 이유의 앞부분 → 실패 코드. 이유는 generation · validation 이 만드는 고정 문구다.
FAILURE_CODES = (
    ("JSON 이 아닙니다", "output_format"),
    ("출력 필드는 정확히", "output_format"),
    ("evidence 는 이 묶음의", "evidence_label"),
    ("스키마:", "schema"),
    ("유형 불일치", "type_mismatch"),
    ("근거 묶음이 이미", "evidence_owned"),
    ("표 관계", "table_relation"),
    ("조건 · 예외 누락", "missing_condition"),
    ("중복", "duplicate"),
    ("근거만으로 답할 수 없습니다", "unanswerable"),
    ("독립 답과 다릅니다", "answer_mismatch"),
    ("복사형", "copied"),
    ("multi_hop 아님", "not_multi_hop"),
    ("검증기 출력 오류", "validator_output"),
    ("근거 충돌", "evidence_conflict"),
)
# 규칙 글을 바꾸면 PREVENTION_VERSION 을 올린다. 기록 항목은 쓸 때의 버전을 남긴다.
PREVENTION_RULES = {
    "output_format": "출력은 정해진 필드만 가진 JSON 객체 하나로 쓰고, 다른 글을 붙이지 않는다.",
    "evidence_label": "evidence 에는 사용자 메시지에 있는 서로 다른 근거 라벨만 넣는다.",
    "schema": "필드마다 정해진 형을 지키고 질문과 답을 비우지 않는다.",
    "type_mismatch": "structure 에는 주제 명세의 필드만 넣고 (필드가 없는 주제는 빈 객체 {}), 값은 근거에 적힌 그대로 쓴다.",
    "evidence_owned": "다른 주제의 질문이 되는 근거 조합은 피하고, 이 주제가 요구하는 근거로만 묻는다.",
    "table_relation": "답에는 행 이름과 열 이름이 만나는 칸의 값을 근거에 적힌 그대로 넣는다.",
    "missing_condition": "답 글에는 그 답을 제한하는 조건 · 예외 문구를 근거에 적힌 그대로 함께 쓴다. structure 의 값 · 단위에는 넣지 않는다.",
    "duplicate": "이미 통과한 질문과 같은 질문을 다시 만들지 않는다.",
    "unanswerable": "근거만 읽고 답할 수 있는 질문만 만든다.",
    "answer_mismatch": "답은 근거에서 바로 읽히는 값과 단위를 그대로 쓰고, 계산하거나 바꿔 쓰지 않는다.",
    "copied": "질문에 답의 값을 넣지 않는다.",
    "not_multi_hop": "근거 하나만으로는 답이 나오지 않고 둘 이상을 이어야 답이 나오는 질문을 만든다.",
    "validator_output": "질문은 근거만 읽고 짧은 답 하나로 답할 수 있게 묻는다.",
    "evidence_conflict": "근거끼리 값이 다르게 적힌 사실은 묻지 않는다.",
}
LOOP_CONFIG = ("max_rounds", "max_calls", "budget_usd", "generator", "validator")
# 생성기 · 검증기마다 모델 · 추론 강도 · 단가. 호출 수 한도와 예산은 loop 전체의 값에서 남은 만큼을 round 마다 넘긴다.
PRICED = ("model", "reasoning_effort", "usd_per_million_input_tokens", "usd_per_million_output_tokens")


def improve(topic, plan_id, loop_id, config_path, generator, validator):
    """A 를 round 마다 생성 → 검증 → 실패 기록으로 돌리고, 멈춘 이유와 목표 대비 모자란 수를 report.json 에 남긴다.

    round n 의 run_id 는 {loop_id}-r{n} 이다. 도중에 멈춘 loop 를 같은 인자로 다시 부르면
    끝난 round 는 건너뛰고, 끝나지 않은 round 는 남은 단계(생성 · 검증 · 실패 기록)부터 잇는다.
    설정 · 계획 · 통과 기준은 loop 를 시작할 때 고정하고, round 마다와 report 직전에 그대로인지 본다.
    """
    config = _loop_config(config_path)
    loop_dir = _loop_dir(topic, loop_id)
    clients = (_counted(generator, loop_dir, config["generator"]), _counted(validator, loop_dir, config["validator"]))
    stop = None
    for n in range(1, config["max_rounds"] + 1):
        _pin(loop_dir, plan_id, config)
        stop = _round(topic, plan_id, loop_id, n, config, clients)
        if stop:
            break
    _pin(loop_dir, plan_id, config)
    report = _report(topic, plan_id, loop_id, stop or "max_rounds")
    with storage.guard(loop_dir / "report.json").open("x", encoding="utf-8") as f:
        f.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def record_failures(topic, run_id):
    """검증한 A run 의 rejected.jsonl 한 줄마다 실패 코드와 예방 규칙을 붙여 failure_memory/A_{run_id}.jsonl 로 남긴다.

    실패 기록에 쓰는 곳은 여기 하나이고, 항목은 rejected.jsonl 의 줄에서만 만든다. 항목의 글은 코드마다 정해 둔
    예방 규칙뿐이고 나머지는 그 줄을 가리키는 참조뿐이라, 질문 · 답 · 고친 답 · 출시본 글이 들어올 자리가 없다.
    rejected.jsonl 은 그대로 둔다.
    """
    run_dir = storage.run_path(topic, "A", run_id)
    if not (run_dir / "validation.json").exists():
        raise ValueError(f"검증하지 않은 run 의 실패는 기록하지 않습니다: {topic}/A/{run_id}")
    entries = []
    for line, row in enumerate(storage._read_jsonl(run_dir / "rejected.jsonl"), 1):
        code = failure_code(_reason(row))
        entries.append({
            "entry_id": f"{run_id}:{line}",
            "failure_code": code,
            "evidence": {"run": f"A/{run_id}", "line": line, "candidate_id": row.get("candidate_id"),
                         "bundle_id": row["bundle_id"]},
            "prevention_rule": PREVENTION_RULES[code],
            "rule_version": PREVENTION_VERSION,
        })
    path = _memory_path(topic, run_id)
    path.parent.mkdir(exist_ok=True)
    storage._write_jsonl(path, entries)
    return path


def failure_code(reason):
    code = next((code for prefix, code in FAILURE_CODES if reason.startswith(prefix)), None)
    if code is None:
        raise ValueError(f"실패 코드가 정해지지 않은 거절 이유입니다. FAILURE_CODES 에 더하세요: {reason!r}")
    return code


def _reason(row):
    # 항목이 된 거절은 마지막 전이에, 항목이 되지 못한 생성 출력은 행에 이유가 있다.
    return row["state_history"][-1]["reason"] if "candidate_id" in row else row["reason"]


def related_failures(topic):
    """주제의 A 실패 기록을 실패 코드별로 묶은 {코드: [entry_id]}. 다른 주제와 B · C 의 기록은 없다."""
    related = {}
    for path in sorted((storage._topic_dir(topic) / "failure_memory").glob("A_*.jsonl")):
        for entry in storage._read_jsonl(path):
            related.setdefault(entry["failure_code"], []).append(entry["entry_id"])
    return related


def open_bundles(topic, plan_id, loop_id):
    """loop 의 앞 round 에서 통과하지 못한 묶음 → 그 묶음에서 마지막으로 거절된 후보 id (없으면 None)."""
    planned = plan.load_plan(plan_id)[0]
    parents = {bundle["bundle_id"]: None for bundle in planned["bundles"] if bundle["topic"] == topic}
    for run_dir in _rounds(topic, loop_id):
        for item in storage.read_validated(topic, "A", run_dir.name):
            parents.pop(item["bundle_id"], None)
        for row in storage._read_jsonl(run_dir / "rejected.jsonl"):
            if "candidate_id" in row and row["bundle_id"] in parents:
                parents[row["bundle_id"]] = row["candidate_id"]
    return parents


def thresholds():
    """통과 기준을 정하는 것들. loop 는 이 값을 바꾸지 않고, report 에 남겨 확인할 수 있게 한다."""
    return {
        "topic_specs": storage.snapshot(storage.CONFIGS / "topics"),
        "validator_prompt_sha256": storage._sha256(storage.PROMPTS / "validator.txt"),
        "judge_prompt_sha256": storage._sha256(storage.PROMPTS / "judge.txt"),
        "validator_version": validation.VALIDATOR_VERSION,
        "difficulty_rule": validation.DIFFICULTY_RULE,
    }


def _round(topic, plan_id, loop_id, n, config, clients):
    """round n 의 남은 단계를 한다. 다음 round 로 가면 None, 멈추면 멈춘 이유를 돌려준다."""
    run_id = f"{loop_id}-r{n}"
    run_dir = storage.run_path(topic, "A", run_id)
    if not _generated(topic, loop_id, n):
        stop = _generate(topic, plan_id, loop_id, n, config, clients[0])
        if stop:
            return stop
    if not (run_dir / "validation.json").exists():
        stop = generation.limit_reached(config, *_spent(topic, loop_id))
        if stop:
            return stop
        validation.validate(topic, "A", run_id, _limits(topic, loop_id, n, config, "validator"), clients[1])
    if not _memory_path(topic, run_id).exists():
        record_failures(topic, run_id)
    statuses = (storage._read_json(run_dir / "manifest.json")["generation"]["status"],
                storage._read_json(run_dir / "validation.json")["status"])
    return next((status for status in statuses if status != "complete"), None)


def _generate(topic, plan_id, loop_id, n, config, client):
    parents = open_bundles(topic, plan_id, loop_id)
    if not parents:
        return "no_open_bundles"
    stop = generation.limit_reached(config, *_spent(topic, loop_id))
    if stop:
        return stop
    path = _limits(topic, loop_id, n, config, "generator")
    generation.generate("A", topic, plan_id, f"{loop_id}-r{n}", path, client, _revision(topic, loop_id, n, parents))
    return None


def _revision(topic, loop_id, n, parents):
    """다음 A round 의 입력: 다시 부를 묶음과 그 부모 후보, 주제의 실패 코드에서 나온 예방 규칙 글,
    묶음마다 그 묶음에서 거절된 지난 시도(notes), 매니페스트에 남길 policy."""
    related = related_failures(topic)
    rules = "".join(f"- {PREVENTION_RULES[code]}\n" for code in sorted(related))
    prevention = f"\n\n지난 실패에서 정한 예방 규칙\n{rules}" if rules else ""
    notes = bundle_notes(topic, loop_id, parents)
    policy = {
        "version": PREVENTION_VERSION,
        "loop_id": loop_id,
        "round": n,
        "start_sha256": storage._sha256(_loop_path(topic, loop_id) / "start.json"),
        "failures": related,
        "prevention_sha256": hashlib.sha256(prevention.encode("utf-8")).hexdigest(),
        "notes": notes,
    }
    return {"parents": parents, "prevention": prevention, "notes": notes, "policy": policy}


def bundle_notes(topic, loop_id, parents):
    """다시 부를 묶음마다 이 loop 에서 그 묶음이 거절된 지난 시도: 그때의 질문과 실패 코드의 예방 규칙 (최근 셋).

    주제 전체의 예방 규칙만으로는 생성기가 이 묶음에서 무엇을 틀렸는지 모른다. 실패 기록 항목이 가리키는
    rejected.jsonl 줄에서 질문만 꺼내고, 고친 답 · 독립 답은 넣지 않는다 (검증하지 않은 답을 사실로 주지 않는다).
    """
    lines = {}
    for run_dir in _rounds(topic, loop_id):
        rejected = storage._read_jsonl(run_dir / "rejected.jsonl")
        for entry in storage._read_jsonl(_memory_path(topic, run_dir.name)):
            bundle = entry["evidence"]["bundle_id"]
            if bundle in parents:
                question = rejected[entry["evidence"]["line"] - 1].get("question")
                tried = f"질문 {question!r}" if question else "출력 (항목이 되지 못함)"
                lines.setdefault(bundle, []).append(f"- {tried}: {PREVENTION_RULES[entry['failure_code']]}")
    return {bundle: "\n\n이 근거 묶음에서 거절된 지난 시도\n" + "\n".join(tried[-3:]) for bundle, tried in lines.items()}


def _limits(topic, loop_id, n, config, role):
    """loop 전체 한도에서 이미 쓴 호출 · 비용을 뺀 run 설정 파일. 생성 · 검증은 이 파일로 돈다."""
    calls, cost = _spent(topic, loop_id)
    path = _loop_path(topic, loop_id) / f"r{n}-{role}.json"
    storage._write_json(path, {
        **config[role], "max_calls": config["max_calls"] - calls, "budget_usd": config["budget_usd"] - cost,
    })
    return path


def _counted(client, loop_dir, priced):
    """돌아온 호출마다 그 자리에서 calls.jsonl 에 남기는 client. 생성 · 검증이 도중에 끊겨도 쓴 호출 · 비용이 남는다.

    호출은 여러 스레드에서 함께 돌아오므로 한 줄씩 잠가 쓴다.
    """
    lock = threading.Lock()

    def call(model, reasoning_effort, messages):
        response = client(model=model, reasoning_effort=reasoning_effort, messages=messages)
        usage = {"model": response["model"], "input_tokens": response["input_tokens"],
                 "output_tokens": response["output_tokens"]}
        with lock:
            storage._append_jsonl(loop_dir / "calls.jsonl", [{**usage, "cost_usd": generation._cost(priced, [usage])}])
        return response
    return call


def _spent(topic, loop_id):
    """loop 가 생성 · 검증에 쓴 호출 수와 비용. 끊긴 run 의 호출까지 든 calls.jsonl 에서 읽는다."""
    path = _loop_path(topic, loop_id) / "calls.jsonl"
    records = storage._read_jsonl(path) if path.exists() else []
    return len(records), sum(record["cost_usd"] for record in records)


def _report(topic, plan_id, loop_id, stop):
    """멈춘 이유, round 별 상태 · policy, 쓴 호출 · 비용, 목표 개수 대비 통과 묶음과 모자란 수."""
    rounds, accepted = [], set()
    for run_dir in _rounds(topic, loop_id):
        generated = storage._read_json(run_dir / "manifest.json")["generation"]
        record = storage._read_json(run_dir / "validation.json") if (run_dir / "validation.json").exists() else None
        rounds.append({
            "run_id": run_dir.name,
            "generation_status": generated["status"],
            "validation_status": record["status"] if record else "not_validated",
            "counts": record["counts"] if record else None,
            "policy": generated["policy"],
        })
        if record:
            accepted.update(item["bundle_id"] for item in storage.read_validated(topic, "A", run_dir.name))
    calls, cost = _spent(topic, loop_id)
    target = plan.load_plan(plan_id)[0]["counts"][topic]
    return {
        "loop_id": loop_id, "topic": topic, "plan_id": plan_id, "stop_reason": stop, "rounds": rounds,
        "calls": calls, "cost_usd": cost, "target": target, "auto_validated": len(accepted),
        "shortfall": max(0, target - len(accepted)), "thresholds": thresholds(),
    }


def _rounds(topic, loop_id):
    """loop 의 생성이 끝난 round 디렉터리를 차례로."""
    n = 1
    while _generated(topic, loop_id, n):
        yield storage.run_path(topic, "A", f"{loop_id}-r{n}")
        n += 1


def _generated(topic, loop_id, n):
    """round n 의 생성 run 이 있는지. 있으면 이 loop 가 start.json 의 계획으로 round n 에 만든 run 이어야 한다.

    run 이름만 같다고 이어 쓰면, 따로 만든 run 이나 다른 계획 · 다른 시작 기록의 run 이 이 loop 의 round 로 검증 · 보고된다.
    """
    run_dir = storage.run_path(topic, "A", f"{loop_id}-r{n}")
    if not (run_dir / "manifest.json").exists():
        return False
    generated = storage._read_json(run_dir / "manifest.json")["generation"]
    policy = generated["policy"] or {}
    start = _loop_path(topic, loop_id) / "start.json"
    pinned = storage._read_json(start)
    owner = {"loop_id": loop_id, "round": n, "start_sha256": storage._sha256(start),
             "plan_id": pinned["plan_id"], "plan_sha256": pinned["plan_sha256"]}
    found = {"loop_id": policy.get("loop_id"), "round": policy.get("round"), "start_sha256": policy.get("start_sha256"),
             "plan_id": generated["plan_id"], "plan_sha256": generated["plan_sha256"]}
    changed = sorted(key for key in owner if owner[key] != found[key])
    if changed:
        raise ValueError(f"{run_dir.name} 은 loop {loop_id} 가 round {n} 에 만든 run 이 아닙니다: {changed}")
    return True


def _loop_config(path):
    """max_rounds · max_calls · budget_usd 와 생성기 · 검증기의 모델 · 추론 강도 · 단가. 기본값 없이 모두 적어야 한다."""
    config = storage._read_json(path)
    if not isinstance(config, dict) or set(config) != set(LOOP_CONFIG):
        raise ValueError(f"loop 설정은 정확히 {LOOP_CONFIG} 를 가져야 합니다: {path}")
    if not all(isinstance(config[role], dict) and set(config[role]) == set(PRICED) for role in ("generator", "validator")):
        raise ValueError(f"generator · validator 는 정확히 {PRICED} 를 가져야 합니다: {path}")
    limits = [config["max_rounds"], config["max_calls"]]
    if not all(isinstance(n, int) and not isinstance(n, bool) and n >= 1 for n in limits):
        raise ValueError(f"max_rounds · max_calls 는 1 이상의 정수여야 합니다: {path}")
    if not generation._is_number(config["budget_usd"]) or config["budget_usd"] <= 0:
        raise ValueError(f"budget_usd 는 0 보다 커야 합니다: {path}")
    return config


def _loop_dir(topic, loop_id):
    """loop 기록 디렉터리. 끝난 loop 는 다시 돌지 않는다."""
    loop_dir = _loop_path(topic, loop_id)
    if (loop_dir / "report.json").exists():
        raise FileExistsError(f"이미 끝난 loop 입니다: {topic}/{loop_id}")
    loop_dir.mkdir(parents=True, exist_ok=True)
    return loop_dir


def _pin(loop_dir, plan_id, config):
    """loop 를 시작할 때의 설정 · 계획 · 통과 기준을 start.json 에 고정하고, 그 뒤로는 지금 값이 같은지 본다.

    한도 · 계획 · 기준이 round 사이에 바뀌면 한 loop 의 round 들이 서로 다른 조건으로 돌고, report 는 그것을 드러내지 못한다.
    """
    current = {"config": config, "plan_id": plan_id, "plan_sha256": plan.load_plan(plan_id)[1],
               "thresholds": thresholds()}
    path = loop_dir / "start.json"
    if not path.exists():
        storage._write_json(path, current)
        return
    pinned = storage._read_json(path)
    changed = sorted(key for key in current if current[key] != pinned[key])
    if changed:
        raise ValueError(f"loop {loop_dir.name} 를 시작할 때와 다릅니다: {changed}")


def _loop_path(topic, loop_id):
    return storage._child(storage._topic_dir(topic) / "loops", loop_id)


def _memory_path(topic, run_id):
    return storage._child(storage._topic_dir(topic) / "failure_memory", f"A_{run_id}.jsonl")


