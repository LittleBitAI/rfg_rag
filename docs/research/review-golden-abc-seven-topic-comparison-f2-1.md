# Review research — F2, cycle 1

집계 결과와 측정 조건은 Git에 보관하고, 원시 질문·정답·근거·OCR 전사와 레코드별 내보내기는 무시된 로컬 `artifacts/`에 보관한다.

복원 출처: 정리 전 `artifacts/review-round2/originals/` 또는 `d7d1682^`. 아래 수치와 검증 기록은 당시 실행의 역사적 관측이며 이번 작업에서 재측정한 결과가 아니다.

Draft research before the fix of review round 5 of PR #65, written 2026-10-18. It is not a verified fact or a shared rule: the review reads it with the fix.

## Problem

F2 requires that human quality is reported as measured only when every sampled review_id in key.json has exactly one complete Y/N judgment on all four RUBRIC checks. Any other judgments.csv shape must come back as {'measured': False, ...}, not crash. Right now `_human()` (golden_pipeline/comparison.py:237-263) still raises when the header is malformed. A header missing a rubric column raises KeyError at line 252, a header missing review_id raises KeyError at line 246, and `compare`/`write` then abort without writing comparison.json.

Trigger: repeat, rounds 4, 5.

- [P1] [P1] golden_pipeline/comparison.py:252 — A missing rubric header still crashes human-review comparison

## Failed fixes

- Round 1 fix (fixed at 62eeb95 → later): added the Counter-based exact-ID check at lines 246-250 (missing/unknown/duplicated IDs → unmeasured). It checked the set of IDs but assumed every row dict holds every RUBRIC key with a str value. Short rows and missing columns were never considered, so round 4 hit `None.strip()`.
- Round 4 fix (cb3f3c1): changed line 252 to `(row[name] or "")` so the None that DictReader fills in for short rows counts as an empty cell. That covers restval=None, which only happens when the column exists in the header. When the header has no such column, the dict has no key, so `row[name]` raises KeyError before `or ""` runs. The test added at tests/golden/test_experiment.py:86-91 always writes the full header, so it could not catch this. Both fixes were placed at the line where the symptom appeared and handled only the malformation that had been reported.

## Sources

### S1 — csv — CSV File Reading and Writing (Python 3 docs), DictReader

- URL: https://docs.python.org/3/library/csv.html
- Retrieved: 2026-10-18
- Locator: class csv.DictReader; DictReader.fieldnames
- Fragment: If fieldnames is omitted, the values in the first row of file f will be used as the fieldnames and will be omitted from the results. ... If a row has more fields than fieldnames, the remaining data is put in a list and stored with the fieldname specified by restkey (which defaults to None). If a non-blank row has fewer fields than fieldnames, the missing values are filled-in with the value of restval (which defaults to None). ... DictReader.fieldnames: If not passed as a parameter when creating the object, this attribute is initialized upon first access or when the first record is read from the file.
- Applicability: comparison.py:244 builds DictReader with no fieldnames, so the header in judgments.csv alone decides the keys. restval None explains round 4. The absence of any key for a missing column explains round 5.
- Counterevidence: The page does not state the empty-file value of fieldnames (None in CPython); experiment (c) checks it.
- Validation: Header-missing-column and header-missing-review_id tests return measured False instead of raising KeyError.

### S2 — golden_pipeline/comparison.py _human

- URL: golden_pipeline/comparison.py
- Retrieved: 2026-10-18
- Locator: lines 237-263
- Fragment: ids = Counter(row["review_id"] for row in rows) ... if any((row[name] or "").strip().upper() not in ("Y", "N") for row in rows for name in RUBRIC):
- Applicability: No check of reader.fieldnames exists. Every row[...] lookup assumes the header is complete.
- Counterevidence: none given
- Validation: After the fix, a fieldnames gate sits before line 246.

### S3 — tests/golden/test_experiment.py review quality test

- URL: tests/golden/test_experiment.py
- Retrieved: 2026-10-18
- Locator: lines 79-93
- Fragment: header = "review_id,evidence_support,answer_correct,topic_fit,useful,note" ... for rows in ([], ["R01"], ["R01", "R01", "R02"], ["R01", "R02", "R03"], ["R01 짧음", "R02 짧음"]):
- Applicability: Every case keeps the full header, so the header dimension was never tested.
- Counterevidence: none given
- Validation: Add the header-variant cases.

## Claims

- C1 (source; S1): DictReader fills missing values in short rows with None only for columns that are in the header. A column missing from the header produces no key at all.
- C2 (interpretation; S1, S2): Both earlier fixes guarded values at the line where the crash appeared. Neither checked the header, so a header without a rubric column (line 252) or without review_id (line 246) still raises KeyError.
- C3 (interpretation; S2, S3): One check that the header contains {'review_id', *RUBRIC}, done before rows are read and returning unmeasured otherwise, plus the existing `or ""` value guard, covers every malformed shape raised so far. The test must vary the header, not only the rows.

## Core theory

