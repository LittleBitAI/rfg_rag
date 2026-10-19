"""v11 입력의 본문·메타데이터를 검색용 파일로 옮기는 계약을 확인한다."""
import unicodedata

import pytest

from rag.config import read_jsonl, write_jsonl
from rag.preprocessing.chunking import chunk_summary, load_v11_package, save_chunks
from rag.retrieval.retrieval import _link_index


@pytest.mark.parametrize("pages,body,cut_rate", [
    ((1, 2), "본문", 100.0),
    ((1, None), "본문입니다.", 0.0),
    ((None, None), "본문", 100.0),
])
def test_load_v11_package(tmp_path, pages, body, cut_rate):
    filename = unicodedata.normalize("NFD", "기관_사업.hwp")
    records = [{"doc_id": "supplier-doc", "source_paths": [filename], "search_text": text}
               for text in ["표지", "개요", "일정"]]
    elements = [{"element_id": f"e{i}", "location": {
        "page": page, "supplier_metadata": {"doc_id": "supplier-doc"}}}
        for i, page in enumerate([*pages, None])]
    chunks = [
        {"chunk_id": "c1", "spans": [{"element_id": "e0"}], "payload": f"검색용 머리말\n{body}",
         "body": body, "chunk_type": "prose", "section_path": ["사업", "개요"]},
        {"chunk_id": "c2", "spans": [{"element_id": "e0"}, {"element_id": "e1"}],
         "payload": "검색용 표", "body": "표", "chunk_type": "table", "section_path": []},
        {"chunk_id": "c3", "spans": [{"element_id": "e2"}], "payload": "그림 머리말\n[IMAGE]",
         "body": " [IMAGE]\n[IMAGE] ", "chunk_type": "prose", "section_path": []},
    ]
    for name, rows in [("records", records), ("elements", elements), ("chunks", chunks)]:
        write_jsonl(rows, tmp_path / f"final_{name}.jsonl")

    docs, loaded = load_v11_package(tmp_path)
    save_chunks(docs, loaded, tmp_path / "output")

    assert read_jsonl(tmp_path / "output/docs.jsonl") == [{
        "doc_id": "supplier-doc", "source": "기관_사업.hwp", "title": "기관_사업",
        "cover_text": "표지", "head_text": "표지\n개요\n일정"}]
    saved = read_jsonl(tmp_path / "output/chunks.jsonl")
    assert saved == [
        {"chunk_id": "c1", "doc_id": "supplier-doc", "source": "기관_사업.hwp", "title": "기관_사업",
         "page": pages[0], "kind": "text", "section": "사업 > 개요", "text": f"검색용 머리말\n{body}", "body": body,
         "requirement_key": None, "requirement_ids": [], "table_refs": []},
        {"chunk_id": "c2", "doc_id": "supplier-doc", "source": "기관_사업.hwp", "title": "기관_사업",
         "page": None, "kind": "table", "section": "", "text": "검색용 표", "body": "표",
         "requirement_key": None, "requirement_ids": [], "table_refs": []},
    ]
    assert chunk_summary(saved).iloc[0]["문장 중간 절단(%)"] == cut_rate


def test_load_v11_package_links_split_requirement_and_table_chunks(tmp_path):
    """요구사항 ID 청크와 상세 내용 청크, 여러 청크로 나뉜 표가 v11 에서 읽은 그대로 02 의 연결 청크가 된다"""
    write_jsonl([{"doc_id": "d", "source_paths": ["기관_사업.hwp"], "search_text": "표지"}], tmp_path / "final_records.jsonl")
    write_jsonl([{"element_id": f"e{i}", "location": {"page": 3, "supplier_metadata": {
        "doc_id": "d", "requirement_ids": ["TST-901"] if i < 2 else []}}} for i in range(4)],
        tmp_path / "final_elements.jsonl")
    requirement = [{"payload": body, "chunk_type": "requirement_detail", "requirement_key": "TST-901"}
                   for body in ["요구사항 고유번호 | TST-901", "요구사항 상세내용 | 예시 점검 절차"]]
    table = [{"payload": body, "chunk_type": "table", "table_refs": ["t1"]} for body in ["| 구분 | 값 |", "| 응답 | 3초 |"]]
    write_jsonl([{"chunk_id": f"c{i}", "spans": [{"element_id": f"e{i}"}], "body": chunk["payload"],
                  "section_path": [], **chunk} for i, chunk in enumerate(requirement + table)],
                tmp_path / "final_chunks.jsonl")

    _, chunks = load_v11_package(tmp_path)
    code_chunks, links = _link_index(chunks)

    assert code_chunks["TST-901"] == {0, 1}
    assert links == [[1], [0], [3], [2]]
