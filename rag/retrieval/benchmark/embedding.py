"""발행자의 프롬프트·풀링·출력 규약으로 로컬 추론한다."""
from __future__ import annotations

import time

import numpy as np
import torch
from huggingface_hub import snapshot_download
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer

from .common import MODEL_IGNORE_PATTERNS, models


def snapshot(spec):
    return snapshot_download(spec["id"], revision=spec["revision"], local_files_only=True,
                             ignore_patterns=MODEL_IGNORE_PATTERNS)


def cosine_vectors(raw):
    vectors = np.asarray(raw, dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    assert np.isfinite(vectors).all() and (norms > 0).all()
    return np.ascontiguousarray(vectors / norms)


class LocalEmbedder:
    def __init__(self, spec):
        assert torch.cuda.is_available() and "RTX 3080" in torch.cuda.get_device_name()
        self.spec = spec
        start = time.perf_counter()
        self.model = SentenceTransformer(snapshot(spec), device="cuda", trust_remote_code=True,
                                         local_files_only=True, model_kwargs={
                                             "dtype": getattr(torch, spec["dtype"]), "attn_implementation": "sdpa"})
        self.model.max_seq_length = spec["max_length"]
        self.model.eval()
        assert {p.device.type for p in self.model.parameters()} == {"cuda"}
        self.budget_tokenizer = AutoTokenizer.from_pretrained(snapshot(models()[0]), local_files_only=True)
        torch.cuda.synchronize()
        self.load_seconds = time.perf_counter() - start
        self.raw_dtypes = set()

    def encode(self, texts, *, query=False, progress=False):
        kwargs = {"task": self.spec["task"]} if self.spec.get("task") else {}
        prompt = self.spec["query_prompt" if query else "document_prompt"]
        if prompt is not None:
            kwargs["prompt_name"] = prompt
        raw = self.model.encode(texts, batch_size=1 if query else self.spec["batch_size"],
                                convert_to_numpy=True, show_progress_bar=progress,
                                normalize_embeddings=False, **kwargs)
        self.raw_dtypes.add(str(raw.dtype))
        assert raw.shape == (len(texts), self.spec["dimensions"])
        return cosine_vectors(raw)

    def embed_query(self, text):
        return self.encode([text], query=True)[0].tolist()

    def token_counts(self, texts):
        return [len(ids) for ids in self.budget_tokenizer(texts, verbose=False)["input_ids"]]

    def truncate(self, text, budget):
        ids = self.budget_tokenizer.encode(text, add_special_tokens=False)
        return self.budget_tokenizer.decode(ids[:max(0, budget)], skip_special_tokens=True)

    def truncation_report(self, texts, query=False):
        name = self.spec["query_prompt" if query else "document_prompt"]
        prompt = self.model.prompts[name] if name else ""
        lengths = [len(ids) for ids in self.model.tokenizer([prompt + text for text in texts],
                                                           verbose=False)["input_ids"]]
        return {"inputs": len(texts), "truncated": sum(n > self.spec["max_length"] for n in lengths),
                "max_tokens_before_truncation": max(lengths, default=0), "prompt": prompt}
