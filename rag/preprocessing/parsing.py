"""① 전처리 — 문서 파싱: ZIP 풀기 → PDF(pypdf 본문 · PyMuPDFLoader 표·그림) · HWP/HWPX(HwpHwpxLoader) → 정리 → (선택) OCR.
담당: 전처리.  문서마다 레코드(text / table / image_caption) 목록을 만들고, chunking.py 가 이것을 청크로 나눈다."""
from __future__ import annotations

import hashlib
import io
import json
import math
import os
import re
import shutil
import struct
import tempfile
import unicodedata
import zipfile
from collections import Counter
from itertools import groupby
from pathlib import Path

import hanja
import numpy as np
import pandas as pd

from ..usage import UsageCallback

SUPPORTED = (".pdf", ".hwp", ".hwpx")


# ====================================================================================================
# 입력: ZIP(중첩 ZIP 포함) 또는 폴더 → 문서 경로
# ====================================================================================================
def _zip_name(info: zipfile.ZipInfo) -> str:
    """ZIP 안 한국어 파일명 보정: UTF-8 플래그가 없으면 cp949 로 해석"""
    if info.flag_bits & 0x800:
        return info.filename
    raw = info.filename.encode("cp437", errors="ignore")
    for enc in ("utf-8", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return info.filename


def _safe_name(name: str, max_bytes: int = 200) -> str:
    """ZIP 속 파일명 정리.
    ① 맥(macOS)에서 만든 ZIP 은 한글이 자모 분리형(NFD)이라 '국' 한 글자가 9바이트 → 리눅스 파일명 한도(255바이트) 초과
       (Errno 36 File name too long). 윈도우는 글자 수 기준이라 문제가 안 됨 → 완성형(NFC)으로 변환
    ② 그래도 길면 확장자는 살리고 앞부분만 max_bytes 까지 자름"""
    name = unicodedata.normalize("NFC", name)
    if len(name.encode("utf-8")) <= max_bytes:
        return name
    stem, ext = os.path.splitext(name)
    b = stem.encode("utf-8")[: max_bytes - len(ext.encode("utf-8"))]
    return b.decode("utf-8", "ignore").rstrip() + ext


def _extract(zf: zipfile.ZipFile, info: zipfile.ZipInfo, out_dir: str) -> str | None:
    """ZIP 항목 하나를 out_dir 에 풀고 경로를 돌려준다. 폴더·맥 부속 파일·지원하지 않는 형식은 None"""
    name = _zip_name(info)
    base = _safe_name(re.sub(r'[<>:"|?*\x00-\x1f]', "_", name.replace("\\", "/").split("/")[-1]).strip())
    if info.is_dir() or "__MACOSX" in name or base.startswith("._") or not base.lower().endswith(SUPPORTED + (".zip",)):
        return None
    dst = os.path.join(out_dir, base)  # 경로 성분을 버려 zip-slip 방지
    if not (os.path.exists(dst) and os.path.getsize(dst) == info.file_size):  # 이미 풀린 파일은 다시 풀지 않음
        with zf.open(info) as src, open(dst, "wb") as out:
            shutil.copyfileobj(src, out)
    return dst


def collect_inputs(src, out_dir) -> list[str]:
    """ZIP(중첩 ZIP 포함) 또는 폴더 → PDF·HWP·HWPX 경로 목록. ZIP 은 out_dir 에 푼다."""
    src, out_dir = str(src), str(out_dir)
    if os.path.isdir(src):
        paths = [os.path.join(root, n) for root, _, names in os.walk(src) for n in sorted(names)]
    elif src.lower().endswith(".zip"):
        os.makedirs(out_dir, exist_ok=True)
        with zipfile.ZipFile(src) as zf:
            paths = [p for p in (_extract(zf, info, out_dir) for info in zf.infolist()) if p]
    else:
        paths = [src]
    files = []
    for p in paths:
        if p.lower().endswith(".zip"):
            files += collect_inputs(p, os.path.join(out_dir, os.path.basename(p)[:-4]))
        elif p.lower().endswith(SUPPORTED):
            files.append(p)
    return sorted(files)


def make_doc_id(path: str) -> str:
    stem = os.path.splitext(os.path.basename(path))[0]
    slug = re.sub(r"[^\w가-힣]+", "_", stem).strip("_")[:40]
    return f"{slug}_{hashlib.sha1(os.path.basename(path).encode()).hexdigest()[:6]}"


def _title(path: str) -> str:
    stem = os.path.splitext(os.path.basename(path))[0]
    return re.sub(r"[_]+", " ", stem).strip()


# ====================================================================================================
# 공통 정리: 정규화 · 한자 독음
# ====================================================================================================
_HANJA_RUN = re.compile(r"[㐀-䶿一-鿿豈-﫿\U00020000-\U0002A6DF]+")
_COMPAT_IDEO = re.compile(r"[豈-﫿\U0002F800-\U0002FA1F]")
_WS = re.compile(r"[ \t 　]+")


def normalize_text(text: str) -> str:
    """HWP/PDF 공통 정규화.
    - CJK 호환 한자(U+F900~)만 NFKC 로 통합 한자로 매핑 (전체 NFKC 는 'ㅇ' 같은 호환 자모를 깨뜨리므로 금지)
    - 공백 정리, 3줄 이상 빈 줄 축소
    """
    if not text:
        return ""
    text = text.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "replace")  # 깨진 서로게이트 제거
    text = _COMPAT_IDEO.sub(lambda m: unicodedata.normalize("NFKC", m.group()), text)
    text = text.replace("\r", "\n").replace("\x00", "")
    text = "\n".join(_WS.sub(" ", ln).strip() for ln in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def apply_hanja(text: str, mode: str) -> str:
    """mode: none | append('必(필)') | replace('필')"""
    if mode == "none" or not _HANJA_RUN.search(text):
        return text

    def _sub(m: re.Match) -> str:
        run = m.group()
        reading = hanja.translate(run, "substitution")
        if reading == run:
            return run
        if mode == "replace":
            return reading
        # 이미 '契約(계약)' 형태로 병기돼 있으면 그대로 둠
        tail = text[m.end(): m.end() + len(reading) + 2]
        if tail.startswith(f"({reading}"):
            return run
        return f"{run}({reading})"

    return _HANJA_RUN.sub(_sub, text)


# ====================================================================================================
# PDF 정리: 머리글·쪽번호·본문에 섞인 표·끊긴 줄·깨진 글머리
# ====================================================================================================
def _remove_repeated_lines(pages: dict[int, str], ratio: float) -> dict[int, str]:
    """페이지의 ratio 이상(최소 3페이지)에 반복되는 짧은 줄 = 머리글/바닥글 → 제거"""
    if len(pages) < 3:
        return pages
    key = lambda ln: re.sub(r"\d+", "#", re.sub(r"\s+", "", ln))  # noqa: E731  페이지 번호 무시
    cnt = Counter()
    for txt in pages.values():
        cnt.update({key(ln) for ln in txt.split("\n") if 0 < len(ln.strip()) < 120})
    thr = max(3, math.ceil(ratio * len(pages)))
    bad = {k for k, c in cnt.items() if c >= thr and k}
    return {p: "\n".join(ln for ln in txt.split("\n") if not (ln.strip() and key(ln) in bad)) for p, txt in pages.items()}


_PAGE_NO = re.compile(r"^\s*(?:[-–−]\s*\d{1,3}\s*[-–−]|\d{1,3}\s*/\s*\d{1,3}|페\s*이\s*지\s*:?\s*\d+\s*/\s*\d+"
                      r"|page\s*\d+(?:\s*of\s*\d+)?|\d{1,3})\s*$", re.IGNORECASE)
_END_OK = re.compile(r"(?:[.?!:;。)\]」』>’”\"'%]|[다요음함임됨것니까죠])\s*$")
_START_MARK = re.compile(r"^\s*(?:[○◦❍●•·▪■□◆◇※\-–▶▷►❏✓√]|ㅇ\s|\(?\d{1,2}[\).]\s*\S|\d+\.\d+|[가-하][\).]\s+\S"
                         r"|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]|[①-⑳]|[A-Z]{2,5}-[\w가-힣]*\d|\||<|\[|【)")


def _remove_page_numbers(text: str) -> str:
    return "\n".join(ln for ln in text.split("\n") if not (ln.strip() and _PAGE_NO.match(ln)))


def _join_broken_lines(text: str, min_len: int) -> str:
    """PDF 줄바꿈으로 끊긴 문장 복원: 앞 줄이 문장 종결이 아니고 다음 줄이 글머리(○, -, 1), 가. …)가 아니면 이어붙임"""
    out: list[str] = []
    for ln in text.split("\n"):
        if (out and out[-1].strip() and ln.strip() and len(out[-1].strip()) >= min_len
                and not _END_OK.search(out[-1]) and not _START_MARK.match(ln)):
            out[-1] = out[-1].rstrip() + " " + ln.strip()
        else:
            out.append(ln)
    return "\n".join(out)


def _drop_table_lines(text: str, tables: list[str], threshold: float, min_tokens: int = 3) -> str:
    """pypdf 본문에 평문으로 섞여 들어간 표 내용을 제거 (표는 Markdown 청크로 따로 있음).
    PDF 는 여러 줄 셀이 줄 단위로 섞여 나오므로(셀1 1행 + 셀2 1행 …) 부분문자열이 아니라
    '줄의 토큰 중 표 셀 토큰 비율'로 판단한다."""
    vocab = {w for t in tables for c in _table_cells(t) for w in c.split() if len(w) >= 2}
    if not vocab:
        return text
    kept = []
    for ln in text.split("\n"):
        toks = [w for w in ln.split() if len(w) >= 2]
        if not (len(toks) >= min_tokens and sum(w in vocab for w in toks) / len(toks) >= threshold):
            kept.append(ln)
    return "\n".join(kept)


_BULLET_GLYPHS = re.compile(r"[\u0178\uf000\uf0a7\uf0b7\uf0d8\uf06c\uf09f\uf0fc\uf076]")  # PDF 폰트 깨진 글머리(Ÿ 등)


def _fix_bullets(text: str) -> str:
    return _BULLET_GLYPHS.sub("•", text)


_IMG_MD = re.compile(r"!\[(.*?)\]\(#\)", re.DOTALL)
_IMG_MARK = re.compile(r"\[IMAGE(?::\s*([^\]]+))?\]")
_IMG_LINE = re.compile(r"\s*\[\[IMG:(\d+)\]\]\s*")


def _md_table_blocks(text: str) -> list[str]:
    """페이지 텍스트 → Markdown 표 블록들 (두 줄 이상 이어진 '|' 줄 묶음)"""
    blocks = ["\n".join(ln.strip() for ln in group)
              for is_table, group in groupby(text.split("\n"), key=lambda ln: ln.lstrip().startswith("|")) if is_table]
    return [b for b in blocks if b.count("\n") >= 1]


def _table_cells(md: str) -> list[str]:
    rows = [r for r in md.split("\n") if not re.fullmatch(r"[\s|:\-]+", r)]
    return [c.strip().replace("<br>", " ") for r in rows for c in r.strip().strip("|").split("|") if c.strip()]


# ====================================================================================================
# PDF: 본문은 pypdf, 표(Markdown)와 그림은 LangChain PyMuPDFLoader
# ====================================================================================================
def _pdf_texts(path: str) -> dict[int, str]:
    """쪽 번호(1부터) → 본문. LangChain PyPDFLoader(mode='page', extraction_mode='plain') 와 같은 추출"""
    from pypdf import PdfReader

    return {p: page.extract_text(extraction_mode="plain").strip() for p, page in enumerate(PdfReader(path).pages, 1)}


def _pdf_tables_images(path: str, image_parser) -> tuple[dict[int, list[str]], dict[int, list[str]]]:
    """쪽 번호 → Markdown 표들, 쪽 번호 → 그림 설명들. image_parser 가 None 이면 그림은 꺼내지 않는다"""
    from langchain_community.document_loaders import PyMuPDFLoader

    if image_parser is not None:
        _patch_pymupdf_image_extraction()
    docs = PyMuPDFLoader(path, mode="page", extract_tables="markdown", extract_images=image_parser is not None,
                         images_parser=image_parser, images_inner_format="markdown-img").load()
    tables, images = {}, {}
    for d in docs:
        p = int(d.metadata.get("page", 0)) + 1
        images[p] = [c.strip() for c in _IMG_MD.findall(d.page_content) if c.strip()]
        tables[p] = [b for b in _md_table_blocks(_IMG_MD.sub("", d.page_content)) if b.count("|") >= 4]
    return tables, images


def _clean_pdf_page(text: str, tables: list[str], pcfg: dict) -> str:
    text = _remove_page_numbers(_fix_bullets(text))
    if tables:
        text = _drop_table_lines(text, tables, float(pcfg["table_dedupe_threshold"]))
    return _join_broken_lines(text, int(pcfg["join_min_line_len"]))


def _parse_pdf(path: str, pcfg: dict, image_parser) -> tuple[list[dict], str]:
    """PDF → (레코드들, 표지 텍스트). 앞 skip_first_pages 쪽(표지·목차)은 레코드에서 빼고 표지 텍스트로만 남긴다"""
    skip = int(pcfg["skip_first_pages"])
    texts = _pdf_texts(path)
    tables, images = _pdf_tables_images(path, image_parser)
    cover = normalize_text("\n".join(texts.get(p, "") for p in range(1, skip + 1)))
    kept = _remove_repeated_lines({p: normalize_text(t) for p, t in texts.items() if p > skip},
                                  float(pcfg["repeated_line_ratio"]))
    repeated = Counter(c for caps in images.values() for c in set(caps))  # 여러 쪽에 반복되는 그림 = 로고·장식
    max_repeat = int(pcfg["max_repeat_image_pages"])
    records = []
    for p in range(skip + 1, max(len(texts), len(tables)) + 1):
        tbls = tables.get(p, [])
        records.append({"page": p, "kind": "text", "text": _clean_pdf_page(kept.get(p, ""), tbls, pcfg)})
        records += [{"page": p, "kind": "table", "text": _fix_bullets(b.replace("<br>", " "))} for b in tbls]
        records += [{"page": p, "kind": "image_caption", "text": f"[그림/도표 설명] {c}"}
                    for c in images.get(p, []) if repeated[c] < max_repeat]
    return records, cover


def _strip_image_list(text: str) -> str:
    """HwpHwpxLoader(include_images=True) 가 본문 끝에 붙이는 '## Images' 파일 목록 제거"""
    if text.startswith("## Images\n"):
        return ""
    return text.rsplit("\n\n## Images\n", 1)[0] if "\n\n## Images\n" in text else text


def _patch_hwp_parser_hang():
    """hwp-hwpx-parser 1.0.0 무한 루프 버그 수정 (HWP5Reader._extract_hyperlink_texts_from_para).
    문단 데이터 끝 6바이트 안에 제어문자 0x03 이 있으면 인덱스가 증가하지 않아 extract_text 가 영원히 멈춤
    (예: 길이 18바이트 문단의 14번째 바이트). 같은 로직에 '남은 길이가 부족하면 2바이트 전진'만 추가."""
    from hwp_hwpx_parser import hwp5

    if getattr(hwp5.HWP5Reader, "_rag_hang_patched", False):
        return
    hyperlink_id = hwp5.CTRL_ID_HYPERLINK

    def _extract_hyperlink_texts_from_para(self, para_data: bytes):
        out, i, n = [], 0, len(para_data)
        while i < n - 1:
            code = struct.unpack_from("<H", para_data, i)[0]
            if code == 0x03 and i + 6 <= n and struct.unpack_from("<I", para_data, i + 2)[0] == hyperlink_id:
                text, i = _read_hyperlink(para_data, i)
                out += [text] if text else []
            else:
                i += _control_width(code, near_end=i + 6 > n)
        return out

    hwp5.HWP5Reader._extract_hyperlink_texts_from_para = _extract_hyperlink_texts_from_para
    hwp5.HWP5Reader._rag_hang_patched = True


def _read_hyperlink(para_data: bytes, i: int) -> tuple[str, int]:
    """i 위치 하이퍼링크 제어문자 뒤의 글자들 → (글자, 다음 위치)"""
    j, chars, n = i + 14, [], len(para_data)
    while j < n - 1:
        c = struct.unpack_from("<H", para_data, j)[0]
        if c == 0x04:
            break
        if c >= 0x20:
            chars.append(chr(c))
        j += 2
    return "".join(chars), max(j, i + 2)


def _control_width(code: int, near_end: bool) -> int:
    """제어문자 code 를 건너뛸 바이트 수 (원본과 같고, 끝 6바이트 안의 0x03 만 2바이트 전진)"""
    if code == 0x03:
        return 2 if near_end else 14  # ← 원본은 near_end 일 때 전진하지 않아 무한 루프
    if code == 0x04:
        return 10
    if code < 32:
        return 10 if code in (11, 12) else (14 if 15 <= code <= 23 else 2)
    return 2


def _hwp_raw_text(path: str, image_dir: str | None) -> str:
    """HwpHwpxLoader 로 HWP/HWPX 읽기. 표는 본문 제자리에 Markdown 으로 들어오므로 include_tables=False
    (True 면 끝에 '## Tables' 로 한 번 더 붙음). image_dir 를 주면 그림을 그 폴더에 저장한다."""
    from hwp_hwpx_parser import ExtractOptions, ImageMarkerStyle, TableStyle
    from langchain_hwp_hwpx import HwpHwpxLoader

    _patch_hwp_parser_hang()
    docs = HwpHwpxLoader(
        path, mode="single",
        extract_options=ExtractOptions(table_style=TableStyle.MARKDOWN, image_marker=ImageMarkerStyle.WITH_NAME),
        include_tables=False, include_notes=True, include_memos=False, include_hyperlinks=False,
        include_images=image_dir is not None, images_dir=image_dir,
        image_document_mode="save_and_reference" if image_dir else "metadata_only",
        on_encrypted="placeholder", on_invalid="placeholder", on_error="raise", include_extracted_at=False).load()
    if not docs or docs[0].metadata.get("status") in ("encrypted", "invalid"):
        print(f"⚠️ 본문을 읽을 수 없는 문서(암호화·배포용·손상): {os.path.basename(path)}")
        return ""
    return _strip_image_list(docs[0].page_content)


def _hwp_text(path: str, pcfg: dict, image_parser) -> tuple[str, list[str]]:
    """HWP/HWPX → 정리된 텍스트(표는 Markdown). 그림은 OCR 결과를 captions 에 넣고 본문에 [[IMG:n]] 자리표시"""
    if image_parser is None:
        return _IMG_MARK.sub("", repair_md_tables(clean_tab_garbage(_hwp_raw_text(path, None)))), []
    with tempfile.TemporaryDirectory(prefix="hwp_img_") as image_dir:
        text = repair_md_tables(clean_tab_garbage(_hwp_raw_text(path, image_dir)))
        return _ocr_hwp_images(text, image_dir, image_parser, int(pcfg["max_repeat_image_pages"]))


def _ocr_hwp_images(text: str, image_dir: str, image_parser, max_repeat: int) -> tuple[str, list[str]]:
    """본문의 [IMAGE: 이름] 표시를 OCR 결과 자리표시 [[IMG:n]] 로 바꾼다. max_repeat 번 이상 나오는 그림(로고·장식)은 지운다"""
    counts = Counter((m.group(1) or "").strip() for m in _IMG_MARK.finditer(text))
    captions: list[str] = []
    done: dict[str, str] = {}

    def sub(m: re.Match) -> str:
        name = (m.group(1) or "").strip()
        path = os.path.join(image_dir, name)
        if counts[name] >= max_repeat or not os.path.isfile(path):
            return ""
        if name not in done:
            done[name] = _ocr_image_file(path, image_parser)
        if not done[name]:
            return ""
        captions.append(done[name])
        return f"\n[[IMG:{len(captions) - 1}]]\n"

    return _IMG_MARK.sub(sub, text), captions


def _hwp_line_kind(line: str) -> str:
    if line.lstrip().startswith("|"):
        return "table"
    return "image" if _IMG_LINE.fullmatch(line) else "text"


def _append_text(records: list[dict], text: str):
    """본문은 앞 레코드가 본문이면 이어 붙인다 (1칸 표 앞뒤의 문단이 끊기지 않게)"""
    if records and records[-1]["kind"] == "text":
        records[-1]["text"] += "\n" + text
    else:
        records.append({"page": None, "kind": "text", "text": text})


def _hwp_records(body: str, captions: list[str]) -> list[dict]:
    """문서 순서 유지: 본문 → 표 → 본문 … (표·그림 위치에서 끊는다). HWP 는 라이브러리가 쪽 정보를 주지 않아 page=None"""
    records: list[dict] = []
    for kind, group in groupby(body.split("\n"), key=_hwp_line_kind):
        lines = list(group)
        if kind == "image":
            records += [{"page": None, "kind": "image_caption",
                         "text": "[그림/도표 설명] " + captions[int(_IMG_LINE.fullmatch(ln).group(1))]} for ln in lines]
            continue
        md = "\n".join(ln.strip() for ln in lines) if kind == "table" else "\n".join(lines)
        if kind == "table" and md.count("\n") >= 1 and md.count("|") >= 4:
            records.append({"page": None, "kind": "table", "text": md})
        elif kind == "table":
            _append_text(records, re.sub(r"\s*\|\s*", " ", md).strip())  # 1칸 표(글상자) → 본문
        else:
            _append_text(records, md)
    return records


def _parse_hwp(path: str, pcfg: dict, image_parser) -> tuple[list[dict], str]:
    """HWP/HWPX → (레코드들, 표지 텍스트). 쪽 정보가 없어 '앞 N쪽' 대신 표지·목차를 자동 감지해 뺀다"""
    text, captions = _hwp_text(path, pcfg, image_parser)
    front, body = split_front_matter(text) if int(pcfg["skip_first_pages"]) > 0 else ("", text)
    return _hwp_records(body, captions), normalize_text(re.sub(r"\[\[IMG:\d+\]\]", "", front))


# ----------------------------------------------------------------------------------------------------
# hwp-hwpx-parser 출력 후처리 (라이브러리가 주는 텍스트를 정리할 뿐, 파일을 직접 읽지 않음)
# ----------------------------------------------------------------------------------------------------
# hwp-hwpx-parser 가 탭 제어문자(8 wchar) 일부를 글자로 내보내는 문제 정리: '\t洴ȃ 1' → '\t 1', '개요  練ȃ  1' → '개요   1'
TAB_GARBAGE = re.compile(r"(?<=[\t ])[^\s가-힣A-Za-z0-9|]{0,2}[Ā-˿](?=[\s|]|$)")
TOC_MARK = re.compile(r"(?:^|\|)[\s\-–•·\[\(<【]*(?:목\s*차|차\s*례|CONTENTS|Contents)[\s\-–•·\]\)>】]*(?:\||$)")
TOC_LINE = re.compile(r"(?:\.{3,}|·{3,}|…{2,}|\s\d{1,3})\s*\|?\s*$")
MULTI_ENTRY = re.compile(r"\s\d{1,3}(?=\s|$)")
NEUTRAL = re.compile(r"^\s*$|^[\s|:\-•·]+$|^(?:\|\s*)+\|?\s*$")      # 빈 줄, |---|, 빈 셀 행
BODY_START = re.compile(r"^\s*(?:[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ][.\s]|제\s*1\s*[장편]|1\.\s|<[^>]{2,20}>|□|❏)")


def clean_tab_garbage(text: str) -> str:
    return TAB_GARBAGE.sub("", text)


def is_toc_line(ln: str) -> bool:
    s = ln.strip()
    return bool(s) and (bool(TOC_LINE.search(s)) or len(MULTI_ENTRY.findall(s)) >= 3)


def _compact_heading(s: str) -> str:
    s = re.sub(r"(?:\.{3,}|·{3,}|…+)?\s*\d{1,3}\s*\|?\s*$", "", s)        # 끝의 쪽번호·점선 제거
    return re.sub(r"[\s\W_]+", "", s)


def split_front_matter(text: str, max_ratio: float = 0.25) -> tuple[str, str]:
    """표지 + 목차 분리 → (front, body). HWP 는 페이지 정보가 없어 '앞 N페이지' 대신 사용.
    ① 목차에 쪽번호가 있으면: 목차 줄이 끝나는 곳까지
    ② 쪽번호 없는 목차면: 목차 첫 항목(예: '1. 제안공모 개요')이 본문에 '다시' 나오는 곳부터 본문
    ③ 목차가 없으면: 앞 10% 안의 첫 본문 제목 전까지"""
    lines = text.split("\n")
    limit = int(len(lines) * max_ratio) or len(lines)
    mark = next((i for i, ln in enumerate(lines[:limit]) if TOC_MARK.search(ln)), None)
    if mark is None:                                                       # ③ 목차 없음
        end = next((i for i, ln in enumerate(lines[:max(5, int(len(lines) * 0.10))]) if BODY_START.match(ln)), 0)
    else:
        end = _toc_end(lines, mark)
    return "\n".join(lines[:end]), "\n".join(lines[end:])


def _toc_end(lines: list[str], mark: int) -> int:
    """'목차' 표시 줄 mark 다음에서 본문이 시작하는 줄 번호"""
    nxt = next((j for j in range(mark + 1, len(lines)) if not NEUTRAL.match(lines[j])), None)
    if nxt is None:                                                        # 목차 뒤 내용 없음
        return len(lines)
    if is_toc_line(lines[mark]) or is_toc_line(lines[nxt]):                # ① 쪽번호 있는 목차
        return _last_toc_line(lines, mark) + 1
    first = _compact_heading(lines[nxt])                                   # ② 쪽번호 없는 목차
    again = next((j for j in range(nxt + 1, len(lines)) if _compact_heading(lines[j]).startswith(first)), None)
    return again if len(first) >= 3 and again is not None else nxt


def _last_toc_line(lines: list[str], mark: int) -> int:
    end = mark
    for j in range(mark + 1, len(lines)):
        if NEUTRAL.match(lines[j]):
            continue
        if not is_toc_line(lines[j]):
            break
        end = j
    return end


def repair_md_tables(text: str) -> str:
    """세로 병합 셀 때문에 칸이 모자란 행 → 왼쪽 칸을 윗행 값으로 채워 열 정렬 복원"""
    out, header_n, prev = [], None, None
    for ln in text.split("\n"):
        if ln.startswith("|") and ln.rstrip().endswith("|"):
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if header_n is None:
                header_n, prev = len(cells), cells
            elif not re.fullmatch(r"[\s|:\-]+", ln):
                if len(cells) < header_n and prev:
                    cells = prev[: header_n - len(cells)] + cells
                    ln = "| " + " | ".join(cells) + " |"
                prev = cells
        else:
            header_n, prev = None, None
        out.append(ln)
    return "\n".join(out)


# ====================================================================================================
# OCR (OCR=True 일 때만): 그림 → 글자. LangChain LLMImageBlobParser + OpenAI 비전 모델 (OPENAI_API_KEY)
# ====================================================================================================
def _ocr_parser(ocr_cfg: dict, callback: UsageCallback):
    from langchain_community.document_loaders.parsers.images import LLMImageBlobParser
    from langchain_openai import ChatOpenAI

    return LLMImageBlobParser(model=ChatOpenAI(model=ocr_cfg["model"], max_tokens=int(ocr_cfg["max_tokens"]),
                                            reasoning_effort=ocr_cfg["reasoning_effort"], callbacks=[callback]))


def _ocr_image_file(path: str, image_parser) -> str:
    """HWP 에서 꺼낸 그림 파일 하나 → 글자. PIL 이 열지 못하는 그림(WMF·EMF 벡터 등)은 건너뛴다"""
    from PIL import Image

    if path.lower().endswith((".wmf", ".emf")):
        return ""
    try:
        with Image.open(path) as img:
            rgb = img.convert("RGB")
    except OSError:
        return ""
    return image_parser._analyze_image(rgb)


def _patch_pymupdf_image_extraction():
    """langchain-community 0.3.x PyMuPDFParser 버그 수정(0.4.2 코드와 동일):
    이미지를 버퍼에 저장하기 '전에' 빈 버퍼인지 검사해서 모든 이미지를 건너뛰던 문제 → 저장 후 검사."""
    from langchain_community.document_loaders.parsers import pdf as P

    if getattr(P.PyMuPDFParser, "_rag_patched", False):
        return

    def _extract_images_from_page(self, doc, page) -> str:
        if not self.images_parser:
            return ""
        import pymupdf

        images = []
        for img in page.get_images():
            try:
                pix = pymupdf.Pixmap(doc, img[0])
                if pix.n - pix.alpha >= 4:  # CMYK → RGB
                    pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, -1)
            except Exception:  # noqa: BLE001  손상·특수 인코딩 이미지는 건너뜀
                continue
            buf = io.BytesIO()
            np.save(buf, arr)
            if buf.getbuffer().nbytes == 0:
                continue
            blob = P.Blob.from_data(buf.getvalue(), mime_type="application/x-npy")
            text = next(self.images_parser.lazy_parse(blob)).page_content
            images.append(P._format_inner_image(blob, text, self.images_inner_format))
        return P._FORMAT_IMAGE_STR.format(image_text=P._JOIN_IMAGES.join(filter(None, images)))

    P.PyMuPDFParser._extract_images_from_page = _extract_images_from_page
    P.PyMuPDFParser._rag_patched = True


