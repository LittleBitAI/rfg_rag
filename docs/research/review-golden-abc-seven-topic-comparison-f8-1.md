# Review research — F8, cycle 1

Draft research before the fix of review round 8 of PR #65, written 2026-10-18. It is not a verified fact or a shared rule: the review reads it with the fix.

## Problem

experiment.freeze() publishes plans/{id}.json (experiment.py:51-53) before reading the evidence manifest (line 54), taking the prompt snapshot (line 61) and exclusively creating experiments/{id}/freeze.json (line 67). If any step after the plan write fails, the plan stays published with no freeze record. generation._plan_for (generation.py:495) and validation.py:217 load any plan by id, so the orphan plan can be used without frozen provenance. A retry hits FileExistsError at plan_path.open('x'), so the experiment can no longer be frozen. Invariant broken: a plan published under an experiment id must exist only if its complete freeze record exists, and a failed freeze must leave nothing behind so it can be retried.

Trigger: backstop, rounds 8.

- [P1] [P1] golden_pipeline/experiment.py:52 — freeze publication is non-atomic / when a later dependency read or manifest write fails / the experiment becomes non-retryable and can be run without frozen provenance

## Failed fixes

- No fix for F8 has been tried yet (correction: none yet). It got through earlier rounds because the only failure test, test_freeze_refuses_a_topic_with_an_empty_part_and_writes_no_plan (tests/golden/test_experiment.py:53), fails during partition checking, before any write. No test covers a failure after the plan write, so the write-then-read order was never exercised.

## Sources

### S1 — golden_pipeline/experiment.py freeze()

- URL: golden_pipeline/experiment.py
- Retrieved: 2026-10-18
- Locator: lines 51-69
- Fragment: plan_path = storage._child(storage.OUTPUTS / "plans", f"{experiment_id}.json")
    with plan_path.open("x", encoding="utf-8") as f: ...
    evidence_manifest = storage._read_json(storage.OUTPUTS / "evidence" / pool["evidence_run"] / "manifest.json") ... "prompts": storage.snapshot(storage.PROMPTS) ... with (root / "freeze.json").open("x", encoding="utf-8") as f:
- Applicability: The plan is written before the reads and steps that can fail, with no rollback.
- Counterevidence: none given
- Validation: After the fix, no write happens before the last read, and the plan link is the last statement that can fail.

### S2 — generation._plan_for and plan.load_plan

- URL: golden_pipeline/generation.py
- Retrieved: 2026-10-18
- Locator: generation.py:495-500; plan.py:74-77; validation.py:217
- Fragment: def _plan_for(plan_id, topic):
    plan, plan_sha = plans.load_plan(plan_id) ... load_plan: path = storage._child(storage.OUTPUTS / "plans", f"{plan_id}.json"); return storage._read_json(path), storage._sha256(path)
- Applicability: Generation and validation load any plan by id and never look for freeze.json, so an orphan plan is usable. load_plan hashes the file bytes, so the recorded hash must come from the file, not the in-memory string.
- Counterevidence: Readers of freeze.json (pro_packets, comparison.py:26,176) also need the plan, so a freeze.json without a plan is not usable.
- Validation: The test checks record['plan']['sha256'] == storage._sha256(plan file).

### S3 — Python os module docs: os.rename, os.replace

- URL: https://docs.python.org/3/library/os.html
- Retrieved: 2026-10-18
- Locator: os.rename / os.replace entries
- Fragment: os.rename: "On Windows, if dst exists a FileExistsError is always raised. The operation may fail if src and dst are on different filesystems." "On Unix, ... If both are files, dst will be replaced silently if the user has permission. ... If successful, the renaming will be an atomic operation (this is a POSIX requirement)." os.replace: "If dst exists and is a file, it will be replaced silently if the user has permission. The operation may fail if src and dst are on different filesystems."
- Applicability: Rules out rename and replace for no-overwrite publishing of plans across Windows and the Linux VM.
- Counterevidence: rename does refuse to overwrite on Windows, so a Windows-only codebase could use it; this repository also runs on Linux (CLAUDE.md section 6).
- Validation: The collision test on Linux would show replacement if rename were used.

