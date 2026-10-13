"""v11 입력의 본문·메타데이터를 검색용 파일로 옮기는 계약을 확인한다."""
import unicodedata

import pytest

from rag.config import read_jsonl, write_jsonl
from rag.preprocessing.chunking import load_v11_package, save_chunks


@pytest.mark.parametrize("pages", [(1, 2), (1, None), (None, None)])
def test_load_v11_package(tmp_path, pages):
    filename = unicodedata.normalize("NFD", "기관_사업.hwp")
    records = [{"doc_id": "supplier-doc", "source_paths": [filename], "search_text": text}
               for text in ["표지", "개요", "일정"]]
    elements = [{"element_id": f"e{i}", "location": {
        "page": page, "supplier_metadata": {"doc_id": "supplier-doc"}}}
        for i, page in enumerate([*pages, None])]
    chunks = [
        {"chunk_id": "c1", "spans": [{"element_id": "e0"}], "payload": "검색용 머리말\n본문",
         "body": "본문", "chunk_type": "prose", "section_path": ["사업", "개요"]},
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
    assert read_jsonl(tmp_path / "output/chunks.jsonl") == [
        {"chunk_id": "c1", "doc_id": "supplier-doc", "source": "기관_사업.hwp", "title": "기관_사업",
         "page": pages[0], "kind": "prose", "section": "사업 > 개요", "text": "검색용 머리말\n본문", "body": "본문"},
        {"chunk_id": "c2", "doc_id": "supplier-doc", "source": "기관_사업.hwp", "title": "기관_사업",
         "page": None, "kind": "table", "section": "", "text": "검색용 표", "body": "표"},
    ]
