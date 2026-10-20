# Review research — F3, cycle 2

Draft research before the fix of review round 5 of PR #76, written 2026-10-20. It is not a verified fact or a shared rule: the review reads it with the fix.

## Problem

F3 is a broken binding between a frozen plan and evidence read later for that plan. Current package declarations and adapter replay can agree on a newer snapshot while experiment._unanswerable_batches still uses an older plan. The estimator never compares current package files with planned['pinned_sha256'], so a frozen experiment can obtain document batches and estimated validation costs from different source bytes. [C1, C2, C3, C10]

Trigger: repeat, rounds 4, 5.

- [P1] [P1] golden_pipeline/experiment.py:301 — unanswerable cost estimation can read evidence from a newer package / after package declarations and adapter records are coherently replaced / because the frozen plan hashes are never checked

## Failed fixes

- The round-3 finding described copying mutable evidence-run hashes without establishing that saved units and judgments came from those source bytes. Adapter replay subsequently closed that stale-record path, but initially omitted package-declaration verification. This chronology comes from the supplied review history and cycle-1 research, rather than independently inspected historical checkouts. [C6]
- The round-4 correction added pin(package) before replay and made plan admission compare the complete evidence-run pin set with the declaration-verified package. Those protections are present in current code and address the earlier admission defect. They establish a coherent current package, but do not establish that it is the package selected by an already frozen plan. [C1, C2, C6]
- Cycle-1 research traced document_units into absence estimation but proposed testing matching adapter replacements with a stale package declaration. That case fails inside pin and never exercises the missing relationship between a coherent replacement package and an old plan. Its reported passing checks therefore did not establish the broader frozen-plan invariant. [C5, C6]
- Both estimation regression branches construct a partial dictionary containing only evidence_run and bundles. Neither passes pinned_sha256 from the real plan created by the fixture. One case leaves adapter records stale; the other leaves the package declaration stale. Neither keeps an old plan while coherently replacing declarations and adapter records. [C5]

## Sources

### S1 — Plan admission, frozen hashes and document reader

- URL: golden_pipeline/plan.py
- Retrieved: 2026-10-20
- Locator: make_plan lines 31–60; document_units lines 98–110; _verified_evidence_pins and _check_package lines 160–173
- Fragment: make_plan: "pinned = _verified_evidence_pins(run_dir, package)"; "\"pinned_sha256\": pinned". _verified_evidence_pins: "pinned = evidence.pin(package)\n    recorded = storage._read_json(run_dir / \"manifest.json\")[\"pinned_sha256\"]\n    if recorded != pinned:". document_units: "def document_units(run_dir, docs):"; "units, _ = evidence.read_verified(run_dir, evidence.PACKAGE)". _check_package: "for name, sha in pinned.items():\n        if storage._sha256(package / name) != sha:\n            raise evidence.PackageMismatch(f\"{name} SHA-256 이 근거 어댑터 run 에 고정된 값과 다릅니다\")".
- Applicability: Shows that plan admission freezes verified hashes, while the current document reader receives no expected plan identity.
- Counterevidence: Plan admission already compares the complete evidence pin set, and _check_package already implements the needed per-file comparison.
- Validation: An old real plan must reject coherently replaced source files; a newly admitted plan must accept them.

### S2 — Current-package declaration verification and adapter replay

- URL: golden_pipeline/evidence.py
- Retrieved: 2026-10-20
- Locator: PINNED line 20; read_verified lines 68–75; pin lines 78–85
- Fragment: "PINNED = (\"manifest.json\", CHUNKS, DOCS, AGENCIES)". read_verified: "pin(package)\n    units, judgments, _ = _adapt(package)\n    for name, expected in ((\"units.jsonl\", units), (\"judgments.jsonl\", judgments)):\n        if list(_iter_jsonl(run_dir / name)) != expected:"; "return units, judgments". pin: "hashes = {name: storage._sha256(package / name) for name in PINNED}\n    declared = storage._read_json(package / \"manifest.json\")[\"files\"]\n    for name in PINNED[1:]:\n        if declared[name][\"sha256\"] != hashes[name]:"; "return hashes".
- Applicability: Both checks validate the current package; neither accepts a frozen plan or compares against its hashes.
- Counterevidence: These checks correctly reject stale declarations, missing or changed records, reordered records and mismatching judgments.
- Validation: Establish that coherent replacements pass these checks independently before expecting plan-based rejection.

### S3 — Estimation reads current document units without a plan-hash guard

