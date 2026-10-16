"""RFP 문서의 그림을 꺼내 OCR 라벨링 화면이 읽을 artifacts/ocr_labels/images.jsonl 을 만든다.

01 전처리와 같은 함수(collect_inputs · make_doc_id · _hwp_raw_text)로 그림을 꺼내고,
위치는 CRAFT 선별(rag/preprocessing/ocr_selection.py 의 SelectionParser)이 남기는 필드 이름 그대로 적는다.
같은 바이트의 그림(반복 로고 등)은 한 줄로 묶고 나온 위치를 모두 occurrences 에 담는다.
저장소 최상위에서 실행: .venv\\Scripts\\python -m frontend.ocr_select.extract
"""
from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from collections import Counter
from pathlib import Path

from PIL import Image

from rag.config import ARTIFACTS, ROOT, load_config, write_jsonl
from rag.preprocessing.parsing import (_IMG_MARK, _hwp_raw_text, clean_tab_garbage, collect_inputs, make_doc_id,
                                       repair_md_tables)

OUT = ARTIFACTS / "ocr_labels"
IMAGES = OUT / "images"


def _found(data: bytes, name: str, reason: str | None, location: dict) -> dict:
    """꺼낸 그림 하나. reason 이 있으면 화면에서 그림 대신 자리표시 카드로 보인다."""
    return {"data": data, "name": name, "reason": reason, "location": location}


def _hwp_reason(path: str) -> str | None:
    """PIL 이 열지 못하는 그림의 이유 (문구는 parsing._ocr_image_file 이 CRAFT 기록에 남기는 것과 같다)"""
    if path.lower().endswith((".wmf", ".emf")):
        return "Unsupported vector image encoding"
    try:
        with Image.open(path) as img:
            img.load()
    except OSError:
        return "HWP image decode failed"
    return None


def hwp_text(path: str, image_dir: str) -> str:
    """marker_start 가 가리키는 본문 — parsing._hwp_text 와 같은 정리. 라벨링 화면의 원본 보기도 이 글에서 앞뒤를 자른다."""
    return repair_md_tables(clean_tab_garbage(_hwp_raw_text(path, image_dir)))


def hwp_images(path: str) -> list[dict]:
    """HWP/HWPX 의 [IMAGE: 이름] 표시마다 그림 하나. marker_start 는 parsing._hwp_text 가 정리한 본문 기준이라 CRAFT 기록과 같다.
    라이브러리가 꺼냈지만 본문에 표시가 없는 그림(쪽에 놓이지 않은 BinData, 머리말 · 글상자 속 그림 등)도
    marker_start=None 으로 싣는다. 01 전처리와 CRAFT 는 이 그림을 보지 않는다."""
    with tempfile.TemporaryDirectory(prefix="ocr_labels_") as image_dir:
        text = hwp_text(path, image_dir)
        marks = [((m.group(1) or "").strip(), m.start()) for m in _IMG_MARK.finditer(text)]
        counts = Counter(name for name, _ in marks)
        marks += [(name, None) for name in sorted(os.listdir(image_dir)) if name not in counts]
        found = []
        for name, start in marks:
            file = os.path.join(image_dir, name)
            if not os.path.isfile(file):  # 파일이 없는 표시는 CRAFT 도 그림 없이 오류로만 남긴다
                continue
            location = {"format": "hwp", "image_name": name, "marker_start": start,
                        "repeated_occurrences": counts[name]}
            found.append(_found(Path(file).read_bytes(), name, _hwp_reason(file), location))
    return found


def _pdf_image(doc, xref: int, name: str, location: dict) -> dict:
    """parsing._patch_pymupdf_image_extraction 과 같은 Pixmap 디코딩. 실패하면 원본 스트림을 자리표시 카드로 남긴다."""
    import pymupdf

    try:
        pix = pymupdf.Pixmap(doc, xref)
        if pix.n - pix.alpha >= 4:  # CMYK → RGB
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        return _found(pix.tobytes("png"), f"{name}.png", None, location)
    except Exception:  # 01 전처리도 손상 · 특수 인코딩 그림은 디코딩 실패로 건너뛴다
        return _found(doc.xref_stream_raw(xref), f"{name}.bin", "PDF image decode failed", location)


