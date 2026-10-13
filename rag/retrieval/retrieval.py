"""② 검색 — BM25(Kiwi) × Dense(FAISS) 하이브리드 + 요구사항 코드 정확 일치 + 발주기관 라우팅.
담당: 검색.  indexing.py 가 만든 색인(artifacts/index/)과 01 전처리의 chunks.jsonl · docs.jsonl,
발주 기관 목록 CSV(config.yaml 의 paths.org_csv — 없으면 docs.jsonl 로 만든다)를 읽는다."""
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

# 같은 문서의 두 청크가 숫자까지 같고 낱말의 이 비율 이상이 겹치면(짧은 쪽 기준) 같은 내용으로 보고 뒤의 것을 버린다.
# 청크 겹침(overlap_ratio 0.2)만큼 겹치는 이웃 청크는 남고, 거의 같은 청크만 빠진다
_DUP_RATIO = 0.8
_NUMBER = re.compile(r"\d[\d,.]*")


def _minmax(d: dict[int, float]) -> dict[int, float]:
    if not d:
        return {}
    lo, hi = min(d.values()), max(d.values())
    if hi - lo < 1e-12:
        return {k: 1.0 for k in d}
    return {k: (v - lo) / (hi - lo) for k, v in d.items()}


def _signature(chunk: dict) -> tuple[str, set[str], set[str]]:
    """중복 비교용 (문서 id, 숫자들, 낱말들). 숫자는 쉼표를 뺀다 ('300,000,000' = '300000000')"""
    body = chunk["body"]
    return chunk["doc_id"], {n.replace(",", "").rstrip(".") for n in _NUMBER.findall(body)}, set(body.split())


def _is_dup(a: tuple[str, set[str], set[str]], b: tuple[str, set[str], set[str]]) -> bool:
    """같은 문서 · 같은 숫자이면서 낱말이 거의 같은 청크. 문서가 다르면(다른 사업) 문구가 같아도,
    금액 · 기간 · 비율 같은 숫자가 하나라도 다르면 낱말이 거의 같아도 서로 다른 근거로 본다"""
    (doc_a, nums_a, words_a), (doc_b, nums_b, words_b) = a, b
    return doc_a == doc_b and nums_a == nums_b and len(words_a & words_b) >= _DUP_RATIO * min(len(words_a), len(words_b))


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
        docs = read_jsonl(artifacts / "docs.jsonl")
        self.router = DocRouter(docs, load_org_csv(docs, ROOT / cfg["paths"]["org_csv"]))
        self.rcfg = cfg["retrieval"]

    @observe(name="retrieve-context", as_type="retriever")
    def search(self, question: str, *, query: str | None = None) -> list[dict]:
        """원본 질문(question)으로 발주기관을 고르고, 검색용 질문(query — 재작성한 질문, 없으면 원본)으로 찾는다
        → 토큰 예산 안의 상위 청크(score = 하이브리드 점수). 두 기관 이상을 비교하는 질문이면 기관별로 찾아 번갈아 섞는다.
        요구사항 코드는 원본과 query 양쪽에서 모은다 (재작성에서 코드가 빠져도 정확 일치를 잃지 않게)"""
        route = self.router.route(question)
        query = query or question
        codes = find_codes(question) | find_codes(query)
        if len(route) < 2:
            return self._pack(self._rank(query, codes, next(iter(route.values()), None)))
        lists = [self._rank(query, codes, doc_ids) for doc_ids in route.values()]
        return self._pack([hit for hit in chain.from_iterable(zip_longest(*lists)) if hit is not None])

    def _rank(self, query: str, codes: set[str], doc_ids: set | None) -> list[tuple[int, float]]:
        """후보 청크 (번호, 하이브리드 점수) — 코드 정확 일치 청크가 먼저, 그다음 점수 순"""
        allowed = np.isin(self.doc_ids, list(doc_ids)) if doc_ids else np.ones(len(self.chunks), dtype=bool)
        w = float(self.rcfg["dense_weight"])
        # 가중치 0 인 쪽은 후보도 내지 않는다 — 내면 점수 0 짜리 무관한 청크가 결과에 섞인다
        dense = _minmax(self._dense(query, allowed)) if w > 0 else {}
        sparse = _minmax(self._sparse(query, allowed)) if w < 1 else {}
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
        """순위대로 본문 토큰 합이 token_budget 안에 들도록 담는다. 앞에 담은 청크와 거의 같은 청크,
        남은 예산보다 긴 청크는 건너뛴다 (멈추면 기관 비교 질문에서 긴 청크 하나 뒤의 다른 기관 청크가 빠진다).
        첫 청크는 예산보다 길어도 담는다 (빈 컨텍스트 방지)"""
        budget = int(self.rcfg["token_budget"])
        picked: list[tuple[int, float, tuple]] = []
        used = 0
        for i, score in ranked:
            sig = _signature(self.chunks[i])
            if any(i == j or _is_dup(sig, seen) for j, _, seen in picked):
                continue
            cost = self.embedder.token_counts([self.chunks[i]["body"]])[0]
            if picked and used + cost > budget:
                continue
            picked.append((i, score, sig))
            used += cost
        return [{**self.chunks[i], "score": round(score, 4)} for i, score, _ in picked]