- URL: golden_pipeline/experiment.py
- Retrieved: 2026-10-20
- Locator: estimate lines 243–271; _unanswerable_batches lines 297–302
- Fragment: "planned, _ = plan.load_plan(experiment_id)\n    batches = _unanswerable_batches(planned)". "if topic == \"unanswerable\":\n            per_output[\"high\"] = max(per_output[\"high\"], sum(batches) / len(batches))". _unanswerable_batches: "bundles = [bundle for bundle in planned[\"bundles\"] if bundle[\"topic\"] == \"unanswerable\"]\n    run_dir = storage.OUTPUTS / \"evidence\" / planned[\"evidence_run\"]\n    found = plan.document_units(run_dir, {bundle[\"doc_sha\"] for bundle in bundles})\n    return [len(validation.document_batches(found[bundle[\"doc_sha\"]])) for bundle in bundles]".
- Applicability: Identifies the precise point where the full plan is reduced to a mutable path and IDs, and the conditional route from batch counts to high cost estimates.
- Counterevidence: The historical validation-call ratio can dominate max, so changed batches need not change the final cost.
- Validation: Test both the helper and public estimate with the unchanged old plan; demonstrate a boundary-changing replacement separately from hash rejection.

### S4 — Existing plan-bound validation and text-dependent batching

- URL: golden_pipeline/validation.py
- Retrieved: 2026-10-20
- Locator: _documents lines 201–212; _pinned_roles and _planned_package lines 680–698; document_batches lines 800–822; DOCUMENT_BATCH_CHARS line 47
- Fragment: _documents: "if topic not in DOCUMENT_TOPICS:\n        return {}"; "_planned_package(planned, evidence.PINNED[1:])" precedes "found = plan.document_units(run_dir, set(asked.values()))". _planned_package: "if \"pinned_sha256\" not in planned:"; "pinned = {name: planned[\"pinned_sha256\"][name] for name in files}\n    plan._check_package(evidence.PACKAGE, pinned)\n    return pinned". _pinned_roles: "# Rename may update agency names; only the source chunks affect role judgments."; "pinned = _planned_package(planned, [evidence.CHUNKS])". Batching: "DOCUMENT_BATCH_CHARS = 60_000"; "if fresh and size + len(unit[\"text\"]) > DOCUMENT_BATCH_CHARS:".
- Applicability: Provides the existing guard estimation can reuse and shows why body length and unit grouping affect estimated calls.
- Counterevidence: The whole-document path already has this protection; role-only consumers deliberately check a smaller file set.
- Validation: Estimation should reject replacement snapshots under the same per-file policy as whole-document validation while role-only name refresh remains valid.

### S5 — Regression combinations omit a real old plan in estimation

- URL: tests/golden/test_comparison_fields.py
- Retrieved: 2026-10-20
- Locator: field_run lines 58–70; stale-adapter test lines 259–291; matching-replacement test lines 294–336; name-refresh test lines 86–125
- Fragment: "plan.make_plan(\"p-fields\", \"ev-roles\", {\"comparison\": 1}, 2000, package=evidence_run)". Both estimation branches use: "\"estimate\": lambda: experiment._unanswerable_batches({\"evidence_run\": \"ev-roles\", \"bundles\": [\n            {\"topic\": \"unanswerable\", \"doc_sha\": DOC_1}]}),". First case: "manifest[\"pinned_sha256\"] = evidence.pin(evidence_run)" and "with pytest.raises(evidence.PackageMismatch, match=\"units.jsonl\"):". Second case: "assert (evidence_run / \"manifest.json\").read_bytes() == package_manifest" and "with pytest.raises(evidence.PackageMismatch, match=r\"corpus/chunks.jsonl SHA-256.*manifest.json\"):".
- Applicability: The fixture creates a pinned plan, but estimation tests do not pass it. Their failures establish replay or declaration rejection rather than historical snapshot identity.
- Counterevidence: These tests cover distinct valid failure modes and should retain that coverage through direct readers after an earlier plan-hash guard is introduced.
- Validation: Pass a complete real old plan to estimation while both declarations and saved adapter records match the replacement package.

### S6 — Documented source authority and manifest-refresh limits

