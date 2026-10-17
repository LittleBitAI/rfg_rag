"""Recover quantity fields from RFP layout while preserving source spans."""
import re
import unicodedata

from .quantities import SCALES, facts, subject_phrase, tokens

COMPARISON = re.compile(r"\s*(?:을|를|이|가|은|는)?\s*(이상|이하|초과|미만|이내|까지)")
DIGITS = dict(zip("영공일이삼사오육칠팔구", (0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9)))
KOREAN_MONEY = re.compile(r"(?<![\d,가-힣])(?:일금\s*|금\s*)?([영공일이삼사오육칠팔구십백천만억조]+)\s*원(?:정)?")
WON_PREFIX = re.compile(r"[₩￦]\s*([+-]?\d[\d,]*(?:\.\d+)?)(?:원+)?")
UNIT_DECLARATION = re.compile(r"\((?:\s*단위\s*[:：]\s*)?([^()|]+)\)|단위\s*[:：]\s*([^()|\n]+)")
NUMBER_CELL = re.compile(r"\s*([+-]?\d[\d,]*(?:\.\d+)?)\s*(?:이상|이하|초과|미만|이내|까지)?\s*")


def _declared_unit(text, offset=0):
    for match in UNIT_DECLARATION.finditer(text):
        group = 1 if match[1] is not None else 2
        original = match[group].strip()
        parsed = tokens(original)
        # Bare parentheses also hold prose such as '(부가세포함)'.
        if "단위" not in match[0] and len(parsed) > 1 and any(t.tag == "NNG" for t in parsed):
            continue
        found = facts("1" + original)
        if len(found) != 1 or found[0][2] != (0, len(original) + 1) or not found[0][0][1]:
            continue
        (scale, unit), _, _ = found[0]
        start = offset + match.start(group) + len(match[group]) - len(match[group].lstrip())
        return {"scale": float(scale), "unit": unit, "original": original, "span": [start, start + len(original)]}
    return None


def _cells(line):
    start, end = len(line) - len(line.lstrip()), len(line.rstrip())
    start += line[start:start + 1] == "|"
    end -= line[end - 1:end] == "|"
    # Exterior pipes are syntax; interior empty cells still occupy a column.
    return list(re.compile(r"[^|]+|(?<=\|)(?=\|)").finditer(line, start, end))


def _cell_column(column, count, declarations):
    if count < len(declarations):
        remaining = [i for i in range(column, len(declarations)) if declarations[i] is not None]
        return remaining[0] if len(remaining) == 1 else None
    return column


def _implicit_cells(line, headers, declarations, default):
    result = []
    cells = _cells(line)
    for column, cell in enumerate(cells):
        target = _cell_column(column, len(cells), declarations)
        declaration = declarations[target] if target is not None and target < len(declarations) else None
        declaration = declaration or default
        number = NUMBER_CELL.fullmatch(cell[0])
        if declaration is None or number is None:
            continue
        field = headers[target] if target is not None and target < len(headers) else ""
        if column and _field_label(cells[0][0]):
            field += " " + cells[0][0].strip()
        declaration = {**declaration, "field": field}
        start, end = cell.start() + number.start(1), cell.start() + number.end(1)
        quantity = (float(number[1].replace(",", "")) * declaration["scale"], declaration["unit"], start, end)
        result.append((quantity, declaration))
    return result


def _field_label(label):
    parsed = tokens(label)
    return any(t.tag in ("NNG", "NNP", "SL") for t in parsed) and not any(
        t.tag == "SN" or t.tag.startswith(("V", "E")) for t in parsed)


