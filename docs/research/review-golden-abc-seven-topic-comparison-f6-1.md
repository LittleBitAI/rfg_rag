# Review research — F6, cycle 1

집계 결과와 측정 조건은 Git에 보관하고, 원시 질문·정답·근거·OCR 전사와 레코드별 내보내기는 무시된 로컬 `artifacts/`에 보관한다.

복원 출처: 정리 전 `artifacts/review-round2/originals/` 또는 `d7d1682^`. 아래 수치와 검증 기록은 당시 실행의 역사적 관측이며 이번 작업에서 재측정한 결과가 아니다.

Draft research before the fix of review round 6 of PR #65, written 2026-10-18. It is not a verified fact or a shared rule: the review reads it with the fix.

> Misfiled (review round 7, F5). From "## Problem" down to "## Experiment", this page analyses F2 (`_human` reading judgments.csv), not F6. It was written by the server's format retry, which ran in a new session whose prompt held only the parse error, not the finding (see `review-golden-abc-seven-topic-comparison-f5-1.md`). Do not cite those sections as grounds for any F6 fix. The F6 research written before the fix is the next section. It was restored from the first, rejected research answer.

## F6 research written before the fix (restored)

Provenance: wiki-agent task transcript `raw/work/rfg_rag/golden-abc-seven-topic-comparison.jsonl`, line 43 (cell `e8e0948d…`, ts 1792283995). That is the server's first F6 research turn, answering the F6 prompt at line 42, which quoted the finding from rounds 4, 5 and 6. The server rejected it only because source S5 was a hub-wiki file outside this repository (line 44). The retry at line 45 (a new cell, `ae2c9fe9…`) produced the F2 text below. The answer is older than the research commit `9458840` (ts 1792284182) and the fix commit `f0ddd69` (ts 1792284592). The fix session did not read it. The fix arrived at the same design on its own, and this page records the answer after the fact. Its wording is condensed here; the record at line 43 is authoritative.

Problem. When a partly validated candidate resumes, the call cap must count only the paid calls still to be bought. Calls that `_reply` will replay for free are already paid. Round 4 found the cap charging a candidate's whole `_calls_needed`. Round 6 found the same for validation records written before `cb3f3c1`, which have no `role`: their settled calls are replayed but still charged. Resuming with the exact remaining allowance (`max_calls=2` for a three-call multi_hop whose full-evidence call settled) stops at `call_cap` with the candidate pending.

Failed fixes. Round 4 (`cb3f3c1`) tagged each call with `role` and counted calls tagged `role == "validator"` at attempt 0 as prepaid. That depends on a tag older records lack. `1884f73` replayed roleless records but deliberately did not subtract them (comment at validation.py:109), and the test pinned this with `(True, 3)` although its own comment says the needed cap is 2. Replay and the cap estimate kept deciding "already paid" by two different rules.

Hypothesis. `_reply` replays when this candidate's (request SHA-256, attempt) matches a saved call. `_settled_calls` counted prepaid calls by a separate stored `role` tag, so the two disagree when the tag is missing. Fix: derive prepaid the way replay works. List the validator requests `_verdict` will make: the full evidence, plus one header-attached single unit per non-header unit for multi_hop, or each `document_batches` batch for unanswerable. Hash each with the function `_reply` uses, and count the hashes with an attempt-0 entry in the candidate's replay map. `_calls_needed` becomes the length of that list, and `role` drops out of the cap logic.

Theory. Replay systems decide what is already done by matching the request against the recorded history, not by a label stored beside the result. Temporal compares the commands the workflow emits with its Event History. Stripe returns the saved result for an idempotency key and checks the incoming parameters against the original. Anything that predicts what replay will cover has to use the same key, or the prediction and the replay disagree.

Applicability. Resume refuses to run when the validator prompt SHA or `VALIDATOR_VERSION` changed (`_criteria`), so a saved validator request hash still matches the one the resumed run computes. The judge request carries both answers and uses the judge prompt, so its hash can never be counted as a validator call, even in roleless records.