- URL: golden_pipeline/README.md
- Retrieved: 2026-10-20
- Locator: lines 440–490
- Fragment: "The pipeline checks this contract but does not certify the source owner's semantic annotations." "Updating `data/data_list.csv` and its package-manifest declaration therefore allows rename to use current organization names while keeping source chunks fixed." "Whole-document validation uses the same per-file anchor for the chunks, document list and agency CSV it already required to remain fixed." "The whole-package manifest hash remains in the plan as provenance, but role checks do not require the current manifest to match it."
- Applicability: Constrains the repair to existing per-file policies and distinguishes byte identity from semantic annotation correctness.
- Counterevidence: Documentation states intended behavior; source and regression controls are needed to establish implementation behavior.
- Validation: Preserve existing name-refresh tests and reject changed source chunks against old plans.

### S7 — Cycle-1 hypothesis, experiment and reported results

- URL: docs/research/review-littlebitai-golden-comparison-fields-f3-1.md
- Retrieved: 2026-10-20
- Locator: Failed fixes lines 15–17; Hypothesis line 112; Experiment line 131; Result lines 135–143; Limits line 147
- Fragment: "Admission actually requires three independent relationships: package manifest declarations equal current file hashes; evidence-run pins equal that verified package hash set; saved units and judgments equal adaptation of that package." "Update only the evidence-run CHUNKS hash; leave the package manifest bytes and its declared chunk hash unchanged." "The shared reader has two production callers, `eligible_units` and `document_units`; the latter reaches two further consumers, whole-document validation and absence estimation." "The initial research did not inspect historical checkouts, so its historical attribution beyond the supplied reports remains unverified."
- Applicability: Shows why cycle 1's admission-focused hypothesis and experiment did not establish the later consumer-to-plan relationship, despite tracing the estimation caller.
- Counterevidence: The page explicitly limits its historical attribution and reports meaningful declaration/replay checks; those checks address the earlier defect.
- Validation: Extend the experiment with a coherent replacement package and matching adapter output while retaining a real older plan.

### S8 — The Update Framework Specification 1.0.37

- URL: https://theupdateframework.github.io/specification/latest/
- Retrieved: 2026-10-20
- Locator: Section 5.6 step 2, lines 890–891; surrounding signature requirement in step 3. Found through an actual web search and opened.
- Fragment: "The hashes of the new targets metadata file MUST match the hashes, if any, listed in the trusted snapshot metadata."
- Applicability: Supports checking a candidate against an independently trusted parent; applying that relationship to plan-pinned local files is an interpretation.
- Counterevidence: The hash condition is explicitly conditional on hashes being present. TUF also verifies signatures and supports update transitions; this repository has no equivalent authenticated metadata chain, and a frozen plan intentionally selects an older snapshot.
- Validation: Keep the old plan as the expected parent; reject a coherent current package whose required file hashes differ from it.

## Claims

- C1 (source; S1): Current plan admission obtains declaration-verified package hashes, compares the complete evidence-run pin set, and stores that verified set in the plan.
- C2 (source; S2): read_verified checks current package declarations and complete adapter replay, but accepts no expected plan hashes.
- C3 (interpretation; S1, S2, S3): A coherent package and adapter replacement can pass the checks reached by estimation even when its source hashes differ from the unchanged old plan, because the caller drops the plan identity before reading.
- C4 (source; S4): Whole-document validation already checks required files against the frozen plan before document_units; comparison role verification deliberately checks only source chunks after checking generation-plan provenance.
- C5 (interpretation; S5): Existing estimation regression branches omit plan pins and independently provoke stale-adapter or stale-declaration rejection; they do not establish rejection of a coherent replacement against an old plan.
- C6 (interpretation; S7, S1, S2, S5): Cycle 1 and the supplied review chronology explain successive repairs to replay and declaration verification, but cycle 1's experiment did not test the historical plan anchor. Historical results are reported evidence, not checks executed in this session.
- C7 (source; S8): TUF requires new targets metadata hashes, when present, to match trusted snapshot metadata; this rule belongs to a procedure that also verifies signatures.
- C8 (interpretation; S1, S2, S3, S4, S5, S7, S8): The remaining repair is to preserve the caller-selected plan anchor before current-package reads. Reusing whole-document validation's existing per-file guard in absence estimation closes the reported sequential replacement path while retaining declaration and replay verification.
- C9 (source; S6, S4, S5): The repository permits agency-name and manifest refresh for comparison rename while source chunks remain fixed, treats the whole-manifest hash as provenance for role checks, and does not certify source-owner semantic annotations.
- C10 (interpretation; S3, S4): Replacement text can change document batching and the high validation-call estimate, but numerical impact requires crossing a batch boundary and exceeding the historical validation-call ratio used by max.

## Core theory

