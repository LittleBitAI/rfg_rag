# Review research — F1, cycle 1

집계 결과와 측정 조건은 Git에 보관하고, 원시 질문·정답·근거·OCR 전사와 레코드별 내보내기는 무시된 로컬 `artifacts/`에 보관한다.

복원 출처: 정리 전 `artifacts/review-round2/originals/` 또는 `d7d1682^`. 아래 수치와 검증 기록은 당시 실행의 역사적 관측이며 이번 작업에서 재측정한 결과가 아니다.

Draft research before the fix of review round 2 of PR #24, written 2026-10-14. It is not a verified fact or a shared rule: the review reads it with the fix.

## Problem

F1: a numeric candidate must carry a value and unit that appear in the cited evidence (and in the answer) as one complete numeric expression: the whole number and the whole unit. golden_pipeline/generation.py `_numeric` checks this by finding `_norm(value+unit)` as a substring with `_contains`. Round 1 showed the number could be the tail of a longer number (30,000,000원 inside 130,000,000원, 2개월 inside 12개월). Round 2 shows the unit can be the start of a longer unit (`12개` inside `12개월`), so an unsupported unit reaches candidates.jsonl.

Trigger: repeat, rounds 1, 2.

- [P1] [P1] golden_pipeline/generation.py:164 — Numeric matching still accepts a different unit from the evidence

## Failed fixes

- a1c573b (original): `_numeric` checked `_norm(value+unit)` as a plain substring of the normalized answer and evidence. Removing commas makes a shorter number a substring of a longer one, so 30000000원 matched inside 130000000원.
- 18ce4bd (review 1 fix): `_contains` got `(?<!\d)(?<!\d\.)` when the quote starts with a digit and `(?!\.?\d)` when it ends with one. That closes the digit edges only. A numeric quote is value+unit, so it always ends in a unit character such as 개, 원 or %, and the end check never runs. The fix was written in the shared helper, which knows nothing about units, and the added tests covered only the digit-prefix cases the review named (30,000,000원, 2개월). No test checked a unit that is a prefix of a longer unit.

## Sources

### S1 — re — Regular expression operations (Python 3 documentation)

- URL: https://docs.python.org/3/library/re.html
- Retrieved: 2026-10-14
- Locator: Regular Expression Syntax: '|', '\b', '\w', '(?!...)'
- Fragment: As the target string is scanned, REs separated by '|' are tried from left to right. When one pattern completely matches, that branch is accepted. This means that once A matches, B will not be tested further, even if it would produce a longer overall match. In other words, the '|' operator is never greedy. / \b ... is defined as the boundary between a \w and a \W character ... The default word characters in Unicode (str) patterns are Unicode alphanumerics and the underscore, but this can be changed by using the ASCII flag. / (?!...) Matches if ... doesn't match next.
- Applicability: Hangul syllables are alphanumeric, so `\b` finds no boundary inside 12개월 or 12개월이다. Any unit alternation built for pair extraction has to list longer units first, or be sorted longest first, because '|' takes the first branch that matches.
- Counterevidence: A bug-tracker discussion found in the same search notes that the 'succeeds' check covers the rest of the pattern, so backtracking can pick a later branch when an earlier one makes the overall match fail. With nothing after the unit group this does not apply.
- Validation: With numeric.json's order (개월 before 개), pairs from '12개월이다' must yield ('12', '개월') and never ('12', '개').

### S2 — 단위를 나타내는 명사와 수 단위 띄어쓰기 (한국교육신문)

- URL: https://hangyo.com/mobile/article.html?no=60347
- Retrieved: 2026-10-14
- Locator: quotation of 한글 맞춤법 제43항 and its numeral examples
- Fragment: "단위를 나타내는 명사는 띄어 쓴다." ... "붙여 써도 의미에 혼란이 오지 않기 때문에 붙여 쓰는 것을 허용했다." Examples: 3 년(3년), 6 개월(6개월), 1 개월(1개월), 10 개(10개), 90 원(90원), 3 개년(3개년). Exception noted: when the number is written in Hangul the words are not closed up: '삼 (개)년, 육 (개)월'.
- Applicability: Explains why RFP text writes 12개월 and 130,000,000원 with no delimiter between number and unit, and why 3개년 (unit 개년) can sit next to 개 in the list. The rule's base form is spaced ('6 개월'); `_norm` removes whitespace, so both forms normalize alike.
- Counterevidence: Secondary source (newspaper column), not the National Institute of Korean Language text; the 다만 clause was not quoted verbatim.
- Validation: The fixture u1 and the v11 run text show numbers and units written together; pair extraction must accept them.

### S3 — 조사와 의존 명사 띄어쓰기 (한국교육신문)

