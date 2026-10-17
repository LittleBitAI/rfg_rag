# Review research — F4, cycle 1

Draft research before the fix of review round 2 of PR #65, written 2026-10-18. It is not a verified fact or a shared rule: the review reads it with the fix.

## Problem

`review_packets()` is supposed to quote only the evidence from the frozen experiment, meaning the plan whose SHA-256 is in freeze.json. At comparison.py:177 it reloads outputs/plans/{plan_id}.json from disk as the file is now and throws away the hash `plan.load_plan` returns. Each sampled item's quoted evidence then comes from that copy (`_packet` -> `validation.evidence_units(item, bundles[...])`, comparison.py:227). If the plan file is edited after the runs, blinded reviewers judge evidence that is not what generated and validated the candidates. The rule it breaks: everything the comparison reads must be tied to the frozen hashes at the moment it is read.

Trigger: repeat, rounds 1, 2.

- [P1] [P1] golden_pipeline/validation.py:122 — a ceiling interruption still discards settled sub-call results within one candidate

## Failed fixes

- Round 1 (89f54e6) added `_checked_runs`/`_check_run` (comparison.py:65-105). This compares each run manifest's recorded `generation.plan_id/plan_sha256/topic_spec_sha256` with freeze.json, rejects outputs on bundles outside the train part, and checks prompt hashes and settings. Both sides of that comparison are records written in the past. Neither is the plan file `review_packets` parses at packet time. The fix answered 'are these the frozen runs?' and never listed what `review_packets` itself reads from disk, so the second read of the plan file (comparison.py:177) stayed unchecked.
- The round-1 test (tests/golden/test_cli.py around 180-205) fakes a mismatch by writing a wrong hash into freeze.json (`write_freeze(plan_sha='0'*64)`) and only runs `compare`. It never edits the plan file after valid runs and never runs `review-packets`, so the case round 2 raised was never exercised.
- The cycle-1 research (291ed08) found the same cause, but no code fix followed it: comparison.py:177 at HEAD still reads `planned, _ = plan.load_plan(...)`. The finding stands because the fix was never made, not because a fix was tried and failed.

## Sources

### S1 — CWE-367: Time-of-check Time-of-use (TOCTOU) Race Condition

- URL: https://cwe.mitre.org/data/definitions/367.html
- Retrieved: 2026-10-18
- Locator: Description; Potential Mitigations
- Fragment: "The product checks the state of a resource before using that resource, but the resource's state can change between the check and the use in a way that invalidates the results of the check." Mitigation: "Ensure that locking occurs before the check, as opposed to afterwards, such that the resource, as checked, is the same as it is when in use." Also: "The most basic advice for TOCTOU vulnerabilities is to not perform a check before the use. This does not resolve the underlying issue of the execution of a function on a resource whose state and identity cannot be assured, but it does help to limit the false sense of security given by the check." Shrinking the window "will not fix the problem, but it could make it more difficult for an attack to succeed."
- Applicability: The plan file's state at generation was checked through the recorded manifest hash, but it is used later at comparison.py:177/227, after it may have changed. The check result is stale at the point of use.
- Counterevidence: CWE frames this as a race between processes or threads. Here the gap is a later manual edit, so the locking mitigations do not apply, only the principle that the resource checked must be the resource used.
- Validation: After the fix, review_packets hashes the same plan load that feeds `_packet` and compares it with freeze.json in the same call. The new test edits p3.json after valid runs and expects ValueError with no review folder written.

### S2 — SLSA v1.2 — Build: Verifying artifacts

- URL: https://slsa.dev/spec/v1.2/verifying-artifacts
- Retrieved: 2026-10-18
- Locator: Step 1, "Given an artifact and its provenance"
- Fragment: "Verify the envelope's signature using the roots of trust ..." then "Verify that statement's `subject` matches the digest of the artifact in question." These steps assume the verifier has been bootstrapped with roots of trust. If provenance is not in the recommended format, "the verifier SHOULD perform equivalent checks".
- Applicability: freeze.json works like the root of trust and the run manifests like provenance. Round 1 checked provenance against the root but not that the artifact in hand, the plan file read at packet time, matches the trusted digest.
- Counterevidence: SLSA covers signed supply-chain attestations. golden_pipeline has no signatures, so the analogy covers only the step of matching the digest of the artifact in hand.
- Validation: After the fix, review_packets compares the SHA-256 of the plan it parses with freeze.json's plan.sha256, the 'subject matches the artifact in question' step. The new test shows a changed file is refused.

