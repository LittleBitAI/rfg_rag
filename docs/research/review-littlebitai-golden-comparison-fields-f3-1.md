# Review research — F3, cycle 1

Draft research before the fix of review round 4 of PR #76, written 2026-10-20. It is not a verified fact or a shared rule: the review reads it with the fix.

## Problem

F3 breaks the binding between package declarations, package bytes, adapter records, and the hashes frozen into a plan. These must describe one consistent package. Currently make_plan can accept an unchanged package manifest declaring old chunks together with changed chunks and matching replacement adapter records, then freeze that inconsistent combination. Later hash checks preserve the admitted inconsistency rather than detect it. [C1, C2, C3]

Trigger: repeat, rounds 3, 4.

- [P1] [P1] golden_pipeline/evidence.py:70 — adapter 재생이 패키지 매니페스트의 파일 선언을 검증하지 않아 승인되지 않은 역할 원문을 계획에 고정합니다

## Failed fixes

- At the supplied round 3 baseline, make_plan compared current package files with hashes supplied by the mutable evidence-run manifest. It did not establish that saved units and judgments were derived from those files. Rewriting the manifests therefore allowed old adapter bodies and references to accompany new source hashes. Role equality could not detect changed body values or requirement links when the role names stayed unchanged. The cumulative PR diff confirms that eligible_units previously read saved units and judgments directly. [C1, C2]
- The correction visible at the round 4 baseline extracted _adapt and added read_verified, which compares both complete saved record sequences with fresh adapter output. This closes the stale-record path. However, evidence.run calls pin before _adapt, while read_verified calls _adapt alone. The extracted replay omitted the producer's package-declaration precondition. Matching source and adapter edits now pass replay even when the package manifest still declares the old source hash. [C1, C4]
- The focused tests covered adapter-only edits and source edits with stale adapter records. The latter deliberately repaired both manifests, so they exercised replay disagreement rather than declaration disagreement. Existing post-plan mutation tests start after a valid plan already exists. None establishes rejection when source and adapter agree before planning but the package declaration is stale. [C4, C5]

## Sources

### S1 — Evidence producer, replay reader and package declaration verification

- URL: golden_pipeline/evidence.py
- Retrieved: 2026-10-20
- Locator: run lines 34–52; _adapt/read_verified/pin lines 56–84; role parsing lines 121–144
- Fragment: run executes `hashes = pin(package)` before `units, judgments, counts = _adapt(package)`. read_verified instead begins `units, judgments, _ = _adapt(package)` and compares the complete parsed units.jsonl and judgments.jsonl lists with those results. _adapt checks chunk/document counts against manifest counts. pin hashes PINNED and, for every name in PINNED[1:], rejects when `declared[name]["sha256"] != hashes[name]`. Role parsing checks shape, names in the body, duplicates and overlap; it does not verify the manifest's file declarations.
- Applicability: Shows the exact producer precondition omitted from replay and the existing function that restores it.
- Counterevidence: Replay detects complete-record disagreement, and initial evidence creation already performs declaration verification.
- Validation: Matching replacement adapter records with a stale package declaration must fail before replay results are exposed.

### S2 — Plan admission, hash copying and shared evidence readers

- URL: golden_pipeline/plan.py
- Retrieved: 2026-10-20
- Locator: make_plan lines 31–71; eligible_units/document_units lines 87–111; _check_package lines 161–165; cumulative PR diff for those functions
- Fragment: make_plan reads `pinned_sha256` from the evidence-run manifest, calls `_check_package(package, pinned)`, then eligible_units. It stores `package_manifest_sha256` and the same `pinned_sha256` in the plan. _check_package compares each supplied hash with its current file; it does not read package file declarations. Both eligible_units and document_units call read_verified. The PR diff replaces direct reads of saved adapter records with those calls.
- Applicability: Explains how individually matching hashes become a supposedly coherent plan and identifies the direct consumers protected by a shared-reader repair.
- Counterevidence: A package changed without corresponding evidence-pin changes already fails _check_package.
- Validation: Reject the mixed manifest/chunk snapshot before the exclusive plan-file write; accept a fresh coherent evidence run.

### S3 — Downstream plan anchors and source role checks

- URL: golden_pipeline/validation.py
- Retrieved: 2026-10-20
- Locator: _documents lines 201–212; _comparison_role_reason/_pinned_roles/_planned_package lines 662–698
- Fragment: _pinned_roles verifies the generation plan SHA, checks CHUNKS against the plan's per-file hash, then reads role_annotations using that hash. Its comment states: `Rename may update agency names; only the source chunks affect role judgments.` _comparison_role_reason compares cited plan roles with source roles. _documents checks the planned hashes for PINNED[1:] before reading document units.
- Applicability: Later consumers preserve the plan's admitted source identity, including an incorrect identity admitted before plan creation.
- Counterevidence: These checks protect against later source mutation and plan-role overrides.
- Validation: Keep existing post-plan mutation failures and agency-name refresh successes after repairing admission.

