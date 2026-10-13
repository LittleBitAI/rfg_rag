"""② 검색 — BM25(Kiwi) × Dense(FAISS) 하이브리드 + 요구사항 코드 정확 일치 + 발주기관 라우팅.
담당: 검색.  indexing.py 가 만든 색인(artifacts/index/)과 01 전처리의 chunks.jsonl · docs.jsonl,
발주 기관 목록 CSV(config.yaml 의 paths.org_csv)를 읽는다."""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections import defaultdict
from itertools import chain, zip_longest
from pathlib import Path

import faiss
import numpy as np
from langfuse import observe
from rank_bm25 import BM25Okapi

from ..config import ROOT, read_jsonl
from .indexing import Embedder, KiwiTokenizer, find_codes

# 두 청크 낱말의 이 비율 이상이 겹치면(짧은 쪽 기준) 같은 내용으로 보고 뒤의 것을 버린다.
# 청크 겹침(overlap_ratio 0.2)만큼 겹치는 이웃 청크는 남고, 거의 같은 청크만 빠진다
_DUP_RATIO = 0.8


def _minmax(d: dict[int, float]) -> dict[int, float]:
    if not d:
        return {}
    lo, hi = min(d.values()), max(d.values())
    if hi - lo < 1e-12:
        return {k: 1.0 for k in d}
    return {k: (v - lo) / (hi - lo) for k, v in d.items()}


def _is_dup(a: set[str], b: set[str]) -> bool:
    return len(a & b) >= _DUP_RATIO * min(len(a), len(b))


class HybridIndex:
    """final = w·Dense + (1-w)·BM25 — 두 후보군을 각각 min-max 정규화한 뒤 가중합 (w = dense_weight, 0=BM25만, 1=Dense만).
    질문의 요구사항 코드(SFR-001)가 그대로 든 청크는 맨 앞에 둔다.
    질문에 발주기관이 나오면 그 기관 문서 안에서만 찾는다 (DocRouter).
    결과는 개수가 아니라 토큰 예산(token_budget)으로 자르고, 거의 같은 청크는 하나만 남긴다."""

    def __init__(self, artifacts: Path, cfg: dict):
        self.chunks = read_jsonl(artifacts / "chunks.jsonl")
        self.doc_ids = np.array([c["doc_id"] for c in self.chunks])
        self.code_chunks: dict[str, set[int]] = defaultdict(set)
        for i, c in enumerate(self.chunks):
            for code in find_codes(c["text"]):
                self.code_chunks[code].add(i)
        self.faiss = faiss.read_index(str(artifacts / "index" / "faiss.index"))
        tokens = json.loads((artifacts / "index" / "bm25_tokens.json").read_text(encoding="utf-8"))
        self.bm25 = BM25Okapi(tokens, k1=float(cfg["bm25"]["k1"]), b=float(cfg["bm25"]["b"]))
        self.embedder = Embedder(cfg["embedding"])
        self.tokenizer = KiwiTokenizer()
        self.router = DocRouter(read_jsonl(artifacts / "docs.jsonl"), read_csv_orgs(ROOT / cfg["paths"]["org_csv"]))
        self.rcfg = cfg["retrieval"]

    @observe(name="retrieve-context", as_type="retriever")
    def search(self, question: str) -> list[dict]:
        """질문 → 토큰 예산 안의 상위 청크(score = 하이브리드 점수). 두 기관 이상을 비교하는 질문이면 기관별로 찾아 번갈아 섞는다"""
        route = self.router.route(question)
        if len(route) < 2:
            return self._pack(self._rank(question, next(iter(route.values()), None)))
        lists = [self._rank(question, doc_ids) for doc_ids in route.values()]
        return self._pack([hit for hit in chain.from_iterable(zip_longest(*lists)) if hit is not None])

    def _rank(self, question: str, doc_ids: set | None) -> list[tuple[int, float]]:
        """후보 청크 (번호, 하이브리드 점수) — 코드 정확 일치 청크가 먼저, 그다음 점수 순"""
        allowed = np.isin(self.doc_ids, list(doc_ids)) if doc_ids else np.ones(len(self.chunks), dtype=bool)
        w = float(self.rcfg["dense_weight"])
        # 가중치 0 인 쪽은 후보도 내지 않는다 — 내면 점수 0 짜리 무관한 청크가 결과에 섞인다
        dense = _minmax(self._dense(question, allowed)) if w > 0 else {}
        sparse = _minmax(self._sparse(question, allowed)) if w < 1 else {}
        fused = {i: w * dense.get(i, 0.0) + (1 - w) * sparse.get(i, 0.0) for i in dense.keys() | sparse.keys()}
        exact = self._exact(question, allowed)
        fused |= {i: 0.0 for i in exact - fused.keys()}
        order = sorted(fused, key=lambda i: (i in exact, fused[i]), reverse=True)
        return [(i, fused[i]) for i in order]

    def _exact(self, question: str, allowed: np.ndarray) -> set[int]:
        """질문의 요구사항 코드가 그대로 든 허용 청크"""
        hits = set().union(*(self.code_chunks.get(code, set()) for code in find_codes(question)))
        return {i for i in hits if allowed[i]}

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

    def _pack(self, ranked: list[tuple[int, float]]) -> list[dict]:
        """순위대로 본문 토큰 합이 token_budget 안에 들도록 담는다. 앞에 담은 청크와 거의 같은 청크,
        남은 예산보다 긴 청크는 건너뛴다 (멈추면 기관 비교 질문에서 긴 청크 하나 뒤의 다른 기관 청크가 빠진다).
        첫 청크는 예산보다 길어도 담는다 (빈 컨텍스트 방지)"""
        budget = int(self.rcfg["token_budget"])
        picked: list[tuple[int, float, set[str]]] = []
        used = 0
        for i, score in ranked:
            words = set(self.chunks[i]["body"].split())
            if any(i == j or _is_dup(words, seen) for j, _, seen in picked):
                continue
            cost = self.embedder.token_counts([self.chunks[i]["body"]])[0]
            if picked and used + cost > budget:
                continue
            picked.append((i, score, words))
            used += cost
        return [{**self.chunks[i], "score": round(score, 4)} for i, score, _ in picked]


