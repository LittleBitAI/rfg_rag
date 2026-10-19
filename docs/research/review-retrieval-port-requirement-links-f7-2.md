# Review research — F7, cycle 2

Draft research before the fix of review round 10 of PR #70, written 2026-10-19. It is not a verified fact or a shared rule: the review reads it with the fix.

## Problem

F7 (PR #70): a found chunk of a long split table must be able to bring related parts of the same table into the context (its header chunk and nearest continuation rows), within a bounded budget. Before the fix, tables with more than 6 chunks got no links at all (_TABLE_LINK_MAX). The fix in 6510eea removed that cut-off and orders links by (not the first chunk, distance, position) under _LINK_TOKENS = 600. The invariant only holds if the chunks it picks actually arrive in the packed context and if real table chunks fit under the cap. Neither has been shown on the real data.

Trigger: repeat, rounds 9, 10.

- [P1] [P1] rag/retrieval/retrieval.py:244 — rejected links consume the link budget before packing, so viable linked evidence is never considered

## Failed fixes

- 6510eea ('retrieval: link long split tables by head and distance') deleted _TABLE_LINK_MAX, added _link_priority (head first, then distance) and made _with_links fill the 600-token cap in that order and yield the picks in document order. It passed a synthetic 9-chunk test at 300 tokens per chunk (['c5','c0','c4']). It did not hold for three reasons. (1) Links are chosen in _with_links, a generator that runs before _pack's checks: already picked (i == j), near-duplicate (_is_dup) and the 2500-token budget. A head chunk already in the context, or dropped as a duplicate, still uses up part of the 600-token cap, so the neighbour it displaced never comes. Links are also yielded even when _pack skips the found chunk itself. (2) Cycle 1's own count put the 21 chunks of the long tables in the v12 package at a median of 670 tokens (p90 790), so for most hits no link fits under 600 in any order. On real data the long tables still lose their links, which is the F7 symptom. (3) That count used the o200k tokenizer, while the cap and the budget are measured with Embedder.token_counts (KURE-v1, an XLM-R SentencePiece tokenizer), so even the size evidence is in the wrong unit.

## Sources

### S1 — rag/retrieval/retrieval.py at 6510eea

- URL: rag/retrieval/retrieval.py
- Retrieved: 2026-10-19
- Locator: lines 25, 81-90, 235-266
- Fragment: _LINK_TOKENS = 600 ... for j in self.links[i]: cost = self.embedder.token_counts([self.chunks[j]["body"]])[0]; if spent + cost <= _LINK_TOKENS: spent += cost; chosen.append(j) / for j in sorted(chosen): yield j, score ... (in _pack) if any(i == j or (... _is_dup(words, seen)) for j, _, seen in picked): continue ... if picked and used + cost > budget: continue
- Applicability: Shows that the link cap is spent in _with_links before _pack's already-picked, duplicate and budget checks, and that links are yielded even if the found chunk is later skipped.
- Counterevidence: When no earlier hit has packed a chunk of the same table and there are no near-duplicates, choosing before packing gives the same result.
- Validation: After the fix, link choice happens inside _pack, after the found chunk is accepted, and skipped links are not charged.

### S2 — tests/test_retrieval.py

- URL: tests/test_retrieval.py
- Retrieved: 2026-10-19
- Locator: lines 308-312, 322-325
- Fragment: index = make_index([f"표 {i}" for i in range(9)], [300] * 9, tables=[["t1"]] * 9) / assert [hit["chunk_id"] for hit in index._pack([(5, 0.9)])] == ["c5", "c0", "c4"]
- Applicability: The only long-table test uses one hit and 300-token chunks, so it checks neither an already-packed head nor chunks larger than the cap.
- Counterevidence: Synthetic sizes are fine for checking the ordering itself.
- Validation: New tests with an already-packed head and a skipped found chunk fail on 6510eea and pass after the fix.

### S3 — Review research — F7, cycle 1 (Result section)

- URL: docs/research/review-retrieval-port-requirement-links-f7-1.md
- Retrieved: 2026-10-19
- Locator: ## Result
- Fragment: 3 of more than 6 (7 chunks each, 21 table chunks, none with a requirement_key). Those 21 chunks have a median of 670 o200k tokens (p90 790), so most of them cannot fit under the 600-token link cap whatever the order. ... Not run: the pipeline-level dev rerun_retrieval and 05 Retrieval comparison.
- Applicability: Measured on the real v12 package: most long-table chunks are above the cap, measured with o200k rather than the embedder's tokenizer.
- Counterevidence: Counts only, from the earlier cycle; the unit differs from the code's, so the real KURE sizes may be lower or higher.
- Validation: Re-measure with Embedder.token_counts on the same 21 chunks.

### S4 — LlamaIndex core — postprocessor/node.py (PrevNextNodePostprocessor)

- URL: https://raw.githubusercontent.com/run-llama/llama_index/main/llama-index-core/llama_index/core/postprocessor/node.py
- Retrieved: 2026-10-19
- Locator: PrevNextNodePostprocessor._postprocess_nodes; get_forward_nodes / get_backward_nodes
- Fragment: all_nodes: Dict[str, NodeWithScore] = {} ... all_nodes[node.node.node_id] = node ... all_nodes.update(...) — neighbours are merged by node id, so a node already present is kept once (its score can be overwritten by the unscored neighbour copy); results are placed before/after a node by prev/next relationship, giving document order. The neighbour count is bounded by num_nodes, not by tokens. (Content as summarised by the fetch tool from the source file.)
- Applicability: Prior art for merging neighbours by identity before counting them and for emitting them in document order, the behaviour _with_links lacks because it runs before _pack's identity check.
- Counterevidence: No token budget in LlamaIndex, so charging the cap after dedup is an extension, not something LlamaIndex documents; the score-overwrite quirk shows its merge is not a model to copy fully.
- Validation: In the fixed _pack, a link already picked is neither added nor charged.

### S5 — KURE v1 onnx int8 (model card, Hugging Face)

- URL: https://huggingface.co/LaraAI-Labs/KURE-v1-onnx-int8
- Retrieved: 2026-10-19
- Locator: model description; spec section
- Fragment: nlpai-lab/KURE-v1 (BGE-M3 한국어 파인튜닝)의 ONNX INT8 변환본 ... XLM-R SentencePiece (sentencepiece.bpe.model 동봉 — xlm-roberta-large/BGE-M3 와 동일, sha256 cfc8146a…). The card does not state a maximum sequence length.
- Applicability: The cap and the budget are counted with KURE-v1's tokenizer (Embedder.token_counts), which is XLM-R SentencePiece, not the o200k tokenizer used in cycle 1.
- Counterevidence: A third-party conversion card, not nlpai-lab's own card; it does not give token counts for Korean.
- Validation: Re-measure the long-table chunk sizes with Embedder.token_counts.

### S6 — config.yaml

- URL: config.yaml
- Retrieved: 2026-10-19
- Locator: lines 40-42, 47, 58
- Fragment: chunk_size: 700 # 글자 단위 / table_size_factor: 2.0 # 표 청크는 chunk_size × 이 배수까지 허용(행 단위 분할, 헤더 반복) / model: nlpai-lab/KURE-v1 / token_budget: 2500 # 검색 결과 본문 토큰 예산 (임베딩 토크나이저 기준)
- Applicability: Table chunks may reach 1400 characters; budget unit is the embedding tokenizer.
- Counterevidence: The v12 package is chunked upstream, so these limits describe 01's own splitter and not necessarily v12's chunks.
- Validation: Measured sizes are compared against the cap in the same unit.

## Claims

- C1 (source; S1): _with_links spends the 600-token link cap before _pack's already-picked, near-duplicate and budget checks, and yields links even when the found chunk is later skipped.
- C2 (interpretation; S1, S2): The fix was checked only with a single hit on 300-token synthetic chunks, which cannot reveal cap waste on already-packed chunks or chunks larger than the cap.
- C3 (source; S3): In the v12 package the long-table chunks have a median of 670 o200k tokens, above the 600 cap, so most long-table hits still attach no link.
- C4 (interpretation; S3, S5, S6): The cap is measured with KURE-v1's XLM-R SentencePiece tokenizer, while the size evidence used o200k, so the fix's size assumption has not been checked in the cap's unit.
- C5 (interpretation; S4): Established neighbour expansion merges neighbours by node identity and returns them in document order; charging the link cap only for links actually added follows from that.

## Core theory

Neighbour expansion in established retrievers merges the fetched neighbours into the set of results keyed by node identity, so a neighbour that is already present is not added or counted a second time, and it returns the merged set in document order (LlamaIndex PrevNextNodePostprocessor: all_nodes keyed by node_id, merged with update(), chain-ordered output). A budget check is only meaningful when it measures what is actually kept, in the unit the budget is defined in. The embedder here is KURE-v1, a BGE-M3 fine-tune with the XLM-R SentencePiece tokenizer, which is not the o200k tokenizer used in the cycle-1 measurement.

## Applicability

rag/retrieval/retrieval.py:235-248 (_with_links fills _LINK_TOKENS before any dedup) and 250-266 (_pack runs the i == j check, _is_dup and the token_budget only afterwards). rag/retrieval/retrieval.py:25 defines _LINK_TOKENS = 600, and config.yaml:58 says token_budget is counted with the embedding tokenizer (KURE-v1, config.yaml:47). The v12 numbers recorded in docs/research/review-retrieval-port-requirement-links-f7-1.md (Result) show that the real long-table chunks are larger than the cap. tests/test_retrieval.py:308-312 checks only the 300-token synthetic case, so it cannot catch either failure.

## Hypothesis

The defect is where and in what unit the link choice is measured, not the order of the links. The 600-token cap is applied to a candidate list before _pack decides what actually enters the context, and the fix was checked on fixture sizes rather than the real table chunks in the cap's own unit. A fix that holds would (a) move the link choice into _pack: only after a found chunk is actually picked, walk links[i] in _link_priority order, skip chunks that are already picked or near-duplicates without charging them to the cap, and charge only chunks that are actually added; (b) measure the long-table chunks with Embedder.token_counts, and if they exceed the cap, decide explicitly how a split table gets at least its nearest part. Two options: always admit the highest-priority link that still fits the 2500 budget, the way _pack already keeps the first chunk over budget, or size _LINK_TOKENS from the measured maximum table chunk. Without (b), the invariant cannot hold on the v12 data whatever the ordering.

## Counterevidence

- The round-10 review text was not available here; the refusal reason is inferred from the code and the cycle-1 numbers, so the review may have refused for a different reason, such as context flooding or a missing pipeline measurement.
- Only 3 tables (21 chunks) in v12 have more than 6 chunks, so whatever the fix does, its effect on dev retrieval metrics may be too small to measure.
- If KURE token counts for those chunks turn out below 600 (XLM-R may split Korean differently from o200k), cause (2) disappears and only the dedup-before-cap cause remains.
- Admitting a link over the cap reopens the original worry behind _TABLE_LINK_MAX: long requirement-list tables taking budget away from other documents' evidence.

## Alternatives

- Keep 6510eea and only rewrite the test with realistic sizes: this would show the defect but fix nothing.
- Raise _LINK_TOKENS to a fixed larger number: this moves the cliff instead of tying it to measured chunk sizes, and the choice would still be made before dedup.
- Restore _TABLE_LINK_MAX: this is exactly what F7 refused.
- Prepend the table header to continuation chunks during preprocessing: that belongs to another pipeline and the v11/v12 package, outside this PR's retrieval scope.

## Experiment

(1) Unit test: a 9-chunk table where an earlier ranked hit has already packed c0, then hit c5 at 300 tokens per chunk. The current code charges c0 to the cap, so _pack skips it as already picked and only c4 is added after c5 (c4, c6 or both may still have been missing). With the choice moved into _pack, c4 and c6 both arrive (c0 is skipped without charge). Add a case where the found chunk is skipped by _pack and assert its links are not packed. (2) No API calls: load the v12 corpus/chunks.jsonl, take the (doc_id, table_ref) groups with more than 6 chunks, compute Embedder.token_counts for their bodies, and count the hits that get zero links under the current code and under the proposed rule. Report counts only. (3) Run rerun_retrieval on dev only (never test), with an index rebuilt for this branch, then 05 Retrieval only, comparing Evidence Coverage single and multi.

## Result

Observed, not verified: this is still a draft. The reviewer's case reproduced at 4090646: a 9-chunk table, hit c5, a 600-token c0 that `_pack` drops as a near-duplicate of c5, and a 100-token c4. `_pack([(5, 0.9)])` returned `['c5']`, because c0 used up the whole link cap before `_pack` dropped it.

Experiment (2), counts only, offline with the KURE-v1 tokenizer (the unit `_LINK_TOKENS` and the budget are measured in). The 21 chunks of the 3 v12 tables with more than 6 chunks have a median of 576 KURE tokens (max 701; 6 are over 600). Under head-then-distance order with the 600 cap, 0 of the 21 possible hits get zero links, so cause (2) disappears, as the Counterevidence anticipated. No change to the cap policy, option (b), was needed. For comparison, 322 of the 1,562 chunks in 2-6 chunk tables exceed 600 tokens (median 461).

The fix follows part (a) of the hypothesis. `_with_links` is removed. `_pack` adds a found chunk through a new `_admit`, which rejects chunks already picked, near-duplicates in the same document, or chunks over the room left. Only after the found chunk is actually picked does it walk `links[i]` in `_link_priority` order. Each link is admitted against min(budget left, `_LINK_TOKENS` minus what this hit's links already took), so the cap is charged only for links actually added. The links added for one hit are put in document order.

Tests (`tests/test_retrieval.py`):
- `test_links_already_packed_or_dropped_as_duplicates_do_not_use_the_link_cap`: hit c0 then c5 at 300 tokens per chunk gives `['c0', 'c1', 'c2', 'c5', 'c4', 'c6']` (old code: no c6), and the reviewer's duplicate-head case gives `['c5', 'c4', 'c6']` (old code: `['c5']`).
- `test_links_of_a_found_chunk_dropped_as_a_duplicate_are_not_packed` gives `['c0']` (old code: `['c0', 'c2']`).

`tests/test_retrieval.py`, `tests/test_retrieval_benchmark.py` and `tests/test_v11_package.py` pass (76 passed), and ruff is clean. The commit is the one that carries this page ("retrieval: charge the link cap only for links actually packed"). Not run: experiment (3), the dev `rerun_retrieval` and 05 Retrieval comparison, because it needs an index rebuilt from this branch's search texts.

## Unresolved limits

The round-10 finding text was not read. KURE token sizes of the long-table chunks are unmeasured; the only figures are o200k. Which cap policy is acceptable (hard cap, nearest link always admitted, or a measured cap) is a product decision for the retrieval owner. The LlamaIndex source shows dedup by node id but no token budget, so the claim that links should be charged after dedup is this page's reading.
