"""② 검색 — BM25(Kiwi) × Dense(FAISS) 하이브리드 + 요구사항 코드 정확 일치 + 발주기관 라우팅.
담당: 검색. 색인과 01 전처리의 chunks.jsonl · docs.jsonl, paths.org_csv의 기관 목록을 읽는다."""
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


_DUP_RATIO = 0.8
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*\s*(?:%|시간|개월|MB|GB|KB|TB|[초분일월년명건회개원부식인장])?")
_NEGATION = re.compile(r"않|아니|없|불가|금지|미적용|불포함|제외")


def _evidence_key(body: str) -> tuple[set[str], frozenset[str], frozenset[str]]:
    """중복 판정에 쓰는 (낱말들, 단위를 붙인 숫자들, 부정어가 든 낱말들)"""
    words = set(body.split())
    numbers = frozenset(re.sub(r"[,\s]", "", n) for n in _NUMBER.findall(body))
    return words, numbers, frozenset(w for w in words if _NEGATION.search(w))


def _is_dup(a: tuple, b: tuple) -> bool:
    """숫자 · 부정어가 모두 같고 큰 낱말 집합의 80%가 겹쳐야 중복이다.
    '2초/5초', '포함한다/포함하지 않는다' 처럼 낱말은 거의 같아도 뜻이 다른 근거는 둘 다 남긴다."""
    (words_a, numbers_a, negations_a), (words_b, numbers_b, negations_b) = a, b
    return (numbers_a == numbers_b and negations_a == negations_b
            and len(words_a & words_b) >= _DUP_RATIO * max(len(words_a), len(words_b)))


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
        self.code_chunks: dict[str, set[int]] = defaultdict(set)
        for i, chunk in enumerate(self.chunks):
            for code in find_codes(chunk["text"]):
                self.code_chunks[code].add(i)
        self.faiss = faiss.read_index(str(artifacts / "index" / "faiss.index"))
        tokens = json.loads((artifacts / "index" / "bm25_tokens.json").read_text(encoding="utf-8"))
        self.bm25 = BM25Okapi(tokens, k1=float(cfg["bm25"]["k1"]), b=float(cfg["bm25"]["b"]))
        self.embedder = Embedder(cfg["embedding"])
        self.tokenizer = KiwiTokenizer()
        self.router = DocRouter(read_jsonl(artifacts / "docs.jsonl"), read_csv_orgs(ROOT / cfg["paths"]["org_csv"]))
        self.rcfg = cfg["retrieval"]

    @observe(name="retrieve-context", as_type="retriever")
    def search(self, question: str, *, query: str | None = None) -> list[dict]:
        """원본 질문으로 기관을 고르고 query(없으면 원본)로 검색한다. 비교 질문은 기관별 결과를 번갈아 섞는다.
        요구사항 코드는 양쪽에서 모아 재작성 때 코드가 빠져도 정확 일치를 유지한다."""
        route = self.router.route(question)
        query = query or question
        codes = find_codes(question) | find_codes(query)
        if len(route) < 2:
            return self._pack(self._rank(query, codes, next(iter(route.values()), None)))
        lists = [self._rank(query, codes, doc_ids) for doc_ids in route.values()]
        return self._pack([hit for hit in chain.from_iterable(zip_longest(*lists)) if hit is not None])

    def _rank(self, question: str, codes: set[str], doc_ids: set | None) -> list[tuple[int, float]]:
        allowed = np.isin(self.doc_ids, list(doc_ids)) if doc_ids else np.ones(len(self.chunks), dtype=bool)
        w = float(self.rcfg["dense_weight"])
        # 가중치 0 인 쪽은 후보도 내지 않는다 — 내면 점수 0 짜리 무관한 청크가 결과에 섞인다
        dense = _minmax(self._dense(question, allowed)) if w > 0 else {}
        sparse = _minmax(self._sparse(question, allowed)) if w < 1 else {}
        fused = {i: w * dense.get(i, 0.0) + (1 - w) * sparse.get(i, 0.0) for i in dense.keys() | sparse.keys()}
        exact = self._exact(codes, allowed)
        fused |= {i: 0.0 for i in exact - fused.keys()}
        order = sorted(fused, key=lambda i: (i in exact, fused[i]), reverse=True)
        return [(i, fused[i]) for i in order]

    def _exact(self, codes: set[str], allowed: np.ndarray) -> set[int]:
        """요구사항 코드가 그대로 든 허용 청크"""
        hits = set().union(*(self.code_chunks.get(code, set()) for code in codes))
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
        """본문 토큰 예산 안에서 순서대로 담고 같은 문서의 거의 같은 청크(숫자 · 부정어까지 같은)는 제외한다.
        긴 청크는 건너뛰되 첫 청크는 예산을 넘어도 담아 빈 컨텍스트를 막는다."""
        budget = int(self.rcfg["token_budget"])
        picked: list[tuple[int, float, tuple]] = []
        used = 0
        for i, score in ranked:
            key = _evidence_key(self.chunks[i]["body"])
            if any(i == j or (self.chunks[i]["doc_id"] == self.chunks[j]["doc_id"] and _is_dup(key, seen))
                   for j, _, seen in picked):
                continue
            cost = self.embedder.token_counts([self.chunks[i]["body"]])[0]
            if picked and used + cost > budget:
                continue
            picked.append((i, score, key))
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
# 법인 형태는 앞뒤 어느 쪽에 붙어도 뗀다 (전각 괄호 포함): '(사)벤처기업협회', '(사）한국대학스포츠협의회', '케빈랩 주식회사', '인천공항운영서비스㈜', '한국철도공사 (용역)'
_LEGAL_FORM = re.compile(r"^[(（](?:재|사|주)[)）]\s*|^㈜\s*|^(?:재단|사단)법인\s*|^주식회사\s*|\s*[(（][^)）]*[)）]$|\s*㈜$|\s*주식회사$")
# 여러 낱말 CSV 기관명에서 따로 라우팅에 쓸 낱말: 기관 접미사나 시·군·구로 끝나는 낱말
# ('경희대학교 산학협력단' → '경희대학교', '경상북도 봉화군' → '봉화군', '아시아물위원회 사무국' → '아시아물위원회').
# 광역 지자체('인천광역시 동구' 의 '인천광역시')와 하위 조직 일반명('산학협력단', '조직위원회')은 따로 쓰지 않는다.
_ORG_PART = re.compile(_ORG_SUFFIX + r"$|대회$|[시군구]$")
_PROVINCE = re.compile(r"(?:특별시|광역시|특별자치시|특별자치도|도)$")
_GENERIC_PART = re.compile(r"^(?:(?:자문|평가|심의|운영|선정|추진|협의|기술|제안|조직)?위원회|산학협력단|사업단|사무국|연구소|센터)$")


