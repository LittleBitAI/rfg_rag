# Review research — F1, cycle 2

Draft research before the fix of review round 3 of PR #24, written 2026-10-14. It is not a verified fact or a shared rule: the review reads it with the fix.

## Problem

F1: a numeric candidate's (value, unit) must appear in the answer and in a cited evidence text as one complete numeric expression: the whole signed number and the whole unit, with nothing that changes its meaning on either side. golden_pipeline/generation.py `_numeric` checks this through `_pairs`, which runs `re.finditer(spec['pattern'], _norm(text))`. At a82bdb0 the match starts at the first digit, so a sign in front of it (`-130,000,000원`) is dropped. It ends at the first listed unit, so a continuation after the unit (`5%p`) is dropped. The answer `-130,000,000원` passes against the positive E1 amount, and `5%` gets evidence from `5%p`.

Trigger: repeat, rounds 2, 3.

- [P1] [P1] golden_pipeline/generation.py:129 — Pair extraction still accepts incomplete numeric expressions

## Failed fixes

- a1c573b (original): `_numeric` checked `_norm(value+unit)` as a plain substring. Removing commas made a shorter number a substring of a longer one (30000000원 inside 130000000원, 2개월 inside 12개월).
- 18ce4bd (review 1): `_contains` got a digit lookbehind and lookahead. It closed the left digit edge, but the right-edge check only runs when the quote ends in a digit, and a value+unit quote ends in a unit. `12개` therefore still matched inside `12개월`.
- a82bdb0 (review 2, from the cycle 1 research): `_pairs` extracts (number, unit) pairs with the numeric spec `pattern`, longest unit first, and requires exact pair equality. That closed unit-prefix cases among listed units (`12개` vs `12개월`) and wrong splits (`12개`/`월`). The pattern is a selection predicate built for `.search` (plan.py:114-120). It has no left anchor, so a sign or range mark outside `\d` is silently dropped, and no right anchor, so whatever follows the unit is ignored. Cycle 1's own counterevidence predicted the `5%p → %` and `3개년 → 개` mis-reads, but the fix added tests only for the review's reproductions, so the predicted case shipped. A third gap is unreported: `_pairs` runs on `_norm(text)`, which deletes spaces and commas first, so token boundaries are gone before extraction (`1, 2, 3개월` → `123개월` → pair (123, 개월)).

## Sources

### S1 — re — Regular expression operations (Python 3 documentation)

- URL: https://docs.python.org/3/library/re.html
- Retrieved: 2026-10-14
- Locator: (?<!...) and re.finditer
- Fragment: (?<!...) Matches if the current position in the string is not preceded by a match for .... This is called a negative lookbehind assertion. Similar to positive lookbehind assertions, the contained pattern must only match strings of some fixed length. Patterns which start with negative lookbehind assertions may match at the beginning of the string being searched. / re.finditer: Return an iterator yielding Match objects over all non-overlapping matches for the RE pattern in string. The string is scanned left-to-right, and matches are returned in the order found. Empty matches are included in the result.
- Applicability: `_pairs` uses finditer with no assertions, so a match starts at whatever digit can start one, and the sign before it is outside the match. Single-character sign and range classes satisfy the fixed-width lookbehind rule.
- Counterevidence: Lookbehind alone cannot see multi-character Hangul prefixes of variable length; those need fixed-length alternatives or another approach.
- Validation: With the lookbehind and sign capture, `-130,000,000원` yields (-130000000, 원) and no (130000000, 원); `10-12개월` yields no 12/개월 pair.

### S2 — Maximal munch (Wikipedia)

- URL: https://en.wikipedia.org/wiki/Maximal_munch
- Retrieved: 2026-10-14
- Locator: lead and C++ section
- Fragment: "maximal munch" or "longest match" is the principle that when creating some construct, as much of the available input as possible should be consumed. ... [pre-C++11] two consecutive > characters are interpreted as the right-shift operator >> ... An exception to the maximal munch rule had to be added anyway [for <::]: unless the sequence is followed by : or >, the < is treated as its own token.
- Applicability: A numeric expression is a token: sign + number + unit, consumed as far as it goes on both ends. Particles after a unit are the exception that needs an explicit rule, as `<::` did in C++.
- Counterevidence: The principle comes from programming-language lexers with closed token sets. Korean unit extensions are not a closed set, so longest match is only as complete as the unit list.
- Validation: `5%p`, `5%포인트` and `3개년` are consumed or blocked as longer tokens, so they never supply a shorter-unit pair.

