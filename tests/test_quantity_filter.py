import json
from unittest.mock import MagicMock

import numpy as np
import pytest

from rag.config import read_jsonl
from rag.generation.generation import format_context
from rag.retrieval import indexing
from rag.retrieval.quantities import facts
from rag.retrieval.quantity_filter import parse_condition
from rag.retrieval.quantity_metadata import quantity_rows
from rag.retrieval.retrieval import DocRouter, HybridIndex, retrieval_fields


@pytest.mark.parametrize("text", ["1억 3천만원", "130백만원", "130,000,000원", "금 130,000,000원"])
def test_reader_money_forms(text):
    assert [pair for pair, _, _ in facts(text)] == [("130000000", "원")]


def test_reader_units_and_table_subject():
    assert [pair for pair, _, _ in facts("8개월 12개 12개월")] == [("8", "개월"), ("12", "개"), ("12", "개월")]
    assert facts("| 사업금액 | 717,285,200원 |")[0][1] == {"사업", "금액"}


def test_corpus_tolerance_is_kept_as_a_bound_quantity():
    row = quantity_rows([chunk("a", "허용 오차 ±7%")])[0]
    assert (row["value"], row["original"], row["bound"]) == (7, "±7%", True)


@pytest.mark.parametrize("text,mode,unit,values", [
    ("사업 예산 1억원 이상인 사업들과, 그 사업들의 개요를 알려줘.", "이상", "원", (1e8,)),
    ("사업기간 6개월 이하인 사업", "이하", "개월", (6,)),
    ("예산 1억원 초과 사업", "초과", "원", (1e8,)),
    ("예산 1억원 미만 사업", "미만", "원", (1e8,)),
    ("예산 1억원이상인 사업", "이상", "원", (1e8,)),
    ("사업 예산이 1억 원 이상인 사업 목록과 각 사업의 개요를 알려줘.", "이상", "원", (1e8,)),
    ("예산 130백만 원 이하 사업", "이하", "원", (1.3e8,)),
    ("예산 1억 원~5억 원 사업", "range", "원", (1e8, 5e8)),
    ("예산 1억원~5억원 사업", "range", "원", (1e8, 5e8)),
    ("예산이 1억~5억인 사업", "range", "", (1e8, 5e8)),
    ("1억~5억 사업", "range", "", (1e8, 5e8)),
    ("예산 1억원과 5억원 사이 사업", "range", "원", (1e8, 5e8)),
    ("예산 1억원 5억원 사이 사업", "range", "원", (1e8, 5e8)),
    ("예산 1억원부터 5억원까지 사업", "range", "원", (1e8, 5e8)),
    ("예산 1억원 이상 5억원 이하 사업", "range", "원", (1e8, 5e8)),
    ("예산이 가장 큰 사업", "max", "", ()),
    ("예산 규모가 가장 큰 사업은 무엇인가요?", "max", "", ()),
    ("사업기간이 최대 긴 사업", "max", "", ()),
    ("예산이 최소 작은 사업", "min", "", ()),
])
def test_question_forms(text, mode, unit, values):
    condition = parse_condition(text)
    assert (condition.mode, condition.unit, condition.values) == (mode, unit, values)


@pytest.mark.parametrize("text", ["예산 개요", "예산 1억원", "예산 1억원~6개월 사업", "2024 예산이 가장 큰 사업"])
def test_non_conditions(text):
    assert parse_condition(text) is None


def test_project_subject_is_shared_by_threshold_range_and_extreme():
    questions = ["사업 예산 1억원 이상 사업", "예산이 1억~5억인 사업", "예산이 가장 큰 사업", "예산 규모가 가장 큰 사업"]
    assert {parse_condition(q).subject for q in questions} == {"사업 예산"}
    assert parse_condition("규모가 가장 큰 사업").subject == "사업 규모"


class StubEmbedder:
    def embed_query(self, text):
        return [1, 0] if "예산" in text else [0, 1]

    def encode(self, texts, progress=False):
        return np.array([self.embed_query(t) for t in texts], dtype=np.float32)

    def token_counts(self, texts):
        return [len(t) + 2 for t in texts]

    def truncate(self, text, budget):
        return text[:budget]


