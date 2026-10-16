"""독립 검증과 출시. 검증기는 질문과 근거 단위만 받아 스스로 답하고, 그 답을 후보의 답과 맞춰 본다.

검증기에는 생성기의 대화 · 프롬프트 · 답 · 구조 · 자기 평가를 보내지 않는다. 독립 답과의 비교가 이 단계의 요점이기 때문이다.
값과 글자로 같은지 정하지 못한 답(표현만 다른 글 답, 대상을 확인하지 못한 값)은 판정기가 독립 답과 후보 답을 받아
같은지 정한다. 독립 답은 이미 후보 답을 보지 않고 나왔으므로, 판정기가 둘을 견주어도 독립성은 그대로다.
모든 후보는 auto_validated(accepted.jsonl) 아니면 rejected(rejected.jsonl) 로 끝난다. 애매한 판정은 실패 코드가 없어
자기 개선에 쓸 수 없으므로 두지 않는다. 출시는 auto_validated 항목을 releases/{version}/ 로 모은다.
"""
import json
import re
import unicodedata
from decimal import Decimal
from functools import lru_cache

from golden_pipeline import evidence, generation, plan, storage
from golden_pipeline.generation import _contains, _norm
from golden_pipeline.state import transition

VALIDATOR_VERSION = "validation-6"
DIFFICULTY_RULE = (
    "difficulty-2: hard = multi_hop 이고 근거 단위를 하나씩만 준 검증기 답이 모두 독립 답에 못 미침 (근거 둘 이상 필요). "
    "easy = 그 밖에 질문의 내용 형태소(NNG · NNP · SL · SN, 의문사 제외, 앞에 붙인 문서 이름 제외)가 모두 근거 본문에 그대로 있음. "
    "medium = 나머지"
)
# Kiwi 는 얼마 를 일반 명사(NNG)로 단다. 의문사는 근거에 있을 수 없으므로 내용 형태소에서 뺀다.
INTERROGATIVES = ("얼마", "몇", "무엇", "어디", "언제", "누구", "어느")
VERDICT_FIELDS = ("answerable", "answer", "conditions", "conflict", "comparison")
DOCUMENT_PREFIX = storage.DOCUMENT_PREFIX
# 천 · 만 · 억(NR) 은 수에 곱하는 단위다. 5만원 과 50,000원 은 같은 값이다.
SCALES = {"십": 10, "백": 100, "천": 1000, "만": 10_000, "억": 10**8, "조": 10**12}
CONTENT_TAGS = ("NNG", "NNP", "SL", "SN")
# 값의 대상에는 의존 명사도 든다 (1차년도 의 차 · 년도).
SUBJECT_TAGS = CONTENT_TAGS + ("NNB",)
# 쓸모 판정기가 쓸모 없다고 할 때 고르는 실패 코드. 뺀 항목은 이 코드로 실패 기록에 들어가 다음 생성의 예방 규칙이 된다.
SCREEN_CODES = ("structure_question", "ordinal_reference", "evidence_reference", "copied", "answer_dump",
                "personal_info", "malformed_question", "invalid_comparison", "useless_answer")
# 칸이 비어 행의 뜻이 정해지지 않는 표 행: 빈 칸으로 시작하거나 빈 칸이 이어진다 (조직도 · 간트 모양).
BLANK_CELL = re.compile(r"(^|\n) *\||\| *\|")
# unanswerable 생성기는 다른 문서의 근거 라벨([E1 · 머리글 행])을 질문에 옮겨 적곤 한다. 질문자는 근거를 보지 못한다.
EVIDENCE_LABEL = re.compile(r"(?<![A-Za-z])E\d+(?!\d)|머리글 행")
# 배점표의 값을 배점 · 평가 기준으로 묻는 질문의 낱말 (공백을 지운 질문에서 찾는다).
SCORING_WORDS = re.compile(r"배점|점수|평가|\d+점|만점|득점|감점|가점")
# unanswerable 검증기에 한 번에 주는 대상 문서의 글자 수. 문서(중앙 6만 6천 자, 가장 긴 것 20만 자)를 몇 번에 나눠 모두 읽힌다.
DOCUMENT_BATCH_CHARS = 60_000
# 새 묶음 앞에 다시 주는 앞 묶음 끝의 글자 수. 표 밖의 소제목('A시스템')과 그 아래 글이 경계로 갈리지 않게 한다.
DOCUMENT_OVERLAP_CHARS = 2_000


def validate(topic, method, run_id, config_path, client):
    """run 의 후보마다 독립 검증기를 불러 auto_validated · rejected 로 나눠 쓴다. run 마다 한 번만 한다.

    client 는 생성과 같은 계약이다: client(model=..., reasoning_effort=..., messages=[...]) -> {"model", "text", "input_tokens", "output_tokens"}.
    """
    run_dir = storage.unvalidated_run(topic, method, run_id)
    candidates = storage._read_jsonl(run_dir / "candidates.jsonl")
    survivors = _survivors(topic, method, run_id)
    judged, info = _judge_run(run_dir, topic, method, config_path, client, candidates, survivors)
    return storage.write_validation(topic, method, run_id, judged, info)


def resume_validation(topic, method, run_id, config_path, client):
    """B · C run 의 검증이 호출 수 한도나 예산에 닿아 남긴 pending 후보만 이어서 검증한다.

    A 의 검증은 자기 개선 loop 가 맡는다. loop 의 round 와 report 가 그 검증 기록을 읽기 때문이다.
    한 run 의 후보는 같은 기준으로 판정해야 하므로 검증기 버전 · 난도 규칙 · 프롬프트 · 모델 · 단가가
    앞 기록과 다르면 호출 전에 멈춘다. 앞에서 통과한 같은 run 의 항목도 중복 검사에 넣는다.
    """
    if method == "A":
        raise ValueError("A 의 검증은 자기 개선 loop 가 이어 돕니다")
    accepted = storage.read_validated(topic, method, run_id)
    run_dir = storage.run_path(topic, method, run_id)
    last = storage._read_json(storage.validation_records(run_dir)[-1])
    if not last["pending"]:
        raise ValueError(f"이어서 검증할 pending 후보가 없습니다: {topic}/{method}/{run_id}")
    current = {"validator_version": VALIDATOR_VERSION, "difficulty_rule": DIFFICULTY_RULE,
               "prompt_sha256": storage._sha256(storage.PROMPTS / "validator.txt"),
               "run_config": generation._run_config(config_path)[0]}
    changed = sorted(key for key, value in _criteria(current).items() if _criteria(last)[key] != value)
    if changed:
        raise ValueError(f"{topic}/{method}/{run_id} 를 앞서 검증할 때와 기준이 다릅니다: {changed}")

    survivors = _survivors(topic, method, run_id)
    for item in accepted:
        for key in _keys(item):
            survivors.setdefault(key, item["candidate_id"])
    pending = set(last["pending"])
    candidates = [item for item in storage._read_jsonl(run_dir / "candidates.jsonl") if item["candidate_id"] in pending]
    judged, info = _judge_run(run_dir, topic, method, config_path, client, candidates, survivors)
    return storage.continue_validation(topic, method, run_id, judged, info)


