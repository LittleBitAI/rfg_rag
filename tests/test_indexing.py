import json
from pathlib import Path
from unittest.mock import MagicMock

import faiss
import numpy as np
import pytest

from rag.config import read_jsonl, write_jsonl
from rag.retrieval import indexing, retrieval


class LocalEmbedder:
    def encode(self, texts, progress=False):
        return np.ones((len(texts), 2), dtype=np.float32)

    def embed_query(self, text):
        return [1, 1]

    def token_counts(self, texts):
        return [len(text) for text in texts]

    def truncate(self, text, budget):
        return text[:budget]


def chunks(count):
    return [{"chunk_id": str(i), "doc_id": str(i), "text": "사업예산: 2억원", "body": "사업예산: 2억원",
             "source": str(i) + ".pdf", "page": 1, "section": "", "title": str(i)} for i in range(count)]


def snapshot(directory):
    return {p.name: p.read_bytes() for p in directory.iterdir()}


@pytest.fixture
def setup_index(monkeypatch, tmp_path):
    embedder = LocalEmbedder()
    monkeypatch.setattr(indexing, "Embedder", lambda cfg: embedder)
    monkeypatch.setattr(retrieval, "Embedder", lambda cfg: embedder)
    monkeypatch.setattr(retrieval, "read_csv_orgs", lambda path: {})
    cfg = {"embedding": {"max_seq_length": 2048}, "bm25": {"k1": 1.2, "b": .75},
           "retrieval": {"field_similarity": .8, "filter_token_budget": 1000, "fusion": "minmax", "dense_weight": .5,
                         "candidate_k": 10, "token_budget": 1000, "rerank": {"enabled": False}},
           "paths": {"org_csv": "unused.csv"}}
    write_jsonl(chunks(1), tmp_path / "chunks.jsonl")
    write_jsonl([], tmp_path / "docs.jsonl")
    directory = tmp_path / "index"
    indexing.build_index(chunks(1), cfg, directory)
    return directory, embedder, cfg


@pytest.mark.parametrize("stage", ["quantity_embedding", "quantity_write", "summary", "publication"])
def test_failed_rebuild_preserves_complete_previous_index(setup_index, monkeypatch, stage):
    directory, embedder, cfg = setup_index
    before = snapshot(directory)
    if stage == "quantity_embedding":
        monkeypatch.setattr(embedder, "encode", MagicMock(side_effect=[np.zeros((2, 2), dtype=np.float32),
                                                                     RuntimeError("failed quantity embedding")]))
    elif stage == "quantity_write":
        monkeypatch.setattr(indexing.np, "save", MagicMock(side_effect=RuntimeError("failed quantity write")))
    elif stage == "summary":
        monkeypatch.setattr(embedder, "token_counts", MagicMock(side_effect=RuntimeError("failed summary")))
    else:
        rename = Path.rename

        def fail_publication(path, target):
            if path.name == "next":
                raise RuntimeError("failed publication")
            return rename(path, target)

        monkeypatch.setattr(Path, "rename", fail_publication)
    with pytest.raises(RuntimeError, match="failed"):
        indexing.build_index(chunks(2), cfg, directory)
    assert snapshot(directory) == before
    assert sorted(p.name for p in directory.parent.iterdir()) == ["chunks.jsonl", "docs.jsonl", "index"]
    monkeypatch.setattr(embedder, "encode", LocalEmbedder().encode)
    monkeypatch.setattr(embedder, "token_counts", LocalEmbedder().token_counts)
    loaded = retrieval.HybridIndex(directory.parent, cfg)
    hits, _ = loaded.search_with_candidates("예산 1억원 이상인 사업")
    assert [row["chunk_id"] for row in hits.values] == ["0"]


def test_successful_rebuild_replaces_core_and_quantity_artifacts_together(setup_index):
    directory, _, cfg = setup_index
    result = indexing.build_index(chunks(2), cfg, directory)
    assert result["청크"] == 2
    assert faiss.read_index(str(directory / "faiss.index")).ntotal == 2
    stored = json.loads((directory / "bm25_tokens.json").read_text(encoding="utf-8"))
    assert len(stored["tokens"]) == 2
    rows = read_jsonl(directory / "quantities.jsonl")
    phrases = json.loads((directory / "quantity_phrases.json").read_text(encoding="utf-8"))
    assert {row["chunk_id"] for row in rows} == {"0", "1"}
    assert {row["phrase"] for row in rows} == set(phrases)
    assert len(np.load(directory / "quantity_vectors.npy")) == len(phrases)
    write_jsonl(chunks(2), directory.parent / "chunks.jsonl")
    loaded = retrieval.HybridIndex(directory.parent, cfg)
    hits, _ = loaded.search_with_candidates("예산 1억원 이상인 사업")
    assert {row["chunk_id"] for row in hits.values} == {"0", "1"}


def test_failed_first_build_leaves_no_published_index(setup_index, monkeypatch):
    directory, embedder, cfg = setup_index
    destination = directory.parent / "first"
    monkeypatch.setattr(embedder, "encode", MagicMock(side_effect=[np.zeros((2, 2), dtype=np.float32),
                                                                 RuntimeError("failed quantity embedding")]))
    with pytest.raises(RuntimeError, match="failed quantity embedding"):
        indexing.build_index(chunks(2), cfg, destination)
    assert not destination.exists()
    assert sorted(p.name for p in directory.parent.iterdir()) == ["chunks.jsonl", "docs.jsonl", "index"]


@pytest.mark.parametrize("change", ["source", "dictionary", "kiwipiepy", "kiwipiepy_model", "hanja"])
def test_incompatible_bm25_index_is_rejected_before_loading_dense_model(setup_index, monkeypatch, change):
    directory, _, cfg = setup_index
    if change == "dictionary":
        read = Path.read_bytes

        def changed_dictionary(path):
            data = read(path)
            return json.dumps(json.loads(data) + ["회귀검사용어"]).encode("utf-8") if path.name == "kiwi_user_words.json" else data

        monkeypatch.setattr(Path, "read_bytes", changed_dictionary)
    elif change == "source":
        read = Path.read_text

        def changed_source(path, **kwargs):
            data = read(path, **kwargs)
            return data + "\n" if path == Path(indexing.__file__) else data

        monkeypatch.setattr(Path, "read_text", changed_source)
    else:
        version = indexing.version
        monkeypatch.setattr(indexing, "version", lambda name: "new-version" if name == change else version(name))
    before = snapshot(directory)
    dense = MagicMock(side_effect=AssertionError("must reject before loading dense model"))
    monkeypatch.setattr(retrieval, "Embedder", dense)
    with pytest.raises(ValueError, match=r"BM25 tokenizer.*Rebuild.*02_retrieval.ipynb"):
        retrieval.HybridIndex(directory.parent, cfg)
    dense.assert_not_called()
    assert snapshot(directory) == before
