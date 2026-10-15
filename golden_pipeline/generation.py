"""주제별 후보 생성. A(첫 생성) · B(고정 프롬프트) · C(웹 결과 가져오기)가 같은 출력 계약 검사와 저장을 거친다.

모든 출력은 candidate 상태로만 남는다. 자동 검증 통과·출시 판정은 검증 단계의 몫이다.
LLM 출력은 같은 입력에도 달라질 수 있어 결정성을 주장하지 않는다. 대신 보낸 컨텍스트, 프롬프트 해시,
API 응답이 알려 준 모델을 남겨 무엇을 넣어 무엇이 나왔는지 추적한다.
"""
import json
import re
import threading
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from string import Template

from kiwipiepy import Kiwi

from golden_pipeline import plan as plans
from golden_pipeline import storage
from golden_pipeline.schema import SchemaError, validate_item

GENERATOR_VERSION = "generation-1"
# 유료 호출 한도는 기본값을 두지 않는다. 설정 파일에 모두 적어야 run 이 시작된다.
RUN_CONFIG = ("model", "reasoning_effort", "max_calls", "budget_usd", "usd_per_million_input_tokens", "usd_per_million_output_tokens")
ROW_FIELDS = ("question", "answer", "evidence", "structure", "secondary_tags")
SIDECAR = ("model_label", "run_date", "provided_files", "tool_use", "input_limits")
UNOBSERVED = "unobserved"
# 부호는 글자로 가린다. Kiwi 는 - 를 SO, △ 를 SW, ± 를 SL 로 달리 단다.
SIGNS = ("+", "-", "−", "±", "△", "▲")
RANGES = ("~", "∼", "〜")
# 수 바로 뒤에 붙어 단위를 이루는 형태소: 천 · 만 · 억(NR), 원 · 개월 · 개년(NNB), %(SW), MB · p(SL), 포인트(NNG), 간(XSN).
UNIT_TAGS = ("NR", "NNB", "NNG", "SW", "SL", "XSN")
# 동시에 보내는 API 호출 수. 호출 하나가 수십 초라 차례로 보내면 큰 run 이 밤새 끝나지 않는다.
WORKERS = 8
_KIWI_LOCK = threading.Lock()


def generate(method, topic, plan_id, run_id, config_path, client, revision=None):
    """A 또는 B 로 계획의 근거 묶음마다 한 번 호출해 후보를 만든다.

    client(model=..., reasoning_effort=..., messages=[...]) 는 {"model", "text", "input_tokens", "output_tokens"} 를 돌려준다.
    model 은 요청한 이름이 아니라 API 응답이 알려 준 이름이어야 한다.
    revision 은 A 의 자기 개선 round 가 준다: {"parents": {묶음 id: 이전 거절 후보 id 또는 None}, "prevention", "notes", "policy"}.
    그 묶음만 다시 부르고, 프롬프트 뒤에 예방 규칙 글(prevention)을, 묶음의 컨텍스트 뒤에 그 묶음의 지난 실패(notes)를 붙이며,
    policy 를 매니페스트에 남긴다.
    """
    if method not in ("A", "B"):
        raise ValueError(f"generate 는 A · B 만 받습니다. C 는 import_c 를 씁니다: {method!r}")
    if revision is not None and method != "A":
        raise ValueError("실패 기록으로 고친 생성(revision)은 A 만 받습니다. B 는 고정 프롬프트입니다")
    config, config_sha = _run_config(config_path)
    plan, plan_sha, spec = _plan_for(plan_id, topic)
    # 저장할 수 없는 run 이면 돈을 쓰기 전에 멈춘다.
    storage.new_run_dir(topic, method, run_id)
    # A 는 주제 전용 프롬프트, B 는 모든 주제가 같은 파일 하나를 쓴다. 둘 다 같은 주제 명세를 받는다.
    prompt_path = storage.PROMPTS / "A" / f"{topic}.txt" if method == "A" else storage.PROMPTS / "B.txt"
    instructions = Template(prompt_path.read_text(encoding="utf-8")).substitute(
        topic=topic, requires=spec["requires"], structure=json.dumps(spec["structure"], ensure_ascii=False),
    )
    prompt_sha = storage._sha256(prompt_path)
    bundles, parents, notes = _bundles(plan, topic), {}, {}
    if revision is not None:
        instructions += revision["prevention"]
        parents, notes = revision["parents"], revision["notes"]
        bundles = [bundle for bundle in bundles if bundle["bundle_id"] in parents]
    calls, outputs, status = _call_all(client, config, instructions, bundles, notes)

    run = {"run_id": run_id, "method": method, "primary_topic": topic, "prompt_version": prompt_sha}
    results = []
    for n, (bundle, text) in enumerate(outputs, 1):
        row, reason = _parse(text, ROW_FIELDS)
        candidate_id = f"{topic}-{method}-{run_id}-{n:04d}"
        parent = parents.get(bundle["bundle_id"])
        results.append(_candidate(run, candidate_id, row, bundle, spec, parent) if row else (None, reason))
    sent = [bundle for bundle, _ in outputs]
    info = {
        **_plan_info(plan_id, plan, plan_sha, topic, sent),
        "model_requested": config["model"],
        "model_reported": sorted({call["model"] for call in calls}),
        "run_config": config,
        "run_config_sha256": config_sha,
        "prompt_file": prompt_path.relative_to(storage.PROMPTS).as_posix(),
        "prompt_sha256": prompt_sha,
        "input_limits": {"max_context_chars": plan["max_context_chars"]},
        "policy": revision["policy"] if revision else None,
        "status": status,
        "cost_usd": _cost(config, calls),
        "calls": calls,
    }
    return _write(topic, method, run_id, outputs, results, info)