### S3 — golden_pipeline/comparison.py (review_packets, _check_run, _packet)

- URL: golden_pipeline/comparison.py
- Retrieved: 2026-10-18
- Locator: lines 85-92 (_check_run pinned tuple), 175-178 (review_packets), 226-227 (_packet)
- Fragment: `pinned = (record["plan"]["plan_id"], record["plan"]["sha256"], record["topic_specs"][topic])` compared with the manifest's `generation` fields; `planned, _ = plan.load_plan(record["plan"]["plan_id"])`; `units = validation.evidence_units(item, bundles[item["bundle_id"]])`
- Applicability: Shows that the only check compares the manifest with freeze.json, and that the plan contents used for packet evidence are loaded with their hash thrown away.
- Counterevidence: `_checked_runs` runs inside review_packets for every topic, so a run built from a different plan is still refused. The gap is only an edit to the plan file after valid runs.
- Validation: The fixed line keeps the hash and raises when it differs from record['plan']['sha256'] before `folder.mkdir()`. The new test fails on HEAD and passes after the fix.

### S4 — Existing plan-hash guards in golden_pipeline

- URL: golden_pipeline/experiment.py
- Retrieved: 2026-10-18
- Locator: experiment.py:79-86 (pro_packets); report.py:43-45 (compare); plan.py:146-148 (asked_document); validation.py:255-257
- Fragment: pro_packets: `planned, sha = plan.load_plan(experiment_id)` ... `frozen = {"계획": record["plan"]["sha256"], ...}` ... `raise ValueError(f"실험 {experiment_id} 를 고정한 뒤 바뀌었습니다: {changed}")`. report.compare: `planned, current_sha = plan.load_plan(plan_id)` / `if current_sha != plan_sha: raise ValueError(...)`. experiment.estimate:214 also discards the hash, but it runs before any run exists.
- Applicability: The repository already uses this pattern wherever plan contents feed a result. review_packets is the exception among post-run consumers, so the fix copies the pattern.
- Counterevidence: experiment.estimate discards the hash too. It is a pre-run cost estimate with no frozen runs to contradict, so it is not a sibling of this bug.
- Validation: The fix's shape and error style match pro_packets. A grep for `load_plan(` with `, _ =` after the fix shows only estimate and improvement.py:342 (a train-part listing) left unguarded.

### S5 — tests/golden/test_cli.py round-1 test

- URL: tests/golden/test_cli.py
- Retrieved: 2026-10-18
- Locator: write_freeze helper and test_compare_refuses_runs_outside_the_frozen_plan_or_train_assignment (around lines 180-205)
- Fragment: `write_freeze(plan_sha="0" * 64)` / `with pytest.raises(ValueError, match="고정한 계획"): golden("compare", "x1")`
- Applicability: The test changes the freeze side, not the plan file, and only runs compare, so it cannot catch review_packets reading a changed plan.
- Counterevidence: The test is still valid for what it guards (a run made under a different plan). It is incomplete, not wrong.
- Validation: The new test edits outputs/plans/p3.json after the runs and calls review-packets. It must fail on HEAD and pass after the fix, which shows it covers the round-2 case.

## Claims

- C1 (source; S1): A check holds only if the resource checked is, when used, the same as when it was checked.
- C2 (interpretation; S1, S2): Checking recorded provenance is not enough: the digest of the artifact actually used must match the trusted digest.
- C3 (source; S3): The round-1 guard compares only the run manifest's recorded plan hash with freeze.json, two records, and never hashes the plan file read later.
- C4 (source; S3): review_packets builds packet evidence from the current plan file and throws away the hash load_plan returns, so an edit after the runs goes unnoticed.
- C5 (source; S4): The other post-run readers of plan contents in golden_pipeline already compare load_plan's hash with the pinned one; review_packets is the exception.
- C6 (interpretation; S5): The round-1 test fakes the mismatch on the freeze side and only for compare, so it could not have caught the round-2 finding.

## Core theory

A check only counts for a resource in the state it is in when it is used. CWE-367 says a resource whose state can change between the check and the use invalidates the check, and recommends making sure the resource, as checked, is the same as it is when in use. SLSA artifact verification checks the provenance and also that the provenance subject matches the digest of the artifact being consumed. A valid provenance record alone does not vouch for the artifact in hand.

## Applicability