def _parallel_parts(line):
    parts = re.split(r"[:：]", line, maxsplit=1)
    if len(parts) != 2 or "/" not in parts[0] or "|" in parts[0]:
        return []
    labels = parts[0].split("/")
    labels[0] = re.sub(r"^\s*(?:\d+|[가-하])[.)]\s*", "", labels[0])
    if not all(_field_label(label) for label in labels):
        return []
    tail = parts[1]
    quantities = _read_value(tail)
    separators = [m.start() for m in re.finditer("/", tail)
                  if not any(a <= m.start() < b - int(unit.endswith("/")) for _, unit, a, b in quantities)]
    if len(separators) != len(labels) - 1:
        return []
    offset = len(line) - len(tail)
    bounds = zip([-1, *separators], [*separators, len(tail)])
    return [(label, offset + a + 1, offset + b) for label, (a, b) in zip(labels, bounds)]


def _parallel_field(line, start):
    parts = _parallel_parts(line)
    prefix = re.split(r"[:：]", line[:start], maxsplit=1)
    if len(prefix) == 2 and re.search(r"[:：□■○◦❍]|\s-\s", prefix[1]):
        return None
    return next(((label, True) for label, a, b in parts if a <= start < b), None)


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


def _written_amount(line, match, number_starts):
    # A parenthesized scale or '단위: 천원' declares a unit, not an amount.
    if set(match[1]) <= set(SCALES) and re.search(r"(?:단위\s*[:：]|\()\s*$", line[:match.start()]):
        return False
    return match.start(1) in number_starts or match[0].startswith(("금", "일금"))


def _read_value(line):
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
                  if _written_amount(line, m, number_starts))
    return sorted(result, key=lambda r: r[2])


def _read_cell(line):
    parts = _parallel_parts(line) or [("", 0, len(line))]
    return [(value, unit, a + start, b + start) for _, start, end in parts
            for value, unit, a, b in _read_value(line[start:end])]


def _read(line):
    return [(value, unit, a + cell.start(), b + cell.start()) for cell in _cells(line)
            for value, unit, a, b in _read_cell(cell[0])]


def _strip_unit(match, unit):
    declaration = _declared_unit(match[0])
    return "" if declaration and declaration["unit"] == unit else match[0]


def _clean_label(label, unit):
    label = re.sub(r"\[IMAGE[^\]]*\]", "", label).strip()
    label = re.sub(r"(?<![가-힣])(?:[가-힣]\s+)+[가-힣](?![가-힣])", lambda m: re.sub(r"\s", "", m[0]), label)
    label = re.sub(r"(?:일금|금)\s*$", "", label).split("/")[0]
    label = UNIT_DECLARATION.sub(lambda m: _strip_unit(m, unit), label)
    if not any(t.tag in ("NNG", "NNP", "SL") for t in tokens(label)):
        return ""
    phrase = subject_phrase(label)
    if phrase and unit == "원" and "사업" not in phrase.replace(" ", ""):
        phrase = "사업 " + phrase
    return phrase


def _field(line, start, headers):
    cells = _cells(line)
    if "|" in line:
        column = next(i for i, cell in enumerate(cells) if cell.start() <= start < cell.end())
        local = line[cells[column].start():start]
        parallel = _parallel_field(cells[column][0], start - cells[column].start())
        if parallel is not None:
            return parallel
        if _clean_label(local, ""):
            return local, ":" in local or "：" in local
        if column < len(headers):
            return headers[column], True
        if column and not re.search(r"\d", cells[column - 1][0]):
            return cells[column - 1][0], True
        return "", False
    parallel = _parallel_field(line, start)
    if parallel is not None:
        return parallel
    prefix = line[:start]
    declared = ":" in prefix or "：" in prefix
    label = re.split(r"[:：]", prefix)[-2] if declared else prefix
    label = re.split(r"[□■○◦❍ㅇᄋ]|(?:^|\s)[가-하0-9]+\.\s*", label)[-1]
    return label, declared