def import_c(topic, plan_id, run_id, exports, sidecar_path):
    """C: 사람이 웹 환경에서 받아 내보낸 JSONL 파일과 관측 기록(sidecar)을 같은 계약으로 검사해 들인다.

    웹 환경은 모델 이름·토큰·비용을 보장해 알려 주지 않으므로, sidecar 에 없는 값은 추정하지 않고 unobserved 로 둔다.
    """
    plan, plan_sha, spec = _plan_for(plan_id, topic)
    observed = _sidecar(sidecar_path)
    bundles = {bundle["bundle_id"]: bundle for bundle in _bundles(plan, topic)}
    lines = [line for path in exports for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]

    # C 가 웹에서 쓴 프롬프트는 관측할 수 없어 prompt_version 도 unobserved 다.
    run = {"run_id": run_id, "method": "C", "primary_topic": topic, "prompt_version": UNOBSERVED}
    inputs, results = [], []
    for n, line in enumerate(lines, 1):
        row, reason = _parse(line, ("bundle_id", *ROW_FIELDS))
        bundle = bundles.get(row["bundle_id"]) if row and isinstance(row["bundle_id"], str) else None
        if row and bundle is None:
            reason = f"계획에 없는 {topic} 근거 묶음입니다: {row['bundle_id']!r}"
        inputs.append((bundle, line))
        candidate_id = f"{topic}-C-{run_id}-{n:04d}"
        results.append(_candidate(run, candidate_id, row, bundle, spec) if bundle else (None, reason))
    used = list({bundle["bundle_id"]: bundle for bundle, _ in inputs if bundle}.values())
    info = {
        **_plan_info(plan_id, plan, plan_sha, topic, used),
        # API 모델 이름 필드를 두지 않는다. 웹 화면에 보인 표시만 관측값으로 남긴다.
        "model": {"observed_label": observed["model_label"]},
        "observed": observed,
        "sidecar_sha256": storage._sha256(sidecar_path),
        "exports": [{"file": Path(path).name, "sha256": storage._sha256(path)} for path in exports],
        "input_limits": observed["input_limits"],
    }
    return _write(topic, "C", run_id, inputs, results, info)


def check_structure(topic, spec, row, cited):
    """주제가 요구하는 구조가 출력에 있는지 본다. 어기면 이유를, 지키면 None 을 돌려준다."""
    structure = row["structure"]
    if set(structure) != set(spec["structure"]):
        # 필드가 없는 주제(multi_hop)에 "필드는 [] 여야" 라고 하면 생성기가 고치지 못하고 필드를 채워 거듭 거절됐다.
        return f"structure 필드는 {sorted(spec['structure'])} 여야 합니다" if spec["structure"] else "structure 는 빈 객체 {} 여야 합니다"
    texts = [unit["text"] for unit in cited]
    return CHECKS[topic](structure, row["answer"], cited, texts)