### S3 — 퍼센트와 퍼센트포인트 (한국경제 생글생글)

- URL: https://sgsg.hankyung.com/article/2006032963621
- Retrieved: 2026-10-14
- Locator: 퍼센트포인트 definition and the 0.75%P example
- Fragment: 그 관심의 대상이 되는 숫자가 퍼센트로 표시된 것(실업률,시장점유율,이자율 등)일 때에는 퍼센트의 변화를 퍼센트포인트로 표현한다. 이 때 두 개의 퍼센트의 차이(혹은 변화)를 퍼센트포인트(혹은 %P)라고 한다. ... '0.75%P'는 0.75%포인트를 줄여 쓴 것이다 ... 0.75%포인트(혹은 0.75%P)를 그냥 0.75%라고 혼동해 쓰고 있다. Condition: 퍼센트끼리의 산술적 연산을 할 수 있는 유일한 경우는 퍼센트를 계산한 기준이 같을 때다.
- Applicability: Shows that the round-3 case `5%` vs `5%p` is a real change of meaning, and that the same unit is also written in Hangul (`%포인트`) and uppercase (`%P`). The right-edge rule must cover all three.
- Counterevidence: A newspaper column, not a 국립국어원 norm; it does not list every way %p is written.
- Validation: check_structure rejects 5/% against `5%p` and against `5%포인트`.

### S4 — Why Financial Statements Lose Units, Signs and Subtotals (imagetotable.ai)

- URL: https://imagetotable.ai/ko/blog/financial-statement-extraction-validation
- Retrieved: 2026-10-14
- Locator: negative amounts section
- Fragment: 마이너스 금액은 마이너스 부호 대신 괄호로 표기됩니다. ... 괄호 쌍은 값 주변의 구두점이기 때문이다. ... 괄호를 제거하면 적자는 이익잉여금이 되고, 손실은 이익이 되며... Condition: rows labeled as a deficit, loss or 'Less:' item should be extracted as negative; if a sign looks wrong, check the source page.
- Applicability: Dropping the sign mark around a number flips its meaning, which is the reviewer's `-130,000,000원` case. Signs must be part of the extracted value.
- Counterevidence: A vendor blog about financial statements, not RFPs. It does not mention △/▲. The △ convention is my reading and unsourced; the search result itself said so.
- Validation: `-130,000,000원` and `△130,000,000원` answers are rejected against E1.

### S5 — golden_pipeline/generation.py at a82bdb0

- URL: golden_pipeline/generation.py
- Retrieved: 2026-10-14
- Locator: _numeric lines 111-120; _pairs lines 123-129; _norm line 315-316
- Fragment: pair = (_norm(value), _norm(unit)); if pair not in _pairs(spec, _norm(answer)) ... return {(match[0][:match.start(1) - match.start()], match[1]) for match in re.finditer(spec["pattern"], text)} ... def _norm(text): return re.sub(r"[\s,]", "", unicodedata.normalize("NFC", text))
- Applicability: Extraction runs on whitespace- and comma-stripped text, with no assertion before the first digit or after the unit.
- Counterevidence: none given
- Validation: After the fix, `_pairs` receives NFC text with boundaries intact and returns signed values; the new red cases turn green.

### S6 — golden_pipeline/configs/topics/numeric.json and plan.py selection

- URL: golden_pipeline/configs/topics/numeric.json
- Retrieved: 2026-10-14
- Locator: "pattern"; plan.py:114-120
- Fragment: "pattern": "\\d[\\d,.]*\\s*(원|천원|만원|억원|%|개월|년|일|시간|명|건|개|회|식|MB|GB|TB)" / plan.py: pattern = re.compile(spec["pattern"]) ... if pattern is None or pattern.search(unit["text"]):
- Applicability: The pattern was written as a presence test for bundle selection, not as a token definition. Its SHA is pinned by plans (`_plan_for`), so editing it invalidates plans.
- Counterevidence: Reusing it does keep selection and validation on the same unit list, which is why cycle 1 chose it.
- Validation: The fix leaves numeric.json unchanged; topic_spec_sha256 in existing plans still matches.

### S7 — Cycle 1 research page

