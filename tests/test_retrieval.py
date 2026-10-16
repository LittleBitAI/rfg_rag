"""요구사항 코드·토큰 예산·중복 제거·기관 라우팅의 회귀를 확인한다."""
from collections import defaultdict
from unittest.mock import MagicMock

import numpy as np
import pytest

from rag.preprocessing import parsing
from rag.retrieval.indexing import Embedder, KiwiTokenizer, find_codes
from rag.retrieval.retrieval import DocRouter, HybridIndex, read_csv_orgs


def ranked(pairs):
    return [{"index": i, "score": score, "dense_score": score, "dense_rank": rank,
             "bm25_score": None, "bm25_rank": None, "exact_code_match": False}
            for rank, (i, score) in enumerate(pairs, 1)]


def make_index(bodies, costs, budget=2500, doc_ids=None):
    index = HybridIndex.__new__(HybridIndex)
    doc_ids = doc_ids or ["doc-a"] * len(bodies)
    index.chunks = [{"chunk_id": f"c{i}", "doc_id": doc, "text": body, "body": body}
                    for i, (body, doc) in enumerate(zip(bodies, doc_ids))]
    index.doc_ids = np.array(doc_ids)
    index.code_chunks = defaultdict(set)
    for i, body in enumerate(bodies):
        for code in find_codes(body):
            index.code_chunks[code].add(i)
    index.rcfg = {"token_budget": budget, "dense_weight": 0.6, "candidate_k": 50}
    index.chunk_file = "fixture/chunks.jsonl"
    index.embedder = MagicMock()
    index.embedder.token_counts.side_effect = lambda texts: [costs[bodies.index(text)] for text in texts]
    index.router = MagicMock()
    index.router.route.return_value = {}
    return index


@pytest.mark.parametrize("text", ["sfr001", "SFR-001", "sfr-001 SFR001", "SFR-001은", "[SFR-001], sfr001."])
def test_find_codes_normalizes(text):
    assert find_codes(text) == {"SFR-001"}


@pytest.mark.parametrize("text", ["SFR-001A", "SFR-001B", "sfr001a", "SFR-0012A", "1SFR-001"])
def test_find_codes_does_not_extract_prefixes_from_longer_identifiers(text):
    assert find_codes(text) == set()


def test_token_counts_uses_untruncated_model_tokenizer():
    embedder = Embedder.__new__(Embedder)
    embedder._st = MagicMock()
    embedder._st.tokenizer.return_value = {"input_ids": [[0, 10, 11, 1], [0, 12, 1]]}
    assert embedder.token_counts(["긴 본문", "짧은 본문"]) == [4, 3]
    embedder._st.tokenizer.assert_called_once_with(["긴 본문", "짧은 본문"])


def test_kiwi_batch_and_query_keep_alias_user_words_negation_and_codes():
    tokenizer = KiwiTokenizer()
    texts = ["지체 상금과 부가세 SFR-001은 제출하지 않는다", "부가 가치세는 대상이 아니다",
             "SFR-001A와 SFR-001B의 응답시간"]
    tokens = tokenizer.batch(texts)
    assert tokens == [tokenizer(text) for text in texts]
    assert {"지체상금", "부가가치세", "sfr-001", "않"} <= set(tokens[0])
    assert {"부가가치세", "아니"} <= set(tokens[1])
    assert "sfr-001" not in tokens[2]


@pytest.mark.parametrize("question,query", [("SFR-001A 요구사항", None), ("원본 질문", "SFR-001A 요구사항"),
                                           ("SFR-001 요구사항", None)])
def test_identifier_prefixes_do_not_promote_wrong_chunks_ahead_of_semantic_candidates(question, query):
    index = make_index(["SFR-001B 다른 식별자", "실제 질문의 답변 근거"], [5, 5], budget=5)
    index._dense = MagicMock(return_value={1: 1.0})
    index._sparse = MagicMock(return_value={1: 1.0})

    hits = index.search(question, query=query)

    assert [hit["chunk_id"] for hit in hits] == ["c1"]