TUF verifies referenced metadata against hashes supplied by an already trusted parent, with the explicit qualification that the hash check applies when hashes are present. Its surrounding procedure also requires signature verification. The relevant principle is that agreement within a candidate artifact set does not replace checking its relationship to an independently selected parent. Here, applying that principle to a frozen plan is an interpretation: this repository needs equality with its selected historical snapshot, not TUF's software-update policy or signature infrastructure. [C7, C8]

## Applicability

Before _unanswerable_batches calls plan.document_units, apply the same plan-based per-file check already used by validation._documents: validation._planned_package(planned, evidence.PINNED[1:]). Then retain document_units' declaration verification and complete adapter replay. The existing experiment module already imports validation; using the same file set requires access to evidence.PINNED. This is a small repair using existing mechanisms. Keep document_units available for current-package reads rather than silently treating its existing two arguments as proof of a frozen plan. Both production callers were found: validation._documents already checks plan hashes; experiment._unanswerable_batches needs the check. Preserve the deliberate distinction between per-file anchors and the historical whole-manifest hash, including the comparison rename path's agency-name refresh. Update estimation regression fixtures to carry real plan pins and account for the earlier hash failure; retain direct-reader tests that independently exercise declaration and replay failures. [C1, C2, C3, C4, C5, C8, C9]

## Hypothesis

The remaining cause is a verification boundary that discards the caller's expected snapshot identity. _unanswerable_batches receives the full planned object but passes only a mutable evidence-run path and document IDs into document_units. That reader verifies current-package consistency without receiving the old plan hashes. Whole-document validation supplies this missing check separately through _planned_package; estimation does not. The earlier repairs strengthened current-package verification without completing the consumer-to-plan relationship. [C3, C4, C5, C8]

## Counterevidence

- Current make_plan already rejects incomplete or mismatching evidence pin sets, and read_verified already rejects stale declarations and complete-record disagreements. The earlier fixes are effective for those relationships; the remaining defect concerns consumption after a valid plan exists. [C1, C2]
- Whole-document validation checks the plan's chunks, document list and agency CSV before document_units. Comparison role checks separately verify the generation plan SHA and the plan-pinned chunks. The inspected paths therefore do not support claiming that all downstream consumers lack plan anchors. [C4]
- A same-length body replacement can leave batch counts unchanged. Acceptance of a different snapshot still demonstrates the provenance failure, but a cost-impact demonstration must change batching and avoid a historical call-rate maximum that masks the difference. [C10]
- Requiring the historical whole-package manifest everywhere would contradict the documented and tested agency-name refresh behavior. The proposed repair must preserve consumer-specific per-file checks. [C9]

## Alternatives

- Compare current package hashes only with the current evidence-run manifest. Coordinated replacement can update that manifest too; the expected identity must come from the frozen plan. [C1, C3, C8]
- Add another declaration or replay check. Both already pass for a coherent replacement package, so repeating them cannot establish old-plan equality. [C2, C3]
- Check only at make_plan or experiment.freeze. A later package replacement occurs after those checks. Estimation needs its own check before reading mutable source files. [C1, C3, C8]
- Check the historical package_manifest_sha256 everywhere. Existing contracts deliberately permit manifest changes for agency-name refresh while source chunks stay fixed; reuse the established per-file policy instead. [C4, C9]
- Change document_units to require a plan and move both callers to one shared plan-bound reader. This could make the invariant harder to omit, but is a broader interface change than adding the existing guard to the sole missing production caller. If chosen, require plan pins rather than making them optional, and preserve separate tests for current-package verification. [C3, C4, C5, C8]
- Add signed manifests, immutable evidence storage, or archived package snapshots. Those could address stronger replacement and availability concerns, but the reported sequential mutation is detectable using the frozen hashes already stored in the plan. [C1, C7, C8]

## Experiment