# ====================================================================================================
# 발주기관 라우팅
# ====================================================================================================
_ORG_SUFFIX = (r"(?:공단|공사|연구원|연구소|대학교|대학|과학기술원|재단|진흥원|협회|센터|위원회|협력단|사회서비스원"
               r"|교육청|시청|도청|구청|은행|박물관|도서관|병원|진흥공사|관리원|정보원|평가원|개발원|기술원|산학협력단"
               r"|중앙회|협의회|진흥회|체육회|상공회의소|의료원|테크노파크|영화제)")
_ORG_RE = re.compile(r"(?:한국|국립|재단법인|\(재\)|\(사\))?\s?[가-힣A-Za-z]{2,15}" + _ORG_SUFFIX)
# 기관명이 아닌 이름: '제안서평가위원회' · '조직위원회' 같은 절차 위원회('중앙선거관리위원회' 는 기관), '해당 기관' 같은 일반어,
# 파일명 · CSV 의 기관 칸을 띄어 쓴 낱말로 가르면 나오는 '입찰공고' · '전자조달' · '(용역)'
_GENERIC_ORG = re.compile(r"(?:자문|평가|심의|운영|선정|추진|협의|협상|기술|제안|조직)(?:위원회|협의회)$"
                          r"|^(?:해당|발주|주관|수요|관련|전문|계약|용역|사업|기타|본|각)"
                          r"|^[가-힣]{1,2}(?:센터|연구소)$|^산학협력단$|(?:공고|조달)$|^\(.*\)$")
_LEGAL_FORM = re.compile(r"^\((?:재|사)\)\s*|^(?:재단|사단)법인\s*|^주식회사\s*|\s*주식회사$|\s*\(주\)$")
# '안양시' · '봉화군' 처럼 세 글자 시 · 군 · 구 이름 (네 글자 미만이어도 기관명으로 쓴다)
_ADMIN = re.compile(r"[가-힣]{2}[시군구]")


def _has(text: str, org: str) -> bool:
    """text 에 기관명 org 가 있나. 한글 이름은 띄어쓰기를 무시한다 ('아시아 물 위원회' = '아시아물위원회')"""
    if org.isascii():
        return re.search(rf"(?<![A-Za-z]){re.escape(org)}(?![A-Za-z])", text, re.IGNORECASE) is not None
    return org.replace(" ", "") in text.replace(" ", "")


def _is_org_name(name: str, min_len: int = 4) -> bool:
    """기관명으로 쓸 이름: min_len 자 이상(또는 시 · 군 · 구 이름), 숫자만이 아니고, 일반어가 아님"""
    long_enough = len(name) >= min_len or _ADMIN.fullmatch(name) is not None
    return long_enough and re.search(r"[가-힣A-Za-z]{2}", name) is not None and not _GENERIC_ORG.search(name)


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