@pytest.mark.parametrize("question,query", [("원본 기관 sfr001", "재작성 질문"),
                                           ("원본 기관 질문", "재작성 sfr001"),
                                           ("원본 기관 sfr001", None)])
def test_exact_code_survives_rewrite_and_candidate_cutoff_with_routing(question, query):
    index = make_index(["SFR-001 원래 근거", "일반 후보", "SFR-001 다른 기관"], [3, 3, 3],
                       doc_ids=["doc-a", "doc-a", "doc-b"])
    index.router.route.return_value = {"원본 기관": {"doc-a"}}
    index._dense = MagicMock(return_value={1: 0.9})
    index._sparse = MagicMock(return_value={1: 2.0})

    hits = index.search(question, query=query)

    assert [hit["chunk_id"] for hit in hits] == ["c0", "c1"]
    assert hits[0]["score"] == 0.0
    index.router.route.assert_called_once_with(question)
    expected_query = question if query is None else query
    assert index._dense.call_args.args[0] == expected_query
    assert index._dense.call_args.args[1].tolist() == [True, True, False]
    assert index._sparse.call_args.args[0] == expected_query


def test_pack_keeps_first_chunk_over_budget():
    index = make_index(["첫 근거", "나중 근거"], [12, 1], budget=10)
    assert [hit["chunk_id"] for hit in index._pack([(0, 1.0), (1, 0.5)])] == ["c0"]


def test_pack_removes_near_duplicates_and_repeated_candidates():
    index = make_index(["가 나 다 라 마", "가 나 다 라 바", "별도 근거", "가 나 다 라 마"], [5, 5, 2, 5], budget=25)
    hits = index._pack([(0, 0.912345), (0, 0.9), (1, 0.8), (3, 0.75), (2, 0.7)])
    assert [hit["chunk_id"] for hit in hits] == ["c0", "c2"]
    assert hits[0]["score"] == 0.9123


def test_candidate_snapshot_is_read_only_and_preserves_existing_search_output():
    index = make_index(["SFR-001 첫 근거", "가 나 다 라 마", "가 나 다 라 바", "별도 근거"],
                       [2, 4, 4, 2], budget=8)
    index._dense = MagicMock(return_value={1: 0.9, 2: 0.5, 3: 0.1})
    index._sparse = MagicMock(return_value={3: 10.0, 2: 1.0})

    hits = index.search("SFR-001")
    observed_hits, candidates = index.search_with_candidates("SFR-001")

    # 변경 전 이 검색 fixture의 코드 승격·가중합·중복 제거·예산 결과를 고정한다.
    assert [(h["chunk_id"], h["score"]) for h in hits] == [("c0", 0.0), ("c1", 0.6), ("c3", 0.4)]
    assert hits == observed_hits
    assert [c["chunk_id"] for c in candidates] == ["c0", "c1", "c3", "c2"]
    assert [c["fused_rank"] for c in candidates] == [1, 2, 3, 4]
    assert dict(candidates[0]) == {"chunk_id": "c0", "doc_id": "doc-a", "fused_rank": 1,
                                    "dense_score": None, "dense_rank": None, "bm25_score": None,
                                    "bm25_rank": None, "exact_code_match": True}
    assert (candidates[1]["dense_score"], candidates[1]["dense_rank"]) == (0.9, 1)
    assert (candidates[2]["bm25_score"], candidates[2]["bm25_rank"]) == (10.0, 1)
    with pytest.raises(TypeError):
        candidates[0]["fused_rank"] = 99