def _is_org_name(name: str) -> bool:
    return len(name) >= 4 and not _GENERIC_ORG.search(name)


def _has(text: str, org: str) -> bool:
    if org.isascii():
        return re.search(rf"(?<![A-Za-z]){re.escape(org)}(?![A-Za-z])", text, re.IGNORECASE) is not None
    return org in text


def _extract_orgs(texts) -> list[str]:
    """문서 앞부분들에서 기관명 추출. 먼저 찾은 이름이 들어 있는 더 긴 이름은 같은 기관으로 보고 건너뛴다"""
    orgs: list[str] = []
    for text in texts:
        for m in _ORG_RE.finditer(text[:2500]):
            name = _LEGAL_FORM.sub("", m.group().strip())
            if _is_org_name(name) and not any(org in name for org in orgs):
                orgs.append(name)
    return orgs


def _source_key(name: str) -> str:
    """전체 파일명 비교에는 NFC를 적용하고 대소문자 차이를 무시한다. 기호와 확장자는 보존한다."""
    return unicodedata.normalize("NFC", name).lower()


def read_csv_orgs(path: Path) -> dict[str, str]:
    """담당자가 제공한 CSV의 파일명 · 발주기관 열을 읽는다"""
    orgs: dict[str, str] = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            name, org = row["파일명"], row["발주기관"]
            key = _source_key(name)
            if key in orgs and orgs[key] != org:
                raise ValueError(f"CSV 파일명에 서로 다른 발주 기관이 지정되었습니다: {name}")
            orgs[key] = org
    return orgs


def _file_key(name: str) -> str:
    """대소문자를 무시한 NFC 파일명에서 확장자와 기호를 제거한 비교 키"""
    stem = re.sub(r"\.(?:pdf|hwpx?)$", "", _source_key(name))
    return re.sub(r"[^0-9A-Za-z가-힣]", "", stem)


def _is_org_part(word: str) -> bool:
    if re.fullmatch(r"[A-Z]{3,}", word):  # 'KOICA 전자조달' → 'KOICA'
        return True
    return (len(word) >= 3 and bool(_ORG_PART.search(word)) and not _PROVINCE.search(word)
            and not _GENERIC_PART.match(word))


