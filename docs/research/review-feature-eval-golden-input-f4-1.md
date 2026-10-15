# Review research — F4, cycle 1

Draft research before the fix of review round 3 of PR #48, written 2026-10-15. It is not a verified fact or a shared rule: the review reads it with the fix.

## Problem

F4 (repeat, rounds 2 and 3): the key facts for multi_hop golden rows drop answer components that the question asks for, so an answer or retrieval with only one component gets full key-fact credit. The rule it breaks: the key facts for a golden item must cover every requested answer component, and each fact must be findable on its own in a single evidence unit. Round 3 example: eval/golden/dev.jsonl:393 (multi_hop-A-fill1-r2-0061) asks for the final deliverable and four cloud activities. The loader keeps only ['실행계획서'], so _key_fact_ratio(facts, '실행계획서') == 1.

Trigger: repeat, rounds 2, 3.

- [P1] [P1] rag/validation/validation.py:53 — Whole-cell matching still discards requested multi-hop facts

## Failed fixes

- Round 1 fix (d763d41): replaced the single whole-reference-sentence fact with the context table-cell values that appear verbatim in the answer, dropping every first cell as a field label. This fixed F2 but brought in F4: a first cell can hold an answer value (DAR-002, PER-002), so requested IDs were lost.
- Round 2 fix (617bc3b): a first cell is treated as a label only when it recurs as a first cell in at least 3 documents (_field_names), and bare numbers become 'N|N<unit>' (_quantity). Rows 333, 335 and 336 were fixed, but the atomic unit stayed the whole cell: _multi_hop_key_facts keeps a value only when the whole whitespace-collapsed cell is a substring of the answer (validation.py:52-53). Row 393's 세부내용 cell holds two ◦ headings and seven ‑ items; the answer quotes four items, the whole cell is not in the answer, and all four facts are lost.
- In both rounds the guarding test (tests/test_eval_items.py:48-50) only checked precision: each surviving fact is found in the row's context. It pinned the exact rows the reviewer had named (270, 333, 335, 336, 362) and never checked that the facts cover the answer's content. So each fix passed the gate while a different row still lost requested facts.

## Sources

### S1 — Initial Nugget Evaluation Results for the TREC 2024 RAG Track with the AutoNuggetizer Framework

- URL: https://arxiv.org/html/2411.09607v1
- Retrieved: 2026-10-15
- Locator: nugget definition and scoring sections
- Fragment: Quoting Voorhees (2003): 'An information nugget was defined as a fact for which the assessor could make a binary decision'; 'nuggets manifest as short natural language phrases or sentences'; 'We aim to generate nuggets that are neither too broad nor too specific.' Scores are averages over nuggets: full support 1, partial 0.5, else 0. Caveats: automatic filtering 'usually trims a few okay nuggets and, less frequently, some vital nuggets'; hallucinations are not considered; results rest on 21 topics, and topic-level agreement with manual scores is weaker than run-level.
- Applicability: Key facts in rag/validation play the role of vital nuggets: each must be judgeable as present or absent on its own, at a grain no coarser than the facts the answer states.
- Counterevidence: Nugget assignment there is done by an LLM that judges meaning, with partial credit. The repo's matcher is literal and binary, so verbatim quotation matters more here than in the source.
- Validation: After the split, the row-393 test shows that a one-component answer ('실행계획서') no longer gets full credit, and the coverage audit shows no multi_hop row whose facts cover only a small part of its answer.

### S2 — FActScore: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text Generation (Min et al., EMNLP 2023)

- URL: https://arxiv.org/abs/2305.14251
- Retrieved: 2026-10-15
- Locator: Abstract
- Fragment: Generations 'often contain a mixture of supported and unsupported pieces of information, making binary judgments of quality inadequate'; FActScore 'breaks a generation into a series of atomic facts' and computes the percentage supported by a reliable knowledge source. The decomposition is done by an LLM and the paper's setting is biographies checked against Wikipedia.
- Applicability: A table cell that holds a bulleted list is a 'mixture' unit: the answer contains some of its items and not others, so judging the whole cell at once (keep or drop) fails the same way a binary judgment of a whole passage does.
- Counterevidence: FActScore measures precision of generated text, not recall of reference facts, and uses LLM decomposition, not rule-based splitting. It supports the granularity principle, not the specific line-split rule.
- Validation: The fix is confirmed if splitting cells into items gives facts that each match one bullet in row 393's context (_key_fact_ratio(facts, context) == 1) and the answer (== 1), while a partial answer scores below 1.

### S3 — rag/validation/validation.py at 7a71cdf