def _numeric(structure, answer, cited, texts):
    value, unit = structure["value"], structure["unit"]
    if not (_is_text(value) and _is_text(unit) and re.search(r"\d", value)):
        return "숫자가 든 값과 단위가 있어야 합니다"
    pair = (_norm(value), _norm(unit))
    if pair not in _pairs(answer):
        return f"답에 값과 단위({value}{unit})가 없습니다"
    if not any(pair in _pairs(source["text"]) for source in cited):
        return f"값과 단위({value}{unit})가 근거에 없습니다"
    return None


def _pairs(text):
    """text 에 적힌 (부호 포함 수, 단위) 쌍들. 형태소 분석으로 수(SN)와 그 앞뒤를 읽는다.

    한국어는 단위가 수에, 조사가 단위에 붙어 써서 (12개월이다) 글자 종류로는 단위 끝을 가를 수 없다.
    형태소 품사로 가르면 조사 · 어미 · 문장부호에서 단위가 끝나고, 붙어 이어지는 단위 형태소는 끝까지 한 단위가 된다.
    """
    found = tokens(text)
    pairs = set()
    for i, token in enumerate(found):
        if token.tag != "SN":
            continue
        sign, unit = _sign(found, i), _unit(found, i)
        if sign is not None and unit:
            pairs.add((_norm(sign + token.form), unit))
    return pairs


def _sign(tokens, i):
    """수 앞의 부호. 띄어 쓴 부호도 값에 든다 (- 130,000,000원).

    앞말에 붙은 - 는 범위 표시(2024년-2025년)이고, 범위 표시 · 수 · 쉼표 · 접두사(제3회) 바로 뒤의 수는
    더 큰 표현의 일부라 쌍이 아니다. 그때는 None 을 돌려준다.
    """
    if i == 0:
        return ""
    before = tokens[i - 1]
    if before.form in SIGNS:
        is_range = i >= 2 and tokens[i - 2].end == before.start
        return None if is_range else before.form
    attached = before.end == tokens[i].start
    if before.form in RANGES or (attached and before.tag in ("SN", "SP", "XPN")):
        return None
    return ""


def _unit(tokens, i):
    """수 뒤의 단위. 붙어 이어지는 단위 형태소를 끝까지 잇는다 (가장 긴 일치, 더 짧은 단위로 물러나지 않음).

    그래서 12개월간 은 개월간, 5%p 는 %p, 5MB/s 는 MB/s 로 읽혀 개 · % · MB 와 같지 않다.
    단위의 첫 형태소만 수와 띄어 쓸 수 있다 (6 개월).
    """
    unit, end = "", tokens[i].end
    for token in tokens[i + 1:]:
        joins = token.tag in UNIT_TAGS or (bool(unit) and token.form == "/")
        if not joins or (unit and token.start != end):
            break
        unit, end = unit + token.form, token.end
    return unit


@lru_cache(maxsize=1)
def _kiwi():
    # 모델을 읽는 데 시간이 들어 한 번만 만든다.
    return Kiwi()


def tokens(text):
    """형태소 분석. 검증을 여러 스레드로 돌리므로 Kiwi 하나를 잠가 차례로 쓴다."""
    with _KIWI_LOCK:
        return _kiwi().tokenize(unicodedata.normalize("NFC", text))


def _table(structure, answer, cited, texts):
    if not any(unit["ref"]["location"]["kind"] == "table" for unit in cited):
        return "표 행 근거가 없습니다"
    return _quoted([structure["row"], structure["column"]], texts, "행·열 이름")


def _condition(structure, answer, cited, texts):
    return _quoted([structure["condition"]], texts, "조건·예외 문구")


