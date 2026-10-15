# Review research — F2, cycle 1

Draft research before the fix of review round 2 of PR #49, written 2026-10-16. It is not a verified fact or a shared rule: the review reads it with the fix.

## Problem

For an unanswerable candidate, _absent_verdict certifies that the asked document lacks the attribute when no validator call over any batch from document_batches answers the question. The invariant: absence may be certified only after the validator has seen every unit of the asked document together with the context needed to read it, above all a table row with its table's header row. document_batches cuts the flat unit list every DOCUMENT_BATCH_CHARS (60,000) characters with no regard to structure. If a table's header row (row 0) is in one batch and its value rows are in the next, no batch can answer. Example: header `시스템 | 하자담보책임기간 | ...`, row `A시스템 | 12개월 | ...`. The literal key_terms check misses the synonym, every call correctly returns unanswerable, and an answerable question is released as auto_validated.

Trigger: repeat, rounds 1, 2.

- [P1] [P1] golden_pipeline/validation.py:697 — Batch boundaries can still turn answerable questions into certified absences

## Failed fixes

- Round 1 (2686380, best_matching): sent the validator only the five units that best matched the question words. An answer written with a synonym further down the document was never seen. The reviewer reproduced this.
- Round 2 fix (b8e4fa6/6007579, validation-5): replaced best_matching with document_batches, which sends every unit in 60,000-character batches. Coverage is now complete, but each batch is judged on its own and boundaries ignore tables. plan.document_units returns only {unit_id, text} and drops location and element_id, so the batcher cannot even tell a header from a row. Original grid cells, one unit per cell and written after all chunk units (evidence.py:48-49), are cut the same way. The fix knew about the hole and deferred it in a ponytail note (validation.py:680). Its regression test sets DOCUMENT_BATCH_CHARS=1 and puts a self-contained answer in the last unit, so it proves delivery only and cannot fail on lost context.

## Sources

### S1 — Unstructured docs — Chunking

- URL: https://docs.unstructured.io/open-source/core-functionality/chunking
- Retrieved: 2026-10-16
- Locator: basic strategy; overlap options
- Fragment: A Table is "always isolated and never combined with another element." An element that exceeds the hard maximum is "divided into two or more chunks using text-splitting." An oversized table "is divided into two or more TableChunk elements using text-splitting." overlap applies "only when using text-splitting to break up an oversized chunk" and includes "this number of characters from the end of the prior chunk as a prefix on the next"; overlap_all may "pollute" normal chunks. by_title: "a single chunk will never contain text that occurred in two different sections" (basic has no section rule).
- Applicability: Supports keeping a table whole in one batch and treating it specially when it is oversized. Also shows that overlap is a fixed character prefix, so it cannot guarantee a header that sits further up.
- Counterevidence: Isolating a table into its own chunk does not by itself carry the header into later TableChunks. That needs the separate repeat option (S2).
- Validation: The unit test asserts that a table that fits stays in one batch.

### S2 — Unstructured commit 615782a — fix(chunking): preserve semantic headers in carried table chunks (#4313)

- URL: https://app.semanticdiff.com/gh/Unstructured-IO/unstructured/commit/615782a466f5e1b8a1e32183e133f8f9564fdb66
- Retrieved: 2026-10-16
- Locator: commit summary (fetch returned HTTP 429; text from search results)
- Fragment: When repeat_table_headers=True and a table is split, leading header rows are detected from <thead> or contiguous <th> rows, and continuation chunks repeat those rows inside a <thead>. Continuation chunk .text also includes the header text; reconstruct_table_from_chunks() strips the synthetic carried-header text so merged tables don't duplicate headers.
- Applicability: The same remedy for an oversized table: repeat row 0 at the top of each continuation batch.
- Counterevidence: Opt-in and recent, so not every chunker does it. It relies on detecting headers; here row 0 is assumed to be the header, which may miss multi-row headers.
- Validation: The unit test asserts row-0 units appear in every batch holding rows of the same table.

### S3 — Chonkie — TableChunker

- URL: https://docs.chonkie.ai/oss/chunkers/table-chunker
- Retrieved: 2026-10-16
- Locator: Overview / behaviour
- Fragment: "splits large markdown or HTML tables into smaller, manageable chunks by row, always preserving the header"; "Each chunk is a valid markdown table segment, always including the header."; "If the table fits within the chunk size, it is returned as a single chunk."; requires "at least a header, separator, and one data row (for Markdown)".
- Applicability: An independent implementation of the same rule: keep a table whole if it fits, otherwise split by rows and put the header in every chunk.
- Counterevidence: Works on markdown/HTML tables with an explicit header. Here the header is inferred as row 0.
- Validation: Same unit test.

### S4 — Anthropic — Introducing Contextual Retrieval

