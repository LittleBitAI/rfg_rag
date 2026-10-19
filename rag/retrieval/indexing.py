"""② 검색 — 색인 만들기: 청크 → HuggingFace 임베딩 → FAISS, 청크 → Kiwi 형태소 → BM25 토큰.
담당: 검색.  retrieval.py 가 여기서 저장한 색인(artifacts/index/)을 읽어 검색한다."""
from __future__ import annotations

import json
import re
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory

import faiss
import hanja
import numpy as np
import torch
from kiwipiepy import Kiwi
from langchain_core.embeddings import Embeddings
from sentence_transformers import SentenceTransformer

from ..config import write_jsonl
from .quantity_metadata import quantity_rows


class Embedder(Embeddings):
    """SentenceTransformer 를 LangChain Embeddings 로 감싼다.
    벡터는 정규화하므로 FAISS 내적 = 코사인 유사도."""

    def __init__(self, ecfg: dict):
        self.model = ecfg["model"]
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

    def truncate(self, text: str, budget: int) -> str:
        ids = self._st.tokenizer.encode(text, add_special_tokens=False)
        return self._st.tokenizer.decode(ids[:max(0, budget)], skip_special_tokens=True)


# 형태소 분석으로 쪼개지는 요구사항 코드를 한 토큰으로도 색인한다
_CODE_RE = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]{2,5})-?(\d{2,4})(?![A-Za-z0-9])")


def find_codes(text: str) -> set[str]:
    """글 속 요구사항 코드를 'SFR-001' 꼴로 통일한다. 긴 영숫자 식별자의 일부는 코드로 보지 않는다."""
    return {f"{letters.upper()}-{digits}" for letters, digits in _CODE_RE.findall(text)}


# 요구사항 표의 명칭 칸: '요구사항 명칭 | 보안관리 및 규정 준수' · '요구사항명 | …' · 오타 '요사항 명칭 | …'
_REQUIREMENT_NAME = re.compile(r"(?:요?구?사항\s*)?명\s*칭\s*\|\s*([^\n|]+)|요구사항\s*명\s*\|\s*([^\n|]+)")


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def requirement_names(chunks: list[dict]) -> dict[tuple[str, str], str]:
    """(문서, 소속 요구사항) → 요구사항 명칭. 전처리 패키지가 같은 요구사항으로 묶은 청크(requirement_key 가 같은 청크)
    중 명칭 칸이 있는 첫 청크에서 가져온다. 명칭 칸이 있는 청크가 없으면 빈 글"""
    names: dict[tuple[str, str], str] = {}
    for chunk in chunks:
        if not chunk.get("requirement_key"):
            continue
        group = (chunk["doc_id"], chunk["requirement_key"])
        if not names.get(group):
            found = _REQUIREMENT_NAME.search(chunk["text"])
            names[group] = (found[1] or found[2]).strip() if found else ""
    return names


def search_texts(chunks: list[dict]) -> list[str]:
    """검색(BM25 · 임베딩)이 읽는 청크 글. 요구사항에 속한 청크의 글에 그 요구사항 ID 나 명칭이 없으면
    '[요구사항 SER-001 보안관리 및 규정 준수]' 를 앞에 붙인다 — 전처리에서 ID · 명칭 청크와 상세 내용 청크가
    나뉘어도 상세 내용 청크가 요구사항 ID · 이름으로 찾히게 (요구사항 소속 정보 requirement_key 를 쓴다).
    답변 근거와 화면에는 원래 글(text · body)을 그대로 쓴다."""
    names = requirement_names(chunks)
    texts = []
    for chunk in chunks:
        key = chunk.get("requirement_key")
        label = [key, names[(chunk["doc_id"], key)]] if key else []
        if any(part and _squash(part) not in _squash(chunk["text"]) for part in label):
            texts.append(f"[요구사항 {' '.join(filter(None, label))}]\n{chunk['text']}")
        else:
            texts.append(chunk["text"])
    return texts