def chunk(doc, text, suffix=""):
    return {"doc_id": doc, "chunk_id": doc + suffix, "body": text, "text": text,
            "source": doc + ".pdf", "page": 1, "section": "", "kind": "prose", "title": doc}


@pytest.fixture
def index():
    obj = HybridIndex.__new__(HybridIndex)
    obj.chunks = [chunk("a", "예산 1억원\n사업기간 8개월"), chunk("b", "예산 3억원"),
                  chunk("c", "예산 3억원"), chunk("d", "사업기간 12개월"),
                  chunk("e", "추정가격 2천만원 이상인 사업은"), chunk("f", "금액 9억원"),
                  chunk("a", "개요: 가 사업 " + "긴 설명 " * 100, "-overview"),
                  chunk("b", "개요: 나 사업", "-overview"), chunk("c", "개요: 다 사업", "-overview")]
    obj.doc_ids = np.array([c["doc_id"] for c in obj.chunks])
    obj.quantity_rows = quantity_rows(obj.chunks)
    obj.quantity_phrases = list(dict.fromkeys(r["phrase"] for r in obj.quantity_rows))
    obj.embedder = StubEmbedder()
    obj.quantity_vectors = obj.embedder.encode(obj.quantity_phrases)
    obj.router = DocRouter([], {})
    obj.rcfg = {"field_similarity": 0.8, "filter_token_budget": 300}
    obj._rank = MagicMock(side_effect=lambda q, codes, ids: [{"index": next(
        i for i, c in reversed(list(enumerate(obj.chunks))) if c["doc_id"] in ids), "score": 1}])
    return obj


@pytest.mark.parametrize("question,docs", [
    ("예산 1억원 이상인 사업들의 개요", ["b", "c", "a"]),
    ("예산 1억원 초과 사업", ["b", "c"]),
    ("예산 3억원 미만 사업", ["a"]),
    ("예산 1억원 이하 사업", ["a"]),
    ("예산 1억~2억 사업", ["a"]),
    ("예산이 가장 큰 사업", ["b", "c"]),
    ("예산이 가장 작은 사업", ["a"]),
    ("사업기간 6개월 이상인 사업", ["d", "a"]),
    ("예산 9억원 이상 사업", []),
])
def test_filter_selection_context_and_contract(index, question, docs):
    hits, candidates = index.search_with_candidates(question)
    assert [h["doc_id"] for h in hits] == docs
    assert [c["fused_rank"] for c in candidates] == list(range(1, len(docs) + 1))
    assert "미표기·매칭 불가로 제외" in format_context(hits)
    for hit, candidate, value in zip(hits, candidates, hits.values):
        assert set(hit) == set(index.chunks[0]) | {"score"}
        assert value["original"] in hit["body"]
        assert index.embedder.token_counts([hit["body"]])[0] <= 300 // len(docs)
        assert all(candidate[k] is None for k in ("dense_score", "dense_rank", "bm25_score", "bm25_rank"))
        assert candidate["exact_code_match"] is False
    if "예산" in question:
        assert set(hits.chosen) == {"a", "b", "c"}
        assert "제외 3개" in format_context(hits)
    if "개요" in question:
        assert "개요: 가 사업" in hits[-1]["body"]
        assert all("개요" in call.args[0] for call in index._rank.call_args_list)


def test_highest_similarity_wins_over_larger_value(index):
    row = {**index.quantity_rows[0], "value": 9e8, "phrase": "other"}
    index.quantity_rows.append(row)
    index.quantity_phrases.append("other")
    index.quantity_vectors = np.vstack([index.quantity_vectors, [0.85, 0]])
    hits, _ = index.search_with_candidates("예산 2억원 이상 사업")
    assert "a" not in [h["doc_id"] for h in hits]


