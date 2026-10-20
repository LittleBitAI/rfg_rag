# Review research — F1, cycle 1

Draft research before the fix of review round 2 of PR #76, written 2026-10-20. It is not a verified fact or a shared rule: the review reads it with the fix.

## Problem

A golden comparison item is supposed to weigh two or more things of the same kind on one shared property and pick one. Some generated items instead compare different fields of a single requirement record (for example '요구사항 분류' vs '응낙수준': which one is '필수'?). Their values match the evidence, so the independent validator passes them, yet an RFP reader would never ask them. The invariant: a comparison item that reaches release must not have the fields (attributes) of one requirement record as its entities. `_comparison_rule` / `_field_comparison` in golden_pipeline/validation.py:657-685 is the only deterministic guard, and it must reject every such item at validation and again at release, while still admitting legitimate comparisons, including detail-table rows inside a requirement chunk ('실명 인증 | 3초' vs '로그인 | 1초').

Trigger: repeat, rounds 1, 2.

- [P1] [P1] golden_pipeline/validation.py:47 — 정상적인 요구사항 이름도 칸 이름으로 분류해 요구사항끼리의 비교를 오거절합니다

## Failed fixes

- fbf9c96 pulled the same-requirement field comparison out into a rule keyed on structure: every evidence ref carries requirement_ids and each entity sits next to its value as neighbouring cells ('대상 | 값'). That held for the observed item but is too broad. Detail tables inside a requirement chunk have exactly the same 'name | value' adjacency, so legitimate comparisons of two functions' response times were rejected as well. Adjacency describes the key-value layout of requirement chunks; it does not tell an attribute name apart from an entity name.
- f0b918d narrowed the rule by also requiring every entity to fully match a hand-written vocabulary, REQUIREMENT_FIELD = r'요구사항\S*|산出정보|응낙수준|정의' (validation.py:47). That brought detail tables back but turned the rule into a closed list. The list covers neither bare '분류', '명칭' and '고유번호' (named in the rule's own rejection message at validation.py:662) nor '세부 내용' (named in the generator prompt at prompts/A/comparison.txt:10). The same goes for labels other RFPs use ('요구사항명', '상세설명', '제약사항', '수용여부', '비고'). Any field comparison whose labels fall outside the list passes again, which is why the finding comes back. Both fixes guessed at 'is this a field name' from surface features of the one observed bad item, rather than checking the property that makes a comparison valid.

## Sources

### S1 — HotpotQA: A Dataset for Diverse, Explainable Multi-hop Question Answering (Yang et al., 2018)

- URL: https://arxiv.org/html/1809.09600
- Retrieved: 2026-10-20
- Locator: Section 2 'Comparison Questions'; Section 4 'Multi-hop Reasoning Types'
- Fragment: "comparing two entities from the same category usually results in interesting multi-hop questions"; "we manually curate 42 lists of similar entities"; "we randomly sample two paragraphs from the same list"; comparison questions "require the system to understand the properties in question about the two entities"; "answering these questions usually requires arithmetic comparison" ("usually", so not always arithmetic).
- Applicability: Defines a valid comparison as same-category entities weighed on one property. A field comparison breaks this because its entities are attributes of one record, not same-category entities. That supports testing 'shared property', not 'label in a list'.
- Counterevidence: HotpotQA is Wikipedia QA, not RFP tables, and says 'usually' arithmetic. Same-kind text-valued comparisons exist (e.g. nationality), so a quantity-only criterion is stricter than the source.
- Validation: The fix holds if the existing same-kind cases (3초/1초, 42/103) stay admitted and the newly added field-label cases outside REQUIREMENT_FIELD are rejected, in the test at tests/golden/test_improvement.py:232 and in the offline re-run over local outputs.

### S2 — Web Table Extraction, Retrieval and Augmentation: A Survey (Zhang & Balog), summarising Crestan & Pantel 2011

- URL: https://arxiv.org/html/2002.00207
- Retrieved: 2026-10-20
- Locator: Section 2.2 'Types of Tables'
- Fragment: "Listings refer to tables consisting a series of entities with a single attribute." "In terms of layout direction, these are further classified as vertical listings or horizontal listings." "Attribute/value tables describe a certain entity along with its attributes."
- Applicability: A v12 requirement chunk is an attribute/value table (one requirement, its fields). A detail table inside it is a vertical listing. Both use 'name | value' rows, which explains why adjacency alone (fix 1) could not separate them.
- Counterevidence: This is a secondary summary of the taxonomy, and real RFP chunks can mix both types in one chunk with no marker between them.
- Validation: In the offline re-run, check that every item the new rule rejects cites a requirement-record attribute/value block and every item it admits compares rows of a listing. A counterexample in either direction refutes the mapping.

### S3 — golden_pipeline/validation.py: _comparison_rule and _field_comparison

- URL: golden_pipeline/validation.py
- Retrieved: 2026-10-20
- Locator: lines 47, 657-685
- Fragment: REQUIREMENT_FIELD = re.compile(r"요구사항\S*|산출정보|응낙수준|정의"); the rejection message reads "칸 비교: 요구사항 표의 서로 다른 칸 이름(고유번호 · 명칭 · 분류 등)을 대상으로 견줍니다"; _field_comparison returns False unless all evidence refs have requirement_ids AND every entity fullmatches REQUIREMENT_FIELD AND each (entity, value) pair is a pair of neighbouring cells.
- Applicability: This is the code both fixes changed. The list does not match bare 고유번호/명칭/분류, even though its own message names them, so any field comparison with those labels passes.
- Counterevidence: If generated entities always carry the '요구사항' prefix ('요구사항 분류'), the gap would be mostly theoretical. That needs checking against local outputs.
- Validation: Call rule_reason with entities ['분류', '명칭'] on requirement evidence with adjacent values. It returns None now and must return the 칸 비교 reason after the fix.

### S4 — golden_pipeline/prompts/A/comparison.txt

- URL: golden_pipeline/prompts/A/comparison.txt
- Retrieved: 2026-10-20
- Locator: lines 9-12
- Fragment: "견주는 대상은 같은 종류의 것들이다 … 대상마다 같은 성질의 값을 견준다. 한 대상의 서로 다른 칸 · 항목 이름(요구사항 고유번호 · 명칭 · 분류 · 정의 · 세부 내용 같은 것)을 대상으로 삼지 않는다." and, as the fallback, "그 요구사항의 세부 내용에 나오는 대상 둘 (예: 두 기능의 처리 시간)을 견준다."
- Applicability: The generator's own contract is 'same kind, same property', which is the criterion proposed for the rule. Its list includes 세부 내용, which REQUIREMENT_FIELD lacks. The prompt also steers generation toward detail-table comparisons, which the rule must admit.
- Counterevidence: The prompt is guidance to an LLM, not proof of what items actually contain.
- Validation: After the fix, the rule's criterion and the prompt's wording should state the same test (same-property values), with no separate label list to keep in sync. Check by reading both side by side in the diff.

### S5 — tests/golden/test_improvement.py: test_a_comparison_between_fields_of_one_requirement_is_ruled_out

- URL: tests/golden/test_improvement.py
- Retrieved: 2026-10-20
- Locator: lines 232-246
- Fragment: Three cases: (['QUR-003'], ['요구사항 분류', '응낙수준'], …) -> 'invalid_comparison'; (['QUR-003'], ['실명 인증', '로그인'], {'3초', '1초'}) -> None; ([], ['목표경영', '과제관리'], {'42', '103'}) -> None.
- Applicability: Covers only labels inside the current list, so it cannot detect the closed-list gap. The two admitted cases both have same-unit quantity values, consistent with the proposed criterion.
- Counterevidence: There is no case with same-kind text values inside requirement evidence, so the proposed rule's over-rejection risk is untested.
- Validation: Add one out-of-list field-label case (expected invalid_comparison) next to the existing three. All four must pass with the new rule.

## Claims

- C1 (source; S1): A valid comparison question pairs entities of the same category and compares them on one property, usually by arithmetic comparison.
- C2 (source; S2): Attribute/value tables describe one entity with its attributes, while listings hold many entities with a single attribute, and both can be laid out as name-value rows.
- C3 (interpretation; S1, S2): Fields of one requirement record are attributes of a single entity, so comparing them breaks the same-category, same-property condition; detail-table rows with same-unit values satisfy it.
- C4 (interpretation; S3, S4, S5): The current REQUIREMENT_FIELD list omits field labels that the rule's own message and the generator prompt name (bare 고유번호, 명칭, 분류, and 세부 내용), so field comparisons using them pass the guard; the existing test cannot detect this.
- C5 (interpretation; S4, S5): Replacing the label list with a same-property test on the values (shared quantity unit, via validation.quantities), behind fix 1's structural precondition, matches the prompt's contract and keeps the existing admitted cases admitted.

## Core theory

HotpotQA's comparison questions are built by pairing entities 'from the same category', sampled from curated 'lists of similar entities', and answering them requires understanding 'the properties in question about the two entities', often by 'arithmetic comparison'. Web-table taxonomies (Crestan & Pantel 2011, as summarised in the survey) separate 'Attribute/value tables', which 'describe a certain entity along with its attributes', from 'Listings', which are 'a series of entities with a single attribute'. A valid comparison draws from the listing reading (many entities, one attribute). A field comparison reads an attribute/value table as if it were a listing, treating one entity's attribute names as entities.

## Applicability

A v12 requirement chunk is an attribute/value table: one requirement (requirement_ids non-empty) with rows like '요구사항 고유번호 | SFR-001', '요구사항 분류 | 품질 요구사항', '응낙수준 | 필수'. A detail table inside it ('실명 인증 | 3초', '로그인 | 1초') is a vertical listing: several entities, one attribute (time). Both have the same 'name | value' adjacency, which is why fix 1 could not tell them apart. They differ in whether the values share one attribute, which shows up here as values with the same unit. This applies in validation.py `_field_comparison` (called from `_comparison_rule` -> `_topic_rule` -> `rule_reason`, at validation.py:244, :312 and :605, i.e. screening, release and verdict). It also needs the comparison prompt (prompts/A/comparison.txt:9-12) to stay consistent with whatever list or criterion the rule uses.

## Hypothesis

The root cause is that the rule tries to decide 'is this entity a field name' with a lexical or layout heuristic. Neither layout nor a name list separates attributes of one record from instances of one type. What separates them is whether the compared values share a property. Fields of one record have heterogeneous values (a category label vs a compliance level vs an ID). Legitimate comparisons, including detail-table rows, have values of the same kind (both durations, both counts, both amounts, both dates). A rule that keeps fix 1's structural precondition (requirement evidence + 'name | value' adjacency) and replaces the REQUIREMENT_FIELD list with 'the values do not share a comparable quantity/unit (via the existing validation.quantities)' would reject field comparisons whatever their labels, and admit '3초 vs 1초' and '42 vs 103'.

## Counterevidence

- Some legitimate comparisons have non-quantity values of the same kind, such as two requirements' 응낙수준 ('필수' vs '선택') or two items' 기준 text. A 'no shared unit' test inside requirement evidence could reject them. Mitigation: the structural precondition (adjacency within requirement evidence) still applies, and comparisons across two requirements normally use requirement IDs or names as entities, not field labels, so this may be rare. It has to be measured, not assumed.
- Detail tables with text values ('실명 인증 | 공인인증서' vs '로그인 | 비밀번호') would also be rejected. Arguably they are not comparisons in HotpotQA's sense anyway, since nothing orders them, but that is a judgment call the reviewer may not share.
- The review text for this round was not available to me. The refused finding might instead concern the other half of f0b918d (replacement split keeping the new release's records, split.py:60-93). If so, this page is about the wrong finding.

## Alternatives

- Extend REQUIREMENT_FIELD with the missing labels (분류, 명칭, 고유번호, 세부내용, …). That is the smallest diff, but it repeats fix 2's failure mode: a closed list that drifts from the prompt, the message and new documents. Not first.
- Learn field labels from the corpus: a key cell that recurs as a left-hand label across chunks of two or more distinct requirement_ids in the v12 package is a schema field; detail-table entities appear under one requirement only. This fits the attribute/value theory better and handles text values, but rule_reason receives only the item's planned units, so it needs the corpus vocabulary loaded and passed in. More plumbing, so second choice if the value-type test over-rejects.
- Rely on the generator prompt alone (comparison.txt:10 already forbids field-name entities). Generation still produced such items, and the guard exists precisely because the prompt is not enough. Rejected.

## Experiment

Offline, with no API calls: (1) add cases to tests/golden/test_improvement.py:232 where entities are field labels outside the current list ('세부 내용' vs '요구사항 명칭', bare '분류' vs '명칭') with heterogeneous text values. Under the current code rule_reason returns None, which confirms the gap. Under the proposed value-type rule they return invalid_comparison, while the existing '실명 인증 3초 / 로그인 1초' and '목표경영 42 / 과제관리 103' cases still return None. (2) Run rule_reason over every comparison item in the local golden_pipeline/outputs runs and releases with the old and the proposed rule. List the items whose verdict changes and read each one by hand. The hypothesis holds if every newly rejected item compares fields of one record and no legitimate same-kind comparison is newly rejected; any such loss refutes the value-type criterion and points to the corpus-vocabulary alternative.

## Result

Draft observation, not verified beyond what is listed here. The fix is in the commit that carries this page, on top of 740f58b ("golden: 칸 비교는 값끼리 같은 단위가 없을 때만 거절한다"). It drops REQUIREMENT_FIELD; `_field_comparison` now returns true when the evidence is requirement evidence, every entity sits next to its value, and the values share no quantity unit (`validation.quantities`). (1) In tests/golden/test_improvement.py::test_a_comparison_between_fields_of_one_requirement_is_ruled_out, the old code failed two new cases: bare labels '고유번호' / '분    류' returned None instead of invalid_comparison (the gap this page predicted), and the reviewer's '요구사항 A | 3초' / '요구사항 B | 5초' was rejected. The new rule passes all five cases, including '실명 인증 3초 / 로그인 1초' and the non-requirement '목표경영 42 / 과제관리 103'. (2) Offline re-run over 856 unique local comparison items (all runs' accepted/candidates plus releases), with no API calls: the old rule rejected 211 and the new one 224. All 211 stay rejected. I read the 13 newly rejected by hand, and every one compares fields of one requirement record ('정의' vs '세부 내용' ×6, '고유번호' vs '명 칭' ×2, '분 류' vs '명 칭', '고유번호' vs '요구사항 분류', '고유번호' vs '분 류', '② 요구사항 고유번호' vs '⑤ 산출정보', '요구사항 분류' vs '세부 내용'). No item with adjacent values of the same unit exists in the data, so the measured set loses nothing legitimate, but it also has no positive example of an admitted detail-table comparison. The release final2 still rejects the same 38 of 184. Gate: 1447 passed. Limits that remain: same-kind values that are text, or bare numbers without a unit, in requirement evidence with adjacent cells would be rejected; none occur in the local outputs.

## Unresolved limits

The exact wording of the refused finding was not visible to me in this turn. This rests on the branch's last two commits and the code they touched. I have not counted how often legitimate non-quantity comparisons occur inside requirement evidence. The web-table taxonomy quote comes from a secondary survey, not the Crestan & Pantel paper itself.