def _bbox_points(page, xref: int) -> list:
    """그림이 쪽에 놓인 자리. 01 전처리처럼 자리를 못 찾으면 [] 로 두고 그림은 남긴다."""
    try:
        return [list(rect) for rect in page.get_image_rects(xref)]
    except Exception:
        return []


def pdf_images(path: str) -> list[dict]:
    """PDF 쪽마다 page.get_images() 순서대로 그림 하나. 위치 필드는 parsing._image_selection_location 과 같다."""
    import pymupdf

    found = []
    with pymupdf.open(path) as doc:
        for page in doc:
            for image_index, img in enumerate(page.get_images()):
                xref = img[0]
                location = {"format": "pdf", "page": page.number + 1, "image_index": image_index, "xref": xref,
                            "bbox_points": _bbox_points(page, xref)}
                found.append(_pdf_image(doc, xref, f"p{page.number + 1}_{image_index}_x{xref}", location))
    return found


def group_images(found: list[dict]) -> list[dict]:
    """그림 바이트의 SHA-256 별로 한 줄. 파일은 처음 나온 위치의 것을 쓰고, 위치는 나온 순서대로 모두 담는다.
    found 의 항목: {image_sha256, file, reason, occurrence}"""
    rows: dict[str, dict] = {}
    for f in found:
        row = rows.setdefault(f["image_sha256"], {
            "image_sha256": f["image_sha256"], "file": f["file"],
            "viewable": f["reason"] is None, "reason": f["reason"], "occurrences": []})
        row["occurrences"].append(f["occurrence"])
    return list(rows.values())


def _document_images(path: str) -> list[dict]:
    """문서 하나의 그림들을 IMAGES/<그림 해시>.<확장자> 로 저장하고 group_images 가 받는 항목으로 돌려준다 (같은 그림은 한 번만 저장).
    doc_id 는 파일 이름만으로 만들어 다른 폴더의 같은 이름 문서끼리 겹치므로 저장 경로에 쓰지 않는다."""
    doc_id = make_doc_id(path)
    document = {"doc_id": doc_id, "source": os.path.basename(path),
                "document_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}
    images = pdf_images(path) if path.lower().endswith(".pdf") else hwp_images(path)
    items = []
    for image in images:
        sha = hashlib.sha256(image["data"]).hexdigest()
        file = sha + Path(image["name"]).suffix
        target = IMAGES / file
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(image["data"])
        items.append({"image_sha256": sha, "file": file, "reason": image["reason"],
                      "occurrence": {**document, **image["location"]}})
    return items


def main():
    cfg = load_config()
    files = collect_inputs(ROOT / cfg["paths"]["input"], ARTIFACTS / "raw")
    shutil.rmtree(IMAGES, ignore_errors=True)  # 지난 실행의 그림만 지운다. labels.jsonl 은 그대로 둔다
    found = []
    for i, path in enumerate(files, 1):
        try:
            items = _document_images(path)
        except Exception as e:  # 손상된 문서 하나 때문에 나머지 문서의 그림을 버리지 않는다 (parse_documents 와 같음)
            print(f"({i}/{len(files)}) ❌ {os.path.basename(path)}: {type(e).__name__}: {e}")
            continue
        found += items
        print(f"({i}/{len(files)}) {os.path.basename(path)}: 그림 {len(items)}개")
    rows = group_images(found)
    write_jsonl(rows, OUT / "images.jsonl")
    print(f"서로 다른 그림 {len(rows)}개 (위치 {len(found)}곳) → {OUT / 'images.jsonl'}")


if __name__ == "__main__":
    main()
