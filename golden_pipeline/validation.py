"""독립 검증과 출시. 검증기는 질문과 근거 단위만 받아 스스로 답하고, 그 답을 후보의 답과 맞춰 본다.

검증기에는 생성기의 대화 · 프롬프트 · 답 · 구조 · 자기 평가를 보내지 않는다. 독립 답과의 비교가 이 단계의 요점이기 때문이다.
검증한 항목은 run 의 accepted.jsonl (auto_validated) · review.jsonl (held, 사람 검토) · rejected.jsonl 로 가고,
출시는 auto_validated 항목과 사람이 확인한 held 항목을 releases/{version}/ 로 모은다.
"""
import json
import re
import unicodedata
from decimal import Decimal
from pathlib import Path

from golden_pipeline import generation, plan, storage
from golden_pipeline.generation import _contains, _norm
from golden_pipeline.state import transition

VALIDATOR_VERSION = "validation-2"
DIFFICULTY_RULE = (
    "difficulty-1: hard = multi_hop 이고 근거 단위를 하나씩만 준 검증기 답이 모두 독립 답에 못 미침 (근거 둘 이상 필요). "
    "easy = 그 밖에 질문의 내용 형태소(NNG · NNP · SL · SN, 의문사 제외)가 모두 근거 본문에 그대로 있음. medium = 나머지"
)
# Kiwi 는 얼마 를 일반 명사(NNG)로 단다. 의문사는 근거에 있을 수 없으므로 내용 형태소에서 뺀다.
INTERROGATIVES = ("얼마", "몇", "무엇", "어디", "언제", "누구", "어느")
VERDICT_FIELDS = ("answerable", "answer", "conditions", "conflict", "comparison")
CONFIRMATION_FIELDS = ("candidate_id", "reason")
# 값은 독립 답과 같지만 어느 값이 어느 대상의 것인지 글로 확인하지 못한 답. 맞을 수도 있어 거절하지 않고 사람에게 넘긴다.
UNATTRIBUTED = "대상 확인 불가: 값은 같지만 값마다 대상이 독립 답과 같은지 확인하지 못했습니다"
# 천 · 만 · 억(NR) 은 수에 곱하는 단위다. 5만원 과 50,000원 은 같은 값이다.
SCALES = {"십": 10, "백": 100, "천": 1000, "만": 10_000, "억": 10**8, "조": 10**12}
CONTENT_TAGS = ("NNG", "NNP", "SL", "SN")
# 값의 대상에는 의존 명사도 든다 (1차년도 의 차 · 년도).
SUBJECT_TAGS = CONTENT_TAGS + ("NNB",)


def validate(topic, method, run_id, config_path, client):
    """run 의 후보마다 독립 검증기를 불러 auto_validated · held · rejected 로 나눠 쓴다. run 마다 한 번만 한다.

    client 는 생성과 같은 계약이다: client(model=..., messages=[...]) -> {"model", "text", "input_tokens", "output_tokens"}.
    """
    config, config_sha = generation._run_config(config_path)
    run_dir = storage.unvalidated_run(topic, method, run_id)
    plan_id, planned, spec = _pinned_plan(run_dir, topic)
    bundles = {bundle["bundle_id"]: bundle for bundle in planned["bundles"]}
    prompt_path = storage.PROMPTS / "validator.txt"
    calls = []
    ask = _asker(client, config, prompt_path.read_text(encoding="utf-8"), calls)
    survivors = _survivors(topic, method, run_id)

    judged, pending, status = [], [], "complete"
    for item in storage._read_jsonl(run_dir / "candidates.jsonl"):
        units = evidence_units(item, bundles[item["bundle_id"]])
        if status == "complete":
            status = _limit(config, calls, _calls_needed(item, units))
        if status != "complete":
            pending.append(item["candidate_id"])
            continue
        judged.append(judge(item, spec, units, ask, survivors))
    info = {
        "run_id": run_id,
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
        "status": status,
        "pending": pending,
        "cost_usd": generation._cost(config, calls),
        "calls": calls,
    }
    return storage.write_validation(topic, method, run_id, judged, info)


