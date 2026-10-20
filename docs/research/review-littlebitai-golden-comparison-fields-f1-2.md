# Review research — F1, cycle 2

Draft research before the fix of review round 3 of PR #76, written 2026-10-20. It is not a verified fact or a shared rule: the review reads it with the fix.

## Problem

F1: a comparison item must be rejected exactly when its entities are field labels of one requirement record (고유번호 · 명칭 · 분류 · 정의 · 세부 내용 · 응낙수준 …), and admitted when it compares same-kind things, including row names of a detail table inside a requirement chunk, whatever the values look like (3초/1초, bare 42/103, or text). `_field_comparison` (golden_pipeline/validation.py:664-685) runs at screening (:242), release/rename (:310) and verdict (:603), so a false positive drops a valid item and writes a wrong invalid_comparison failure record, and a false negative lets a field comparison into the release. Round 3 shows the current rule rejects '목표경영 | 42' vs '과제관리 | 103' once requirement_ids=['QUR-003'] is attached, because quantities() drops bare numbers and the unit intersection is empty.

Trigger: repeat, rounds 2, 3.

- [P1] [P1] golden_pipeline/validation.py:676 — 단위 없는 수치나 글 값의 정상 비교를 요구사항 칸 비교로 오거절합니다

## Failed fixes

- fbf9c96: rejected when every evidence ref has requirement_ids and each entity sits next to its value ('대상 | 값'). Detail tables inside requirement chunks have the same 'name | value' layout, so '실명 인증 | 3초' vs '로그인 | 1초' was rejected (round 1). Layout is shared by attribute/value records and listings, so it cannot separate them.
- f0b918d: added a closed list REQUIREMENT_FIELD = '요구사항\S*|산출정보|응낙수준|정의'. '요구사항\S*' matched real requirement names such as '요구사항 A' vs '요구사항 B', which the prompt (prompts/A/comparison.txt:9) allows as '요구사항 둘' (round 2). The list also missed bare 고유번호 · 명칭 · 분류 · 세부 내용. A label list drifts both ways because labels vary per document.
- d3f129f: replaced the list with 'the values share no quantity unit'. That moved the test from the entity to the values. Valid comparisons of bare numbers ('42' vs '103') or text values have no shared unit and are rejected (round 3). Cycle 1 recorded this limit, but there was no positive example in local data to catch it. Value type does not say whether the entity is a field: a field record can hold same-unit values, and a detail listing can hold unitless or text values.
- Common cause: all three judged field-ness from the single item and its cited units. Nothing in one item's text marks an attribute label apart from an instance name.

## Sources

### S1 — Extracting Structured Data from Web Pages (Arasu & Garcia-Molina, SIGMOD 2003)

- URL: https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/extract.pdf
- Retrieved: 2026-10-20
- Locator: definitions of occurrence vector, equivalence class and LFEQ
- Fragment: occurrence vector: "the vector of occurrence frequencies of the dtoken in the input pages"; equivalence class: "the maximal set of dtokens having the same occurrence vector"; "EXALG retains only the equivalence classes that are large and whose tokens occur in a large number of input pages. We call such equivalence classes LFEQs." (quoted via search extraction of the PDF; the full text, including its handling of tokens with several roles, was not readable to me)
- Applicability: Requirement chunks of one document are pages from one form. Field labels are tokens that occur in a large number of those pages; detail-table entity names occur in one.
- Counterevidence: ExAlg works on HTML tokens of many pages from one site and relies on enough input pages. A document with one or two requirement records gives too few pages.
- Validation: In the data run, field labels should show near-full record coverage within a document and detail names coverage of one record.

### S2 — ExAlg overview (slide summary)

- URL: https://www.slideshare.net/slideshow/exalg-overview/3589649
- Retrieved: 2026-10-20
- Locator: slides on template vs data tokens
- Fragment: Per the search summary: nothing in the raw text syntactically marks template text apart from data, so tokens are grouped by occurrence counts across pages; a large class with wide page support usually comes from the template, while data tokens tend to appear rarely. (Student presentation, secondary; 'usually' and 'tend to' are its own hedges.)
- Applicability: Explains why all three fixes failed: each looked for a syntactic mark (layout, label spelling, value type) inside one item.
- Counterevidence: Secondary and informal; wording paraphrased by the search tool.
- Validation: Same as S1.

### S3 — golden_pipeline/validation.py _comparison_rule / _field_comparison

- URL: golden_pipeline/validation.py
- Retrieved: 2026-10-20
- Locator: lines 655-685; callers 242, 310, 603
- Fragment: if set.intersection(*({unit for _, unit in quantities(text)} for text in texts)): return False … return all((name, value) in pairs …) after `if not all(ref["requirement_ids"] …): return False`; quantities() skips a number when `not unit` (line 428).
- Applicability: Bare numbers and text values produce empty unit sets, so the intersection is empty and requirement evidence with adjacent cells is rejected: round 3's '42 vs 103'.
- Counterevidence: none given
- Validation: After the fix, lines 674-677 no longer read values; field-ness comes from the label set.

### S4 — tests/golden/test_improvement.py field-comparison cases

