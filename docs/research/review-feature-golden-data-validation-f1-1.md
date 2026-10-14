# Review research — F1, cycle 1

Draft research before the fix of review round 2 of PR #26, written 2026-10-14. It is not a verified fact or a shared rule: the review reads it with the fix.

## Problem

F1: when an answer holds several values, the candidate must attach each value to the same subject the independent answer does; otherwise a comparison candidate with the right numbers on the wrong subjects reaches auto_validated and is released. same_answer (golden_pipeline/validation.py:172) is the only gate that compares the candidate's attribution, because check_structure only checks that structure.entities appear in the evidence, not in the answer.

Trigger: repeat, rounds 1, 2.

- [P1] [P1] golden_pipeline/validation.py:181 — Matching quantities still pass with incorrect subjects

## Failed fixes

- Round 1 fix (b49e0b0): replaced the unordered set of (value, unit) pairs with facts() that also returns the subject words in front of each value. A value then failed only when the candidate's subject held a word from the other expected value's subject. That is a pass-unless-proven-swapped rule, so subjects that are unrelated (C안/D안) or missing ('1억원, 2억원') still passed, which round 2 reported.
- Round 2 fix (a41c9fb): _attributed now requires the value's own words (own) to be in the candidate's subject, returns False when every occurrence carries a foreign word, and returns None (held) otherwise. It closes both round-2 counterexamples (tests at test_validation.py:138-139). But the whole subject check is still behind `if not rivals: return True` (validation.py:200-201): when the independent answer has only one value of a unit, the subject is never compared. So 'A안이 2억원으로 더 많다' against the independent 'B안이 2억원으로 더 많다' should still return True, and so should swaps across units ('B안 1억원, A안 12개월' against 'A안 1억원, B안 12개월'). Neither fix changed the default outcome, which is still pass.

## Sources

### S1 — golden_pipeline/validation.py (a41c9fb)

- URL: golden_pipeline/validation.py
- Retrieved: 2026-10-14
- Locator: _attributed, lines 188-206; same_answer 172-185; _verdict 219-236
- Fragment: rivals = [other for other in expected if other is not fact and other[0][1] == pair[1]]
    if not rivals:
        return True
- Applicability: The only gate on subject–value attribution; returns True with no subject check whenever there is no same-unit rival.
- Counterevidence: Inside the rival branch it does hold unrelated or missing subjects, as round 2 asked.
- Validation: New test rows for the single-value and cross-unit cases must not return True.

### S2 — tests/golden/test_validation.py

- URL: tests/golden/test_validation.py
- Retrieved: 2026-10-14
- Locator: test_same_answer_compares_after_value_and_unit_normalization, lines 127-142
- Fragment: ("C안은 2억원, D안은 1억원", "A안 2억원, B안 1억원", None),
    ("2억원, 1억원", "A안 2억원, B안 1억원", None),
- Applicability: Shows that every attribution test has two same-unit values; none has a single value per unit.
- Counterevidence: none given
- Validation: Add the missing rows.

### S3 — golden_pipeline/configs/topics/comparison.json

