"""요구사항 코드·토큰 예산·중복 제거·기관 라우팅의 회귀를 확인한다."""
from unittest.mock import MagicMock

import numpy as np
import pytest

from rag.preprocessing import parsing
from rag.retrieval.indexing import Embedder, KiwiTokenizer, find_codes, search_texts, texts_digest
from rag.retrieval.retrieval import DocRouter, HybridIndex, _check_index, _link_index, read_csv_orgs


def ranked(pairs):
    return [{"index": i, "score": score, "dense_score": score, "dense_rank": rank,
             "bm25_score": None, "bm25_rank": None, "exact_code_match": False}
            for rank, (i, score) in enumerate(pairs, 1)]


def make_index(bodies, costs, budget=2500, doc_ids=None, requirements=None, tables=None):
    index = HybridIndex.__new__(HybridIndex)
    doc_ids = doc_ids or ["doc-a"] * len(bodies)
    requirements = requirements or [None] * len(bodies)
    tables = tables or [[] for _ in bodies]
    index.chunks = [{"chunk_id": f"c{i}", "doc_id": doc, "text": body, "body": body,
                     "requirement_key": req, "requirement_ids": [req] if req else [], "table_refs": table}
                    for i, (body, doc, req, table) in enumerate(zip(bodies, doc_ids, requirements, tables))]
    index.doc_ids = np.array(doc_ids)
    index.code_chunks, index.links = _link_index(index.chunks)
    index.rcfg = {"token_budget": budget, "dense_weight": 0.6, "candidate_k": 50}
    index.chunk_file = "fixture/chunks.jsonl"
    index.embedder = MagicMock()
    index.embedder.token_counts.side_effect = lambda texts: [costs[bodies.index(text)] for text in texts]
    index.router = MagicMock()
    index.router.route.return_value = {}
    index.router.focus.side_effect = lambda query, org, doc_ids: query
    index.router.prefer.return_value = set()
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


def test_kiwi_batch_and_query_keep_dictionary_aliases_negation_and_codes_without_noise():
    tokenizer = KiwiTokenizer()
    texts = ["지체 상금과 부가세 SFR-001은 제출하지 않는다", "부가 가치세는 대상이 아니다",
             "SFR-001A와 SFR-001B의 응답시간",
             "경기도사회서비스원 개인정보처리시스템 구축 및 운영을 하며 지원할 수 있다. 대상 등이 된다."]
    tokens = tokenizer.batch(texts)
    assert tokens == [tokenizer(text) for text in texts]
    assert {"지체상금", "부가가치세", "sfr-001", "않"} <= set(tokens[0])
    assert {"부가가치세", "아니"} <= set(tokens[1])
    assert "sfr-001" not in tokens[2]
    assert {"경기도사회서비스원", "개인정보처리시스템", "구축", "운영", "지원"} <= set(tokens[3])
    assert not {"및", "하", "되", "등", "수"} & set(tokens[3])
    assert "있" in tokens[3]


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
    expected_query = question if query is None else query
    index.router.route.assert_called_once_with(expected_query)
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


def test_shared_document_candidates_keep_each_occurrence_rank_before_packing():
    index = make_index(["가 첫 근거", "공동 근거", "나 첫 근거"], [1] * 3,
                       doc_ids=["a", "shared", "b"])
    index.router.route.return_value = {"가": {"a", "shared"}, "나": {"b", "shared"}}
    index._dense = MagicMock(side_effect=[{0: 0.9, 1: 0.8}, {2: 0.9, 1: 0.8}])
    index._sparse = MagicMock(return_value={})
    hits, candidates = index.search_with_candidates("가 나 비교")
    assert [c["chunk_id"] for c in candidates] == ["c0", "c2", "c1", "c1"]
    assert [c["dense_rank"] for c in candidates] == [1, 2, 3, 4]
    assert [c["fused_rank"] for c in candidates] == [1, 2, 3, 4]
    assert [h["chunk_id"] for h in hits] == ["c0", "c2", "c1"]


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