- URL: docs/research/review-feature-golden-data-generation-f1-1.md
- Retrieved: 2026-10-14
- Locator: Counterevidence, first bullet
- Fragment: Units outside it (개년, 년간, 일간, %p, 천만원 written as 3천만원) would either be read with a shorter unit (3개년 read as 3 + 개, 5%p read as 5 + %) or yield no pair ... the mis-read cases (3개년 → 개, 5%p → %) would accept a wrong unit, the same class of bug.
- Applicability: Round 3's `5%p` case was predicted before the a82bdb0 fix and left untested.
- Counterevidence: none given
- Validation: This cycle's experiment adds tests for every predicted mis-read, not only for the reviewer's reproductions.

### S8 — tests/golden/test_generation.py at a82bdb0

- URL: tests/golden/test_generation.py
- Retrieved: 2026-10-14
- Locator: lines 84-111 and 119-131
- Fragment: ("기간은 12개이다", {"value": "12", "unit": "개"}), ("기간은 12개월이다", {"value": "12개", "unit": "월"}) ... test_numeric_unit_followed_by_a_particle_is_accepted ... ("numeric", {"value": "5"}, [unit("5%")], False)
- Applicability: No test covers a signed value, a %p, 개년 or range continuation, or text joined by `_norm`.
- Counterevidence: none given
- Validation: The new parametrized cases sit next to these, and the particle control stays.

## Claims

- C1 (source; S1, S5): `_pairs` starts a match at the first digit that can start one and checks nothing after the unit, so a leading sign and a trailing unit continuation are both discarded.
- C2 (source; S6): The numeric spec pattern is a selection predicate used with `.search` in plan.py.
- C3 (interpretation; S5, S6, S7): All three fixes reused presence tests (substring, then a search pattern) as an equality test for a token, and each closed only the edge the review had just shown.
- C4 (source; S7, S8): The cycle 1 research predicted the `5%p → %` and `3개년 → 개` mis-reads, and the following fix added no test for them.
- C5 (source; S2): Longest match defines a token by consuming as much input as possible, and its known failures are handled with explicit exception rules.
- C6 (source; S3): %포인트/%P means something different from %, and Korean text writes it both as %p/%P and as %포인트.
- C7 (interpretation; S1, S4): Dropping a number's sign mark flips its meaning, so the sign must stay in the extracted value; Python lookbehind with single-character sign and range classes can enforce the left edge.
- C8 (interpretation; S5): Running `_norm` before extraction deletes the spaces and commas that separate tokens, so `1, 2, 3개월` produces a pair (123, 개월) that the text does not hold. Extraction should run on NFC text, and normalization should apply only to the captured value.

## Core theory

Maximal munch / longest match: 'when creating some construct, as much of the available input as possible should be consumed.' The token is defined by both of its ends, and where longest match gives the wrong split, an explicit exception rule is added; Wikipedia gives C++'s `<::` as an example. Python `re.finditer` returns non-overlapping matches scanned left to right, starting wherever the pattern can match. Without assertions, nothing forces a match to begin at a token start or end at a token end. A negative lookbehind must be fixed width, so the sign and range marks fit as one-character classes. Domain: Korean writing gives %포인트/%P a meaning distinct from % ('두 개의 퍼센트의 차이...를 퍼센트포인트(혹은 %P)라고 한다', with a headline that confused 0.75%포인트 with 0.75%). Dropping a sign or the parentheses turns a loss into a profit.

## Applicability

golden_pipeline/generation.py:111-129 (`_numeric`, `_pairs`) only. Both the answer check (line 116) and the evidence check (line 118) go through `_pairs`, so one change covers both. `_contains`/`_quoted` (table, condition, comparison) have no unit concept and stay as they are. RFP evidence holds the affected forms: amounts possibly signed or △-marked, rates in % and %p, periods in 개월 and 개년, and ranges with ~ or -. The fixture u1 (`사업 예산은 130,000,000원(부가세 포함)이며 계약 기간은 12개월이다.`) provides the reviewer's sign case and the particle controls. golden_pipeline/README.md:218 describes the numeric rule and should change with it.

## Hypothesis