- URL: golden_pipeline/configs/topics/comparison.json
- Retrieved: 2026-10-14
- Locator: requires, structure.entities
- Fragment: "requires": "둘 이상의 대상(항목, 안, 기관, 단계 등)을 견주는 질문. 답은 각 대상의 값이나 내용을 함께 밝힌다." … "entities": "견주는 대상 이름 2개 이상의 리스트. 각각 근거에 적힌 그대로"
- Applicability: The invariant (each entity's value is stated) and the known entity names to anchor attribution on.
- Counterevidence: Entities are 'as written in the evidence'; answers may write them differently, which yields held.
- Validation: The entity-anchored check reads these names.

### S4 — Relational triple extraction scoring (Wei et al., A Novel Cascade Binary Tagging Framework for Relational Triple Extraction)

- URL: https://ar5iv.labs.arxiv.org/html/1909.03227
- Retrieved: 2026-10-14
- Locator: Section 4.1 Experimental Setting, Datasets and Evaluation Metrics
- Fragment: [an extracted relational triple] is regarded as correct only if the relation and the heads of both subject and object are all correct.
- Applicability: A value matched without its subject is not a correct fact; same_answer should score (entity, value) as one unit.
- Counterevidence: It is a scoring convention for extraction benchmarks (and uses head-token partial matching), not a rule for comparing free-text answers.
- Validation: The fix compares the entity and the value together for every expected fact.

### S5 — Saltzer & Schroeder, The Protection of Information in Computer Systems (1975)

- URL: https://www.cs.virginia.edu/~evans/cs551/saltzer/
- Retrieved: 2026-10-14
- Locator: Design principles, b) Fail-safe defaults
- Fragment: Base access decisions on permission rather than exclusion. … A design or implementation mistake in a mechanism that gives explicit permission tends to fail by refusing permission, a safe situation, since it will be quickly detected. On the other hand, a design or implementation mistake in a mechanism that explicitly excludes access tends to fail by allowing access, a failure which may go unnoticed in normal use. (Stated for access control; the fetch tool returned this paraphrased, and the wording is the paper's widely quoted text.)
- Applicability: _attributed accepts unless excluded; each review found another allowing path. Making 'same answer' require an established attribution makes flaws fail toward held.
- Counterevidence: The principle is stated for access control, so carrying it over to answer validation is an analogy. Here the cost of failing safe is a larger human-review queue.
- Validation: After the fix, any case the predicate does not understand returns None and the item is held, not auto_validated.

## Claims

- C1 (source; S1): In a41c9fb, _attributed returns True without comparing subjects whenever the independent answer has no other value with the same unit.
- C2 (interpretation; S1, S2): So a single-value comparison answer with the wrong entity, or a swap across values with different units, should still reach auto_validated, and no existing test covers those cases.
- C3 (interpretation; S3, S1): Comparison items carry the entity names in structure.entities, so attribution can be checked against known names instead of being inferred from contrast with rival values.
- C4 (source; S4): A fact counts as correct only when its subject and value match together.
- C5 (source; S5): A check that accepts unless it finds a mismatch fails by accepting; a check that accepts only on positive evidence fails by refusing, which is the safe direction here.

## Core theory

Saltzer and Schroeder's fail-safe defaults: base decisions on permission rather than exclusion. A flaw in a mechanism that grants explicit permission fails by refusing, which gets noticed; a flaw in a mechanism that excludes fails by allowing, which can go unnoticed. Relation-extraction scoring treats a fact as a bound tuple: a triple is correct only if the relation and both entities are all correct, so a value with the wrong subject counts as wrong rather than partially right.

## Applicability

_attributed is an exclusion mechanism. It returns True whenever no rival exists (validation.py:200) and, inside the rival branch, rejects only on foreign words. Its flaws therefore fail by allowing, and each review found one more allowing path. For comparison items the subjects are known in advance (structure.entities, checked against the evidence by generation._comparison), so attribution can be required directly: for each expected fact, find which entity names occur in its subject window, in the independent answer and in each candidate occurrence of the same value. Exactly the same single entity gives True, only other entities gives False, none or several gives None. Apply this regardless of rivals. Leave the current rule for other topics so numeric answers like '1억원' versus '총 사업비는 1억원' don't all become held. The call sites (_same_as_independent, the None→held step in _verdict, _single_unit_verdict, _not_copied) already treat None as held, so they need the entities passed in and nothing else.

## Hypothesis

Both fixes patched the reviewer's specific counterexample inside a predicate whose default is to accept. Attribution is inferred only by contrast with same-unit rivals in the independent answer, and anything outside that branch (a single value per unit, values with different units) passes without any subject check. A fix that holds has to require positive attribution for every value of a comparison item, anchored on the known entity names (structure.entities), with 'cannot establish' going to None (held) instead of True.

## Counterevidence

- I have not run the code. The single-value counterexample depends on Kiwi tagging '2억원으로' the same way in both texts. If the unit came out differently, the pair would fail to match and the case would return False, not True.
- a41c9fb does satisfy the two counterexamples round 2 named, and the reviewer's wording ('hold answers whose attribution cannot be established') can be read as limited to multi-value answers. A round-3 reviewer might accept it.
- Matching on entity names will hold correct answers that write a name differently from the evidence (for example 'A안' against an entity 'A안(기본형)'), or that put the subject after the value ('2억원(A안)'). That raises the human-review load; a stricter rule causes no false accepts.

## Alternatives

- Just delete `if not rivals: return True` and require the independent subject words for every value: simplest, but it also applies to numeric and table items, where the validator often adds subject words ('총 사업비는 …') the candidate leaves out. Those would all be held. Better scoped to comparison.
- Ask the validator for structured {entity: value} output and compare dictionaries: the strongest binding, but it changes validator.txt, the verdict schema (VERDICT_FIELDS) and the prompt SHA in manifests. A larger change than the finding needs.
- Keep tuning the word-set predicate (own/foreign): this is what failed twice. It keeps accept as the default.
- Treat any comparison answer with fewer than two values as held: blunt, and it holds correct 'which one is bigger' answers that name the right entity.

## Experiment

Before editing, run on a41c9fb: same_answer('A안이 2억원으로 더 많다', 'B안이 2억원으로 더 많다') and same_answer('B안은 1억원, A안은 12개월', 'A안은 1억원, B안은 12개월'). The hypothesis predicts True for both. Then run validate() with a comparison candidate (entities ['A안','B안'], answer 'A안이 2억원으로 더 많다') and a validator verdict 'B안이 2억원으로 더 많다'; the prediction is auto_validated. After the fix, the same three must give False/False/rejected, and every existing row in test_same_answer_compares_after_value_and_unit_normalization must keep its result.

## Result

Draft observation, not a verification. Before the edit, on a41c9fb: `same_answer('A안이 2억원으로 더 많다', 'B안이 2억원으로 더 많다')` and `same_answer('B안은 1억원, A안은 12개월', 'A안은 1억원, B안은 12개월')` both returned True, as predicted. The new test `test_comparison_values_must_belong_to_the_same_entity_as_in_the_independent_answer` (comparison candidate, entities ['A안','B안'], validator answer 'B안이 2억원으로 더 많다') gave auto_validated for the candidate 'A안이 2억원으로 더 많다' (predicted) and also for '2억원인 안이 더 많다'. After the fix in the commit that adds this result: comparison items now compare each value through `_anchored`, which reads the entity name written before the value in both texts. Called with entities, the two calls above return False and False. The validate() case is rejected, the unnamed candidate is held, and 'B안이 2억원으로 더 많다' stays auto_validated. `test_comparison_attribution_is_read_from_the_entity_names_for_every_value` covers the cross-unit swap (False), the correct order (True) and C안/D안 (None). Called without entities, as the experiment literally wrote them, the two calls still return True. That is intended: other topics keep the rival-word rule, per this page's Applicability section. Every existing row of `test_same_answer_compares_after_value_and_unit_normalization` keeps its result (tests/golden/test_validation.py: 51 passed).

## Unresolved limits

Not executed: the counterexamples are read from the code. Answers without numbers keep the substring rule (_contains): an independent answer 'B안' is contained in the candidate 'A안이 B안보다 크다', the same attribution flaw outside F1's numeric scope. Entity names that contain each other ('B안' inside 'AB안') would need longest-match handling. The subject window still reads only before the value.
