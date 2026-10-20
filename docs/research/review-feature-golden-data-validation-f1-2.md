# Review research — F1, cycle 2

집계 결과와 측정 조건은 Git에 보관하고, 원시 질문·정답·근거·OCR 전사와 레코드별 내보내기는 무시된 로컬 `artifacts/`에 보관한다.

복원 출처: 정리 전 `artifacts/review-round2/originals/` 또는 `d7d1682^`. 아래 수치와 검증 기록은 당시 실행의 역사적 관측이며 이번 작업에서 재측정한 결과가 아니다.

Draft research before the fix of review round 3 of PR #26, written 2026-10-14. It is not a verified fact or a shared rule: the review reads it with the fix.

## Problem

F1: a comparison candidate reaches auto_validated and is released while it attributes the answer to a different entity than the independent validator does, or states the opposite conclusion. The invariant is the comparison topic's requirement (configs/topics/comparison.json 'requires': the answer states each entity's value or content), which only same_answer can enforce: check_structure looks for structure.entities in the evidence, not in the answer. At 6c334d7 same_answer('A안이 B안보다 예산이 많다', 'B안', ['A안','B안']) is True because an independent answer without quantities goes straight to substring containment (validation.py:184-185) before any entity check. _not_copied (validation.py:333-334) then exempts the bare entity name, so the candidate reaches auto_validated.

Trigger: repeat, rounds 2, 3.

- [P1] [P1] golden_pipeline/validation.py:185 — Text-only comparison answers bypass attribution and can approve the opposite conclusion

## Failed fixes

- b49e0b0 (round-1 fix): replaced the unordered set of (value, unit) pairs with facts() carrying the subject words before each value, and rejected only when the candidate's subject held a word belonging to another expected value. Accept stayed the default, so unrelated subjects (C안/D안) and missing subjects ('1억원, 2억원') still passed (round 2).
- a41c9fb (round-2 fix): _attributed required the value's own subject words, False on foreign words, None otherwise. But it all sat behind `if not rivals: return True`, so a single value per unit or a swap across units passed without any subject check (cycle-1 research, confirmed there by running it).
- 2bfd9a3 (cycle-1 research fix): comparison items use _anchored, which reads the entity name written before every value. It closed every numeric case, but it sits after `if not expected: return _contains(...)`, so text-only independent answers never reach it. The cycle-1 page itself listed this ('an independent answer B안 is contained in the candidate A안이 B안보다 크다') as an unresolved limit outside F1's numeric scope, and the fix left it open. _anchored also checks only the name before each value, not the conclusion words, and not whether the independent answer covers every entity. So the fix narrowed the accepting paths but did not make True require the topic's invariant.

## Sources

### S1 — golden_pipeline/validation.py at 6c334d7

- URL: golden_pipeline/validation.py
- Retrieved: 2026-10-14
- Locator: same_answer lines 176-193; _anchored 196-213; _not_copied 328-335; _verdict 251-268
- Fragment: expected = facts(independent)
    if not expected:
        return _contains(_norm(text), _norm(independent))
    found = facts(text)
    if entities:
        results = [_anchored(fact, found, entities) for fact in expected]
- Applicability: The text-only exit returns before the entity check, and _anchored checks only the entity name before each value. Together these are the True exits for comparison items.
- Counterevidence: The numeric entity path does return False for every swap the earlier reviews named.
- Validation: After the fix, the entities branch returns True only when the independent answer covers every entity once and each value is anchored. The text-only branch returns None when contained.

### S2 — tests/golden/test_validation.py

- URL: tests/golden/test_validation.py
- Retrieved: 2026-10-14
- Locator: lines 145-152 and 230-245
- Fragment: ("B안이 2억원으로 더 많다", "auto_validated"), ("A안이 2억원으로 더 많다", "rejected"), ("2억원인 안이 더 많다", "held") ... Validator({"*": verdict("B안이 2억원으로 더 많다")})
- Applicability: Every comparison test has an independent answer with a quantity. None covers a text-only verdict, which is why the bypass went untested. The first row depends on an independent answer that covers only B안.
- Counterevidence: none given
- Validation: Add the reviewer's text-only repro and the opposite-conclusion row. Update the first row's verdict or its expected state.

### S3 — golden_pipeline/configs/topics/comparison.json

