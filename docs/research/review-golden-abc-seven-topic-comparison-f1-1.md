# Review research — F1, cycle 1

Draft research before the fix of review round 2 of PR #65, written 2026-10-18. It is not a verified fact or a shared rule: the review reads it with the fix.

## Problem

The A/B/C comparison (`compare`, `review-packets`) must only use what the frozen experiment defined: the plan whose SHA-256 is in freeze.json, the train bundles and the frozen prompts and topic specs. Round 1 found that runs were scored without that check. Round 2 found that `review_packets()` loads the plan file from disk as it is now (comparison.py:177), discards the hash `plan.load_plan` returns, and takes each sampled item's quoted evidence from it (`_packet` -> `validation.evidence_units(item, bundles[...])`). If the plan file is edited after the runs, the blinded reviewers judge evidence that is not what generated and validated the candidates.

Trigger: repeat, rounds 1, 2.

- [P1] [P1] golden_pipeline/comparison.py:177 — review packets can use a plan that no longer matches the frozen hash

## Failed fixes

- Round 1 fix (89f54e6) added `_checked_runs`/`_check_run`. It compares each run manifest's recorded `generation.plan_id/plan_sha256/topic_spec_sha256` with freeze.json, rejects outputs on validation or held-out bundles, and checks prompt hashes and settings. Both sides of that comparison are records of the past; neither is the plan file read at packet time. The fix treated the finding as 'are the runs the frozen runs' and never listed what `review_packets` itself reads from disk. The plan file is read twice over time, once at generation (hash recorded) and once at packet time (hash computed and thrown away), and only the first read is checked.
- The round-1 test (tests/golden/test_cli.py:203-205) fakes a plan mismatch by writing a wrong hash into freeze.json (`write_freeze(plan_sha='0'*64)`), and only for `compare`. It never edits the plan file on disk after valid runs, and never runs `review-packets` in that state, so the case round 2 raised was never exercised.

## Sources

### S1 — CWE-367: Time-of-check Time-of-use (TOCTOU) Race Condition

- URL: https://cwe.mitre.org/data/definitions/367.html
- Retrieved: 2026-10-18
- Locator: Description; Potential Mitigations
- Fragment: "The product checks the state of a resource before using that resource, but the resource's state can change between the check and the use in a way that invalidates the results of the check." Mitigation: "Ensure that locking occurs before the check, as opposed to afterwards, such that the resource, as checked, is the same as it is when in use." Also: "The most basic advice for TOCTOU vulnerabilities is to not perform a check before the use. This does not resolve the underlying issue of the execution of a function on a resource whose state and identity cannot be assured, but it does help to limit the false sense of security given by the check."
- Applicability: The plan file's state when the runs were generated was checked (via the recorded manifest hash), but it is used later at comparison.py:177 after it may have changed. The check result is stale at the point of use.
- Counterevidence: CWE frames this as a concurrency race between processes. Here the gap is a later manual edit, so only the principle (check the resource as used) carries over, not the locking mitigations.
- Validation: The fix computes the hash on the plan load that feeds `_packet` and compares it to freeze.json in the same call. The experiment edits the plan after valid runs and expects a refusal.

### S2 — SLSA v1.2 — Build: Verifying artifacts

- URL: https://slsa.dev/spec/v1.2/verifying-artifacts
- Retrieved: 2026-10-18
- Locator: Step 1, "Given an artifact and its provenance"
- Fragment: "Verify the envelope's signature using the roots of trust ..." then "Verify that statement's `subject` matches the digest of the artifact in question." These steps apply after the verifier has been bootstrapped with roots of trust. If the provenance is not in the recommended format, "the verifier SHOULD perform equivalent checks".
- Applicability: freeze.json works like the root of trust and the run manifests like provenance. Round 1 checked provenance against the root but not that the artifact in hand (the plan file read at packet time) matches the trusted digest.
- Counterevidence: SLSA is about supply-chain attestations with signatures. golden_pipeline has no signatures, and the analogy covers only the digest-of-the-artifact-in-hand step.
- Validation: After the fix, review_packets compares the digest of the plan it parses with freeze.json's plan.sha256, which is the 'subject matches artifact in question' step.

