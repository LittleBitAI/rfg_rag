"""③ 검증 — 평가 데이터셋 만들기: 골든 dev 분할 · 평가 질문을 같은 형식으로 모아 점검해
평가에 쓸 수 있는 항목만 남긴다.
담당: 검증.  결과(artifacts/eval_set.jsonl)를 04 생성이 답하고 05 평가가 채점한다."""
from __future__ import annotations

import re

import pandas as pd
import yaml

from ..config import ROOT, read_jsonl


# ====================================================================================================
# 평가 항목: 골든 dev 분할 · 평가 질문 → 같은 형식으로 모아 점검
# ====================================================================================================
def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _multi_hop_key_facts(row: dict) -> list[str]:
    """정답 글이 언급한 근거 표 칸 값 — 05 평가는 사실을 이어진 글자로 찾으므로, 근거 단위마다 따로 찾을 수 있는 값이어야
    근거를 모두 검색했을 때 만점이 된다. 근거 단위의 첫 칸('요구사항 분류' 같은 이름)과 질문에 이미 있는 값은 뺀다.
    표 칸 값이 하나도 없는 서술형 정답은 [] 이 되어 점검에서 빠진다."""
    units = [unit.split(" | ") for unit in re.split(r"^\[E\d+[^\]\n]*\]$", row["context"], flags=re.M)]
    values = {_squash(cell) for cells in units for cell in (cells[1:] if len(cells) > 1 else cells)}
    answer, question = _squash(row["answer"]), _squash(row["question"])
    found = [v for v in values if len(v) > 1 and v in answer and v not in question]
    return sorted(v for v in found if not any(v != other and v in other for other in found))


def _golden_key_facts(row: dict) -> list[str]:
    """주제별 structure 값 — 골든 검증이 근거와 대조한 값이라 문장형 정답보다 답에 그대로 나올 가능성이 높다"""
    topic, s = row["primary_topic"], row["structure"]
    if topic == "numeric":
        return [s["value"] + s["unit"]]
    if topic == "comparison":
        return [s["choice"]]  # 비교 질문은 모두 '어느 쪽' 을 묻는다. 값은 질문에 이미 적혀 있기도 하다
    if topic == "condition":
        return [s["condition"]]
    if topic == "multi_hop":
        return _multi_hop_key_facts(row)
    # 표 칸 안의 ' | ' 는 칸 구분선이다. 05 평가의 'A|B'(둘 중 하나)로 읽히지 않게 칸마다 따로 요구한다
    return [part.strip() for part in row["answer"].split(" | ")]


def _golden_row(row: dict) -> dict:
    """골든 릴리스 행 → 평가 질문과 같은 필드"""
    return {"id": row["candidate_id"], "question": row["question"], "reference": row["answer"],
            "key_facts": _golden_key_facts(row)}


def _eval_item(row: dict) -> dict:
    if "candidate_id" in row:
        row = _golden_row(row)
    return {"id": row["id"], "question": (row.get("question") or "").strip(), "reference": row.get("reference") or "",
            "key_facts": row.get("key_facts") or row.get("must_include") or [], "conv": row.get("conv"),
            "reset_context": bool(row.get("reset_context"))}


def load_eval_items(paths: list[str]) -> list[dict]:
    """골든 릴리스(jsonl)·평가 질문(yaml) → {id, question, reference, key_facts, conv, reset_context}"""
    items = []
    for path in paths:
        path = ROOT / path
        rows = yaml.safe_load(path.read_text(encoding="utf-8")) if path.suffix == ".yaml" else read_jsonl(path)
        items += [_eval_item(r) for r in rows]
    return items


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