# 요구사항 ID · 명칭 청크와 상세 내용 청크가 나뉜 전처리 패키지 사례 (서민금융진흥원 SER-001)
_SPLIT_REQUIREMENT = ["요구사항 고유번호 | SER-001 / 요구사항 명칭 | 보안관리 및 규정 준수",
                      "요구사항 상세내용 | 누출금지 대상정보는 내·외부 IP주소 현황, 정보통신망 구성도",
                      "다른 요구사항 상세 내용", "다른 문서의 같은 코드 상세 내용"]


def test_detail_chunk_without_id_text_matches_its_requirement_code():
    index = make_index(_SPLIT_REQUIREMENT, [5, 5, 5, 5], doc_ids=["a", "a", "a", "b"],
                       requirements=["SER-001", "SER-001", None, "SER-001"])
    index.router.route.return_value = {"서민금융진흥원": {"a"}}
    index._dense = MagicMock(return_value={2: 1.0})
    index._sparse = MagicMock(return_value={2: 1.0})

    hits = index.search("서민금융진흥원 SER-001 누출금지 대상정보")

    assert [hit["chunk_id"] for hit in hits] == ["c0", "c1", "c2"]  # 다른 문서(b)의 SER-001 은 라우팅으로 제외


@pytest.mark.parametrize("found", [0, 1])
def test_pack_adds_other_chunks_of_the_same_requirement_right_after_the_found_one(found):
    index = make_index(_SPLIT_REQUIREMENT, [5, 5, 5, 5], doc_ids=["a", "a", "a", "b"],
                       requirements=["SER-001", "SER-001", None, "SER-001"])

    hits = index._pack([(found, 0.9), (2, 0.5)])

    assert [hit["chunk_id"] for hit in hits] == [f"c{found}", f"c{1 - found}", "c2"]
    assert hits[1]["score"] == 0.9


def test_requirement_chunks_still_respect_token_budget():
    index = make_index(_SPLIT_REQUIREMENT, [5, 30, 5, 5], budget=12, doc_ids=["a", "a", "a", "b"],
                       requirements=["SER-001", "SER-001", None, "SER-001"])

    assert [hit["chunk_id"] for hit in index._pack([(0, 0.9), (2, 0.5)])] == ["c0", "c2"]


def test_split_table_chunks_are_linked_but_long_tables_are_not():
    tables = [["t1"], ["t1"], *[["long"]] * 7]
    index = make_index([f"표 {i}" for i in range(9)], [1] * 9, tables=tables)

    assert index.links[0] == [1] and index.links[1] == [0]
    assert all(index.links[i] == [] for i in range(2, 9))
    assert [hit["chunk_id"] for hit in index._pack([(1, 0.9)])] == ["c1", "c0"]


def test_linked_chunks_stop_at_link_token_cap():
    index = make_index(["ID 청크", "상세 하나", "상세 둘"], [5, 400, 400], requirements=["SER-001"] * 3)

    assert [hit["chunk_id"] for hit in index._pack([(0, 0.9)])] == ["c0", "c1"]  # 400 + 400 > 600


_REQUIREMENT_CHUNKS = [
    {"doc_id": "a", "text": "요구사항 고유번호 | SER-001\n요구사항 명칭 | 보안관리 및 규정 준수", "requirement_key": "SER-001"},
    {"doc_id": "a", "text": "요구사항 상세내용 | 누출금지 대상정보는 IP주소 현황", "requirement_key": "SER-001"},
    {"doc_id": "a", "text": "일반 본문", "requirement_key": None}]


def test_search_texts_label_detail_chunks_with_their_requirement_id_and_name():
    assert search_texts(_REQUIREMENT_CHUNKS) == [
        _REQUIREMENT_CHUNKS[0]["text"],  # ID · 명칭이 이미 있으면 그대로
        "[요구사항 SER-001 보안관리 및 규정 준수]\n요구사항 상세내용 | 누출금지 대상정보는 IP주소 현황",
        "일반 본문"]