Counterevidence. (1) `_criteria` does not cover the code of `validator_input` or `document_batches`. If that code changed without a version bump, old hashes would miss, and replay would miss too and pay again. The estimate would still agree with the spend: conservative, not wrong. (2) The count is the largest number of validator calls a candidate can make; retries and judge calls stay uncounted, which is the known ponytail limit. (3) The new list repeats how `_single_unit_verdict` and `_absent_verdict` build their units, and the copies can drift unless they share code.

Alternatives (rejected). Infer the role from the saved output: an attempt-0 output that fails to parse is ambiguous, and it guesses rather than matching replay. Count every roleless attempt-0 call as a validator call: saved judge calls would be subtracted and the cap overrun. Rewrite old records to add `role`: that changes recorded evidence. Document "raise the cap for old records": round 6 rejected exactly that.

Experiment. Change `(True, 3)` to `(True, 2)` in `tests/golden/test_validation.py`. Before the fix it should end at `call_cap` and send nothing new. After it, it should send exactly `(E1,)` and `(E2,)` and end auto_validated. Add a negative case: a saved attempt-0 call that is a judge call must not lower the count.

Sources. S1, Temporal Workflow Definition (deterministic constraints and replay), https://docs.temporal.io/workflow-definition.md. S2, Stripe API, Idempotent requests, https://docs.stripe.com/api/idempotent_requests. Both were read from search summaries in that turn. S3 is `golden_pipeline/validation.py`: `_settled_calls`, `_reply`, `_batch`, `_calls_left`/`_calls_needed` at `1884f73`. S4 is `tests/golden/test_validation.py` lines 474-504 at `1884f73`. The rejected S5 was the hub rule `craft/measure-after-the-last-change`, an internal rule rather than external evidence, so it is not cited here.

## Problem

F2: human review quality may be reported as measured only when every sampled review_id in key.json has exactly one complete Y/N judgment on all four RUBRIC checks. Any other shape of the hand-edited judgments.csv must return {'measured': False, ...} instead of raising, so that compare()/write() still write comparison.json. The finding has come back in rounds 4 and 5 and now again. Each time the reviewer found another malformed file that still makes golden_pipeline/comparison.py::_human (lines 237-269) raise.

Trigger: oscillation, rounds 4, 5, 6.

- [P1] [P1] golden_pipeline/validation.py:110 — roleless settled calls are still charged against the resume cap / when resuming an older partial record with the exact remaining-call allowance / a resumable candidate remains pending

## Failed fixes

