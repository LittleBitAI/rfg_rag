---
scope: project
severity: contract
repeat: rule
triggers: ['색인', '인덱스', '(?i)\bindex', '(?i)indexing\.py', '(?i)build_index', '토크나이저', '(?i)tokenizer', '(?i)kiwi', '사전', '(?i)chunks\.jsonl', '(?i)tokenizer mismatch']
slots: []
sources: ['rag/retrieval/indexing.py#L174', 'rag/retrieval/retrieval.py#L141', 'README.md#L198', 'docs/index_rollback.md']
links: []
---

# After changing indexing.py, the Kiwi dictionary or the chunks, rebuild the index with 02's build_index

Rule. Any edit to `rag/retrieval/indexing.py` (even a comment), to
`rag/retrieval/kiwi_user_words.json`, to the Kiwi or hanja versions, or a
new `artifacts/chunks.jsonl` from 01, makes the saved `artifacts/index/`
stale. Rerun 02's load, settings and `build_index` cells before 04, 05 or
the frontend; it is local and costs no API money. Never edit or copy files
inside `artifacts/index/` by hand, and never weaken the fingerprint or
`texts.sha256` checks to make an old index load. When rolling code back,
roll the index back too (`docs/index_rollback.md`).

Why. The BM25 tokenizer fingerprint hashes the whole `indexing.py` source,
the dictionary and package versions (`rag/retrieval/indexing.py:174-179`),
and `texts.sha256` must match the current search texts
(`rag/retrieval/retrieval.py:141-147`). An index whose vector and BM25 order
no longer matched the chunks would return the wrong chunks, so loading
stops instead. `build_index` builds aside and swaps the folder in atomically.

What goes wrong. `HybridIndex` raises "BM25 tokenizer mismatch" or "검색 색인이
지금 청크와 맞지 않습니다"; the frontend API fails at startup.