### S4 — POSIX link() (The Open Group Base Specifications)

- URL: https://pubs.opengroup.org/onlinepubs/9799919799/functions/link.html
- Retrieved: 2026-10-18
- Locator: DESCRIPTION; ERRORS [EEXIST]
- Fragment: "The link() function shall atomically create a new hard link for the existing file" ... "If link() fails, no link shall be created and the link count of the file shall remain unchanged." [EEXIST] "The path2 argument resolves to an existing directory entry or refers to a symbolic link."
- Applicability: os.link on Linux publishes the plan in one step and fails rather than overwriting an existing plan.
- Counterevidence: The page does not literally say link never replaces; that follows from the EEXIST condition together with the no-link-on-failure sentence.
- Validation: The pre-existing-plan test raises FileExistsError and leaves the existing bytes unchanged.

### S5 — CreateHardLinkW function (Microsoft Learn)

- URL: https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createhardlinkw
- Retrieved: 2026-10-18
- Locator: summary; Remarks
- Fragment: "This function is only supported on the NTFS file system, and only for files, not directories." "all hard links to a file must be on the same volume." Technology table: "Resilient File System (ReFS) | No"; "SMB 3.0 does not support creation of hard links on shares with continuous availability capability."
- Applicability: os.link on Windows needs NTFS and the same volume, hence the temporary folder under OUTPUTS.
- Counterevidence: The page does not state the error raised when lpFileName exists; FileExistsError on Windows is expected from Python's error mapping but not quoted here.
- Validation: The Windows gate run of the collision test confirms FileExistsError from os.link.

### S6 — atomicwrites README

- URL: https://slackbuilds.org/repository/14.2/python/atomicwrites/
- Retrieved: 2026-10-18
- Locator: README, overwrite behaviour
- Fragment: It uses a temporary file in the same directory as the given path. ... On POSIX, it will use rename if files should be overwritten, otherwise a combination of link and unlink. ... there's a timewindow where the file might be available under two entries in the filesystem; permissions of the target file may change this way.
- Applicability: Established pattern: temporary file plus link for no-overwrite publishing. The window with two names is harmless here because the temporary name sits in a TemporaryDirectory that no reader looks at.
- Counterevidence: The project is marked unmaintained; it is used here only as evidence of the pattern, not as a dependency.
- Validation: No reader looks at the temporary folder (grep found no glob over outputs/plans or OUTPUTS root).

### S7 — OpenStack Swift: Make object creation more atomic in Linux

- URL: https://opendev.org/openstack/swift/commit/773edb4a5dd22b22f5fcab57820bcbdd4176dfcd
- Retrieved: 2026-10-18
- Locator: commit message
- Fragment: Unlike os.rename(), linkat() cannot overwrite destination path if it already exists.
- Applicability: A production system that uses link rather than rename for no-overwrite publishing.
- Counterevidence: Swift uses O_TMPFILE on Linux, which Windows does not have; this fix uses a named temporary file instead.
- Validation: As S4.

### S8 — tests/golden/test_experiment.py existing freeze failure test

- URL: tests/golden/test_experiment.py
- Retrieved: 2026-10-18
- Locator: lines 53-59
- Fragment: def test_freeze_refuses_a_topic_with_an_empty_part_and_writes_no_plan ... with pytest.raises(ValueError, match="numeric 묶음이 모자랍니다"): experiment.freeze("x1", "pool") ... assert not (outputs / "outputs/plans/x1.json").exists()
- Applicability: Only a failure before any write is covered, which is why the post-write failure was not caught.
- Counterevidence: none given
- Validation: The new tests cover the post-write failure and the publish collision.