- URL: golden_pipeline/configs/topics/comparison.json
- Retrieved: 2026-10-14
- Locator: requires; structure.entities
- Fragment: "requires": "둘 이상의 대상(항목, 안, 기관, 단계 등)을 견주는 질문. 답은 각 대상의 값이나 내용을 함께 밝힌다." ... "entities": "견주는 대상 이름 2개 이상의 리스트. 각각 근거에 적힌 그대로"
- Applicability: States the positive condition for True: each entity's value is stated. Supplies the names to check coverage against.
- Counterevidence: '값이나 내용' includes text content, which this numeric-anchored rule cannot verify. Such answers go to held.
- Validation: The coverage check reads structure.entities.

### S4 — Review research — F1, cycle 1

- URL: docs/research/review-feature-golden-data-validation-f1-1.md
- Retrieved: 2026-10-14
- Locator: Unresolved limits
- Fragment: Answers without numbers keep the substring rule (_contains): an independent answer 'B안' is contained in the candidate 'A안이 B안보다 크다', the same attribution flaw outside F1's numeric scope.
- Applicability: Shows the text-only bypass was known before fix 2bfd9a3 and was scoped out, not missed.
- Counterevidence: none given
- Validation: This cycle's fix must not scope any comparison True exit out.

### S5 — McCoy, Pavlick & Linzen (2019), Right for the Wrong Reasons: Diagnosing Syntactic Heuristics in Natural Language Inference

- URL: https://ar5iv.labs.arxiv.org/html/1902.01007
- Retrieved: 2026-10-14
- Locator: Table 1; Section 1 paragraph introducing HANS
- Fragment: Subsequence: "Assume that a premise entails all of its contiguous subsequences." Example: "The doctor near the actor danced." Lexical overlap: "Assume that a premise entails all hypotheses constructed from words in the premise." Example: "The doctor was paid by the actor." These heuristics: "they are not valid inference strategies because they fail on many examples." (Stated for NLI models trained on MNLI; the failing HANS cases are non-entailment cases.)
- Applicability: same_answer's text-only exit treats 'the candidate contains the independent answer' as 'the candidate asserts it', which is the subsequence heuristic. 'A안이 B안보다 예산이 많다' contains 'B안' without asserting B안 is larger.
- Counterevidence: The paper diagnoses learned NLI models, not rule-based answer checks, and the heuristics also hold on many examples, so carrying it over is an analogy about what surface containment can show.
- Validation: Text-only comparison candidates that contain the independent answer but are not identical return None, not True.

### S6 — Saltzer & Schroeder (1975), The Protection of Information in Computer Systems

- URL: https://www.cs.virginia.edu/~evans/cs551/saltzer/
- Retrieved: 2026-10-14
- Locator: Section I.A.3, design principle (b) Fail-safe defaults
- Fragment: "Base access decisions on permission rather than exclusion." (Fetch returned the rest paraphrased: a mistake in a permission-based mechanism fails by refusing, which is quickly noticed; a mistake in an exclusion-based mechanism fails by allowing, which may go unnoticed. Stated for access control.)
- Applicability: Every True exit of same_answer for comparison items is exclusion-based, and each review found one more allowing path. Granting True only on the topic invariant makes remaining flaws fail toward held.
- Counterevidence: It is an access-control principle, so this is an analogy. Here failing safe costs human review time.
- Validation: Any comparison case the predicate cannot establish returns None and the item is held.

### S7 — Kamalloo, Dziri, Clarke & Rafiei (ACL 2023), Evaluating Open-Domain Question Answering in the Era of Large Language Models

- URL: https://ar5iv.labs.arxiv.org/html/2305.06984
- Retrieved: 2026-10-14
- Locator: Section 3 (lexical matching definitions); Abstract; Section 4.4
- Fragment: EM: "A candidate answer is deemed correct iff it can be found in the set of gold answers." Lexical matching "fails completely when a plausible candidate answer does not appear in the list of gold answers"; more than 50% of lexical matching failures came from semantically equivalent answers; "the automated methods are prone to misjudging hallucinated long answers" (about BEM and InstructGPT-eval, not lexical matching).
- Applicability: Argues against two directions: stricter surface matching holds many correct answers (the cost of the fix), and an automated LLM judge is not a safe replacement for long answers (why the LLM-judge alternative is not taken first).
- Counterevidence: Studied open-domain QA in English, not RFP comparison answers in Korean, and focuses on false negatives rather than the false positives at issue here.
- Validation: Measure the held rate of comparison candidates after the fix, and keep human confirmation as the release path for held items.

## Claims