def test_index_built_from_other_texts_is_rejected(tmp_path):
    texts = search_texts(_REQUIREMENT_CHUNKS)
    (tmp_path / "texts.sha256").write_text(texts_digest(texts), encoding="utf-8")
    _check_index(tmp_path, texts)
    with pytest.raises(ValueError, match="02"):
        _check_index(tmp_path, [c["text"] for c in _REQUIREMENT_CHUNKS])


_SHARED = "제안사는 사용자 요청 시점부터 화면 표시까지의 처리 기준을 아래와 같이 준수하여야 하며 측정 결과를 보고한다"


@pytest.mark.parametrize("first,second", [
    (f"{_SHARED} 응답시간은 2초 이내", f"{_SHARED} 응답시간은 5초 이내"),
    (f"{_SHARED} 계약금액은 부가가치세를 포함한다", f"{_SHARED} 계약금액은 부가가치세를 포함하지 않는다"),
], ids=["2초-5초", "포함한다-포함하지않는다"])
def test_pack_keeps_same_document_evidence_with_different_number_or_negation(first, second):
    index = make_index([first, second], [5, 5], budget=10)
    assert [hit["chunk_id"] for hit in index._pack([(0, 0.9), (1, 0.8)])] == ["c0", "c1"]


def test_pack_still_drops_same_document_duplicate_with_same_number_and_negation():
    index = make_index([f"{_SHARED} 응답시간은 2초 이내", f"{_SHARED} 응답시간은 2초 이내로"], [5, 5], budget=10)
    assert [hit["chunk_id"] for hit in index._pack([(0, 0.9), (1, 0.8)])] == ["c0"]


def test_unrouted_titles_lists_documents_without_any_organization():
    docs = [{"doc_id": did, "source": f"{title}.pdf", "title": title, "cover_text": cover, "head_text": ""}
            for did, title, cover in [("a", "철도 사업", "발주기관: 한국철도공사"), ("b", "포털 사업", ""),
                                      ("c", "가 사업", "")]]
    assert DocRouter(docs, {}).unrouted_titles() == ["가 사업", "포털 사업"]


@pytest.mark.parametrize("csv_org,question,expected", [
    ("중앙선거관리위원회", "중앙선거관리위원회 2025년도 행정정보시스템 위탁운영사업의 QUR-006은?", "중앙선거관리위원회"),
    ("케빈랩 주식회사", "케빈랩의 영상감시 시스템 하자보수 기간은?", "케빈랩"),
    ("(주)케빈랩", "케빈랩 사업 기간은?", "케빈랩"),
    ("인천공항운영서비스㈜", "인천공항운영서비스 ERP 사업의 무상보증기간은?", "인천공항운영서비스"),
    ("경상북도 봉화군", "봉화군 재난통합관리시스템의 CPU 사용률 상한은?", "봉화군"),
    ("경희대학교 산학협력단", "경희대학교 정보시스템 운영 용역의 범위는?", "경희대학교"),
    ("아시아물위원회 사무국", "아시아물위원회 스마트 관개시스템 사업 기간은?", "아시아물위원회"),
    ("재단법인 예술경영지원센터", "예술경영지원센터 사전 컨설팅 범위는?", "예술경영지원센터"),
])
def test_csv_organization_names_route_without_generic_filter(csv_org, question, expected):
    docs = [{"doc_id": "a", "source": "사업.hwp", "title": "사업", "cover_text": "", "head_text": ""}]
    assert DocRouter(docs, {"사업.hwp": csv_org}).route(question) == {expected: {"a"}}