def _criteria(record):
    """한 run 의 검증 기준: 검증기 버전 · 난도 규칙 · 프롬프트 SHA-256 과 run 설정의 모델 · 단가 (한도 · 예산은 빼고)."""
    priced = {key: value for key, value in record["run_config"].items() if key not in ("max_calls", "budget_usd")}
    return {"validator_version": record["validator_version"], "difficulty_rule": record["difficulty_rule"],
            "prompt_sha256": record["prompt_sha256"], "run_config": priced}


def _judge_run(run_dir, topic, method, config_path, client, candidates, survivors):
    """candidates 를 차례로 검증해 (판정한 항목, 검증 기록) 을 돌려준다. 한도에 닿으면 남은 후보를 pending 에 남긴다."""
    config, config_sha = generation._run_config(config_path)
    plan_id, planned, spec = _pinned_plan(run_dir, topic)
    bundles = {bundle["bundle_id"]: bundle for bundle in planned["bundles"]}
    units = {item["candidate_id"]: evidence_units(item, bundles[item["bundle_id"]]) for item in candidates}
    documents = _documents(topic, planned, bundles, candidates)
    prompt_path = storage.PROMPTS / "validator.txt"
    calls = []
    ask = _asker(client, config, prompt_path.read_text(encoding="utf-8"), calls)
    judge = _judger(client, config, (storage.PROMPTS / "judge.txt").read_text(encoding="utf-8"), calls)
    free_rejects = _static_rejections(candidates, spec, units, survivors, documents)
    rejected_ids = {item["candidate_id"] for item in free_rejects}
    to_judge = [item for item in candidates if item["candidate_id"] not in rejected_ids]

    judged, status = [], "complete"
    while len(judged) < len(to_judge):
        rest = to_judge[len(judged):]
        batch = _batch(config, calls, rest, units, documents)
        if not batch:
            needed = _calls_needed(rest[0], units[rest[0]["candidate_id"]], documents.get(rest[0]["candidate_id"]))
            status = generation.limit_reached(config, len(calls), generation._cost(config, calls), needed)
            break
        verdicts = generation.parallel(lambda item: _verdict(
            item, spec, units[item["candidate_id"]], ask, judge, survivors, documents.get(item["candidate_id"])), batch)
        judged += [_settle(item, verdict, units[item["candidate_id"]], survivors) for item, verdict in zip(batch, verdicts)]
    unjudged = to_judge[len(judged):]
    free_rejects += _static_rejections(unjudged, spec, units, survivors, documents)
    rejected_ids.update(item["candidate_id"] for item in free_rejects)
    pending = [item["candidate_id"] for item in unjudged if item["candidate_id"] not in rejected_ids]
    if not pending:
        status = "complete"
    info = {
        "run_id": run_dir.name,
        "topic": topic,
        "method": method,
        "validator_version": VALIDATOR_VERSION,
        "difficulty_rule": DIFFICULTY_RULE,
        "created_at": storage._now(),
        "code_commit": storage._code_commit(),
        "plan_id": plan_id,
        "model_requested": config["model"],
        "model_reported": sorted({call["model"] for call in calls}),
        "run_config": config,
        "run_config_sha256": config_sha,
        "prompt_file": prompt_path.relative_to(storage.PROMPTS).as_posix(),
        "prompt_sha256": storage._sha256(prompt_path),
        "judge_prompt_sha256": storage._sha256(storage.PROMPTS / "judge.txt"),
        "status": status,
        "pending": pending,
        "cost_usd": generation._cost(config, calls),
        "calls": calls,
    }
    settled = {item["candidate_id"]: item for item in [*free_rejects, *judged]}
    return [settled[item["candidate_id"]] for item in candidates if item["candidate_id"] in settled], info


def _static_rejections(candidates, spec, units, survivors, documents):
    """호출 한도가 부족해도 무료 검사로 거절할 후보는 실패 기록에 남기도록 먼저 판정한다."""
    return [_settle(item, ("rejected", reason), units[item["candidate_id"]], survivors)
            for item in candidates
            if (reason := _static_reason(item, spec, units[item["candidate_id"]], survivors,
                                         documents.get(item["candidate_id"])))]


def _documents(topic, planned, bundles, candidates):
    """candidate_id → 질문이 묻는 문서의 모든 근거 단위. 문서 전체를 보는 주제(DOCUMENT_TOPICS)만 읽는다.

    근거 어댑터 run 이 고정한 패키지와 지금 패키지가 다르면 판정과 본문이 맞지 않으므로 멈춘다.
    """
    if topic not in DOCUMENT_TOPICS:
        return {}
    run_dir = storage._child(storage.OUTPUTS / "evidence", planned["evidence_run"])
    plan._check_package(evidence.PACKAGE, storage._read_json(run_dir / "manifest.json")["pinned_sha256"])
    asked = {item["candidate_id"]: bundles[item["bundle_id"]]["doc_sha"] for item in candidates}
    found = plan.document_units(run_dir, evidence.PACKAGE, set(asked.values()))
    return {candidate_id: found[doc] for candidate_id, doc in asked.items()}


def _pinned_plan(run_dir, topic):
    """생성 run 이 쓴 계획. 생성 뒤에 계획 파일이 바뀌었으면 검증기에 줄 근거가 후보의 근거와 다르므로 멈춘다."""
    generated = storage._read_json(run_dir / "manifest.json")["generation"]
    planned, plan_sha, spec = generation._plan_for(generated["plan_id"], topic)
    if plan_sha != generated["plan_sha256"]:
        raise ValueError(f"계획 {generated['plan_id']} 가 생성 run {run_dir.name} 을 만든 뒤 바뀌었습니다. 새 run 을 만드세요")
    return generated["plan_id"], planned, spec


