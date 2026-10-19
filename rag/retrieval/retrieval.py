"""② 검색 — BM25(Kiwi) × Dense(FAISS) 하이브리드 + 요구사항 코드 정확 일치 + 발주기관 라우팅.
담당: 검색. 색인과 01 전처리의 chunks.jsonl · docs.jsonl, paths.org_csv의 기관 목록을 읽는다."""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections import defaultdict
from functools import cached_property
from hashlib import sha256
from itertools import chain, zip_longest
from pathlib import Path
from types import MappingProxyType

import faiss
import numpy as np
from langfuse import observe
from rank_bm25 import BM25Okapi

from ..config import ROOT, read_jsonl
from .indexing import Embedder, KiwiTokenizer, Reranker, find_codes, search_texts, texts_digest
from .quantity_filter import choose_values, content_query, introduction, project_condition, substantive


_DUP_RATIO = 0.8
_TABLE_LINK_MAX = 6  # 한 표가 이 개수 이하 청크로 나뉘었을 때만 같은 표 청크를 함께 담는다 (요구사항 목록표처럼 긴 표는 제외)
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


_NUMBER = re.compile(r"\d+(?:[.,]\d+)*\s*(?:%|시간|개월|MB|GB|KB|TB|[초분일월년명건회개원부식인장])?")
_NEGATION = re.compile(r"않|아니|없|불가|금지|미적용|불포함|제외")


def _evidence_key(body: str) -> tuple[set[str], frozenset[str], frozenset[str]]:
    """중복 판정에 쓰는 (낱말들, 단위를 붙인 숫자들, 부정어가 든 낱말들)"""
    words = set(body.split())
    numbers = frozenset(re.sub(r"[,\s]", "", n) for n in _NUMBER.findall(body))
    return words, numbers, frozenset(w for w in words if _NEGATION.search(w))


def _is_dup(a: tuple, b: tuple) -> bool:
    """숫자 · 부정어가 모두 같고 큰 낱말 집합의 80%가 겹쳐야 중복이다. 짧은 코드만 겹치는 상세 근거는 남긴다.
    '2초/5초', '포함한다/포함하지 않는다' 처럼 낱말은 거의 같아도 뜻이 다른 근거는 둘 다 남긴다."""
    (words_a, numbers_a, negations_a), (words_b, numbers_b, negations_b) = a, b
    return (numbers_a == numbers_b and negations_a == negations_b
            and len(words_a & words_b) >= _DUP_RATIO * max(len(words_a), len(words_b)))


def _org_query(query: str, route: dict[str, set], org: str) -> str:
    """비교 질문에서 이 기관을 찾을 질문 — 다른 기관 이름을 뺀다 (한 질문에 두 기관이 섞여 검색이 흐려지지 않게)"""
    for other in route:
        if other != org:
            for name in other.split(" · "):
                query = query.replace(name, " ")
    return re.sub(r"\s+", " ", query).strip()


def _interleave(lists: list[list[dict]]) -> list[dict]:
    """기관별 결과를 하나씩 번갈아 섞는다. 두 기관이 같은 문서를 가리켜 겹친 청크는 한 번만"""
    seen, out = set(), []
    for hit in chain.from_iterable(zip_longest(*lists)):
        if hit is not None and hit["chunk_id"] not in seen:
            seen.add(hit["chunk_id"])
            out.append(hit)
    return out


def _minmax(d: dict[int, float]) -> dict[int, float]:
    if not d:
        return {}
    lo, hi = min(d.values()), max(d.values())
    if hi - lo < 1e-12:
        return {k: 1.0 for k in d}
    return {k: (v - lo) / (hi - lo) for k, v in d.items()}


