"""② 검색 — 색인 만들기: 청크 → HuggingFace 임베딩 → FAISS, 청크 → Kiwi 형태소 → BM25 토큰.
청크는 01 전처리 결과(artifacts/chunks.jsonl) 또는 v10 전처리 데이터셋(load_v10)을 쓴다.
담당: 검색.  retrieval.py 가 여기서 저장한 색인(artifacts/index/)을 읽어 검색한다."""
from __future__ import annotations

import json
import re
import unicodedata
from itertools import chain
from pathlib import Path

import faiss
import hanja
import numpy as np
import torch
from kiwipiepy import Kiwi
from langchain_core.embeddings import Embeddings
from sentence_transformers import SentenceTransformer


class Embedder(Embeddings):
    """SentenceTransformer 를 LangChain Embeddings 로 감싼다 (05 평가의 RAGAS answer_relevancy 에도 그대로 넘긴다).
    벡터는 정규화하므로 FAISS 내적 = 코사인 유사도."""

    def __init__(self, ecfg: dict):
        self.model = ecfg["model"]  # RAGAS 가 사용량 기록에 모델 이름(문자열)을 쓴다
        self.batch_size = int(ecfg["batch_size"])
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self._st = SentenceTransformer(self.model, device=device)
        self._st.max_seq_length = int(ecfg["max_seq_length"])
        if device == "cuda":
            self._st.half()  # fp16: 메모리 절반, 텐서코어 사용

    def encode(self, texts: list[str], progress: bool = False) -> np.ndarray:
        return self._st.encode(texts, batch_size=self.batch_size, normalize_embeddings=True, convert_to_numpy=True,
                               show_progress_bar=progress).astype(np.float32)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.encode(texts).tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.encode([text])[0].tolist()

    def token_counts(self, texts: list[str]) -> list[int]:
        """임베딩 모델 토크나이저 기준 토큰 수 (특수 토큰 포함 — max_seq_length 와 같은 기준)"""
        return [len(ids) for ids in self._st.tokenizer(texts)["input_ids"]]


# ====================================================================================================
# 요구사항 코드 (SFR-001, ECR-002 …)
# ====================================================================================================
# 형태소 분석은 'SFR-001' 을 SFR / - / 001 로 쪼갠다 → 코드 자체를 한 토큰으로 따로 색인한다.
# 가운데 마디가 있는 코드도 잡는다: SFR-상담-001 · SFR-01-001 · SFR-PR-003 · SFR-P01 (98개 RFP 요구사항 ID 929개 중 927개)
_CODE_RE = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]{2,5})-?((?:[가-힣A-Za-z]{1,8}-)*[A-Za-z]{0,3}\d{2,4}(?:-\d{1,4})*)"
                      r"(?![\dA-Za-z])")


def find_codes(text: str) -> set[str]:
    """글 속 요구사항 코드를 'SFR-001' 꼴로 통일해 돌려준다 (sfr001 · SFR-001 → SFR-001, SFR-상담-001 은 그대로)"""
    return {f"{letters.upper()}-{rest.upper()}" for letters, rest in _CODE_RE.findall(text)}


# ====================================================================================================
# 사용자 사전 · 별칭
# ====================================================================================================
# 사용자 사전: 붙여 쓰면 한 토큰. 띄어 쓴 '지체 상금' 도 붙여 쓴 꼴로 바꾼 뒤 분석한다 (공백 = 낱말 경계)
_USER_WORDS = ("지체 상금", "부가 가치세", "하자 보수", "과업 지시서", "제안 요청서", "기술 협상", "공동 수급")
# 별칭 → 원래 이름 (질문과 문서를 같은 토큰으로 맞춘다)
_ALIASES = {"부가세": "부가가치세"}

_SPELLINGS = ([(re.compile(r"\s*".join(w.split())), w.replace(" ", "")) for w in _USER_WORDS]
              + [(re.compile(alias), word) for alias, word in _ALIASES.items()])


def _canonical(text: str) -> str:
    """띄어 쓴 사용자 사전 낱말과 별칭을 원래 이름으로 바꾼다 ('지체 상금' · '부가세' → '지체상금' · '부가가치세')"""
    for pattern, word in _SPELLINGS:
        text = pattern.sub(word, text)
    return text