def release(topic, version, runs, config_path, client):
    """검증한 run 들의 auto_validated 항목 중 쓸모 판정을 통과한 것을 releases/{version}/ 로 낸다. runs 는 [(method, run_id)] 다.

    검증은 답이 근거와 맞는지만 본다. 목차 · 쪽 번호 · 표 머리글을 묻는 질문도 답은 맞아 통과하므로,
    출시 전에 판정기(prompts/screen.txt)가 RFP 를 읽는 사람이 물을 만한 질문인지 참거짓으로 정한다. 사람이 확인하는 단계는 없다.
    판정 전에 규칙 검사(rule_reason)를 한 번 더 본다. 규칙이 생기기 전에 검증한 run 도 같은 기준으로 내기 위해서다.
    빠진 항목과 이유 · 실패 코드는 출시 매니페스트에 남기고, improvement.record_screen 이 실패 기록으로 옮긴다.
    한도에 닿으면 일부만 낸 출시본을 만들지 않고 멈춘다.
    """
    items, units = _release_items(topic, runs)
    _refuse_duplicates(items)
    config, config_sha = generation._run_config(config_path)
    prompt_path = storage.PROMPTS / "screen.txt"
    # 일부러 답이 없거나 전제가 틀린 질문은 판정기가 안내 문구 · 틀린 질문으로 빼지 않게, 주제 명세의 설명을 붙인다.
    note = plan.topic_spec(topic)[0].get("screen")
    calls = []
    screen = _screener(client, config, prompt_path.read_text(encoding="utf-8") + (f"\n\n{note}" if note else ""), calls)
    ruled = {item["candidate_id"]: (False, None, rule)
             for item in items if (rule := rule_reason(item, units[item["candidate_id"]]))}
    to_screen = [item for item in items if item["candidate_id"] not in ruled]
    verdicts = []
    for start in range(0, len(to_screen), generation.WORKERS):
        batch = to_screen[start:start + generation.WORKERS]
        # 출력 오류면 한 번 더 부르므로 항목마다 두 번까지 센다.
        status = generation.limit_reached(config, len(calls), generation._cost(config, calls), 2 * len(batch))
        if status:
            raise ValueError(f"쓸모 판정이 한도({status})에 닿아 출시하지 않았습니다: {len(verdicts)}/{len(to_screen)} 판정")
        verdicts += generation.parallel(screen, batch)
    judged = {**ruled, **{item["candidate_id"]: verdict for item, verdict in zip(to_screen, verdicts)}}
    released = [transition(item, "released", "자동 검증 · 쓸모 판정 통과")
                for item in items if judged[item["candidate_id"]][0]]
    dropped = [{"candidate_id": item["candidate_id"], "method": item["method"], "run_id": item["run_id"],
                "question": item["question"],
                "code": judged[item["candidate_id"]][1], "reason": judged[item["candidate_id"]][2]}
               for item in items if not judged[item["candidate_id"]][0]]
    info = {
        "screen_prompt_sha256": storage._sha256(prompt_path),
        "screen_note": note,
        "run_config": config,
        "run_config_sha256": config_sha,
        "model_reported": sorted({call["model"] for call in calls}),
        "calls": len(calls),
        "cost_usd": generation._cost(config, calls),
        "screened": len(to_screen),
        "dropped": dropped,
    }
    return storage.write_release(topic, version, released, runs, info)


def _release_items(topic, runs):
    """출시의 규칙 검사도 검증 때와 같은 고정 계획에서 인용 근거와 표 머리글만 읽는다.

    정책을 재는 run 은 받지 않는다. 출시에서 빠진 항목은 실패 기록이 되므로, 받으면 validation · held-out 결과가 정책에 새어 든다.
    질문 앞의 문서 이름은 지금 data_list.csv 의 이름으로 다시 붙인다. 팀이 기관 이름을 고쳐도 한 출시본에서 한 문서는 한 이름이다.
    """
    items, units, docs = [], {}, {}
    for method, run_id in runs:
        run_dir = storage.run_path(topic, method, run_id)
        if measuring(run_dir):
            raise ValueError(f"{run_id} 은 자기 개선이 정책을 재려고 만든 run 이라 출시하지 않습니다")
        accepted = storage.read_validated(topic, method, run_id)
        generated = storage._read_json(run_dir / "manifest.json")["generation"]
        planned, sha = plan.load_plan(generated["plan_id"])
        if sha != generated["plan_sha256"]:
            raise ValueError(f"계획 {generated['plan_id']} 가 생성 run {run_id} 을 만든 뒤 바뀌었습니다. 새 run 을 만드세요")
        bundles = {bundle["bundle_id"]: bundle for bundle in planned["bundles"]}
        units.update((item["candidate_id"], evidence_units(item, bundles[item["bundle_id"]])) for item in accepted)
        docs.update((item["candidate_id"], bundles[item["bundle_id"]]["doc_sha"]) for item in accepted)
        items.extend(accepted)
    return _current_names(items, docs), units


def rename(topic, version, sources):
    """이미 낸 출시본들을 쓸모 판정 없이 합쳐, 질문 앞 문서 이름만 지금 data_list.csv 의 이름으로 바꿔 releases/{version}/ 로 낸다.

    팀이 기관 이름을 고친 뒤 판정을 다시 사지 않으려는 것이다. 항목 내용은 write_release 가 카탈로그 기록과 대조한다.
    """
    items, runs, golden = [], set(), {}
    for source in sources:
        released, manifest = storage.read_release(topic, source)
        items += released
        runs.update(tuple(run.split("/", 1)) for run in manifest["runs"])
        golden[source] = manifest["golden_sha256"]
    docs = {item["candidate_id"]: plan.asked_document(item) for item in items}
    items = _current_names(items, docs)
    # 이름이 같아진 뒤에 견준다. 옛 이름 · 새 이름 질문은 앞머리만 달라 이름을 바꾸기 전에는 같은 질문으로 보이지 않는다.
    _refuse_duplicates(items)
    return storage.write_release(topic, version, items, runs, {"renamed_from": golden})


def _current_names(items, docs):
    """docs 는 candidate_id → 문서 SHA. 한 출시본에서 한 문서는 지금 data_list.csv 의 한 이름으로 나간다."""
    names = plan.doc_names(evidence.PACKAGE, set(docs.values()))
    return [{**item, "question": generation.with_document(DOCUMENT_PREFIX.sub("", item["question"], count=1),
                                                          names[docs[item["candidate_id"]]])} for item in items]


def _screener(client, config, instructions, calls):
    """항목 하나를 판정기에 묻고 (쓸모 있는지, 실패 코드, 이유) 를 돌려주는 함수. 출력이 두 번 다 계약을 어기면 쓸모 없다고 본다."""
    def screen(item):
        content = json.dumps({"question": item["question"], "answer": item["answer"]}, ensure_ascii=False)
        verdict, error = _reply(client, config, instructions, content, calls, item["question"], [], _parse_useful)
        return verdict if error is None else (False, None, f"판정기 출력 오류: {error}")
    return screen


def _parse_useful(text):
    row, reason = generation._parse(text, ("useful", "code", "reason"))
    if row is None:
        return None, reason
    if not (isinstance(row["useful"], bool) and generation._is_text(row["reason"])):
        return None, "useful 은 참거짓, reason 은 비어 있지 않은 문자열이어야 합니다"
    if not (row["code"] is None if row["useful"] else row["code"] in SCREEN_CODES):
        return None, f"code 는 쓸모 있으면 null, 없으면 {', '.join(SCREEN_CODES)} 중 하나여야 합니다"
    return (row["useful"], row["code"], row["reason"]), None


def validator_input(question, units):
    """검증기가 받는 전부: 질문과 근거 단위의 라벨 · 본문. 생성기의 답 · 구조 · 대화는 넣지 않는다."""
    return {"question": question, "evidence": [{"label": unit["label"], "text": unit["text"]} for unit in units]}


def evidence_units(item, bundle):
    """후보가 인용한 근거 단위를 계획의 근거 묶음에서 찾는다. 표 행에는 그 표의 머리글 행을 붙인다 (열 이름 없이는 칸을 읽을 수 없다)."""
    cited = [unit for unit in bundle["units"] if unit["ref"] in item["evidence"]]
    headers = {unit["ref"]["element_id"]: unit for unit in bundle["units"] if plan._table_row(unit) == 0}
    return plan._with_headers(cited, headers)


