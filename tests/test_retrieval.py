"""요구사항 코드·토큰 예산·중복 제거·기관 라우팅의 회귀를 확인한다."""
from collections import defaultdict
from unittest.mock import MagicMock

import faiss
import numpy as np
import pytest

from rag.preprocessing import parsing
from rag.retrieval.indexing import Embedder, KiwiTokenizer, find_codes
from rag.retrieval.retrieval import DocRouter, HybridIndex, read_csv_orgs


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
    index._rank = MagicMock(side_effect=[[(0, 1.0), (1, 0.9)], [(2, 0.8), (3, 0.7)]])
    assert [hit["chunk_id"] for hit in index.search("기관 가와 기관 나 비교")] == ["c0", "c2", "c3"]


@pytest.mark.parametrize("second_body", ["SFR-001 응답시간은 2초 이내여야 한다", "SFR-001 응답시간은 2초 이내여야 합니다"])
@pytest.mark.parametrize("route", [{}, {"기관 가": {"a", "b"}}, {"기관 가": {"a"}, "기관 나": {"b"}}])
def test_search_preserves_overlapping_evidence_from_distinct_documents(second_body, route):
    index = make_index(["SFR-001 응답시간은 2초 이내여야 한다", second_body], [5, 5], budget=10, doc_ids=["a", "b"])
    for chunk in index.chunks:
        chunk.update(source=f"{chunk['doc_id']}.pdf", page=1)
    index.router.route.return_value = route
    index._rank = MagicMock(return_value=[(0, 0.9), (1, 0.8)])
    if len(route) == 2:
        index._rank.side_effect = [[(0, 0.9)], [(1, 0.8)]]

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


def test_unrouted_titles_lists_documents_without_any_organization():
    docs = [{"doc_id": did, "source": f"{title}.pdf", "title": title, "cover_text": cover, "head_text": ""}
            for did, title, cover in [("a", "철도 사업", "발주기관: 한국철도공사"), ("b", "포털 사업", ""),
                                      ("c", "가 사업", "")]]
    router = DocRouter(docs, {})
    assert router.unrouted_titles() == ["가 사업", "포털 사업"]


def _fake_embedder(monkeypatch, calls, stop_at=None):
    """청크 본문 길이로 만든 가짜 임베딩. stop_at 번째 묶음에서 노트북이 중지된 것처럼 멈춘다"""
    from rag.retrieval import indexing

    def encode(texts, progress=False):
        calls.append(list(texts))
        if len(calls) == stop_at:
            raise KeyboardInterrupt
        return np.array([[len(t), 1.0] for t in texts], dtype=np.float32)

    embedder = MagicMock()
    embedder.encode.side_effect = encode
    embedder.token_counts.side_effect = lambda texts: [1] * len(texts)
    monkeypatch.setattr(indexing, "Embedder", MagicMock(return_value=embedder))
    monkeypatch.setattr(indexing, "_PART_SIZE", 2)


def _index_cfg():
    return {"embedding": {"model": "kure", "max_seq_length": 2048, "batch_size": 4}}


def test_build_index_resumes_embedding_from_checkpoint(monkeypatch, tmp_path):
    from rag.retrieval import indexing
    chunks = [{"text": f"청크 본문 {'가' * i}"} for i in range(5)]  # 묶음 3개: 2 · 2 · 1
    calls = []
    _fake_embedder(monkeypatch, calls, stop_at=2)
    with pytest.raises(KeyboardInterrupt):
        indexing.build_index(chunks, _index_cfg(), tmp_path)

    calls.clear()
    _fake_embedder(monkeypatch, calls)
    summary = indexing.build_index(chunks, _index_cfg(), tmp_path)

    assert calls == [[c["text"] for c in chunks[2:4]], [chunks[4]["text"]]]  # 첫 묶음은 저장된 결과를 읽음
    index = faiss.read_index(str(tmp_path / "faiss.index"))
    assert index.ntotal == summary["청크"] == 5
    assert index.reconstruct_n(0, 5)[:, 0].tolist() == [len(c["text"]) for c in chunks]


def test_build_index_recomputes_changed_chunks_and_drops_old_checkpoints(monkeypatch, tmp_path):
    from rag.retrieval import indexing
    chunks = [{"text": f"청크 {i}"} for i in range(4)]
    calls = []
    _fake_embedder(monkeypatch, calls)
    indexing.build_index(chunks, _index_cfg(), tmp_path)

    calls.clear()
    chunks[3] = {"text": "바뀐 청크"}
    indexing.build_index(chunks, _index_cfg(), tmp_path)

    assert calls == [["청크 2", "바뀐 청크"]]
    assert len(list((tmp_path / "checkpoint").glob("*.npy"))) == 2


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


@pytest.mark.parametrize("csv_org,question,expected", [
    ("중앙선거관리위원회", "중앙선거관리위원회 2025년도 행정정보시스템 위탁운영사업의 QUR-006은?", "중앙선거관리위원회"),
    ("케빈랩 주식회사", "케빈랩의 영상감시 시스템 하자보수 기간은?", "케빈랩"),
    ("(주)케빈랩", "케빈랩 사업 기간은?", "케빈랩"),
    ("인천공항운영서비스㈜", "인천공항운영서비스 ERP 사업의 무상보증기간은?", "인천공항운영서비스"),
    ("경상북도 봉화군", "봉화군 재난통합관리시스템의 CPU 사용률 상한은?", "봉화군"),
    ("케빈랩", "케빈랩 영상감시 시스템의 요구사항은?", "케빈랩"),
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
