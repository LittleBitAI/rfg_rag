"""② 검색 — 색인 만들기: 청크 → HuggingFace 임베딩 → FAISS, 청크 → Kiwi 형태소 → BM25 토큰.
담당: 검색.  retrieval.py 가 여기서 저장한 색인(artifacts/index/)을 읽어 검색한다."""
from __future__ import annotations

import hashlib
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


# 임베딩을 이 개수씩 나눠 저장한다 — 끊기면 마지막 묶음 하나만 다시 계산한다
_PART_SIZE = 1000


def _part_file(ckpt_dir: Path, ecfg: dict, texts: list[str]) -> Path:
    """임베딩 묶음 하나의 저장 파일. 모델 · 최대 길이 · 청크 본문이 모두 같을 때만 같은 이름이 되므로,
    01 을 다시 돌려 청크가 바뀌거나 임베딩 설정을 바꾸면 그 묶음은 새로 계산한다"""
    key = json.dumps({"model": ecfg["model"], "max_seq_length": int(ecfg["max_seq_length"]), "texts": texts},
                     ensure_ascii=False)
    return ckpt_dir / f"{hashlib.sha1(key.encode()).hexdigest()[:16]}.npy"


def _embed_with_checkpoint(embedder: Embedder, texts: list[str], ecfg: dict, ckpt_dir: Path) -> np.ndarray:
    """묶음마다 임베딩을 ckpt_dir 에 저장한다. 다시 실행하면 저장된 묶음은 읽기만 하고 남은 묶음부터 이어서 계산한다.
    임시 파일에 쓴 뒤 바꿔치기해서, 쓰는 도중 끊겨도 반쯤 쓰인 파일이 남지 않는다."""
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    parts = [texts[i: i + _PART_SIZE] for i in range(0, len(texts), _PART_SIZE)]
    files = [_part_file(ckpt_dir, ecfg, part) for part in parts]
    vectors = []
    for k, (part, file) in enumerate(zip(parts, files), 1):
        if file.exists():
            vectors.append(np.load(file))
            print(f"임베딩 ({k}/{len(parts)}) 청크 {len(part)}개 — 저장된 결과")
            continue
        vectors.append(embedder.encode(part, progress=True))
        tmp = file.with_suffix(".tmp")
        with open(tmp, "wb") as f:
            np.save(f, vectors[-1])
        tmp.replace(file)
        print(f"임베딩 ({k}/{len(parts)}) 청크 {len(part)}개 — 저장")
    for stale in set(ckpt_dir.glob("*.npy")) - set(files):  # 예전 청크의 묶음은 지워 디스크가 쌓이지 않게
        stale.unlink()
    return np.concatenate(vectors)


def build_index(chunks: list[dict], cfg: dict, out_dir: Path) -> dict:
    """청크 → out_dir/faiss.index (정확 검색 IndexFlatIP) + out_dir/bm25_tokens.json (청크별 형태소).
    임베딩은 out_dir/checkpoint/ 에 묶음별로 저장해, 중간에 끊겨도 다시 실행하면 이어서 만든다."""
    out_dir.mkdir(parents=True, exist_ok=True)
    texts = [c["text"] for c in chunks]
    embedder = Embedder(cfg["embedding"])
    vectors = _embed_with_checkpoint(embedder, texts, cfg["embedding"], out_dir / "checkpoint")
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    faiss.write_index(index, str(out_dir / "faiss.index"))
    tokens = KiwiTokenizer().batch(texts)
    (out_dir / "bm25_tokens.json").write_text(json.dumps(tokens, ensure_ascii=False), encoding="utf-8")
    max_len = int(cfg["embedding"]["max_seq_length"])
    return {"청크": len(chunks), "벡터 차원": int(vectors.shape[1]), "BM25 토큰": sum(map(len, tokens)),
            "BM25 어휘": len({w for t in tokens for w in t}),
            f"임베딩에서 잘린 청크(>{max_len} 토큰)": sum(n > max_len for n in embedder.token_counts(texts))}
