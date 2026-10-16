"""A 의 자기 개선. round 마다 A 생성 → 독립 검증 → 거절을 실패 기록(failure_memory)으로 남기고, 다음 round 의 A 프롬프트에 그 예방 규칙을 붙인다.

실패 기록에는 고친 답을 사실로 넣지 않는다. 검증하지 않은 답이 다음 후보에 사실처럼 들어가면 오염되기 때문이다.
그래서 기록 항목은 실패 코드, 보존된 실패(rejected.jsonl 의 한 줄, 또는 출시 매니페스트에 남은 뺀 항목)를 가리키는 참조,
코드마다 정해 둔 예방 규칙과 그 버전만 갖는다.
B · C 는 실패 기록을 읽지 않는다. 이 모듈은 A run 만 다룬다.
기준(주제 명세, 검증기 프롬프트 · 버전, 난도 규칙)은 바꾸지 않는다. 목표에 못 미치면 모자란 수를 보고한다.
예방 규칙은 무조건 더하지 않는다. 새 규칙은 validation 묶음에서 지금 정책보다 낫다고 잰 때만 채택한다 (adoption).
"""
import hashlib
import json
import threading

from golden_pipeline import adoption, generation, plan, storage, validation

PREVENTION_VERSION = "prevention-8"
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
    # 같은 앞말의 not_multi_hop 보다 먼저 맞춘다. 근거는 둘 이상 이었지만 청크가 하나였던 실패다.
    ("multi_hop 아님: 인용한 근거가 모두 한 청크", "single_chunk"),
    ("multi_hop 아님", "not_multi_hop"),
    ("검증기 출력 오류", "validator_output"),
    ("근거 충돌", "evidence_conflict"),
    ("모호한 대상", "ordinal_reference"),
    ("끊긴 질문", "malformed_question"),
    ("빈 칸 표", "broken_table"),
    ("답 덧붙임", "answer_dump"),
    ("비교 아님", "invalid_comparison"),
    ("판정기 출력 오류", "validator_output"),
    ("대상 문서에 있음", "present_in_target"),
    ("전제가 문서에 있음", "premise_in_document"),
    ("근거 지칭", "evidence_reference"),
    ("배점 기준", "scoring_as_requirement"),
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
    "single_chunk": "evidence 에 청크 번호가 다른 근거를 함께 넣고, 그 근거들을 이어야 답이 나오게 묻는다.",
    "validator_output":"질문은 근거만 읽고 짧은 답 하나로 답할 수 있게 묻는다.",
    "evidence_conflict": "근거끼리 값이 다르게 적힌 사실은 묻지 않는다.",
    "present_in_target": "어느 사업 문서에나 있을 만한 속성 말고, 근거 사업에만 있는 고유한 속성과 핵심어로 묻는다.",
    "premise_in_document": "stated 는 문서의 어느 값과도 겹치지 않게, 근거의 다른 값이나 흔한 값을 피한 드문 수로 바꾼다.",
    # 아래는 검증을 통과했지만 규칙 검사(validation.rule_reason) · 출시 쓸모 판정이 뺀 실패의 코드다 (record_screen).
    "useless_answer": "답이 '방문 후 열람 가능' · '없음' 같은 안내 문구나 빈 값이 되는 질문은 만들지 않는다.",
    "ordinal_reference": "대상을 순번('1행' · '번호 3' · '연번 2'), '둘 중', '첫 번째 값' · '값과 단위' 로 가리키지 말고 이름으로 가리킨다.",
    "broken_table": "병합 셀 · 빈 칸 · 밀린 열이 있어 칸의 뜻이 하나로 정해지지 않는 표 행은 묻지 않는다.",
    "answer_dump": "답에는 묻는 내용만 쓰고, 근거 원문이나 '(조건: …)' 같은 덧붙임을 붙이지 않는다.",
    "invalid_comparison": "같은 종류의 대상끼리만 비교하고, 표 머리글 · 합계와 그 부분 · 서로 다른 속성(예: 인원과 기간)은 비교하지 않는다.",
    "malformed_question": "질문은 끊기지 않은 완결된 한 문장으로 쓴다.",
    "scoring_as_requirement": "배점표의 기준값은 배점 · 평가 기준으로 묻고, 제출 · 참가 요건처럼 묻지 않는다.",
    "personal_info": "사람 이름 · 연락처 · 결재란을 묻지 않는다.",
    "structure_question": "목차 번호 · 항목 위치 · 표 형식을 묻지 말고 내용을 묻는다.",
    "evidence_reference": "질문자는 근거를 보지 못하므로 'E1 · E2' · '근거들' · '이 요구사항' 처럼 근거를 가리키지 말고 이름으로 묻는다.",
}
LOOP_CONFIG = ("max_rounds", "max_calls", "budget_usd", "generator", "validator")
# 생성기 · 검증기마다 모델 · 추론 강도 · 단가. 호출 수 한도와 예산은 loop 전체의 값에서 남은 만큼을 round 마다 넘긴다.
PRICED = ("model", "reasoning_effort", "usd_per_million_input_tokens", "usd_per_million_output_tokens")