@pytest.mark.parametrize("toc_body", [
    "목 차\n1. 사업개요와 일반사항 1\n2. 사업 추진배경 및 필요성 2\n3. 주요 사업내용 및 범위 3",
    "Ⅰ. 사업개요와 일반사항 1\n1. 사업 추진배경 및 필요성 2\n2. 주요 사업내용 및 범위 3",
    "Ⅰ. 사업개요와 일반사항 1 1. 추진배경 2 2. 사업목표 3 3. 사업내용 4 4. 추진체계 5 5. 요구사항 6",
])
def test_filter_skips_heading_and_toc_candidates(index, toc_body):
    heading = chunk("a", "Ⅰ | 사업 개요", "-heading")
    toc = chunk("a", toc_body, "-toc")
    index.chunks.extend([heading, toc])
    index._rank.side_effect = lambda *args: [{"index": 9, "score": 1}, {"index": 10, "score": 0.9},
                                           {"index": 6, "score": 0.8}]
    hits, candidates = index.search_with_candidates("예산 1억원 이하인 사업의 개요")
    assert hits[0]["chunk_id"] == candidates[0]["chunk_id"] == "a"
    assert "chunk_id=a-overview" in hits[0]["body"]
    assert "개요: 가 사업" in hits[0]["body"] and "목 차" not in hits[0]["body"]


def test_original_value_is_preserved_when_overview_tokenizer_normalizes_spaces(index):
    original = "100,000,000  원"
    index.quantity_rows[0]["original"] = original
    index.embedder.truncate = lambda text, budget: " ".join(text[:budget].split())
    hits, _ = index.search_with_candidates("예산 1억원 이하 사업")
    assert original in hits[0]["body"]


@pytest.mark.parametrize("value_page,overview_page,overview_source,location", [
    (1, 2, "a.pdf", "p.2"), (None, None, "a.hwp", "Overview"),
])
def test_filter_value_and_overview_keep_their_own_locations(index, value_page, overview_page, overview_source, location):
    index.chunks[0].update(page=value_page, section="Budget")
    index.chunks[6].update(page=overview_page, section="Overview", source=overview_source)
    index.chunk_file = "fixture/chunks.jsonl"
    question = "예산 1억원 이하인 사업의 개요"
    hits, record = retrieval_fields(index, question, question, reused=False)
    candidates = record["ranked_candidates"]
    assert hits[0]["chunk_id"] == candidates[0]["chunk_id"] == "a"
    assert record["context_chunk_ids"] == ["a"]
    assert (hits[0]["source"], hits[0]["page"], hits[0]["section"]) == ("a.pdf", value_page, "Budget")
    assert f"개요 출처: {overview_source} {location}" in hits[0]["body"]
    assert "개요: 가 사업" in hits[0]["body"]
    value_location = "p.1" if value_page else "Budget"
    assert f"[1] (a.pdf {value_location}" in format_context(hits)


@pytest.mark.parametrize("question", [
    "예산 1억원 이하인 사업의 개요", "예산 1억원 이하인 사업",
    "예산이 1억~2억인 사업", "예산 1억~2억 원 규모의 사업",
])
def test_overview_prefers_actual_value_source_over_high_ranked_blank_proposal_form(index, question):
    index.chunks[0]["body"] += "\n사업개요: 시민에게 교통정보를 제공하기 위한 시스템을 구축하는 사업이다."
    index.chunks.append(chunk("a", "[서식2] 제안 요약서\n사업추진목적 사업추진배경 사업추진전략을 작성하여 제출하는 양식", "-form"))
    index._rank.side_effect = None
    index._rank.return_value = [{"index": 9, "score": 1}]
    hits, candidates = index.search_with_candidates(question)
    assert hits[0]["chunk_id"] == candidates[0]["chunk_id"] == "a"
    assert "시민에게 교통정보" in hits[0]["body"] and "제안 요약서" not in hits[0]["body"]


@pytest.mark.parametrize("results", [[], [{"index": 9, "score": 1}]])
def test_document_is_kept_with_explicit_missing_content_if_no_substantive_candidate(index, results):
    index.chunks.append(chunk("a", "Ⅰ | 사업 개요", "-heading"))
    index._rank.side_effect = None
    index._rank.return_value = results
    hits, _ = index.search_with_candidates("예산 1억원 이하 사업")
    assert [h["doc_id"] for h in hits] == ["a"]
    assert "본문을 찾지 못했습니다" in hits[0]["body"]
    assert "Ⅰ | 사업 개요" not in hits[0]["body"]