Proposed checks only; none were executed in this research session. Use independently authored synthetic fixtures and no APIs. First create a declaration-valid package, a real evidence run and a real unanswerable plan through make_plan; retain the complete old plan and its file bytes. Include at least two units in the target document, including a held unit where practical, because absence validation reads all units rather than just selected bundle evidence. Record baseline batch counts. Change target-document text so the same unit count crosses a document_batches size boundary; preserve valid source links and role annotations. Update package declarations coherently, replace both saved adapter files with exact fresh _adapt output, and update the evidence-run pins as a strong control. Prove evidence.pin and evidence.read_verified accept the replacement, while its CHUNKS hash differs from the unchanged old plan. On current code, static tracing predicts _unanswerable_batches(old_plan) returns replacement-derived counts. After repair it must raise PackageMismatch naming the changed pinned file before document batching or history loading, with output snapshots unchanged. Exercise public estimate using the stored old plan as well; a sentinel _history can prove rejection occurs before historical calculations, without fabricating real usage. Positive controls: unchanged plan/package still produces baseline counts, and a fresh evidence run plus fresh plan accepts the coherent replacement and produces its new counts. For a public cost comparison, supply clearly synthetic history with a sufficiently low validation-call ratio so estimate's max does not hide the batch change. Retain distinct direct-reader tests for stale declarations and stale adapter records, test missing plan pins through the existing rejection behavior, and preserve agency-name refresh controls. [C1, C2, C3, C4, C5, C8, C9, C10]

## Result

Observed against baseline `d75399a`; the repair commit carrying this page is named `golden: pin absence cost estimates to the frozen plan`. These are synthetic experiment observations in draft research, not an independently verified rule.

`test_estimation_rejects_coherent_replacement_of_a_frozen_plans_source` creates a real evidence run and unanswerable plan, then retains the old plan bytes. Its target document has four units, including held evidence. The replacement preserves record counts, coherently updates package declarations and evidence pins, and replaces both adapter files with exact fresh adaptation. Both `evidence.pin` and `evidence.read_verified` accept the replacement while its chunk hash differs from the old plan. Before repair, both the helper and public estimate accepted it: batches changed from 1 to 4, high validation calls from 40 to 160, and the synthetic unanswerable high estimate from USD 0.0104 to USD 0.0272. The low synthetic history ratio prevents the historical maximum from hiding that change. `.venv\Scripts\python -m pytest -q tests/golden/test_experiment.py -k 'estimation_rejects_coherent or estimation_accepts_a_fresh' --tb=short --junitxml=artifacts/comparison-fields-review5-reproduction.xml` ended `2 failed, 1 passed, 24 deselected in 50.65s`: both old-plan cases failed to raise `PackageMismatch`; the fresh-plan control passed.

The correction calls `validation._planned_package(planned, evidence.PINNED[1:])` in `_unanswerable_batches` before document reads. The old-plan cases now reject with the changed chunk filename before batching or history loading, with unchanged output snapshots and plan bytes. `test_estimation_accepts_a_fresh_plan_for_the_coherent_replacement` confirms unchanged-source baseline estimates and successful fresh evidence/plan estimates for the replacement. `test_estimation_requires_plan_pins_before_loading_history` checks both entry points retain the existing new-plan instruction for missing hashes. There is one other production caller of `document_units`, `validation._documents`; it already applies the same per-file guard. Comparison role checks keep their narrower source-chunk policy, preserving agency-name refresh.

After final code and test cleanup, `.venv\Scripts\python -m pytest -q tests/golden/test_experiment.py tests/golden/test_comparison_fields.py --tb=short -x --junitxml=artifacts/comparison-fields-review5-final.xml` ended `121 passed in 517.21s (0:08:37)`. This includes the new real-plan regressions and controls, retained direct-reader declaration/replay cases, post-plan mutation guards and agency-name refresh through validation/release/rename. Cleanup folded the four old `estimate` parameter cases using partial unpinned dictionaries into the stronger real-plan helper/public estimate coverage; direct-reader cases were retained.

`.venv\Scripts\python -m pytest -q tests/golden/test_validation.py -k 'inconsistent_source_or_adapter or held_unit or absence_is_certified' --tb=short -x --junitxml=artifacts/comparison-fields-review5-document-controls.xml` ended `8 passed, 108 deselected in 470.22s (0:07:50)`. Both processes exited successfully after slow final reporting; no test retry or process termination was needed. `ruff check .` passed. The full repository gate remains server-owned and pending.

## Unresolved limits

This remains draft research; its initial source inspection is supplemented by the synthetic observations under Result. No paid calls were made and no actual dataset records were inspected. The numerical values describe synthetic history and a reduced test batch limit, not production cost or performance. Historical test results quoted by cycle 1 remain that document's reported observations, apart from the explicitly retained controls run above. Frozen plan hashes are treated as the expected identity; coherent replacement of the plan itself and every external anchor is a stronger threat model. Local declarations do not authenticate package ownership or establish semantic correctness. Separate hash and file reads also leave concurrent-write atomicity outside this investigation. [C6, C7, C8, C9, C10]