### S9 — cli._config_file temporary folder under OUTPUTS

- URL: golden_pipeline/cli.py
- Retrieved: 2026-10-18
- Locator: lines 147-155
- Fragment: with tempfile.TemporaryDirectory(dir=storage.guard(storage.OUTPUTS)) as folder: path = Path(folder) / "config.json"
- Applicability: An existing pattern to reuse for the plan's temporary file: same volume as outputs/plans, inside the output guard, and cleaned up automatically.
- Counterevidence: none given
- Validation: After freeze, no stray temporary file remains under OUTPUTS.

## Claims

- C1 (source; S1, S2): freeze() publishes the plan before steps that can fail, and generation/validation use any published plan without needing freeze.json, so a failure after the plan write leaves a usable, unbacked plan and the experiment cannot be retried.
- C2 (source; S3, S4, S6, S7): For no-overwrite publishing on both Linux and Windows, a hard link from a temporary file is the right step; os.rename overwrites on Unix and os.replace overwrites everywhere.
- C3 (interpretation; S4, S5): os.link fails without creating anything when the target exists, so a plan-id collision with an existing pool plan is refused and rolled back rather than overwritten.
- C4 (interpretation; S2): The recorded plan SHA-256 must be computed from the written file, not the in-memory string, because Windows text-mode writes change newlines and load_plan hashes the file bytes.
- C5 (interpretation; S5, S9): Putting the temporary file in a TemporaryDirectory under OUTPUTS meets the same-volume and NTFS-only requirements for hard links and reuses an existing repository pattern.
- C6 (interpretation; S8): The finding got through earlier rounds because the only freeze failure test fails before any write.

## Core theory

To publish a file without letting a reader see a partial or unbacked state, prepare it under a temporary name and expose it with a single atomic directory operation. When the target must not be overwritten, use link() rather than rename(): POSIX link() 'shall atomically create a new hard link' and fails with EEXIST if path2 exists, creating no link when it fails. Python's os.rename overwrites silently on Unix but always raises FileExistsError on Windows, and os.replace overwrites on both, so neither gives portable no-overwrite publishing. A two-file commit cannot be made atomic, so one file has to be the commit point and written last, after everything it depends on.

## Applicability

In golden_pipeline/experiment.py freeze(): move storage._read_json(...evidence manifest...) and storage.snapshot(storage.PROMPTS) above any write. Serialise `frozen` into a file in a tempfile.TemporaryDirectory(dir=storage.guard(storage.OUTPUTS)), reusing the cli._config_file pattern (cli.py:147-155). That keeps the temporary file on the same volume as outputs/plans, which hard links require, and the folder cleans up the temporary name. Hash that file with storage._sha256 for record['plan']['sha256']. Windows text-mode writes turn '\n' into '\r\n', so hashing the in-memory string would not match load_plan's hash of the file. Write freeze.json with open('x'), then os.link(temp, plan_path) inside try/except that unlinks freeze.json and re-raises. plan_path is in outputs/plans, a namespace shared with pool plans, so an id collision is caught by the link's FileExistsError and the rollback runs. Consumers that read freeze.json (experiment.pro_packets, comparison.py:26, 176) also load the plan, so a freeze.json left without a plan is never used.

## Hypothesis

The cause is ordering. The artifact that consumers can see (the plan) is written first, and the steps that can still fail (the manifest read, the prompt snapshot, the freeze.json creation) run after it, with no rollback. The fix is to do every read before any write, and to make the plan the last thing published, using one no-overwrite step: write the plan bytes to a temporary file under OUTPUTS, record that file's SHA-256 in freeze.json, create freeze.json with open('x'), then os.link(temp, plan_path). If the link fails, delete freeze.json and re-raise. Then a plan file existing means its freeze record exists, and _plan_for needs no new check.

## Counterevidence

