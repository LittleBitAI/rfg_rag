"""① 전처리 — 청크 분할: 본문은 RecursiveCharacterTextSplitter(문서 단위 연결 + 페이지·섹션 추적), 표는 행 단위 분할(헤더 반복).
담당: 전처리.  결과(artifacts/chunks.jsonl · docs.jsonl)를 02 검색과 03 검증이 읽는다."""
from __future__ import annotations

import bisect
import re
import statistics
import unicodedata
from collections import Counter
from pathlib import Path

import pandas as pd
from langchain_text_splitters import RecursiveCharacterTextSplitter

from ..config import read_jsonl, write_jsonl

# 앞에 올수록 우선 분할하는 구분자 (글머리 기호는 다음 청크의 시작에 남김), 마지막 "" 는 글자 단위 안전장치
SEPARATORS = [
    r"\n\s*\n",                                   # 문단
    r"\n(?=\s*[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ][.\s])",              # Ⅰ.
    r"\n(?=\s*\d{1,2}\.\s)",                      # 1.
    r"\n(?=\s*[가-하]\.\s)",                       # 가.
    r"\n(?=\s*\(?\d{1,2}\)\s)",                   # 1)
    r"\n(?=\s*[○◦❍●]|\s*ㅇ\s)",                   # ○
    r"\n(?=\s*[□■❏◆◇▪])",                        # □
    r"\n(?=\s*[-–•·]\s?)",                        # -
    r"\n(?=\s*※)",                               # ※
    r"\n",                                        # 줄바꿈
    r"(?<=[다요함음임됨]\.)\s+|(?<=[.?!])\s+",       # 문장
    r"\s+",                                       # 공백
    "",
]

_HEADING = [  # (level, pattern, 최대 길이) — 짧은 줄만 제목으로 인정
    (1, re.compile(r"^\s*[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ][.\s]\s*\S"), 40),
    (1, re.compile(r"^\s*제\s*\d+\s*[장편]\s*\S"), 40),
    (2, re.compile(r"^\s*\d{1,2}\.\s+\S"), 30),
    (3, re.compile(r"^\s*\d{1,2}\.\d{1,2}\.?\s+\S"), 35),
    (4, re.compile(r"^\s*\d{1,2}\.\d{1,2}\.\d{1,2}\.?\s+\S"), 35),
    (4, re.compile(r"^\s*[가-하]\.\s+\S"), 22),
]


def _heading_index(full: str) -> tuple[list[int], list[str]]:
    """본문 전체에서 제목 줄 위치와 '상위 > 하위' 섹션 경로 계산"""
    offs, paths, stack, pos = [], [], {}, 0
    for ln in full.split("\n"):
        t = ln.strip()
        if t and not t.endswith(("다.", "함.", "음.", "함", "음")):
            for lvl, pat, max_len in sorted(_HEADING, key=lambda x: -x[0]):  # 1.1.1 을 1. 보다 먼저 검사
                if len(t) <= max_len and pat.match(t):
                    stack = {k: v for k, v in stack.items() if k < lvl}
                    stack[lvl] = t
                    offs.append(pos)
                    paths.append(" > ".join(stack[k] for k in sorted(stack)))
                    break
        pos += len(ln) + 1
    return offs, paths


def _split_table(md: str, size: int) -> list[str]:
    """표를 size 글자 안쪽으로 행 단위 분할, 조각마다 헤더(캡션 줄 + 헤더 2줄)를 반복"""
    lines = md.split("\n")
    i = next((k for k, ln in enumerate(lines) if ln.startswith("|---")), None)
    if i is None or len(md) <= size:
        return [md]
    head = "\n".join(lines[: i + 1])
    out, cur, cur_len = [], [], len(head)
    for r in lines[i + 1:]:
        if cur and cur_len + len(r) + 1 > size:
            out.append(head + "\n" + "\n".join(cur))
            cur, cur_len = [], len(head)
        cur.append(r)
        cur_len += len(r) + 1
    if cur:
        out.append(head + "\n" + "\n".join(cur))
    return out