def _pinned_plan(run_dir, topic):
    """생성 run 이 쓴 계획. 생성 뒤에 계획 파일이 바뀌었으면 검증기에 줄 근거가 후보의 근거와 다르므로 멈춘다."""
    generated = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))["generation"]
    planned, plan_sha, spec = generation._plan_for(generated["plan_id"], topic)
    if plan_sha != generated["plan_sha256"]:
        raise ValueError(f"계획 {generated['plan_id']} 가 생성 run {run_dir.name} 을 만든 뒤 바뀌었습니다. 새 run 을 만드세요")
    return generated["plan_id"], planned, spec


def release(topic, version, runs, confirmations=None):
    """검증한 run 들의 auto_validated 항목과, 사람이 확인한 held 항목을 releases/{version}/ 로 낸다.

    runs 는 [(method, run_id)], confirmations 는 사람이 쓴 JSONL 파일 경로다. 한 줄은 {"candidate_id", "reason"} 이다.
    """
    confirmed = _confirmations(confirmations)
    items = []
    for method, run_id in runs:
        accepted, held = storage.read_validated(topic, method, run_id)
        items += [transition(item, "released", "자동 검증 통과") for item in accepted]
        items += [
            transition(item, "released", f"사람 확인: {confirmed.pop(item['candidate_id'])}")
            for item in held if item["candidate_id"] in confirmed
        ]
    if confirmed:
        raise ValueError(f"고른 run 의 보류(held) 항목이 아닌 확인이 있습니다: {sorted(confirmed)}")
    _refuse_duplicates(items)
    info = {"confirmations": None}
    if confirmations:
        info["confirmations"] = {"file": Path(confirmations).name, "sha256": storage._sha256(confirmations)}
    return storage.write_release(topic, version, items, info)


def validator_input(question, units):
    """검증기가 받는 전부: 질문과 근거 단위의 라벨 · 본문. 생성기의 답 · 구조 · 대화는 넣지 않는다."""
    return {"question": question, "evidence": [{"label": unit["label"], "text": unit["text"]} for unit in units]}


def evidence_units(item, bundle):
    """후보가 인용한 근거 단위를 계획의 근거 묶음에서 찾는다. 표 행에는 그 표의 머리글 행을 붙인다 (열 이름 없이는 칸을 읽을 수 없다)."""
    cited = [unit for unit in bundle["units"] if unit["ref"] in item["evidence"]]
    headers = {unit["ref"]["element_id"]: unit for unit in bundle["units"] if plan._table_row(unit) == 0}
    return plan._with_headers(cited, headers)


def judge(item, spec, units, ask, survivors):
    """후보 하나를 검증해 전이한 항목을 돌려준다. 통과하거나 보류된 항목은 survivors 에 더해 뒤의 중복을 막는다."""
    to, reason = _verdict(item, spec, units, ask, survivors)
    proven = to == "auto_validated" and item["primary_topic"] == "multi_hop"
    level = difficulty(item["question"], units, proven)
    judged = transition(item, to, reason, validator_version=VALIDATOR_VERSION, difficulty=level)
    if to != "rejected":
        for key in _keys(item):
            survivors.setdefault(key, item["candidate_id"])
    return judged


def quantities(text):
    """text 에 적힌 (부호 포함 값, 단위) 쌍. 값은 쉼표를 지운 십진수이고 천 · 만 · 억은 값에 곱한다.

    1억 3천만원 처럼 수 단위로 끝난 수 뒤에 이어 쓴 수는 하나로 더한다. 그래서 1억 3천만원 = 130,000,000원 이다.
    수와 단위를 읽는 법(부호, 단위 끝)은 생성의 numeric 검사와 같다.
    """
    return {pair for pair, _ in facts(text)}


def facts(text):
    """text 의 (값, 단위) 쌍마다 그 대상을 함께 돌려준다: [((값, 단위), 대상 낱말 집합)].

    대상은 단위가 같은 앞 값 뒤부터 이 값 앞까지의 내용 형태소다. A안은 2억원, B안은 1억원 에서 2억원 의 대상은 {A, 안},
    1억원 의 대상은 {B, 안} 이다. 단위가 다른 값끼리는 바뀔 수 없어 경계로 삼지 않는다 (1차년도 1억원 의 대상은 {1, 차, 년도}).
    """
    tokens = generation._kiwi().tokenize(unicodedata.normalize("NFC", text))
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
        found.append(((sign.replace("−", "-") + format(amount.normalize(), "f"), rest), subject))
        after[rest] = _unit_end(tokens, end, rest)
    return found