def texts_digest(texts: list[str]) -> str:
    """색인을 만든 검색 글의 해시 — 검색 때 다시 계산해 색인이 지금 청크와 맞는지 확인한다"""
    return sha256("\n\x00".join(texts).encode("utf-8")).hexdigest()


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
_NOISE = {("및", "MAG"), ("하", "VV"), ("되", "VV"), ("있", "VV"), ("등", "NNB"), ("수", "NNB")}


def _is_kept(tok) -> bool:
    return (tok.form, tok.tag) not in _NOISE and (
        tok.tag.startswith(_KIWI_KEEP) or (tok.form, tok.tag) in _NEGATION)


class KiwiTokenizer:
    """한국어 형태소 기반 BM25 토크나이저. 한자 독음과 요구사항 코드도 색인하며 부정어를 남긴다."""

    def __init__(self):
        dictionary = Path(__file__).with_name("kiwi_user_words.json").read_bytes()
        # 규칙 변경 누락을 막으려고 이 모듈 전체를 지문에 넣는다. 줄바꿈 방식은 무시한다.
        source = Path(__file__).read_text(encoding="utf-8").encode("utf-8")
        self.fingerprint = {"source_sha256": sha256(source).hexdigest(),
                            "dictionary_sha256": sha256(dictionary).hexdigest(),
                            **{name: version(name) for name in ("kiwipiepy", "kiwipiepy_model", "hanja")}}
        # num_workers=-1: 모든 CPU 코어 사용 (batch 에서 여러 청크를 병렬 분석). 단일 문장(질문)은 그대로 1스레드
        self.kiwi = Kiwi(num_workers=-1)
        for word in _USER_WORDS:
            self.kiwi.add_user_word(word.replace(" ", ""), "NNP", 1.0)
        for word in json.loads(dictionary):
            self.kiwi.add_user_word(word, "NNP", 1.0)

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
    """Build coupled artifacts privately and restore the old directory if publication fails."""
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=f".{out_dir.name}-", dir=out_dir.parent) as folder:
        workspace = Path(folder)
        staged = workspace / "next"
        staged.mkdir()
        result = _build_index(chunks, cfg, staged)
        _publish_index(staged, out_dir, workspace / "previous")
    return result


def _publish_index(staged, out_dir, previous):
    if out_dir.exists():
        out_dir.rename(previous)
    try:
        staged.rename(out_dir)
    except BaseException:
        if previous.exists():
            previous.rename(out_dir)
        raise


def _build_index(chunks, cfg, out_dir):
    texts = search_texts(chunks)
    embedder = Embedder(cfg["embedding"])
    vectors = embedder.encode(texts, progress=True)
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    faiss.write_index(index, str(out_dir / "faiss.index"))
    tokenizer = KiwiTokenizer()
    tokens = tokenizer.batch(texts)
    payload = {"tokenizer": tokenizer.fingerprint, "tokens": tokens}
    (out_dir / "bm25_tokens.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    (out_dir / "texts.sha256").write_text(texts_digest(texts), encoding="utf-8")
    build_quantity_index(chunks, embedder, out_dir)
    max_len = int(cfg["embedding"]["max_seq_length"])
    labelled = sum(text != chunk["text"] for text, chunk in zip(texts, chunks))
    return {"청크": len(chunks), "요구사항 머리말을 붙인 청크": labelled, "벡터 차원": int(vectors.shape[1]),
            "BM25 토큰": sum(map(len, tokens)),
            "BM25 어휘": len({w for t in tokens for w in t}),
            f"임베딩에서 잘린 청크(>{max_len} 토큰)": sum(n > max_len for n in embedder.token_counts(texts))}


def build_quantity_index(chunks: list[dict], embedder: Embedder, out_dir: Path):
    rows = quantity_rows(chunks)
    phrases = list(dict.fromkeys(r["phrase"] for r in rows))
    vectors = embedder.encode(phrases, progress=True) if phrases else np.empty((0, 0), dtype=np.float32)
    write_jsonl(rows, out_dir / "quantities.jsonl")
    (out_dir / "quantity_phrases.json").write_text(json.dumps(phrases, ensure_ascii=False), encoding="utf-8")
    np.save(out_dir / "quantity_vectors.npy", vectors)