def _batch(config, calls, candidates, units, documents):
    """함께 검증할 앞쪽 후보들 (많아야 WORKERS 개). 후보마다 쓸 수 있는 호출 수를 더해 한도 안에 드는 데까지 고른다."""
    batch, needed = [], 0
    for item in candidates[:generation.WORKERS]:
        needed += _calls_needed(item, units[item["candidate_id"]], documents.get(item["candidate_id"]))
        if generation.limit_reached(config, len(calls), generation._cost(config, calls), needed):
            break
        batch.append(item)
    return batch


def _settle(item, verdict, units, survivors):
    """판정을 항목에 전이로 남긴다. 함께 판정한 앞 후보와 겹치면 중복으로 거절하고, 통과한 항목은 survivors 에 더한다.

    판정은 여러 후보를 함께 돌리므로 그동안 survivors 를 바꾸지 않는다. 같은 묶음 안의 중복은 여기서 차례대로 막는다.
    """
    to, reason = verdict
    duplicate = next((survivors[key] for key in _keys(item) if key in survivors), None)
    if to == "auto_validated" and duplicate:
        to, reason = "rejected", f"중복: {duplicate} 와 같은 근거 묶음이나 질문입니다"
    proven = to == "auto_validated" and item["primary_topic"] == "multi_hop"
    level = difficulty(item["question"], units, proven)
    judged = transition(item, to, reason, validator_version=VALIDATOR_VERSION, difficulty=level)
    if to == "auto_validated":
        for key in _keys(item):
            survivors.setdefault(key, item["candidate_id"])
    return judged


def quantities(text):
    """text 에 적힌 (부호 포함 값, 단위) 쌍. 값은 쉼표를 지운 십진수이고 천 · 만 · 억은 값에 곱한다.

    1억 3천만원 처럼 수 단위로 끝난 수 뒤에 이어 쓴 수는 하나로 더한다. 그래서 1억 3천만원 = 130,000,000원 이다.
    수와 단위를 읽는 법(부호, 단위 끝)은 생성의 numeric 검사와 같다.
    """
    return {pair for pair, _, _ in facts(text)}


def facts(text):
    """text 의 (값, 단위) 쌍마다 그 대상과 글자 범위를 함께 돌려준다: [((값, 단위), 대상 낱말 집합, (시작, 끝))].

    대상은 단위가 같은 앞 값 뒤부터 이 값 앞까지의 내용 형태소다. A안은 2억원, B안은 1억원 에서 2억원 의 대상은 {A, 안},
    1억원 의 대상은 {B, 안} 이다. 단위가 다른 값끼리는 바뀔 수 없어 경계로 삼지 않는다 (1차년도 1억원 의 대상은 {1, 차, 년도}).
    글자 범위는 NFC 로 바꾼 text 에서 그 수 표현(부호부터 단위 끝까지)의 자리다.
    """
    text = unicodedata.normalize("NFC", text)
    tokens = generation.tokens(text)
    found, carry, after = [], {}, {}
    for i, token in enumerate(tokens):
        if token.tag != "SN":
            continue
        sign, unit = generation._sign(tokens, i), generation._unit(tokens, i)
        if sign is None or not unit:
            continue
        scale, end = _scale(tokens, i)
        sign, before, start = carry.pop(i, (sign, 0, i))
        amount = before + Decimal(token.form.replace(",", "")) * scale
        rest = unit[len("".join(t.form for t in tokens[i + 1:end])):]
        if not rest and end < len(tokens) and tokens[end].tag == "SN":
            carry[end] = (sign, amount, start)
            continue
        subject = {_norm(t.form) for t in tokens[after.get(rest, 0):start] if t.tag in SUBJECT_TAGS}
        after[rest] = _unit_end(tokens, end, rest)
        span = (tokens[start - 1 if sign else start].start, tokens[after[rest] - 1].end)
        found.append(((sign.replace("−", "-") + format(amount.normalize(), "f"), rest), subject, span))
    return found


def same_answer(text, independent):
    """독립 답이 text 에 들어 있는지. 수 · 단위는 값과 그 대상으로 맞추고, 수가 없는 답은 글자로 맞춘다 (공백 · 쉼표 차이만 허용).

    True · False 이고, 값은 모두 있지만 어느 값이 어느 대상의 것인지 확인하지 못하면 None 이다 (판정기가 정한다).
    그래서 A안 1억원, B안 2억원 은 A안 2억원, B안 1억원 과 값은 같아도 다른 답이고, 1억원, 2억원 은 확인하지 못한 답이다.
    """
    expected = facts(independent)
    if not expected:
        return _contains(text, independent)
    found = facts(text)
    return _combined([_attributed(fact, expected, found) for fact in expected])


def same_comparison(structure, independent):
    """비교 항목: 후보 structure 의 대상별 값과 고른 대상을 검증기의 comparison 과 맞춘다. True · False · None.

    결론(어느 대상을 골랐는지)은 글에서 읽을 수 없어 둘 다 필드로 받는다. 후보의 답 글은 생성 검사에서 structure 와 같게 묶였다.
    검증기가 comparison 을 주지 않았거나, 대상 이름이 entities 와 꼭 같지 않으면 맞출 기준이 없어 None (판정기가 정한다) 이다.
    대상마다 값은 _same_value 로 맞추고 (1억원 = 100,000,000원), 고른 대상은 이름이 같아야 한다 (둘 다 null 도 같다).
    """
    if independent is None:
        return None
    names = {_norm(entity): entity for entity in structure["entities"]}
    values = {names.get(_norm(name)): value for name, value in independent["values"].items()}
    choice = independent["choice"]
    if set(values) != set(structure["entities"]) or (choice is not None and _norm(choice) not in names):
        return None
    results = [_same_value(structure["values"][entity], values[entity]) for entity in structure["entities"]]
    chosen = names[_norm(choice)] if choice is not None else None
    return _combined([*results, chosen == structure["choice"]])


def _same_value(value, independent):
    """구조화 비교의 값 하나가 같은지: True · False · None.

    필드는 답 글이 아니라 값 하나라서, 담기(부분 문자열)가 아니라 같음을 본다. 미지원 은 지원 을 담지만 반대 뜻이다.
    글이 같으면(공백 · 쉼표 차이만) True, 수 · 단위 값이 다르면 False, 수 표기만 다르면(1억원 = 100,000,000원) True,
    그 밖(글이 다른 값)은 같은지 글자로 알 수 없어 None 이다.
    수가 여럿이면 수를 쓴 차례로 견준다. 집합으로 견주면 구축 1억원, 운영 2억원 과 구축 2억원, 운영 1억원 이 같아진다.
    수 밖의 글이 같은데 차례대로 놓인 수가 다르면 다른 값이다.
    수 밖의 글에는 수 · 단위 쌍으로 읽지 않은 수(제3회 의 3)가 그대로 남는다. 제3회 회의 1억원 과 제4회 회의 1억원 은 같지 않다.
    """
    if _norm(value) == _norm(independent):
        return True
    (mine, my_frame), (theirs, their_frame) = _layout(value), _layout(independent)
    if not (mine and theirs):
        return None
    if set(mine) != set(theirs):
        return False
    if my_frame != their_frame:
        return None
    return mine == theirs