freeze.json plays the trusted root and the run manifests the provenance. Round 1 checked provenance against the root but skipped the subject-digest step for the artifact actually consumed: the plan file read at comparison.py:177 and used at comparison.py:227. The window between check and use is the time between generating the runs and running review-packets, which can be days. `compare()` does not parse plan contents. It uses freeze.json parts, run files through report._collect/read_validated, and loop report.json. So the new guard is needed in review_packets only. Other plan readers already guard this way: experiment.pro_packets:79-86, report.compare:43-45, plan.asked_document:146-148, validation.py:255-257.

## Hypothesis

The guard checks recorded provenance (manifest against freeze), not the bytes that are actually used. In comparison.py, `review_packets` is the only code that parses the plan file's contents, and it never ties those contents to the frozen hash. Fix: `planned, sha = plan.load_plan(record['plan']['plan_id'])`, then raise ValueError if `sha != record['plan']['sha256']`. Do this before `_checked_runs`/sampling and before `folder.mkdir()`, so nothing is written on refusal. This mirrors experiment.pro_packets (experiment.py:79-86) and report.compare (report.py:43-45).

## Counterevidence

- CWE-367 is about concurrent races. Here the change is a later edit by a person, so only the principle carries over (check the resource as used), not the threat model or the locking mitigations.
- plan.load_plan reads the file twice (`_read_json`, then `_sha256` on the same path). Even after the fix, a change between those two reads is possible in theory. That window is tiny, every existing caller shares it, and the reviewer did not raise it.
- validation.py:255-257 already refuses to validate if the plan changed since generation. So accepted items were validated against the frozen plan, and the remaining risk is only what review_packets reads later. That supports the hypothesis rather than weakening it, but it means compare's numbers are not affected.

## Alternatives

- Add an `expected_sha` argument to `plan.load_plan` so every caller is checked in one place. That centralises the check, but five call sites already check inline with their own messages, so it is a wider refactor than the finding needs. Not first.
- Copy each bundle's evidence text into the run or into freeze.json and build packets from that copy. This removes the dependency on the plan file but adds storage and changes formats. Elsewhere golden_pipeline handles a changed plan by refusing and telling the user to make a new run, and a hash refusal matches that.
- Call the check from `_checked_runs` so compare also refuses a changed plan. compare does not read plan contents, so this would refuse a state that does not change its numbers. It could be added for consistency, but the finding does not require it.

## Experiment

Add one test to tests/golden/test_cli.py using the existing planned/api fixtures. Run B b1 on p3 with `--part train`, call `write_freeze()` with correct hashes, then rewrite outputs/plans/p3.json so a train bundle's unit text changes. `golden('review-packets', 'x1')` must raise ValueError (match the frozen-plan message), and outputs/experiments/x1/review must not exist. On the current code the same steps should instead write packet.md quoting the edited text, which confirms the hypothesis. Run only this test, then the gate once.

## Result

Observed, not verified (draft). This page's text researches the review-packets plan hash (round-2 F1), not the round-2 F4 finding it is listed under (sub-call results lost inside one candidate's verdict). Both were run.

- Plan hash: the experiment in this page is `tests/golden/test_cli.py::test_review_packets_refuse_a_plan_file_changed_after_the_freeze`. It failed on 9272eca (`DID NOT RAISE`; the review folder was written from the edited plan) and passes after the fix (see the F1 page).
- F4 as raised: `tests/golden/test_cli.py::test_resuming_a_candidate_refused_mid_verdict_reuses_its_settled_calls`. In it, the bond candidate's first validator call settles with output that breaks the contract, and the retry is refused by the ledger (`BudgetExceeded`). The candidate stays pending; `resume` then runs. On 9272eca, resume re-sent the settled first call, giving 4 validator requests where 3 were needed (`assert 4 == 3`). That confirms the settled sub-call result was lost.
- Fix (commit after 9272eca): `validation._reply` records each call's request SHA-256, attempt and output in the validation record. `resume_validation` passes these as `settled`, so `_reply` reuses a settled output instead of calling again and does not count its cost twice. The test then passed, with exactly 3 requests and the candidate rejected for validator output error.
- All validator, judge, document-batch and multi-hop sub-calls go through `_reply`, so there are no other call sites. release screening passes an empty `settled` because release refuses `--experiment`.

## Unresolved limits

Nothing was run; there is no shell in this turn. I did not check whether review_packets' other inputs are tied to the freeze: candidates.jsonl/accepted.jsonl/rejected.jsonl read by `_sample` for the items themselves, and loop report.json cost fields used by `_costs`/`_reconcile`. They may draw the same kind of finding later, but they are separate from F1. freeze.json itself is trusted and not protected.