def _row(chunk, line, quantity, offset, headers, context, declaration=None):
    value, unit, start, end = quantity
    attached = re.search(r"(이상|이하|초과|미만|이내|까지)$", unit)
    if attached:
        unit, end = unit[:attached.start()], end - len(attached[0])
    comparison = COMPARISON.match(line[end:])
    unit = "원" if unit in ("원원", "원정") else unit
    label, declared = (declaration["field"], True) if declaration else _field(line, start, headers)
    phrase = _clean_label(label, unit)
    illustrative = "예시" in context or bool(re.search(r"\[\s*참고[.\s][^\]]*\]", context))
    cap = (declared and comparison is not None and comparison[1] in ("이하", "이내", "까지")
           and not re.match(r"\s*(?:인|의|사업|용역)", line[end + comparison.end():]))
    return {"doc_id": chunk["doc_id"], "chunk_id": chunk["chunk_id"], "value": value, "unit": unit,
            "subject": phrase.split(), "phrase": phrase, "span": [offset + start, offset + end],
            "original": line[start:end], "bound": bool(attached or comparison or line[start:start+1] == "±"),
            "declared_cap": cap, "illustrative": illustrative,
            "estimated_price": "추정가격" in phrase.replace(" ", "")}


def _header_label(cell, declaration, offset, spans):
    suffix = cell.string[declaration["span"][1] - offset:cell.end()].strip()
    if suffix not in ("", ")"):
        return False
    ends = {end for _, end in spans}
    if any(t.start in ends and t.tag.startswith("J") for t in tokens(cell[0])):
        return False
    label = cell.string[cell.start():declaration["span"][0] - offset]
    for start, end in reversed(spans):
        label = label[:start] + label[end:]
    parsed = tokens(label.lstrip(" \t.()"))
    return bool(parsed) and not parsed[0].tag.startswith("J") and _field_label(label)


def _header_modifiers(cell, declaration, offset, quantities):
    spans = [(start - cell.start(), end - cell.start()) for (_, _, start, end), _ in quantities
             if cell.start() <= start < cell.end()]
    if not spans:
        return True
    if declaration is None or max(end for _, end in spans) + cell.start() + offset > declaration["span"][0]:
        return False
    return _header_label(cell, declaration, offset, spans)


def _marked_header(cells, declarations, following):
    delimiter = _cells(following)
    return (any(declarations) and len(delimiter) == len(cells)
            and all(re.fullmatch(r":?-{3,}:?", cell[0].strip()) for cell in delimiter))


def _table_schema(line, following, offset, headers, declarations, quantities):
    if not re.search(r"[가-힣]", line):
        return headers, declarations, False
    cells = _cells(line)
    declared = [_declared_unit(cell[0], offset + cell.start()) for cell in cells]
    if _marked_header(cells, declared, following):
        return [cell[0].strip() for cell in cells], declared, True
    if any(NUMBER_CELL.fullmatch(cell[0]) for cell in cells):
        return headers, declarations, False
    if not all(_header_modifiers(cell, declaration, offset, quantities) for cell, declaration in zip(cells, declared)):
        return headers, declarations, False
    if headers and not any(declared):
        return headers, declarations, False
    return [cell[0].strip() for cell in cells], declared, True


def _chunk_rows(chunk):
    rows = []
    offset, headers, declarations, default = 0, [], [], None
    body = unicodedata.normalize("NFC", chunk["body"])
    lines = body.splitlines(keepends=True)
    for line, following in zip(lines, [*lines[1:], ""]):
        quantities = [(quantity, None) for quantity in _read(line)]
        if "|" in line:
            headers, declarations, is_header = _table_schema(line, following, offset, headers, declarations, quantities)
            if is_header:
                quantities = []
            quantities.extend(_implicit_cells(line, headers, declarations, default))
        else:
            declared = _declared_unit(line, offset) if "단위" in line else None
            default = declared if headers or declared else default
            headers, declarations = [], []
        for quantity, declaration in quantities:
            row = _row(chunk, line, quantity, offset, headers, body[max(0, offset-200):offset+len(line)], declaration)
            if declaration is not None:
                row["unit_declaration"] = {key: declaration[key] for key in ("original", "span")}
            rows.append(row)
        offset += len(line)
    return rows


def quantity_rows(chunks):
    return [row for chunk in chunks for row in _chunk_rows(chunk)]