# ====================================================================================================
# 문서 → 레코드
# ====================================================================================================
def _cache_file(cache_dir: Path, path: str, pcfg: dict, ocr: bool, ocr_cfg: dict) -> Path:
    """문서 하나의 파싱 결과 파일. 파일 이름 · 크기와 파싱 · OCR 설정이 모두 같을 때만 같은 이름이 되므로,
    원본 파일이나 설정을 바꾸면 옛 결과를 쓰지 않는다 (단가는 결과에 영향이 없어 뺀다)"""
    ocr_key = {k: ocr_cfg[k] for k in ("model", "max_tokens", "reasoning_effort")} if ocr else None
    key = json.dumps({"size": os.path.getsize(path), "parsing": pcfg, "ocr": ocr_key}, sort_keys=True, ensure_ascii=False)
    return cache_dir / f"{make_doc_id(path)}_{hashlib.sha1(key.encode()).hexdigest()[:8]}.json"


def _parse_or_load(path: str, pcfg: dict, image_parser, cache_file: Path) -> dict:
    """저장된 결과가 있으면 읽고, 없으면 파싱해서 저장한다. 임시 파일에 쓴 뒤 바꿔치기해서,
    쓰는 도중 컴퓨터가 꺼져도 반쯤 쓰인 파일이 남지 않는다"""
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))
    doc = _parse_file(path, pcfg, image_parser)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    tmp.replace(cache_file)
    return doc