- URL: https://hangyo.com/mobile/article.html?no=60332
- Retrieved: 2026-10-14
- Locator: 제41항 (search result summary; page not fetched)
- Fragment: 제41항 '조사는 그 앞말에 붙여 쓴다.' 예: 꽃이, 꽃마저, 꽃밖에, 꽃에서부터 ... 조사는 앞에 무슨 말이 와도 예외 없이 붙여 쓴다. Exception discussed: '같이' and '만큼' are particles (attached) or adverb/dependent noun (spaced) depending on use.
- Applicability: Particles such as 이다, 으로, 의 attach directly to the unit (12개월이다, 130,000,000원으로). So a Hangul character after a unit does not mean the unit continues, and a Hangul lookahead cannot be the boundary rule.
- Counterevidence: I read this through the search tool's summary of the page, not a fetched copy. The wording should be checked against the primary text before being cited as a rule.
- Validation: The accepted control '계약 기간은 12개월이다' with unit 개월 must still pass after the fix.

### S4 — golden_pipeline/generation.py at 18ce4bd

- URL: golden_pipeline/generation.py
- Retrieved: 2026-10-14
- Locator: _numeric lines 111-120; _contains lines 158-165
- Fragment: quote = _norm(value + unit) ... if not any(_contains(text, quote) for text in texts) ... head = r"(?<!\d)(?<!\d\.)" if quote[:1].isdigit() else "" / tail = r"(?!\.?\d)" if quote[-1:].isdigit() else ""
- Applicability: The tail lookahead exists only for quotes ending in a digit. Numeric quotes end in a unit, so the unit edge is never checked, in the answer check or the evidence check.
- Counterevidence: none given
- Validation: After the fix, `_numeric` no longer relies on `_contains` for the unit edge.

### S5 — golden_pipeline/configs/topics/numeric.json

- URL: golden_pipeline/configs/topics/numeric.json
- Retrieved: 2026-10-14
- Locator: "pattern"
- Fragment: "pattern": "\\d[\\d,.]*\\s*(원|천원|만원|억원|%|개월|년|일|시간|명|건|개|회|식|MB|GB|TB)"; used by plan.py:113-119 to choose numeric bundles.
- Applicability: An existing unit list, already pinned by plan topic_spec SHA, with 개월 ordered before 개. Reusing it means the same list chooses numeric bundles and validates them.
- Counterevidence: Missing units (개년, 년간, %p, mixed Korean number forms) are read with a shorter unit or not at all, as listed in counterevidence.
- Validation: The reviewer's case is rejected and the 12개월이다 control is accepted with the units read from this pattern.

### S6 — tests/golden/conftest.py evidence fixture

- URL: tests/golden/conftest.py
- Retrieved: 2026-10-14
- Locator: line 81, unit u1
- Fragment: ("u1", DOC_1, "사업 예산은 130,000,000원(부가세 포함)이며 계약 기간은 12개월이다.", "eligible")
- Applicability: One cited unit contains both the reviewer's repro (12개 vs 12개월) and a unit followed by a particle (12개월이다). It is the natural fixture for a negative case and an accepted control.
- Counterevidence: none given
- Validation: Both new parametrized cases use evidence ['E1'] from the existing `planned` fixture.

## Claims

- C1 (source; S4): The 18ce4bd fix checks the end of the match only when the quote ends in a digit, so a value+unit quote is never checked at its unit edge.
- C2 (source; S1): Python regex alternation takes the first branch that matches, not the longest, so a unit list must put longer units before their prefixes.
- C3 (interpretation; S1, S2, S3): In Korean text, units attach to Arabic numerals and particles attach to units, and `\b` treats Hangul as word characters. So no character-class boundary separates a longer unit from a unit plus particle.
- C4 (interpretation; S3, S6): A Hangul negative lookahead after the unit would reject the fixture's valid '12개월이다', so it cannot be the fix.
- C5 (interpretation; S2, S5): Extracting number+unit pairs with the pinned numeric spec pattern, and requiring an exact (value, unit) pair in the answer and in a cited text, enforces the whole-number and whole-unit rule for listed units.

## Core theory

Python `re` alternation tries branches left to right and is 'never greedy', so a unit list must put longer units before their prefixes (개월 before 개). Unicode `\b`/`\w` counts Hangul syllables as word characters, so `\b` sees no boundary between 개 and 월, or between 월 and a following particle. Hangul spelling article 41 attaches particles to the preceding word. Article 43 allows unit nouns to be written attached to Arabic numerals (6개월, 90원, 10개, 3개년). Together these mean a unit can be followed directly by more Hangul, either a longer unit or a particle, with no delimiter.

## Applicability

Applies to `_numeric` (generation.py:111-120), which calls `_contains(_norm(answer), quote)` and `_contains(text, quote)` for each cited text, and to the tail branch of `_contains` (generation.py:163-165), which only checks digits. The fixture evidence u1 is '사업 예산은 130,000,000원(부가세 포함)이며 계약 기간은 12개월이다.' (tests/golden/conftest.py:81). It holds both the reviewer's case (12개 vs 12개월) and the trap for a naive fix (12개월 followed by the particle 이다). The fix belongs in `_numeric` because both checks run through it. `_contains`/`_quoted` serve table, condition and comparison, which have no unit concept, so they should stay as they are.

## Hypothesis

