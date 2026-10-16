# Review research — F2, cycle 2

Draft research before the fix of review round 3 of PR #49, written 2026-10-16. It is not a verified fact or a shared rule: the review reads it with the fix.

## Problem

For an unanswerable candidate, _absent_verdict certifies that the asked document lacks the attribute when no validator call over any batch from document_batches answers the question. Each batch is read on its own, so the invariant is: every unit must be read at least once in one batch together with the units it needs to be understood. For a table cell that means its row's identifying cell and its column header. Original grids break this. evidence.grid_units makes one unit per cell, and document_batches can split a grid between any two cells. A row's label cell ('A시스템') and its value cell ('1년') then land in different batches. The continuation batch repeats the row-0 headers but not the row label. Every batch correctly answers 'unanswerable', and an answerable question is released as auto_validated. This happens in production when a grid crosses 60,000 characters right after a cell longer than DOCUMENT_OVERLAP_CHARS, because _tail then carries nothing.

Trigger: repeat, rounds 2, 3.

- [P1] [P1] golden_pipeline/validation.py:712 — Original-grid rows can still be split between their label and value

## Failed fixes

- Round 1 (2686380): best_matching sent only the five units that best matched the question words. An answer written with a synonym further down was never seen.
- Round 2 fix (b8e4fa6/6007579): document_batches sent every unit in 60,000-character batches, but cut by character count with no regard to structure, so a table header and its rows could land in different batches. Its test used a self-contained answer unit, so it proved delivery only.
- Cycle 1 fix (24fe719, validation-6): kept each table in one group (logical table by element_id, grid by stream:control). An oversized table is split between units, with the row-0 units repeated in each continuation batch, plus a 2,000-character overlap. It assumed one unit is one row. That holds for logical tables (one unit per row, cells joined with ' | ') but not for original grids (one unit per cell), so the 'row boundary' split is really a cell boundary. The overlap does not rescue this: _tail returns nothing when the last unit is longer than 2,000 characters. The test test_every_batch_holding_a_table_row_also_holds_that_tables_header asserted only header ⊆ batch, so it passed even though at limit 1 its own TABLES fixture sends GRID:1:0 ('A시스템') and GRID:1:1 ('1년') to separate batches. The cycle-1 research made the same mistake: it said 'split at row boundaries' but specified 'repeat row-0 units' and tested only header presence.

## Sources

### S1 — Twig — Tables breaking across chunks (RAG scenarios and solutions)

- URL: https://www.twig.so/dev/rag-scenarios-and-solutions/chunking/table-splitting
- Retrieved: 2026-10-16
- Locator: rowspan/colspan section; chunk boundary rules
- Fragment: For HTML tables the chunk boundary 'must not' split the table, separate the header from the body, or break rows. Defines 'Rowspan="2": Cell spans 2 rows' and warns that a split after the first row gives 'Misaligned columns in chunk 2'. Large tables: 'Keep headers, split rows', with the tradeoff 'Header repetition, storage overhead'. Keeping tables whole 'Ensures no table is split' but gives 'Variable chunk sizes'. A long cell 'Might trigger chunk split mid-cell'.
- Applicability: Directly states the two rules this fix needs: never split inside a row, and track rowspan because a spanning cell ties rows together.
- Counterevidence: A vendor guide about embedding chunks of HTML tables, not LLM verification batches; no measurements. It also admits mid-cell splits for long cells.
- Validation: The unit test asserts every grid cell is read with its whole rowspan band and the header band.

### S2 — Ragie — Our approach to table chunking

- URL: https://www.ragie.ai/blog/our-approach-to-table-chunking
- Retrieved: 2026-10-16
- Locator: approach section
- Fragment: In most typical cases 'rows are never split mid-record' and 'table data is never disassociated from its table headers'; headers 'aren't repeated excessively'. A table that does not fit is 'processed by row', creating a new table and chunk for as many rows as fit. Exception: if 'a single row exceeds the maximum size for an embedding it is then split'. Merged cells are not mentioned.
- Applicability: An independent implementation of the same rule: the row is atomic, split only between rows, keep headers. That maps to a grid band as the atomic unit.
- Counterevidence: It has an oversized-row exception and says nothing about merged cells. Here a band over 60k would stay oversized instead.
- Validation: Same unit test; an oversized band goes into a batch of its own and is not split.

### S3 — Structure-Aware Chunking for Tabular Data in Retrieval-Augmented Generation (arXiv 2605.00318)