- C1 (source; S1): At 6c334d7, same_answer returns _contains(...) for an independent answer with no quantities before any entity check, so comparison entities are never consulted for text-only answers.
- C2 (interpretation; S4, S1): The cycle-1 fix knowingly left the text-only path open; the fix failed by scope, not by a bug in _anchored.
- C3 (interpretation; S1, S2): _anchored compares only the entity name before each value. The same values with the opposite conclusion ('더 적다' vs '더 많다') should return True, and no test covers it.
- C4 (interpretation; S3, S6): For comparison items, True should be granted only when the topic invariant is shown: the independent answer gives a value for every entity in structure.entities, and each is anchored to the same entity in the candidate. Otherwise None, or False on a proven mismatch.
- C5 (source; S5): Treating containment of a string as entailment (the subsequence heuristic) is not a valid inference strategy and fails on many examples.
- C6 (interpretation; S2): The fix changes one existing expectation: the comparison test row whose independent answer covers only B안 moves from auto_validated to held, unless its verdict is changed to cover both entities.
- C7 (source; S6): A mechanism that decides by exclusion fails by allowing; one that decides by permission fails by refusing, which is noticed.
- C8 (source; S7): Surface matching often rejects semantically equivalent answers, and automated judges misjudge hallucinated long answers, so the fix will raise the held rate and an LLM judge is not the first choice.

## Core theory

Two sources. (1) McCoy, Pavlick & Linzen (HANS) list the subsequence heuristic, 'Assume that a premise entails all of its contiguous subsequences', and the lexical overlap heuristic, and state that 'they are not valid inference strategies because they fail on many examples' (e.g. 'The doctor near the actor danced' does not entail 'The actor danced'). Containment of the independent answer in the candidate is exactly that heuristic. (2) Saltzer & Schroeder's fail-safe defaults: 'Base access decisions on permission rather than exclusion.' A flaw in a permission-based mechanism fails by refusing, which gets noticed. A flaw in an exclusion-based one fails by allowing, which can go unnoticed.

## Applicability

