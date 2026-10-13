"""③ 검증 — 평가 데이터셋 만들기: 청크로 QA 생성 → 근거 키워드 정리 → train/valid/test 분할,
골든 셋·평가 질문 + test QA 를 점검해 평가에 쓸 수 있는 항목만 남긴다.
담당: 검증.  결과(artifacts/eval_set.jsonl)를 04 생성이 답하고 05 평가가 채점한다."""
from __future__ import annotations

import json
import random
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import openai
import pandas as pd
import yaml
from sklearn.model_selection import train_test_split

from ..config import ROOT, read_jsonl

QA_PROMPT = """다음은 공공기관 제안요청서(RFP)의 일부입니다. 이 내용만으로 답할 수 있는 실무형 질문 1개를 만드세요.
- 질문에는 어느 사업인지 알 수 있게 사업명/기관명을 자연스럽게 포함
- 정답은 원문 근거로 1~3문장
- evidence_keywords: 정답의 근거가 되는 핵심 키워드 3~6개 (원문에 '그대로' 등장하는 단어/수치)
- question_type: 사실형 | 수치형 | 절차형 | 자격요건형 | 표해석형 중 하나
JSON 으로만 출력: {{"question": "...", "answer": "...", "evidence_keywords": ["..."], "question_type": "..."}}

[문서] {title} (p.{page}, {kind})
[내용]
{body}"""


# ====================================================================================================
# QA 생성 · 근거 키워드 정리 · 분할
# ====================================================================================================
def _pick_chunks(chunks: list[dict], per_doc: int, min_chars: int, seed: int) -> list[dict]:
    """문서마다 min_chars 이상인 청크를 무작위로 per_doc 개"""
    rng = random.Random(seed)
    by_doc: dict[str, list[dict]] = {}
    for c in chunks:
        if len(c["body"]) >= min_chars:
            by_doc.setdefault(c["doc_id"], []).append(c)
    picked = []
    for doc_id in sorted(by_doc):
        cs = by_doc[doc_id][:]
        rng.shuffle(cs)
        picked += cs[:per_doc]
    return picked


def _qa_for_chunk(client: openai.OpenAI, chunk: dict, vcfg: dict, model: str) -> dict | None:
    prompt = QA_PROMPT.format(title=chunk["title"], page=chunk["page"], kind=chunk["kind"], body=chunk["body"][:3000])
    try:
        resp = client.chat.completions.create(
            model=model, messages=[{"role": "user", "content": prompt}], response_format={"type": "json_object"},
            max_completion_tokens=int(vcfg["qa_max_tokens"]), reasoning_effort=vcfg["qa_reasoning_effort"])
        qa = json.loads(resp.choices[0].message.content or "")
    except (openai.APIError, json.JSONDecodeError) as e:  # 수천 번 호출 중 한두 번의 실패로 전체를 버리지 않는다
        print(f"QA 생성 실패 {chunk['chunk_id']}: {type(e).__name__}")
        return None
    return {"id": f"qa_{chunk['chunk_id']}", "chunk_id": chunk["chunk_id"], "doc_id": chunk["doc_id"],
            "question": str(qa.get("question", "")).strip(), "reference": str(qa.get("answer", "")).strip(),
            "evidence_keywords": [k.strip() for k in qa.get("evidence_keywords", []) if isinstance(k, str) and k.strip()],
            "evidence_text": chunk["body"]}


def generate_qa(chunks: list[dict], vcfg: dict, model: str) -> list[dict]:
    """문서당 qa_per_doc 개 청크를 골라 청크마다 gpt 로 (질문, 정답, 근거 키워드) 1개"""
    picked = _pick_chunks(chunks, int(vcfg["qa_per_doc"]), int(vcfg["qa_min_chunk_chars"]), int(vcfg["seed"]))
    rows = []
    with openai.OpenAI(max_retries=3) as client, ThreadPoolExecutor(max_workers=int(vcfg["qa_workers"])) as ex:
        for i, row in enumerate(ex.map(lambda c: _qa_for_chunk(client, c, vcfg, model), picked), 1):
            if row and row["question"]:
                rows.append(row)
            if i % 50 == 0 or i == len(picked):
                print(f"QA {i}/{len(picked)}")
    return rows


def _compact(s: str) -> str:
    """키워드 매칭용: 공백/기호 제거 + 소문자"""
    return re.sub(r"[\s\W_]+", "", s).lower()


