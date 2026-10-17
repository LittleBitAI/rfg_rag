# Review research — F2, cycle 1

Draft research before the fix of review round 2 of PR #63, written 2026-10-17. It is not a verified fact or a shared rule: the review reads it with the fix.

## Problem

F2 breaks declared-unit inheritance: a numeric table cell should retain its column's scale, field identity and source spans across supported row formatting. The first repair restored declaration state, but the current parser can still discard a shortened total when boundary pipes and a line ending inflate the apparent cell count. Components remain available and may become the document value. [C1, C2, C4]

Trigger: repeat, rounds 1, 2.

- [P1] [P1] rag/retrieval/quantity_metadata.py:41 — declared units still miss shortened rows in standard Markdown tables

## Failed fixes

- At 588577d, the supplied review reports that declaration-like currency scales were suppressed as amounts without being retained for numeric cells. That prevented a false standalone amount but also lost the actual budget. The repair report confirms this reproduction; historical code was not independently available through the diff tool. [C2]
- The round-1 repair added column declarations, a preceding default declaration, scaling, source spans, component labels and shortened-row remapping. It repaired the original example, but remapping depends on a raw regex match count rather than the logical row width. Header parsing trims boundary syntax; implicit data-cell parsing does not. [C2, C3]
- The shortened-total regression uses '계 | 200,000' at EOF, without boundary pipes. Its numeric cell remains the second of two matches, enabling remapping to the third header column. It never exercises the extra match after a trailing pipe, so it cannot substantiate the broader shortened-row claim in the repair report. [C3, C5]

## Sources

### S1 — Quantity metadata extraction

- URL: rag/retrieval/quantity_metadata.py
- Retrieved: 2026-10-17
- Locator: Lines 32–55, 135–137, 158–171 and 202–223
- Fragment: if count < len(declarations):
    remaining = [i for i in range(column, len(declarations)) if declarations[i] is not None]
    return remaining[0] if len(remaining) == 1 else None
return column

cells = list(re.finditer(r"[^|]+", line))

for line in body.splitlines(keepends=True):
    quantities = [(quantity, None) for quantity in _read(line)]
    if "|" in line:
        quantities.extend(_implicit_cells(line, headers, declarations, default))
        if not quantities and re.search(r"[가-힣]", line):
            cells = list(re.finditer(r"[^|]+", line.strip().strip("|")))

 offset += len(line)
- Applicability: Shows raw data-cell counting, conditional remapping, different header normalization and raw-line offset accounting. A missed Korean-labelled row can also enter header replacement because no quantity was recovered.
- Counterevidence: A default declaration can supply a unit even when column remapping fails; explicit-unit quantities follow a separate path.
- Validation: Inspect the failing row's cell spans and target column, then verify formatting-invariant values, labels and original source slices.

### S2 — Declared-unit and shortened-total regression fixtures

- URL: tests/test_quantity_filter.py
- Retrieved: 2026-10-17
- Locator: Lines 68–73 and 374–420
- Fragment: def embed_query(self, text):
    return [1, 0] if "예산" in text else [0, 1]

text = ("예산과목 | 주요 내용 | 예산(천원)\n"
        "전산개발비 | 시스템 구축 | 140,000\n장비비 | 장비 구입 | 60,000\n계 | 200,000")
rows = quantity_rows([chunk("a", text)])
assert [(row["value"], row["phrase"]) for row in rows] == [
    (140000000, "사업 예산 전산 개발비"), (60000000, "사업 예산 장비 비"), (200000000, "사업 예산 계")]
assert all(text[slice(*row["span"])] == row["original"] for row in rows)
- Applicability: Defines the intended component/total extraction and exposes the missing boundary-pipe/newline case. Nearby tests cover declaration scaling, explicit units and scope.
- Counterevidence: The fixture genuinely covers the delimiter-free EOF representation. Its stub cannot distinguish budget field similarities.
- Validation: Extend this behavior regression with the reported representation and retain its label and span assertions.

### S3 — Documented quantity-filter contract

- URL: README.md
- Retrieved: 2026-10-17
- Locator: Lines 46–61
- Fragment: Declared column units and a preceding `(단위: 천원)` apply to numeric table cells: `사업예산(천원) | 부문` followed by `10 | 운영` yields 10,000 won. The metadata preserves both the numeric cell and its unit declaration spans; the context displays `10 (천원)`. Explicit cell units take precedence, and inherited units end with the table or chunk. Component row labels remain distinct from a shortened total row.