- URL: https://arxiv.org/abs/2605.00318
- Retrieved: 2026-10-16
- Locator: abstract
- Fragment: STC 'operates on row-level units' where 'each row is encoded as a key-value block', 'performs token-constrained splitting aligned with structural boundaries' and 'preserves semantic relationships between fields within a row'. Evaluated only on the MAUD dataset; marked work in progress; the abstract states no rule for rows over the token limit.
- Applicability: Supports making the row (here, a rowspan band) the indivisible unit of batching, so the fields of a row stay together.
- Counterevidence: Retrieval metrics on CSV/Excel, one dataset, work in progress; not about LLM absence judgments.
- Validation: End-to-end test: the label and value of a row reach the same validator request.

### S4 — Chonkie — TableChunker

- URL: https://docs.chonkie.ai/oss/chunkers/table-chunker
- Retrieved: 2026-10-16
- Locator: overview
- Fragment: Splits large markdown or HTML tables 'into smaller, manageable chunks by row, always preserving the header'; a table that fits is returned as a single chunk.
- Applicability: Row-based splitting with the header kept, the same as the existing loop once grid units are rows.
- Counterevidence: Works on markdown/HTML where a row is already one line; says nothing about rowspan.
- Validation: Existing header test plus the new band test.

### S5 — golden_pipeline/validation.py — document_batches, _table_groups, _tail, validator_input

- URL: golden_pipeline/validation.py
- Retrieved: 2026-10-16
- Locator: lines 44-46, 304-306, 696-745, 958
- Fragment: for unit in group: if fresh and size + len(unit['text']) > DOCUMENT_BATCH_CHARS: carried = _tail(batches[-1]); batches.append([header for header in headers if _row(unit) and header not in carried] + carried) ... _tail: if size > DOCUMENT_OVERLAP_CHARS: break ... validator_input sends only {label, text}.
- Applicability: Shows that splits happen between any two units of a group, that the repeated context is only row-0 units, that _tail drops everything after a long last unit, and that the validator sees no coordinates.
- Counterevidence: none
- Validation: The fix changes document_batches (band merge before the loop) and lets document_units pass rowspan.

### S6 — golden_pipeline/evidence.py — grid_units, _cell_unit

- URL: golden_pipeline/evidence.py
- Retrieved: 2026-10-16
- Locator: lines 152-173, 247-261
- Fragment: return [_cell_unit(base, stream, control, cell, errors, pkg) for cell in grid['cells']] ... 'unit_id': f"grid:{doc_sha}:{stream}:{control}:{cell['row']}:{cell['col']}" ... 'location': {'kind': 'table', 'grid': 'original_reference', 'row': cell['row'], 'cell': cell['col']}
- Applicability: One unit per grid cell, whereas logical tables have one unit per row. This is the mismatch the cycle-1 fix missed.
- Counterevidence: none
- Validation: The band test builds grid units in this shape.

### S7 — v11 original grid reference file, first record

- URL: data/RFP_Preprocessing_Final_v11_Team/validation/복구표_원본그리드_참고.jsonl
- Retrieved: 2026-10-16
- Locator: line 1, control 1974
- Fragment: {'row': 3, 'col': 0, 'rowspan': 2, 'colspan': 1, 'text': '요구사항 \n세부내용\n'}, {'row': 3, 'col': 1, 'text': '정의\n'}, ... {'row': 4, 'col': 1, 'text': '세부\n내용\n'}, {'row': 4, 'col': 2, 'text': '◦ 사업자는 모든 정보자산 도입 시 …'}; grid has rows 8, cols 3, level 1, parent_control null.
- Applicability: Real data has rowspan, so row 4 is labelled by a cell in row 3, and grouping by row index alone would split them. The record is a vertical key-value form, which shows row 0 is not always a column header. Repeating it is harmless, but the row label is what matters.
- Counterevidence: One record inspected; how common rowspan is across grids is not counted.
- Validation: Band test fixture copies this rowspan shape.

### S8 — tests/golden/test_validation.py — TABLES fixture and header test

- URL: tests/golden/test_validation.py
- Retrieved: 2026-10-16
- Locator: lines 575-602
- Fragment: doc_unit(f'{GRID}:1:0', 'A시스템', row=1), doc_unit(f'{GRID}:1:1', '1년', row=1) ... @pytest.mark.parametrize('limit', [40, 70, 1]) ... assert header <= sent
- Applicability: The test asserts only header presence, so it passes while its own fixture at limit 1 splits the grid row's label from its value.
- Counterevidence: none
- Validation: The new test asserts whole-band co-occurrence and fails on current code with this same fixture.