def _comparison(structure, answer, cited, texts):
    """대상마다 값과 고른 대상을 structure 에 두고, 답은 그 structure 로 만든 글이어야 한다.

    결론(어느 대상을 골랐는지)을 글에서 읽을 수 없으므로, 검증은 structure 를 견주고 답 글은 structure 와 같게 묶는다.
    """
    entities, values, choice = structure["entities"], structure["values"], structure["choice"]
    # 이름의 형을 먼저 본다. 문자열이 아닌 이름(객체)으로 집합을 만들면 거절 대신 예외로 run 전체가 멈춘다.
    if not isinstance(entities, list) or not all(_is_text(entity) for entity in entities):
        return "entities 는 비어 있지 않은 문자열 리스트여야 합니다"
    if len(set(entities)) < 2:
        return "견주는 대상이 둘 이상이어야 합니다"
    if not isinstance(values, dict) or set(values) != set(entities):
        return "values 는 entities 마다 값을 담은 객체여야 합니다"
    names = {_norm(entity) for entity in entities}
    if any(_norm(str(value)) in names for value in values.values()):
        return "대상의 값이 대상 이름이라 견줄 값이 없습니다"
    if choice not in entities:
        return "choice 는 entities 중 하나여야 합니다 (고르지 않는 비교는 나란한 조회다)"
    reason = _quoted(entities, texts, "비교 대상") or _quoted(list(values.values()), texts, "대상의 값")
    if reason:
        return reason
    expected = comparison_answer(structure)
    return None if _norm(answer) == _norm(expected) else f"답은 structure 로 만든 글 {expected!r} 이어야 합니다"


def comparison_answer(structure):
    """비교 structure 로 만든 답 글: A안 1억원, B안 2억원. 답: B안"""
    text = ", ".join(f"{entity} {structure['values'][entity]}" for entity in structure["entities"])
    return f"{text}. 답: {structure['choice']}"


def _multi_hop(structure, answer, cited, texts):
    return None if len(cited) >= 2 else "근거 단위가 둘 이상이어야 합니다"


CHECKS = {
    "numeric": _numeric, "table": _table, "condition": _condition,
    "comparison": _comparison, "multi_hop": _multi_hop,
}


def _quoted(values, texts, label):
    """구조의 값은 근거에 적힌 그대로여야 한다 (공백·쉼표 차이만 허용)."""
    if not all(_is_text(value) for value in values):
        return f"{label}은 비어 있지 않은 문자열이어야 합니다"
    missing = [value for value in values if not any(_contains(text, value) for text in texts)]
    return f"{label}이 근거에 없습니다: {missing}" if missing else None


def _contains(text, quote):
    """quote 가 text 에 있는지 본다 (공백 · 쉼표 차이만 허용). 숫자로 시작하거나 끝나는 quote 는 더 긴 수의 일부와 맞추지 않는다.

    쉼표를 지우고 견주므로 그냥 부분 문자열이면 30,000,000원 이 130,000,000원 안에서, 2개월 이 12개월 안에서 맞는다.
    수의 경계는 공백을 지우기 전의 글에서 본다. 띄어 쓴 두 수(목차의 13\\n 1.)를 지운 뒤 보면 131 로 이어져 맞지 않는다.
    다만 줄바꿈 등으로 쉼표 앞뒤가 벌어진 세 자리 묶음(1,\\n300,000)은 먼저 붙여 한 수로 본다. 그러지 않으면 300,000 이 그 안에서 맞는다.
    """
    quote = _norm(quote)
    head = r"(?<!\d)(?<!\d,)(?<!\d\.)" if quote[:1].isdigit() else ""
    tail = r"(?!,?\.?\d)" if quote[-1:].isdigit() else ""
    body = r"[\s,]*".join(map(re.escape, quote))
    text = re.sub(r"(?<=\d)\s*,\s*(?=\d{3}(?!\d))", ",", unicodedata.normalize("NFC", text))
    return re.search(head + body + tail, text) is not None