def _link_index(chunks: list[dict]) -> tuple[dict[str, set[int]], list[list[int]]]:
    """(요구사항 코드 → 청크들, 청크마다 함께 담을 연결 청크들 — 문서 순서).
    전처리 패키지의 연결 정보를 쓴다.
    - 요구사항 소속(requirement_key · requirement_ids): 요구사항 ID 와 상세 내용이 다른 청크로 나뉘어 상세 청크 본문에
      ID 가 없어도 그 ID 로 정확 일치하고, 같은 요구사항의 다른 청크(ID · 명칭 / 상세 내용)를 연결 청크로 둔다.
    - 표 연결(table_refs): 한 표가 여러 청크로 나뉘었으면 같은 표의 다른 청크를 연결 청크로 둔다.
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
            groups[("table", table)].append(i)
    links: list[set[int]] = [set() for _ in chunks]
    for group, members in groups.items():
        if group[0] == "requirement" or len(members) <= _TABLE_LINK_MAX:
            for i in members:
                links[i].update(members)
    return code_chunks, [sorted(linked - {i}) for i, linked in enumerate(links)]


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
    찾은 청크에 연결 청크(같은 요구사항의 ID · 명칭 / 상세 내용, 같은 표의 나뉜 부분)가 있으면 바로 뒤에 함께 담는다.
    retrieval.rerank.enabled 이면 상위 후보를 로컬 크로스 인코더(Reranker)로 다시 정렬한다."""

    reranker: Reranker | None = None

    def __init__(self, artifacts: Path, cfg: dict):
        self.tokenizer = KiwiTokenizer()
        stored = json.loads((artifacts / "index" / "bm25_tokens.json").read_text(encoding="utf-8"))
        if not isinstance(stored, dict) or stored.get("tokenizer") != self.tokenizer.fingerprint:
            raise ValueError("BM25 tokenizer mismatch or missing fingerprint. "
                             "Rebuild the index with 02_retrieval.ipynb's build_index cell before searching.")
        self.chunks = read_jsonl(artifacts / "chunks.jsonl")
        self.texts = search_texts(self.chunks)
        _check_index(artifacts / "index", self.texts)
        self.doc_ids = np.array([c["doc_id"] for c in self.chunks])
        self.code_chunks, self.links = _link_index(self.chunks)
        self.faiss = faiss.read_index(str(artifacts / "index" / "faiss.index"))
        self.bm25 = BM25Okapi(stored["tokens"], k1=float(cfg["bm25"]["k1"]), b=float(cfg["bm25"]["b"]))
        self.embedder = Embedder(cfg["embedding"])
        self.router = DocRouter(read_jsonl(artifacts / "docs.jsonl"), read_csv_orgs(ROOT / cfg["paths"]["org_csv"]))
        self.rcfg = cfg["retrieval"]
        if self.rcfg["rerank"]["enabled"]:
            self.reranker = Reranker(self.rcfg["rerank"])
        self.chunk_file = str((artifacts / "chunks.jsonl").resolve())
        self.quantity_rows = read_jsonl(artifacts / "index" / "quantities.jsonl")
        self.quantity_phrases = json.loads((artifacts / "index" / "quantity_phrases.json").read_text(encoding="utf-8"))
        self.quantity_vectors = np.load(artifacts / "index" / "quantity_vectors.npy")
        self.settings = {name: cfg[name] for name in ("embedding", "bm25", "retrieval")}

    @cached_property
    def fingerprint(self) -> str:
        """검색 결과를 바꾸는 입력(청크 · 기관 라우팅 · 검색 설정)의 해시.
        04 답변 체크포인트가 이 값으로 갈려, 01 · 02 를 다시 돌리거나 검색 설정을 바꾸면 예전 답을 쓰지 않는다."""
        routes = {org: sorted(doc_ids) for org, doc_ids in self.router.org_docs.items()}
        key = json.dumps({"chunks": self.chunks, "routes": routes, "settings": self.settings},
                         ensure_ascii=False, sort_keys=True)
        return sha256(key.encode("utf-8")).hexdigest()

    @observe(name="retrieve-context", as_type="retriever")
    def search(self, question: str, *, query: str | None = None) -> list[dict]:
        """재작성 질문 query(없으면 원본)로 기관을 고르고 검색한다.
        후속 질문의 '그 사업'은 재작성 때 사업명으로 풀리므로 기관 · 사업명도 재작성 질문에서 찾는다.
        비교 질문(기관 둘 이상)은 기관마다 다른 기관 이름을 뺀 질문으로 따로 찾고, 토큰 예산도 기관마다 따로 써서
        번갈아 섞는다 — 한 기관이 예산을 다 차지하지 않게. 요구사항 코드는 원본 · 재작성 양쪽에서 모은다."""
        return self.search_with_candidates(question, query=query)[0]

    def search_with_candidates(self, question: str, *, query: str | None = None) -> tuple:
        """기존 검색 결과와 패킹 전 후보의 읽기 전용 스냅샷을 함께 반환한다."""
        query = query or question
        route = self.router.route(query)
        condition = project_condition(query) if not route and not re.match(r"^.*?」 사업에서 ", query) else None
        if condition:
            return self._filter(condition)
        codes = find_codes(question) | find_codes(query)
        groups = [self._rank(self.router.focus(_org_query(query, route, org), org, doc_ids), codes, doc_ids,
                             self.router.prefer(query, doc_ids)) for org, doc_ids in route.items()]
        groups = groups or [self._rank(query, codes, None)]
        ranked = [hit for hit in chain.from_iterable(zip_longest(*groups)) if hit is not None]
        candidates = self._candidate_snapshot(groups, ranked)
        packed = [self._pack([(c["index"], c["score"]) for c in group]) for group in groups]
        return _interleave(packed), candidates

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

    def _rank(self, question: str, codes: set[str], doc_ids: set | None, preferred: set = frozenset()) -> list[dict]:
        """preferred 문서(질문에 사업명이 나온 문서)의 후보를 먼저, 같은 기관의 다른 사업 문서는 그 뒤에 둔다"""
        allowed = np.isin(self.doc_ids, list(doc_ids)) if doc_ids else np.ones(len(self.chunks), dtype=bool)
        w = float(self.rcfg["dense_weight"])
        # 가중치 0 인 쪽은 후보도 내지 않는다 — 내면 점수 0 짜리 무관한 청크가 결과에 섞인다
        dense_raw = self._dense(question, allowed) if w > 0 else {}
        sparse_raw = self._sparse(question, allowed) if w < 1 else {}
        dense, sparse = _minmax(dense_raw), _minmax(sparse_raw)
        fused = {i: w * dense.get(i, 0.0) + (1 - w) * sparse.get(i, 0.0) for i in dense.keys() | sparse.keys()}
        exact = self._exact(codes, allowed)
        fused |= {i: 0.0 for i in exact - fused.keys()}
        order = sorted(fused, key=lambda i: (self.doc_ids[i] in preferred, i in exact, fused[i]), reverse=True)
        if self.reranker and order:
            order, fused = self._rerank(question, order, exact, preferred)
        dense_ranks = {i: rank for rank, i in enumerate(dense_raw, 1)}
        sparse_ranks = {i: rank for rank, i in enumerate(sparse_raw, 1)}
        return [{"index": i, "score": fused[i], "dense_score": dense_raw.get(i), "dense_rank": dense_ranks.get(i),
                 "bm25_score": sparse_raw.get(i), "bm25_rank": sparse_ranks.get(i),
                 "exact_code_match": i in exact} for i in order]

    def _rerank(self, question: str, order: list[int], exact: set[int], preferred: set) -> tuple[list[int], dict]:
        """하이브리드 상위 rerank.top_n 후보만 리랭커 점수로 다시 정렬한다. 사업명 문서와 요구사항 코드 일치 청크는 계속
        앞에 둔다. 후보 수십 개면 토큰 예산(수천 토큰)을 넘으므로 나머지 후보는 버린다."""
        top = order[: int(self.rcfg["rerank"]["top_n"])]
        scores = dict(zip(top, self.reranker.scores(question, [self.texts[i] for i in top])))
        return sorted(top, key=lambda i: (self.doc_ids[i] in preferred, i in exact, scores[i]), reverse=True), scores

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

    def _with_links(self, ranked: list[tuple[int, float]]):
        """각 청크 바로 뒤에 연결 청크를 문서 순서대로 붙인다 (점수는 찾은 청크와 같게).
        찾은 청크 하나에 붙이는 연결 청크는 _LINK_TOKENS 토큰까지 — 넘치는 연결 청크는 건너뛴다"""
        for i, score in ranked:
            yield i, score
            spent = 0
            for j in self.links[i]:
                cost = self.embedder.token_counts([self.chunks[j]["body"]])[0]
                if spent + cost <= _LINK_TOKENS:
                    spent += cost
                    yield j, score

    def _pack(self, ranked: list[tuple[int, float]]) -> list[dict]:
        """본문 토큰 예산 안에서 순서대로 담고 같은 문서의 거의 같은 청크는 제외한다.
        연결 청크(같은 요구사항 · 같은 표)는 함께 담는다. 긴 청크는 건너뛰되 첫 청크는 예산을 넘어도 담아 빈 컨텍스트를 막는다."""
        budget = int(self.rcfg["token_budget"])
        picked: list[tuple[int, float, tuple]] = []
        used = 0
        for i, score in self._with_links(ranked):
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