- URL: https://www.anthropic.com/news/contextual-retrieval
- Retrieved: 2026-10-16
- Locator: problem statement; SEC filing example
- Fragment: "it can lead to problems when individual chunks lack sufficient context." ... "these traditional RAG systems have a significant limitation: they often destroy context." Example chunk "The company's revenue grew by 3% over the previous quarter" — "this chunk on its own doesn't specify which company it's referring to or the relevant time period." Hedged: works "well for many applications".
- Applicability: The general principle: a chunk read on its own can lose what it needs to be understood. A table row without its header is this case.
- Counterevidence: Written about retrieval embeddings, not LLM reading. Its remedy (LLM-generated context per chunk) costs paid calls and is not proposed here.
- Validation: The end-to-end test: header and row in separate batches lead to wrong absence certification before the fix.

### S5 — Liu et al., Lost in the Middle: How Language Models Use Long Contexts (TACL 2024)

- URL: https://arxiv.org/abs/2307.03172v3
- Retrieved: 2026-10-16
- Locator: abstract
- Fragment: Performance is often highest when relevant information occurs at the beginning or end of the input context, and significantly degrades when models must access relevant information in the middle of long contexts, even for explicitly long-context models; performance also decreases as the input context grows longer.
- Applicability: Argues against removing batching altogether by sending the whole document in one call. A missed answer in the middle would produce the same silent false absence.
- Counterevidence: Measured on 2023 models with multi-document QA and key-value retrieval. Newer models may degrade less, and this was not tested on gpt-5-mini.
- Validation: Not exercised by the fix.

### S6 — golden_pipeline/validation.py — _absent_verdict, document_batches, _calls_needed