Values without an accepted matching field can still be omitted, and conflicting values within one document are not semantically reconciled.
- Applicability: Establishes inheritance, provenance, scope and distinct labels as intended behavior. Line 46 also requires rebuilding the index after extraction changes.
- Counterevidence: The contract expressly limits semantic reconciliation; it does not promise that any total always outranks every component.
- Validation: Verify extraction and displayed evidence, then rebuild the stored quantity index before evaluating application behavior.

### S4 — Round-1 quantity repair and validation report

- URL: docs/quantity_filter_validation.md
- Retrieved: 2026-10-17
- Locator: Review round 1, lines 5–23
- Fragment: Both a column declaration `사업예산(천원)` and a preceding `(단위: 천원)` lost numeric-only cells.

Shortened total rows retain their column unit, and component labels prevent a partial cost from replacing the project's total.

Of 119 chunks with parenthesized currency declarations and tables, 4 documents gained 8 inherited numeric rows. Seven have labels; one KOICA row remains unlabelled and cannot supply a budget.

The paid answers and user-reported browser acceptance below predate these review repairs. They remain historical evidence for those saved contexts, not new paid or browser acceptance of the repaired contexts.
- Applicability: Records the earlier failure, attempted repair, census and limits of acceptance evidence.
- Counterevidence: Reports a successful museum-total check and unchanged selected values for four queries. Those records do not establish coverage of the round-2 formatting, and their artifacts were unavailable here.
- Validation: Repeat the relevant offline comparison after adding the exact failing representation, reporting changed values and exclusions rather than assuming unchanged totals.

### S5 — Document-value selection

- URL: rag/retrieval/quantity_filter.py
- Retrieved: 2026-10-17
- Locator: Lines 126–158
- Fragment: if row["doc_id"] not in chosen or row["similarity"] > chosen[row["doc_id"]]["similarity"]:
    chosen[row["doc_id"]] = row

eligible = [{**r, "similarity": float(similarities[r["phrase"]])} for r in rows
            if _usable(r) and similarities[r["phrase"]] >= cutoff]

chosen = _document_values(eligible, unit)
matched = [r for r in chosen.values() if condition.accepts(r["value"])]
- Applicability: Explains how a surviving component can supply the document value and alter threshold matches after total extraction fails.
- Counterevidence: A component must still meet usability, unit and similarity requirements. Even an extracted total is not automatically preferred.
- Validation: Use controlled, distinct field similarities to isolate the effect of recovering the missing total.

### S6 — Python 3.10 str.splitlines documentation

- URL: https://docs.python.org/3.10/library/stdtypes.html#str.splitlines
- Retrieved: 2026-10-17
- Locator: str.splitlines, lines 893–919
- Fragment: Line breaks are not included in the resulting list unless keepends is given and true.
- Applicability: _chunk_rows() explicitly passes keepends=True, so LF and CRLF remain in each raw line.
- Counterevidence: Keeping endings is useful for source-offset accounting and is not itself an error.
- Validation: Confirm the raw total line includes its ending; preserve downstream offsets after changing cell parsing.

### S7 — Python 3.10 complemented regex character sets

- URL: https://docs.python.org/3.10/library/re.html#regular-expression-syntax
- Retrieved: 2026-10-17
- Locator: Regular Expression Syntax, complemented sets, line 82
- Fragment: If the first character of the set is '^', all the characters that are not in the set will be matched.
- Applicability: The actual pattern [^|]+ accepts newline and exterior spaces as well as cell contents.
- Counterevidence: Without a trailing pipe, the ending remains inside the preceding cell match rather than creating an additional segment.
- Validation: Compare the cell matches for a total with and without a trailing pipe and ending.

### S8 — GitHub Flavored Markdown specification

- URL: https://github.github.com/gfm/#tables-extension-
- Retrieved: 2026-10-17
- Locator: Section 4.10; table recognition and Example 204
- Fragment: If there are a number of cells fewer than the number of cells in the header row, empty cells are inserted.
- Applicability: Provides a structural comparison: recognized GFM tables require matching header/delimiter widths; short body rows are padded and excess cells are ignored. Example 204 places padding after existing cells.
- Counterevidence: The repository accepts delimiter-free flattened tables and remaps a shortened row to a unique declared column. That domain behavior is not implied by GFM.
- Validation: Include a proper delimiter-row variant, but retain the repository's existing delimiter-free regression and explicit recovery expectations.