### S3 — golden_pipeline/comparison.py (review_packets, _check_run)

- URL: golden_pipeline/comparison.py
- Retrieved: 2026-10-18
- Locator: lines 85-92 (_check_run pinned tuple), 175-178 (review_packets), 218-230 (_packet)
- Fragment: `pinned = (record["plan"]["plan_id"], record["plan"]["sha256"], record["topic_specs"][topic])` compared with the manifest's `generation` fields; `planned, _ = plan.load_plan(record["plan"]["plan_id"])`; `units = validation.evidence_units(item, bundles[item["bundle_id"]])`
- Applicability: Shows that the only check compares the manifest with freeze.json, and that the plan contents used for packet evidence are loaded with their hash discarded.
- Counterevidence: none given
- Validation: The fixed line keeps the hash and compares it to record['plan']['sha256'] before writing.

### S4 — Existing plan-hash guards in golden_pipeline

- URL: golden_pipeline/experiment.py
- Retrieved: 2026-10-18
- Locator: experiment.py:79-86 (pro_packets); report.py:43-45 (compare); plan.py:146-148 (asked_document)
- Fragment: pro_packets: `planned, sha = plan.load_plan(experiment_id)` ... `frozen = {"계획": record["plan"]["sha256"], ...}` ... `raise ValueError(f"실험 {experiment_id} 를 고정한 뒤 바뀌었습니다: {changed}")`. report.compare: `planned, current_sha = plan.load_plan(plan_id)` / `if current_sha != plan_sha: raise ValueError(...)`
- Applicability: The repository already uses this idiom wherever plan contents are consumed. review_packets is the exception, so the fix copies this idiom.
- Counterevidence: none given
- Validation: The fix's shape and error style match these call sites.

### S5 — tests/golden/test_cli.py round-1 test

- URL: tests/golden/test_cli.py
- Retrieved: 2026-10-18
- Locator: lines 180-205 (write_freeze, test_compare_refuses_runs_outside_the_frozen_plan_or_train_assignment)
- Fragment: `write_freeze(plan_sha="0" * 64)` / `with pytest.raises(ValueError, match="고정한 계획"): golden("compare", "x1")`
- Applicability: The test changes the freeze side, not the plan file, and only checks compare, so it cannot catch review_packets reading a changed plan.
- Counterevidence: none given
- Validation: The new test edits outputs/plans/p3.json after the runs and checks review-packets.

## Claims

- C1 (source; S1): A check is only valid if the resource checked is, at the time of use, the same as when it was checked.
- C2 (interpretation; S1, S2): Verifying recorded provenance is not enough; the digest of the artifact actually consumed must match the trusted digest.
- C3 (source; S3): The round-1 guard compares only the run manifest's recorded plan hash with freeze.json, two records, and never hashes the plan file read later.
- C4 (source; S3): review_packets builds packet evidence from the current plan file and discards the hash load_plan returns, so an edit after the runs goes undetected.
- C5 (source; S4): Other consumers of plan contents in golden_pipeline already compare load_plan's hash with the pinned one; review_packets is the exception.
- C6 (interpretation; S5): The round-1 test fakes the mismatch on the freeze side and only for compare, so it could not have caught the round-2 finding.

## Core theory

A check is only valid for the resource that is then used, in the state it is in when used. CWE-367: a resource whose state can change between check and use invalidates the check. SLSA verification checks the provenance and also that the provenance subject matches the digest of the artifact being consumed. A valid provenance record alone does not vouch for the artifact in hand.

## Applicability