- URL: golden_pipeline/validation.py
- Retrieved: 2026-10-16
- Locator: lines 44, 674-702, 915-925
- Fragment: DOCUMENT_BATCH_CHARS = 60_000 ... if batches[-1] and size + len(unit["text"]) > DOCUMENT_BATCH_CHARS: batches.append([]) ... ponytail: 묶음 경계에 걸친 답(표 머리글과 그 행이 다른 묶음)이나 묶음 사이의 충돌은 보지 못한다. 놓치면 묶음을 겹쳐 나눈다. ... if item["primary_topic"] == "unanswerable": return len(document_batches(document))
- Applicability: Shows the character-count cut, the hole the round-2 fix itself flagged, and the call count that depends on the same function.
- Counterevidence: none
- Validation: The fix changes only document_batches (plus document_units' fields).

### S7 — golden_pipeline/plan.py — document_units, _with_headers; golden_pipeline/evidence.py — unit order

- URL: golden_pipeline/plan.py
- Retrieved: 2026-10-16
- Locator: plan.py:101-118, 249-263; evidence.py:48-49, 236-256
- Fragment: found[unit["doc_sha"]].append({"unit_id": unit["unit_id"], "text": text}) ... _with_headers: 표 행이 든 묶음 앞에 그 표의 머리글 행(논리 표 0행)을 붙인다 ... pairs += [pair for grid in pkg["grids"] for pair in grid_units(grid, pkg)] ... grid unit location {kind: table, grid: original_reference, row, cell}
- Applicability: Document units lose location and element_id, so the batcher cannot keep a table with its header. Grid cells are per cell and come after all chunk units. The codebase already has a header-attaching helper for bundles.
- Counterevidence: none
- Validation: After the fix document_units carries element_id and location, and the unit test exercises both table kinds.

### S8 — tests/golden/test_validation.py — whole-document absence test

- URL: tests/golden/test_validation.py
- Retrieved: 2026-10-16
- Locator: lines 553-565
- Fragment: monkeypatch.setattr(validation, "DOCUMENT_BATCH_CHARS", 1) ... validator = Validator({(last,): verdict("2년"), "*": verdict("", answerable=False)}) ... assert [Validator.labels(request) ...][-1] == (last,)
- Applicability: The only regression test answers from a single self-contained unit, so it cannot detect lost relational context.
- Counterevidence: none
- Validation: The new end-to-end test needs header and row labels in the same request.

## Claims

- C1 (source; S4): Splitting a document into chunks can leave a chunk without the context needed to understand it.
- C2 (source; S1, S2, S3): Document chunkers keep a table that fits in one chunk, split oversized tables at row boundaries, and repeat the header row in each continuation chunk.
- C3 (source; S6, S7): document_batches cuts on character count over units that carry no table location, so a table header and its rows can land in different batches. The round-2 fix flagged this as a deferred limit.
- C4 (interpretation; S1, S2, S7): Keeping element_id and location in document_units, batching by table, and repeating row-0 units in continuation batches closes the reviewer's reproduction for both logical tables and original grids.
- C5 (interpretation; S5): Removing batching by sending the whole document in one call trades boundary loss for recall loss in the middle of a long context, which leads to the same silent false absence.
- C6 (interpretation; S6, S8): Both earlier fixes addressed coverage (which units are sent) rather than readability (whether each batch can be read on its own). The regression test, built on a self-contained answer unit, could not tell the two apart, which is why the finding came back.

## Core theory

Chunking a document destroys context: a chunk can lose what it needs to be understood (Anthropic, Contextual Retrieval). Document chunkers therefore treat tables as units. Unstructured isolates Table elements, splits an oversized table at row boundaries first, and in #4313 adds repeat_table_headers so continuation chunks repeat the leading header rows. Chonkie's TableChunker splits by row, always keeping the header, and returns a table that fits as a single chunk. Character overlap alone covers only 'this number of characters from the end of the prior chunk', so it cannot bring back a header further up than the overlap.

## Applicability

golden_pipeline/validation.py:693 document_batches is the only place batches are made. _absent_verdict (:674) and _calls_needed (:923) both read it, so one change there fixes both. Its input comes from golden_pipeline/plan.py:101 document_units, which builds {unit_id, text} from units that do have element_id and location (units.jsonl, evidence.py:236-256). Logical table rows have location.kind=='table' with row 0 as the header, the convention plan._table_row and plan._with_headers already use. Grid cells have unit_id grid:sha:stream:control:row:col and location row/cell.

## Hypothesis

The cause is no longer which units are sent. It is that batching splits the document into pieces that cannot each be read on their own. document_batches works on a structure-less list, because document_units strips location and element_id, and it cuts on a character count. A table row then reaches the validator without the header row that names its columns. Fix: have document_units keep element_id and location. In document_batches, put each table in one batch: a logical table keyed by element_id, a grid keyed by (stream, control). When a table cannot fit, split it at row boundaries and repeat its row-0 units, with their original labels, at the top of each continuation batch, as plan._with_headers already does for bundles. _calls_needed must keep counting with document_batches so the call budget includes the repeated headers.

## Counterevidence

- Most boundaries may never touch a table. Documents are about 66k characters at the median, so most need one or two batches and have at most one boundary. How often this happens in the real data is unmeasured.
- Header repetition only fixes table context. A section heading in one batch and its paragraph in the next (for example 'A시스템' then '하자담보책임기간: 12개월') can still be separated. Keeping whole elements together does not cover a heading that is a separate element.
- Even inside one batch, original grid cells reach the validator as isolated cell texts without row and column coordinates, so a header that is present may still be hard to read. That is a separate weakness this fix does not address.

## Alternatives

- One call per document, so there are no boundaries: the largest document is about 200k characters, which probably fits in gpt-5-mini's context, and total input tokens stay about the same. Not first, because recall falls in the middle of long contexts (Lost in the Middle). A missed answer there becomes the same silent false certification, and nothing records why the 60k limit was chosen.
- Fixed character overlap between batches (the upgrade the ponytail note names): cheap, but a table longer than the overlap still loses its header. Not a guarantee.
- Reject any unanswerable candidate whose document needs more than one batch (the reviewer's fallback): sound and minimal, but with a median document near 66k characters it would drop roughly half the documents from the topic. Keep it only as a fallback for a group that cannot be kept with its context, if one is found.
- Restore context per unit by LLM, as in Anthropic's contextual retrieval: costs one paid call per unit, on a shared key. Not justified when the structure is already in units.jsonl.

## Experiment

1) A unit test on document_batches: build a document with a paragraph, a table element (row 0 header plus rows 1..n) and a grid with cells in rows 0 and 1. Set DOCUMENT_BATCH_CHARS so a plain cut falls between the header and the rows. Assert that every batch containing a row of table X also contains X's row-0 unit(s), and the same for the grid. 2) An end-to-end test in tests/golden/test_validation.py with an asked document containing a header and a value row that use a synonym of the key term. The fake Validator answers '12개월' only when the header's label and the row's label arrive in the same request. On current code the item comes out auto_validated; on the fix it must be rejected with '대상 문서에 있음: 검증기'. The existing test_absence_is_certified_only_after... must still pass. 3) Against the real evidence run, count how many released unanswerable items in feabfe5 have a table cut by a 60k batch boundary. Those items need validation again.

## Result

pending — the fix records what it observed here, with the tests and the commit.

## Unresolved limits

No shell here, so nothing was run and how often tables are cut in the real data is not known. Section headings separated from their text, conflicts between batches, and grid cells sent without coordinates stay uncovered. The Unstructured #4313 page returned HTTP 429, so its wording comes from search-result summaries. Nothing in the repository says why DOCUMENT_BATCH_CHARS is 60,000. Whether row 0 is always the only header row (multi-row headers) is not checked.
