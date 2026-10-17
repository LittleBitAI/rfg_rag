# Review research — F2, cycle 2

Draft research before the fix of review round 3 of PR #63, written 2026-10-17. It is not a verified fact or a shared rule: the review reads it with the fix.

## Problem

F2 concerns the lifetime of a table's declared units and field labels. Numeric cells must inherit the active column schema until the supported table boundary, even when an earlier data row contains no usable quantity. In the current code, '사업명 | 사업예산(천원)\n--- | ---\nA 사업 | -\nB 사업 | 100' is predicted to lose the budget declaration at 'A 사업 | -', preventing recovery of 100,000 won. This violates the documented inheritance contract and can change document selection or exclusion counts. [C1, C4, C9]

Trigger: repeat, rounds 2, 3.

- [P1] [P1] rag/retrieval/quantity_metadata.py:218 — 값이 비어 있는 데이터 행이 선언 단위 상태를 지움 / 선언 단위 표에서 앞 행의 값이 `-`인 경우 / 이후 숫자 셀이 색인에서 누락됨

## Failed fixes

- The original implementation suppressed declaration-like currency scales as standalone amounts without retaining them for numeric cells. The round-1 repair added column/default declarations, scaling and provenance. It addressed the original omission, but retained a rule that treats a Korean pipe row with no extracted quantity as a new header. The earlier research records that rule, and it remains in the current source. [C2, C3]
- The round-1 shortened-total fixture omitted exterior pipes and placed the total at EOF. Consequently, it did not expose a trailing newline being counted as an extra cell, which prevented shortened-column recovery. The previous research and repair report document this separate failure. [C2]
- The round-2 repair consolidated cell parsing in _cells(), trimming exterior syntax while preserving interior empty cells. Its expanded tests exercise formatting and alignment, but all component/total data rows contain recoverable quantities. The separate empty-cell fixture also contains a recoverable budget. None exercises a wholly quantity-free Korean data row followed by a numeric row. Correct cell boundaries therefore left the destructive header transition untouched. [C3, C5]
- The recorded round-2 corpus comparison found no changed quantity rows, and the existing searches retained their results. Those observations support the tested corpus and formatting repair; they do not establish that declaration state survives a missing-value row. Referenced execution artifacts are not tracked sources available to this research pass. [C12]

## Sources

### S1 — Quantity metadata extraction and table-state mutation

- URL: rag/retrieval/quantity_metadata.py
- Retrieved: 2026-10-17
- Locator: Lines 15–64, 143–145, 166–180 and 210–236
- Fragment: quantities.extend(_implicit_cells(line, headers, declarations, default))
if not quantities and re.search(r"[가-힣]", line):
    cells = _cells(line)
    headers = [cell[0].strip() for cell in cells]
    declarations = [_declared_unit(cell[0], offset + cell.start()) for cell in cells]

else:
    declared = _declared_unit(line, offset) if "단위" in line else None
    default = declared if headers or declared else default
    headers, declarations = [], []

Declaration fallback in _implicit_cells():
declaration = declaration or default
number = NUMBER_CELL.fullmatch(cell[0])
if declaration is None or number is None:
    continue
- Applicability: Contains the destructive transition, the default-unit masking path, paired field/unit inheritance and the existing non-pipe reset. _cells() already handles structural exterior pipes.
- Counterevidence: Explicit units and a default declaration can preserve quantity extraction in some cases. Preserving an active schema indiscriminately could obstruct genuine later headers.
- Validation: Trace the exact input line by line, then verify preservation of both field labels and declarations across quantity-free rows and their reset at supported boundaries.

### S2 — Quantity-filter regression fixtures

- URL: tests/test_quantity_filter.py
- Retrieved: 2026-10-17
- Locator: Lines 279–285, 374–436 and 458–463
- Fragment: Declared-unit fixture: ("사업예산(천원) | 부문\n10 | 운영", 10000, "원", "사업 예산")

Scope fixture:
text = ("(단위: 천원)\n사업예산 | 사업기간(개월)\n10 | 5\n20원 | 6개월\n"
        "다음 본문\n사업예산 | 부문\n30 | 운영")

Boundary fixture:
lines = ["예산과목 | 주요 내용 | 예산(천원)",
         "전산개발비 | 시스템 구축 | 140,000", "장비비 | 장비 구입 | 60,000", total]