same_answer is the auto-validation gate for comparison candidates (_same_as_independent, and the None→held step in _verdict, validation.py:261-265). Its text-only exit (line 185) applies the subsequence heuristic: 'A안이 B안보다 예산이 많다' contains 'B안' but does not assert that B안 has the larger budget. Its numeric exit (_anchored, lines 196-213) asserts only the name in front of each value. Both are exclusion mechanisms (accept unless a mismatch is found), so each flaw surfaces as an accepted wrong answer, one review at a time. comparison.json already states the positive condition (each entity's value is stated) and structure.entities gives the names, so True can be granted only when that condition is shown. Scope: only the entities branch of same_answer, which only comparison items take via _entities(). numeric, table, condition and multi_hop keep their current rule.

## Hypothesis

All three fixes repaired the branch a reviewer named, inside a predicate whose exits default to True. Substring containment, and a name in front of each value, are surface checks that cannot see the relation a comparison answer asserts (which entity is chosen, in which direction). So each round leaves another True exit for comparison items: first unordered values, then single-value units, now text-only answers. A predicted next one is the same values with the opposite conclusion: 'B안이 2억원으로 더 적다' against 'B안이 2억원으로 더 많다' returns True at 6c334d7, read from the code but not run. The fix that holds makes True for comparison items require the topic invariant positively: the independent answer names every entity in structure.entities exactly once, against its own value, and each of those values is anchored to the same entity in the candidate. False stays where a value is found only under other entities, or where text is not contained at all. Every other case, including all text-only comparison answers that are contained but not identical, returns None (held).

## Counterevidence

- Not executed here (no shell). The reviewer's repro is quoted from round 3. The 'B안이 2억원으로 더 적다' sibling is read from the code: facts() gives the window 'B안이' for 2억원 in both texts, so _anchored returns True.
- The coverage rule changes an existing expectation: test_comparison_values_must_belong_to_the_same_entity_as_in_the_independent_answer has 'B안이 2억원으로 더 많다' → auto_validated against the verdict 'B안이 2억원으로 더 많다', which covers only B안. Under the rule it becomes held. Either that row becomes held, or the test validator answers 'A안 1억원, B안 2억원'.
- Kamalloo et al. 2023 find lexical matching mostly errs the other way (rejecting correct answers: 'more than 50%' of failures were semantically equivalent answers). Stricter surface rules will hold many correct comparison answers, and the human queue grows.
- The round-3 reviewer asks for 'establish the same conclusion or go to held'. A reviewer could read held-on-everything-text-only as too blunt, but it explicitly satisfies 'or go to held'.

## Alternatives

- Text-only comparison: True when the candidate names only the entity the independent answer names. Smaller held cost, but it still uses the subsequence heuristic: 'B안은 예산이 많지 않다' would pass. Rejected as another accept-default patch.
- Equality after canonicalizing value notation (candidate == independent once each quantity is rewritten as its (value, unit)). Precise, but it needs span bookkeeping in facts() and holds nearly every sentence-form candidate. Not needed when the coverage rule exists.
- An LLM entailment judge or structured {entity: value} validator output. Strongest binding, but it changes VERDICT_FIELDS, validator.txt and the prompt SHA, adds calls, and Kamalloo et al. report automated judges misjudge hallucinated long answers. Too large for this finding.
- Optional companion, not a substitute: add one line to validator.txt asking comparison answers to give each entity's value before it (as prompts/A/comparison.txt already asks the generator). That lowers the held rate under the coverage rule. It changes the prompt SHA, which manifests already record.

## Experiment

Before editing, on 6c334d7: (a) the reviewer's repro (comparison candidate 'A안이 B안보다 예산이 많다', validator verdict('B안')) → predicted auto_validated. (b) same_answer('B안이 2억원으로 더 적다', 'B안이 2억원으로 더 많다', ['A안','B안']) → predicted True. (c) same_answer('B안은 예산이 많지 않다', 'B안', ['A안','B안']) → predicted True. After the fix: (a) held, (b) None, (c) None. same_answer('A안은 1억원, B안은 2억원', 'A안 1억원, B안 2억원', ['A안','B안']) → True. 'A안은 2억원, B안은 1억원' against the same → False. Every row of test_comparison_attribution_is_read_from_the_entity_names_for_every_value keeps its result, since that independent answer covers both entities. All non-comparison rows of test_same_answer_compares_after_value_and_unit_normalization and test_each_check_sends_the_candidate_to_its_state keep theirs, because they pass no entities. Then grep same_answer and _anchored callers to confirm only the entities branch changed. _single_unit_verdict calls without entities and is unaffected.

## Result

Draft observation, not a verification. Before the edit, on c9ff991 (code identical to 6c334d7):
- (b) `same_answer('B안이 2억원으로 더 적다', 'B안이 2억원으로 더 많다', ['A안','B안'])` returned True.
- (c) `same_answer('B안은 예산이 많지 않다', 'B안', ['A안','B안'])` returned True.
- `same_answer('A안이 B안보다 예산이 많다', 'B안', ['A안','B안'])` returned True.
- (a) `test_comparison_values_must_belong_to_the_same_entity_as_in_the_independent_answer`, rewritten so each row carries its own validator answer, failed on the reviewer's row (validator `B안`) and on the `더 적다` row: both reached auto_validated where held was expected.

After the fix (`_comparison_same`, in the commit that adds this result), comparison items return True only in two cases: the texts are equal, or the validator's answer names every entity exactly once before its own value and each of those values is anchored to the same name in the candidate.
- (a) is held, (b) is None and (c) is None.
- `same_answer('A안은 1억원, B안은 2억원', 'A안 1억원, B안 2억원', ['A안','B안'])` is True, and the swapped candidate is False.
- Every row of `test_comparison_attribution_is_read_from_the_entity_names_for_every_value` keeps its result. So does every row of `test_same_answer_compares_after_value_and_unit_normalization` and `test_each_check_sends_the_candidate_to_its_state`, none of which pass entities.
- tests/golden/test_validation.py: 55 passed.
- The grep confirms that only the two answer-comparison sites pass entities: the None-to-held step in `_verdict` and `_same_as_independent`. `_single_unit_verdict` and `_not_copied` call without entities and are unchanged.
- `validator.txt` gained one line asking the validator to give each compared entity its value, to lower the held rate. The held rate itself was not measured.

## Unresolved limits

Candidates may add claims beyond the independent answer (e.g. a correct per-entity list followed by a contradicting sentence). same_answer checks only that the independent answer is covered, for every topic, and this fix does not change that. Entity names are still matched as substrings ('B안' inside 'AB안'), and only the name before a value counts ('2억원(A안)' gives held). Text-only content comparisons ('A안은 클라우드, B안은 온프레미스') will all be held unless identical. How much the human queue grows is unmeasured.