def same_answer(text, independent):
    """독립 답이 text 에 들어 있는지. 수 · 단위는 값과 그 대상으로 맞추고, 수가 없는 답은 글자로 맞춘다 (공백 · 쉼표 차이만 허용).

    True · False 이고, 값은 모두 있지만 어느 값이 어느 대상의 것인지 확인하지 못하면 None 이다 (사람이 볼 일).
    그래서 A안 1억원, B안 2억원 은 A안 2억원, B안 1억원 과 값은 같아도 다른 답이고, 1억원, 2억원 은 확인하지 못한 답이다.
    """
    expected = facts(independent)
    if not expected:
        return _contains(_norm(text), _norm(independent))
    found = facts(text)
    return _combined([_attributed(fact, expected, found) for fact in expected])


def same_comparison(structure, independent):
    """비교 항목: 후보 structure 의 대상별 값과 고른 대상을 검증기의 comparison 과 맞춘다. True · False · None.

    결론(어느 대상을 골랐는지)은 글에서 읽을 수 없어 둘 다 필드로 받는다. 후보의 답 글은 생성 검사에서 structure 와 같게 묶였다.
    검증기가 comparison 을 주지 않았거나, 대상 이름이 entities 와 꼭 같지 않으면 맞출 기준이 없어 None (held) 이다.
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
    그 밖(글이 다른 값)은 같은지 글자로 알 수 없어 None (held) 이다.
    """
    if _norm(value) == _norm(independent):
        return True
    mine, theirs = quantities(value), quantities(independent)
    if not (mine and theirs):
        return None
    if mine != theirs:
        return False
    return True if _without_numbers(value) == _without_numbers(independent) else None


def _without_numbers(text):
    """수 표기(숫자 · 쉼표 · 소수점 · 천 · 만 · 억)와 공백을 지운 글. 1억원 과 100,000,000원 은 모두 원 이 된다."""
    return re.sub(rf"[\d.,\s{''.join(SCALES)}]", "", unicodedata.normalize("NFC", text))


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
    pair, subject = fact
    subjects = [other_subject for other, other_subject in found if other == pair]
    if not subjects:
        return False
    rivals = [other for other in expected if other is not fact and other[0][1] == pair[1]]
    if not rivals:
        return True
    own = subject - set().union(*(other_subject for _, other_subject in rivals))
    foreign = set().union(*(other_subject for other, other_subject in rivals if other != pair)) - subject
    if own and any(own <= other_subject and not other_subject & foreign for other_subject in subjects):
        return True
    return False if all(other_subject & foreign for other_subject in subjects) else None


def difficulty(question, units, proven_multi_hop):
    """DIFFICULTY_RULE 대로 easy · medium · hard 를 정한다."""
    if proven_multi_hop:
        return "hard"
    evidence = _norm(" ".join(unit["text"] for unit in units))
    tokens = generation._kiwi().tokenize(unicodedata.normalize("NFC", question))
    words = [_norm(t.form) for t in tokens if t.tag in CONTENT_TAGS and t.form not in INTERROGATIVES]
    return "easy" if all(word in evidence for word in words) else "medium"


def _verdict(item, spec, units, ask, survivors):
    """(갈 상태, 이유). 돈이 들지 않는 검사를 먼저 하고, 그다음 독립 답을 받는다."""
    reason = _static_reason(item, spec, units, survivors)
    if reason:
        return "rejected", reason
    full, error = ask(item["question"], units)
    if error:
        return "held", f"검증기 출력 오류: {error}"
    if full["conflict"]:
        return "held", "근거 충돌: 검증기가 근거끼리 같은 사실의 값이 다르다고 답했습니다"
    reason = next((reason for check in ANSWER_CHECKS if (reason := check(item, full))), None)
    if reason:
        return "rejected", reason
    if _agreement(item, full) is None:
        return "held", f"{UNATTRIBUTED}: 독립 답 {full['answer']!r}"
    if item["primary_topic"] == "multi_hop":
        return _single_unit_verdict(item, units, full, ask)
    return "auto_validated", "자동 검증 통과"