- URL: tests/golden/test_improvement.py
- Retrieved: 2026-10-20
- Locator: lines 232-250
- Fragment: Admitted cases: (['QUR-003'], 실명 인증/로그인, 3초/1초), (['QUR-003'], 요구사항 A/B, 3초/5초), ([], 목표경영/과제관리, 42/103). The bare-number case is only tested with requirement_ids=[].
- Applicability: Each round's test covered only the counterexample just raised, so the next one (unitless numbers under a requirement) stayed untested.
- Counterevidence: none given
- Validation: Add 목표경영/과제관리 and a text-valued detail case under ['QUR-003']; expect None.

### S5 — golden_pipeline/prompts/A/comparison.txt

- URL: golden_pipeline/prompts/A/comparison.txt
- Retrieved: 2026-10-20
- Locator: lines 9-12, 15
- Fragment: "견주는 대상은 같은 종류의 것들이다 (차수 둘 · 요구사항 둘 · 장비 둘 · 평가 항목 둘처럼) … 한 대상의 서로 다른 칸 · 항목 이름(요구사항 고유번호 · 명칭 · 분류 · 정의 · 세부 내용 같은 것)을 대상으로 삼지 않는다." and values are "금액 · 기간 · 수량 · 날짜 · 비율 · 기준 같은 것".
- Applicability: The contract forbids field names as entities; it does not restrict value type. '기준' values are text, so a value-type rule contradicts the prompt.
- Counterevidence: The prompt is guidance, not evidence of what items contain.
- Validation: The rule after the fix tests the entity (form label), matching line 10.

### S6 — Cycle-1 research page for F1

- URL: docs/research/review-littlebitai-golden-comparison-fields-f1-1.md
- Retrieved: 2026-10-20
- Locator: Alternatives (corpus vocabulary) and Result
- Fragment: "Learn field labels from the corpus: a key cell that recurs as a left-hand label across chunks of two or more distinct requirement_ids … is a schema field; detail-table entities appear under one requirement only." Result: 856 items, 224 rejected, all hand-read as field comparisons; "same-kind values that are text, or bare numbers without a unit … would be rejected; none occur in the local outputs."
- Applicability: Gives the regression set (224 field comparisons) and records that cycle 1 knew the value-type limit; the label-recurrence route was its second choice.
- Counterevidence: Its label list is from hand reading, not a measured recurrence count.
- Validation: All 224 must stay rejected under the recurrence rule.

## Claims

- C1 (source; S1): In template extraction, template tokens are those in large equivalence classes whose tokens occur in a large number of input pages; data tokens vary across pages.
- C2 (source; S2): Template text and data are not syntactically distinguishable within one page; occurrence across pages separates them.
- C3 (interpretation; S1, S6): Requirement field labels behave as template tokens of the per-document requirement form (they recur across requirement records), and detail-table or requirement names behave as data; recurrence across requirement_ids is therefore the signal for 'field label'.
- C4 (interpretation; S3, S5): The current rule rejects bare-number and text-valued comparisons in requirement evidence because quantities() yields no unit for them, contradicting the prompt contract that allows '기준'-type values.
- C5 (interpretation; S4, S5, S6): Each fix was validated only against the counterexample just raised, so the next reviewer counterexample was untested; the fix needs a test matrix of entity kind (field label / detail name / requirement name) × value kind (unit / bare number / text) under requirement evidence.

## Core theory

In template-based extraction (Arasu & Garcia-Molina, ExAlg, SIGMOD 2003), template text and data cannot be told apart syntactically within one page. They are separated by occurrence across pages: tokens with the same occurrence vector form equivalence classes, and the large, frequently occurring classes are taken as template. Data tokens vary from page to page. Web-table taxonomies (cycle 1, S2) call one record's table an attribute/value table and a detail table a listing; both use 'name | value' rows, which is why single-item layout fails.

## Applicability

Each v12 requirement chunk is one page generated from a per-document form. The form's labels recur across the document's requirement chunks (requirement_ids gives the record identity), while detail-table row names and requirement names do not. This applies in _field_comparison: replace lines 674-677 (the quantities intersection) with a membership test against the document's recurring-label set. The set comes from the evidence run that the plan pins (plan → evidence_run → outputs/evidence/<run>/units.jsonl, keyed by doc_sha), and it must reach all three rule_reason call sites (:242, :310, :603). The rejection message and improvement code stay the same.

## Hypothesis

Field labels are template text of the requirement-record form. The same label recurs as the left cell of a 'label | value' pair in most requirement records of a document (고유번호, 명칭, 분류, 정의, 세부 내용, 응낙수준, 산출정보 …). Detail-table entities and requirement names (실명 인증, 로그인, 요구사항 A, 목표경영) are data and appear under one record. So the rule should: keep fix 1's preconditions (all evidence has requirement_ids and each entity is adjacent to its value), drop the value-unit test, and reject only when every entity, whitespace- and ordinal-normalized ('② 요구사항 고유번호' → '요구사항고유번호'), is a recurring label of the document's requirement records. A recurring label is a left cell found in units of at least 2 distinct requirement_ids and at least half of the document's requirement_ids, computed from the evidence run's units.jsonl.

