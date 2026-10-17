"""RFP 배치에서 수량 항목을 복원하고 원문 범위를 보존한다."""
import re
import unicodedata

from .quantities import SCALES, facts, subject_phrase, tokens

COMPARISON = re.compile(r"\s*(?:을|를|이|가|은|는)?\s*(이상|이하|초과|미만|이내|까지)")
DIGITS = dict(zip("영공일이삼사오육칠팔구", (0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9)))
KOREAN_MONEY = re.compile(r"(?<![\d,가-힣])(?:일금\s*|금\s*)?([영공일이삼사오육칠팔구십백천만억조]+)\s*원(?:정)?")
WON_PREFIX = re.compile(r"[₩￦]\s*([+-]?\d[\d,]*(?:\.\d+)?)(?:원+)?")


def _korean_number(text):
    total = section = digit = 0
    for char in text:
        if char in DIGITS:
            digit = DIGITS[char]
        elif SCALES[char] < 10000:
            section += (digit or 1) * SCALES[char]
            digit = 0
        else:
            total += (section + digit or 1) * SCALES[char]
            section = digit = 0
    return total + section + digit


def _read(line):
    prefixed = [(float(m[1].replace(",", "")), "원", m.start(), m.end()) for m in WON_PREFIX.finditer(line)]
    result = []
    for (value, unit), _, (start, end) in facts(line):
        if any(start < b and end > a for _, _, a, b in prefixed):
            continue
        value = float(value.replace("±", "").replace("△", "-").replace("▲", "-"))
        result.append((value, unit, start, end))
    result.extend(prefixed)
    number_starts = {t.start for t in tokens(line) if t.tag == "NR"}
    result.extend((_korean_number(m[1]), "원", m.start(), m.end())
                  for m in KOREAN_MONEY.finditer(line)
                  if m.start(1) in number_starts or m[0].startswith(("금", "일금")))
    return sorted(result, key=lambda r: r[2])


def _clean_label(label):
    label = re.sub(r"\[IMAGE[^\]]*\]", "", label).strip()
    label = re.sub(r"(?<![가-힣])(?:[가-힣]\s+)+[가-힣](?![가-힣])", lambda m: re.sub(r"\s", "", m[0]), label)
    label = re.sub(r"(?:일금|금)\s*$", "", label).split("/")[0]
    phrase = subject_phrase(label)
    if phrase and "사업" not in phrase.replace(" ", ""):
        phrase = "사업 " + phrase
    return phrase


def _field(line, start, headers):
    cells = list(re.finditer(r"[^|]+", line))
    if "|" in line:
        column = next(i for i, cell in enumerate(cells) if cell.start() <= start < cell.end())
        if column < len(headers):
            return headers[column], True
        if column and not re.search(r"\d", cells[column - 1][0]):
            return cells[column - 1][0], True
        return "", False
    prefix = line[:start]
    declared = ":" in prefix or "：" in prefix
    label = re.split(r"[:：]", prefix)[-2] if declared else prefix
    label = re.split(r"[□■○◦❍ㅇᄋ]|(?:^|\s)[가-하0-9]+\.\s*", label)[-1]
    return label, declared


def _row(chunk, line, quantity, offset, headers, context):
    value, unit, start, end = quantity
    attached = re.search(r"(이상|이하|초과|미만|이내|까지)$", unit)
    if attached:
        unit, end = unit[:attached.start()], end - len(attached[0])
    comparison = COMPARISON.match(line[end:])
    unit = "원" if unit in ("원원", "원정") else unit
    label, declared = _field(line, start, headers)
    phrase = _clean_label(label)
    illustrative = "예시" in context
    cap = (declared and unit == "원" and comparison is not None and comparison[1] in ("이하", "이내", "까지")
           and not re.match(r"\s*(?:인|의|사업|용역)", line[end + comparison.end():]))
    return {"doc_id": chunk["doc_id"], "chunk_id": chunk["chunk_id"], "value": value, "unit": unit,
            "subject": phrase.split(), "phrase": phrase, "span": [offset + start, offset + end],
            "original": line[start:end], "bound": bool(attached or comparison or line[start:start+1] == "±"),
            "declared_cap": cap, "illustrative": illustrative,
            "estimated_price": "추정가격" in phrase.replace(" ", "")}


def quantity_rows(chunks):
    rows = []
    for chunk in chunks:
        offset, headers = 0, []
        body = unicodedata.normalize("NFC", chunk["body"])
        for line in body.splitlines(keepends=True):
            quantities = _read(line)
            if "|" in line and not quantities and re.search(r"[가-힣]", line):
                headers = [cell.strip() for cell in line.strip().strip("|").split("|")]
            for quantity in quantities:
                rows.append(_row(chunk, line, quantity, offset, headers, body[max(0, offset-200):offset+len(line)]))
            if "|" not in line:
                headers = []
            offset += len(line)
    return rows