def improve(topic, plan_id, loop_id, config_path, generator, validator):
    """A 를 round 마다 정책 채택 → 생성 → 검증 → 실패 기록으로 돌리고, 끝에 held-out 을 잰 뒤
    멈춘 이유와 목표 대비 모자란 수를 report.json 에 남긴다.

    round n 의 run_id 는 {loop_id}-r{n} 이고 계획의 train 묶음만 부른다. 채택을 정하는 validation run 은 {loop_id}-v{n},
    held-out run 은 {loop_id}-h-base · {loop_id}-h-final 이다. 도중에 멈춘 loop 를 같은 인자로 다시 부르면
    끝난 단계는 건너뛰고 남은 단계부터 잇는다.
    설정 · 계획 · 통과 기준은 loop 를 시작할 때 고정하고, round 마다와 report 직전에 그대로인지 본다.
    """
    config = _loop_config(config_path)
    loop_dir = _loop_dir(topic, loop_id)
    _pin(loop_dir, plan_id, config)
    empty = [part for part in ("validation", "held_out") if not _split_bundles(plan_id, topic, part)]
    if empty:
        raise ValueError(f"계획 {plan_id} 의 {topic} 묶음이 적어 {empty} 몫이 비었습니다. 정책을 잴 수 없습니다")
    clients = (_counted(generator, loop_dir, config["generator"]), _counted(validator, loop_dir, config["validator"]))
    stop = None
    for n in range(1, config["max_rounds"] + 1):
        _pin(loop_dir, plan_id, config)
        stop = _round(topic, plan_id, loop_id, n, config, clients)
        if stop:
            break
    _pin(loop_dir, plan_id, config)
    held_out, held_stop = _held_out(topic, plan_id, loop_id, config, clients)
    # held-out 의 한도가 마지막으로 멈춘 이유다. round 가 no_open_bundles 로 먼저 끝났어도 그것을 남긴다.
    report = _report(topic, plan_id, loop_id, held_stop or stop or "max_rounds", held_out)
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


def record_screen(topic, version):
    """출시에서 규칙 검사 · 쓸모 판정이 뺀 A 항목을 failure_memory/screen_{version}.jsonl 로 남긴다.

    검증을 통과해도 출시에서 빠진 항목은 다음 생성이 피해야 할 실패다. 기록에 넣지 않으면 생성기가 같은 실패를 되풀이한다.
    항목은 출시 매니페스트의 dropped 에서만 만들고, record_failures 처럼 코드 · 참조 · 예방 규칙만 남긴다.
    판정기가 코드를 고른 항목은 그 코드를, 규칙 검사 · 판정기 출력 오류로 빠진 항목은 이유 문구의 코드를 쓴다.
    """
    release_dir = storage._child(storage._topic_dir(topic) / "releases", version)
    dropped = storage._read_json(release_dir / "manifest.json")["release"]["dropped"]
    entries = []
    for row in (row for row in dropped if row["method"] == "A"):
        code = row["code"] or failure_code(row["reason"])
        entries.append({
            "entry_id": f"screen-{version}:{len(entries) + 1}",
            "failure_code": code,
            "evidence": {"release": version, "run": f"A/{row['run_id']}", "candidate_id": row["candidate_id"]},
            "prevention_rule": PREVENTION_RULES[code],
            "rule_version": PREVENTION_VERSION,
        })
    path = storage._child(storage._topic_dir(topic) / "failure_memory", f"screen_{version}.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
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
    """주제의 A 실패 기록과 출시에서 빠진 A 항목의 기록을 실패 코드별로 묶은 {코드: [entry_id]}. 다른 주제와 B · C 의 기록은 없다."""
    related = {}
    folder = storage._topic_dir(topic) / "failure_memory"
    for path in sorted([*folder.glob("A_*.jsonl"), *folder.glob("screen_*.jsonl")]):
        for entry in storage._read_jsonl(path):
            related.setdefault(entry["failure_code"], []).append(entry["entry_id"])
    return related


def open_bundles(topic, plan_id, loop_id):
    """loop 의 앞 round 에서 통과하지 못한 train 묶음 → 그 묶음에서 마지막으로 거절된 후보 id (없으면 None)."""
    parents = {bundle_id: None for bundle_id in _split_bundles(plan_id, topic, "train")}
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
        "adoption": adoption.settings(),
    }


