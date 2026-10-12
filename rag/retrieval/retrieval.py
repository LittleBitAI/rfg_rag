"""② 검색 — BM25(Kiwi) × Dense(FAISS) 하이브리드 + 발주기관 라우팅.
담당: 검색.  indexing.py 가 만든 색인(artifacts/index/)과 01 전처리의 chunks.jsonl · docs.jsonl 을 읽는다."""
from __future__ import annotations

import json
import math
import re
from itertools import chain, zip_longest
from pathlib import Path

import faiss
import numpy as np
from langfuse import observe
from rank_bm25 import BM25Okapi

from ..config import read_jsonl
from .indexing import Embedder, KiwiTokenizer


def _minmax(d: dict[int, float]) -> dict[int, float]:
    if not d:
        return {}
    lo, hi = min(d.values()), max(d.values())
    if hi - lo < 1e-12:
        return {k: 1.0 for k in d}
    return {k: (v - lo) / (hi - lo) for k, v in d.items()}


class HybridIndex:
    """final = w·Dense + (1-w)·BM25 — 두 후보군을 각각 min-max 정규화한 뒤 가중합 (w = dense_weight, 0=BM25만, 1=Dense만).
    질문에 발주기관이 나오면 그 기관 문서 안에서만 찾는다 (DocRouter)."""

    def __init__(self, artifacts: Path, cfg: dict):
        self.chunks = read_jsonl(artifacts / "chunks.jsonl")
        self.doc_ids = np.array([c["doc_id"] for c in self.chunks])
        self.faiss = faiss.read_index(str(artifacts / "index" / "faiss.index"))
        tokens = json.loads((artifacts / "index" / "bm25_tokens.json").read_text(encoding="utf-8"))
        self.bm25 = BM25Okapi(tokens, k1=float(cfg["bm25"]["k1"]), b=float(cfg["bm25"]["b"]))
        self.embedder = Embedder(cfg["embedding"])
        self.tokenizer = KiwiTokenizer()
        self.router = DocRouter(read_jsonl(artifacts / "docs.jsonl"))
        self.rcfg = cfg["retrieval"]

    @observe(as_type="retriever")
    def search(self, question: str) -> list[dict]:
        """질문 → 상위 top_k 청크(score = 하이브리드 점수). 두 기관 이상을 비교하는 질문이면 기관별로 찾아 번갈아 섞는다"""
        route = self.router.route(question)
        top_k = int(self.rcfg["top_k"])
        if len(route) < 2:
            return self._search(question, top_k, next(iter(route.values()), None))
        k_each = max(2, math.ceil(top_k / len(route)))
        lists = [self._search(question, k_each, doc_ids) for doc_ids in route.values()]
        merged: dict[str, dict] = {}
        for hit in chain.from_iterable(zip_longest(*lists)):
            if hit is not None:
                merged.setdefault(hit["chunk_id"], hit)
        return list(merged.values())

    def _search(self, question: str, top_k: int, doc_ids: set | None) -> list[dict]:
        allowed = np.isin(self.doc_ids, list(doc_ids)) if doc_ids else np.ones(len(self.chunks), dtype=bool)
        dense, sparse = _minmax(self._dense(question, allowed)), _minmax(self._sparse(question, allowed))
        w = float(self.rcfg["dense_weight"])
        fused = {i: w * dense.get(i, 0.0) + (1 - w) * sparse.get(i, 0.0) for i in dense.keys() | sparse.keys()}
        best = sorted(fused, key=fused.get, reverse=True)[:top_k]
        return [{**self.chunks[i], "score": round(fused[i], 4)} for i in best]

    def _dense(self, question: str, allowed: np.ndarray) -> dict[int, float]:
        """허용된 청크 중 내적 상위 candidate_k. 정확 검색(IndexFlatIP)이라 전체를 점수 매긴 뒤 거른다"""
        query = np.array([self.embedder.embed_query(question)], dtype=np.float32)
        scores, ids = self.faiss.search(query, self.faiss.ntotal)
        hits = [(int(i), float(s)) for i, s in zip(ids[0], scores[0]) if allowed[i]]
        return dict(hits[: int(self.rcfg["candidate_k"])])

    def _sparse(self, question: str, allowed: np.ndarray) -> dict[int, float]:
        scores = np.where(allowed, self.bm25.get_scores(self.tokenizer(question)), 0.0)
        top = np.argsort(-scores)[: int(self.rcfg["candidate_k"])]
        return {int(i): float(scores[i]) for i in top if scores[i] > 0}


