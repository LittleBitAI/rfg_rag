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


def _raw_cells(context: str) -> list[list[str]]:
    """골든 근거 글 → 근거 단위([E1] …)마다 ' | ' 로 나눈 표 칸 (줄바꿈 그대로)"""
    return [unit.split(" | ") for unit in re.split(r"^\[E\d+[^\]\n]*\]$", context, flags=re.M)]


def _cells(context: str) -> list[list[str]]:
    return [[_squash(cell) for cell in cells] for cells in _raw_cells(context)]


def _cell_items(cell: str) -> list[str]:
    """칸 전체와 그 안의 글머리 항목(줄, 또는 한 줄 안의 ' o ' ' - ' 등으로 이어 적힌 항목) — 칸 하나에 사실 여럿이
    적힌 경우, 정답이 그중 일부만 옮겨도 그 항목들이 따로 사실이 된다. 쉼표로는 나누지 않는다(2,150 · 이름 속 쉼표)"""
    items = re.split(r"\n|(?:^|\s)(?:[◦○●•·∘ㅇo*\-‑–]|\d+[.)])(?=\s)", cell)
    return [_squash(cell)] + [_squash(item) for item in items]


def _field_names(rows: list[dict]) -> set[str]:
    """여러 문서(3개 이상)에서 표 행의 첫 칸으로 되풀이되는 글 — '요구사항 분류' 같은 항목 이름.
    첫 칸이 값('DAR-002')인 행도 있어 자리만으로는 가를 수 없다. 값은 한두 문서에만 나온다."""
    docs = {}
    for row in rows:
        for cells in _cells(row.get("context") or ""):
            if len(cells) > 1:
                docs.setdefault(cells[0], set()).update(ref["doc_sha"] for ref in row["evidence"])
    # 행 번호(1 · 2 · 3)도 첫 칸으로 되풀이되지만 이름이 아니다 — 배점 4 같은 값을 지운다
    return {name for name, shas in docs.items() if len(shas) >= 3 and re.search(r"[^\W\d_]", name)}


def _quantity(number: str, answer: str) -> str | None:
    """표의 맨 수(47)를 정답이 쓴 꼴로. 05 평가는 '47' 과 '47개' 를 다른 값으로 보므로 둘 다 받는다('47|47개').
    정답에서 날짜 같은 더 큰 수의 일부(2024.12.27 의 2024)뿐이면 None"""
    found = re.search(rf"(?<![\d.,]){re.escape(number)}(?![\d]|[.,]\d)([가-힣%]*)", answer)
    if not found:
        return None
    return f"{number}|{number}{found[1]}" if found[1] else number


_ENDINGS = re.compile(r"은|는|이|가|을|를|의|에|와|과|및|로|로는|으로|이며|이고|이다|하며|한다|함|등|그")


def _letters(text: str) -> int:
    return len(re.findall(r"[가-힣A-Za-z0-9]", text))


def _coverage(row: dict, facts: list[str], field_names: set[str]) -> float:
    """정답 글자 중 사실이 덮는 몫. 항목 이름 · 'X:' 꼴 이름 · 질문에 있는 낱말 · 조사뿐인 낱말은 셈에서 뺀다"""
    answer = _squash(row["answer"])
    rest = answer
    for fact in sorted({alt for f in facts for alt in f.split("|")}, key=len, reverse=True):
        rest = rest.replace(fact, " ")
    covered = _letters(answer) - _letters(rest)
    for word in sorted(field_names | set(_squash(row["question"]).split()), key=len, reverse=True):
        if len(word) > 1:
            rest = rest.replace(word, " ")
    rest = re.sub(r"[^\s:;.]+(?: [^\s:;.]+)?\s*:", " ", rest)
    left = sum(_letters(w) for w in re.findall(r"[가-힣A-Za-z0-9‧/]+", rest) if not _ENDINGS.fullmatch(w))
    return covered / (covered + left)


def _starts(text: str, part: str) -> list[int]:
    return [m.start() for m in re.finditer(re.escape(part), text)]


def _copied(value: str, answer: str, question: str) -> bool:
    """정답 속 value 가 모두 질문을 옮긴 자리인가 — 앞이나 뒤로 한 글자 늘려도 질문에 있다 (공백 무시).
    379 의 '요구사항 분류: 기능' 은 ':기능' · '기능지' 모두 질문에 없어 옮긴 자리가 아니다"""
    v, a, q = (re.sub(r"\s+", "", t) for t in (value, answer, question))
    return all((s > 0 and a[s - 1:s + len(v)] in q) or (s + len(v) < len(a) and a[s:s + len(v) + 1] in q)
               for s in _starts(a, v))


def _inside_longer(value: str, answer: str, found: list[str]) -> bool:
    """정답 속 value 가 모두 더 긴 값 안에만 나오는가 — 343 의 '데이터' 는 '데이터 설계 요구사항' 밖에도 나온다"""
    spans = [(s, s + len(other)) for other in found if value != other and value in other for s in _starts(answer, other)]
    return all(any(b <= s and s + len(value) <= e for b, e in spans) for s in _starts(answer, value))