### S4 — Focused adapter and comparison provenance regression tests

- URL: tests/golden/test_comparison_fields.py
- Retrieved: 2026-10-20
- Locator: lines 86–125, 153–190, 227–243 and 259–291
- Fragment: The post-plan mutation test changes body, requirement_ids or roles and optionally repins the evidence and package manifests. The adapter-output test changes saved units or judgments alone. The stale-reader test changes body or requirement_ids, updates the package declaration and evidence pins using evidence.pin, but leaves adapter records stale; it expects a units.jsonl mismatch. Its plan branch also checks that a fresh evidence run succeeds. The name-refresh test updates the agency CSV and its package declaration while preserving chunk bytes.
- Applicability: Shows the missing pre-plan combination: changed source plus matching adapter output with an unchanged package declaration.
- Counterevidence: The suite already covers several real tampering paths and valid regeneration.
- Validation: Add the coordinated replacement case alongside these tests and retain their distinct failure expectations.

### S5 — Producer declaration and complete-record verification tests

- URL: tests/golden/test_evidence.py
- Retrieved: 2026-10-20
- Locator: lines 90–102 and 169–191
- Fragment: test_run_stops_when_files_differ_from_manifest_declaration changes the declared CHUNKS hash, expects evidence.run to raise PackageMismatch, and asserts no evidence-run directory exists. test_verified_reader_checks_complete_records_including_held_units mutates saved records through missing, duplicate, reversed or promoted cases and expects read_verified to reject.
- Applicability: The declaration invariant is already enforced and tested for production, but not for replay with matching replacement records.
- Counterevidence: These tests do not execute the reported coordinated-edit scenario.
- Validation: Require the same declaration rejection through the replay entry point, with records that otherwise match.

### S6 — Documented source-role authority and manifest-refresh contract

- URL: golden_pipeline/README.md
- Retrieved: 2026-10-20
- Locator: lines 440–486
- Fragment: `Requirement comparisons use explicit roles authored by the trusted source-package owner.` The contract states that the pipeline does not certify the owner's semantic annotations. It describes adapter replay before copying per-file hashes into the plan, permits agency CSV and package-declaration updates while source chunks remain fixed, and says the whole-package manifest hash remains provenance rather than a required current-manifest match for role checks. Using annotations from an old package requires a new owner-prepared package and new evidence, plan and generation runs.
- Applicability: Defines the authority boundary and constrains the repair to preserve deliberate downstream name refresh.
- Counterevidence: The documented binding is stronger than the implementation currently establishes; documentation is intent rather than proof.
- Validation: A stale declaration must block admission, while coherent new packages and permitted name refresh continue to work.

### S7 — The Update Framework Specification — verified metadata chain

- URL: https://theupdateframework.github.io/specification/latest/
- Retrieved: 2026-10-20
- Locator: Sections 5.6 step 2 and 5.7 steps 1–3; found by web search and opened
- Fragment: "The hashes of the new targets metadata file MUST match the hashes, if any, listed in the trusted snapshot metadata."
- Applicability: Supports verifying declaration-to-file relationships before admitting a composite snapshot.
- Counterevidence: TUF uses authenticated metadata; this repository's local manifest has no equivalent signature verification. The source does not establish package-owner identity here.
- Validation: Reject matching derived records when their source bytes disagree with the declaring package manifest.

## Claims

- C1 (source; S1): The producer verifies package declarations through pin before adaptation; read_verified performs adaptation and complete-record equality without that declaration check.
- C2 (interpretation; S2): make_plan checks current files against evidence-supplied hashes and copies those hashes into the plan, so this check alone does not establish agreement with package declarations.
- C3 (interpretation; S2, S3): Plan-based downstream checks preserve an admitted snapshot but cannot repair an inconsistent snapshot accepted at plan creation.
- C4 (interpretation; S1, S4): Replay fixes stale adapter records but admits coordinated source and adapter replacements when declarations are not checked.
- C5 (interpretation; S4, S5): The inspected tests cover separate source/adapter disagreement and post-plan mutation, but omit matching pre-plan replacements with stale package declarations.
- C6 (interpretation; S1, S2, S3, S5, S6): The appropriate repair is to compose declaration verification, evidence-pin agreement and full replay before plan admission, sharing declaration verification with direct evidence readers.
- C7 (interpretation; S7): TUF verifies metadata through previously trusted parents and verifies target hashes against their declaring metadata; matching hashes from an unverified context are insufficient.
- C8 (interpretation; S1, S3, S4, S6): The intended contract trusts owner-authored role semantics and permits agency-name refresh without changing pinned source chunks; declaration consistency does not prove annotation correctness or historical authorship.