@pytest.mark.parametrize("csv_org,question", [
    ("인천광역시 동구", "이동구간 요구사항은?"),
    ("인천광역시 동구", "인천광역시 도시계획위원회 통합관리시스템 요구사항은?"),   # 광역 지자체만 나온 질문
    ("경희대학교 산학협력단", "서영대학교 산학협력단 사업 기간은?"),               # 하위 조직 일반명
    ("대한적십자사 의료원", "국립중앙의료원 응급의료 시스템 요구사항은?"),
])
def test_csv_province_or_generic_word_alone_does_not_route(csv_org, question):
    docs = [{"doc_id": "a", "source": "사업.hwp", "title": "사업", "cover_text": "", "head_text": ""}]
    assert DocRouter(docs, {"사업.hwp": csv_org}).route(question) == {}


def test_route_keeps_every_document_of_organization_even_if_question_matches_other_title():
    docs = [{"doc_id": did, "source": f"{did}.hwp", "title": title, "cover_text": "", "head_text": ""}
            for did, title in [("rec", "국방과학연구소 기록관리시스템 통합 활용"), ("big", "국방과학연구소 대용량 자료전송시스템 고도화")]]
    router = DocRouter(docs, {"rec.hwp": "국방과학연구소", "big.hwp": "국방과학연구소"})
    assert router.route("국방과학연구소 기록관리 시스템의 대용량 전송 예외는?") == {"국방과학연구소": {"rec", "big"}}


def test_csv_name_also_routes_other_documents_whose_title_mentions_it():
    docs = [{"doc_id": did, "source": f"{did}.hwp", "title": title, "cover_text": "", "head_text": ""}
            for did, title in [("bus", "평택시 버스정보시스템"), ("cctv", "평택시 스마트시티 영상감시")]]
    router = DocRouter(docs, {"bus.hwp": "경기도 평택시", "cctv.hwp": "케빈랩 주식회사"})
    assert router.route("평택시 스마트시티 영상감시 요구사항은?") == {"평택시": {"bus", "cctv"}}


@pytest.mark.parametrize("source,csv_org,question,expected", [
    ("KOICA 전자조달_우즈베키스탄 의정활동.hwp", "한국국제협력단", "KOICA 우즈베키스탄 사업은?", "KOICA"),
    ("KOICA 전자조달_우즈베키스탄 의정활동.hwp", "한국국제협력단", "한국국제협력단 우즈베키스탄 사업은?", "한국국제협력단"),
    ("수협중앙회_상황관제시스템 구축.hwp", "수산업협동조합중앙회", "수협중앙회 상황관제시스템은?", "수협중앙회"),
    ("(사）한국대학스포츠협의회_KUSF 시스템.hwp", "한국대학스포츠협의회", "한국대학스포츠협의회 KUSF 시스템은?",
     "한국대학스포츠협의회"),
])
def test_csv_official_name_and_filename_common_name_both_route(source, csv_org, question, expected):
    docs = [{"doc_id": "a", "source": source, "title": source.rsplit(".", 1)[0], "cover_text": "", "head_text": ""}]
    assert DocRouter(docs, {source: csv_org}).route(question) == {expected: {"a"}}


def test_comparison_gives_each_organization_its_own_budget_and_query():
    index = make_index(["가 기관 근거 하나", "가 기관 근거 둘", "나 기관 근거 하나", "나 기관 근거 둘"], [5, 5, 5, 5],
                       budget=10, doc_ids=["a", "a", "b", "b"])
    index.router.route.return_value = {"고려대학교": {"a"}, "광주과학기술원": {"b"}}
    index._rank = MagicMock(side_effect=[ranked([(0, 0.9), (1, 0.8)]), ranked([(2, 0.7), (3, 0.6)])])

    hits = index.search("고려대학교와 광주과학기술원의 추가 교육 비교")

    assert [hit["chunk_id"] for hit in hits] == ["c0", "c2", "c1", "c3"]  # 예산을 나눠 쓰면 2개만 담겼다
    queries = [c.args[0] for c in index._rank.call_args_list]
    assert "광주과학기술원" not in queries[0] and "고려대학교" in queries[0]
    assert "고려대학교" not in queries[1] and "광주과학기술원" in queries[1]