def test_unlabelled_values_are_excluded_even_if_empty_embedding_is_similar(index):
    index.quantity_rows = quantity_rows([chunk("a", "9억원")])
    index.quantity_phrases = [""]
    index.quantity_vectors = np.array([[1, 0]])
    hits, _ = index.search_with_candidates("예산 1억원 이상 사업")
    assert hits == [] and "제외 6개" in format_context(hits)


@pytest.mark.parametrize("comparison", ["이상", "이하", "초과", "미만", "이내", "까지"])
@pytest.mark.parametrize("space", ["", " "])
def test_bounds_are_not_document_values(index, comparison, space):
    rows = quantity_rows([chunk("a", f"예산 9억원{space}{comparison}인 사업")])
    assert rows[0]["unit"] == "원" and rows[0]["bound"] is True
    index.quantity_rows = rows
    index.quantity_phrases = ["예산"]
    index.quantity_vectors = np.array([[1, 0]])
    hits, _ = index.search_with_candidates("예산 1억원 이상 사업")
    assert hits == [] and "제외 6개" in format_context(hits)


@pytest.mark.parametrize("question", ["한국정보공사 예산 1억원 이상 사업", "「문서명」 사업에서 예산 1억원 이상 사업"])
def test_agency_and_document_prefix_keep_current_route(index, question):
    index.router.org_docs = {"한국정보공사": {"a"}}
    index._rank.side_effect = None
    index._rank.return_value = [{"index": 0, "score": 1}]
    index._pack = MagicMock(return_value=[{"existing": True}])
    index._candidate_snapshot = MagicMock(return_value=())
    hits, _ = index.search_with_candidates("다른 원본", query=question)
    assert hits == [{"existing": True}]
    assert index._rank.call_args.args[0] == question


def test_build_index_persists_quantities_and_embeds_distinct_phrases_once(monkeypatch, tmp_path):
    embedder = StubEmbedder()
    embedder.encode = MagicMock(side_effect=embedder.encode)
    monkeypatch.setattr(indexing, "Embedder", lambda _: embedder)
    chunks = [chunk("a", "예산 1억원\n예산 2억원"), chunk("b", "추정가격 2천만원 이상인 사업은")]
    indexing.build_index(chunks, {"embedding": {"max_seq_length": 2048}}, tmp_path)
    rows = read_jsonl(tmp_path / "quantities.jsonl")
    phrases = json.loads((tmp_path / "quantity_phrases.json").read_text(encoding="utf-8"))
    assert len(rows) == 3 and rows[-1]["bound"] is True
    assert rows[-1]["original"] == "2천만원"
    assert phrases == ["사업 예산", "사업 추정 가격"]
    assert embedder.encode.call_args_list[1].args[0] == phrases
    assert np.load(tmp_path / "quantity_vectors.npy").shape == (2, 2)
    assert rows[1]["span"] == [10, 13]


@pytest.mark.parametrize("text,value", [
    ("사 업 비 : 금470백만원", 470000000),
    ("사업예산: 1억 5천만 원(부가세 포함)", 150000000),
    ("사업예산: 400,000,000원원(부가세포함)", 400000000),
    ("사업금액: 일금 일억구천오백삼만원정(￦195,030,000, VAT포함)", 195030000),
    ("사업예산: ￦493,270,440 부가세포함", 493270440),
    ("사업예산: 50,000,000(금 오천만원/VAT포함)", 50000000),
    ("사업예산: 일금 육천만원정", 60000000),
])
def test_audited_quantity_formats_preserve_original_spans(text, value):
    rows = quantity_rows([chunk("a", text)])
    money = [r for r in rows if r["unit"] == "원"]
    assert money and all(r["value"] == value for r in money)
    assert all(text[r["span"][0]:r["span"][1]] == r["original"] for r in rows)


