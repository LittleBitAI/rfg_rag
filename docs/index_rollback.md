# Rolling back a tokenizer index

Rolling back code alone is unsupported after a tokenizer rebuild. The old reader cannot interpret
the new `{tokenizer, tokens}` payload, and extracting its `tokens` array would still pair the
wrong corpus and query segmentation. Downgrade the code, dependency environment and complete
index together, while every reader is stopped.

The supported procedure rebuilds derived state with the exact rollback revision, verifies it
in isolation and publishes the complete directory with one rename. It uses the existing builder;
there is no fallback reader, new configuration or automatic tokenizer conversion.

## Prerequisites and ordering

1. Stop the question server and close the 02, 04 and 05 notebook kernels. Keep them stopped until
   publication succeeds. Keep this procedure available before switching revisions.
2. Record the intended code revision, environment, configuration and matching `chunks.jsonl`,
   `docs.jsonl` and organization CSV. Freeze those inputs during the migration. The regression
   target is pre-tokenizer `dev`, commit `2f746f38dba1d5fdbdfc924fbce3eac3297081b7`.
   Select that exact revision and its compatible dependency environment without starting readers.
   Required embedding weights must already be cached. This is a local rebuild; do not run rewrite,
   generation or judge cells.
3. From a fresh Python process in that checkout, quarantine the entire active index. Both destination
   names below must be unused. Never overwrite a previous rollback bundle.

   ```python
   from rag.config import ARTIFACTS

   root = ARTIFACTS.resolve()
   active = root / "index"
   previous = root / "index.before-downgrade"
   staging = root / "downgrade-staging"
   assert all(path.resolve().parent == root for path in (active, previous, staging))
   assert not previous.exists() and not staging.exists()
   active.rename(previous)
   ```

   The active `index` path is now absent. A base reader accidentally started during rebuilding
   fails to load FAISS instead of serving a mixed generation. The quarantined directory remains
   usable only with its matching newer code, environment and inputs.

## Build and verify before publication

4. In the rollback checkout and environment, build the whole index in an isolated artifacts tree.

   ```python
   from shutil import copy2
   from rag.config import ARTIFACTS, load_config, read_jsonl
   from rag.retrieval.indexing import build_index

   staging = ARTIFACTS / "downgrade-staging"
   staging.mkdir()
   for name in ("chunks.jsonl", "docs.jsonl"):
       copy2(ARTIFACTS / name, staging / name)
   build_index(read_jsonl(staging / "chunks.jsonl"), load_config(), staging / "index")
   ```

   If construction fails, leave the active path absent and all readers stopped. To retry, use a
   fresh staging directory or explicitly remove only the failed staging tree after inspecting it;
   do not publish its contents. The regression injects a build failure and confirms a fresh base
   loader still cannot start against the active path.
5. Start a separate fresh Python process with the same rollback revision and environment.
   Verify the staged index before making it active.

   ```python
   from rag.config import ARTIFACTS, load_config
   from rag.retrieval.retrieval import HybridIndex

   cfg = load_config()
   index = HybridIndex(ARTIFACTS / "downgrade-staging", cfg)
   query = "개인정보처리시스템"
   assert index.bm25.corpus_size == len(index.chunks)
   assert len(index.bm25.get_scores(index.tokenizer(query))) == len(index.chunks)
   index.rcfg["fusion"] = "minmax"  # dense_weight 0 = BM25만은 minmax 에서만 뜻이 있다
   for weight in (0, cfg["retrieval"]["dense_weight"]):
       index.rcfg["dense_weight"] = weight
       hits = index.search(query)
       assert hits
       print(weight, [row["chunk_id"] for row in hits])
   print("PASS: staged rollback search")
   ```

   Use known queries present in the intended corpus and compare the printed IDs with recorded
   results from that rollback revision. The three-document regression asserts exact original
   tokens, BM25-only results and normal hybrid results, rather than just successful construction.
   Any verification failure leaves the active path absent; do not proceed to publication.

## Publish and restart

6. Only after the fresh verification process succeeds, publish the verified directory on the
   same filesystem. With readers still stopped, the destination must remain absent.

   ```python
   from rag.config import ARTIFACTS

   active = ARTIFACTS / "index"
   staged = ARTIFACTS / "downgrade-staging" / "index"
   assert not active.exists()
   staged.rename(active)
   ```

   All five coupled files move together: `faiss.index`, `bm25_tokens.json`, `quantities.jsonl`,
   `quantity_phrases.json` and `quantity_vectors.npy`. Never replace just the BM25 file or attach a
   fingerprint to old tokens. Keep `index.before-downgrade` until recovery is accepted. If build,
   verification or publication fails, do not restart the old application against that newer bundle.
7. Start a fresh rollback application/kernel and repeat the same ordinary BM25-enabled search.
   If abandoning the downgrade, stop readers again and restore the newer code/environment and
   its matching whole index bundle together.

This is a stopped-reader migration with a single directory publication rename, not a live code
switch or a crash-recovery guarantee. Restarting after a crash requires inspecting which complete
bundle exists and matching it to the selected revision before starting readers.

## Regression evidence

Run `.venv\Scripts\python -m pytest -q tests/test_index_migration.py tests/test_indexing.py`.
The migration test uses the actual frozen base code from Git and current candidate code in fresh
processes. A normal full clone must contain the base commit; shallow checkouts need that history
before running it. Network connections are blocked and embeddings are local test substitutes.
The test covers base build/search, forward rejection without mutation, candidate rebuild/search,
the old-reader shape-failure negative control, failed downgrade blocking, isolated base rebuild,
fresh verification, whole-directory publication and a fresh base search after publication.