def test_organizations_pointing_to_the_same_document_are_merged():
    docs = [{"doc_id": "jst", "source": "jst.hwp", "title": "전북대학교_JST 공유대학(원) xAPI기반 LRS시스템 구축",
             "cover_text": "전북대학교", "head_text": ""},
            {"doc_id": "v", "source": "v.hwp", "title": "(사)벤처기업협회_벤처확인종합관리시스템 기능 고도화",
             "cover_text": "벤처기업협회", "head_text": ""}]
    router = DocRouter(docs, {})
    router.org_docs = {"전북대학교": {"jst"}, "공유대학": {"jst"}, "벤처기업협회": {"v"}}

    route = router.route("벤처기업협회와 전북대학교 JST 공유대학의 연계 데이터 비교")

    assert sorted(route.values(), key=sorted) == [{"jst"}, {"v"}]
    assert any("전북대학교" in org and "공유대학" in org for org in route)


_KOREA_DEFENSE = [{"doc_id": "records", "title": "국방과학연구소_기록관리시스템 통합 활용 및 보안 환경 구축"},
                  {"doc_id": "transfer", "title": "국방과학연구소_대용량 자료전송시스템 고도화"},
                  {"doc_id": "x", "title": "다른기관_통합 시스템 구축"}, {"doc_id": "y", "title": "또다른기관_보안 고도화 구축"}]


@pytest.mark.parametrize("question,expected", [
    # 띄어 써도 '기록관리시스템'(7자)이 '대용량'(3자)보다 길게 맞아 기록관리 사업을 앞세운다
    ("국방과학연구소 기록관리 시스템의 응답시간과 대용량 전송 예외는?", {"records"}),
    ("국방과학연구소 대용량 자료전송시스템의 전송 속도는?", {"transfer"}),
    ("국방과학연구소 사업의 보안 요구사항은?", set()),  # 사업명이 없으면 앞세우지 않는다
])
def test_project_name_in_question_picks_the_document_to_put_first(question, expected):
    router = DocRouter([{**d, "source": f"{d['doc_id']}.hwp", "cover_text": "", "head_text": ""} for d in _KOREA_DEFENSE], {})
    assert router.prefer(question, {"records", "transfer"}) == expected


def test_preferred_project_candidates_come_first_and_keep_their_dense_rank():
    index = make_index(["기록관리 근거", "대용량 근거"], [5, 5], budget=10, doc_ids=["records", "transfer"])
    index.router.route.return_value = {"국방과학연구소": {"records", "transfer"}}
    index.router.prefer.return_value = {"records"}
    index._dense = MagicMock(return_value={1: 0.9, 0: 0.2})
    index._sparse = MagicMock(return_value={})

    hits, candidates = index.search_with_candidates("국방과학연구소 기록관리 시스템 응답시간")

    assert [hit["chunk_id"] for hit in hits] == ["c0", "c1"]
    assert [(c["chunk_id"], c["dense_rank"]) for c in candidates] == [("c0", 2), ("c1", 1)]


_FOCUS_DOCS = [{"doc_id": "lms", "title": "재단법인스포츠윤리센터_스포츠윤리센터 LMS(학습지원시스템) 기능개선"},
               {"doc_id": "erp", "title": "한국어촌어항공단_한국어촌어항공단 경영관리시스템(ERP·GW) 기능 고도"},
               {"doc_id": "x", "title": "다른기관_통합 시스템 구축"}]