def test_label_cleanup_and_table_header_inheritance():
    chunks = [chunk("a", "사 업 명: NCIC ❍ 사업기간: 2024.11.15.(금) ❍ 사업금액: 50,000,000원"),
              chunk("b", "사업구분 | 사업예산\n계 | 금 773,801천원\n개발 | 금 153,000천원"),
              chunk("c", "사 업 비 : 금470백만원")]
    money = [r for r in quantity_rows(chunks) if r["unit"] == "원"]
    assert [(r["value"], r["phrase"]) for r in money] == [
        (50000000, "사업 금액"), (773801000, "사업 예산"), (153000000, "사업 예산"), (470000000, "사업비")]


@pytest.mark.parametrize("comparison", ["이내", "이하", "까지"])
def test_declared_budget_caps_are_usable_but_eligibility_clauses_are_not(index, comparison):
    rows = quantity_rows([chunk("a", f"사업예산: 230,000천원 {comparison} (부가세 포함)"),
                          chunk("b", f"사업예산: 20억원 {comparison}인 사업은 중소기업만 참여")])
    assert [r["bound"] for r in rows] == [True, True]
    assert [r["declared_cap"] for r in rows] == [True, False]
    index.quantity_rows = rows
    index.quantity_phrases = list(dict.fromkeys(r["phrase"] for r in rows))
    index.quantity_vectors = index.embedder.encode(index.quantity_phrases)
    hits, _ = index.search_with_candidates("예산 1억원 이상인 사업")
    assert [h["doc_id"] for h in hits] == ["a"]


@pytest.mark.parametrize("value", [-1, 0, 1, 2])
def test_won_placeholders_are_unstated_without_suppressing_one_month(index, value):
    rows = quantity_rows([chunk("a", f"예산: {value}원\n사업기간: 1개월\n수량: 1개")])
    index.quantity_rows = rows
    index.quantity_phrases = list(dict.fromkeys(r["phrase"] for r in rows))
    index.quantity_vectors = index.embedder.encode(index.quantity_phrases)
    money, _ = index.search_with_candidates("예산 2원 이하 사업")
    duration, _ = index.search_with_candidates("사업기간 1개월 이상 사업")
    items, _ = index.search_with_candidates("수량 1개 이상 사업")
    assert [h["doc_id"] for h in money] == (["a"] if value > 1 else [])
    assert [h["doc_id"] for h in duration] == ["a"]
    assert [h["doc_id"] for h in items] == ["a"]


def test_estimated_prices_and_example_amounts_remain_unusable_at_high_similarity(index):
    rows = quantity_rows([chunk("a", "추정가격: 140,000,000원"), chunk("b", "예시) 사업예산: 1.5억원")])
    index.quantity_rows = rows
    index.quantity_phrases = list(dict.fromkeys(r["phrase"] for r in rows))
    index.quantity_vectors = np.ones((len(index.quantity_phrases), 2))
    hits, _ = index.search_with_candidates("예산 1억원 이상 사업")
    assert hits == []


def test_employee_word_is_not_a_korean_written_money_amount():
    assert quantity_rows([chunk("a", "사원 정보 관리")]) == []


def test_comparison_particles_and_numeric_table_cells_are_not_budget_fields():
    rows = quantity_rows([chunk("a", "자재 품목당 합계액이 1억원을 초과하는 경우"),
                          chunk("b", "건당 500만원 | 300만원 | 100만원")])
    assert rows[0]["bound"] and not rows[0]["declared_cap"]
    assert not rows[2]["phrase"] and not rows[3]["phrase"]


@pytest.mark.parametrize("question,docs", [("예산이 1억~2억인 사업", ["a"]),
                                          ("예산이 가장 큰 사업", ["b", "c"])])
def test_table_separators_and_repeated_forms_cannot_dominate_inferred_units(index, question, docs):
    rows = quantity_rows([chunk("a", "예산 | 123 | 금액\n" * 20)])
    assert rows == []
    assert facts("수량 | 1조 | 보안모듈")[0][0] == ("1000000000000", "")
    index.quantity_rows.extend([{**index.quantity_rows[0], "phrase": "other", "unit": "호", "value": 123}] * 20)
    index.quantity_phrases.append("other")
    index.quantity_vectors = np.vstack([index.quantity_vectors, [0.85, 0]])
    hits, _ = index.search_with_candidates(question)
    assert [hit["doc_id"] for hit in hits] == docs


