import json
from unittest.mock import MagicMock

import numpy as np
import pytest

from rag.config import read_jsonl
from rag.generation.generation import format_context
from rag.retrieval import indexing
from rag.retrieval.quantities import facts
from rag.retrieval.quantity_filter import parse_condition, quantity_rows
from rag.retrieval.retrieval import DocRouter, HybridIndex


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
    questions = ["사업 예산 1억원 이상 사업", "예산이 1억~5억인 사업", "예산이 가장 큰 사업"]
    assert {parse_condition(q).subject for q in questions} == {"사업 예산"}


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
    assert "없어 제외" in format_context(hits)
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
    assert hits[0]["chunk_id"] == candidates[0]["chunk_id"] == "a-overview"
    assert "개요: 가 사업" in hits[0]["body"] and "목 차" not in hits[0]["body"]


def test_original_value_is_preserved_when_overview_tokenizer_normalizes_spaces(index):
    original = "100,000,000  원"
    index.quantity_rows[0]["original"] = original
    index.embedder.truncate = lambda text, budget: " ".join(text[:budget].split())
    hits, _ = index.search_with_candidates("예산 1억원 이하 사업")
    assert original in hits[0]["body"]


def test_overview_prefers_actual_value_source_over_high_ranked_blank_proposal_form(index):
    index.chunks[0]["body"] += "\n사업개요: 시민에게 교통정보를 제공하기 위한 시스템을 구축하는 사업이다."
    index.chunks.append(chunk("a", "[서식2] 제안 요약서\n사업추진목적 사업추진배경 사업추진전략을 작성하여 제출하는 양식", "-form"))
    index._rank.side_effect = None
    index._rank.return_value = [{"index": 9, "score": 1}]
    hits, candidates = index.search_with_candidates("예산 1억원 이하인 사업의 개요")
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
    assert phrases == ["예산", "추정 가격"]
    assert embedder.encode.call_args_list[1].args[0] == phrases
    assert np.load(tmp_path / "quantity_vectors.npy").shape == (2, 2)
    assert rows[1]["span"] == [10, 13]