### S9 — GitHub Docs: organizing information with tables

- URL: https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/organizing-information-with-tables
- Retrieved: 2026-10-17
- Locator: Creating a table, line 46
- Fragment: The pipes on either end of the table are optional.
- Applicability: Supports treating exterior pipes as row syntax rather than additional data columns.
- Counterevidence: This formatting guidance does not specify currency inheritance or recovery of flattened merged cells.
- Validation: Compare otherwise identical rows with and without exterior pipes and require equivalent quantity metadata.

## Claims

- C1 (interpretation; S2, S3): Declared numeric table values must preserve scale, field identity and source provenance, including the supported shortened-total representation.
- C2 (source; S1, S4): The repair report confirms the original declaration loss; the current implementation adds retained declaration state, scaling and shortened-row recovery.
- C3 (interpretation; S1, S6, S7): For the supplied trailing-pipe/newline total with no default declaration, the current source predicts a phantom third cell, skipped remapping and an omitted amount; full component rows remain extractable.
- C4 (interpretation; S2, S3, S5): Missing total metadata can change the selected document value and matches, but recovery alone does not guarantee total preference because selection uses field similarity and preserves the first row on ties.
- C5 (source; S2): The existing shortened-total regression covers a delimiter-free row at EOF without exterior pipes; nearby positive tests cover scaling, spans, explicit units and scope.
- C6 (source; S6, S7, S9): Python retains endings with keepends=True, complemented pipe sets match those endings, and exterior Markdown table pipes are optional.
- C7 (interpretation; S1, S2, S8): GFM's short-row padding does not justify the repository's later-column remapping; the latter is a domain recovery heuristic for flattened input.
- C8 (interpretation; S1, S2, S5, S6, S8, S9): The proposed repair should establish consistent structural cell boundaries before counting, preserve original offsets and interior empty positions, and validate formatting invariance without broadening selection policy.
- C9 (interpretation; S2, S4): The reported round-1 corpus checks support their recorded inputs, while their scope and historical acceptance caveat do not establish coverage of the round-2 representation.
- C10 (source; S3): Extraction changes require rebuilding the stored quantity index before application results can establish that the repair is active.

## Core theory

Python preserves line endings when splitlines(keepends=True) is used, and a complemented character class excludes only its specified characters; excluding a pipe does not exclude a newline. Markdown boundary pipes are optional syntax. Logical cells must therefore be identified before their count drives column inference. Separately, GFM pads short rows with empty cells: it does not authorize moving a second-cell amount into a third budget column. That movement is this repository's flattened-table recovery heuristic. [C6, C7]

## Applicability

Correct the row-boundary interpretation used by _implicit_cells() before _cell_column() measures row width. Header and data parsing should agree about optional exterior pipes and exterior whitespace while retaining offsets into the original line. Keep genuine interior empty cells positional; removing every whitespace-only segment would introduce another alignment error. Retain the existing unique-declaration restriction for shortened rows, explicit-unit precedence, component labels and declaration scope. Audit the other three cell-parsing sites for consistency, without turning this repair into a general Markdown parser. After verification, rebuild quantity metadata and its phrase embeddings before judging frontend results. [C3, C8, C10]

## Hypothesis

The remaining defect is inconsistent structural cell parsing before column assignment. For '| 계 | 200,000 |\n', keepends=True supplies the newline to _implicit_cells(), and [^|]+ matches [' 계 ', ' 200,000 ', '\n']. With three declarations, _cell_column(1, 3, declarations) returns column 1 instead of remapping to budget column 2. With no default declaration, the amount is omitted. A full component row still reaches column 2 and survives. This is a static trace, awaiting runtime confirmation. [C3]

## Counterevidence

- The original declaration examples now have positive scaling, span and scope regressions. The declaration-state repair is substantive; it is not entirely ineffective. [C2, C5]
- The repair report records an offline corpus check retaining the museum's 200-million total and unchanged selected values for four queries. This supports those recorded inputs, but the available fixture omits the failing boundary-pipe representation. Referenced execution artifacts were not available as tracked files. [C5, C9]
- The precise omission trace assumes no preceding default declaration. With a default, inheritance may still occur, although the field can be assigned incorrectly. [C3]
- Restoring the total does not guarantee its selection. The selector chooses the highest-similarity usable field and keeps the first row on a tie; the current test embedder assigns identical vectors to budget phrases. Selection behavior must be checked separately under controlled similarities or the existing local model. [C4]
- Strict GFM would leave the third column empty in this shortened row. The desired total recovery comes from the repository's documented extraction behavior, not from Markdown semantics alone. [C1, C7]