Interior-empty fixture:
text = "| 사업기간(개월) | 부문 | 예산(천원) |\n||운영|200,000|\n다음 본문"
- Applicability: Defines existing positive scaling, generic-header, explicit-unit, scope, formatting and empty-column behaviors. Its empty-column row still contains a recoverable quantity.
- Counterevidence: These are meaningful regressions for earlier defects. Their presence does not establish coverage of a wholly quantity-free data row preceding another row.
- Validation: Extend coverage with the reported sequential state transition and baseline equivalence while retaining these existing assertions.

### S3 — Documented quantity-filter inheritance and selection contract

- URL: README.md
- Retrieved: 2026-10-17
- Locator: Lines 46–65
- Fragment: Declared column units and a preceding `(단위: 천원)` apply to numeric table cells: `사업예산(천원) | 부문` followed by `10 | 운영` yields 10,000 won. The metadata preserves both the numeric cell and its unit declaration spans; the context displays `10 (천원)`. Explicit cell units take precedence, and inherited units end with the table or chunk. Component row labels remain distinct from a shortened total row.

A shortened total still uses the existing unique-declared-column recovery; this does not infer arbitrary merged cells or prefer totals over fields with higher similarity.

Values without an accepted matching field can still be omitted, and conflicting values within one document are not semantically reconciled.
- Applicability: Establishes unit/label provenance, precedence and scope. Line 46 requires rebuilding the index after quantity-extraction changes.
- Counterevidence: The contract limits merged-cell inference and semantic reconciliation and does not guarantee total preference.
- Validation: Check restored numeric values and original spans, retain scope/precedence regressions, then rebuild affected stored metadata and embeddings before assessing application results.

### S4 — Recorded round-1 and round-2 repairs and validation

- URL: docs/quantity_filter_validation.md
- Retrieved: 2026-10-17
- Locator: Review round 2, lines 5–17; Review round 1, lines 21–39
- Fragment: Four quantity-cell parsing sites now share one boundary/offset reader: inherited numeric cells, explicit quantity reading, field assignment and header declarations. It removes exterior table syntax before counting and retains interior empty cells.

Rebuilding every table-bearing chunk changed zero quantity rows or documents; all 29,339 rows and their numeric/declaration source spans were retained (`artifacts/quantity_filter/review2/scope.json`). The raw boundary-pipe omission is a demonstrated regression fixture, not a claimed change to this corpus's selected budgets.

Both a column declaration `사업예산(천원)` and a preceding `(단위: 천원)` lost numeric-only cells.

The paid answers and user-reported browser acceptance below predate these review repairs. They remain historical evidence for those saved contexts, not new paid or browser acceptance of the repaired contexts.
- Applicability: Records what each repair targeted, its reported checks and the distinction between synthetic reproduction, corpus observations and historical frontend acceptance.
- Counterevidence: The report records successful affected tests and unchanged offline results. Its referenced artifact logs are unavailable as tracked evidence here and were not independently rerun.
- Validation: Report the new transition reproduction separately from corpus frequency and rerun comparisons after the final state-lifetime change.

### S5 — Previous F2 research and recorded outcome

- URL: docs/research/review-fix-quantity-filter-questions-f2-1.md
- Retrieved: 2026-10-17
- Locator: Failed fixes, lines 13–17; source fragment, lines 33–41; Result and Unresolved limits, lines 194–200
- Fragment: if "|" in line:
    quantities.extend(_implicit_cells(line, headers, declarations, default))
    if not quantities and re.search(r"[가-힣]", line):
        cells = list(re.finditer(r"[^|]+", line.strip().strip("|")))

A missed Korean-labelled row can also enter header replacement because no quantity was recovered.

The shortened-total regression uses '계 | 200,000' at EOF, without boundary pipes.

These are recorded implementation observations; this page remains a draft, not a verified finding or shared rule.
- Applicability: Shows that the header-replacement condition already existed when cycle 1 diagnosed inconsistent cell counting. Its recorded outcome addresses boundary formatting rather than declaration survival across quantity-free data rows.
- Counterevidence: This is an earlier draft and implementation record, not independent historical execution evidence.
- Validation: Confirm that the new regression reaches the surviving header-replacement condition rather than the previously repaired cell-count mechanism.

### S6 — W3C Model for Tabular Data and Metadata on the Web

