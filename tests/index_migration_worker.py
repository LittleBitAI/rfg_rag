import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

os.environ.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", LANGFUSE_TRACING_ENABLED="false",
                  LANGFUSE_PUBLIC_KEY="", LANGFUSE_SECRET_KEY="", OPENAI_API_KEY="offline-no-calls")
code, test_root, operation, folder = sys.argv[1:]
sys.path[:0] = [code, test_root]

from rag.config import write_jsonl
from rag.retrieval import indexing, retrieval
from test_indexing import LocalEmbedder


def exercise(artifacts, operation):
    cfg = {"embedding": {"max_seq_length": 2048}, "bm25": {"k1": 1.2, "b": .75},
           "retrieval": {"dense_weight": 0, "candidate_k": 10, "token_budget": 1000, "rerank": {"enabled": False}},
           "paths": {"org_csv": "unused.csv"}}
    texts = ["개인정보처리시스템", "네트워크 보안", "계약 기간"]
    rows = [dict(chunk_id=str(i), doc_id=str(i), text=t, body=t, source=f"{i}.pdf",
                 page=1, section="", title=str(i)) for i, t in enumerate(texts)]
    embedder = LocalEmbedder()
    with patch.object(indexing, "Embedder", return_value=embedder), \
            patch.object(retrieval, "Embedder", return_value=embedder), \
            patch.object(retrieval, "read_csv_orgs", return_value={}):
        if operation in ("build", "fail-build"):
            write_jsonl(rows, artifacts / "chunks.jsonl")
            write_jsonl([], artifacts / "docs.jsonl")
            if operation == "fail-build":
                embedder.encode = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("injected rebuild failure"))
            indexing.build_index(rows, cfg, artifacts / "index")
        index = retrieval.HybridIndex(artifacts, cfg)
        result = {"loaded_source": str(Path(indexing.__file__).resolve()),
                  "corpus_size": index.bm25.corpus_size,
                  "score_length": len(index.bm25.get_scores(index.tokenizer(texts[0]))),
                  "query_tokens": index.tokenizer(texts[0])}
        try:
            result["bm25_hits"] = [h["chunk_id"] for h in index.search(texts[0])]
            index.rcfg["dense_weight"] = .6
            result["hybrid_hits"] = [h["chunk_id"] for h in index.search(texts[0])]
        except ValueError as exc:
            result["search_error"] = str(exc)
        return result


with patch("socket.socket.connect", side_effect=AssertionError("Migration test must stay offline")):
    print("RESULT " + json.dumps(exercise(Path(folder), operation), ensure_ascii=True), flush=True)