The Python csv docs say DictReader builds each dict's keys from fieldnames, which by default is the first row. Short rows get restval (default None) for the missing fields, and extra fields go into a list under restkey (default None). So a value is None only when the column exists in the header. When a column is missing from the header, the key does not exist in any row. These are two different failure shapes and need two different guards: a header check for absent keys, and a value check for None or blank values.

## Applicability

golden_pipeline/comparison.py:243-252. judgments.csv is written by review_packets (line 198-201) with the header `review_id,*RUBRIC,note`, but it is then edited by hand. That makes it a trust boundary, and a human editor can delete or rename a column. The header check belongs right after `csv.DictReader(f)` is created, before the `rows` list is consumed, so it runs ahead of the ID Counter at line 246, which itself needs the review_id column. Extra cells (restkey None) do not crash today and are not scored, so they need no handling.

## Hypothesis

The root cause is that the file's schema is never validated: `_human()` checks row values but never checks the header (`DictReader.fieldnames`). Every key lookup (`row['review_id']` at 246, `row[name]` at 252/257/262) relies on an unchecked assumption that the header contains review_id and all of RUBRIC. One check right after the DictReader is built, `if not {'review_id', *RUBRIC} <= set(reader.fieldnames or ()): return {'measured': False, 'reason': ..., 'missing_columns': ...}`, closes the whole class of failures: a missing rubric column, a missing review_id column, and an empty 0-byte file (fieldnames None). The existing `or ""` stays, because short rows under a complete header still yield None. Once both gates pass, lines 257 and 262 only ever see 'Y'/'N' strings, so they need no change.

## Counterevidence

- Leaving out `note` from the header is harmless, since nothing reads note. The check must not require it, or a valid file with no note column would be wrongly reported as unmeasured.
- A header written with stray spaces (e.g. ' useful') or a duplicated column name would be judged by the header check, not by the values. Spaces would make it unmeasured, which is conservative and acceptable. A duplicated name lets DictReader keep the later column, which the check cannot see. This is an edge case and not in the finding.

## Alternatives

- Replace `row[name]` with `row.get(name)` everywhere. This also stops the crash, but it spreads the guard across lines 246, 252, 257 and 262 instead of putting one guard where all of them route through, and a missing review_id column would show up as a confusing 'IDs don't match' reason. That is not the first choice.
- Pass `fieldnames=('review_id', *RUBRIC, 'note')` explicitly to DictReader and skip the first row. This hides a reordered or renamed header by binding values to the wrong columns, which silently produces wrong judgments. It is worse than refusing to measure.
- Wrap the whole function in try/except KeyError/AttributeError. This is speculative error handling (CLAUDE.md 1.1), and it would also hide real bugs.

## Experiment

Extend tests/golden/test_experiment.py:79 so that, with the expected IDs R01/R02 present, each of the following asserts `_human('x1')['measured'] is False` without raising: (a) a header missing each one of the RUBRIC columns in turn, (b) a header missing review_id, (c) a 0-byte judgments.csv. Keep the existing case of short rows under a full header. Keep the positive case (full header and rows → A · all = 1/2). Also check that a header without `note` and full rubric rows is still measured. Before the fix, (a) and (b) should raise KeyError; after it, all of them pass. One narrow pytest run of that test, then the gate.

## Result

Ran the proposed experiment in `tests/golden/test_experiment.py::test_review_quality_is_unmeasured_unless_every_sampled_output_is_judged_exactly_once`, extended with (a) and (b) as a loop that drops each of `review_id` and the four RUBRIC columns in turn, (c) a 0-byte file, and a header with no `note`. The short-row and positive cases were kept. Before the fix (at `1513ad5`) the test failed on the first header case: dropping `review_id` raised `KeyError: 'review_id'` at comparison.py:246. A scratch run of the HEAD `_human` with the finding's header `review_id,evidence_support,answer_correct,topic_fit` raised `KeyError 'useful'`. The fix is the hypothesis's single header gate right after `csv.DictReader`, with `reader.fieldnames or ()`, returning `{'measured': False, 'reason': ..., 'missing_columns': [...]}`; `or ""` on values stays. Case (c) changed the gate's placement. The first version read `reader.fieldnames` after the `with` block, and the 0-byte file then raised `ValueError: I/O operation on closed file`. For an empty file, `fieldnames` stays None and re-reads the file on every access. The gate now reads `fieldnames` while the file is open. After that, the same scratch run returns `measured False, missing_columns ['useful']`, and the test passes, including the 0-byte file and the header without `note` (still measured, A · all = 1/2). The rest of `tests/golden/test_validation.py` and `tests/golden/test_experiment.py` passed (108). Results are in the commit that carries this page; the full gate is the server's and still pending.

## Unresolved limits

The docs do not say what DictReader.fieldnames is for an empty file. CPython returns None, so the check needs `or ()`, and experiment (c) confirms this. This research covers only schema and value shape. It does not cover whether key.json itself might be missing or malformed when judgments.csv exists (line 242 would raise); the finding does not raise that and review_packets writes both files together.