- URL: rag/validation/validation.py
- Retrieved: 2026-10-15
- Locator: _cells lines 21-24; _multi_hop_key_facts lines 47-56
- Fragment: _cells splits each evidence unit on ' | ' and _squash collapses all whitespace including newlines. _multi_hop_key_facts builds values = {cell ...} - field_names, then keeps v only if 'len(v) > 1 and v in answer and v not in question', and drops any value contained in another found value.
- Applicability: This is where the cell is fixed as the fact unit, and where newlines that mark bullet items are lost before any split could use them.
- Counterevidence: The whole-cell rule is correct for single-value cells (IDs, names, numbers), which most rows have, and the F1/F2/F3/F5 fixes rely on it. The split must reduce to the same result for single-line cells.
- Validation: The pinned rows 270, 333, 335, 336 and 362 in tests/test_eval_items.py still pass after the split, and row 393 gains the four bullet facts.

### S4 — rag/evaluation/evaluation.py key-fact matcher

- URL: rag/evaluation/evaluation.py
- Retrieved: 2026-10-15
- Locator: _fact_matches lines 154-161; _key_fact_ratio lines 164-168
- Fragment: _key_fact_ratio returns the share of facts for which any '|' alternative matches as a contiguous pattern in the canonicalised text (whitespace and commas removed, numbers and dates tokenised), unless the match is negated.
- Applicability: Each key fact must be one contiguous span in one text, so facts must be no larger than what a single evidence unit or answer states contiguously.
- Counterevidence: Removing whitespace makes matching somewhat lenient, so slightly different spacing between context and answer bullets still matches. This argues that line splitting is enough for verbatim-quoted bullets.
- Validation: _key_fact_ratio(facts[393], row['context']) == 1 and _key_fact_ratio(facts[393], row['answer']) == 1 after the change.

### S5 — tests/test_eval_items.py at 7a71cdf

- URL: tests/test_eval_items.py
- Retrieved: 2026-10-15
- Locator: test_bundled_dev_key_facts_score_the_requested_answer, lines 40-58
- Fragment: for multi_hop rows with facts: assert _key_fact_ratio(facts[n], row['context']) == 1; then pinned asserts for rows 270, 333, 335, 336, 362 only.
- Applicability: This shows why each fix passed the gate: the test checks precision of surviving facts and pins reviewer-named rows, but never checks that the facts cover the answer.
- Counterevidence: Pinned asserts did catch regressions on the named rows. The gap is only the missing coverage dimension.
- Validation: Adding the row-393 assertion makes the test fail on 7a71cdf and pass after the fix. A coverage audit run once before the fix lists the other under-covered rows.

### S6 — eval/golden/dev.jsonl line 393 (multi_hop-A-fill1-r2-0061)

- URL: eval/golden/dev.jsonl
- Retrieved: 2026-10-15
- Locator: line 393, fields answer, context, structure
- Fragment: context E2: '세부내용 | ◦ 클라우드컴퓨팅 기술 도입 방안 마련\n ‑ 클라우드 전환 로드맵 및 전략 수립\n ‑ 클라우드 보안 및 데이터 보호 정책/가이드라인 마련\n ‑ 클라우드 기반 가상 데스크톱(VDI) 및 원격 학습 환경 구축 방안\n ‑ 클라우드 거버넌스 및 운영/관리 프로세스 수립\n◦ 기존 정보시스템의 클라우드 전환 방안 마련 …'; answer quotes those four ‑ items verbatim after '1)'…'4)'; structure is {}.
- Applicability: This is the concrete case: four requested facts sit as line items in one cell, the answer quotes the items but not the whole cell, and there is no structure to fall back on.
- Counterevidence: One row is one shape. Other under-covered rows may paraphrase rather than quote, which line splitting does not fix.
- Validation: After the split, the loader's facts for this row are 실행계획서 plus the four bullet strings. That is checked by the pinned test and by _key_fact_ratio(facts, '실행계획서') == 0.2.

## Claims

- C1 (source; S1): Nugget-based RAG evaluation scores answers by atomic facts that can each be judged present or absent, and aims at a grain neither too broad nor too specific.
- C2 (source; S2): Judging a unit that mixes several facts as one unit is inadequate; the unit should be broken into atomic facts first.
- C3 (source; S3): The current multi_hop extraction keeps a context cell only when the whole whitespace-collapsed cell is a substring of the answer, and newlines are removed before any split.
- C4 (source; S4): The evaluator matches each key fact, or one of its '|' alternatives, as one contiguous pattern in the target text.
- C5 (source; S5): The guarding test checks only that surviving facts are found in the context, plus specific reviewer-named rows; it never checks that facts cover the answer.
- C6 (interpretation; S1, S2, S3, S5, S6): The fixes failed because the fact unit stayed the table cell, coarser than the bullet-level facts golden answers state, and nothing measured coverage. Splitting cells into line items, plus a coverage audit, addresses the cause rather than one row.