@pytest.mark.parametrize("question,org,doc,expected", [
    ("스포츠윤리센터의 「스포츠윤리센터 LMS(학습지원시스템) 기능개선」 사업에서 하자보증 기간은 얼마인가?",
     "스포츠윤리센터", "lms", "사업에서 하자보증 기간은 얼마인가?"),
    # 사업명 낱말이 본문에서 다시 나오면('ERP 행') 남긴다
    ("한국어촌어항공단의 「한국어촌어항공단 경영관리시스템(ERP·GW) 기능 고도」 사업에서 ERP 행의 내용 열은 무엇인가?",
     "한국어촌어항공단", "erp", "사업에서 ERP 행의 내용 열은 무엇인가?"),
    # 빼면 낱말이 거의 안 남는 질문은 그대로
    ("스포츠윤리센터 LMS 기능개선 사업", "스포츠윤리센터", "lms", "스포츠윤리센터 LMS 기능개선 사업"),
])
def test_focus_drops_the_organization_and_project_mention(question, org, doc, expected):
    router = DocRouter([{**d, "source": f"{d['doc_id']}.hwp", "cover_text": "", "head_text": ""} for d in _FOCUS_DOCS], {})
    assert router.focus(question, org, {doc}) == expected


def test_routed_search_ranks_with_the_focused_query():
    index = make_index(["근거"], [1])
    index.router.route.return_value = {"스포츠윤리센터": {"doc-a"}}
    index.router.focus.side_effect = lambda query, org, doc_ids: "하자보증 기간은 얼마인가?"
    index._rank = MagicMock(return_value=ranked([(0, 1.0)]))

    index.search("스포츠윤리센터의 「LMS 기능개선」 사업에서 하자보증 기간은 얼마인가?")

    assert index._rank.call_args.args[0] == "하자보증 기간은 얼마인가?"


def test_reranker_reorders_top_candidates_packs_only_them_and_keeps_every_candidate_in_the_snapshot():
    index = make_index(["SFR-001 코드 근거", "하이브리드 1위", "하이브리드 2위", "하이브리드 3위"], [1, 1, 1, 1])
    index.texts = [c["text"] for c in index.chunks]
    index.rcfg["rerank"] = {"top_n": 3}
    index._dense = MagicMock(return_value={1: 1.0, 2: 0.5, 3: 0.1})
    index._sparse = MagicMock(return_value={})
    index.reranker = MagicMock()
    index.reranker.scores.return_value = [0.1, 0.2, 0.9]

    hits, candidates = index.search_with_candidates("SFR-001 질문", query="SFR-001 재작성 질문")

    index.reranker.scores.assert_called_once_with("SFR-001 재작성 질문",
                                                  ["SFR-001 코드 근거", "하이브리드 1위", "하이브리드 2위"])
    assert [(h["chunk_id"], h["score"]) for h in hits] == [("c0", 0.1), ("c2", 0.9), ("c1", 0.2)]
    assert [(c["chunk_id"], c["fused_rank"], c["dense_rank"], c["exact_code_match"]) for c in candidates] == [
        ("c0", 1, None, True), ("c2", 2, 2, False), ("c1", 3, 1, False), ("c3", 4, 3, False)]


def test_reranker_is_skipped_when_routed_documents_have_no_candidates():
    index = make_index(["다른 기관 근거"], [1], doc_ids=["doc-b"])
    index._dense = MagicMock(return_value={})
    index._sparse = MagicMock(return_value={})
    index.reranker = MagicMock()

    assert index._rank("질문", set(), {"doc-a"}) == []
    index.reranker.scores.assert_not_called()


def test_reranker_scores_question_chunk_pairs(monkeypatch):
    from rag.retrieval import indexing
    cross_encoder = MagicMock()
    cross_encoder.return_value.predict.return_value = np.array([0.7, 0.2])
    monkeypatch.setattr(indexing, "CrossEncoder", cross_encoder)
    monkeypatch.setattr(indexing.torch.cuda, "is_available", lambda: False)

    reranker = indexing.Reranker({"model": "reranker", "batch_size": 4, "max_length": 512})

    assert reranker.scores("질문", ["청크1", "청크2"]) == [0.7, 0.2]
    cross_encoder.assert_called_once_with("reranker", device="cpu", max_length=512)
    cross_encoder.return_value.predict.assert_called_once_with([("질문", "청크1"), ("질문", "청크2")], batch_size=4)