- Round 1 (62eeb95): added the Counter exact-ID check (now lines 252-256). It assumed every row holds a str for every required key, so a short row later crashed on None.strip().
- Round 4 (cb3f3c1): changed the Y/N check to (row[name] or '') (now line 258). That handles None in rubric cells only. A column missing from the header produces no key at all, so row[name] raised KeyError before `or ''` ran.
- Round 5 (1884f73, after the cycle-1 page): added a header gate (lines 246-250) that returns unmeasured when review_id or a RUBRIC column is missing, read while the file is open. It closes absent keys but still trusts what the cells hold and what the bytes decode to. Three file shapes still crash: (a) a header where review_id is not the first column plus a short row. DictReader fills review_id with None, the Counter at 252 counts it, and sorted(set(ids) - set(key)) at 255, or sorted over the duplicated IDs at 256, compares None with a str and raises TypeError. (b) A file saved in a non-UTF-8 encoding (for example Excel's plain 'CSV' save on a Korean-locale PC) with Korean text in note. open(encoding='utf-8-sig') uses errors='strict', so list(reader) at 246 raises UnicodeDecodeError. (c) A NUL byte, for example a UTF-16 'Unicode text' save that happens to decode. On the repo's Python 3.10, csv raises csv.Error 'line contains NUL'. All three fixes, including the cycle-1 one, guarded the shape just reported at the line it named. None made the read itself total.

## Sources

### S1 — csv — CSV File Reading and Writing (Python 3 docs)

- URL: https://docs.python.org/3/library/csv.html
- Retrieved: 2026-10-18
- Locator: class csv.DictReader; exception csv.Error; Dialect.strict
- Fragment: If a row has more fields than fieldnames, the remaining data is put in a list and stored with the fieldname specified by restkey (which defaults to None). If a non-blank row has fewer fields than fieldnames, the missing values are filled-in with the value of restval (which defaults to None). ... exception csv.Error: Raised by any of the functions when an error is detected. ... Dialect.strict: When True, raise exception Error on bad CSV input. The default is False.
- Applicability: A short row under a header where review_id is not first gives review_id None (comparison.py:252), which reaches sorted() at 255-256. csv.Error is the parser's error type for bad input at line 246.
- Counterevidence: The page does not list exactly which inputs raise csv.Error when strict is False. NUL is not mentioned in its version notes.
- Validation: Case (a) returns measured False instead of TypeError.

### S2 — Built-in Functions — open() (Python 3.10 docs)

- URL: https://docs.python.org/3.10/library/functions.html
- Retrieved: 2026-10-18
- Locator: open(), errors parameter
- Fragment: 'strict' to raise a ValueError exception if there is an encoding error. The default value of None has the same effect.
- Applicability: comparison.py:243 opens judgments.csv with encoding='utf-8-sig' and default errors, so non-UTF-8 bytes raise when list(reader) runs at 246.
- Counterevidence: If the non-UTF-8 file holds only ASCII bytes, it decodes fine. Only non-ASCII text such as a Korean note triggers the error.
- Validation: Case (b), a cp949 file with a Korean note, returns measured False instead of UnicodeDecodeError.

### S3 — Parse, don't validate (Alexis King)

- URL: https://lexi-lambda.github.io/blog/2019/11/05/parse-don-t-validate/
- Retrieved: 2026-10-18
- Locator: sections defining parser vs validator; 'Ideally, this should happen at the boundary'
- Fragment: a parser is just a function that consumes less-structured input and produces more-structured output. ... Ideally, this should happen at the boundary of your system, before any of the data is acted upon. ... Sometimes, making an illegal state truly unrepresentable is just plain impractical ... Consider the principles in this blog post ideals to strive for, not strict requirements to meet.
- Applicability: _human checks and acts on the data in alternation (header, Counter, sorted, Y/N), so each unchecked stage became a new finding. A single parse step at lines 243-258 before the Counter matches this idea.
- Counterevidence: The author says the approach is an ideal. In Python there is no type to carry the proof, so the guarantee holds only by ordering the checks.
- Validation: After the change, lines from the Counter on see only str values. The three new cases and the old ones all return measured False without new guards at later lines.

### S4 — denoland/deno_std PR 3143 (discussion of Excel CSV export and BOM)

- URL: https://github.com/denoland/deno_std/pull/3143
- Retrieved: 2026-10-18
- Locator: web search result summary for Excel 'CSV UTF-8' vs 'CSV'
- Fragment: The 'CSV UTF-8' option in Excel's Save As list adds a byte order mark; the plainly labeled 'CSV' option does not add a BOM and transforms all non-Windows-1252 characters into question marks (lossy). (from the search result; the PR page itself was not fetched)
- Applicability: A team member who re-saves judgments.csv through Excel's plain 'CSV' option gets a file in the ANSI code page, not UTF-8. On a Korean locale I assume that is CP949, so a Korean note becomes non-UTF-8 bytes.
- Counterevidence: It describes a Windows-1252 locale and does not test the default Save of a file that was opened with a BOM. Korean-locale behaviour is not stated.
- Validation: Case (b) reproduces the resulting bytes directly with encoding='cp949', so the fix does not depend on Excel's exact behaviour.

### S5 — docutils py311 test patch (Adélie Linux packages)

- URL: https://cgit.adelielinux.org/packages/tree/user/py3-docutils/py311-test.patch
- Retrieved: 2026-10-18
- Locator: commit message of the patch, per the web search result
- Fragment: changed for Python 3.11: Null char valid in CSV ... 3.11.0a2 ... csv module supports null character (from the search result)
- Applicability: The repo's .venv is Python 3.10 (CLAUDE.md section 6), where csv still raises csv.Error 'line contains NUL' on a NUL byte at comparison.py:246.
- Counterevidence: A downstream note, not a CPython release note. On 3.11+ case (c) would not raise, so the catch would cover only other csv.Error causes.
- Validation: Case (c) on the 3.10 .venv raises csv.Error before the fix and returns measured False after.

### S6 — golden_pipeline/comparison.py _human

- URL: golden_pipeline/comparison.py
- Retrieved: 2026-10-18
- Locator: lines 237-269
- Fragment: columns, rows = set(reader.fieldnames or ()), list(reader) ... missing_columns = sorted({"review_id", *RUBRIC} - columns) ... ids = Counter(row["review_id"] for row in rows) ... "unknown": sorted(set(ids) - set(key)), "duplicated": sorted(review_id for review_id, n in ids.items() if n > 1)} ... if any((row[name] or "").strip().upper() not in ("Y", "N") for row in rows for name in RUBRIC):
- Applicability: The header gate is present. There is no guard on decoding or csv errors, and no None check on review_id before the Counter and the sorted() reason lists.
- Counterevidence: none
- Validation: After the fix, one parse step sits between line 243 and the Counter, and lines 252-269 are unchanged except that `or ''` is removed.