def _asked_value_in_question(row: dict, field_names: set[str], answer: str, question: str) -> bool:
    """질문이 묻는 항목(이름의 끝 낱말이 질문에 있음)의 값이 질문에도 있고, 정답 쪽은 질문을 옮긴 자리가 아니다.
    질문이 조건으로 준 값(367 의 'SFR-021 요구사항의')인지 묻는 값(379 의 분류 '기능' — 질문의 '지도기반 기능')인지
    글만으로는 가를 수 없어, 이런 행은 사실을 만들지 않고 뺀다"""
    for cells in _raw_cells(row["context"]):
        label = _squash(cells[0])
        if len(cells) < 2 or label not in field_names or label.split()[-1] not in question:
            continue
        for value in (item for cell in cells[1:] for item in _cell_items(cell)):
            if len(value) > 1 and value in answer and value in question and not _copied(value, answer, question):
                return True
    return False


def _multi_hop_key_facts(row: dict, field_names: set[str]) -> list[str]:
    """정답 글이 언급한 근거 표 칸 값 · 칸 속 글머리 항목 — 05 평가는 사실을 이어진 글자로 찾으므로, 근거 단위마다
    따로 찾을 수 있는 값이어야 근거를 모두 검색했을 때 만점이 된다. 항목 이름과 질문에 이미 있는 값은 뺀다.
    정답을 바꿔 말해 사실이 정답의 60% 를 못 덮으면 [] — 답의 일부만으로 만점이 나지 않게 점검에서 뺀다.
    (dev 에서 덮지 못한 행은 0.54 이하, 다 덮은 행은 0.60 이상이었다)"""
    answer, question = _squash(row["answer"]), _squash(row["question"])
    if _asked_value_in_question(row, field_names, answer, question):
        return []
    # 여러 칸 행의 첫 칸은 줄로 나누지 않는다 — '세부\n내용' 처럼 이름이 줄바꿈된 칸이다
    values = {item for cells in _raw_cells(row["context"]) for i, cell in enumerate(cells)
              for item in (_cell_items(cell) if i or len(cells) == 1 else [_squash(cell)])} - field_names
    found = [v for v in values if (len(v) > 1 or v.isdigit()) and v in answer and v not in question]
    facts = [v for v in found if not _inside_longer(v, answer, found)]
    facts = [f for f in (_quantity(v, answer) if re.fullmatch(r"[\d,.]+", v) else v for v in facts) if f]
    return sorted(facts) if facts and _coverage(row, facts, field_names) >= 0.6 else []


def _golden_key_facts(row: dict, field_names: set[str]) -> list[str]:
    """주제별 structure 값 — 골든 검증이 근거와 대조한 값이라 문장형 정답보다 답에 그대로 나올 가능성이 높다"""
    topic, s = row["primary_topic"], row["structure"]
    if topic == "numeric":
        return [s["value"] + s["unit"]]
    if topic == "comparison":
        return [s["choice"]]  # 비교 질문은 모두 '어느 쪽' 을 묻는다. 값은 질문에 이미 적혀 있기도 하다
    if topic == "condition":
        return [s["condition"]]
    if topic == "multi_hop":
        return _multi_hop_key_facts(row, field_names)
    if topic == "unanswerable":
        return ["확인할 수 없"]  # 문서에 없는 내용 — 04 생성의 거절 문장 '제공된 문서에서 확인할 수 없습니다.' 를 찾는다
    if topic == "false_premise":
        return [s["actual"]]  # 질문의 틀린 전제를 바로잡은 문서의 값
    # 표 칸 안의 ' | ' 는 칸 구분선이다. 05 평가의 'A|B'(둘 중 하나)로 읽히지 않게 칸마다 따로 요구한다
    return [part.strip() for part in row["answer"].split(" | ")]


def _golden_row(row: dict, field_names: set[str]) -> dict:
    """골든 릴리스 행 → 평가 질문과 같은 필드"""
    return {"id": row["candidate_id"], "question": row["question"], "reference": row["answer"],
            "key_facts": _golden_key_facts(row, field_names), "answerable": row["primary_topic"] != "unanswerable"}


def _eval_item(row: dict, field_names: set[str]) -> dict:
    if "candidate_id" in row:
        row = _golden_row(row, field_names)
    return {"id": row["id"], "question": (row.get("question") or "").strip(), "reference": row.get("reference") or "",
            "key_facts": row.get("key_facts") or row.get("must_include") or [], "conv": row.get("conv"),
            "reset_context": bool(row.get("reset_context")), "answerable": row.get("answerable", True)}


def load_eval_items(paths: list[str]) -> list[dict]:
    """골든 릴리스(jsonl)·평가 질문(yaml) → {id, question, reference, key_facts, conv, reset_context, answerable}.
    answerable 은 답이 문서에 있는가 — 골든 unanswerable 만 False 이고, 05 평가가 그 질문에 맞지 않는 지표를 뺀다"""
    items = []
    for path in paths:
        path = ROOT / path
        rows = yaml.safe_load(path.read_text(encoding="utf-8")) if path.suffix == ".yaml" else read_jsonl(path)
        field_names = _field_names(rows)
        items += [_eval_item(r, field_names) for r in rows]
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
    → (평가 데이터셋 {id, question, reference, key_facts, reset_context, answerable}, 점검 표)"""
    kept, report, questions, convs = [], [], set(), set()
    for it in items:
        problem = _problem(it, questions, convs)
        if it["conv"]:
            convs.add(it["conv"])
        report.append({"id": it["id"], "질문": it["question"], "점검": problem or "통과"})
        if not problem:
            # 통과한 항목만 질문을 차지한다 — 정답 없는 골든 항목이 같은 질문의 온전한 yaml 항목을 막지 않게
            questions.add(it["question"])
            kept.append({k: it[k] for k in ("id", "question", "reference", "key_facts", "reset_context", "answerable")})
    return kept, pd.DataFrame(report)