def test_actual_period_cap_and_warranty_labels_remain_distinct(index):
    rows = quantity_rows([chunk("a", "사업기간: 계약일로부터 24개월 이내\n무상유지보수기간: 사업종료일로부터 12개월")])
    assert rows[0]["declared_cap"] and rows[0]["phrase"] == "사업 기간"
    assert rows[1]["phrase"] == "무상 유지 보수 기간"
    index.quantity_rows = rows
    index.quantity_phrases = [r["phrase"] for r in rows]
    index.quantity_vectors = index.embedder.encode(index.quantity_phrases)
    hits, _ = index.search_with_candidates("사업기간 6개월 이상인 사업")
    assert hits.values[0]["value"] == 24


def test_table_cell_subject_overrides_generic_header_and_reference_is_not_own_value():
    rows = quantity_rows([chunk("a", "항목 | 세부 내용\n내용 | 무상 하자보수 기간은 검수완료일로부터 12개월"),
                          chunk("b", "[ 참고. 사업 PDM 안 ]\n예산: 977,240,000원")])
    assert "하자" in rows[0]["phrase"] and "검수" in rows[0]["phrase"]
    assert not rows[0]["phrase"].startswith("사업")
    assert rows[1]["illustrative"]


def test_per_case_fines_are_not_budget_fields_and_standalone_scale_is_an_amount():
    rows = quantity_rows([chunk("b", "건당 500만원 | 300만원 | 100만원"),
                          chunk("c", "사업예산: 천원")])
    assert all(not r["phrase"] for r in rows if r["doc_id"] == "b")
    assert next(r for r in rows if r["doc_id"] == "c")["value"] == 1000


@pytest.mark.parametrize("text,value,unit,phrase", [
    ("사업예산(천원) | 부문\n10 | 운영", 10000, "원", "사업 예산"),
    ("(단위: 천원)\n사업예산 | 부문\n10 | 운영", 10000, "원", "사업 예산"),
    ("부문 | 사업예산(백만원)\n운영 | 1.5", 1500000, "원", "사업 예산 운영"),
    ("사업기간(개월) | 부문\n10 | 운영", 10, "개월", "사업 기간"),
    ("수량(개) | 부문\n10 | 운영", 10, "개", "수량"),
    ("용량(MB) | 부문\n10 | 운영", 10, "MB", "용량"),
])
def test_declared_table_units_scale_numeric_cells_and_preserve_spans(text, value, unit, phrase):
    rows = quantity_rows([chunk("a", text)])
    assert len(rows) == 1
    row = rows[0]
    assert (row["value"], row["unit"], row["phrase"]) == (value, unit, phrase)
    assert text[slice(*row["span"])] == row["original"]
    declaration = row["unit_declaration"]
    assert text[slice(*declaration["span"])] == declaration["original"]


def test_table_units_are_column_specific_and_end_with_the_table():
    text = ("(단위: 천원)\n사업예산 | 사업기간(개월)\n10 | 5\n20원 | 6개월\n"
            "다음 본문\n사업예산 | 부문\n30 | 운영")
    rows = quantity_rows([chunk("a", text), chunk("b", "10 | 운영")])
    assert [(row["value"], row["unit"], row["phrase"]) for row in rows] == [
        (10000, "원", "사업 예산"), (5, "개월", "사업 기간"),
        (20, "원", "사업 예산"), (6, "개월", "사업 기간")]
    assert not any(row["doc_id"] == "b" for row in rows)
    assert not any(row.get("unit_declaration") for row in rows[2:])
    assert quantity_rows([chunk("c", "사업예산(부가세포함) | 부문\n10 | 운영")]) == []


def test_filter_displays_the_inherited_unit_with_the_original_numeric_cell(index):
    index.chunks[0] = chunk("a", "사업예산(천원) | 부문\n10 | 운영")
    index.quantity_rows = quantity_rows([index.chunks[0]])
    index.quantity_phrases = [index.quantity_rows[0]["phrase"]]
    index.quantity_vectors = index.embedder.encode(index.quantity_phrases)
    hits, _ = index.search_with_candidates("예산 10000원 이상 사업")
    assert hits.values[0]["value"] == 10000
    assert hits[0]["body"].splitlines()[0] == "사업 예산: 10 (천원)"