### S7 — tests/golden/test_experiment.py review quality test

- URL: tests/golden/test_experiment.py
- Retrieved: 2026-10-18
- Locator: lines 79-103
- Fragment: header = "review_id,evidence_support,answer_correct,topic_fit,useful,note" ... for dropped in range(5): ... (folder / "judgments.csv").write_bytes(b"") ... write_text(..., encoding="utf-8-sig")
- Applicability: Every case keeps review_id as the first column and writes UTF-8 with BOM, so it never tests a reordered header with a short row, a non-UTF-8 file or a NUL byte.
- Counterevidence: none
- Validation: Add cases (a), (b) and (c), plus a reordered complete header that is still measured.

### S8 — Review research — F2, cycle 1

- URL: docs/research/review-golden-abc-seven-topic-comparison-f2-1.md
- Retrieved: 2026-10-18
- Locator: Failed fixes; Hypothesis; Unresolved limits
- Fragment: Both fixes were placed at the line where the symptom appeared and handled only the malformation that had been reported. ... This research covers only schema and value shape.
- Applicability: Cycle 1 itself limited its scope to schema and value shape. Encoding, csv tokenising and None in review_id under a reordered header fell outside that scope.
- Counterevidence: Cycle 1 argued that the header gate plus `or ''` covers every malformed shape raised so far, which was true of the shapes raised up to that point.
- Validation: This cycle's experiment covers the shapes cycle 1 left out.

## Claims

- C1 (interpretation; S1, S6): DictReader fills the missing values of a short non-blank row with None, including review_id when review_id is not the first column. _human then counts that None and sorts it next to str IDs, which raises TypeError.
- C2 (interpretation; S2, S4, S6): A judgments.csv holding non-UTF-8 bytes (for example a CP949 Korean note) makes the utf-8-sig read raise UnicodeDecodeError, because open() defaults to strict errors.
- C3 (interpretation; S1, S5, S6): csv raises csv.Error when it detects bad input, and on Python 3.10 a NUL byte is such input. _human does not catch it.
- C4 (interpretation; S3, S6): Parsing at the boundary, before any data is acted upon, means converting the file once into str-only rows, or into an unmeasured reason, before the Counter. That closes the whole set of failures instead of one shape per round.
- C5 (interpretation; S7, S8): The existing test and the cycle-1 research covered only header and value shape, always with review_id first and UTF-8 encoding. That is why the remaining shapes were not caught.