- Hard links are NTFS-only on Windows (not ReFS) and need the same volume. The repository on a local Windows PC (NTFS) and the Linux VM (likely ext4) should be fine, but this is assumed, not checked.
- If the process is killed (not an exception) between creating freeze.json and the link, no rollback runs. freeze.json is left without a plan and blocks a retry at open('x') until someone deletes it by hand. It cannot be used, but the experiment is not retryable in that case.
- Repository rule 1.1 forbids speculative error handling. The rollback is justified only because the reviewer's reproduction (missing manifest) and a plan-id collision are real, reachable failures.

## Alternatives

- Reorder only (all reads first, freeze.json then plan with open('x')) without temp+link: smaller, but a failure partway through writing the plan leaves a truncated plan, and the experiment cannot be retried. Acceptable fallback if hard links prove unavailable.
- os.rename(temp, plan_path): refuses to overwrite on Windows (FileExistsError) but silently replaces on Linux, so it would clobber an existing pool plan on the team VM. Rejected.
- os.replace: overwrites on every platform. Rejected because plans must never be overwritten (README.md:291).
- Make _plan_for require freeze.json for experiment plans: needs a way to tell experiment plans from pool plans (the 'stratified_from' key) and adds a branch on every load, while leaving the retry deadlock. Rejected in favour of fixing the publication order.
- Move the plan into experiments/{id}/ so one folder is the commit point: changes plan.load_plan and every consumer. Larger diff than the finding needs.

## Experiment

Add to tests/golden/test_experiment.py: (1) build the pool with write_pool, delete outputs/evidence/ev/manifest.json, assert freeze('x1','pool') raises FileNotFoundError and that neither outputs/plans/x1.json nor outputs/experiments/x1/freeze.json exists; restore the manifest and assert freeze succeeds and record['plan']['sha256'] == storage._sha256(plan file). (2) Pre-create outputs/plans/x1.json with known bytes, assert freeze raises FileExistsError, freeze.json is absent and the existing plan bytes are unchanged. Before the fix, test (1) fails at the retry with FileExistsError and test (2) leaves freeze.json behind. Run the gate once on Windows. os.link on NTFS in tmp_path covers the Windows link path.

## Result

Ran the experiment as `tests/golden/test_experiment.py::test_a_freeze_that_fails_after_planning_leaves_nothing_and_can_be_retried` (1) and `::test_a_freeze_onto_an_existing_plan_id_keeps_that_plan_and_writes_no_record` (2). Before the fix (HEAD `12597db`), (1) failed: after the FileNotFoundError, `outputs/plans/x1.json` existed and `freeze.json` did not. A throwaway test (deleted afterwards) restored the manifest and retried, and got `FileExistsError [Errno 17] File exists: …\outputs\plans\x1.json`. (2) passed before the fix, not failed as predicted. In the old order the plan's `open("x")` came first and raised before freeze.json was written. It is kept because it guards the rollback in the new order. The fix follows the hypothesis. `freeze()` builds the plan bytes and reads the evidence manifest and prompt snapshot before any write. The plan SHA-256 is taken from those bytes, which are written as binary, so the file and the record hash the same bytes. It publishes freeze.json, then the plan, each with `experiment._publish` (temporary sibling file, then `os.link`, which never overwrites). If the plan cannot be linked, freeze.json is removed and the error re-raised. After the fix, (1) and (2) pass on Windows (NTFS tmp_path, so the hard-link path ran), as do the rest of `test_experiment.py` and `test_cli.py` (46 passed). Same rule elsewhere: `pro_packets` read topic specs and filled the template between its exclusive writes, and `review_packets` built `packet.md` after `mkdir()` and `key.json`. Both now finish every read and render before the first write. Results are in the commit that carries this page; the full gate is the server's and still pending.

## Unresolved limits

Not checked: the filesystem of the team VM's outputs directory supports hard links. A hard kill between creating freeze.json and the link still needs a manual delete. Two concurrent freeze() calls with the same id are not considered: it is a single-user CLI.