### S9 — Earlier research — review-feature-golden-absent-premise-f2-1.md

- URL: docs/research/review-feature-golden-absent-premise-f2-1.md
- Retrieved: 2026-10-16
- Locator: Hypothesis; Experiment 1; Counterevidence
- Fragment: When a table cannot fit, split it at row boundaries and repeat its row-0 units ... Assert that every batch containing a row of table X also contains X's row-0 unit(s), and the same for the grid ... original grid cells reach the validator as isolated cell texts without row and column coordinates ... That is a separate weakness this fix does not address.
- Applicability: The prescribed test checked only headers, and the grid-cell weakness was noted but set aside. That is the exact gap round 3 found.
- Counterevidence: none
- Validation: This cycle's experiment replaces the header-only assertion.

## Claims

- C1 (source; S5, S6): document_batches splits a group between any two units, and original-grid units are single cells, so a grid row's label cell and value cell can land in different batches. The continuation batch repeats only the row-0 units, and _tail carries nothing after a unit longer than DOCUMENT_OVERLAP_CHARS.
- C2 (source; S1, S2, S3, S4): Table-aware chunkers treat a row as the unit that may not be split, split large tables only between rows, and keep the header with each chunk. A single oversized row is split only as a fallback.
- C3 (interpretation; S1, S7): Rowspan ties consecutive rows together, and the v11 grid file has rowspan cells. So the indivisible unit for a grid is a rowspan band, not a row index.
- C4 (interpretation; S5, S8, S9): Each failed fix enforced and tested a weaker property than the invariant: delivery in round 2, header presence in cycle 1. Each review found the gap between the tested property and 'the units needed to read an answer arrive in one batch'. The cycle-1 fix assumed unit == row, which is false for grids.
- C5 (interpretation; S1, S2, S5, S7): Merging each original grid into one unit per rowspan band before the existing split loop makes every split fall between bands, keeps a multi-row header together as the band at row 0, makes _tail carry whole bands, and gives the validator row structure it cannot see from isolated cells.

## Core theory

Table-aware chunkers treat the row as the smallest unit that may not be split, split only between rows, and keep headers with every chunk. Merged cells (rowspan/colspan) must be tracked because a split after a spanning row loses its context and misaligns the columns. A row is split only as a fallback when it alone exceeds the size limit.

## Applicability

golden_pipeline/validation.py:696-718 document_batches is the only place batches are made; _absent_verdict (:685) and _calls_needed (:958) both read it. _table_groups (:721-730) already groups a grid by unit_id minus ':row:col'. Grid units come from evidence.py:152-173 and _cell_unit (:247-261), one per cell with location {kind: table, grid: original_reference, row, cell}. The grid source (data/RFP_Preprocessing_Final_v11_Team/validation/복구표_원본그리드_참고.jsonl) gives each cell row, col, rowspan and colspan. plan.document_units (plan.py:101-121) reads that file for cell text and can carry rowspan the same way. validator_input (validation.py:304-306) sends only label and text, so a merged band text is also the only way the validator can see which cells form a row.

## Hypothesis

Once more the fix enforced a weaker property than the invariant. This time it is 'a header is present' instead of 'the cells a row needs to be read are read together'. The structural cause is that the batching unit for grids is a cell, while the smallest self-contained piece is a row band: a run of consecutive rows tied together by rowspan. The real grid file has rowspan, for example aea2b415… control 1974, where row 3 col 0 '요구사항 세부내용' has rowspan 2 and labels row 4, which has no col-0 cell of its own. So grouping by row index alone, as the reviewer suggests, would still cut a merged label from its second row. The fix: at the start of document_batches, replace each original-grid group with one unit per row band. Band text is cells joined with ' | ' within a row and rows joined by newlines. location.row is the band's first row, so the band holding row 0 stays the header that the existing loop repeats, which also covers multi-row headers. element_id/unit_id stay grouped the same way. The existing per-unit split loop then splits only between bands, _tail carries whole bands, and _calls_needed counts the same batches. document_units must pass rowspan through for grid cells; it already reads the grid file for their text.

## Counterevidence

- The fraction of real grids larger than one batch may be tiny (median document about 66k characters). How often this triggers in final6 is unmeasured, and the fix may change no released item.
- Logical-table rows can depend on the row above in the same way: a restored markdown row that starts with an empty cell (the BLANK_CELL pattern, validation.py:38) continues a merged label from the row above. Splitting between such logical rows separates them. Banding only grids leaves this case open.
- Nested grids (parent_control set) get their meaning from the parent cell's row, which is in another group. Banding does not keep them together.
- A single band over DOCUMENT_BATCH_CHARS still goes into an oversized batch on its own (the fresh==0 branch). The sources split an oversized row as a fallback, which would bring the problem back for that band.