def _layout(text):
    """(차례대로 놓인 수 · 단위 쌍, 수 밖의 글). 수 밖의 글은 쌍으로 읽은 수 표현 자리만 # 로 바꾸고 공백 · 쉼표를 지운 것이다.

    쌍으로 읽은 범위만 지운다. 숫자를 모두 지우면 쌍이 아닌 수(제3회, 2차년도)까지 사라져 다른 사실이 같아진다.
    """
    text = unicodedata.normalize("NFC", text)
    pairs, frame, last = [], [], 0
    for pair, _, (start, end) in facts(text):
        pairs.append(pair)
        frame.append(text[last:start])
        last = end
    frame.append(text[last:])
    return pairs, "#".join(_norm(part) for part in frame)


def _combined(results):
    """값마다의 결과를 하나로: 하나라도 False 면 False, 아니면 하나라도 None 이면 None, 모두 True 면 True."""
    if False in results:
        return False
    return None if None in results else True


def _attributed(fact, expected, found):
    """독립 답의 값 하나가 text 에서 같은 대상에 붙어 있는지: True · False · None (확인하지 못함).

    독립 답에 단위가 같은 값이 그 하나뿐이면 바뀔 상대가 없어 값만 본다. 여럿이면 그 값의 대상에만 있는 낱말(own)이
    text 의 대상에 모두 있어야 하고, 다른 값의 대상에 있는 낱말(foreign)이 있으면 다른 대상의 값이다.
    ponytail: 대상은 값 앞에서만 읽는다. 2억원(A안) 처럼 대상을 값 뒤에 쓴 답은 확인하지 못하거나 바뀐 답으로 읽힌다.
    """
    pair, subject, _ = fact
    subjects = [other_subject for other, other_subject, _ in found if other == pair]
    if not subjects:
        return False
    rivals = [other for other in expected if other is not fact and other[0][1] == pair[1]]
    if not rivals:
        return True
    own = subject - set().union(*(other_subject for _, other_subject, _ in rivals))
    foreign = set().union(*(other_subject for other, other_subject, _ in rivals if other != pair)) - subject
    if own and any(own <= other_subject and not other_subject & foreign for other_subject in subjects):
        return True
    return False if all(other_subject & foreign for other_subject in subjects) else None


def difficulty(question, units, proven_multi_hop):
    """DIFFICULTY_RULE 대로 easy · medium · hard 를 정한다.

    생성이 질문 앞에 붙인 문서 이름은 근거 본문에 없으므로 떼고 본다. 붙이면 모든 질문이 medium 이 된다.
    """
    if proven_multi_hop:
        return "hard"
    evidence = _norm(" ".join(unit["text"] for unit in units))
    return "easy" if all(word in evidence for word in _content_words(question)) else "medium"


def _content_words(question):
    """질문의 내용 형태소 (의문사와 앞에 붙인 문서 이름은 뺌)."""
    question = DOCUMENT_PREFIX.sub("", question, count=1)
    return [_norm(t.form) for t in generation.tokens(question) if t.tag in CONTENT_TAGS and t.form not in INTERROGATIVES]


def _verdict(item, spec, units, ask, judge, survivors, document):
    """(갈 상태, 이유). 돈이 들지 않는 검사를 먼저 하고, 그다음 독립 답을 받는다. 상태는 auto_validated 아니면 rejected 다.

    document 는 질문이 묻는 문서의 모든 근거 단위다 (DOCUMENT_TOPICS 만, 아니면 None).
    """
    reason = _static_reason(item, spec, units, survivors, document)
    if reason:
        return "rejected", reason
    if item["primary_topic"] == "unanswerable":
        return _absent_verdict(item, document, ask)
    full, error = ask(item["question"], units)
    reason = _answer_reason(item, units, full, error, judge)
    if reason:
        return "rejected", reason
    if item["primary_topic"] == "multi_hop":
        return _single_unit_verdict(item, units, full, ask, judge)
    return "auto_validated", "자동 검증 통과"


def _answer_reason(item, units, full, error, judge):
    """독립 답으로 본 거절 이유, 없으면 None. 검증기가 답하지 못했거나 근거가 서로 다르다고 하면 그 질문은 틀린 문제다."""
    if error:
        return f"검증기 출력 오류: {error}"
    if full["conflict"]:
        return "근거 충돌: 검증기가 근거끼리 같은 사실의 값이 다르다고 답했습니다"
    reason = next((reason for check in ANSWER_CHECKS if (reason := check(item, full))), None)
    if reason:
        return reason
    missing = [condition for condition in full["conditions"] if not _states(item["answer"], condition)]
    same, error = _agreed(item, units, full, missing, judge)
    if error:
        return f"검증기 출력 오류 (판정기): {error}"
    if same:
        return None
    if missing:
        return f"조건 · 예외 누락: 독립 답이 단 조건 {missing} 이 답에 없습니다"
    independent = full["comparison"] if item["primary_topic"] == "comparison" else full["answer"]
    return f"독립 답과 다릅니다: 독립 답 {independent!r}"


def _static_reason(item, spec, units, survivors, document):
    cited = [unit for unit in units if unit["ref"] in item["evidence"]]
    mismatch = generation.check_structure(item["primary_topic"], spec, item, cited)
    if mismatch:
        return f"유형 불일치: {mismatch}"
    rule = rule_reason(item, units)
    if rule:
        return rule
    check = RELATIONS.get(item["primary_topic"])
    relation = check(item, units, document) if check else None
    if relation:
        return relation
    duplicate = next((survivors[key] for key in _keys(item) if key in survivors), None)
    return f"중복: {duplicate} 와 같은 근거 묶음이나 질문입니다" if duplicate else None


def rule_reason(item, units):
    """독립 답과 맞아 검증을 통과하지만 평가에 쓸 수 없던 꼴이면 그 이유, 아니면 None. 돈이 들지 않아 검증 앞과 출시 앞에서 본다."""
    question = DOCUMENT_PREFIX.sub("", item["question"]).strip()
    return _topic_rule(item, question, units) or _scoring_rule(item, question, units)


def _scoring_rule(item, question, units):
    """값을 답하는 주제(CLAIMED)가 인용한 표가 배점표(머리글에 '배점')인데 질문이 배점 · 평가를 묻지 않으면 그 이유.

    배점표의 기준값(실적 5건 이상 | 10점)은 그 점수를 받는 조건이지 제출 · 참가 요건이 아니다.
    검증기는 그 칸의 값만 맞춰 보므로, 기준값을 요건처럼 묻는 질문('5건 이상 제출해야 하나요?')도 통과시킨다.
    조건 · 비교 주제는 뺀다. 배점표 주석의 필수 자격처럼 배점표에도 진짜 요건이 적혀 있다.
    """
    if item["primary_topic"] not in CLAIMED:
        return None
    scoring = any(plan._table_row(unit) == 0 and "배점" in re.sub(r"\s", "", unit["text"]) for unit in units)
    if scoring and not SCORING_WORDS.search(re.sub(r"\s", "", question)):
        return "배점 기준: 인용한 표가 배점표인데 질문이 배점 · 평가를 묻지 않아 기준값을 요건처럼 묻습니다"
    return None