# ====================================================================================================
# 발주기관 라우팅
# ====================================================================================================
_ORG_SUFFIX = (r"(?:공단|공사|연구원|연구소|대학교|대학|과학기술원|재단|진흥원|협회|센터|위원회|협력단|사회서비스원"
               r"|교육청|시청|도청|구청|은행|박물관|도서관|병원|진흥공사|관리원|정보원|평가원|개발원|기술원|산학협력단)")
_ORG_RE = re.compile(r"(?:한국|국립|재단법인|\(재\)|\(사\))?\s?[가-힣A-Za-z]{2,15}" + _ORG_SUFFIX)
_GENERIC_ORG = re.compile(r"(?:자문|평가|심의|운영|선정|추진|협의|기술|제안)?위원회$|^(?:해당|발주|주관|수요|관련|전문|계약|용역|사업|기타|본|각)"
                          r"|^[가-힣]{1,2}(?:센터|연구소)$|^산학협력단$")
_LEGAL_FORM = re.compile(r"^\((?:재|사)\)\s*|^(?:재단|사단)법인\s*|^주식회사\s*|\s*\(주\)$")


def _has(text: str, org: str) -> bool:
    if org.isascii():
        return re.search(rf"(?<![A-Za-z]){re.escape(org)}(?![A-Za-z])", text, re.IGNORECASE) is not None
    return org in text


def _is_org_name(name: str) -> bool:
    return len(name) >= 4 and not _GENERIC_ORG.search(name)


def _extract_orgs(texts) -> list[str]:
    """문서 앞부분들에서 기관명 추출. 먼저 찾은 이름이 들어 있는 더 긴 이름은 같은 기관으로 보고 건너뛴다"""
    orgs: list[str] = []
    for text in texts:
        for m in _ORG_RE.finditer(text[:2500]):
            name = _LEGAL_FORM.sub("", m.group().strip())
            if _is_org_name(name) and not any(org in name for org in orgs):
                orgs.append(name)
    return orgs


def read_csv_orgs(path: Path) -> dict[str, str]:
    """발주 기관 목록 CSV → {파일명: 발주 기관} ('파일명' · '발주 기관' 열)"""
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {row["파일명"]: row["발주 기관"] for row in csv.DictReader(f)}


def _file_key(name: str) -> str:
    """파일명 비교 키: 완성형(NFC) · 확장자와 기호 제거. 01 전처리가 파일명 기호를 '_' 로 바꾸고 긴 이름을 자른 것을 흡수"""
    stem = re.sub(r"\.(?:pdf|hwpx?)$", "", unicodedata.normalize("NFC", name), flags=re.IGNORECASE)
    return re.sub(r"[^0-9A-Za-z가-힣]", "", stem)


def _org_names(org: str) -> set[str]:
    """CSV 기관명 → 질문에서 찾을 이름들: 전체 · 띄어쓰기 없앤 꼴 · 띄어 쓴 낱말 각각('경기도 남양주시' → '남양주시')"""
    name = _LEGAL_FORM.sub("", org.strip())
    return {n for n in {name, name.replace(" ", ""), *name.split()} if _is_org_name(n)}


def _csv_org_docs(docs: list[dict], csv_orgs: dict[str, str]) -> dict[str, set]:
    """CSV 의 파일명을 docs.jsonl 의 source 와 맞춰 {기관명: 문서 id 들}. 잘린 파일명은 앞부분이 같으면 같은 파일"""
    by_key = {_file_key(name): org for name, org in csv_orgs.items()}
    org_docs: dict[str, set] = defaultdict(set)
    for d in docs:
        key = _file_key(d["source"])
        org = by_key.get(key) or next((o for k, o in by_key.items() if k.startswith(key)), None)
        if org:
            for name in _org_names(org):
                org_docs[name].add(d["doc_id"])
    return org_docs


class DocRouter:
    """질문에 나온 발주기관 → 그 기관 문서로 검색 범위를 좁힌다 (RFP 가 많을수록 정확도 ↑).
    기관명은 ① 발주 기관 목록 CSV 와 ② 파일명·표지(PDF 앞 N쪽, HWP 표지·목차 — 청크에서 뺀 부분)에서 모은다.
    표지가 없으면 본문 앞부분을 쓴다."""

    def __init__(self, docs: list[dict], csv_orgs: dict[str, str]):
        self.titles = {d["doc_id"]: d["title"] for d in docs}
        hay = {d["doc_id"]: f"{d['title']}\n" + (d["cover_text"] or d["head_text"][:1500]) for d in docs}
        self.org_docs: dict[str, set] = defaultdict(set)
        for org in _extract_orgs(hay.values()):
            self.org_docs[org] |= {did for did, text in hay.items() if _has(text, org)}
        for org, doc_ids in _csv_org_docs(docs, csv_orgs).items():
            self.org_docs[org] |= doc_ids
        self.org_docs = {org: doc_ids for org, doc_ids in self.org_docs.items() if doc_ids}

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
