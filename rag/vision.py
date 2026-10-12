"""(선택) 그래프·도표 이미지 → 텍스트.  LangChain 의 `images_parser`(BaseImageBlobParser) 형식으로 제공.

PDF : PyMuPDFLoader(extract_images=True, images_parser=<여기서 만든 파서>) 가 페이지 이미지를 넘겨줌
HWP : HwpHwpxLoader(include_images=True, image_document_mode="save_and_reference") 가 저장한 이미지를 같은 파서의 _analyze_image() 로 처리
파서 종류(노트북 IMAGE_PARSER):
  "rapidocr" : LangChain RapidOCRBlobParser (로컬 CPU OCR, 이미지 속 글자만)
  "tesseract": LangChain TesseractBlobParser (로컬 OCR, kor+eng)
  "llm"      : LangChain LLMImageBlobParser (gpt-5-mini 등 멀티모달 LLM, API 비용)
  None       : 이미지 무시
로컬 VLM 은 쓰지 않습니다.

한국어 차트/표/다이어그램을 텍스트로 풀어 청크로 넣어주면, 이미지 속 수치도 검색·답변에 쓰입니다.
"""
from __future__ import annotations

import io


def pil_from_bytes(data: bytes, ext: str):
    from PIL import Image

    if ext.lower() in ("wmf", "emf"):
        return None  # PIL 미지원 벡터 포맷
    try:
        return Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        return None


def make_image_parser(kind: str | None, pcfg: dict):
    if not kind or kind == "none":
        return None
    from langchain_community.document_loaders.parsers.images import (LLMImageBlobParser, RapidOCRBlobParser,
                                                                      TesseractBlobParser)
    if kind == "rapidocr":
        return RapidOCRBlobParser()
    if kind == "tesseract":
        return TesseractBlobParser(langs=("kor", "eng"))
    if kind == "llm":
        from .llm import make_judge_llm

        return LLMImageBlobParser(model=make_judge_llm(pcfg.get("image_llm_model", "gpt-5-mini"), 2048, "low"))
    raise ValueError(f"알 수 없는 image_parser: {kind}")


def patch_pymupdf_image_extraction():
    """langchain-community 0.3.x PyMuPDFParser 버그 수정(0.4.2 코드와 동일):
    이미지를 버퍼에 저장하기 '전에' 빈 버퍼인지 검사해서 모든 이미지를 건너뛰던 문제 → 저장 후 검사."""
    import io as _io

    import numpy as _np
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
                arr = _np.frombuffer(pix.samples, dtype=_np.uint8).reshape(pix.height, pix.width, -1)
            except Exception:  # noqa: BLE001  손상·특수 인코딩 이미지는 건너뜀
                continue
            buf = _io.BytesIO()
            _np.save(buf, arr)
            if buf.getbuffer().nbytes == 0:
                continue
            blob = P.Blob.from_data(buf.getvalue(), mime_type="application/x-npy")
            text = next(self.images_parser.lazy_parse(blob)).page_content
            images.append(P._format_inner_image(blob, text, self.images_inner_format))
        return P._FORMAT_IMAGE_STR.format(image_text=P._JOIN_IMAGES.join(filter(None, images)))

    P.PyMuPDFParser._extract_images_from_page = _extract_images_from_page
    P.PyMuPDFParser._rag_patched = True