def _topic_rule(item, question, units):
    topic = item["primary_topic"]
    if topic == "numeric" and re.fullmatch(
            r"(?:사업의\s*)?(?:값과 단위|수치와 단위|첫 번째 값)(?:은|는)?\s*(?:(?:무엇|얼마)인가)?[?？]?", question):
        return "모호한 대상: 질문이 '값과 단위' · '첫 번째 값' 처럼 대상을 이름으로 가리키지 않습니다"
    if topic == "table" and "\n" in question:
        return "끊긴 질문: 질문에 줄바꿈이 있습니다"
    if topic == "table" and any(BLANK_CELL.search(unit["text"]) for unit in units if plan._table_row(unit) is not None):
        return "빈 칸 표: 인용한 표 행이나 머리글에 빈 칸으로 시작하거나 빈 칸이 이어진 행이 있습니다"
    if topic == "condition" and "(조건:" in item["answer"]:
        return "답 덧붙임: 답에 '(조건: …)' 이 붙었습니다"
    # 생성 검사도 choice 를 요구하지만, 그 전에 검증한 run 을 출시할 때 여기서 걸러진다.
    if topic == "comparison" and item["structure"].get("choice") is None:
        return "비교 아님: 대상 하나를 고르지 않아 값을 나란히 조회할 뿐입니다"
    if topic == "multi_hop" and len({ref["chunk_id"] for ref in item["evidence"]}) < 2:
        return "multi_hop 아님: 인용한 근거가 모두 한 청크 안에 있습니다"
    if topic == "unanswerable" and EVIDENCE_LABEL.search(question):
        return "근거 지칭: 질문에 'E1' · '머리글 행' 같은 근거 라벨이 있습니다"
    return None


def _single_unit_verdict(item, units, full, ask, judge):
    """multi_hop 은 근거 단위를 하나씩만 줬을 때 어느 것으로도 독립 답이 나오지 않아야 한다 (머리글 행은 그 표 행에 붙여 준다)."""
    headers = {unit["ref"]["element_id"]: unit for unit in units if plan._table_row(unit) == 0}
    for unit in units:
        if plan._table_row(unit) == 0:
            continue
        single, error = ask(item["question"], plan._with_headers([unit], headers))
        if not error and single["answerable"]:
            same, error = _settled(item["question"], units, full["answer"], single["answer"], judge)
        if error:
            return "rejected", f"검증기 출력 오류 (근거 {unit['label']} 단독): {error}"
        if single["answerable"] and same:
            return "rejected", f"multi_hop 아님: 근거 {unit['label']} 하나로 답이 나옵니다"
    return "auto_validated", "자동 검증 통과: 근거 하나만으로는 답이 나오지 않습니다"


def _answerable(item, full):
    return None if full["answerable"] else "근거만으로 답할 수 없습니다 (독립 검증기)"


def _numeric_answer(item, full):
    """수를 답하는 주제는 독립 답에도 그 수 · 단위가 있어야 한다. false_premise 는 바로잡은 값(actual)이다."""
    claim = CLAIMED.get(item["primary_topic"])
    if claim is None:
        return None
    found = quantities(full["answer"])
    if not found:
        return f"유형 불일치: 독립 답 {full['answer']!r} 에 수 · 단위가 없습니다"
    claimed = claim(item["structure"])
    if not quantities(claimed) <= found:
        return f"독립 답과 다릅니다: 값 · 단위 {claimed!r}, 독립 답 {full['answer']!r}"
    return None


def _agreed(item, units, full, missing, judge):
    """후보 답이 독립 답과 같은지 (참거짓, 출력 오류). 비교 항목은 글 대신 대상별 값과 고른 대상을 맞춘다.

    값 · 글자로 정하지 못하면 판정기가 정한다. 독립 답이 단 조건이 답에 글자 그대로 없을 때(missing)도 판정기가 정한다.
    검증기는 질문과 상관없는 조건까지 달기도 해서, 글자로만 보면 맞는 답이 조건 누락으로 쌓인다.
    """
    if missing:
        independent = f"{full['answer']} (조건 · 예외: {'; '.join(missing)})"
        return judge(item["question"], units, independent, item["answer"])
    if item["primary_topic"] != "comparison":
        return _settled(item["question"], units, full["answer"], item["answer"], judge)
    same = same_comparison(item["structure"], full["comparison"])
    if same is None:
        independent = json.dumps(full["comparison"] or full["answer"], ensure_ascii=False)
        return judge(item["question"], units, independent, item["answer"])
    return same, None


def _settled(question, units, independent, answer, judge):
    """answer 가 독립 답과 같은지 (참거짓, 출력 오류).

    수 · 단위가 다르면 다르다. 대상을 확인하지 못한 값, 그리고 수가 없는 글 답이 글자로 다를 때는 표현만 다를 수 있어
    판정기가 정한다.
    """
    same = same_answer(answer, independent)
    if same is None or (same is False and not facts(independent)):
        return judge(question, units, independent, answer)
    return same, None


def _not_copied(item, full):
    """질문에 답이 이미 들어 있으면 복사형이다. 비교 질문이 선택지로 든 대상 이름 하나를 답하는 것은 예외다."""
    # 질문에 값이 모두 있으면 대상을 확인하지 못했어도(None) 답을 내준 것이다.
    if same_answer(item["question"], full["answer"]) is False:
        return None
    entities = item["structure"]["entities"] if item["primary_topic"] == "comparison" else []
    if _norm(full["answer"]) in {_norm(entity) for entity in entities}:
        return None
    return f"복사형: 질문에 답 {full['answer']!r} 이 들어 있습니다"


CLAIMED = {"numeric": lambda structure: structure["value"] + structure["unit"],
           "false_premise": lambda structure: structure["actual"]}
ANSWER_CHECKS = (_answerable, _numeric_answer, _not_copied)