def test_component_ranks_interleave_agencies_independently_of_fused_order():
    index = make_index(["가 첫 근거", "가 두번째 근거", "나 첫 근거", "나 두번째 근거"], [1] * 4,
                       doc_ids=["a", "a", "b", "b"])
    index.router.route.return_value = {"가": {"a"}, "나": {"b"}}
    index._dense = MagicMock(side_effect=[{0: 0.9, 1: 0.8}, {2: 0.9, 3: 0.8}])
    index._sparse = MagicMock(side_effect=[{1: 10.0}, {3: 10.0}])
    _, candidates = index.search_with_candidates("가 나 비교")
    assert [c["chunk_id"] for c in candidates] == ["c0", "c2", "c1", "c3"]
    assert [c["dense_rank"] for c in candidates] == [1, 2, 3, 4]
    assert [c["bm25_rank"] for c in candidates] == [None, None, 1, 2]


@pytest.mark.parametrize("weight,disabled", [(0, "dense"), (1, "bm25")])
def test_disabled_component_has_no_candidates_or_scores(weight, disabled):
    index = make_index(["근거"], [1])
    index.rcfg["dense_weight"] = weight
    index._dense = MagicMock(return_value={0: 0.9})
    index._sparse = MagicMock(return_value={0: 2.0})
    _, candidates = index.search_with_candidates("질문")
    assert candidates[0][f"{disabled}_rank"] is None
    assert candidates[0][f"{disabled}_score"] is None
    (index._dense if disabled == "dense" else index._sparse).assert_not_called()


@pytest.mark.parametrize("order", [[0, 1], [1, 0]])
def test_pack_keeps_richer_evidence_when_another_chunk_only_contains_its_code(order):
    index = make_index(["SFR-001", "SFR-001 응답시간은 2초 이내여야 한다"], [1, 5], budget=6)
    hits = index._pack([(i, 1.0 - rank * 0.1) for rank, i in enumerate(order)])
    assert [hit["chunk_id"] for hit in hits] == [f"c{i}" for i in order]
    assert any("2초" in hit["body"] for hit in hits)


def test_comparison_interleaves_and_skips_long_chunk_without_stopping():
    index = make_index(["SFR-001", "기관 가 두번째 내용", "SFR-001 응답시간은 2초 이내여야 한다", "기관 나 나중 항목"],
                       [3, 8, 3, 2], budget=8, doc_ids=["a", "a", "b", "b"])
    index.router.route.return_value = {"기관 가": {"a"}, "기관 나": {"b"}}
    index._rank = MagicMock(side_effect=[ranked([(0, 1.0), (1, 0.9)]), ranked([(2, 0.8), (3, 0.7)])])
    assert [hit["chunk_id"] for hit in index.search("기관 가와 기관 나 비교")] == ["c0", "c2", "c3"]


@pytest.mark.parametrize("second_body", ["SFR-001 응답시간은 2초 이내여야 한다", "SFR-001 응답시간은 2초 이내여야 합니다"])
@pytest.mark.parametrize("route", [{}, {"기관 가": {"a", "b"}}, {"기관 가": {"a"}, "기관 나": {"b"}}])
def test_search_preserves_overlapping_evidence_from_distinct_documents(second_body, route):
    index = make_index(["SFR-001 응답시간은 2초 이내여야 한다", second_body], [5, 5], budget=10, doc_ids=["a", "b"])
    for chunk in index.chunks:
        chunk.update(source=f"{chunk['doc_id']}.pdf", page=1)
    index.router.route.return_value = route
    index._rank = MagicMock(return_value=ranked([(0, 0.9), (1, 0.8)]))
    if len(route) == 2:
        index._rank.side_effect = [ranked([(0, 0.9)]), ranked([(1, 0.8)])]

    hits = index.search("기관 가와 기관 나의 SFR-001 비교")

    assert [(hit["doc_id"], hit["source"]) for hit in hits] == [("a", "a.pdf"), ("b", "b.pdf")]