In comparison.py, freeze.json plays the role of the trust root and the run manifests the provenance. Round 1 verified provenance against the root (SLSA step 1-ish) but skipped the subject-digest step for the artifact consumed at packet time: outputs/plans/{plan_id}.json read at comparison.py:177. The 'state change' window is the time between generating the runs and running review-packets, which can be days. `compare()` does not read the plan's contents (it uses freeze.json parts, run state files via report._collect/read_validated, and loop report.json), so it needs no plan-content guard. The guard belongs in review_packets only.

## Hypothesis

The guard sits on the recorded provenance (manifest vs freeze), not on the bytes that are actually used. `review_packets` is the only code path in comparison.py that parses the plan file's contents, and it does not tie those contents to the frozen hash. Fix: `planned, sha = plan.load_plan(record['plan']['plan_id'])`, and raise ValueError if `sha != record['plan']['sha256']`, before `folder.mkdir()` and before any packet is written. This mirrors experiment.pro_packets (experiment.py:79-86) and report.compare (report.py:43-45).

## Counterevidence

- CWE-367 is framed around concurrent races. Here the 'change' is a later edit by a person, not an attacker racing a check, so the analogy is about principle, not threat model.
- plan.load_plan reads the file twice (read_json, then _sha256 on the path). So even with the fix, a change between those two reads is theoretically possible. That is a narrow window, the same in every existing caller, and not what the reviewer raised.

## Alternatives

- Change `plan.load_plan(plan_id, expected_sha)` to verify for every caller: it would centralise the check, but there are already five inline call sites with their own error messages (report.compare, plan.asked_document, validation.py:188/255, experiment.pro_packets), so it is a wider refactor than the finding needs. Not first.
- Snapshot each bundle's evidence text into the run (or into freeze.json) and build packets from the snapshot: this would remove the dependency on the plan file, but it adds storage and changes formats. A hash refusal matches how the rest of golden_pipeline handles a changed plan ('make a new run').
- Call the check from `_checked_runs` so compare also refuses a changed plan file: this would make compare refuse a state that does not affect its numbers. It may still be wanted for consistency, but it is not required by the finding.

## Experiment

In tests/golden/test_cli.py, reuse the `planned`/`api` fixtures: run B b1 on p3 with `--part train`, call `write_freeze()` (correct hashes), then rewrite outputs/plans/p3.json so that a train bundle's unit text changes (any byte change alters the SHA-256). `golden('review-packets', 'x1')` must raise ValueError mentioning the frozen plan, and outputs/experiments/x1/review must not exist. On the current code (89f54e6) the same steps should write packet.md quoting the edited text, which confirms the hypothesis. Run only this test, then the gate once.

## Result

Observed, not verified (draft). Ran the proposed experiment as `tests/golden/test_cli.py::test_review_packets_refuse_a_plan_file_changed_after_the_freeze`. It runs B b1 on p3 with `--part train`, calls `write_freeze()`, then replaces `130,000,000원` with `140,000,000원` in outputs/plans/p3.json. On 89f54e6 + the research pages (9272eca) it failed with `DID NOT RAISE ValueError`, and `outputs/experiments/x1/review` was written from the edited plan, which confirms the hypothesis. The fix in the commit after 9272eca ("golden: tie review packets to the frozen plan and reuse settled validation calls on resume") makes `review_packets` keep the hash from `plan.load_plan` and raise before `_checked_runs` and `folder.mkdir()` when it differs from `freeze.json`. The test then passed, as did all of test_cli.py and test_experiment.py (39 passed). A grep found no other post-run reader of plan contents in comparison.py.

## Unresolved limits

Not verified by running anything: no shell in this turn. I did not check whether other inputs that review_packets or compare read are tied to the freeze: loop report.json cost fields used in `_costs`/`_reconcile`, and candidates.jsonl read by `_sample` for unvalidated runs. They may draw the same kind of finding later, but they are separate from F1. freeze.json is taken as the trusted root and is not itself protected.