def parse_documents(files: list[str], pcfg: dict, ocr: bool, ocr_cfg: dict, cache_dir: Path) -> list[dict]:
    """문서마다 {doc_id, source, title, doc_type, cover_text, head_text, records}.
    ocr=False 면 그림을 API 로 보내지 않는다. True 면 로고·장식(반복 그림)을 뺀 그림을 OCR 해 image_caption 레코드로 넣는다.
    문서 하나를 끝낼 때마다 cache_dir 에 저장하므로, 중간에 끊겨도 다시 실행하면 끝낸 문서는 건너뛰고(OCR 비용도 다시 들지 않음)
    이어서 한다. 오류가 난 문서는 저장하지 않아 다음 실행에서 다시 시도한다."""
    callback = UsageCallback("ocr", ocr_cfg["usd_per_1m_tokens"]) if ocr else None
    image_parser = _ocr_parser(ocr_cfg, callback) if ocr else None
    docs = []
    for i, path in enumerate(files, 1):
        if callback is not None:
            callback.subject = os.path.basename(path)
        cache_file = _cache_file(cache_dir, path, pcfg, ocr, ocr_cfg)
        reused = cache_file.exists()
        try:
            docs.append(_parse_or_load(path, pcfg, image_parser, cache_file))
        except Exception as e:  # noqa: BLE001  손상된 문서 하나 때문에 나머지 문서 파싱을 버리지 않는다
            print(f"({i}/{len(files)}) ❌ {os.path.basename(path)}: {type(e).__name__}: {e}")
            continue
        print(f"({i}/{len(files)}) {docs[-1]['source']}: 블록 {len(docs[-1]['records'])}개" + (" (저장된 결과)" if reused else ""))
    return docs


def _parse_file(path: str, pcfg: dict, image_parser) -> dict:
    ext = os.path.splitext(path)[1].lower()
    parse = _parse_pdf if ext == ".pdf" else _parse_hwp
    records, cover = parse(path, pcfg, image_parser)
    for r in records:
        r["text"] = apply_hanja(normalize_text(r["text"]), pcfg["hanja_mode"])
    records = [r for r in records if r["text"].strip()]
    return {"doc_id": make_doc_id(path), "source": os.path.basename(path), "title": _title(path),
            "doc_type": ext.lstrip("."), "cover_text": cover[:2500],
            "head_text": "\n".join(r["text"] for r in records if r["kind"] == "text")[:1500],  # 기관 라우팅용
            "records": records}


def parsing_summary(docs: list[dict]) -> pd.DataFrame:
    """문서별 레코드 수(본문 text · 표 table · 그림 image_caption)와 글자 수"""
    rows = [{"문서": d["source"], "형식": d["doc_type"], **Counter(r["kind"] for r in d["records"]),
             "글자 수": sum(len(r["text"]) for r in d["records"])} for d in docs]
    return pd.DataFrame(rows).fillna(0)
