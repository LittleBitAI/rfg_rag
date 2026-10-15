from itertools import permutations

import pytest

from rag.evaluation.evaluation import _key_fact_ratio


@pytest.mark.parametrize("fact,text,expected", [
    ("3초", "응답 13초 이내", 0),
    ("3초", "3 초 이내", 1),
    ("3초", "3분", 0),
    ("3", "버전 3", 1),
    ("3", "13", 0),
    ("3", "30", 0),
    ("3", "3초", 0),
    ("3", "가격은 3원", 0),
    ("2", "다음 해 2월", 0),
    ("3", "제3조", 0),
    ("90", "90점", 0),
    ("2월", "다음 해 2월분", 1),
])
def test_numbers_require_whole_values_and_matching_units(fact, text, expected):
    assert _key_fact_ratio([fact], text) == expected


@pytest.mark.parametrize("fact,text,expected", [
    ("SFR-009", "고유번호: SFR-009\n분류: 성능 요구사항", 1),
    ("SFR-상담-001", "고유번호 SFR-상담-001 분류", 1),
    ("SFR-009", "SFR-0091", 0),
])
def test_identifier_digits_are_not_quantities(fact, text, expected):
    """식별자 끝 숫자 뒤에 '분류' 같은 낱말이 와도 단위(분)로 읽지 않는다"""
    assert _key_fact_ratio([fact], text) == expected


AMOUNT_FORMS = [
    ["1억 3천만원", "130백만원", "1.3억원", "130,000,000원"],
    ["2억 5천만원", "250,000,000원", "2.5억원"],
    ["4천5백만원", "45,000,000원"],
]


@pytest.mark.parametrize("fact,text", [pair for forms in AMOUNT_FORMS for pair in permutations(forms, 2)])
def test_amount_notations_match_each_other(fact, text):
    assert _key_fact_ratio([fact], f"사업 예산 {text}") == 1


@pytest.mark.parametrize("fact,text", [
    ("1억 3천만원", "1억 3백만원"),
    ("45,000,000원", "4천5백만"),
    ("2.5억원", "2.6억원"),
])
def test_different_amounts_or_missing_currency_do_not_match(fact, text):
    assert _key_fact_ratio([fact], text) == 0


@pytest.mark.parametrize("numeric,korean", [
    ("2024.6.11(화) 17:00", "2024년 6월 11일 오후 5시"),
    ("2025-01-03 09:30", "2025년 1월 3일 오전 9시 30분"),
    ("2025-02-04 00:15", "2025년 2월 4일 오전 12시 15분"),
    ("2025-02-04 12:00", "2025년 2월 4일 오후 12시"),
])
def test_date_and_time_notations_match_in_both_directions(numeric, korean):
    assert _key_fact_ratio([numeric], f"마감 {korean}") == 1
    assert _key_fact_ratio([korean], f"마감 {numeric}") == 1


@pytest.mark.parametrize("text", [
    "2024년 6월 12일 오후 5시",
    "2024년 6월 11일 오후 6시",
    "2024년 6월 11일 오전 5시",
    "2024년 6월 11일 오후 5시 30분",
    "2024년 6월 11일",
])
def test_different_or_missing_date_time_components_do_not_match(text):
    assert _key_fact_ratio(["2024.6.11(화) 17:00"], text) == 0


def test_date_only_fact_matches_a_date_with_time():
    assert _key_fact_ratio(["2024년 6월 11일"], "마감 2024.6.11(화) 17:00") == 1


@pytest.mark.parametrize("fact,expected", [
    ("2월", 1), ("2월 10일", 1), ("10일", 1), ("2025년", 1),
    ("3월", 0), ("2월 1일", 0), ("1일", 0), ("2", 0),
])
def test_partial_date_fact_matches_the_same_part_of_a_full_date(fact, expected):
    assert _key_fact_ratio([fact], "마감 2025.2.10") == expected


@pytest.mark.parametrize("text", [
    "부가세 미포함", "부가세 불포함", "부가세 비포함", "포함되지 않음",
    "포함 제외", "포함 별도", "포함 없음",
])
def test_negation_outside_the_match_rejects_positive_fact(text):
    assert _key_fact_ratio(["포함"], text) == 0


@pytest.mark.parametrize("fact,text", [
    ("불포함", "부가세 불포함"),
    ("부가세 별도", "부가세 별도"),
    ("포함", "부가세 불포함, 유지보수 포함"),
    ("포함", "포함123456없음"),
    ("포함", "미 해당: 포함"),
])
def test_negation_window_preserves_negative_facts_and_other_occurrences(fact, text):
    assert _key_fact_ratio([fact], text) == 1


def test_negation_window_counts_original_characters_after_numeric_match():
    assert _key_fact_ratio(["3초"], "3 초 제외") == 0
    assert _key_fact_ratio(["포함"], "포함12345없음") == 0


@pytest.mark.parametrize("fact,text,expected", [
    ("3초|5분", "응답 13초, 처리 5 분", 1),
    ("포함|별도", "부가세 불포함, 배송비 별도", 1),
    ("3초|포함", "13초, 부가세 불포함", 0),
])
def test_alternatives_use_semantic_and_negation_checks(fact, text, expected):
    assert _key_fact_ratio([fact], text) == expected


def test_plain_text_normalization_and_ratio_are_preserved():
    assert _key_fact_ratio(["클라우드", "CLOUD 전환", "누락"], "클라우드 전환 사업, cloud전환") == pytest.approx(2 / 3)


def test_plain_text_matches_original_words_around_semantic_values():
    assert _key_fact_ratio(["년", "원", "초"], "2024년 6월 11일, 3초, 1억원") == 1
    assert _key_fact_ratio(["number", "date", "time"], "2024년 6월 11일 오후 5시, 3초") == 0


def test_lowercase_expansion_keeps_positions_aligned():
    assert _key_fact_ratio(["x"], "İx") == 1
    assert _key_fact_ratio(["3초"], "İ 3초 제외") == 0


@pytest.mark.parametrize("fact,text,expected", [
    ("1,000만", "한도는 연 1,000만원입니다", 1),
    ("1,000만", "한도는 연 1,000만", 1),
    ("800만", "그 밖의 대출은 1,800만원", 0),
    ("1,000만", "1,000만명", 0),
])
def test_amount_fact_without_currency_matches_amount_with_currency(fact, text, expected):
    assert _key_fact_ratio([fact], text) == expected