## Alternatives

- Changing Kiwi tokenization or currency-scale recognition is not the first fix: declaration recognition succeeds in the positive regressions, while the failing branch can be explained before numeric scaling. [C3, C5]
- Removing only newline characters from the regex would address the reported LF case but leave exterior spaces after a trailing pipe and indentation before a leading pipe able to inflate cell counts. Handle structural boundaries rather than one character. [C3, C6, C8]
- Changing splitlines() globally to discard endings risks invalidating subsequent source offsets because _chunk_rows() advances offset by len(line). Preserve raw-line accounting and parse cells within it. [C3, C8]
- Discarding every empty or whitespace-only cell confuses exterior syntax with genuine empty columns. Preserve interior positions. [C7, C8]
- Summing components, choosing the largest amount or adding a total-selection preference would change document-value policy and cannot repair the missing metadata. Address extraction first; measure whether a separate selection defect remains. [C4]
- A full Markdown parser is disproportionate to the demonstrated defect and would not inherently recover flattened merged cells. The existing fixture also intentionally accepts pipe-separated tables without a GFM delimiter row. [C5, C7]

## Experiment

No tests were executed in this read-only research turn. In the implementation turn, extend the existing shortened-total regression with '| 예산과목 | 주요 내용 | 예산(천원) |\n| --- | --- | --- |\n| 전산개발비 | 시스템 구축 | 140,000 |\n| 장비비 | 장비 구입 | 60,000 |\n| 계 | 200,000 |\n다음 본문'. Before editing, confirm that the total's raw matches include a third newline segment and that its numeric target is column 1. Expect components to remain and the total to be absent. After the correction, require exactly the three intended monetary rows, including 200000000 won labelled '사업 예산 계', with numeric and declaration spans slicing their original text. Compare boundary-pipe variants with LF, CRLF, EOF and trailing exterior spaces; preserve the existing delimiter-free form. Include one explicit interior-empty-cell row to catch over-trimming. Re-run existing explicit-unit and scope regressions. For downstream verification, assign the total a higher controlled field similarity than components and choose a threshold between 140 million and 200 million; confirm that the selected original value and match are invariant across formatting. Do not use the existing equal-vector budget stub to infer a total preference. Finally run the affected tests and required repository checks, then rebuild affected quantity metadata and embeddings for the recorded corpus queries. [C3, C4, C5, C8, C10]

## Result

Observed before editing at `684c463`: the total's raw matches were `[' 계 ', ' 200,000 ', '\n']`, the numeric target was column 1, and only the 140-million/60-million components survived (`artifacts/quantity_review2_before.log`). The fix is committed together with this draft under the unique subject `retrieval: fix table boundaries, project routing and index rollback` (parent `684c463`). `tests/test_quantity_filter.py::test_declared_table_units_preserve_component_labels_and_collapsed_total_cells` checks ten formatting/empty-cell variants, including the original separator-free EOF form; `test_interior_empty_cells_keep_positions_between_different_declared_units` checks column identity, while `test_table_units_are_column_specific_and_end_with_the_table` retains explicit-unit and scope coverage. Numeric and declaration spans slice the source. Controlled similarities prefer the total, and a 150-million threshold returns 200 million in every variant. The affected ten-file run passed 694 tests with 12 warnings; after explicitly retaining the original separator-free form, the changed test file passed all 130 tests again in 12.06 seconds. Rebuilding all 13,627 table-bearing chunks (6,968 with declarations) changed zero corpus rows; re-embedding the resulting 11,949 phrases preserved the four query values/counts/exclusions and all 60 dev context-ID sequences. Logs: `artifacts/quantity_review2_cleanup_gate.log`, `quantity_review2_final_test_cleanup.log`, `quantity_review2_scope.log` and `quantity_review2_offline.log`. These are recorded implementation observations; this page remains a draft, not a verified finding or shared rule.

## Unresolved limits

At research time, the supplied review established the chronology, historical diff lookup failed, and current behavior was only statically traced. The implementation observations above now record runtime coverage and a local corpus census; generated artifacts remain local and are not tracked-source evidence. Ambiguous shortened rows, escaped pipes and general merged-cell recovery remain outside the demonstrated fix. The similarity policy does not guarantee a total outranks every component. This remains a draft hypothesis and experiment record, not an independently verified repair. [C3, C7, C9]