The fixes keep failing for one reason: a search predicate is being used as a tokenizer. Each round adds a guard for one edge of one character class, the one the reviewer just reproduced: digit-left, then unit-prefix-right, now sign-left and continuation-right. The invariant needs both token boundaries defined at once, by the longest-match rule, on text whose boundaries are still intact. What would hold: (1) Extract from NFC text before `_norm` and apply `_norm` only to the captured value, so spaces and commas still separate tokens. (2) Left edge: capture an optional sign `[+\-−±△▲]` as part of the value, and refuse to start a match right after `[\d.,~∼〜+\-−±△▲]`. A sign after a digit is then a range dash, not a sign, and neither `-12개월` nor `12개월` is extracted from `10-12개월`. (3) Right edge: after the longest listed unit, refuse a following Latin letter or `/` (closes `%p`, `MB/s`, `원/월`), plus a short list of Hangul unit extensions that no particle begins with (`포인트`, `년`, `간`), so `5%포인트` and `3개년` give no pair. Particles still pass: `12개월이다`, `130,000,000원(부가세`. (4) Exact equality of (`_norm(value)`, `_norm(unit)`) in the answer and in a cited text, as now. Build the extractor in generation.py around the spec pattern. Do not edit numeric.json: that changes the spec SHA every plan pins and changes plan selection.

## Counterevidence

- The Hangul continuation list (`포인트`, `년`, `간`) is an enumeration, the same shape that failed before. A later review can find another Hangul extension (개소, 회차, 년차, 년도), or a Hangul prefix that changes meaning on the left (`제3회` vs `3회`). The non-Hangul rule (Latin letter, `/`) is a class rule and complete for its class; the Hangul side is not.
- Cycle 1 showed that a broad Hangul lookahead breaks particles (`12개월이다`). Any Hangul continuation entry must not begin a particle, which keeps `도` out of the list (`2025년도` vs particle 도), so some extensions stay readable as the shorter unit.
- Refusing a match after a range mark or a sign-after-unit (`2024년-2025년` → (-2025, 년)) rejects some candidates that are literally fine. That costs recall but is the safe direction.
- The sign and range-mark sets (−, △, ▲, ±, ~, ∼, 〜) come from my reading and one secondary source on sign loss. No source lists every negative or range notation in Korean RFP text.

## Alternatives

- Patch only the two reproductions: a sign lookbehind, plus `(?!p)` after `%`. It is the smallest diff, but this is the pattern that failed three times, and `5%포인트`, `3개년`, `MB/s` and the `_norm` merge stay open.
- Edit numeric.json `pattern` to the tokenizer form. This would keep selection and validation identical, but it changes the pinned topic_spec SHA, so `_plan_for` refuses existing plans, and it changes which units plan.py selects. Not first.
- Kiwi morphology (kiwipiepy is already in requirements.txt and golden_pipeline may import it): require SN + unit morpheme(s) equal to the unit, followed by a particle, ending or punctuation, not a noun or SL. In principle it closes the Hangul side as a class rule. Not first: Kiwi's tags for %, %p, 개년 and MB are unverified, and it adds a model load to a pure-regex check. This is the fallback if a fourth review lands on another Hangul extension.
- Normalize signs to '-' and compare by meaning: rejected. Numeric goldens want the value as written, and matching by meaning is the rag/evaluation approach golden_pipeline must not import.
- Changing `_contains`: rejected. `_numeric` no longer uses it, and the condition, table and comparison topics depend on its behavior.

## Experiment

Before the fix (red): add cases to `test_numeric_candidate_without_a_value_from_evidence_is_rejected_as_type_mismatch` with evidence E1: answer `-130,000,000원` with structure 130,000,000/원 (the reviewer's case), and answer `△130,000,000원`. Add `check_structure` numeric cases: 5/% against `5%p` → mismatch, 5/% against `5%포인트` → mismatch, 3/개 against `3개년` → mismatch, 12/개월 against `10~12개월` → mismatch, 123/개월 against `1, 2, 3개월` → mismatch. Controls that must stay accepted: 5/% against `5%이다`, 6/개월 against `6 개월`, plus the existing `12개월이다` and `130,000,000원(부가세 포함)` tests. Confirm the new mismatch cases fail at a82bdb0, then pass after the change with every existing review-1 and review-2 case unchanged. Then run `ruff check .` (C901 ≤ 8) and the full gate. The hypothesis is refuted if any control fails, or if a mismatch case can only be closed by touching `_contains` or numeric.json.

## Result

pending — the fix records what it observed here, with the tests and the commit.

## Unresolved limits

The Hangul right edge stays an enumeration, and Hangul prefixes on the left (제N회) are not covered. A complete answer needs morphological analysis, which is untested here. I ran no code: predicted outcomes, including the `1, 2, 3개월` merge, are from reading `_pairs` and `_norm`, not from execution. The Korean sources are secondary (a newspaper column and a vendor blog). The maximal-munch source is Wikipedia, because the EPFL PDF could not be read as text.