def _static_reason(item, spec, units, survivors):
    cited = [unit for unit in units if unit["ref"] in item["evidence"]]
    mismatch = generation.check_structure(item["primary_topic"], spec, item, cited)
    if mismatch:
        return f"유형 불일치: {mismatch}"
    relation = _table_relation(item, units) if item["primary_topic"] == "table" else _condition_relation(item)
    if relation:
        return relation
    duplicate = next((survivors[key] for key in _keys(item) if key in survivors), None)
    return f"중복: {duplicate} 와 같은 근거 묶음이나 질문입니다" if duplicate else None


def _single_unit_verdict(item, units, full, ask):
    """multi_hop 은 근거 단위를 하나씩만 줬을 때 어느 것으로도 독립 답이 나오지 않아야 한다 (머리글 행은 그 표 행에 붙여 준다)."""
    headers = {unit["ref"]["element_id"]: unit for unit in units if plan._table_row(unit) == 0}
    for unit in units:
        if plan._table_row(unit) == 0:
            continue
        single, error = ask(item["question"], plan._with_headers([unit], headers))
        if error:
            return "held", f"검증기 출력 오류 (근거 {unit['label']} 단독): {error}"
        same = single["answerable"] and same_answer(single["answer"], full["answer"])
        if same is None:
            return "held", f"{UNATTRIBUTED} (근거 {unit['label']} 단독): 답 {single['answer']!r}"
        if same:
            return "rejected", f"multi_hop 아님: 근거 {unit['label']} 하나로 답이 나옵니다"
    return "auto_validated", "자동 검증 통과: 근거 하나만으로는 답이 나오지 않습니다"


def _answerable(item, full):
    return None if full["answerable"] else "근거만으로 답할 수 없습니다 (독립 검증기)"


def _numeric_answer(item, full):
    if item["primary_topic"] != "numeric":
        return None
    found = quantities(full["answer"])
    if not found:
        return f"유형 불일치: 독립 답 {full['answer']!r} 에 수 · 단위가 없습니다"
    claimed = item["structure"]["value"] + item["structure"]["unit"]
    if not quantities(claimed) <= found:
        return f"독립 답과 다릅니다: 값 · 단위 {claimed!r}, 독립 답 {full['answer']!r}"
    return None


def _same_as_independent(item, full):
    # 대상을 확인하지 못한 답(None)은 여기서 거절하지 않고, 다른 거절 검사를 마친 뒤 held 로 보낸다.
    if _agreement(item, full) is False:
        independent = full["comparison"] if item["primary_topic"] == "comparison" else full["answer"]
        return f"독립 답과 다릅니다: 독립 답 {independent!r}"
    return None


def _agreement(item, full):
    """후보 답이 독립 답과 같은지: True · False · None. 비교 항목은 글 대신 대상별 값과 고른 대상을 맞춘다."""
    if item["primary_topic"] == "comparison":
        return same_comparison(item["structure"], full["comparison"])
    return same_answer(item["answer"], full["answer"])


def _conditions_stated(item, full):
    missing = [condition for condition in full["conditions"] if not _states(item["answer"], condition)]
    return f"조건 · 예외 누락: 독립 답이 단 조건 {missing} 이 답에 없습니다" if missing else None


def _not_copied(item, full):
    """질문에 답이 이미 들어 있으면 복사형이다. 비교 질문이 선택지로 든 대상 이름 하나를 답하는 것은 예외다."""
    # 질문에 값이 모두 있으면 대상을 확인하지 못했어도(None) 답을 내준 것이다.
    if same_answer(item["question"], full["answer"]) is False:
        return None
    if _norm(full["answer"]) in {_norm(entity) for entity in _entities(item) or []}:
        return None
    return f"복사형: 질문에 답 {full['answer']!r} 이 들어 있습니다"


def _entities(item):
    """비교 항목이 견주는 대상 이름 (구조의 entities). 다른 주제는 None 이다."""
    return item["structure"]["entities"] if item["primary_topic"] == "comparison" else None