@pytest.mark.parametrize("boundary,ending,following", [
    (False, "\n", False), (True, "\n", True), (True, "\r\n", True),
    (True, "\n", False), (True, " \t\n", True),
])
@pytest.mark.parametrize("total", ["계 | 200,000", "계 || 200,000"])
def test_declared_table_units_preserve_component_labels_and_collapsed_total_cells(index, boundary, ending, following, total):
    lines = ["예산과목 | 주요 내용 | 예산(천원)",
             "전산개발비 | 시스템 구축 | 140,000", "장비비 | 장비 구입 | 60,000", total]
    if boundary:
        lines.insert(1, "--- | --- | ---")
    lines = ["  | " + line + " |" if boundary else line for line in lines]
    text = ending.join(lines) + (ending + "다음 본문" if following else "")
    rows = quantity_rows([chunk("a", text)])
    assert [(row["value"], row["phrase"]) for row in rows] == [
        (140000000, "사업 예산 전산 개발비"), (60000000, "사업 예산 장비 비"), (200000000, "사업 예산 계")]
    assert all(text[slice(*row["span"])] == row["original"] for row in rows)
    assert all(text[slice(*row["unit_declaration"]["span"])] == "천원" for row in rows)
    index.chunks[0] = chunk("a", text)
    index.quantity_rows = rows
    index.quantity_phrases = [row["phrase"] for row in rows]
    index.quantity_vectors = np.array([[.85, 0], [.8, 0], [1, 0]])
    hits, _ = index.search_with_candidates("예산 1억5천만원 이상인 사업")
    assert [(row["value"], row["original"]) for row in hits.values] == [(200000000, "200,000")]


@pytest.mark.parametrize("question", [
    "응답시간 3초 이하인 요구사항을 알려줘", "사업 응답시간 3초 이하인 요구사항을 알려줘",
    "응답시간 1초~3초 사이 요구사항", "응답시간이 가장 짧은 요구사항",
    "예산 1억원 이상인 업체의 자격을 알려줘",
])
@pytest.mark.parametrize("rewritten", [False, True])
def test_non_project_quantity_questions_keep_hybrid_retrieval(index, question, rewritten):
    index._rank.side_effect = None
    index._rank.return_value = [{"index": 0, "score": 1, "dense_score": .9, "dense_rank": 1,
                                 "bm25_score": 2, "bm25_rank": 1, "exact_code_match": False}]
    index._pack = MagicMock(return_value=[index.chunks[0]])
    index._filter = MagicMock(side_effect=AssertionError("Non-project question entered filter"))
    hits, candidates = index.search_with_candidates("앞 질문" if rewritten else question,
                                                   query=question if rewritten else None)
    index._rank.assert_called_once_with(question, set(), None)
    assert hits == [index.chunks[0]] and not hasattr(hits, "summary")
    assert candidates[0]["dense_score"] == .9 and candidates[0]["bm25_rank"] == 1


def test_interior_empty_cells_keep_positions_between_different_declared_units():
    text = "| 사업기간(개월) | 부문 | 예산(천원) |\n||운영|200,000|\n다음 본문"
    rows = quantity_rows([chunk("a", text)])
    assert [(row["value"], row["unit"], row["phrase"]) for row in rows] == [(200000000, "원", "사업 예산")]
    assert text[slice(*rows[0]["span"])] == "200,000"
    assert text[slice(*rows[0]["unit_declaration"]["span"])] == "천원"


@pytest.mark.parametrize("text", [
    "과업비/과업기간 : 100,000천원 / 착수일로부터 5개월",
    "과업기간/과업비: 착수일로부터 5개월/100,000천원",
    "내용 | 과업비/과업기간 : 100,000천원 / 착수일로부터 5개월",
    "1. 과업비/과업기간: 100,000천원/5개월",
])
def test_parallel_fields_assign_each_quantity_to_its_corresponding_label(text):
    rows = quantity_rows([chunk("a", text)])
    assert {(row["value"], row["unit"], row["phrase"]) for row in rows} == {
        (100000000, "원", "사업 과업비"), (5, "개월", "과업 기간")}
    assert all(text[slice(*row["span"])] == row["original"] for row in rows)