@pytest.mark.parametrize("bom", ["", "\ufeff"])
def test_csv_routes_normalized_and_truncated_filenames_alongside_cover(tmp_path, bom):
    path = tmp_path / "orgs.csv"
    path.write_text(bom + "파일명,발주기관\n조달 사업 (최종).PDF,(재) 미래정보재단\n", encoding="utf-8")
    docs = [{"doc_id": "a", "source": "조달_사업.pdf", "title": "조달 사업",
             "cover_text": "발주기관: 한국철도공사", "head_text": ""}]
    router = DocRouter(docs, read_csv_orgs(path))
    assert router.route("미래정보재단 요구사항") == {"미래정보재단": {"a"}}
    assert router.route("한국철도공사 요구사항") == {"한국철도공사": {"a"}}
    assert router.route("일반 질문") == {}


@pytest.mark.parametrize("bullet", ["•", "·"])
def test_toc_bullet_markers_and_neutral_rows(bullet):
    assert parsing.TOC_MARK.search(f"| {bullet} 목 차 {bullet} |")
    assert parsing.NEUTRAL.fullmatch(f"| {bullet} -- {bullet} |")


def test_csv_full_organization_name_does_not_route_topic_words():
    docs = [{"doc_id": "a", "source": "사업.pdf", "title": "사업",
             "cover_text": "", "head_text": ""}]
    router = DocRouter(docs, {"사업.pdf": "한국 지능정보 사회진흥원"})
    assert router.route("지능정보 시스템 요구사항은?") == {}
    assert router.route("한국 지능정보 사회진흥원 요구사항은?") == {"한국 지능정보 사회진흥원": {"a"}}
    assert router.route("한국지능정보사회진흥원 요구사항은?") == {"한국지능정보사회진흥원": {"a"}}


@pytest.mark.parametrize("reverse", [False, True])
def test_csv_symbol_collision_preserves_document_organization(reverse):
    docs = [{"doc_id": did, "source": source, "title": "사업", "cover_text": "", "head_text": ""}
            for did, source in [("a", "사업-a.PDF"), ("b", "사업a.PDF")]]
    rows = [("사업-A.pdf", "기관가공사"), ("사업A.pdf", "기관나공사")]
    router = DocRouter(docs, dict(reversed(rows) if reverse else rows))
    assert router.route("기관가공사 요구사항") == {"기관가공사": {"a"}}
    assert router.route("기관나공사 요구사항") == {"기관나공사": {"b"}}


@pytest.mark.parametrize("source", ["사업_A.pdf", "사업.pdf"])
def test_csv_ambiguous_normalized_or_truncated_filename_does_not_route(source):
    docs = [{"doc_id": "a", "source": source, "title": "사업", "cover_text": "", "head_text": ""}]
    router = DocRouter(docs, {"사업-A.pdf": "기관가공사", "사업A.pdf": "기관나공사"})
    assert router.route("기관가공사와 기관나공사 요구사항") == {}


@pytest.mark.parametrize("first,second", [("사업.pdf", "사업.pdf"), ("RFP_A.pdf", "rfp_a.pdf")])
def test_csv_conflicting_duplicate_filename_is_rejected(tmp_path, first, second):
    path = tmp_path / "orgs.csv"
    path.write_text(f"파일명,발주기관\n{first},기관가공사\n{second},기관나공사\n", encoding="utf-8")
    with pytest.raises(ValueError, match=second):
        read_csv_orgs(path)


@pytest.mark.parametrize("source", ["RFP_A.pdf", "RFP-A.PDF", "RFP.pdf"])
def test_csv_filename_case_is_ignored_for_exact_normalized_and_truncated_matches(source):
    docs = [{"doc_id": "a", "source": source, "title": "사업", "cover_text": "", "head_text": ""}]
    router = DocRouter(docs, {"rfp_a.pdf": "한국정보화진흥원"})
    assert router.route("한국정보화진흥원 요구사항") == {"한국정보화진흥원": {"a"}}


def test_csv_case_only_collision_does_not_choose_an_organization():
    docs = [{"doc_id": "a", "source": "RFP_A.pdf", "title": "사업", "cover_text": "", "head_text": ""}]
    router = DocRouter(docs, {"RFP_A.pdf": "기관가공사", "rfp_a.pdf": "기관나공사"})
    assert router.route("기관가공사와 기관나공사 요구사항") == {}