- URL: https://www.w3.org/TR/tabular-data-model/
- Retrieved: 2026-10-17
- Locator: Section 1, Introduction; sections 4.3 Columns, 4.5 Cells and 6.4 Parsing Cells
- Fragment: Each row contains the same number of cells (although some of these cells may be empty)
- Applicability: Supports distinguishing missing cell values from column structure. The model separately represents column metadata and cell values, including empty and configured null values.
- Counterevidence: This is a general tabular model, not an algorithm for identifying Korean RFP headers. Defaults and configured null markers affect cell interpretation; it does not declare '-' universally null or specify thousand-won inheritance.
- Validation: Insertion of a row with an absent quantity must leave later cells attached to their established column schema without inventing a value for the absent cell.

### S7 — GitHub Flavored Markdown specification

- URL: https://github.github.com/gfm/#tables-extension-
- Retrieved: 2026-10-17
- Locator: Section 4.10 Tables; lines 2991–2993, 3067 and 3126–3139
- Fragment: Each row consists of cells containing arbitrary text

The table is broken at the first empty line, or beginning of another block-level structure:
- Applicability: For recognized GFM tables, body-row membership does not depend on extracting a number. Header/delimiter structure and block boundaries provide structural evidence.
- Counterevidence: GFM requires matching header/delimiter widths. It pads shortened body rows rather than remapping values into a unique declared column. The repository also supports delimiter-free extracted tables and uses its own boundary heuristic, so GFM is a comparison rather than a replacement contract.
- Validation: Retain a proper delimiter-row reproduction while preserving the repository's delimiter-free and shortened-total regressions.

### S8 — Quantity usability and document-value selection

- URL: rag/retrieval/quantity_filter.py
- Retrieved: 2026-10-17
- Locator: Lines 135–167
- Fragment: def _usable(row):
    return ((not row["bound"] or row["declared_cap"]) and not row["illustrative"]
            and not row["estimated_price"]
            and row["unit"] and row["phrase"] and (row["unit"] != "원" or row["value"] > 1))

if row["doc_id"] not in chosen or row["similarity"] > chosen[row["doc_id"]]["similarity"]:
    chosen[row["doc_id"]] = row

chosen = _document_values(eligible, unit)
matched = [r for r in chosen.values() if condition.accepts(r["value"])]
- Applicability: Explains why losing a value or its accepted field can change matches, and why another surviving row may become the document value.
- Counterevidence: A restored row must still pass usability, unit and similarity requirements. Selection does not automatically prefer totals or larger amounts.
- Validation: Use controlled similarities to isolate the restored row's effect on document selection and threshold matching.

### S9 — Stored quantity-index construction

- URL: rag/retrieval/indexing.py
- Retrieved: 2026-10-17
- Locator: Lines 151–157, build_quantity_index
- Fragment: rows = quantity_rows(chunks)
phrases = list(dict.fromkeys(r["phrase"] for r in rows))
vectors = embedder.encode(phrases, progress=True) if phrases else np.empty((0, 0), dtype=np.float32)
write_jsonl(rows, out_dir / "quantities.jsonl")
(out_dir / "quantity_phrases.json").write_text(json.dumps(phrases, ensure_ascii=False), encoding="utf-8")
np.save(out_dir / "quantity_vectors.npy", vectors)
- Applicability: Extraction and phrase changes feed persisted rows, phrase names and embeddings. Source changes alone do not update previously built artifacts.
- Counterevidence: An extraction-level reproduction does not require rebuilding the full dense/BM25 index. Application-level conclusions require compatible quantity artifacts.
- Validation: Build isolated compatible quantity artifacts after the final change and compare selected values, matches and exclusions.

## Claims