def test_parallel_values_keep_compound_units_and_support_more_than_two_fields():
    rows = quantity_rows([chunk("a", "속도/기간: 100MB/s/5개월"),
                          chunk("b", "예산/사업기간/수량: 1억원/6개월/12개")])
    assert [(row["value"], row["unit"], row["phrase"]) for row in rows] == [
        (100, "MB/s", "속도"), (5, "개월", "기간"),
        (100000000, "원", "사업 예산"), (6, "개월", "사업 기간"), (12, "개", "수량")]


@pytest.mark.parametrize("text", [
    "사용 시스템/메뉴: SAP / 관리 화면 상세 설명: 퇴직 3개월 전 알림",
    "접근권한 관리 내역 기록 - 사용 시스템/메뉴: SAP / 권한모니터링 등 ❍ 기능 요구사항 - 내역 저장(3개월 이상)",
])
def test_parallel_field_scope_does_not_relabel_later_clauses_or_numbered_glossaries(text):
    rows = quantity_rows([chunk("a", text)])
    assert len(rows) == 1 and rows[0]["unit"] == "개월" and rows[0]["phrase"] != "메뉴"
    glossary = "(용어설명) 1. I/O Driver: 설명 2. DIT: 설명 3. SAC: I/O 연결"
    rows = quantity_rows([chunk("b", glossary)])
    assert [(row["original"], row["phrase"]) for row in rows] == [
        ("1. I/O", "용어 설명"), ("2. DIT", "I"), ("3. SAC", "DIT")]
    assert all(glossary[slice(*row["span"])] == row["original"] for row in rows)


@pytest.mark.parametrize("distractor", [
    "요구사항 고유번호 | PMR-001\n세부내용 | 사업자는 사업내용과 사업목적을 작성해 산출물을 제출해야 한다.",
    "3. 사업목적\n4. 사업범위\n1. 사 업 명\n◎ 작성요령 : 계약서상의 사업명을 기입\n"
    "3. 사업목적\n◎ 작성요령 : 제안요청서상의 과제의 추진배경 및 목적을 기입",
])
def test_overview_uses_real_introduction_before_unrelated_value_source(index, distractor):
    index.chunks[0]["body"] = "국가 일반개황: 수도·면적·기후·인구와 경제현황에 관한 일반 정보를 제공한다."
    index.chunks.append(chunk("a", distractor, "-requirements"))
    index.chunks.append(chunk("a", "사업 목적: 스마트 관개시스템을 구축하여 취약 지역의 기후 및 재해 회복력을 강화한다.", "-purpose"))
    index._rank.side_effect = None
    index._rank.return_value = [{"index": 9, "score": 1}, {"index": 10, "score": .9}]
    hits, _ = index.search_with_candidates("예산 1억원 이하인 사업의 개요")
    assert hits[0]["chunk_id"] == "a"
    assert "chunk_id=a-purpose" in hits[0]["body"]
    assert "스마트 관개" in hits[0]["body"] and "일반개황" not in hits[0]["body"]


def test_overview_recovers_real_introduction_after_toc_tail(index):
    index.chunks[0]["body"] = ("Ⅵ. 기타 사항 61\n제출자료 서식 64\n정성제안서 서식 69\n정량제안서 서식 79\n참고자료 82\n"
                              "Ⅰ. 사업 개요\n1. 사업 일반\n사업명: 수문정보시스템 고도화\n"
                              "2. 사업 배경\n수자원정보를 표준화하고 이용 불편 사항을 개선하기 위한 시스템 고도화 사업이다.")
    hits, _ = index.search_with_candidates("예산 1억원 이하인 사업의 개요")
    assert hits[0]["chunk_id"] == "a"
    assert "수자원정보를 표준화" in hits[0]["body"] and "정량제안서" not in hits[0]["body"]