_TITLE_WORD = re.compile(r"[가-힣A-Za-z0-9]{2,}")
_TITLE_MAX_DOCS = 2  # 이보다 많은 사업 제목에 나오는 낱말('시스템' · '구축' · '고도화' · '2024년')은 사업을 가르지 못한다
_PREFER_MIN_CHARS = 4  # 질문에 나온 사업명 고유 낱말이 이 글자 수 이상일 때만 그 문서를 앞세운다
_FOCUS_MIN_WORDS = 2  # 기관명 · 사업명 낱말을 뺀 질문에 이보다 적은 낱말이 남으면 빼지 않는다


def _title_keys(titles: dict[str, str]) -> dict[str, set[str]]:
    """문서별 사업명 고유 낱말 — 파일명 '발주기관_사업명' 의 사업명 낱말 중 다른 사업 제목에 거의 안 나오는 것"""
    words = {did: set(_TITLE_WORD.findall(title.split("_", 1)[-1])) for did, title in titles.items()}
    df = defaultdict(int)
    for ws in words.values():
        for w in ws:
            df[w] += 1
    return {did: {w for w in ws if df[w] <= _TITLE_MAX_DOCS} for did, ws in words.items()}


def _merge_overlaps(route: dict[str, set]) -> dict[str, set]:
    """같은 문서를 가리키는 기관명은 하나로 합친다 ('전북대학교' 와 '공유대학' 이 같은 JST 문서) —
    따로 두면 그 문서가 기관별 검색 · 예산을 두 몫 가져간다. 다른 기관 문서에 모두 들어가는 쪽은 그 기관에 합친다."""
    merged: dict[str, set] = {}
    for org, doc_ids in sorted(route.items(), key=lambda item: -len(item[1])):
        owner = next((name for name, docs in merged.items() if doc_ids <= docs), None)
        if owner:
            merged[f"{owner} · {org}"] = merged.pop(owner)
        else:
            merged[org] = set(doc_ids)
    return merged


