# Review research — F8, cycle 2

집계 결과와 측정 조건은 Git에 보관하고, 원시 질문·정답·근거·OCR 전사와 레코드별 내보내기는 무시된 로컬 `artifacts/`에 보관한다.

복원 출처: 정리 전 `artifacts/review-round2/originals/` 또는 `d7d1682^`. 아래 수치와 검증 기록은 당시 실행의 역사적 관측이며 이번 작업에서 재측정한 결과가 아니다.

Draft research before the fix of review round 9 of PR #65, written 2026-10-18. It is not a verified fact or a shared rule: the review reads it with the fix.

## Problem

experiment.freeze() must leave either both artifacts (experiments/{id}/freeze.json and plans/{id}.json) or neither. A plan must never exist without its freeze record, because generation._plan_for loads plans by id without checking for freeze.json. A failed freeze must also be retryable. The round-9 reproduction breaks this: os.link() in _publish() (experiment.py:87) succeeds, then temp.unlink() in the finally (experiment.py:89) raises. When that happens on the plan, freeze() treats the exception as a link failure, deletes freeze.json and leaves the linked plan behind. A retry then fails on the plan collision. When it happens on freeze.json, freeze.json is left without a plan.

Trigger: repeat, rounds 8, 9.

- [P1] [P1] golden_pipeline/experiment.py:89 — successful publication can be reported as failed / when temporary-link cleanup raises / F8’s split, non-retryable state returns

## Failed fixes

- Cycle 1 (05c5196) moved every read (the evidence manifest, the prompt snapshot) before any write, published freeze.json first and the plan last through _publish() (temp sibling file + os.link + unlink in finally), and removed freeze.json if publishing the plan raised. The ordering was right. The rollback condition was wrong. It decides what to undo from 'an exception came out of _publish', but _publish has a fallible step after its commit point (temp.unlink after os.link). An exception therefore does not mean the destination was not created. Its tests covered a failure before publication (missing manifest) and a collision before linking (existing plan id), so neither exercised a failure after the link.

## Sources

### S1 — golden_pipeline/experiment.py freeze() and _publish()

- URL: golden_pipeline/experiment.py
- Retrieved: 2026-10-18
- Locator: lines 70-89
- Fragment: _publish(root / "freeze.json", ...)
    try:
        _publish(plan_path, plan_bytes)
    except BaseException:
        (root / "freeze.json").unlink()
        raise
...
    temp.write_bytes(data)
    try:
        os.link(temp, path)
    finally:
        temp.unlink()
- Applicability: The commit point (os.link) is followed by a fallible cleanup inside the same call, and the outer handler reads any exception as 'not published'.
- Counterevidence: If unlink never fails in practice, the split state is only reachable by fault injection; the reviewer nonetheless treats it as P1.
- Validation: After the fix, no statement that can raise runs after the plan's write completes, and the rollback deletes only the paths in `created`.

### S2 — Python Language Reference: The try statement (finally clause)

- URL: https://docs.python.org/3/reference/compound_stmts.html
- Retrieved: 2026-10-18
- Locator: 8.4 The try statement, finally clause
- Fragment: If an exception occurs in any of the clauses and is not handled, the exception is temporarily saved. The finally clause is executed. If there is a saved exception it is re-raised at the end of the finally clause. If the finally clause raises another exception, the saved exception is set as the context of the new exception. If the finally clause executes a return, break or continue statement, the saved exception is discarded.
- Applicability: When os.link succeeds, there is no saved exception, so the exception from temp.unlink in the finally is the only one that propagates. To the caller, a successful link and a failed link look the same.
- Counterevidence: Exception chaining keeps the context when both fail, but that does not help the success case.
- Validation: The reviewer's fault injection (the unlink of the temp file raises after the link) reproduces the split on HEAD.

### S3 — atomicwrites source (_move_atomic, AtomicWriter)

- URL: https://python-atomicwrites.readthedocs.io/en/latest/_modules/atomicwrites.html
- Retrieved: 2026-10-18
- Locator: _move_atomic POSIX branch; move_atomic docstring; AtomicWriter._open
- Fragment: def _move_atomic(src, dst):
        os.link(src, dst)
        os.unlink(src)  ... "Move src to dst. There might a timewindow where both filesystem entries exist." "If dst already exists, FileExistsError will be raised." "Both paths must reside on the same filesystem for the operation to be atomic." rollback failures are suppressed: try: self.rollback(f) except Exception: pass
- Applicability: The library cycle 1 cited as the model for link-then-unlink also unlinks after the link with nothing guarding it, so a cleanup failure after the link propagates from commit. The weakness belongs to the pattern, not just to this code. It suppresses exceptions only in rollback, not after commit.
- Counterevidence: atomicwrites publishes a single file, so a post-link exception there does not split two artifacts. The project is unmaintained.
- Validation: The ownership design has no step after the commit, so this weakness cannot apply.