def _absent_verdict(item, document, ask):
    """unanswerable: 대상 문서의 모든 근거 단위를 나눠 받은 검증기가 어느 묶음으로도 답하지 못해야 한다.

    핵심어 검사(_key_terms_absent)는 글자로만 본다. 핵심어를 다른 말로 쓴 근거(하자보수 · 하자담보책임)는 검증기가 찾는다.
    일부 단위만 주면 그 밖의 단위에 있는 답을 놓치므로, 없음은 문서 전체를 읽고서야 정한다.
    근거 충돌도 거절한다. 같은 사실의 값이 근거마다 다르다는 것은 속성이 문서에 있다는 뜻이다.
    묶음은 저마다 따로 읽히므로, 표 행은 그 표의 머리글과 같은 묶음에 든다 (document_batches).
    ponytail: 묶음 사이의 충돌과, 경계에서 DOCUMENT_OVERLAP_CHARS 보다 멀리 떨어진 표 밖 소제목은 보지 못한다.
    """
    for batch in document_batches(document):
        found, error = ask(item["question"], batch)
        if error:
            return "rejected", f"검증기 출력 오류: {error}"
        if found["conflict"]:
            return "rejected", "근거 충돌: 검증기가 대상 문서의 근거끼리 같은 사실의 값이 다르다고 답했습니다"
        if found["answerable"]:
            return "rejected", f"대상 문서에 있음: 검증기가 대상 문서의 근거로 답했습니다: {found['answer']!r}"
    return "auto_validated", "자동 검증 통과: 대상 문서의 모든 근거로 답이 나오지 않습니다"


def document_batches(document):
    """대상 문서의 근거 단위를 문서 차례대로 DOCUMENT_BATCH_CHARS 자 안팎씩 나눈다. 라벨(E1 …)은 문서 전체에서 이어 붙인다.

    검증기는 묶음마다 따로 읽으므로, 묶음 하나가 홀로 읽혀야 한다.
    한 표의 행은 한 묶음에 넣고, 한 묶음보다 큰 표는 행 경계에서 나누어 이어지는 묶음마다 그 표의 머리글(0행)을 다시 준다.
    새 묶음은 앞 묶음 끝 DOCUMENT_OVERLAP_CHARS 자를 다시 받는다. 다시 주는 단위는 처음의 라벨을 그대로 쓴다.
    """
    labelled = [{**unit, "label": f"E{n}"} for n, unit in enumerate(document, 1)]
    batches, size, fresh = [[]], 0, 0
    for group in _table_groups(labelled):
        headers = [unit for unit in group if _row(unit) == 0]
        if fresh and size + sum(len(unit["text"]) for unit in group) > DOCUMENT_BATCH_CHARS:
            batches.append(_tail(batches[-1]))
            size, fresh = sum(len(unit["text"]) for unit in batches[-1]), 0
        for unit in group:
            if fresh and size + len(unit["text"]) > DOCUMENT_BATCH_CHARS:
                carried = _tail(batches[-1])
                batches.append([header for header in headers if _row(unit) and header not in carried] + carried)
                size, fresh = sum(len(unit["text"]) for unit in batches[-1]), 0
            batches[-1].append(unit)
            size, fresh = size + len(unit["text"]), fresh + 1
    return batches


def _table_groups(units):
    """단위를 문서 차례대로 두되, 한 표의 행은 처음 나온 자리에 모은다. 논리 표는 요소, 원본 그리드는 stream · control 이 한 표다."""
    groups = {}
    for unit in units:
        if unit["location"]["kind"] != "table":
            key = unit["unit_id"]
        else:
            key = unit["element_id"] or unit["unit_id"].rsplit(":", 2)[0]
        groups.setdefault(key, []).append(unit)
    return list(groups.values())


def _row(unit):
    return unit["location"]["row"] if unit["location"]["kind"] == "table" else None


def _tail(batch):
    """묶음 끝에서 DOCUMENT_OVERLAP_CHARS 자 안에 드는 단위들."""
    tail, size = [], 0
    for unit in reversed(batch):
        size += len(unit["text"])
        if size > DOCUMENT_OVERLAP_CHARS:
            break
        tail.insert(0, unit)
    return tail


def _table_relation(item, units, document):
    """표 주제의 답은 인용한 표에서 행 이름과 열 이름이 만나는 칸의 값이어야 한다."""
    row, column = item["structure"]["row"], item["structure"]["column"]
    cell = _cell(units, row, column)
    if cell is None:
        return f"표 관계: 인용한 표에서 {row!r} 행과 {column!r} 열이 만나는 칸을 찾지 못했습니다"
    return None if _states(item["answer"], cell) else f"표 관계: {row} · {column} 칸은 {cell!r} 인데 답에 없습니다"


def _condition_relation(item, units, document):
    """조건 주제의 답은 그 조건 · 예외 문구를 함께 밝혀야 한다 (주제 명세 requires)."""
    condition = item["structure"]["condition"]
    return None if _states(item["answer"], condition) else f"조건 · 예외 누락: 답에 조건 {condition!r} 이 없습니다"


def _key_terms_absent(item, units, document):
    """unanswerable: 빌린 속성의 핵심어가 대상 문서의 어느 근거 단위에도 없어야 한다 (held 단위 포함, 공백 · 쉼표 무시)."""
    for unit in document:
        found = [term for term in item["structure"]["key_terms"] if _norm(term) in _norm(unit["text"])]
        if found:
            return f"대상 문서에 있음: 핵심어 {found} 가 근거 단위 {unit['unit_id']} 에 있습니다"
    return None


def _premise_absent(item, units, document):
    """false_premise: 전제한 값(stated)이 대상 문서의 어느 근거 단위에도 없어야 한다 (held 단위 포함).

    값은 quantities 로 견주므로 표기만 다른 같은 값(3천만원 · 30,000,000원)도 있는 것으로 본다. 13초 는 3초 가 아니다.
    """
    stated = quantities(item["structure"]["stated"])
    unit = next((unit for unit in document if stated <= _unit_quantities(unit["text"])), None)
    return f"전제가 문서에 있음: {item['structure']['stated']!r} 이 근거 단위 {unit['unit_id']} 에 있습니다" if unit else None


@lru_cache(maxsize=None)
def _unit_quantities(text):
    # 한 문서의 단위 수천 개를 후보마다 다시 형태소 분석하지 않는다.
    return frozenset(quantities(text))


RELATIONS = {"table": _table_relation, "condition": _condition_relation,
             "unanswerable": _key_terms_absent, "false_premise": _premise_absent}
# 질문이 묻는 문서 전체를 읽어 검사하는 주제. 근거 묶음 밖에 답이나 전제가 있으면 틀린 문제다.
DOCUMENT_TOPICS = ("unanswerable", "false_premise")


def _cell(units, row, column):
    tables = {}
    for unit in units:
        if plan._table_row(unit) is not None:
            tables.setdefault(unit["ref"]["element_id"], {})[plan._table_row(unit)] = unit["text"].split(" | ")
    for rows in tables.values():
        header = [_norm(cell) for cell in rows.get(0, [])]
        if _norm(column) not in header:
            continue
        col = header.index(_norm(column))
        for number, cells in rows.items():
            if number and _norm(row) in map(_norm, cells) and col < len(cells) and cells[col].strip():
                return cells[col]
    return None


def _states(answer, phrase):
    return _contains(answer, phrase)


def _scale(tokens, i):
    """수 바로 뒤의 수 단위(천 · 만 · 억) 형태소를 곱한 값과, 그 형태소들 다음 토큰 위치."""
    scale, end = 1, i + 1
    while end < len(tokens) and tokens[end].tag == "NR" and set(tokens[end].form) <= set(SCALES):
        if end > i + 1 and tokens[end].start != tokens[end - 1].end:
            break
        for char in tokens[end].form:
            scale *= SCALES[char]
        end += 1
    return scale, end