def _first_mentions(words: list[str], names: set[str]) -> set[int]:
    """각 이름이 처음 들어 있는 낱말의 위치"""
    used: set[str] = set()
    found = set()
    for i, word in enumerate(words):
        names_in = {name for name in names if name in word}
        if names_in - used:
            found.add(i)
            used |= names_in
    return found


def _is_title_word(word: str, title_words: set[str]) -> bool:
    """사업명 낱말이 들었거나 괄호 · 기호뿐인 낱말"""
    return not _TITLE_WORD.search(word) or any(t in word for t in title_words)


class DocRouter:
    """질문에 나온 발주기관 → 그 기관 문서로 검색 범위를 좁힌다 (RFP 가 많을수록 정확도 ↑).
    기관명은 담당자 CSV와 파일명·표지에서 모으고, 표지가 없으면 본문 앞부분을 쓴다."""

    def __init__(self, docs: list[dict], csv_orgs: dict[str, str]):
        self.titles = {d["doc_id"]: d["title"] for d in docs}
        self.title_keys = _title_keys(self.titles)
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
        return _merge_overlaps({org: self.org_docs[org] for org in found})

    def focus(self, query: str, org: str, doc_ids: set) -> str:
        """기관 문서 안에서 순위를 매길 질문 — 질문에서 기관 · 사업을 가리킨 부분('스포츠윤리센터의 「… LMS 기능개선」')을 뺀다.
        검색 범위를 이미 그 기관 문서로 좁혔으니 이 부분은 청크를 가르지 못하고, 사업명을 되풀이하는 표지 · 서식 ·
        서약서 청크만 앞세워 정작 묻는 내용('하자보증 기간')의 청크를 토큰 예산 밖으로 밀어낸다.
        기관명 · 사업명 고유 낱말은 처음 나올 때만 빼고(본문에서 다시 묻는 'ERP 행' 은 남김), 그 옆에 붙은 사업명 낱말도 함께 뺀다.
        남는 낱말이 너무 적으면(사업명 자체를 묻는 질문) 그대로 둔다."""
        words = query.split()
        title_words = {w for did in doc_ids for w in _TITLE_WORD.findall(self.titles[did].split("_", 1)[-1])}
        drop = _first_mentions(words, {*org.split(" · "), *(w for did in doc_ids for w in self.title_keys.get(did, ()))})
        for i in sorted(drop):
            for step in (-1, 1):
                j = i + step
                while 0 <= j < len(words) and j not in drop and _is_title_word(words[j], title_words):
                    drop.add(j)
                    j += step
        focused = " ".join(w for i, w in enumerate(words) if i not in drop)
        return focused if len(_TITLE_WORD.findall(focused)) >= _FOCUS_MIN_WORDS else query

    def prefer(self, question: str, doc_ids: set) -> set:
        """기관 문서가 여럿이면 질문에 사업명 고유 낱말이 가장 많이(글자 수 기준) 나온 문서 → 그 문서 후보를 앞세운다.
        빼지 않고 뒤로 미루기만 한다 — 질문의 '대용량 전송' 이 다른 사업 제목('대용량 자료전송시스템')과 겹쳐
        정답 문서를 빼던 문제가 있었다. 고유 낱말이 긴 쪽('기록관리시스템' 7자 > '대용량' 3자)이 이기고,
        동점이거나 사업명이 없으면 빈 집합(앞세울 문서 없음)."""
        compact = re.sub(r"\s+", "", question)
        scores = {did: sum(len(w) for w in self.title_keys.get(did, ()) if w in compact) for did in doc_ids}
        best = max(scores.values(), default=0)
        preferred = {did for did, score in scores.items() if score == best}
        return set() if best < _PREFER_MIN_CHARS or preferred == set(doc_ids) else preferred
