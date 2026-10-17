# Corrected-index paid validation

On 2026-10-17 the person approved four questions through GPT-6 LUNA rewriting and answering, plus a separate final frontend pair. The eight agent calls completed for $0.0090984 against an estimate of $0.02568245. They exposed defects, so this run is not an acceptance pass.

## Execution and usage

The run used commit `69bacea`, empty history, `low` reasoning, rewrite output limit 2,048 and answer output limit 8,192, including reasoning. Each rewritten query was searched against the active corrected index before generation. No paid judges, OCR, embedding API or evaluation test split ran.

The evidence writer initially could not serialize the read-only candidate mappings after saving the first rewrite response. It was corrected to copy those mappings for serialization. The saved response was reused: there were exactly eight paid usage rows, with no duplicate rewrite charge.

| Case | Rewrite cost | Answer cost | Paid call time | Table rows | Exclusions |
| --- | ---: | ---: | ---: | ---: | ---: |
| Budget ≥100 million won and overviews | $0.0000793 | $0.0035685 | 26.397 s | 61 | 10 |
| Duration ≥6 months | $0.0000631 | $0.0021402 | 14.599 s | 31 | 45 |
| Budget 100–500 million won | $0.0000809 | $0.0028921 | 19.215 s | 44 | 10 |
| Largest budget | $0.0000499 | $0.0002244 | 4.121 s | 1 | 9 |
| Total | $0.0002732 | $0.0088252 | 64.332 s | 137 | |

Usage: 47,219 input tokens, zero cached input, 8,753 output tokens including 860 reasoning tokens. Times sum paid calls only; local index loading, retrieval and the resumed writer are excluded. Actual usage was 64.6% below the approved estimate.

Recorded USD uses actual response tokens and the approved configured rates; it is not invoice reconciliation.

## Observations

All four answers contained a Markdown table, an overview column, citations for every supplied row, the supplied original numeric amounts and the supplied exclusion count. These structural observations do not establish that the selected field or overview is correct.

| Check | Finding |
| --- | --- |
| Project order and chosen numeric values after rewriting | Preserved for all four questions |
| Exclusions after rewriting | Preserved for the first three. Adding `규모` changed the maximum query's field phrase and reduced exclusions from 10 to 9, although its winning project and value stayed the same |
| Exact original text | One budget row changed the equivalent currency glyph `￦` to `₩`. Numeric value was unchanged; the literal-copy audit failed that row |
| Main-question overviews | Rows 3, 11, 20 and 23 said `문서에 없음`. Inspection found country background, a reference PDM and a blank proposal form among the excerpts; the HDIMS excerpt contained a work schedule that the answer did not summarize |
| Range overview faithfulness | The university operations row described the supplied blank form rather than the project. It was grounded in the excerpt but did not answer the requested project overview |
| Duration field correctness | Six rows used warranty or maintenance periods instead of the project period, including a 12-month warranty in a project whose labelled implementation period is 24 months within a ceiling. One further row used a historical research phase. The answer itself warned about these mismatches |

Manual inspection established these failures. The deterministic audit checks row count, citations, original value strings, overview headers and exclusion text; it is not a semantic faithfulness score. No paid judge score is claimed. Original answers remain unchanged as evidence.

## Local corrections after this run

The local repair removes the filler `규모` from quantity-field questions, prefers substantive introductions before unrelated value-source excerpts, rejects blank form candidates, and clarifies literal value copying in the existing filter prompt rule. Metadata now preserves subjects inside table cells instead of generic column headers and adds project context only to monetary labels. Explicit labelled quantity ceilings can be used for project periods as well as budgets; relative eligibility clauses remain excluded. Explicit reference blocks are not used as a project's own value.

These corrections add no API calls. They require fresh offline verification and an approved answer recheck on the resulting contexts. The four paid rewrite responses can be reused for that recheck, including the `규모` case, without purchasing new rewrites. Final frontend acceptance remains outstanding.

The final network-blocked replay passes with 61/30/44/1 projects and 10/45/10/10 exclusions. All four stored rewrites preserve the selected project order and exclusions. All 30 recovered amounts and all 88 previously chosen budget values are unchanged. The seven observed wrong period rows are absent or replaced, including the 24-month implementation period replacing the 12-month warranty. Introductions are recognized at section headings, with purpose/background preferred and mixed TOC prefixes trimmed; incidental mentions of project contents in requirement paragraphs do not qualify as introductions. The earlier 60 stored dev reruns retain every context ID sequence; subsequent excerpt-only changes do not enter their agency/document-prefixed route.

Final inputs and checks are in `artifacts/quantity_filter/post_paid_final/` and `artifacts/quantity_post_paid_final2.log`. Fresh paid generation evidence for these final contexts is still pending approval under the [updated complete estimate](quantity_filter_estimate.md).

Final local checks: 92 quantity-filter tests passed; the full gate passed with 1,182 tests and 12 warnings in 407.29 seconds (`artifacts/quantity_validation_repair_gate5.log`); `ruff check .` passed; `CLAUDE.md` and `AGENTS.md` are byte-identical. The test cleanup audit retained the current regressions and found no obsolete cases, superseded duplicates, or expired skips/xfails. The frontend was restarted with the final metadata, and both its page and backend OpenAPI endpoint returned HTTP 200 without an answer call.

Full evidence is under `artifacts/quantity_filter/repaired_paid_validation/`: `manifest.json` records prompts, settings, commit, index hashes and the starting usage row; `calls.jsonl` and `usage_summary.json` record all eight calls; per-case retrieval, context and answer files preserve the inputs and outputs. `audit.json` contains structural checks, and `overview_review_pairs.json` pairs rows with their supplied excerpts.
