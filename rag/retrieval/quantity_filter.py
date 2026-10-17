"""색인 시 수량 메타데이터와 결정적인 질문 조건 판별."""
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

import numpy as np

from .quantities import SCALES, SUBJECT_TAGS, facts, tokens

COMPARISON = re.compile(r"\s*(이상|이하|초과|미만|이내|까지)")
EXTREME = re.compile(r"(?:가장|최대|최소)\s*(큰|많은|높은|긴|작은|적은|낮은|짧은)")
HEADING_LINE = re.compile(r"^[\s|#]*[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩIVX\d]+[.\s|)]+[^:：]{1,60}$")


def subject_phrase(text):
    return " ".join(t.form for t in tokens(text) if t.tag in SUBJECT_TAGS and t.tag != "SN")


def substantive(text):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(text.strip()) < 40 and not re.search(r"[:：]", text):
        return False
    if re.search(r"목\s*차", text[:80]):
        return False
    if sum(bool(HEADING_LINE.fullmatch(line)) for line in lines) >= len(lines) / 2:
        return False
    return len(re.findall(r"\S+\s+\d+(?=\s|$)", text)) < 5


def content_query(remainder):
    words = subject_phrase(remainder).split()
    if "개요" in words or not set(words) - {"사업"}:
        return "사업 개요와 목적, 추진배경 및 주요 사업내용"
    return remainder


def _question_subject(question, prefix):
    phrase = subject_phrase(prefix)
    if "사업" in subject_phrase(question).split() and "사업" not in phrase.split():
        phrase = "사업 " + phrase
    return phrase.strip()


def _row_facts(line):
    for (value, unit), subject, (start, end) in facts(line):
        attached = re.search(r"(이상|이하|초과|미만|이내|까지)$", unit)
        if attached:
            unit, end = unit[:attached.start()], end - len(attached[0])
        yield value, unit, subject, start, end, bool(attached or COMPARISON.match(line[end:]))


def quantity_rows(chunks):
    rows = []
    for chunk in chunks:
        offset = 0
        for line in unicodedata.normalize("NFC", chunk["body"]).splitlines(keepends=True):
            for value, unit, subject, start, end, bound in _row_facts(line):
                phrase = " ".join(dict.fromkeys(t.form for t in tokens(line[:start]) if t.form in subject))
                rows.append({"doc_id": chunk["doc_id"], "chunk_id": chunk["chunk_id"],
                             "value": float(value.replace("±", "").replace("△", "-").replace("▲", "-")),
                             "unit": unit, "subject": sorted(subject),
                             "phrase": phrase,
                             "span": [offset + start, offset + end], "original": line[start:end],
                             "bound": bound or value.startswith("±")})
            offset += len(line)
    return rows


@dataclass(frozen=True)
class Condition:
    subject: str
    unit: str
    mode: str
    values: tuple
    remainder: str

    def accepts(self, value):
        if self.mode == "range":
            return self.values[0] <= value <= self.values[1]
        comparisons = {"이상": lambda: value >= self.values[0], "이하": lambda: value <= self.values[0],
                       "초과": lambda: value > self.values[0], "미만": lambda: value < self.values[0]}
        return comparisons[self.mode]() if self.mode in comparisons else True


def _range_parts(question):
    # 복사한 수량 파서는 범위 끝값을 제외하므로 먼저 양쪽을 나눈다.
    parts = re.split(r"[~∼〜]|부터|이상|(?:과|와)\s*(?=\d)|에서\s*(?=\d)", question, maxsplit=1)
    if len(parts) == 2:
        return parts
    found = facts(question)
    if len(found) == 2:
        start = found[1][2][0]
        return [question[:start], question[start:]]
    return None


def _range(question):
    parts = _range_parts(question)
    if not parts:
        return None
    left, right = facts(parts[0]), facts(parts[1])
    if len(left) != 1 or len(right) != 1:
        return None
    (lo, lu), _, (start, _) = left[0]
    (hi, ru), _, (_, end) = right[0]
    tail = parts[1][end:]
    if lu != ru and lu and ru:
        return None
    if re.search(r"[~∼〜]", question) or re.match(r"\s*(?:사이|까지|이하)", tail):
        return Condition(_question_subject(question, parts[0][:start]), lu or ru, "range",
                         tuple(sorted((float(lo), float(hi)))), re.sub(r"^\s*(사이|까지|이하)", "", tail))
    return None


def _join_scale_unit(question):
    parsed = tokens(question)
    gaps = [(left.end, right.start) for left, right in zip(parsed, parsed[1:])
            if left.tag == "NR" and set(left.form) <= set(SCALES) and right.tag in ("NNB", "SL", "SW", "XSN")
            and question[left.end:right.start].isspace()]
    # 배율 뒤의 의존명사·기호 단위는 잇되 '5억 사업'의 일반명사는 뒷질문으로 남긴다.
    for start, end in reversed(gaps):
        question = question[:start] + question[end:]
    return question


def parse_condition(question):
    question = unicodedata.normalize("NFC", question)
    question = _join_scale_unit(question)
    question = re.sub(rf"(?<=[{''.join(SCALES)}])인(?=\s|$)", " 인", question)
    question = re.sub(r"(이상|이하|초과|미만)", r" \1", question)
    ranged = _range(question)
    if ranged:
        return ranged
    found = facts(question)
    if len(found) == 1:
        (value, unit), _, (start, end) = found[0]
        comparison = COMPARISON.match(question[end:])
        if comparison and comparison[1] in ("이상", "이하", "초과", "미만"):
            return Condition(_question_subject(question, question[:start]), unit, comparison[1], (float(value),),
                             question[end + comparison.end():])
    extreme = EXTREME.search(question)
    if not any(t.tag == "SN" for t in tokens(question)) and extreme:
        mode = "max" if extreme[1] in ("큰", "많은", "높은", "긴") else "min"
        return Condition(_question_subject(question, question[:extreme.start()]), "", mode, (), question[extreme.end():])
    return None


def choose_values(rows, phrases, vectors, embedder, condition, cutoff):
    if not phrases:
        return [], {}
    query = np.asarray(embedder.embed_query(condition.subject))
    similarities = dict(zip(phrases, vectors @ query))
    eligible = [{**r, "similarity": float(similarities[r["phrase"]])} for r in rows
                if not r["bound"] and r["unit"] and r["phrase"] and similarities[r["phrase"]] >= cutoff]
    unit = condition.unit
    if not unit and eligible:
        unit = Counter(r["unit"] for r in eligible).most_common(1)[0][0]
    chosen = {}
    for row in eligible:
        if row["unit"] == unit and (row["doc_id"] not in chosen
                                   or row["similarity"] > chosen[row["doc_id"]]["similarity"]):
            chosen[row["doc_id"]] = row
    matched = [r for r in chosen.values() if condition.accepts(r["value"])]
    matched.sort(key=lambda r: r["value"], reverse=condition.mode not in ("min", "이하", "미만"))
    if matched and condition.mode in ("max", "min"):
        matched = [r for r in matched if r["value"] == matched[0]["value"]]
    return matched, chosen


def inspect_questions(index, questions):
    records = []
    for question in questions:
        hits, _ = index.search_with_candidates(question)
        print(question, hits.summary)
        matched = {r["doc_id"] for r in hits.values}
        for doc_id, row in hits.chosen.items():
            records.append({"question": question, "doc_id": doc_id, "value": row["value"],
                            "unit": row["unit"], "subject": row["phrase"],
                            "similarity": row["similarity"], "matched": doc_id in matched})
    return records