def _candidate(run, candidate_id, row, bundle, spec, parent=None):
    """출력 한 행을 candidate 항목으로 만든다. 어기면 (None, 이유) 를 돌려준다.

    run 은 run 전체에 같은 값 {run_id, method, primary_topic, prompt_version} 이다.
    parent 는 같은 묶음에서 거절된 이전 후보 id 다. 다시 만든 후보는 새 id 를 받고, 원래 후보는 그 run 에 그대로 남는다.
    """
    units = {unit["label"]: unit for unit in bundle["units"]}
    labels = row["evidence"]
    if not (isinstance(labels, list) and labels and all(isinstance(label, str) for label in labels)
            and len(set(labels)) == len(labels) and set(labels) <= set(units)):
        return None, f"evidence 는 이 묶음의 서로 다른 근거 라벨 {sorted(units)} 이어야 합니다: {labels!r}"
    # 열 이름은 표의 머리글 행에 있다. 표 행만 인용해도 그 머리글 행을 근거에 넣는다 (계획이 묶음에 늘 넣어 둔다).
    headers = {unit["ref"]["element_id"]: unit for unit in bundle["units"] if plans._table_row(unit) == 0}
    cited = plans._with_headers([units[label] for label in labels], headers)
    tags = row["secondary_tags"]
    # 주 주제를 보조 태그에 다시 적은 것은 틀린 사실이 아니라 겹친 표시라, 거절하지 않고 뺀다.
    if isinstance(tags, list):
        tags = [tag for tag in tags if tag != run["primary_topic"]]
    question = row["question"]
    if _is_text(question):
        question = with_document(question, bundle["doc"])
    item = {
        **run,
        "candidate_id": candidate_id,
        "parent_candidate_id": parent,
        "secondary_tags": tags,
        "question": question,
        "answer": row["answer"],
        "evidence": [unit["ref"] for unit in cited],
        "bundle_id": bundle["bundle_id"],
        "context": bundle["context"],
        "structure": row["structure"],
        "generator_version": GENERATOR_VERSION,
        "validator_version": None,
        "difficulty": None,
        "state": "candidate",
        "state_history": [],
    }
    try:
        validate_item(item)
    except SchemaError as error:
        return None, f"스키마: {error}"
    mismatch = check_structure(run["primary_topic"], spec, row, cited)
    return (None, f"유형 불일치: {mismatch}") if mismatch else (item, None)


def with_document(question, doc):
    """질문 앞에 문서를 밝힌다. 문서 98개를 함께 찾는 평가에서 문서를 밝히지 않은 질문은 답이 하나로 정해지지 않는다.

    생성기에게 쓰게 하면 이름을 바꿔 쓰거나 글자를 깨뜨려, 계획에 적힌 이름을 그대로 붙인다.
    """
    return f"{doc['agency']}의 「{doc['title']}」 사업에서 {question}"


def _write(topic, method, run_id, inputs, results, info):
    """항목이 된 행은 candidates.jsonl 로, 못 된 행은 원문과 이유를 rejected.jsonl 로 보낸다.

    카탈로그에서 다른 주제가 가진 근거 묶음을 인용한 행도 거절 행으로 남긴다. 예외로 멈추면 이미 낸 호출 기록이 사라진다.
    """
    owners = {}
    for entry in storage.read_catalog():
        owners.setdefault(entry["evidence_group"], entry["topic"])
    items, rejects = [], []
    for (bundle, raw), (item, reason) in zip(inputs, results):
        owner = owners.get(storage.evidence_group(item), topic) if item else topic
        if owner != topic:
            item, reason = None, f"근거 묶음이 이미 {owner} 주제 소유입니다"
        if item is None:
            rejects.append({"bundle_id": bundle["bundle_id"] if bundle else None, "reason": reason, "raw": raw})
        else:
            items.append(item)
    return storage.write_run(topic, method, run_id, items, rejects, info)


def _call_all(client, config, instructions, bundles, notes):
    """호출 수 한도와 예산 안에서 묶음마다 한 번 호출한다. 한도에 닿으면 멈추고 그 이유를 status 로 남긴다.

    WORKERS 개씩 함께 보내고 한도는 그 사이에서 본다. 출력은 묶음 차례대로 남는다.
    """
    calls, outputs = [], []
    while len(outputs) < len(bundles):
        stop = limit_reached(config, len(calls), _cost(config, calls))
        if stop:
            return calls, outputs, stop
        size = min(WORKERS, config["max_calls"] - len(calls))
        batch = bundles[len(outputs):len(outputs) + size]
        for bundle, response in zip(batch, parallel(lambda b: _ask(client, config, instructions, b, notes), batch)):
            calls.append({
                "bundle_id": bundle["bundle_id"],
                "model": response["model"],
                "input_tokens": response["input_tokens"],
                "output_tokens": response["output_tokens"],
            })
            outputs.append((bundle, response["text"]))
    return calls, outputs, "complete"


def _ask(client, config, instructions, bundle, notes):
    content = bundle["context"] + notes.get(bundle["bundle_id"], "")
    messages = [{"role": "system", "content": instructions}, {"role": "user", "content": content}]
    return client(model=config["model"], reasoning_effort=config["reasoning_effort"], messages=messages)