# 표지의 '발주기관 : 한국철도공사' · '수요기관명 | 고려대학교' 같은 칸
_ORG_LABEL = re.compile(r"(?:발주|수요|주관)\s*기\s*관\s*명?\s*[:：|]?\s*([^\n|]{2,60})")


def _clean_org(org: str) -> str:
    """기관명 정리: 전각 괄호 · ㈜ 를 NFKC 로 맞추고 '(사)' · '재단법인' · '(주)' 같은 법인 표기와
    '입찰공고' · '(용역)' · '산학협력단' 같은 일반어 낱말을 뺀다 ('한국철도공사 (용역)' → '한국철도공사')"""
    name = _LEGAL_FORM.sub("", unicodedata.normalize("NFKC", org).strip())
    return " ".join(word for word in name.split() if not _GENERIC_ORG.search(word))


def _file_org(source: str) -> str:
    """파일명 '발주기관_사업명' 의 앞부분 → 정리한 기관명. '_' 가 없으면 빈 칸.
    HWP 표지에는 기관명이 없는 문서가 많아(부서명만 있거나 사업명만 있음) 파일명이 가장 확실한 출처다"""
    return _clean_org(source.split("_", 1)[0]) if "_" in source else ""


def _doc_org(doc: dict) -> str:
    """문서 하나의 발주 기관: ① 파일명 앞부분 ② 표지(없으면 본문 앞부분)의 '발주기관 : …' 칸
    ③ 제목의 기관명 ④ 표지·본문 앞부분에 처음 나온 기관명. 못 찾으면 빈 칸"""
    if _file_org(doc["source"]):
        return _file_org(doc["source"])
    head = doc["cover_text"] or doc["head_text"]
    label = _ORG_LABEL.search(head)
    found = (_extract_orgs([label.group(1)]) if label else []) or _extract_orgs([doc["title"]]) or _extract_orgs([head])
    return found[0] if found else ""