### S4 — Python built-in open(): mode 'x'

- URL: https://docs.python.org/3/library/functions.html
- Retrieved: 2026-10-18
- Locator: open() mode table, 'x'
- Fragment: 'x' open for exclusive creation, failing if the file already exists
- Applicability: A successful open('xb') proves this call created the path, so the rollback may delete it. A failed open on an existing plan id leaves that plan alone.
- Counterevidence: The docs do not state an atomicity guarantee directly; that comes from the underlying O_EXCL (S5). On NFSv2, O_EXCL is unreliable.
- Validation: The existing test test_a_freeze_onto_an_existing_plan_id_keeps_that_plan_and_writes_no_record passes: FileExistsError, existing bytes unchanged, no freeze.json.

### S5 — open() O_CREAT|O_EXCL semantics (Open Group text quoted)

- URL: https://zenn.dev/tn_a/articles/system-call-open
- Retrieved: 2026-10-18
- Locator: O_EXCL description quoting the Open Group open() page
- Fragment: If O_CREAT and O_EXCL are set, open() shall fail if the file exists. The check for the existence of the file and the creation of the file if it does not exist shall be atomic with respect to other threads executing open() naming the same filename in the same directory with O_EXCL and O_CREAT set.
- Applicability: This is the guarantee behind ownership: only one caller can create the path, and it knows it did.
- Counterevidence: This is a secondary page quoting POSIX. Atomicity is guaranteed only against other O_EXCL opens, and NFSv2 does not support O_EXCL (SEI CERT).
- Validation: As S4.

### S6 — golden_pipeline/plan.py pool-plan write

- URL: golden_pipeline/plan.py
- Retrieved: 2026-10-18
- Locator: line 69
- Fragment: with path.open("x", encoding="utf-8") as f:
- Applicability: The repository already publishes plans by exclusive creation directly, with no temp file, so the fix reuses an existing idiom (written as binary 'xb' so that the recorded SHA-256 matches the bytes on disk).
- Counterevidence: The pool-plan write has no rollback, because it writes only one artifact.
- Validation: The plan's SHA-256 in freeze.json equals storage._sha256(plan file) in the retry test.

## Claims

- C1 (source; S1): freeze()'s rollback deletes freeze.json whenever _publish(plan_path) raises, but _publish can raise after os.link has already created the plan, so the rollback can delete the record of a plan that exists.
- C2 (source; S1, S2): An exception raised in a finally clause after a successful step propagates as the only exception, so the caller cannot tell that the link succeeded.
- C3 (interpretation; S3): Link-then-unlink in atomicwrites leaves the same unlink after commit unguarded, so the cycle-1 pattern carried this failure in with it.
- C4 (interpretation; S4, S5, S6): Exclusive creation gives an ownership signal: if open('xb') returned, this call created the path and the rollback may remove exactly that path, while a pre-existing plan is never touched.
- C5 (interpretation; S1, S6): Creating freeze.json then the plan with open('xb'), recording each in `created` and unlinking exactly those on any exception, leaves no fallible step after the last commit and removes the temp file, the hard link and _publish().

## Core theory

A commit-then-cleanup sequence must not report failure after the commit has happened, and a rollback must undo only what the operation is known to have created. Python's try statement re-raises a saved exception at the end of finally, but 'if the finally clause raises another exception, the saved exception is set as the context of the new exception'. An exception from a finally that runs after a successful step therefore looks exactly like a failure of that step. Exclusive creation ('x': 'open for exclusive creation, failing if the file already exists'; POSIX O_CREAT|O_EXCL fails if the file exists, and the check and the creation are atomic with respect to other O_EXCL opens) gives a clear ownership signal: if open returned, this call created the file and may delete it.

## Applicability

golden_pipeline/experiment.py:70-89. The commit point inside _publish is os.link at line 87, and the fallible step after it is temp.unlink at line 89. The outer handler at lines 71-75 maps any exception from _publish(plan_path) to 'plan not created' and deletes freeze.json. The same thing at line 70 leaves freeze.json without a plan. Rewriting lines 70-89 as one try block with a `created` list and two open('xb') writes removes both paths. No reader lists outputs/plans (a grep of golden_pipeline finds only plan.py:31,76 and experiment.py:65, all by id), so nothing depends on the temp files. Readers that load freeze.json (pro_packets, comparison.py) also load the plan and compare SHA-256 values, so a missing plan stops them.

## Hypothesis

The rollback in freeze() infers which artifacts exist from where an exception came from, not from which artifacts this call actually created. _publish() has a fallible cleanup step after its commit point (os.link), so 'raised' does not mean 'not published'. The fix is to undo by ownership, with no step after the last commit. Create each file directly with exclusive creation (path.open('xb'), the idiom plan.py:69 already uses for pool plans), freeze.json first and the plan last. Append each path to a `created` list as soon as its open succeeds. On any exception, unlink exactly the paths in `created` and re-raise. That removes the temp file, the hard link and _publish(), so nothing can fail after a file is committed. If the plan id is already taken, open('xb') raises before the plan path is recorded, so only freeze.json is removed and the existing plan is untouched.