# ====================================================================================================
# BM25 토크나이저
# ====================================================================================================
_KIWI_KEEP = ("NNG", "NNP", "NNB", "NR", "NP", "VV", "VA", "XR", "SL", "SH", "SN", "MAG")
# 부정어: '제출하지 않는다' 의 않(VX) · '대상이 아니다' 의 아니(VCN). 버리면 긍정문과 같은 토큰이 된다
_NEGATION = {("않", "VX"), ("아니", "VCN")}


def _is_kept(tok) -> bool:
    return tok.tag.startswith(_KIWI_KEEP) or (tok.form, tok.tag) in _NEGATION


class KiwiTokenizer:
    """한국어 형태소 기반 BM25 토크나이저 (kiwipiepy).
    한자(SH) 토큰은 한글 독음도, 요구사항 코드는 'sfr-001' 한 토큰도 함께 색인. 부정어 '않' · '아니' 는 남긴다."""

    def __init__(self):
        # num_workers=-1: 모든 CPU 코어 사용 (batch 에서 여러 청크를 병렬 분석). 단일 문장(질문)은 그대로 1스레드
        self.kiwi = Kiwi(num_workers=-1)
        for word in _USER_WORDS:
            self.kiwi.add_user_word(word.replace(" ", ""), "NNP", 1.0)  # 점수 0 이면 '부가가치세' 가 여전히 갈라진다

    def _keep(self, toks, text: str) -> list[str]:
        out = []
        for tok in toks:
            if _is_kept(tok):
                out.append(tok.form.lower())
                reading = hanja.translate(tok.form, "substitution") if tok.tag == "SH" else tok.form
                if reading != tok.form:
                    out.append(reading)
        return out + [code.lower() for code in sorted(find_codes(text))]

    def __call__(self, text: str) -> list[str]:
        return self._keep(self.kiwi.tokenize(_canonical(text)), text)

    def batch(self, texts: list[str]) -> list[list[str]]:
        """여러 청크를 멀티스레드로 한꺼번에 분석 (결과는 __call__ 과 같다)"""
        analyzed = self.kiwi.tokenize([_canonical(t) for t in texts])
        return [self._keep(toks, text) for toks, text in zip(analyzed, texts)]


# ====================================================================================================
# v10 전처리 데이터셋 (github.com/mitguchin/-json-) → 01 전처리와 같은 형식의 청크 · 문서 목록
# ====================================================================================================
_V10_KIND = {"prose": "text", "table": "table", "requirement_detail": "table", "requirement_summary": "table",
             "image_text": "image_caption", "image_ocr": "image_caption"}
_TOC_LINE = re.compile(r"(?:\.{3,}|·{3,}|…{2,}|\s)\d{1,3}\s*$")            # '1. 사업 개요 ···· 12'
_SECTION_PAGE = re.compile(r"\s*\t.*$")                                     # 섹션 경로에 붙은 목차 쪽 번호 'Ⅵ. 서식\t\t 61'


def _read_v10(path: Path):
    """v10 jsonl 한 줄씩. git-lfs 없이 받은 포인터 파일이면 실제 파일을 받으라고 알린다"""
    with open(path, encoding="utf-8") as f:
        first = f.readline()
        if first.startswith("version https://git-lfs"):
            raise FileNotFoundError(f"{path} 는 Git LFS 포인터입니다. 저장소에서 'git lfs pull' 로 실제 파일을 받으세요")
        yield from (json.loads(line) for line in chain([first], f) if line.strip())


def _drop_images(text: str) -> str:
    """OCR 하지 않은 그림 자리표시 [IMAGE] 를 지우고, 그래서 비게 된 줄('| [IMAGE] |')도 지운다"""
    return "\n".join(ln for ln in text.replace("[IMAGE]", "").splitlines() if ln.strip(" |"))


def _is_toc(body: str) -> bool:
    """목차 청크: 세 줄 이상이고 60% 이상의 줄이 쪽 번호로 끝난다 (본문 청크에만 쓴다 — 숫자로 끝나는 표가 많다)"""
    lines = [ln for ln in body.splitlines() if ln.strip()]
    return len(lines) >= 3 and sum(bool(_TOC_LINE.search(ln)) for ln in lines) >= 0.6 * len(lines)