def write_org_csv(docs: list[dict], path: Path):
    """docs.jsonl 로 발주 기관 목록 CSV('파일명' · '발주 기관' 열)를 만든다. 엑셀에서 한글이 깨지지 않게 utf-8-sig"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["파일명", "발주 기관"])
        writer.writeheader()
        writer.writerows({"파일명": d["source"], "발주 기관": _doc_org(d)} for d in docs)


def load_org_csv(docs: list[dict], path: Path) -> dict[str, str]:
    """발주 기관 목록 CSV 를 읽는다. 파일이 없으면 문서 표지 · 제목으로 먼저 만든다 (있으면 손대지 않음)"""
    if not path.exists():
        write_org_csv(docs, path)
        print(f"발주 기관 목록이 없어 문서 표지 · 제목으로 만들었습니다: {path}")
    return read_csv_orgs(path)


def _file_key(name: str) -> str:
    """파일명 비교 키: 완성형(NFC) · 확장자와 기호 제거. 01 전처리가 파일명 기호를 '_' 로 바꾸고 긴 이름을 자른 것을 흡수"""
    stem = re.sub(r"\.(?:pdf|hwpx?)$", "", unicodedata.normalize("NFC", name), flags=re.IGNORECASE)
    return re.sub(r"[^0-9A-Za-z가-힣]", "", stem)


def _org_names(org: str) -> set[str]:
    """기관명 → 질문에서 찾을 이름들: 전체('경기도 안양시') · '…사무국' 을 뗀 이름 · 띄어 쓴 낱말 각각('안양시').
    낱말 하나는 4자 이상이거나 시 · 군 · 구 이름만 쓴다 ('경기도' · '구미' 처럼 넓거나 짧은 낱말은 다른 문서로 샌다)"""
    name = _clean_org(org)
    names = {name, re.sub(r"사무국$", "", name)} if _is_org_name(name, min_len=3) else set()
    return names | {word for word in name.split() if _is_org_name(word)}


def _listed_org_docs(docs: list[dict], csv_orgs: dict[str, str]) -> dict[str, set]:
    """문서마다 파일명 앞부분과 CSV 발주 기관으로 {기관명: 문서 id 들}.
    CSV 의 파일명은 docs.jsonl 의 source 와 맞추고, 잘린 파일명은 앞부분이 같으면 같은 파일로 본다"""
    by_key = {_file_key(name): org for name, org in csv_orgs.items()}
    org_docs: dict[str, set] = defaultdict(set)
    for d in docs:
        key = _file_key(d["source"])
        csv_org = by_key.get(key) or next((o for k, o in by_key.items() if k.startswith(key)), "")
        for name in _org_names(_file_org(d["source"])) | _org_names(csv_org):
            org_docs[name].add(d["doc_id"])
    return org_docs


def _labelled_orgs(doc: dict) -> list[str]:
    """제목과 표지의 '발주기관 · 주관기관 · 수요기관' 칸에 적힌 기관명 ('수협중앙회' 문서의 '수산업협동조합중앙회').
    표지 · 본문 전체를 훑지 않는다 — 협력 · 지원 기관('한국산업기술기획평가원'), 일반어('우리대학' · '종합병원'),
    직함('참여연구원'), 시설('IT운영센터')까지 기관명으로 잡혀 엉뚱한 문서로 좁히기 때문이다"""
    head = (doc["cover_text"] or doc["head_text"])[:2500]
    return _extract_orgs([doc["title"], *(m.group(1) for m in _ORG_LABEL.finditer(head))])


class DocRouter:
    """질문에 나온 발주기관 → 그 기관 문서로 검색 범위를 좁힌다 (RFP 가 많을수록 정확도 ↑).
    기관명은 ① 파일명 앞부분('경기도 안양시_…') ② 발주 기관 목록 CSV
    ③ 제목과 표지(PDF 앞 N쪽, HWP 표지·목차 — 청크에서 뺀 부분)의 발주 · 주관 · 수요기관 칸에서 모은다.
    표지가 없으면 본문 앞부분을 쓴다. ③ 은 파일명과 다른 이름('수산업협동조합중앙회')을 더한다."""

    def __init__(self, docs: list[dict], csv_orgs: dict[str, str]):
        self.titles = {d["doc_id"]: d["title"] for d in docs}
        self.org_docs: dict[str, set] = defaultdict(set)
        for d in docs:
            for org in _labelled_orgs(d):
                self.org_docs[org].add(d["doc_id"])
        for org, doc_ids in _listed_org_docs(docs, csv_orgs).items():
            self.org_docs[org] |= doc_ids
        self.org_docs = {org: doc_ids for org, doc_ids in self.org_docs.items() if doc_ids}

    def route(self, question: str) -> dict[str, set]:
        """질문에 나온 기관 → 검색할 문서 id 들. 기관이 없으면 빈 dict(전체 검색).
        '경상북도 봉화군' 처럼 두 이름이 같은 문서를 가리키면 하나만 남긴다 (기관 비교 질문으로 오인하지 않게)"""
        found = [org for org in self.org_docs if _has(question, org)]
        # '한국원자력연구원' 과 자동추출 '원자력연구원' 처럼 겹치면 긴 이름만
        found = [o for o in found if not any(o != p and _has(p, o) for p in found)]
        route: dict[str, set] = {}
        for org in found:
            doc_ids = self._narrow(self.org_docs[org], question)
            if doc_ids not in route.values():
                route[org] = doc_ids
        return route

    def _narrow(self, doc_ids: set, question: str) -> set:
        """같은 기관 문서가 여러 개면 질문 단어와 제목이 가장 많이 겹치는 문서로 좁힘"""
        if len(doc_ids) <= 1:
            return doc_ids
        words = set(re.findall(r"[가-힣A-Za-z0-9]{2,}", question))
        score = {d: sum(w in self.titles[d] for w in words) for d in doc_ids}
        best = max(score.values())
        return {d for d, s in score.items() if s == best} if best > 0 else doc_ids