- C1 (interpretation; S2, S3): The repository's declared-unit contract requires stable column units, field identity and provenance within the supported table scope, while retaining explicit-unit precedence and bounded shortened-row recovery.
- C2 (source; S4, S5): Recorded repairs first restored unit inheritance, then corrected exterior-pipe cell counting; the original shortened-total regression did not cover the latter representation.
- C3 (source; S1, S5): The current and previously recorded extraction loops replace headers on a Korean pipe row whenever no quantities were extracted; the current loop also replaces declarations there.
- C4 (interpretation; S1): The exact round-3 input is statically predicted to erase the thousand-won declaration at the dash row and omit the following bare 100. This session did not execute that prediction.
- C5 (interpretation; S2, S4): Current formatting and interior-empty-cell fixtures do not exercise a wholly quantity-free Korean data row followed by another numeric row, leaving the destructive state transition uncovered.
- C6 (source; S6, S7): The W3C model permits empty cells within stable columns; GFM permits textual body cells and defines structural table boundaries. Neither specifies this repository's Korean unit inheritance or flattened-row recovery.
- C7 (interpretation; S1, S3, S6, S7): A bounded repair should distinguish schema transitions from quantity extraction, preserving paired headers and declarations across ordinary quantity-free data rows while retaining legitimate initialization, declaration changes and boundary resets.
- C8 (interpretation; S1, S8): Default declarations and explicit cell units can mask missing numeric output without protecting field identity, so successful amount extraction alone does not prove preservation.
- C9 (interpretation; S3, S8): Missing or mislabelled metadata can alter document selection and threshold matching, subject to usability and similarity requirements; restoring extraction does not guarantee total preference.
- C10 (source; S3, S9): Quantity extraction produces persisted rows, distinct phrases and phrase vectors, and the README requires rebuilding after extraction changes.
- C11 (interpretation; S1, S2, S8, S9): A before/after insertion experiment, source-span checks, scoped boundary controls and controlled downstream similarities can distinguish schema-lifetime repair from numeric recovery that merely masks field corruption.
- C12 (interpretation; S4, S5): Prior pages record successful checks and unchanged corpus results but explicitly limit their evidentiary scope; those records do not independently demonstrate the new missing-value transition.

## Core theory

Tabular structure and individual cell values are separate concerns. The W3C model allows empty cells while retaining their column positions and property relationships. GFM permits textual body cells and defines table boundaries structurally; a row need not contain a number to remain a data row. These sources support preserving an established schema when a value is absent. They do not prescribe this repository's Korean unit recognition, dash semantics or flattened-table recovery heuristic. [C6]

## Applicability

Change the decision that mutates the active table schema in _chunk_rows(), rather than adding another special case to numeric parsing. Within an established table, an ordinary data row without quantities must preserve both headers and declarations. Initialize headers at table entry and replace an established schema only on positively identified header/declaration evidence or a supported table boundary. Preserve the existing generic-header, default-unit, explicit-unit, shortened-total and source-offset behavior. A guard that preserves declarations but still overwrites headers would leave field identity corrupted; a dash-only exception would leave the same defect for other nonnumeric values. This is a proposed bounded repair, whose exact header predicate must be validated against existing supported inputs. [C7, C8]

## Hypothesis

The remaining cause is conflation of extraction success with structural row identity. At quantity_metadata.py:218–221, 'no quantities and some Korean text' authorizes replacement of both headers and declarations. For the reported input, the initial header establishes a thousand-won declaration in column 1; the delimiter leaves it intact; 'A 사업 | -' produces no quantities and replaces it with declarations [None, None]. The subsequent bare 100 has neither an explicit unit nor an inherited declaration, so it disappears. The same destructive condition existed before the boundary repair. This is a static trace consistent with the supplied review, not an independently executed reproduction. [C3, C4]

## Counterevidence

- The shared _cells() reader addresses the earlier exterior-pipe/newline mechanism, and the current regression now covers that representation. Round 3 is a different remaining failure in schema lifetime, not evidence that the boundary repair had no effect. [C2, C5]
- A preceding '(단위: 천원)' can mask the missing amount because default survives a pipe-row header replacement. Nevertheless, the column label can still be overwritten, so preserving only numeric output would be insufficient. [C8]
- Explicit cell units use a separate extraction path and can still produce rows after the destructive transition. Their inherited field label may nevertheless be lost; extraction and downstream usability must be checked separately. [C8, C9]
- Header replacement currently helps discover headers in delimiter-free extracted text. Freezing every header forever could obstruct a genuine later declaration. Preservation must remain scoped to the active table, with existing boundary resets and legitimate declaration changes retained. [C7]
- No runtime checks were available in this read-only session. The reported exact failure is supported by the current control flow, but the proposed replacement policy has not been executed against the corpus. [C4, C11]

## Alternatives

- Blacklist '-' or enumerate missing-value strings: this repairs one spelling while leaving the structural error for empty, textual or otherwise unparseable cells. Preserve the schema independently of extraction success. [C7]
- Keep declarations but continue replacing headers: this may recover the amount while attaching the wrong field, affecting similarity and usability. Headers and declarations form one schema for this purpose. [C7, C8, C9]
- Allow replacement whenever there is no column declaration: default-unit tables still need stable field labels, and generic explicit-unit tables also use header inheritance. This condition does not express table identity. [C7, C8]
- Change Kiwi tokenization or currency scaling: existing positive regressions already exercise those mechanisms. The failing transition removes the declaration before multiplication could occur. [C4, C5]
- Revert or broaden cell-boundary parsing: the current shared reader addresses the previous counting defect; the reported row has an ordinary two-column structure. Changing it does not repair schema replacement. [C3, C5]
- Choose the largest value, sum components or prefer totals: these change selection policy and cannot restore missing extraction metadata. Existing selection uses field similarity, with the first row retained on equal similarity. [C9]
- Adopt a full Markdown parser: the repository deliberately supports delimiter-free flattened tables and unique-declared-column recovery. Strict GFM alone would not reproduce those domain behaviors, and a parser replacement is unnecessary to test this state-lifetime hypothesis. [C1, C6, C7]