ANSWER_CHECKS = (_answerable, _numeric_answer, _same_as_independent, _conditions_stated, _not_copied)


def _table_relation(item, units):
    """표 주제의 답은 인용한 표에서 행 이름과 열 이름이 만나는 칸의 값이어야 한다."""
    row, column = item["structure"]["row"], item["structure"]["column"]
    cell = _cell(units, row, column)
    if cell is None:
        return f"표 관계: 인용한 표에서 {row!r} 행과 {column!r} 열이 만나는 칸을 찾지 못했습니다"
    return None if _states(item["answer"], cell) else f"표 관계: {row} · {column} 칸은 {cell!r} 인데 답에 없습니다"


def _condition_relation(item):
    """조건 주제의 답은 그 조건 · 예외 문구를 함께 밝혀야 한다 (주제 명세 requires)."""
    condition = item["structure"]["condition"] if item["primary_topic"] == "condition" else None
    if condition is None or _states(item["answer"], condition):
        return None
    return f"조건 · 예외 누락: 답에 조건 {condition!r} 이 없습니다"


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
    return _contains(_norm(answer), _norm(phrase))


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


def _survivors(topic, method, run_id):
    """카탈로그로 찾은 같은 주제 · 방식의 다른 run 에서 검증을 통과했거나 보류된 항목의 중복 키.

    거절된 항목은 넣지 않는다. 같은 근거로 다시 만든 항목(자기 개선)이 중복으로 막히지 않게 하기 위해서다.
    다른 방식(A · B · C)은 같은 계획을 받아 같은 근거 묶음을 쓰는 것이 비교의 전제라 중복으로 보지 않는다.
    """
    runs = {
        entry["run_id"] for entry in storage.read_catalog()
        if (entry["topic"], entry["method"]) == (topic, method) and entry["run_id"] != run_id
    }
    survivors = {}
    for other in sorted(runs):
        if (storage.run_path(topic, method, other) / "validation.json").exists():
            accepted, held = storage.read_validated(topic, method, other)
            for item in accepted + held:
                for key in _keys(item):
                    survivors.setdefault(key, item["candidate_id"])
    return survivors


def _asker(client, config, instructions, calls):
    """질문과 근거 단위로 검증기를 한 번 부르고 (답, None) 또는 (None, 출력 오류) 를 돌려주는 함수."""
    def ask(question, units):
        content = json.dumps(validator_input(question, units), ensure_ascii=False)
        messages = [{"role": "system", "content": instructions}, {"role": "user", "content": content}]
        response = client(model=config["model"], messages=messages)
        calls.append({
            "question": question,
            "labels": [unit["label"] for unit in units],
            "model": response["model"],
            "input_tokens": response["input_tokens"],
            "output_tokens": response["output_tokens"],
        })
        return _parse_verdict(response["text"])
    return ask


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


def _calls_needed(item, units):
    """후보 하나에 쓸 수 있는 최대 호출 수: 독립 답 한 번, multi_hop 이면 머리글이 아닌 근거 단위마다 한 번 더."""
    singles = sum(plan._table_row(unit) != 0 for unit in units) if item["primary_topic"] == "multi_hop" else 0
    return 1 + singles


def _limit(config, calls, needed):
    """한 후보의 검증을 도중에 끊지 않도록 후보를 시작하기 전에 호출 수 한도와 예산을 본다."""
    if len(calls) + needed > config["max_calls"]:
        return "call_cap"
    # ponytail: 예산은 후보 사이에만 본다. 마지막 후보의 호출만큼 넘을 수 있다.
    if generation._cost(config, calls) >= config["budget_usd"]:
        return "budget"
    return "complete"


def _confirmations(path):
    """사람이 held 항목을 확인한 기록. 한 줄이 정확히 {candidate_id, reason} 이고 이유는 비어 있지 않아야 한다."""
    if path is None:
        return {}
    confirmed = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict) or set(row) != set(CONFIRMATION_FIELDS) or not generation._is_text(row["reason"]):
            raise ValueError(f"확인 기록 한 줄은 정확히 {CONFIRMATION_FIELDS} 이고 reason 이 있어야 합니다: {line}")
        confirmed[row["candidate_id"]] = row["reason"]
    return confirmed