## Counterevidence

- A document with only one requirement record has no recurrence inside it, so field comparisons there would pass. A corpus-wide fallback (a label recurring across many documents' requirement chunks) covers this, but it risks catching common detail names such as '로그인'.
- A detail-table row name could recur across most requirement records of one document (e.g. every requirement has a '처리 시간' row). The rule would then call it a field. That is arguably right: it is a field of the form.
- Some RFPs may not render requirement records as 'label | value' cells in v12 chunks (e.g. a header row plus one value row). Then the adjacency precondition does not hold either way, so the gap is unchanged rather than new.
- I did not measure label recurrence on the v12 package. It is not in this worktree, and I cannot run code. Recurrence is assumed from the 13 hand-read cycle-1 rejections, whose labels are standard form fields.

## Alternatives

- Extend or tighten REQUIREMENT_FIELD again: this is f0b918d's failure mode, a closed list that over- and under-matches. Rejected.
- Keep the unit test and add 'or the values are bare numbers / same-kind text': it stays a value-type heuristic, and the reviewer can always build a counterexample, such as same-kind text values in a detail table or a field record with same-unit values. Rejected.
- Admit any entity whose name is not in the cited record's first rows (position heuristic): the order of form fields versus detail tables is not guaranteed in v12 chunks. Not first.
- Drop the rule and rely on the generator prompt (comparison.txt:10): generation produced 224 such items even with that instruction. Rejected.

## Experiment

Offline, no API calls. (1) Unit: extend tests/golden/test_improvement.py:232 with a small field vocabulary and the reviewer's three cases under requirement_ids=['QUR-003']: '실명 인증 3초 / 로그인 1초', '요구사항 A 3초 / 요구사항 B 5초', '목표경영 42 / 과제관리 103', plus one text-valued detail case. All must return None. The two field cases ('요구사항 분류'/'응낙수준', '고유번호'/'분    류') must return invalid_comparison. Under d3f129f the '목표경영 42' case with QUR-003 fails, which confirms the bug. (2) Data: build the recurring-label set per document from the evidence run's units.jsonl and record the distribution of 'requirement records per label' (aggregate counts only). Then re-run the rule over the 856 local comparison items from cycle 1. The hypothesis holds if all 224 items the current rule rejects stay rejected (they were hand-read as field comparisons), no item comparing non-label names is rejected, and the label-frequency distribution is bimodal: form labels near 100% of a document's records, other left cells near one record. Recurring labels without a clean split, or any of the 224 lost, refute it.

## Result

Draft observation, not verified beyond what is listed here. The fix is in the commit that carries this page, on top of 98a5df7 ("golden: 칸 비교는 그 문서 요구사항 양식의 칸 이름을 견줄 때만 거절한다"). `_field_comparison` keeps fix 1's preconditions (every evidence ref has requirement_ids, each entity is next to its value) and drops the value-unit test. It rejects when any entity, whitespace-removed, is a form label of the cited document: a left cell found in requirement chunks of at least 2 records and at least `LABEL_SHARE` = 0.5 of that document's records. The labels are counted from `evidence.PACKAGE`'s `corpus/chunks.jsonl` (`_form_labels`, cached per package). The local evidence run predates unit text, so it could not be used. Ordinal normalization was not needed. (1) tests/golden/test_improvement.py::test_a_comparison_between_fields_of_one_requirement_is_ruled_out now runs all six cases under requirement_ids ['QUR-003'] against a two-record synthetic package. Under d3f129f the bare-number detail case ('목표경영 42 / 과제관리 103') and the text-valued detail case failed, which confirms the finding. With the fix, all six pass, and so does test_a_rename_drops_what_a_newer_rule_rules_out_and_records_it_as_a_failure. (2) Data, aggregates only: 89 documents in the v12 package have requirement chunks, with a median of 56 records per document. Over the 5,127 (document, left cell) pairs in documents with at least 4 records, the share of records per cell is bimodal: 4,456 fall in the lowest decile and 460 in the highest, with 211 in between. Requiring every entity to be a label kept 214 of the 224 at share 0.5 and 219 at 0.3. In each miss, one entity was a full-recurrence label and the other an optional field. Requiring any entity to be a label keeps 224 of 224 at both thresholds. The real `_field_comparison` over the 856 local items rejects the same 224 and admits the other 632, and release final2 still rejects 38 of 184. A plan-only variant (recurrence counted from plan bundle units) kept only 206 of 224, because some documents have fewer than 2 requirement records in the plan, so it was not used. Gate: 1448 passed. Limits: a document with a single requirement record yields no labels, so field comparisons there pass. The rule reads the current package, so a run pinned to an older package is screened with the current package's labels, matched by document SHA.

## Unresolved limits

The ExAlg wording comes from search-result quotes of the PDF; I could not render the PDF itself. Whether v12 requirement chunks repeat field labels in every record has not been measured. The thresholds (≥2 records and ≥50% of a document's records) are a starting guess that the data run must set. Documents with a single requirement record need a decision: corpus fallback or accept the gap. Local outputs have no confirmed admitted detail-table comparison, so positives rest on synthetic tests.
