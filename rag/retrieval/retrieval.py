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
from types import MappingProxyType

import faiss
import numpy as np
from langfuse import observe
from rank_bm25 import BM25Okapi

from ..config import ROOT, read_jsonl
from .indexing import Embedder, KiwiTokenizer, find_codes, search_texts, texts_digest
from .quantity_filter import choose_values, content_query, introduction, project_condition, substantive


_DUP_RATIO = 0.8
_LINK_TOKENS = 600  # 찾은 청크 하나에 함께 담는 연결 청크의 토큰 상한 — 연결 청크가 토큰 예산을 다 차지하지 않게


class FilterHits(list):
    def __init__(self, hits, summary, values, chosen):
        super().__init__(hits)
        self.summary = summary
        self.values = values
        self.chosen = chosen


def retrieval_fields(index, question: str, query: str, *, reused: bool) -> tuple:
    """04와 검색 전용 재실행이 동일한 검색 기록 형식을 쓴다."""
    hits, candidates = index.search_with_candidates(question, query=query)
    return hits, {"ranked_candidates": [dict(c) for c in candidates],
                  "context_chunk_ids": [h["chunk_id"] for h in hits],
                  "retrieval_settings": {**index.rcfg, "chunk_file": index.chunk_file,
                                         "k_values": [5, 10, 20], "stored_rewrites_reused": reused}}


def _is_dup(a: set[str], b: set[str]) -> bool:
    """큰 낱말 집합의 80%가 겹쳐야 중복이다. 짧은 코드만 겹치는 상세 근거는 남긴다."""
    return len(a & b) >= _DUP_RATIO * max(len(a), len(b))


def _minmax(d: dict[int, float]) -> dict[int, float]:
    if not d:
        return {}
    lo, hi = min(d.values()), max(d.values())
    if hi - lo < 1e-12:
        return {k: 1.0 for k in d}
    return {k: (v - lo) / (hi - lo) for k, v in d.items()}


def _link_index(chunks: list[dict]) -> tuple[dict[str, set[int]], list[list[int]]]:
    """(요구사항 코드 → 청크들, 청크마다 함께 담을 연결 청크들 — 담을 우선순위 순서).
    전처리 패키지의 연결 정보를 쓴다. 우선순위는 묶음의 첫 청크(표 머리글 · 요구사항 ID 와 명칭 — v11 의 이어지는 표
    청크엔 머리글이 없기도 하다), 그다음 찾은 청크에 가까운 청크 순이다 — 긴 표에서도 이어지는 행이 담기게.
    - 요구사항 소속(requirement_key · requirement_ids): 요구사항 ID 와 상세 내용이 다른 청크로 나뉘어 상세 청크 본문에
      ID 가 없어도 그 ID 로 정확 일치하고, 같은 요구사항의 다른 청크(ID · 명칭 / 상세 내용)를 연결 청크로 둔다.
    - 표 연결(table_refs): 한 표가 여러 청크로 나뉘었으면 같은 표의 다른 청크를 연결 청크로 둔다.
    두 연결 모두 같은 문서 안에서만 묶는다 — 연결 청크가 기관 라우팅(DocRouter)을 벗어나지 않게.
    01 에서 직접 청크를 나눈 경우엔 연결 정보가 없어 본문 속 코드만 쓴다."""
    code_chunks: dict[str, set[int]] = defaultdict(set)
    groups: dict[tuple, list[int]] = defaultdict(list)
    for i, chunk in enumerate(chunks):
        member_of = find_codes(" ".join([*chunk.get("requirement_ids", []), chunk.get("requirement_key") or ""]))
        for code in find_codes(chunk["text"]) | member_of:
            code_chunks[code].add(i)
        if chunk.get("requirement_key"):
            groups[("requirement", chunk["doc_id"], chunk["requirement_key"])].append(i)
        for table in chunk.get("table_refs", []):
            groups[("table", chunk["doc_id"], table)].append(i)
    return code_chunks, _link_priority(groups.values(), len(chunks))