def filter_qa(rows: list[dict], vcfg: dict) -> list[dict]:
    """근거 청크에 실제로 있는 근거 키워드만 남기고(최대 max_keywords 개), min_keywords 개보다 적으면 그 QA 를 뺀다"""
    out = []
    for r in rows:
        context = _compact(r["evidence_text"])
        kws = [k for k in dict.fromkeys(r["evidence_keywords"]) if _compact(k) and _compact(k) in context]
        kws = kws[: int(vcfg["max_keywords"])]
        if len(kws) >= int(vcfg["min_keywords"]):
            out.append({**r, "evidence_keywords": kws})
    return out


def _doc_labels(rows: list[dict]) -> list[str] | None:
    """문서(doc_id)별 층화 라벨. QA 가 1개뿐인 문서는 '__rare__' 로 묶고, 그것도 1개면 가장 큰 문서에 넣는다"""
    raw = [r["doc_id"] for r in rows]
    count = Counter(raw)
    labels = [x if count[x] >= 2 else "__rare__" for x in raw]
    if Counter(labels)["__rare__"] == 1:
        top = Counter(labels).most_common(1)[0][0]
        labels = [top if x == "__rare__" else x for x in labels]
    return labels if len(set(labels)) > 1 else None


def _split(rows: list[dict], share: float, seed: int) -> tuple[list[dict], list[dict]]:
    if share <= 0 or len(rows) < 2:
        return rows, []
    try:
        return train_test_split(rows, test_size=share, random_state=seed, stratify=_doc_labels(rows))
    except ValueError:  # 층(문서) 수가 나눌 개수보다 많으면 층화 없이 나눈다
        return train_test_split(rows, test_size=share, random_state=seed)


def split_qa(rows: list[dict], vcfg: dict) -> dict[str, list[dict]]:
    """split_ratio [train, valid, test] 로 문서별 층화 분할"""
    train_r, valid_r, test_r = (float(r) / sum(vcfg["split_ratio"]) for r in vcfg["split_ratio"])
    seed = int(vcfg["seed"])
    rest, test = _split(rows, test_r, seed)
    train, valid = _split(rest, valid_r / (train_r + valid_r), seed)
    return {"train": train, "valid": valid, "test": test}


# ====================================================================================================
# 평가 항목: 골든 셋 · 평가 질문 · test QA → 같은 형식으로 모아 점검
# ====================================================================================================
def _eval_item(row: dict) -> dict:
    return {"id": row["id"], "question": (row.get("question") or "").strip(), "reference": row.get("reference") or "",
            "key_facts": row.get("key_facts") or row.get("must_include") or [], "conv": row.get("conv"),
            "reset_context": bool(row.get("reset_context"))}


def load_eval_items(paths: list[str]) -> list[dict]:
    """골든 셋(jsonl)·평가 질문(yaml) → {id, question, reference, key_facts, conv, reset_context}"""
    items = []
    for path in paths:
        path = ROOT / path
        rows = yaml.safe_load(path.read_text(encoding="utf-8")) if path.suffix == ".yaml" else read_jsonl(path)
        items += [_eval_item(r) for r in rows]
    return items


def qa_eval_items(test_qa: list[dict], max_qa: int) -> list[dict]:
    """test QA 앞 max_qa 개 → 평가 항목 (핵심 사실 = 근거 키워드)"""
    return [_eval_item({**r, "key_facts": r["evidence_keywords"]}) for r in test_qa[:max_qa]]


def _problem(item: dict, questions: set, convs: set) -> str:
    if not item["question"]:
        return "질문 없음"
    if item["question"] in questions:
        return "중복 질문"
    if item["conv"] in convs:
        return "후속 질문 — 04 생성은 질문마다 새 대화라 앞 질문의 맥락이 없음"
    if not item["reference"]:
        return "정답(reference) 없음"
    if not item["key_facts"]:
        return "핵심 사실(key_facts) 없음"
    return ""


def check_eval_items(items: list[dict]) -> tuple[list[dict], pd.DataFrame]:
    """평가에 쓸 수 없는 항목을 사유와 함께 걸러낸다
    → (평가 데이터셋 {id, question, reference, key_facts, reset_context}, 점검 표)"""
    kept, report, questions, convs = [], [], set(), set()
    for it in items:
        problem = _problem(it, questions, convs)
        if it["conv"]:
            convs.add(it["conv"])
        report.append({"id": it["id"], "질문": it["question"], "점검": problem or "통과"})
        if not problem:
            # 통과한 항목만 질문을 차지한다 — 정답 없는 골든 항목이 같은 질문의 온전한 yaml 항목을 막지 않게
            questions.add(it["question"])
            kept.append({k: it[k] for k in ("id", "question", "reference", "key_facts", "reset_context")})
    return kept, pd.DataFrame(report)