## Core theory

Alexis King, 'Parse, don't validate': a parser consumes less-structured input and produces more-structured output that keeps what it learned. Parsing 'should happen at the boundary of your system, before any of the data is acted upon'. The author offers this as an ideal, not a strict rule, and notes that making illegal states unrepresentable is sometimes impractical. The Python docs give the concrete failure shapes: DictReader fills the missing values of a short non-blank row with restval (None), and puts extra values in a list under restkey (None). open() with the default errors raises ValueError (UnicodeDecodeError) on a decoding error. csv raises csv.Error when it detects an error, and NUL bytes raised it before Python 3.11.

## Applicability

judgments.csv is written by review_packets (comparison.py:198-201) as UTF-8 with BOM and header review_id,*RUBRIC,note, and then a person edits it by hand. That makes it a trust boundary, and F2's invariant demands a total function over it. The parse step belongs in _human, at lines 243-258, in front of the Counter (252), because the Counter is the first consumer that assumes review_id is a str. Column order is free because DictReader keys by name, and the existing test already rearranges columns by dropping them, so a reordered header is a real shape. The team works on Korean Windows and note is free text, so non-UTF-8 saves are plausible. The repo's .venv is Python 3.10, where NUL still raises.

## Hypothesis

The root cause is that _human validates the file piece by piece instead of parsing it once into a trusted form before using any value. Every reading stage can raise on bad input: decoding, csv tokenising, header keys, per-row None values, and then the Counter, sorted and Y/N checks. Each round closed one stage. The fix that holds has a single parse step at the start: (1) wrap the open/DictReader/list(reader) block so that UnicodeDecodeError and csv.Error, the only errors file content can cause there, return measured False with a reason (for example, save the file as 'CSV UTF-8'). (2) Keep the header gate. (3) Before the Counter, return unmeasured if any row has None in review_id or any RUBRIC column (a short row), so every later value is a str. After that the ID check, the sorted() reason lists and the Y/N check run only on strs and need no further guards. The `or ''` on line 258 can then go.

## Counterevidence

- CLAUDE.md 1.1 forbids speculative error handling. Catching UnicodeDecodeError/csv.Error could be read that way. It is input validation at a trust boundary, which the invariant explicitly asks for, and the catch should cover only the read block, not the whole function.
- I did not confirm that Excel's default Save turns a BOM CSV into the ANSI code page. The source I found says only that the plain 'CSV' option drops the BOM and is lossy (it mentions Windows-1252). On a Korean locale the ANSI page is CP949, which is my interpretation.
- I could not read the round-6 finding text in the repo. If the reviewer flagged something other than these three shapes (for example key.json), this hypothesis misses it.

## Alternatives

- Open with errors='replace': a CP949 note would become U+FFFD while the ASCII ID and Y/N cells survive, so the file would still be measured. It does not cover NUL on 3.10 or UTF-16, and it silently accepts a mis-encoded file. A possible follow-up, not first.
- Replace sorted(...) with sorted(..., key=str) on lines 255-256: fixes only shape (a) at the symptom line, the same pattern that has failed three times.
- try/except Exception around the whole of _human: hides real bugs and violates CLAUDE.md 1.1.
- Pass explicit fieldnames to DictReader: binds values to the wrong columns when the header is reordered, giving silently wrong judgments. Already rejected in cycle 1.

## Experiment

Extend tests/golden/test_experiment.py::test_review_quality_is_unmeasured_unless_every_sampled_output_is_judged_exactly_once with three files, keeping key R01/R02: (a) header 'evidence_support,answer_correct,topic_fit,useful,review_id' with rows 'Y,Y,Y,Y,R01', 'N,Y,Y,Y' and 'Y,Y,Y,Y,R03'; (b) the full header with R01/R02 rows whose note holds Korean, written with encoding='cp949'; (c) the full header with a NUL byte inside a note cell. Each must return measured False. On HEAD (af5aa9f) under the repo's .venv (3.10), expect (a) TypeError, (b) UnicodeDecodeError, (c) csv.Error before the fix. Also assert that a reordered header with complete rows is still measured (A · all = 1/2), so the parse step does not over-reject. One narrow pytest run of this test, then the gate.