def _round(topic, plan_id, loop_id, n, config, clients):
    """round n 의 남은 단계를 한다. 다음 round 로 가면 None, 멈추면 멈춘 이유를 돌려준다."""
    run_id = f"{loop_id}-r{n}"
    run_dir = storage.run_path(topic, "A", run_id)
    if not _generated(topic, loop_id, f"r{n}"):
        stop = _generate(topic, plan_id, loop_id, n, config, clients)
        if stop:
            return stop
    if not (run_dir / "validation.json").exists():
        stop = generation.limit_reached(config, *_spent(topic, loop_id))
        if stop:
            return stop
        validation.validate(topic, "A", run_id, _limits(topic, loop_id, f"r{n}", config, "validator"), clients[1])
    if not _memory_path(topic, run_id).exists():
        record_failures(topic, run_id)
    return _status(run_dir)


def _generate(topic, plan_id, loop_id, n, config, clients):
    parents = open_bundles(topic, plan_id, loop_id)
    if not parents:
        return "no_open_bundles"
    # 채택을 재는 run 이 남은 한도를 다 쓸 수 있으므로 채택 뒤에도 한도를 다시 본다.
    stop = (generation.limit_reached(config, *_spent(topic, loop_id))
            or _adopt(topic, plan_id, loop_id, n, config, clients)
            or generation.limit_reached(config, *_spent(topic, loop_id)))
    if stop:
        return stop
    codes = storage._read_json(_loop_path(topic, loop_id) / f"r{n}-adoption.json")["adopted"]
    path = _limits(topic, loop_id, f"r{n}", config, "generator")
    generation.generate("A", topic, plan_id, f"{loop_id}-r{n}", path, clients[0],
                        _revision(topic, loop_id, f"r{n}", parents, codes, "train"))
    return None


def _adopt(topic, plan_id, loop_id, n, config, clients):
    """round n 이 쓸 예방 규칙을 정해 r{n}-adoption.json 에 남긴다. 멈추면 그 이유를, 정했으면 None 을 돌려준다.

    주제의 실패 코드 중 이 loop 가 아직 채택하지도 버리지도 않은 코드에서 기록이 가장 많은 하나를 더한 정책으로
    validation 묶음을 생성 · 검증해 지금 정책의 validation 결과와 묶음끼리 짝지어 견준다.
    짝지은 통과 차이의 부트스트랩 하한이 0 보다 클 때만 채택하고, 채택되지 않은 코드는 이 loop 에서 다시 시도하지 않는다.
    코드를 한 번에 하나만 시험한다. 여럿을 함께 붙이면 도움이 되는 규칙이 해로운 규칙과 함께 버려진다 (fill1 의 table · comparison).
    """
    path = _loop_path(topic, loop_id) / f"r{n}-adoption.json"
    if path.exists():
        return None
    state = _policy(topic, loop_id, n - 1)
    related = related_failures(topic)
    untried = set(related) - set(state["adopted"]) - set(state["retired"])
    measured = _measured_codes(topic, loop_id, f"v{n}")
    # 끊긴 뒤 다른 loop 가 실패 기록 수를 바꾸면 다시 고른 코드가 이미 잰 run 의 코드와 달라진다. 잰 코드로 정한다.
    new = (sorted(set(measured) - set(state["adopted"])) if measured is not None
           else sorted(untried, key=lambda code: (-len(related[code]), code))[:1])
    decision = {**state, "tried": new, "gain": None, "floor": None}
    if new:
        candidate = sorted(state["adopted"] + new)
        stop = (_measure(topic, plan_id, loop_id, state["reference"], state["adopted"], "validation", config, clients)
                or _measure(topic, plan_id, loop_id, f"v{n}", candidate, "validation", config, clients))
        if stop:
            return stop
        gain, floor = adoption.paired_gain(adoption.passes(topic, f"{loop_id}-v{n}"),
                                           adoption.passes(topic, f"{loop_id}-{state['reference']}"))
        decision.update(gain=gain, floor=floor)
        if floor > 0:
            decision.update(adopted=candidate, reference=f"v{n}")
        else:
            decision.update(retired=sorted(state["retired"] + new))
    storage._write_json(path, decision)
    return None