## Core theory

TUF separates metadata consistency from file verification: checks follow an already verified parent, and target bytes must match their declaring metadata. Its metadata-hash requirement is conditional on hashes being present. Applied here, agreement among derived records cannot replace checking the package declaration that authorizes their input. This is a consistency analogy, not a recommendation to implement TUF. [C7, C6]

## Applicability

The missing declaration check belongs before _adapt inside evidence.read_verified, so eligible_units and document_units receive the same package-validity precondition as evidence.run. At make_plan admission, obtain hashes through evidence.pin(package), compare the complete PINNED set with the evidence-run pins, retain replay verification, and store the verified set in the plan. Keep downstream checks anchored to the generation plan: the documented agency-name refresh may update the current package manifest without changing source chunks, so requiring the old whole-manifest hash at every later role check would reverse intended behavior. [C1, C2, C3, C6, C8]

## Hypothesis

The root cause is an incomplete verification boundary: replay equivalence was treated as sufficient evidence of package validity. Admission actually requires three independent relationships: package manifest declarations equal current file hashes; evidence-run pins equal that verified package hash set; saved units and judgments equal adaptation of that package. The original path lacked the third relationship; the replay correction still lacks the first. Reuse pin before replay in the shared verified reader, retain complete-record comparison, and ensure make_plan freezes the complete verified hash set only after it matches the evidence-run pins. [C1, C2, C6]

## Counterevidence

- Replay already checks full records, order, held units, eligibility and reasons. It is meaningful protection against stale or independently modified adapter output; the hypothesis concerns its missing precondition, not an inadequacy of record equality itself. [C1, C4]
- Initial evidence creation already rejects files that disagree with package declarations. The inconsistent state requires modification after evidence creation and before another read or plan. [C1, C5]
- Downstream plan and chunk hash checks correctly reject source changes made after a valid plan was frozen. They cannot distinguish a valid snapshot from an inconsistent one admitted at plan creation. [C3, C5]
- The repository explicitly trusts source-owner role annotations and does not certify their semantic correctness. Even a declaration-consistent package can contain incorrect roles; this repair cannot establish semantic authority beyond the supplied package contract. [C8]

## Alternatives

- Add only hashes of units.jsonl and judgments.jsonl to the mutable evidence manifest. Coordinated replacement can update those hashes too, and it still leaves the package declaration unchecked. Retain replay instead. [C1, C6]
- Check only source-role equality or record counts. Matching replacement roles and unchanged counts satisfy both checks while package file declarations remain wrong. [C1, C3]
- Put pin only in make_plan. This would close the reported plan entry point but leave direct eligible_units and document_units reads without the producer's declaration check. The shared reader is the stronger existing boundary. [C1, C2]
- Require the historical package-manifest hash during every validation, release and rename role check. This would interfere with the documented agency-name refresh. Establish declaration consistency when admitting a plan, then preserve its existing per-file anchors. [C3, C8]
- Introduce signed manifests, immutable storage or authenticated historical run identities. Those address a stronger threat model involving coherent replacement of every local artifact. The reported stale-declaration case is addressable with existing pin and replay mechanisms first. [C6, C7]

## Experiment

Use synthetic fixtures only, without API calls. Create a valid package and evidence run, then change chunk body or valid role assignments without changing record counts. Replace both saved adapter files with the exact records derived from the changed chunks. Update only the evidence-run CHUNKS hash; leave the package manifest bytes and its declared chunk hash unchanged. Assert the adapter records really match the changed source so replay disagreement cannot explain rejection. On current code, static tracing predicts make_plan accepts this mixture; after the repair it must raise PackageMismatch identifying the package chunk declaration before writing a plan. Exercise the same fixture through read_verified, eligible_units, document_units and the absence-estimation path, asserting output snapshots remain unchanged. Preserve existing adapter-only and stale-adapter failures. As positive controls, an unchanged package must remain readable, and a coherently updated package with a fresh evidence run must produce a plan containing the new body, references and roles. Retain the existing validation/release/rename tests for post-plan source changes and agency-name refresh. These checks are proposed, not executed. [C4, C5, C6, C8]

## Result

pending — the fix records what it observed here, with the tests and the commit.

## Unresolved limits

This is a draft based on source inspection, the cumulative PR diff and the supplied round reports. No files were edited, no tests or reproduction were executed, and actual dataset records were not inspected. The tools did not provide historical commit checkout, so exact commit attribution beyond the supplied reports remains unverified. pin checks consistency with a local manifest; it does not authenticate who authored that manifest or prove the historical identity of a run if all package files, manifests and adapter records are coherently replaced. Separate file reads also do not establish an atomic snapshot under concurrent writes; that scenario was not investigated. [C1, C2, C6, C8]