def _unit_end(tokens, end, unit):
    """end 부터 이어 쓴 단위 형태소들이 끝난 다음 토큰 위치."""
    written = ""
    while len(written) < len(unit):
        written, end = written + tokens[end].form, end + 1
    return end


def _keys(item):
    """같은 근거 묶음, 또는 공백 · 쉼표만 다른 같은 질문이면 중복이다."""
    return [("group", storage.evidence_group(item)), ("question", _norm(item["question"]))]


def _refuse_duplicates(items):
    """출시본 하나에는 같은 근거 묶음이나 같은 질문의 항목이 둘 들어가지 않는다. A · B · C 를 섞어 낼 때도 같다."""
    seen, duplicates = {}, []
    for item in items:
        for key in _keys(item):
            if key in seen:
                duplicates.append((seen[key], item["candidate_id"]))
            seen.setdefault(key, item["candidate_id"])
    if duplicates:
        raise ValueError(f"같은 근거 묶음이나 같은 질문의 항목이 출시본에 함께 들어 있습니다: {duplicates}")


def measuring(run_dir):
    """자기 개선 loop 가 정책을 재려고 validation · held-out 묶음으로 만든 run 인지 (출시용 후보가 아니다).

    B 의 policy 는 None 이고 C 매니페스트에는 policy 가 없다.
    """
    policy = storage._read_json(run_dir / "manifest.json")["generation"].get("policy") or {}
    return policy.get("part") in ("validation", "held_out")


def _survivors(topic, method, run_id):
    """카탈로그로 찾은 같은 주제 · 방식의 다른 run 에서 검증을 통과한 항목의 중복 키.

    거절된 항목은 넣지 않는다. 같은 근거로 다시 만든 항목(자기 개선)이 중복으로 막히지 않게 하기 위해서다.
    다른 방식(A · B · C)은 같은 계획을 받아 같은 근거 묶음을 쓰는 것이 비교의 전제라 중복으로 보지 않는다.
    정책을 재는 run 은 같은 묶음을 정책마다 다시 부르므로, 다른 run 과 서로 중복으로 보지 않는다.
    다른 run 을 중복으로 보면 앞 정책이 통과시킨 묶음에서 새 정책은 언제나 거절되어 정책끼리 견줄 수 없다.
    """
    if measuring(storage.run_path(topic, method, run_id)):
        return {}
    runs = {
        entry["run_id"] for entry in storage.read_catalog()
        if (entry["topic"], entry["method"]) == (topic, method) and entry["run_id"] != run_id
    }
    survivors = {}
    for other in sorted(runs):
        other_dir = storage.run_path(topic, method, other)
        if (other_dir / "validation.json").exists() and not measuring(other_dir):
            for item in storage.read_validated(topic, method, other):
                for key in _keys(item):
                    survivors.setdefault(key, item["candidate_id"])
    return survivors


def _asker(client, config, instructions, calls):
    """질문과 근거 단위로 검증기를 부르고 (답, None) 또는 (None, 출력 오류) 를 돌려주는 함수."""
    def ask(question, units):
        content = json.dumps(validator_input(question, units), ensure_ascii=False)
        return _reply(client, config, instructions, content, calls, question, units, _parse_verdict)
    return ask


def _judger(client, config, instructions, calls):
    """독립 답(answer_a)과 후보 답(answer_b)이 같은 답인지 판정기에 묻고 (참거짓, None) 또는 (None, 출력 오류) 를 돌려주는 함수.

    판정기는 질문 · 근거 · 두 답만 받는다. 독립 답은 후보 답을 보지 않고 나왔으므로, 판정기는 견주기만 한다.
    """
    def judge(question, units, independent, answer):
        content = json.dumps({**validator_input(question, units), "answer_a": independent, "answer_b": answer},
                             ensure_ascii=False)
        return _reply(client, config, instructions, content, calls, question, units, _parse_same)
    return judge


def _reply(client, config, instructions, content, calls, question, units, parse):
    """한 번 부르고, 출력이 계약에 맞지 않으면 한 번 더 부른다. 두 번 다 어기면 (None, 출력 오류)."""
    messages = [{"role": "system", "content": instructions}, {"role": "user", "content": content}]
    for _ in range(2):
        response = client(model=config["model"], reasoning_effort=config["reasoning_effort"], messages=messages)
        calls.append({
            "question": question,
            "labels": [unit["label"] for unit in units],
            "model": response["model"],
            "input_tokens": response["input_tokens"],
            "output_tokens": response["output_tokens"],
        })
        parsed, error = parse(response["text"])
        if error is None:
            return parsed, None
    return None, error


def _parse_same(text):
    row, reason = generation._parse(text, ("same",))
    if row is not None and not isinstance(row["same"], bool):
        return None, "same 은 참거짓이어야 합니다"
    return (row["same"], None) if row is not None else (None, reason)


def _parse_verdict(text):
    row, reason = generation._parse(text, VERDICT_FIELDS)
    if row is None:
        return None, reason
    valid = (
        isinstance(row["answerable"], bool) and isinstance(row["conflict"], bool)
        and isinstance(row["answer"], str) and (bool(row["answer"].strip()) or not row["answerable"])
        and isinstance(row["conditions"], list) and all(generation._is_text(c) for c in row["conditions"])
        and _valid_comparison(row["comparison"])
    )
    if not valid:
        return None, ("answerable · conflict 는 참거짓, 답할 수 있으면 answer 는 문자열, conditions 는 문자열 리스트, "
                      "comparison 은 null 이거나 {values: {이름: 값}, choice: 이름 또는 null} 이어야 합니다")
    return row, None


def _valid_comparison(comparison):
    if comparison is None:
        return True
    if not isinstance(comparison, dict) or set(comparison) != {"values", "choice"}:
        return False
    values, choice = comparison["values"], comparison["choice"]
    return (
        isinstance(values, dict) and len(values) >= 2
        and all(generation._is_text(name) and generation._is_text(value) for name, value in values.items())
        and (choice is None or generation._is_text(choice))
    )


def _calls_needed(item, units, document):
    """후보 하나에 드는 호출 수: 독립 답 한 번, multi_hop 이면 머리글이 아닌 근거 단위마다 한 번 더.
    unanswerable 은 독립 답 대신 대상 문서의 묶음마다 한 번이다.

    한 후보의 검증을 도중에 끊지 않도록 후보를 시작하기 전에 이만큼을 한도와 견준다.
    ponytail: 출력 오류의 다시 묻기 · 판정기 호출은 세지 않아 그만큼 한도를 넘을 수 있다. 정확히 막아야 하면 최대치로 센다.
    """
    if item["primary_topic"] == "unanswerable":
        return len(document_batches(document))
    singles = sum(plan._table_row(unit) != 0 for unit in units) if item["primary_topic"] == "multi_hop" else 0
    return 1 + singles
