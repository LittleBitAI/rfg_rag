"""② 검색 — 색인 만들기: 청크 → HuggingFace 임베딩 → FAISS, 청크 → Kiwi 형태소 → BM25 토큰.
담당: 검색.  retrieval.py 가 여기서 저장한 색인(artifacts/index/)을 읽어 검색한다."""
from __future__ import annotations

import json
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


_KIWI_KEEP = ("NNG", "NNP", "NNB", "NR", "NP", "VV", "VA", "XR", "SL", "SH", "SN", "MAG")


class KiwiTokenizer:
    """한국어 형태소 기반 BM25 토크나이저 (kiwipiepy). 한자(SH) 토큰은 한글 독음도 함께 색인."""

    def __init__(self):
        # num_workers=-1: 모든 CPU 코어 사용 (batch 에서 여러 청크를 병렬 분석). 단일 문장(질문)은 그대로 1스레드
        self.kiwi = Kiwi(num_workers=-1)

    def _keep(self, toks) -> list[str]:
        out = []
        for tok in toks:
            if tok.tag.startswith(_KIWI_KEEP):
                out.append(tok.form.lower())
                reading = hanja.translate(tok.form, "substitution") if tok.tag == "SH" else tok.form
                if reading != tok.form:
                    out.append(reading)
        return out

    def __call__(self, text: str) -> list[str]:
        return self._keep(self.kiwi.tokenize(text))

    def batch(self, texts: list[str]) -> list[list[str]]:
        """여러 청크를 멀티스레드로 한꺼번에 분석 (결과는 __call__ 과 같다)"""
        return [self._keep(t) for t in self.kiwi.tokenize(texts)]


def build_index(chunks: list[dict], cfg: dict, out_dir: Path) -> dict:
    """청크 → out_dir/faiss.index (정확 검색 IndexFlatIP) + out_dir/bm25_tokens.json (청크별 형태소)"""
    out_dir.mkdir(parents=True, exist_ok=True)
    texts = [c["text"] for c in chunks]
    vectors = Embedder(cfg["embedding"]).encode(texts, progress=True)
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    faiss.write_index(index, str(out_dir / "faiss.index"))
    tokens = KiwiTokenizer().batch(texts)
    (out_dir / "bm25_tokens.json").write_text(json.dumps(tokens, ensure_ascii=False), encoding="utf-8")
    return {"청크": len(chunks), "벡터 차원": int(vectors.shape[1]), "BM25 토큰": sum(map(len, tokens)),
            "BM25 어휘": len({w for t in tokens for w in t})}