def _org_names(org: str) -> set[str]:
    """CSV의 기관명(법인 형태 제외) · 공백을 뺀 이름 · 여러 낱말이면 기관다운 낱말 각각.
    CSV 전체 이름에는 자동 추출용 필터(4글자 이상 · …위원회 제외)를 쓰지 않는다 — '케빈랩' · '중앙선거관리위원회'가 빠지지 않게."""
    name = _LEGAL_FORM.sub("", org.strip())
    names = {name, re.sub(r"\s+", "", name)}
    words = name.split()
    if len(words) > 1:
        names |= {w for w in words if _is_org_part(w)}
    return {n for n in names if len(n) >= 2}


def _file_org_names(source: str) -> set[str]:
    """'발주기관_사업명' 파일명의 앞부분. CSV는 정식 명칭('한국국제협력단', '수산업협동조합중앙회')이라도
    질문에는 파일명 쪽의 흔한 이름('KOICA', '수협중앙회')이 나오므로 함께 쓴다"""
    stem = unicodedata.normalize("NFC", source)
    return _org_names(stem.split("_", 1)[0]) if "_" in stem else set()


def _csv_org_docs(docs: list[dict], csv_orgs: dict[str, str]) -> dict[str, set]:
    """전체 파일명을 우선 맞추고, 정규화·앞부분 일치는 기관이 하나일 때만 쓴다.
    맞춘 문서에는 CSV 기관명과 파일명 앞부분의 기관명을 함께 붙인다."""
    by_source: dict[str, set[str]] = defaultdict(set)
    by_key: dict[str, set[str]] = defaultdict(set)
    for name, org in csv_orgs.items():
        by_source[_source_key(name)].add(org)
        by_key[_file_key(name)].add(org)
    org_docs: dict[str, set] = defaultdict(set)
    for doc in docs:
        key = _file_key(doc["source"])
        orgs = (by_source.get(_source_key(doc["source"])) or by_key.get(key)
                or set().union(*(orgs for k, orgs in by_key.items() if k.startswith(key))))
        if len(orgs) == 1:
            for name in _org_names(next(iter(orgs))) | _file_org_names(doc["source"]):
                org_docs[name].add(doc["doc_id"])
    return org_docs


class DocRouter:
    """질문에 나온 발주기관 → 그 기관 문서로 검색 범위를 좁힌다 (RFP 가 많을수록 정확도 ↑).
    기관명은 담당자 CSV와 파일명·표지에서 모으고, 표지가 없으면 본문 앞부분을 쓴다."""

    def __init__(self, docs: list[dict], csv_orgs: dict[str, str]):
        self.titles = {d["doc_id"]: d["title"] for d in docs}
        hay = {d["doc_id"]: f"{d['title']}\n" + (d["cover_text"] or d["head_text"][:1500]) for d in docs}
        self.org_docs: dict[str, set] = defaultdict(set)
        for org in _extract_orgs(hay.values()):
            self.org_docs[org] |= {did for did, text in hay.items() if _has(text, org)}
        for org, doc_ids in _csv_org_docs(docs, csv_orgs).items():
            # 다른 문서 제목 · 표지에 같은 이름이 나오면 그 문서도 넣는다 (예: '평택시' 사업을 다른 업체가 발주)
            self.org_docs[org] |= doc_ids | {did for did, text in hay.items() if _has(text, org)}
        self.org_docs = {org: doc_ids for org, doc_ids in self.org_docs.items() if doc_ids}

    def unrouted_titles(self) -> list[str]:
        """기관명이 하나도 연결되지 않은 문서 제목. 이 문서들은 질문에 기관명이 나와도 전체 검색으로만 찾힌다"""
        routed = set().union(*self.org_docs.values())
        return sorted(title for doc_id, title in self.titles.items() if doc_id not in routed)

    def route(self, question: str) -> dict[str, set]:
        """질문에 나온 기관 → 검색할 문서 id 들. 기관이 없으면 빈 dict(전체 검색)"""
        found = [org for org in self.org_docs if _has(question, org)]
        # '한국원자력연구원' 과 자동추출 '원자력연구원' 처럼 겹치면 긴 이름만
        found = [o for o in found if not any(o != p and o in p for p in found)]
        # 같은 기관의 여러 문서 중 하나를 제목 낱말로 고르지 않는다 — 질문의 '대용량 전송' 이 다른 사업 제목
        # ('대용량 자료전송시스템')과 겹쳐 정답 문서를 빼던 문제. 기관 문서 안의 순위는 하이브리드 점수가 정한다.
        return {org: self.org_docs[org] for org in found}