## Alternatives

- Split grids only between row indices (the reviewer's literal suggestion): smaller, but a rowspan label ('요구사항 세부내용' at row 3, rowspan 2) is still cut from row 4. The real data has such cells.
- Keep cells as separate units and only restrict split points to band boundaries: equivalent coverage, but the loop becomes two-level and the validator still receives isolated cell texts without row structure. Merging bands is less code and more readable.
- Merge grid bands in document_units instead of document_batches: also works, but it changes the text that other callers and the existing test at tests/golden/test_validation.py:550 expect for the asked document. Doing it in document_batches keeps the change local to the absence path.
- Larger DOCUMENT_OVERLAP_CHARS: does not guarantee anything, because a long cell still empties _tail. This is the production case the reviewer named.
- Reject any unanswerable candidate whose asked document has a grid larger than one batch: sound and minimal, but it discards candidates for a structural reason that banding removes for free.

## Experiment

1) Unit test on document_batches: a grid with header row 0, row 1 with a rowspan-2 label cell at col 0, row 2 with only a value cell, plus a long cell (> DOCUMENT_OVERLAP_CHARS) just before the boundary. Run limits 1, 40, 70 with overlap 0 and with overlap 20. Assert that for every grid cell some batch contains every cell of its band and the header band. On current code this fails at limit 1 with the TABLES fixture already (GRID:1:0 and GRID:1:1 in separate batches). 2) End-to-end through _absent_verdict: the fake ask answers '1년' only when the row-label text and the value text arrive in one batch. Current code returns auto_validated; the fix must return 'rejected', '대상 문서에 있음: 검증기'. The existing tests test_every_batch_holding_a_table_row_also_holds_that_tables_header and test_absence_is_certified_only_after… must still pass, with label expectations adjusted if banding changes numbering. 3) Offline, no paid calls: for the 16 released unanswerable items in final6, rebuild document_batches with the current code against evidence run v11-20261014 and count the grid bands split across batches. If any exist, list the items for revalidation and price that before calling the API. Also count logical rows matching BLANK_CELL that are cut from the row above, to decide whether that case needs the same treatment.

## Result

Draft, not verified beyond what is listed here. Observed in commit 8723a5e (validation-7):

- Reproduced before the fix: with the old `document_batches`, limit 1 and overlap 0, the cells `:7:1:0` and `:7:1:1` of the `TABLES` grid were sent in separate batches.
- Fix: `_grid_bands` replaces each original-grid group with one unit per rowspan band before labelling. Cells in a row are joined with ' | ' and rows with newlines, and the band keeps its first cell's `unit_id` and `location`, so the row-0 band is the header. `plan.document_units` now passes `rowspan` for grid cells.
- Experiment 1: `tests/golden/test_validation.py::test_every_table_row_is_read_in_one_batch_with_the_rest_of_its_row_and_its_header`, limits 1, 40 and 70 × overlap 0 and 20. The fixture has a rowspan-2 label `C시스템`, a long cell before the boundary, and a value-only row 2. It fails on the old code at limit 1 (both overlaps) and passes on the new code. Limits 40 and 70 also passed on the old code with this fixture.
- Experiment 2: the `(1, 0, TABLES, {"C시스템", "유지보수 1년"}, …)` case of `test_absence_is_not_certified_when_the_answer_needs_units_on_both_sides_of_a_batch_boundary`. On the old code it returned `auto_validated`; on the new code it is `rejected` with `대상 문서에 있음: 검증기`. The existing tests pass: `.venv\Scripts\python -m pytest -q tests` → 569 passed.
- Experiment 3 (offline, old code, final6's 16 released unanswerable items): 0 grid bands split across batches, 0 blank-led logical rows cut from the row above, 0 nested grids, and 0 items affected, across 245 rowspan bands seen. No released item was read with a split band, so eval/golden stays as is and no paid revalidation was run.

## Unresolved limits

No shell here, so nothing was run. The frequency of oversized grids, rowspan bands and blank-led logical rows in the real data is unknown. Whether colspan matters is untested; it changes cell positions inside a band but not band membership. Nested grids and bands over 60,000 characters stay uncovered. The web sources describe retrieval chunking of HTML or CSV tables, not LLM absence certification over HWP grids, so they support the row-as-atomic-unit rule only by analogy.