def _record_texts(record: dict, splitter, size: int, table_size: int) -> list[str]:
    """표·그림 레코드 → 청크 본문들. 표는 행 단위, 셀 하나가 매우 긴 표 조각과 그림 설명은 본문 분할기로"""
    if record["kind"] == "image_caption":
        return splitter.split_text(record["text"])
    out = []
    for part in _split_table(record["text"], table_size):
        out += splitter.split_text(part) if len(part) > size + table_size else [part]
    return out


def _text_pieces(text, splitter, starts, pages, section_at, offset):
    pieces = []
    for chunk in splitter.create_documents([text]) if text.strip() else []:
        start = offset + chunk.metadata["start_index"]
        page = pages[bisect.bisect_right(starts, start) - 1]
        pieces.append((chunk.page_content, page, "text", section_at(start)))
    return pieces


def _caption_pieces(anchors, body_pieces, anchor_pieces, length, position_captions):
    if not position_captions:
        pieces = body_pieces(0, length)
        for record, offset in anchors:
            pieces += anchor_pieces(record, offset)
        return pieces
    pieces, cursor = [], 0
    for record, offset in anchors:
        pieces += body_pieces(cursor, offset)
        pieces += anchor_pieces(record, offset)
        cursor = offset
    return pieces + body_pieces(cursor, length)


def _doc_pieces(doc: dict, splitter, size: int, table_size: int, position_captions=False):
    """문서 1개 → [(본문, 쪽, kind, 섹션)]. 본문 레코드는 이어 붙여 나누고, 시작 위치로 쪽·섹션을 역추적한다.
    표·그림은 '나온 위치'(앞 본문 길이)의 섹션을 붙인다."""
    full, starts, pages, anchors = "", [], [], []
    for r in doc["records"]:
        if r["kind"] == "text":
            starts.append(len(full))
            pages.append(r["page"])
            full += r["text"] + "\n\n"
        else:
            anchors.append((r, len(full)))
    offs, paths = _heading_index(full)

    def section_at(off: int) -> str:
        i = bisect.bisect_right(offs, off) - 1
        return paths[i] if i >= 0 else ""

    def body_pieces(start, end):
        return _text_pieces(full[start:end], splitter, starts, pages, section_at, start)

    def anchor_pieces(r, off):
        section = section_at(max(off - 1, 0))
        return [(text, r["page"], r["kind"], section) for text in _record_texts(r, splitter, size, table_size)]

    return _caption_pieces(anchors, body_pieces, anchor_pieces, len(full), position_captions)


def _chunk_pieces(doc, splitter, size, table_size, ccfg, position_captions):
    positioned = position_captions and any(r["kind"] == "image_caption" for r in doc["records"])
    minimum = int(ccfg["min_chunk_chars"])
    pieces = _doc_pieces(doc, splitter, size, table_size, positioned)
    return [piece for piece in pieces
            if len(piece[0].strip()) >= (1 if positioned and piece[2] != "table" else minimum)]


def chunk_documents(docs: list[dict], ccfg: dict, *, position_captions=False) -> list[dict]:
    """청크마다 머리말 '문서: <제목> | p.N | 섹션: 1. 사업개요 > 1.1 …' 을 붙인다 (text = 머리말 + body)"""
    size = int(ccfg["chunk_size"])
    table_size = int(size * float(ccfg["table_size_factor"]))
    splitter = RecursiveCharacterTextSplitter(chunk_size=size, chunk_overlap=round(size * float(ccfg["overlap_ratio"])),
                                              separators=SEPARATORS, is_separator_regex=True, keep_separator="start",
                                              add_start_index=True, strip_whitespace=True)
    chunks = []
    for doc in docs:
        pieces = _chunk_pieces(doc, splitter, size, table_size, ccfg, position_captions)
        for i, (text, page, kind, section) in enumerate(pieces):
            header = f"문서: {doc['title']}" + (f" | p.{page}" if page else "") + (f" | 섹션: {section}" if section else "")
            chunks.append({"chunk_id": f"{doc['doc_id']}::c{i:05d}", "doc_id": doc["doc_id"], "source": doc["source"],
                           "title": doc["title"], "doc_type": doc["doc_type"], "page": page, "kind": kind,
                           "section": section, "text": header + "\n" + text.strip(), "body": text.strip()})
    return chunks