## Counterevidence

- Without the temp file, a hard kill (not an exception) while the plan is being written leaves a truncated plan beside a complete freeze.json. load_plan parses the JSON, so a truncated object fails to load instead of being silently used. The one edge is a prefix that ends exactly at the closing brace, which _plan_for would accept even though its SHA-256 differs from the record. Under the cycle-1 design, a hard kill between the two links already left freeze.json behind and blocked retries, so neither design survives a hard kill cleanly.
- If an unlink inside the rollback itself fails, the state is split again. That is a second failure during error handling, and neither design guards against it; rule 1.1 argues against adding more layers for it.
- Cycle 1 rejected 'reorder only with open(x)' because a failure partway through writing leaves a truncated plan and blocks retries. That reasoning assumed no rollback of the plan. With ownership rollback, the plan this call created is removed on any exception, so the objection no longer applies.

## Alternatives

- Keep _publish and make the cleanup after the link best-effort (`with contextlib.suppress(OSError): temp.unlink()`, applied after the link and on the failure path). It is a smaller diff and fixes the reviewer's reproduction, but it leaves a stray hidden hard link to the plan in outputs/plans/ and keeps the unchecked dependence on hard links (NTFS, same volume, the team VM's filesystem). It also suppresses only OSError, so a test that raises a different type would still split the state. This is the second choice.
- Move temp.unlink out of _publish to after both links have succeeded in freeze(). freeze() would still raise after a complete, consistent publication (the 'reported as failed' half of the finding), and a retry would collide with its own successful freeze. Rejected.
- Make _plan_for require freeze.json for experiment plans. That adds a branch on every load and does not restore retryability. Rejected, as in cycle 1.

## Experiment

Replace the post-link scenario with one that fits the new design. In tests/golden/test_experiment.py, monkeypatch pathlib.Path.open so that for outputs/plans/x1.json it calls the real open with 'xb', closes the file and returns it. The file now exists, and the f.write that follows raises ValueError. Assert that freeze('x1','pool') raises, that neither plans/x1.json nor experiments/x1/freeze.json exists, then undo the patch and assert that a retry succeeds and record['plan']['sha256'] == storage._sha256(plan file). On the current HEAD 51ebc1b this test should fail: the patched open never touches plans/x1.json there (the plan comes from os.link), so make the temp unlink raise instead, as the reviewer described, and expect freeze.json to be gone and the plan to be present. Keep the two existing cycle-1 tests (missing manifest; existing plan id keeps its bytes and writes no record). They should pass unchanged. Run test_experiment.py once, then the gate.

## Result

Reproduced the reviewer's scenario on HEAD `065063a` (code as at `51ebc1b`) with a throwaway test, deleted afterwards. It patched `pathlib.Path.unlink` to raise only for the temporary `.x1.json.*.tmp`. `freeze()` raised PermissionError, the plan existed, and freeze.json did not. A retry raised `FileExistsError [WinError 183]` on `plans/x1.json`. The proposed experiment is `tests/golden/test_experiment.py::test_a_freeze_that_fails_after_creating_the_plan_removes_what_it_created_and_can_be_retried`. It patches `Path.open` to return the plan's file already closed. Run against the HEAD `experiment.py`, it failed with `DID NOT RAISE ValueError`, as predicted: the plan came from `os.link`, so the patched open never touched it. The fix follows the hypothesis. `_publish`, the temp file and the hard link are gone. `experiment.create_all({path: bytes})` creates each file with `open("xb")`, records the path as soon as the open returns, and on any exception unlinks exactly the recorded paths and re-raises. One deviation was needed: the path is recorded before entering `with`, not inside it. The experiment's closed file makes `with` itself raise, which would have left the plan unrecorded. After the fix the new test passes, and so do the two cycle-1 tests, unchanged (missing manifest; an existing plan id keeps its bytes and writes no record). Same rule elsewhere: `pro_packets` (14 exclusive files written in a loop) and `review_packets` (`key.json`, `packet.md`, `judgments.csv` after `mkdir`) now also publish through `create_all`, so a failed write leaves nothing that blocks a rerun. `tests/golden/test_experiment.py` and `test_cli.py` gave 47 passed, in the commit that carries this page; the full gate is the server's and still pending.

## Unresolved limits

A double failure (the rollback's unlink fails) is not covered. A hard kill during the plan write leaves freeze.json and a truncated plan that has to be deleted by hand before retrying. Concurrent freezes with the same id are not considered (single-user CLI). The prediction that the test fails on HEAD has not been run.
