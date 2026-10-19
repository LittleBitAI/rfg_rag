"""운영 코드를 수정하지 않고 순위와 패킹을 재사용하는 실험 경로."""
from __future__ import annotations

import json

import faiss
import numpy as np
from rank_bm25 import BM25Okapi

from rag.config import read_jsonl
from rag.retrieval.indexing import KiwiTokenizer
from rag.retrieval.retrieval import DocRouter, HybridIndex, _link_index, read_csv_orgs

from .common import OUT


class BenchmarkIndex(HybridIndex):
    def __init__(self, embedder, cfg, folder):
        self.embedder = embedder
        self.cfg = cfg
        self.rcfg = dict(cfg["retrieval"])
        self.chunks = read_jsonl(OUT / "input/chunks.jsonl")
        self.chunk_file = str((OUT / "input/chunks.jsonl").resolve())
        self.doc_ids = np.array([c["doc_id"] for c in self.chunks])
        self.code_chunks, self.links = _link_index(self.chunks)
        self.faiss = faiss.read_index(str(folder / "faiss.index"))
        self.kiwi = KiwiTokenizer()
        tokens = json.loads((OUT / "kiwi_tokens.json").read_text(encoding="utf-8"))
        assert tokens["tokenizer"] == self.kiwi.fingerprint
        self.sparse_indexes = {"kiwi": BM25Okapi(tokens["tokens"], k1=1.5, b=0.75),
                               "whitespace": BM25Okapi([c["text"].split() for c in self.chunks], k1=1.5, b=0.75)}
        self.router = DocRouter(read_jsonl(OUT / "input/docs.jsonl"), read_csv_orgs(OUT / "input/orgs.csv"))
        self.quantity_rows = read_jsonl(folder / "quantities.jsonl")
        self.quantity_phrases = json.loads((folder / "quantity_phrases.json").read_text(encoding="utf-8"))
        self.quantity_vectors = np.load(folder / "quantity_vectors.npy")
        self.configure("kiwi", 0.6, "integrated")

    def configure(self, sparse, weight, mode):
        self.rcfg["dense_weight"] = weight
        self.bm25 = self.sparse_indexes[sparse]
        self.tokenizer = self.kiwi if sparse == "kiwi" else str.split
        self.mode = mode

    def search_with_candidates(self, question, *, query=None):
        if self.mode == "integrated":
            return super().search_with_candidates(question, query=query)
        from itertools import chain, zip_longest

        query = query or question
        route = self.router.route(query)
        groups = [self._rank(query, set(), doc_ids) for doc_ids in (list(route.values()) or [None])]
        ranked = [hit for hit in chain.from_iterable(zip_longest(*groups)) if hit is not None]
        candidates = self._candidate_snapshot(groups, ranked)
        return self._pack([(c["index"], c["score"]) for c in ranked]), candidates

    def _exact(self, codes, allowed):
        return super()._exact(codes, allowed) if self.mode == "integrated" else set()