def parallel(work, items):
    """items 마다 work 를 WORKERS 개까지 함께 돌려, 결과를 items 차례대로 돌려준다."""
    with ThreadPoolExecutor(max(1, min(WORKERS, len(items)))) as pool:
        return list(pool.map(work, items))


def limit_reached(config, calls, cost, needed=1):
    """호출 needed 번을 더 하면 호출 수 한도를 넘거나 이미 예산에 닿았으면 call_cap · budget, 아니면 None.

    생성 · 검증 · 자기 개선 loop 가 모두 이 규칙 하나로 멈춘다.
    ponytail: 예산은 호출 사이에만 본다. 마지막 호출(검증은 마지막 후보의 호출)만큼 넘을 수 있고, 호출 전 추정이 필요하면 그때 넣는다.
    """
    if calls + needed > config["max_calls"]:
        return "call_cap"
    return "budget" if cost >= config["budget_usd"] else None


def _cost(config, calls):
    tokens_in = sum(call["input_tokens"] for call in calls)
    tokens_out = sum(call["output_tokens"] for call in calls)
    usd = tokens_in * config["usd_per_million_input_tokens"] + tokens_out * config["usd_per_million_output_tokens"]
    return usd / 1_000_000


def _run_config(path):
    """모델·추론 강도·호출 수 한도·예산·단가가 모두 적힌 설정만 받는다. 빠진 값을 기본값으로 채우지 않는다."""
    config = storage._read_json(path)
    if not isinstance(config, dict) or set(config) != set(RUN_CONFIG):
        raise ValueError(f"run 설정은 정확히 {RUN_CONFIG} 를 가져야 합니다: {path}")
    numbers = [config[name] for name in RUN_CONFIG[2:]]
    texts = [config["model"], config["reasoning_effort"]]
    if not all(map(_is_text, texts)) or not all(_is_number(n) and n >= 0 for n in numbers):
        raise ValueError(f"model · reasoning_effort 는 문자열, 한도·단가는 0 이상의 수여야 합니다: {path}")
    if not isinstance(config["max_calls"], int) or config["max_calls"] < 1 or config["budget_usd"] <= 0:
        raise ValueError(f"max_calls 는 1 이상의 정수, budget_usd 는 0 보다 커야 합니다: {path}")
    return config, storage._sha256(path)


def _plan_for(plan_id, topic):
    plan, plan_sha = plans.load_plan(plan_id)
    spec, spec_sha = plans.topic_spec(topic)
    if plan["topic_specs"].get(topic) != spec_sha:
        raise ValueError(f"{topic} 주제 명세가 계획 {plan_id} 를 만들 때와 다릅니다. 새 계획을 만드세요")
    return plan, plan_sha, spec


def _bundles(plan, topic):
    return [bundle for bundle in plan["bundles"] if bundle["topic"] == topic]


def _plan_info(plan_id, plan, plan_sha, topic, bundles):
    return {
        "plan_id": plan_id,
        "plan_sha256": plan_sha,
        "evidence_run": plan["evidence_run"],
        "v11_manifest_sha256": plan["v11_manifest_sha256"],
        "topic_spec_sha256": plan["topic_specs"][topic],
        "bundle_ids": [bundle["bundle_id"] for bundle in bundles],
        "document_scope": sorted({bundle["doc_sha"] for bundle in bundles}),
    }


def _sidecar(path):
    """C 의 관측 기록. 정해진 필드만 받고, 비어 있거나 없는 값은 unobserved 로 둔다."""
    data = storage._read_json(path)
    if not isinstance(data, dict) or set(data) - set(SIDECAR):
        raise ValueError(f"sidecar 는 {SIDECAR} 중의 필드만 가진 객체여야 합니다: {path}")
    return {name: data[name] if data.get(name) not in (None, "", [], {}) else UNOBSERVED for name in SIDECAR}


def _parse(text, fields):
    try:
        row = json.loads(text)
    except json.JSONDecodeError as error:
        return None, f"JSON 이 아닙니다: {error}"
    if not isinstance(row, dict) or set(row) != set(fields):
        return None, f"출력 필드는 정확히 {fields} 여야 합니다"
    return row, None


def _norm(text):
    return re.sub(r"[\s,]", "", unicodedata.normalize("NFC", text))


def _is_text(value):
    return isinstance(value, str) and bool(value.strip())


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)