## Result

This page analyses F2 (`_human` reading judgments.csv), not the round-6 F6 finding, which is about the resume call cap in `golden_pipeline/validation.py:110` (`_settled_calls`). Both were handled in the same commit, and both are recorded here.

The page's experiment on F2: `tests/golden/test_experiment.py::test_review_quality_is_unmeasured_unless_every_sampled_output_is_judged_exactly_once` was extended with (a), (b), (c) and a reordered complete header. A scratch run of the `af5aa9f` `_human` under the repo's 3.10 `.venv` gave the predicted errors: (a) `TypeError '<' not supported between instances of 'NoneType' and 'str'`, (b) `UnicodeDecodeError 'utf-8' codec can't decode byte 0xb1`, (c) `csv.Error line contains NUL`. The reordered complete header was already measured (A · all = 1/2). The fix is the hypothesis's single parse step, `comparison._judgment_rows`. It catches `UnicodeDecodeError` and `csv.Error` around the read block only. It keeps the header gate. It returns unmeasured when any row holds None in `review_id` or a RUBRIC column. The `or ""` is removed. After the fix, (a) is unmeasured as a short row, (b) and (c) are unmeasured as unreadable with "save as 'CSV UTF-8'", and the reordered complete header is still measured.

F6 as raised: the same test-file run with the roleless case of `tests/golden/test_validation.py::test_resume_counts_only_the_calls_a_candidate_has_not_already_settled_against_the_call_cap` at `max_calls=2` failed before the fix. Only `[('E1','E2')]` was sent, and the candidate stayed pending. The fix drops the `role` field rather than inferring it. `_calls_left` rebuilds the validator requests the candidate will send from the same unit lists `_verdict` uses (`_validator_unit_lists`, which replaces `_calls_needed`). It counts a request as already paid when its first attempt is in that candidate's replay, matched by request SHA-256; a judge request also carries both answers, so it cannot match. Old (8326cee) and new records now count the same way. The test was folded back to one case with cap 2, and it passes. `tests/golden/test_validation.py`, `test_experiment.py` and `test_cli.py` gave 137 passed; `test_improvement.py` gave 41 passed. The full gate is the server's and is still pending.

Round 7 (F5), against the restored F6 research above. Its experiment's first case is the `(True, 2)` run above: before `f0ddd69` it sent only `[('E1','E2')]` and stopped at `call_cap`; after it, the cap of 2 sends `(E1,)` and `(E2,)` and ends auto_validated. Its negative case was missing and is now `tests/golden/test_validation.py::test_a_settled_judge_call_does_not_count_as_a_paid_validator_call`. It saves only a judge call for the same question and evidence and expects the multi_hop candidate to still need all 3 validator calls. Counting every saved attempt-0 call (a rejected alternative) would give 2. Its counterevidence (3), drift between the counted requests and the sent ones, applied: `_single_unit_verdict` built its own header-attached singles. Both now take them from `validation._single_units`, and unanswerable already shared `document_batches`. `tests/golden/test_validation.py`, `test_cli.py` and `test_improvement.py` passed (the 163 other tests, then the negative case and the resume test: 2 passed), in the commit that carries this banner.

## Unresolved limits

The round-6 finding text was not available to me, so I derived these shapes by reading the code rather than from the reviewer's words. Excel's exact save behaviour on a Korean locale is unverified. NUL support from Python 3.11 on comes from a downstream patch note, not CPython release notes; it matters only if the venv moves past 3.10. key.json missing or malformed while judgments.csv exists still raises at line 242. review_packets writes both files and key.json is not meant to be edited, so I left it out, but a strict reviewer could count it under 'any shape'. csv.field_size_limit (a field over 131072 characters) also raises csv.Error and would be covered by the same catch.