This is not a missing lookahead in `_contains`. Substring matching on Korean text cannot tell where a unit ends. Units attach to numerals and particles attach to units, so `12개|월` (a longer unit) and `12개월|이다` (a particle) look the same to any character-class boundary. Ending a unit correctly needs a list of known units, matched longest first, applied in `_numeric` to both the answer and the evidence. The list already exists: the numeric topic spec's `pattern`, which plan building uses to choose numeric bundles and whose SHA the plan pins. The fix: extract every number+unit pair from the normalized answer and from each cited text with that pattern. Accept only when `(_norm(value), _norm(unit))` equals one extracted pair in the answer and in at least one cited text.

## Counterevidence

- The unit list is closed. numeric.json lists 원|천원|만원|억원|%|개월|년|일|시간|명|건|개|회|식|MB|GB|TB. Units outside it (개년, 년간, 일간, %p, 천만원 written as 3천만원) would either be read with a shorter unit (3개년 read as 3 + 개, 5%p read as 5 + %) or yield no pair, so the candidate is rejected. Rejection is the safe direction, but the mis-read cases (3개년 → 개, 5%p → %) would accept a wrong unit, the same class of bug.
- Korean number forms like 1억 3천만원 or 3천만원 have no pair under `\d[\d,.]*(unit)`, so candidates the current check accepts would become rejections. That loses recall, not correctness.
- Tying validation to the selection `pattern` means any later edit to that pattern changes what validation accepts. The plan pins topic_spec_sha256, and generation refuses a changed spec, so this is tracked but still a coupling.

## Alternatives

- Hangul lookahead `(?![가-힣])` after the unit: rejected. It would also reject valid evidence and answers where a particle follows (12개월이다, 130,000,000원으로). The fixture's 12개월이다 breaks it immediately.
- Unit-continuation lookahead: after the unit, reject only text that would extend it into a longer listed unit (after 개, forbid 월). Smallest diff, and particles still pass. It needs the same unit list, and it does not stop a wrong value/unit split (value '12개', unit '월' still forms 12개월). Acceptable fallback if pair extraction turns out too strict.
- Kiwi morphological analysis (kiwipiepy is already in requirements.txt and golden_pipeline may import it, just not rag/): would split number, unit and particle without a hand-written list. Not first, because nothing here confirms how Kiwi tags units like 개월, %, MB, and it adds a heavy model load to a check that is currently pure regex.
- Reuse rag/evaluation key-fact matching from PR #11 (meaning-based number/unit comparison): rejected. golden_pipeline must import nothing from rag/, and golden numeric wants the value as written, not meaning-equivalence.
- A deeper digit fix in `_contains`: rejected. The digit edges already pass the review-1 tests. The failure is at the unit edge.

## Experiment

Extend `test_numeric_candidate_without_a_value_from_evidence_is_rejected_as_type_mismatch` with ('기간은 12개이다', {'value': '12', 'unit': '개'}), the reviewer's case, which must be rejected. Add an accepted control, ('계약 기간은 12개월이다', {'value': '12', 'unit': '개월'}) with evidence ['E1'], which must land in candidates.jsonl. This control refutes any fix that rejects units followed by a particle. Optionally add {'value': '12개', 'unit': '월'} to decide whether a wrong value/unit split is rejected. Pair extraction rejects it; the lookahead fallback does not. Run the existing review-1 cases (30,000,000원, 2개월) and the 130,000,000원(부가세 포함) positive case unchanged. The hypothesis holds if the new rejection and the 12개월이다 control both pass with the change confined to `_numeric`.

## Result

Observed in the commit that adds this Result (parent `d92eceb`). Before the fix, `test_numeric_candidate_without_a_value_from_evidence_is_rejected_as_type_mismatch` failed for both new cases: `('기간은 12개이다', 12/개)` and the wrong split `('기간은 12개월이다', 12개/월)` each landed in `candidates.jsonl`. The accepted control `test_numeric_unit_followed_by_a_particle_is_accepted` (`계약 기간은 12개월이다`, 12/개월, evidence E1) already passed, as predicted. The fix follows the hypothesis: `_numeric` extracts (number, unit) pairs with the numeric spec `pattern` (`_pairs`) from the normalized answer and each cited text, and accepts only an exact `(_norm(value), _norm(unit))` pair. Both new rejections and the control pass, and the review-1 cases (30,000,000원, 2개월) and the 130,000,000원(부가세 포함) positive case pass unchanged. The change is confined to `_numeric`; the topic checks now also receive `spec` so `_numeric` can read the pattern. `_contains` stays for `_quoted` (condition, table, comparison). Full gate: `.venv\Scripts\python -m pytest -q tests` 331 passed. The unit-list limits under Counterevidence and Unresolved limits still hold and were not tested.

## Unresolved limits

Not executed: I had no shell, so the test behaviour above is predicted, not observed. The unit list is incomplete (개년, 년간, %p, mixed Korean number forms), so the invariant holds only for listed units. Sibling exposure is not addressed: `_quoted` (condition, table, comparison) also accepts a Hangul-ending quote that is a prefix of a longer word (예산 in 예산액, 않는다 in 않는다면). That is out of F1's scope and may come up in a later review. The Korean spelling sources are secondary explanations (newspaper column, search summary), not the National Institute of Korean Language text itself.
