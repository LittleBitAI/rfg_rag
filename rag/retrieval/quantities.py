"""Kiwi quantity reader copied from golden_pipeline; retrieval owns this copy."""
import re
import threading
import unicodedata
from decimal import Decimal
from functools import lru_cache

from kiwipiepy import Kiwi

SIGNS = ("+", "-", "−", "±", "△", "▲")
RANGES = ("~", "∼", "〜")
UNIT_TAGS = ("NR", "NNB", "NNG", "SW", "SL", "XSN")
SCALES = {"십": 10, "백": 100, "천": 1000, "만": 10_000, "억": 10**8, "조": 10**12}
SUBJECT_TAGS = ("NNG", "NNP", "SL", "SN", "NNB")
_KIWI_LOCK = threading.Lock()


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


def _norm(text):
    return re.sub(r"[\s,]", "", unicodedata.normalize("NFC", text))


def facts(text):
    """text 의 (값, 단위) 쌍마다 그 대상과 글자 범위를 함께 돌려준다: [((값, 단위), 대상 낱말 집합, (시작, 끝))].

    대상은 단위가 같은 앞 값 뒤부터 이 값 앞까지의 내용 형태소다. A안은 2억원, B안은 1억원 에서 2억원 의 대상은 {A, 안},
    1억원 의 대상은 {B, 안} 이다. 단위가 다른 값끼리는 바뀔 수 없어 경계로 삼지 않는다 (1차년도 1억원 의 대상은 {1, 차, 년도}).
    글자 범위는 NFC 로 바꾼 text 에서 그 수 표현(부호부터 단위 끝까지)의 자리다.
    """
    text = unicodedata.normalize("NFC", text)
    parsed = tokens(text)
    found, carry, after = [], {}, {}
    for i, token in enumerate(parsed):
        if token.tag != "SN":
            continue
        sign, unit = _sign(parsed, i), _unit(parsed, i)
        if sign is None or not unit:
            continue
        scale, end = _scale(parsed, i)
        sign, before, start = carry.pop(i, (sign, 0, i))
        amount = before + Decimal(token.form.replace(",", "")) * scale
        rest = unit[len("".join(t.form for t in parsed[i + 1:end])):]
        if not rest and end < len(parsed) and parsed[end].tag == "SN":
            carry[end] = (sign, amount, start)
            continue
        subject = {_norm(t.form) for t in parsed[after.get(rest, 0):start] if t.tag in SUBJECT_TAGS}
        after[rest] = _unit_end(parsed, end, rest)
        span = (parsed[start - 1 if sign else start].start, parsed[after[rest] - 1].end)
        found.append(((sign.replace("−", "-") + format(amount.normalize(), "f"), rest), subject, span))
    return found


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