## Core theory

Nugget-based RAG evaluation scores an answer by the atomic facts (nuggets) a good answer must contain. Each nugget is a fact an assessor can judge as present or absent, written as a short phrase, 'neither too broad nor too specific'. FActScore makes the same argument for long-form text: a passage mixes supported and unsupported pieces, so judging the whole unit at once is inadequate, and the text should be broken into atomic facts first. A fact unit coarser than the facts the answer states makes the judgment depend on the coarse unit, not on the content.

## Applicability

Here the 'judgment' is the existing contiguous-substring matcher (rag/evaluation/evaluation.py:154-168). It can only judge facts that occur contiguously in one text. A table cell holding a bulleted list is several atomic facts, not one. Treating it as one fact makes validation either keep it (the answer must quote the whole cell) or drop it (as happens at row 393). The fix belongs in rag/validation/validation.py _cells / _multi_hop_key_facts: split each cell into its lines and bullet items before _squash removes the newlines, strip leading markers (◦, ‑ U+2011, -, ·, •, '1)'), and treat each item as a candidate value. The existing subsumption filter (validation.py:54) and the _field_names / question exclusions still apply. For row 393 this would give 실행계획서 plus the four quoted bullet items.

## Hypothesis

The fact unit is fixed to a whole table cell, while golden answers state facts at a finer grain (lines and bullet items inside a cell). Extraction goes context-cell to answer with whole-cell substring containment, so any cell the answer only partly quotes is silently dropped. With no recall or coverage check, every fix that only changes which cells are kept leaves this loss in place.

## Counterevidence

- Line or bullet splitting only helps when the answer quotes items verbatim. Answers that paraphrase a bullet, or list items inside one comma-separated line, would still lose facts. Splitting on commas would break numbers like 2,150 and names.
- The rough regex count shows only about 9 of 71 multi_hop dev rows with bullet-marked contexts. Other under-covered rows may have a different shape (part of a prose sentence quoted), which line splitting does not fix.
- Smaller units mean more short items. A short line such as a heading fragment could match the answer by accident and become a fact the question never asked for. The question-exclusion and len>1 filters limit but do not remove this risk.

## Alternatives

- Answer to context: split the answer into segments (on 'N)', ',', '.', ':') and keep each segment found in one evidence unit. This handles answer-led enumerations, but segments carry connective text ('최종 산출물은 … 이다') that never matches, so it needs trimming or longest-common-substring logic. That is more code and more heuristics than line splitting; not first.
- LLM atomic-fact decomposition (FActScore / AutoNuggetizer style): best granularity, but it costs money on the shared OpenAI key (user rule: price it and ask first), is nondeterministic, and adds a paid step to an offline loader. Not first.
- Have golden_pipeline emit a per-hop structure for multi_hop rows (row 393 has structure {}), so key facts come from structured fields as for the other topics. This is the cleanest long-term fix, but it means regenerating the release (paid, a different module). It is a follow-up.
- Exclude rows whose facts cover too little of the answer (a new _problem reason, e.g. 'key facts do not cover the answer'). Cheap and honest, and the reviewer accepted not keeping such questions. Use it as the fallback for rows still under-covered after line splitting, not instead of it, because it shrinks the dev set.

## Experiment

1) Pinned test: load eval/golden/dev.jsonl and check that the facts for row 393 contain 실행계획서 and the four quoted bullet items, and that _key_fact_ratio(facts[393], '실행계획서') < 1. It should fail on 7a71cdf and pass after the split. 2) Coverage audit over all multi_hop rows: remove from the whitespace-collapsed answer every extracted fact and every substring shared with the question, and measure the remaining Hangul/alphanumeric characters. List rows where facts cover less than about half the answer. If line splitting is the right cause, row 393 and the bullet-context rows leave that list, and what remains shows how much paraphrase-type loss is left to exclude. 3) Re-run the existing precision check (every fact found in its row's context) and the pinned rows 270/333/335/336/362, so the split does not undo the F1, F2, F3 and F5 fixes.

## Result

pending — the fix records what it observed here, with the tests and the commit.

## Unresolved limits

No shell was available, so the extraction was not re-run after reading the code. The count of 9 bullet-context rows is a rough regex estimate, and the number of rows whose answers paraphrase cell content is unknown. The coverage threshold (about half) is a judgement call, not taken from the sources. The nugget literature uses LLM or human assessors that judge meaning; this repository's matcher is literal, so the granularity argument transfers but the sources' agreement numbers do not.