def _policy(topic, loop_id, n):
    """round n 까지 정한 정책: 채택한 코드, 그 정책을 잰 validation run, 버린 코드. round 0 은 규칙 없는 정책(v0)이다."""
    if n == 0:
        return {"adopted": [], "reference": "v0", "retired": []}
    decided = storage._read_json(_loop_path(topic, loop_id) / f"r{n}-adoption.json")
    return {key: decided[key] for key in ("adopted", "reference", "retired")}


def _measured_codes(topic, loop_id, name):
    """이 loop 가 이미 생성한 run {loop_id}-{name} 의 예방 규칙 코드. 아직 생성하지 않았으면 None."""
    if not _generated(topic, loop_id, name):
        return None
    generated = storage._read_json(storage.run_path(topic, "A", f"{loop_id}-{name}") / "manifest.json")["generation"]
    return sorted(generated["policy"]["failures"])


def _measure(topic, plan_id, loop_id, name, codes, part, config, clients):
    """예방 규칙 codes 로 계획의 part(validation · held_out) 묶음을 생성 · 검증한 run {loop_id}-{name}. 멈추면 그 이유.

    이 run 의 거절은 실패 기록에 넣지 않는다. validation 은 채택을 정하는 데만, held-out 은 재는 데만 쓴다.
    이미 검증한 run 이면 다시 부르지 않는다.
    """
    run_dir = storage.run_path(topic, "A", f"{loop_id}-{name}")
    if not _generated(topic, loop_id, name):
        stop = generation.limit_reached(config, *_spent(topic, loop_id))
        if stop:
            return stop
        parents = {bundle_id: None for bundle_id in _split_bundles(plan_id, topic, part)}
        generation.generate("A", topic, plan_id, run_dir.name, _limits(topic, loop_id, name, config, "generator"),
                            clients[0], _revision(topic, loop_id, name, parents, codes, part))
    if not (run_dir / "validation.json").exists():
        stop = generation.limit_reached(config, *_spent(topic, loop_id))
        if stop:
            return stop
        validation.validate(topic, "A", run_dir.name, _limits(topic, loop_id, name, config, "validator"), clients[1])
    return _status(run_dir)


def _held_out(topic, plan_id, loop_id, config, clients):
    """loop 끝의 held-out: 규칙 없는 정책(h-base)과 마지막에 채택한 정책(h-final)을 같은 묶음에서 견준다.

    held-out 은 어떤 채택 결정에도 쓰지 않았으므로, 이 차이가 채택한 규칙의 실제 효과다.
    (report 의 held_out, 한도에 닿아 멈췄으면 그 이유) 를 돌려준다.
    """
    rounds = sum(1 for _ in _loop_path(topic, loop_id).glob("r*-adoption.json"))
    adopted = _policy(topic, loop_id, rounds)["adopted"]
    if not adopted:
        return {"measured": False, "reason": "채택한 예방 규칙이 없습니다"}, None
    stop = (_measure(topic, plan_id, loop_id, "h-base", [], "held_out", config, clients)
            or _measure(topic, plan_id, loop_id, "h-final", adopted, "held_out", config, clients))
    if stop:
        return {"measured": False, "reason": stop}, stop
    base, final = adoption.passes(topic, f"{loop_id}-h-base"), adoption.passes(topic, f"{loop_id}-h-final")
    gain, floor = adoption.paired_gain(final, base)
    return {"measured": True, "adopted": adopted, "bundles": len(base), "base_passed": sum(base.values()),
            "final_passed": sum(final.values()), "gain": gain, "floor": floor}, None


def _split_bundles(plan_id, topic, part):
    planned = plan.load_plan(plan_id)[0]
    return [bundle["bundle_id"] for bundle in planned["bundles"]
            if bundle["topic"] == topic and adoption.split(bundle["bundle_id"]) == part]


def _status(run_dir):
    """생성 · 검증 중 끝나지 못한 쪽의 상태 (한도 등), 둘 다 끝났으면 None."""
    statuses = (storage._read_json(run_dir / "manifest.json")["generation"]["status"],
                storage._read_json(run_dir / "validation.json")["status"])
    return next((status for status in statuses if status != "complete"), None)