def _link_priority(groups, size: int) -> list[list[int]]:
    """청크마다 같은 묶음의 다른 청크를 (묶음의 첫 청크가 아님, 거리, 위치) 순으로 늘어놓는다"""
    priority: list[dict[int, tuple]] = [{} for _ in range(size)]
    for members in groups:
        for i in members:
            for j in members:
                if j != i:
                    key = (j != members[0], abs(j - i), j)
                    priority[i][j] = min(key, priority[i].get(j, key))
    return [sorted(linked, key=linked.get) for linked in priority]


def _check_index(index_dir: Path, texts: list[str]):
    """색인이 지금 청크의 검색 글로 만들어졌는지 확인한다. 01 을 다시 돌렸거나 검색 글 만드는 방식(요구사항 머리말)이
    바뀌었는데 색인을 그대로 두면, 벡터 · BM25 순서가 청크와 어긋나 엉뚱한 청크가 찾힌다."""
    digest = index_dir / "texts.sha256"
    if not digest.exists() or digest.read_text(encoding="utf-8").strip() != texts_digest(texts):
        raise ValueError("검색 색인이 지금 청크(artifacts/chunks.jsonl)와 맞지 않습니다 — "
                         "02 의 build_index 셀을 다시 실행하세요")


class HybridIndex:
    """final = w·Dense + (1-w)·BM25 — 두 후보군을 각각 min-max 정규화한 뒤 가중합 (w = dense_weight, 0=BM25만, 1=Dense만).
    질문에 발주기관이 나오면 그 기관 문서 안에서만 찾는다 (DocRouter).
    찾은 청크에 연결 청크(같은 요구사항의 ID · 명칭 / 상세 내용, 같은 표의 나뉜 부분)가 있으면 바로 뒤에 함께 담는다."""

    def __init__(self, artifacts: Path, cfg: dict):
        self.tokenizer = KiwiTokenizer()
        stored = json.loads((artifacts / "index" / "bm25_tokens.json").read_text(encoding="utf-8"))
        if not isinstance(stored, dict) or stored.get("tokenizer") != self.tokenizer.fingerprint:
            raise ValueError("BM25 tokenizer mismatch or missing fingerprint. "
                             "Rebuild the index with 02_retrieval.ipynb's build_index cell before searching.")
        self.chunks = read_jsonl(artifacts / "chunks.jsonl")
        _check_index(artifacts / "index", search_texts(self.chunks))
        self.doc_ids = np.array([c["doc_id"] for c in self.chunks])
        self.code_chunks, self.links = _link_index(self.chunks)
        self.faiss = faiss.read_index(str(artifacts / "index" / "faiss.index"))
        self.bm25 = BM25Okapi(stored["tokens"], k1=float(cfg["bm25"]["k1"]), b=float(cfg["bm25"]["b"]))
        self.embedder = Embedder(cfg["embedding"])
        self.router = DocRouter(read_jsonl(artifacts / "docs.jsonl"), read_csv_orgs(ROOT / cfg["paths"]["org_csv"]))
        self.rcfg = cfg["retrieval"]
        self.chunk_file = str((artifacts / "chunks.jsonl").resolve())
        self.quantity_rows = read_jsonl(artifacts / "index" / "quantities.jsonl")
        self.quantity_phrases = json.loads((artifacts / "index" / "quantity_phrases.json").read_text(encoding="utf-8"))
        self.quantity_vectors = np.load(artifacts / "index" / "quantity_vectors.npy")

    @observe(name="retrieve-context", as_type="retriever")
    def search(self, question: str, *, query: str | None = None) -> list[dict]:
        """재작성 질문 query(없으면 원본)로 기관을 고르고 검색한다. 비교 질문은 기관별 결과를 번갈아 섞는다.
        후속 질문의 '그 사업'은 재작성 때 사업명으로 풀리므로 기관도 재작성 질문에서 찾는다.
        요구사항 코드는 양쪽에서 모아 재작성 때 코드가 빠져도 정확 일치를 유지한다."""
        return self.search_with_candidates(question, query=query)[0]

    def search_with_candidates(self, question: str, *, query: str | None = None) -> tuple:
        """기존 검색 결과와 패킹 전 후보의 읽기 전용 스냅샷을 함께 반환한다."""
        query = query or question
        route = self.router.route(query)
        condition = project_condition(query) if not route and not re.match(r"^.*?」 사업에서 ", query) else None
        if condition:
            return self._filter(condition)
        codes = find_codes(question) | find_codes(query)
        groups = [self._rank(query, codes, doc_ids) for doc_ids in (list(route.values()) or [None])]
        ranked = [hit for hit in chain.from_iterable(zip_longest(*groups)) if hit is not None]
        candidates = self._candidate_snapshot(groups, ranked)
        return self._pack([(c["index"], c["score"]) for c in ranked]), candidates

    def _filter(self, condition):
        matched, chosen = choose_values(self.quantity_rows, self.quantity_phrases, self.quantity_vectors,
                                        self.embedder, condition, float(self.rcfg["field_similarity"]))
        excluded = len(set(self.doc_ids) - chosen.keys())
        summary = f"[수량 필터] 조건 일치 {len(matched)}개 문서; 값 미표기·매칭 불가로 제외 {excluded}개 문서."
        share = int(self.rcfg["filter_token_budget"]) // max(1, len(matched))
        hits, ranked = [], []
        for row in matched:
            top, overview = self._filter_excerpt(row, condition.remainder)
            value_index = next(i for i, c in enumerate(self.chunks) if c["chunk_id"] == row["chunk_id"])
            chunk = self.chunks[value_index]
            if top["index"] != value_index:
                source = self.chunks[top["index"]]
                loc = f"p.{source['page']}" if source["page"] else source["section"]
                overview = f"개요 출처: {source['source']} {loc} [chunk_id={source['chunk_id']}]\n" + overview
            original = row["original"]
            if row.get("unit_declaration"):
                original += f" ({row['unit_declaration']['original']})"
            value = f"{row['phrase']}: {original}\n"
            available = share - self.embedder.token_counts([value])[0] - 2
            body = value + self.embedder.truncate(overview, max(0, available))
            hits.append({**chunk, "body": body, "score": round(row["similarity"], 4)})
            ranked.append({**top, "index": value_index, "dense_score": None, "dense_rank": None, "bm25_score": None,
                           "bm25_rank": None, "exact_code_match": False})
        return FilterHits(hits, summary, matched, chosen), self._candidate_snapshot([ranked], ranked)

    def _filter_excerpt(self, row, remainder):
        value_index = next(i for i, c in enumerate(self.chunks) if c["chunk_id"] == row["chunk_id"])
        query = content_query(remainder)
        results = self._rank(query, set(), {row["doc_id"]})
        if query != remainder:
            results.insert(0, {"index": value_index, "score": 0})
            for candidate in results:
                excerpt = introduction(self.chunks[candidate["index"]]["body"])
                if excerpt:
                    return candidate, excerpt
        top = next((c for c in results if substantive(self.chunks[c["index"]]["body"])), None)
        if top:
            return top, self.chunks[top["index"]]["body"]
        return {"index": value_index, "score": 0}, "(관련 내용을 담은 본문을 찾지 못했습니다.)"

    def _candidate_snapshot(self, groups: list, ranked: list) -> tuple:
        for component in ("dense", "bm25"):
            lists = [sorted((c for c in group if c[f"{component}_score"] is not None),
                            key=lambda c: c[f"{component}_rank"]) for group in groups]
            merged = [c for c in chain.from_iterable(zip_longest(*lists)) if c is not None]
            for rank, c in enumerate(merged, 1):
                c[f"{component}_rank"] = rank
        return tuple(MappingProxyType({"chunk_id": self.chunks[c["index"]]["chunk_id"],
                     "doc_id": self.chunks[c["index"]]["doc_id"], "fused_rank": rank,
                     "dense_score": c["dense_score"], "dense_rank": c["dense_rank"],
                     "bm25_score": c["bm25_score"], "bm25_rank": c["bm25_rank"],
                     "exact_code_match": c["exact_code_match"]}) for rank, c in enumerate(ranked, 1))

    def _rank(self, question: str, codes: set[str], doc_ids: set | None) -> list[dict]:
        allowed = np.isin(self.doc_ids, list(doc_ids)) if doc_ids else np.ones(len(self.chunks), dtype=bool)
        w = float(self.rcfg["dense_weight"])
        # 가중치 0 인 쪽은 후보도 내지 않는다 — 내면 점수 0 짜리 무관한 청크가 결과에 섞인다
        dense_raw = self._dense(question, allowed) if w > 0 else {}
        sparse_raw = self._sparse(question, allowed) if w < 1 else {}
        dense, sparse = _minmax(dense_raw), _minmax(sparse_raw)
        fused = {i: w * dense.get(i, 0.0) + (1 - w) * sparse.get(i, 0.0) for i in dense.keys() | sparse.keys()}
        exact = self._exact(codes, allowed)
        fused |= {i: 0.0 for i in exact - fused.keys()}
        order = sorted(fused, key=lambda i: (i in exact, fused[i]), reverse=True)
        dense_ranks = {i: rank for rank, i in enumerate(dense_raw, 1)}
        sparse_ranks = {i: rank for rank, i in enumerate(sparse_raw, 1)}
        return [{"index": i, "score": fused[i], "dense_score": dense_raw.get(i), "dense_rank": dense_ranks.get(i),
                 "bm25_score": sparse_raw.get(i), "bm25_rank": sparse_ranks.get(i),
                 "exact_code_match": i in exact} for i in order]

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

    def _admit(self, i: int, picked: list[tuple[int, float, set[str]]], room: int) -> tuple[int, set[str]] | None:
        """청크 i 를 담을 수 있으면 (토큰 수, 낱말 집합). 이미 담았거나, 같은 문서의 거의 같은 청크가 있거나,
        room 토큰을 넘으면 None — 단 아무것도 담지 않았으면 넘어도 담는다 (빈 컨텍스트를 막는다)"""
        words = set(self.chunks[i]["body"].split())
        if any(i == j or (self.chunks[i]["doc_id"] == self.chunks[j]["doc_id"] and _is_dup(words, seen))
               for j, _, seen in picked):
            return None
        cost = self.embedder.token_counts([self.chunks[i]["body"]])[0]
        return None if picked and cost > room else (cost, words)

    def _pack(self, ranked: list[tuple[int, float]]) -> list[dict]:
        """본문 토큰 예산 안에서 순서대로 담고 같은 문서의 거의 같은 청크는 제외한다. 긴 청크는 건너뛴다.
        찾은 청크를 담았으면 바로 뒤에 연결 청크(같은 요구사항 · 같은 표)를 우선순위 순서로 _LINK_TOKENS 토큰까지
        고르고 문서 순서대로 담는다 (점수는 찾은 청크와 같게). 연결 한도는 실제로 담은 연결 청크만 쓴다 —
        이미 담았거나 중복이라 빠진 청크가 더 가까운 청크의 자리를 빼앗지 않게."""
        budget = int(self.rcfg["token_budget"])
        picked: list[tuple[int, float, set[str]]] = []
        used = 0
        for i, score in ranked:
            admitted = self._admit(i, picked, budget - used)
            if admitted is None:
                continue
            picked.append((i, score, admitted[1]))
            used += admitted[0]
            start, spent = len(picked), 0
            for j in self.links[i]:
                admitted = self._admit(j, picked, min(budget - used, _LINK_TOKENS - spent))
                if admitted is not None:
                    picked.append((j, score, admitted[1]))
                    used += admitted[0]
                    spent += admitted[0]
            picked[start:] = sorted(picked[start:], key=lambda p: p[0])
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


def _org_names(org: str) -> set[str]:
    """CSV의 전체 기관명과 공백을 제거한 전체 이름만 모은다"""
    name = _LEGAL_FORM.sub("", org.strip())
    return {n for n in {name, re.sub(r"\s+", "", name)} if _is_org_name(n)}


def _csv_org_docs(docs: list[dict], csv_orgs: dict[str, str]) -> dict[str, set]:
    """전체 파일명을 우선 맞추고, 정규화·앞부분 일치는 기관이 하나일 때만 쓴다"""
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
            for name in _org_names(next(iter(orgs))):
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
