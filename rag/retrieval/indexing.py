"""② 검색 — 색인 만들기: 청크 → HuggingFace 임베딩 → FAISS, 청크 → Kiwi 형태소 → BM25 토큰.
담당: 검색.  retrieval.py 가 여기서 저장한 색인(artifacts/index/)을 읽어 검색한다."""
from __future__ import annotations

import json
import re
from pathlib import Path

import faiss
import hanja
import numpy as np
import torch
from kiwipiepy import Kiwi
from langchain_core.embeddings import Embeddings
from sentence_transformers import SentenceTransformer


class Embedder(Embeddings):
    """SentenceTransformer 를 LangChain Embeddings 로 감싼다.
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


# 형태소 분석으로 쪼개지는 요구사항 코드를 한 토큰으로도 색인한다
_CODE_RE = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]{2,5})-?(\d{2,4})(?![A-Za-z0-9])")


def find_codes(text: str) -> set[str]:
    """글 속 요구사항 코드를 'SFR-001' 꼴로 통일한다. 긴 영숫자 식별자의 일부는 코드로 보지 않는다."""
    return {f"{letters.upper()}-{digits}" for letters, digits in _CODE_RE.findall(text)}


_USER_WORDS = ("지체 상금", "부가 가치세", "하자 보수", "과업 지시서", "제안 요청서", "기술 협상", "공동 수급")
_ALIASES = {"부가세": "부가가치세"}
_SPELLINGS = ([(re.compile(r"\s*".join(w.split())), w.replace(" ", "")) for w in _USER_WORDS]
              + [(re.compile(alias), word) for alias, word in _ALIASES.items()])


def _canonical(text: str) -> str:
    """띄어 쓴 사용자 사전 낱말과 별칭을 원래 이름으로 바꾼다"""
    for pattern, word in _SPELLINGS:
        text = pattern.sub(word, text)
    return text


_KIWI_KEEP = ("NNG", "NNP", "NNB", "NR", "NP", "VV", "VA", "XR", "SL", "SH", "SN", "MAG")
_NEGATION = {("않", "VX"), ("아니", "VCN")}


def _is_kept(tok) -> bool:
    return tok.tag.startswith(_KIWI_KEEP) or (tok.form, tok.tag) in _NEGATION


class KiwiTokenizer:
    """한국어 형태소 기반 BM25 토크나이저. 한자 독음과 요구사항 코드도 색인하며 부정어를 남긴다."""

    def __init__(self):
        # num_workers=-1: 모든 CPU 코어 사용 (batch 에서 여러 청크를 병렬 분석). 단일 문장(질문)은 그대로 1스레드
        self.kiwi = Kiwi(num_workers=-1)
        for word in _USER_WORDS:
            self.kiwi.add_user_word(word.replace(" ", ""), "NNP", 1.0)

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