# ====================================================================================================
# 발주기관 라우팅
# ====================================================================================================
_ORG_SUFFIX = (r"(?:공단|공사|연구원|연구소|대학교|대학|과학기술원|재단|진흥원|협회|센터|위원회|협력단|사회서비스원"
               r"|교육청|시청|도청|구청|은행|박물관|도서관|병원|진흥공사|관리원|정보원|평가원|개발원|기술원|산학협력단)")
_ORG_RE = re.compile(r"(?:한국|국립|재단법인|\(재\)|\(사\))?\s?[가-힣A-Za-z]{2,15}" + _ORG_SUFFIX)
_GENERIC_ORG = re.compile(r"(?:자문|평가|심의|운영|선정|추진|협의|기술|제안)?위원회$|^(?:해당|발주|주관|수요|관련|전문|계약|용역|사업|기타|본|각)"
                          r"|^[가-힣]{1,2}(?:센터|연구소)$|^산학협력단$")
def _has(text: str, org: str) -> bool:
    if org.isascii():
        return re.search(rf"(?<![A-Za-z]){re.escape(org)}(?![A-Za-z])", text, re.IGNORECASE) is not None
    return org in text


def _extract_orgs(texts) -> list[str]:
    """문서 앞부분들에서 기관명 추출. 먼저 찾은 이름이 들어 있는 더 긴 이름은 같은 기관으로 보고 건너뛴다"""
    orgs: list[str] = []
    for text in texts:
        for m in _ORG_RE.finditer(text[:2500]):
            name = re.sub(r"^\(?(재|사)\)?\s*|재단법인\s*", "", m.group().strip())
            if len(name) >= 4 and not _GENERIC_ORG.search(name) and not any(org in name for org in orgs):
                orgs.append(name)
    return orgs


class DocRouter:
    """질문에 나온 발주기관 → 그 기관 문서로 검색 범위를 좁힌다 (RFP 가 많을수록 정확도 ↑).
    기관명은 파일명·표지(PDF 앞 N쪽, HWP 표지·목차 — 청크에서 뺀 부분)에서 자동 추출하고, 표지가 없으면 본문 앞부분을 쓴다."""

    def __init__(self, docs: list[dict]):
        self.titles = {d["doc_id"]: d["title"] for d in docs}
        hay = {d["doc_id"]: f"{d['title']}\n" + (d["cover_text"] or d["head_text"][:1500]) for d in docs}
        self.org_docs: dict[str, set] = {}
        for org in _extract_orgs(hay.values()):
            doc_ids = {did for did, text in hay.items() if _has(text, org)}
            if doc_ids:
                self.org_docs[org] = doc_ids

    def route(self, question: str) -> dict[str, set]:
        """질문에 나온 기관 → 검색할 문서 id 들. 기관이 없으면 빈 dict(전체 검색)"""
        found = [org for org in self.org_docs if _has(question, org)]
        # '한국원자력연구원' 과 자동추출 '원자력연구원' 처럼 겹치면 긴 이름만
        found = [o for o in found if not any(o != p and o in p for p in found)]
        return {org: self._narrow(self.org_docs[org], question) for org in found}

    def _narrow(self, doc_ids: set, question: str) -> set:
        """같은 기관 문서가 여러 개면 질문 단어와 제목이 가장 많이 겹치는 문서로 좁힘"""
        if len(doc_ids) <= 1:
            return doc_ids
        words = set(re.findall(r"[가-힣A-Za-z0-9]{2,}", question))
        score = {d: sum(w in self.titles[d] for w in words) for d in doc_ids}
        best = max(score.values())
        return {d for d, s in score.items() if s == best} if best > 0 else doc_ids