## Experiment

Before editing, run quantity_rows on the exact review input and on the baseline with 'A 사업 | -\n' removed. Record headers, declarations, default and quantities after each line. The hypothesis predicts that the baseline emits 100000 won, while the reported input replaces the schema at the dash row and omits that amount. Refute or revise the hypothesis if the declaration remains intact or the omission occurs elsewhere. After the fix, inserting a quantity-free data row must leave the later value, unit, phrase and declaration identity equivalent to the baseline; absolute numeric offsets should move with the inserted text, while every stored span still slices its own original text. The dash row must emit no invented amount. Cover the demonstrated transition with '-' and an empty value, including insertion after a valid numeric data row. Retain boundary-pipe/LF/CRLF coverage through the existing fixtures rather than duplicating their whole matrix. Include a default-unit case to detect label corruption, an explicit-unit case to retain precedence, and a following table after the supported boundary to detect leaked units or labels. For downstream confirmation, use a controlled accepted field similarity and a 100000-won threshold: the restored row must supply the selected value and matching document. Rebuild quantity rows and phrase embeddings in isolated artifacts, then report any changed values, matches and exclusions for the existing offline corpus checks. Run the affected tests and repository-required checks in the implementation session. No tests or corpus rebuilds were executed here. [C11, C10]

## Result

Observed at parent `51629a7` before editing: the baseline produced 100000 won with the original budget label and declaration; inserting `A 사업 | -` changed headers to the data cells and declarations to `[None, None]`, leaving no later quantity. The line-by-line trace is `artifacts/quantity_review3_before.log`. The fix is committed with this draft under the unique subject `retrieval: preserve table schemas and whole-project modifiers`. `tests/test_quantity_filter.py::test_quantity_free_data_rows_preserve_schema_and_later_values` covers 18 insertion cases across dash/empty/text, before/after-valid placement and column/default/explicit units, preserving label/unit/declaration identity and shifted source spans. `test_schema_changes_need_a_declaration_or_table_boundary_and_explicit_units_win` checks supported changes/reset and precedence; `test_numeric_key_value_rows_are_not_headers` and `test_declared_headers_do_not_require_every_label_to_have_noun_only_pos_tags` guard two observed issues in intermediate implementations. The final affected ten-file run passed 740 tests with 12 warnings in 54.12 seconds (`artifacts/quantity_review3_checked_cleanup_gate.log`). The checked census rebuilt all 13,627 table-bearing chunks: 34 inherited rows added, 14 removed, 372 existing subjects changed, across 185 chunks/79 documents, yielding 29359 rows. No currency amount was added or removed; 21 currency-row labels changed. All numeric/declaration source spans were checked. Counts are implementation observations, not claims that every heuristic unit or field is semantically correct. Evidence: `artifacts/quantity_filter/review3_checked/scope.json`, `scope_summary.json`, and `artifacts/quantity_review3_scope_checked_summary.log`. This page remains a draft, not a verified finding or shared rule.

The final checked search run re-embedded 11,934 distinct phrases after the last production change. Four actual queries retained 61/30/44/1 projects, 10/45/10/10 exclusions and every chosen value; both dev reruns preserved all 60 context-ID sequences. Socket connections were blocked and the usage CSV remained byte-identical (`artifacts/quantity_review3_offline_checked.log`). The active index was not replaced. These local observations do not supersede independent review.

## Unresolved limits

This remains a draft diagnosis and experiment record. Research-time historical source limitations still apply; local execution observations are now recorded above and in the validation report. Within an established table, the bounded repair requires a positive unit declaration to replace the schema; adjacent unmarked generic headers in delimiter-free text remain ambiguous and require a supported boundary. POS-based unit reading does not establish semantic correctness of every inferred unit. General merged cells, escaped pipes, reconciliation of conflicting budgets and guaranteed total preference remain outside this repair. [C1, C6, C7, C9, C12]