def load_v11_package(package_dir: str | Path) -> tuple[list[dict], list[dict]]:
    """v11의 저장된 청크·요소·레코드를 02 검색이 읽는 문서·청크 형식으로 옮긴다.
    요구사항 소속 정보(requirement_key · requirement_ids)도 옮겨 02 검색이 나뉜 요구사항 청크를 함께 찾게 한다."""
    package_dir = Path(package_dir)
    elements = {e["element_id"]: e for e in read_jsonl(package_dir / "final_elements.jsonl")}
    records_by_doc = {}
    for record in read_jsonl(package_dir / "final_records.jsonl"):
        records_by_doc.setdefault(record["doc_id"], []).append(record)
    docs = []
    for doc_id, records in records_by_doc.items():
        source = unicodedata.normalize("NFC", Path(records[0]["source_paths"][0]).name)
        docs.append({"doc_id": doc_id, "source": source, "title": Path(source).stem,
                     "cover_text": records[0]["search_text"],
                     "head_text": "\n".join(r["search_text"] for r in records[:3])})
    docs_by_id = {d["doc_id"]: d for d in docs}
    chunks = []
    for chunk in read_jsonl(package_dir / "final_chunks.jsonl"):
        if re.fullmatch(r"(?:\s*\[IMAGE\]\s*)+", chunk["body"]):
            continue
        linked = [elements[span["element_id"]]["location"] for span in chunk["spans"]]
        doc = docs_by_id[linked[0]["supplier_metadata"]["doc_id"]]
        pages = {element["page"] for element in linked}
        requirement_ids = [rid for location in linked for rid in location["supplier_metadata"].get("requirement_ids", [])]
        chunks.append({"chunk_id": chunk["chunk_id"], "doc_id": doc["doc_id"],
                       "source": doc["source"], "title": doc["title"],
                       "page": next(iter(pages)) if len(pages) == 1 else None,
                       "kind": "text" if chunk["chunk_type"] == "prose" else chunk["chunk_type"],
                       "section": " > ".join(chunk["section_path"]),
                       "text": chunk["payload"], "body": chunk["body"],
                       # 요구사항 소속: 청크가 속한 요구사항(ID 와 상세 내용이 다른 청크여도 같은 값)과 요소들이 속한 요구사항 ID
                       "requirement_key": chunk.get("requirement_key"),
                       "requirement_ids": list(dict.fromkeys(requirement_ids))})
    return docs, chunks


def save_chunks(docs: list[dict], chunks: list[dict], out_dir: Path):
    """02 검색·03 검증으로 넘기는 파일: chunks.jsonl, docs.jsonl(기관 라우팅용 문서 목록 — 레코드 제외)"""
    write_jsonl(chunks, out_dir / "chunks.jsonl")
    write_jsonl([{k: v for k, v in d.items() if k != "records"} for d in docs], out_dir / "docs.jsonl")


def chunk_summary(chunks: list[dict]) -> pd.DataFrame:
    """청크 품질 지표: 종류별 개수 · 길이 · 문장 중간 절단 비율 · 섹션 부착률"""
    body = [c for c in chunks if c["kind"] == "text"]
    cut = sum(1 for c in body if not re.search(r"(?:[.?!:;)\]」』%]|[다요음함임됨])\s*$", c["body"]))
    lens = [len(c["body"]) for c in chunks]
    return pd.DataFrame([{"청크 수": len(chunks), **Counter(c["kind"] for c in chunks),
                          "평균 길이": round(statistics.mean(lens), 1), "중앙값": int(statistics.median(lens)),
                          "문장 중간 절단(%)": round(100 * cut / max(len(body), 1), 1),
                          "섹션 부착(%)": round(100 * sum(bool(c["section"]) for c in chunks) / len(chunks), 1)}])