def _revision(topic, loop_id, name, parents, codes, part):
    """A run 의 입력: 부를 묶음과 그 부모 후보, 채택한 실패 코드(codes)의 예방 규칙 글,
    묶음마다 그 묶음에서 거절된 지난 시도(notes), 매니페스트에 남길 policy.
    name 은 loop 안의 run 이름(r1 · v0 · h-base), part 는 그 묶음의 몫(train · validation · held_out)이다."""
    related = related_failures(topic)
    rules = "".join(f"- {PREVENTION_RULES[code]}\n" for code in codes)
    prevention = f"\n\n지난 실패에서 정한 예방 규칙\n{rules}" if rules else ""
    notes = bundle_notes(topic, loop_id, parents)
    policy = {
        "version": PREVENTION_VERSION,
        "loop_id": loop_id,
        "round": name,
        "part": part,
        "start_sha256": storage._sha256(_loop_path(topic, loop_id) / "start.json"),
        "failures": {code: related[code] for code in codes},
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


def _limits(topic, loop_id, name, config, role):
    """loop 전체 한도에서 이미 쓴 호출 · 비용을 뺀 run 설정 파일. 생성 · 검증은 이 파일로 돈다."""
    calls, cost = _spent(topic, loop_id)
    path = _loop_path(topic, loop_id) / f"{name}-{role}.json"
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


def _report(topic, plan_id, loop_id, stop, held_out):
    """멈춘 이유, round 별 상태 · policy · 채택 결정, held-out 효과, 쓴 호출 · 비용, train 묶음 대비 통과 묶음과 모자란 수."""
    rounds, accepted = [], set()
    for n, run_dir in enumerate(_rounds(topic, loop_id), 1):
        generated = storage._read_json(run_dir / "manifest.json")["generation"]
        record = storage._read_json(run_dir / "validation.json") if (run_dir / "validation.json").exists() else None
        rounds.append({
            "run_id": run_dir.name,
            "generation_status": generated["status"],
            "validation_status": record["status"] if record else "not_validated",
            "counts": record["counts"] if record else None,
            "policy": generated["policy"],
            "adoption": _policy_record(topic, loop_id, n),
        })
        if record:
            accepted.update(item["bundle_id"] for item in storage.read_validated(topic, "A", run_dir.name))
    calls, cost = _spent(topic, loop_id)
    # 출시용 후보는 train 묶음에서만 나온다. validation · held-out 묶음은 정책을 재는 데만 쓴다.
    target = len(_split_bundles(plan_id, topic, "train"))
    return {
        "loop_id": loop_id, "topic": topic, "plan_id": plan_id, "stop_reason": stop, "rounds": rounds,
        "held_out": held_out, "calls": calls, "cost_usd": cost, "target": target, "auto_validated": len(accepted),
        "shortfall": max(0, target - len(accepted)), "thresholds": thresholds(),
    }


def _policy_record(topic, loop_id, n):
    return storage._read_json(_loop_path(topic, loop_id) / f"r{n}-adoption.json")


def _rounds(topic, loop_id):
    """loop 의 생성이 끝난 round 디렉터리를 차례로."""
    n = 1
    while _generated(topic, loop_id, f"r{n}"):
        yield storage.run_path(topic, "A", f"{loop_id}-r{n}")
        n += 1


def _generated(topic, loop_id, name):
    """loop 안의 run {loop_id}-{name} 이 생성됐는지. 있으면 이 loop 가 start.json 의 계획으로 그 이름에 만든 run 이어야 한다.

    run 이름만 같다고 이어 쓰면, 따로 만든 run 이나 다른 계획 · 다른 시작 기록의 run 이 이 loop 의 run 으로 검증 · 보고된다.
    """
    run_dir = storage.run_path(topic, "A", f"{loop_id}-{name}")
    if not (run_dir / "manifest.json").exists():
        return False
    generated = storage._read_json(run_dir / "manifest.json")["generation"]
    policy = generated["policy"] or {}
    start = _loop_path(topic, loop_id) / "start.json"
    pinned = storage._read_json(start)
    owner = {"loop_id": loop_id, "round": name, "start_sha256": storage._sha256(start),
             "plan_id": pinned["plan_id"], "plan_sha256": pinned["plan_sha256"]}
    found = {"loop_id": policy.get("loop_id"), "round": policy.get("round"), "start_sha256": policy.get("start_sha256"),
             "plan_id": generated["plan_id"], "plan_sha256": generated["plan_sha256"]}
    changed = sorted(key for key in owner if owner[key] != found[key])
    if changed:
        raise ValueError(f"{run_dir.name} 은 loop {loop_id} 가 {name} 로 만든 run 이 아닙니다: {changed}")
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