def _v10_doc(doc_id: str, source: str) -> dict:
    source = unicodedata.normalize("NFC", source)
    stem, ext = source.rsplit(".", 1)
    return {"doc_id": doc_id, "source": source, "title": re.sub(r"_+", " ", stem).strip(), "doc_type": ext.lower(),
            "cover_text": "", "head_text": ""}


def _v10_elements(path: Path) -> tuple[dict[str, tuple], dict[str, dict]]:
    """요소 → (문서 id, PDF 쪽, 종류), 문서 목록. head_text = 문서 앞부분 2,500자 (기관 라우팅이 발주기관 칸을 찾는 곳)"""
    elements, docs = {}, {}
    for e in _read_v10(path):
        meta = e["location"]["supplier_metadata"]
        doc_id = meta["doc_id"][:16]
        elements[e["element_id"]] = (doc_id, meta["pdf_page_number"], e["kind"])
        doc = docs.setdefault(doc_id, _v10_doc(doc_id, meta["source_paths"][0]))
        if e["kind"] != "toc" and len(doc["head_text"]) < 2500:
            doc["head_text"] += _drop_images(e["search_text"]) + "\n"
    return elements, docs


def _v10_chunk(c: dict, elements: dict, docs: dict, min_chars: int) -> dict | None:
    """v10 청크 → 01 전처리 청크 형식 (text = '문서: 제목 | p.N | 섹션: …' 머리말 + body).
    min_chars 보다 짧거나('요구사항 분류 | 기능 요구사항' 같은 표 머리 줄 · 목차 조각) 목차면 None"""
    body = _drop_images(c["body"]).strip()
    if len(body) < min_chars or (c["chunk_type"] == "prose" and _is_toc(body)):
        return None
    doc_id, page, _ = elements[c["spans"][0]["element_id"]]
    doc = docs[doc_id]
    section = " > ".join(_SECTION_PAGE.sub("", s).strip() for s in c["section_path"])
    header = f"문서: {doc['title']}" + (f" | p.{page}" if page else "") + (f" | 섹션: {section}" if section else "")
    return {"chunk_id": c["chunk_id"], "doc_id": doc_id, "source": doc["source"], "title": doc["title"],
            "doc_type": doc["doc_type"], "page": page, "kind": _V10_KIND[c["chunk_type"]], "section": section,
            "text": f"{header}\n{body}", "body": body}


def load_v10(package_dir: Path, min_chars: int) -> tuple[list[dict], list[dict]]:
    """v10 데이터셋 폴더의 final_elements.jsonl · final_chunks.jsonl → (청크, 문서 목록).
    01 전처리의 chunks.jsonl · docs.jsonl 과 같은 형식이라 02 ~ 05 가 그대로 읽는다.
    min_chars 는 01 과 같은 config.yaml 의 chunking.min_chunk_chars"""
    elements, docs = _v10_elements(package_dir / "final_elements.jsonl")
    chunks = (_v10_chunk(c, elements, docs, min_chars) for c in _read_v10(package_dir / "final_chunks.jsonl"))
    return [c for c in chunks if c], list(docs.values())


def build_index(chunks: list[dict], cfg: dict, out_dir: Path) -> dict:
    """청크 → out_dir/faiss.index (정확 검색 IndexFlatIP) + out_dir/bm25_tokens.json (청크별 형태소)"""
    out_dir.mkdir(parents=True, exist_ok=True)
    texts = [c["text"] for c in chunks]
    embedder = Embedder(cfg["embedding"])
    vectors = embedder.encode(texts, progress=True)
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    faiss.write_index(index, str(out_dir / "faiss.index"))
    tokens = KiwiTokenizer().batch(texts)
    (out_dir / "bm25_tokens.json").write_text(json.dumps(tokens, ensure_ascii=False), encoding="utf-8")
    max_len = int(cfg["embedding"]["max_seq_length"])
    return {"청크": len(chunks), "벡터 차원": int(vectors.shape[1]), "BM25 토큰": sum(map(len, tokens)),
            "BM25 어휘": len({w for t in tokens for w in t}),
            f"임베딩에서 잘린 청크(>{max_len} 토큰)": sum(n > max_len for n in embedder.token_counts(texts))}
