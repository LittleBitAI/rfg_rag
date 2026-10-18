# Review research — F3, cycle 1

Draft research before the fix of review round 2 of PR #66, written 2026-10-19. It is not a verified fact or a shared rule: the review reads it with the fix.

## Problem

F3 concerns a content boundary across the repository, not merely exclusion of eval/golden/. AGENTS.md forbids committing dataset content, metadata and derived reports, while permitting source, model configuration, generic instructions and synthetic fixtures. Tracked research quotations and evaluation reports still violate that boundary after removal of the original release files. [C1, C3]

Trigger: repeat, rounds 1, 2.

- [P1] [P1] docs/research/review-feature-eval-golden-input-f4-1.md:76 — dataset content and derived reports remain tracked despite F3’s stated repository-wide boundary

## Failed fixes

- At round 1, the ignore rule did not remove existing tracked datasets. Git explicitly distinguishes ignoring untracked paths from removing tracked files. [C2]
- According to the supplied review chronology, the correction before round 2 removed the three eval/golden files. Current inspection agrees with that limited result, and tests/test_eval_items.py now creates synthetic temporary releases. This was useful, but demonstrated only removal of the original files and their test dependency. It did not demonstrate repository-wide removal of embedded copies and derived results. [C3, C4]
- The benchmark protocol correctly places dataset records and measurements under ignored artifacts/, but existing research pages and older reports retain their own copies. Treating the new benchmark boundary as evidence that the entire repository satisfies section 1.4 allowed F3 to be marked fixed prematurely. The exact earlier patch could not be independently retrieved. [C3, C4, C5]

## Sources

### S1 — Repository dataset boundary

- URL: AGENTS.md
- Retrieved: 2026-10-19
- Locator: Section 1.4, lines 45-52
- Fragment: "Never commit or upload dataset content or metadata"; the list includes "dataset-derived measurements and reports." "Keep these under ignored `artifacts/` locally. Commit only source code, model configuration, generic instructions, and synthetic test fixtures." "Ignore rules do not remove already tracked files".
- Applicability: Defines the invariant and its permitted content categories across the repository.
- Counterevidence: Allows generic instructions, model configuration and synthetic fixtures; it does not require deleting every document mentioning evaluation.
- Validation: Classify all tracked content against these categories rather than checking only eval/golden/.

### S2 — Current root ignore rules

- URL: .gitignore
- Retrieved: 2026-10-19
- Locator: Lines 4-10
- Fragment: "artifacts/"; "# Benchmark records and dataset-derived reports remain local."; "/docs/benchmarks/seven_model/*" with exceptions for protocol.md and models.json; "/eval/golden/"; "data/".
- Applicability: Shows path exclusions and the explicit distinction between benchmark records and permitted protocol/configuration.
- Counterevidence: Patterns do not establish index removal or content cleanup in other files.
- Validation: Check both tracked ignored paths and the contents of all remaining tracked files.

### S3 — Synthetic evaluation regression tests

- URL: tests/test_eval_items.py
- Retrieved: 2026-10-19
- Locator: Lines 10-15, 29-35 and 60-75
- Fragment: "def _release_row(topic: str, answer: str, structure: dict"; "def test_golden_release_row_becomes_eval_item(tmp_path, topic, answer, structure, key_facts):"; "def test_synthetic_multi_hop_facts_preserve_scoring_regressions(tmp_path, context, answer, question, expected):".
- Applicability: Current tests construct synthetic releases in temporary directories instead of loading the tracked dev dataset.
- Counterevidence: Functional extraction tests do not inspect tracked reports or research documents.
- Validation: Preserve these behavioral tests and validate repository content separately.

### S4 — Research document with embedded dataset evidence

- URL: docs/research/review-feature-eval-golden-input-f4-1.md
- Retrieved: 2026-10-19
- Locator: Lines 71-79, especially fragment at line 76; Result section, lines 119-132
- Fragment: "- Locator: line 393, fields answer, context, structure"; "## Result"; "Observed, still a draft: these are measurements on eval/golden/dev.jsonl, not a verified rule." The dataset quotation and measurement values are deliberately not reproduced here.
- Applicability: Directly confirms that removing the release file leaves evidence quotations and derived observations in a tracked document.
- Counterevidence: The same document contains reusable literature and generic reasoning that can survive sanitization.
- Validation: Remove original evidence and dataset-specific results while preserving generic reasoning with synthetic examples.

### S5 — Kiwi evaluation report

- URL: docs/kiwi_bm25_review.md
- Retrieved: 2026-10-19
- Locator: Lines 9-33, 116-132 and 153-200
- Fragment: "## 범위와 입력"; "## 라벨 범위와 제외율"; "## 채택 판정"; "## 문서 순위 지표"; "## 청크 순위 지표". Dataset fingerprints and measured table entries are deliberately not reproduced.
- Applicability: Contains dataset fingerprints, label coverage and measured ranking results outside the excluded release directory.
- Counterevidence: Some tokenizer methodology and implementation criteria are generic and may remain.
- Validation: Preserve the full report locally; retain only permitted generic material in Git.

### S6 — IR evaluation sample report

- URL: docs/eval_ir_sample.md
- Retrieved: 2026-10-19
- Locator: Lines 8-48 and 88-139
- Fragment: "## 입력과 표본"; "## 실제 비용과 심판 결과"; "문자열 지표는 의미적 정확성으로 해석하지 않습니다." Dataset fingerprints, sample statistics, measured scores and costs are deliberately not reproduced.
- Applicability: Contains dataset metadata and derived results even though underlying artifacts are stored locally.
- Counterevidence: It correctly limits interpretation of the experiment, but that limitation does not change the storage rule.
- Validation: Move the measured report locally and retain generic procedures without dataset-specific values.

### S7 — Tracked Kiwi metrics table

- URL: docs/kiwi_bm25_metrics.csv
- Retrieved: 2026-10-19
- Locator: Header and first result row, lines 1-2
- Fragment: "variant,level,component,recall_at_5,recall_at_10,recall_at_20,mrr_at_5,mrr_at_10,mrr_at_20". The measured row values are deliberately not reproduced.
- Applicability: Shows that cleanup must include structured reports as well as Markdown.
- Counterevidence: The schema itself is generic; the measured rows are the relevant prohibited content.
- Validation: Keep actual measured rows in ignored artifacts/ and inspect other structured outputs.

### S8 — Benchmark publication contract

- URL: docs/benchmarks/seven_model/protocol.md
- Retrieved: 2026-10-19
- Locator: Lines 3, 21, 50 and 60
- Fragment: "데이터셋 내용·메타데이터·실측 결과는 Git에 넣지 않는다." "아래는 발행자의 설명과 라이선스이며 로컬 데이터셋의 실측 결과가 아니다." "실제 dev 행을 저장소 테스트 fixture로 사용하지 않는다."
- Applicability: Demonstrates the intended local-record boundary and distinguishes public model information from local dataset results.
- Counterevidence: A correct benchmark contract does not establish compliance of pre-existing reports elsewhere.
- Validation: Apply its content distinction consistently across the entire tracked inventory.

### S9 — Git gitignore documentation

- URL: https://git-scm.com/docs/gitignore
- Retrieved: 2026-10-19
- Locator: DESCRIPTION and NOTES
- Fragment: "Files already tracked by Git are not affected"; "To stop tracking a file that is currently tracked, use git rm --cached".
- Applicability: Explains why the original ignore change could not remove committed data and why further patterns cannot sanitize embedded copies.
- Counterevidence: Ignore patterns remain useful for preventing ordinary re-addition after files are removed from tracking.
- Validation: Verify removal from the index as well as prevention of reintroduction.

### S10 — Git git-ls-files documentation

- URL: https://git-scm.com/docs/git-ls-files.html
- Retrieved: 2026-10-19
- Locator: OPTIONS: --cached, --ignored and --exclude-standard
- Fragment: "Show all files cached in Git’s index, i.e. all tracked files." "Standard ignore rules are not automatically activated".
- Applicability: Supports complete index enumeration and the separate git ls-files -ci --exclude-standard diagnostic.
- Counterevidence: An ignored-path diagnostic cannot detect forbidden content embedded in an otherwise permitted tracked document.
- Validation: Combine index enumeration with content classification and inspection of staged blobs.

### S11 — GitHub: Removing sensitive data from a repository

- URL: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository
- Retrieved: 2026-10-19
- Locator: Side effects of rewriting history; About sensitive data exposure
- Fragment: "You cannot remove sensitive data from other users' clones of your repository"; "GitHub Support won't remove non-sensitive data".
- Applicability: Limits claims about historical removal and explains why publication history requires separate inspection.
- Counterevidence: This guidance concerns sensitive-data removal. The dataset's sensitivity and remote exposure are unverified; rewriting also changes commit identities and requires coordination.
- Validation: Inspect outgoing reachable history and document residual exposure without claiming recall of other clones, forks or cached references.

## Claims

- C1 (source; S1): Section 1.4 excludes dataset content, metadata and derived reports throughout Git, while permitting source, model configuration, generic instructions and synthetic fixtures.
- C2 (interpretation; S2, S9): Ignore rules do not remove tracked files; the current exclusions therefore cannot establish removal of previously committed datasets or embedded copies.
- C3 (interpretation; S1, S4, S5, S6, S7): The inspected research document, evaluation reports and metrics CSV retain dataset content or derived information prohibited by section 1.4.
- C4 (interpretation; S2, S3, S4, S5, S6, S7): Current inspection supports a successful narrow release-file/test cleanup, not repository-wide compliance. Attribution to the earlier correction follows the supplied review chronology; its exact historical patch was unavailable.
- C5 (interpretation; S2, S3, S4, S8): The benchmark protocol states the intended boundary correctly, but its scope and synthetic tests cannot demonstrate cleanup of older tracked documentation.
- C6 (interpretation; S9, S10): Complete index enumeration and tracked-ignored-path detection are distinct checks; neither substitutes for examining file contents.
- C7 (interpretation; S11): Current-tree deletion does not demonstrate historical erasure. Publication history and residual copies need separate assessment, and historical rewriting has coordination requirements and removal limits.
- C8 (interpretation; S1, S3, S4, S5, S6, S7, S8, S10, S11): The appropriate next fix is a repository-wide content audit and cleanup, preserving local originals and permitted generic material, with synthetic behavioral tests and separate publication-history validation.

## Core theory

Git ignore patterns govern intentionally untracked paths; they do not inspect file contents or remove existing index entries. Git can enumerate the complete index and, separately, tracked paths matching ignore rules. Therefore neither an ignore match nor absence of files in one directory establishes a repository-wide content boundary. Removing content from the current tree also does not establish removal from published history or other copies. These Git mechanics support the diagnosis; the requirement to exclude dataset-derived documentation comes from this repository's rule. [C1, C2, C6, C7]

## Applicability

Apply cleanup to the complete tracked inventory, including docs/research/, Markdown reports, CSV reports, notebook outputs, tests and tracked .wiki records. The cited research page contains a dedicated original-evidence fragment and dataset-specific experimental results; the Kiwi and IR reports contain dataset fingerprints, mapping information and measured results; the Kiwi CSV stores measured metrics. These are separate copies even after eval/golden/ disappears. Preserve generic methodology, public model revisions, configuration and synthetic regression cases: their presence alone does not violate section 1.4. This research page must likewise cite locations without reproducing the prohibited payload. [C1, C3, C4, C5, C8]

## Hypothesis

The fixes used a path-based completion criterion for a content-based invariant: absence of the named release files was mistaken for absence of dataset information throughout tracked content. Research quotations and measured reports were implicitly treated as documentation exceptions, although section 1.4 provides no such exception. The next fix should preserve local originals under artifacts/, remove tracked data-only reports, and replace embedded dataset examples with independently authored synthetic examples while retaining generic explanations. [C1, C3, C5]

## Counterevidence

- The original-file cleanup appears effective at the current snapshot: the tracked eval listing contains only eval/eval_questions.yaml, and the inspected evaluation tests generate synthetic files. The first correction was incomplete rather than entirely ineffective. [C4]
- The benchmark protocol explicitly excludes dataset content, metadata and measurements from Git. This argues against an absent or ambiguous intended boundary; it supports incomplete application of an already stated boundary. [C5]
- A dataset path mentioned in instructions is not itself dataset content, and a hash may identify public model source rather than a dataset. Keyword or hash matches require classification rather than automatic deletion. [C1, C5, C8]
- The available tools did not expose the historical patches or publication graph. The attribution of the narrow correction to the interval between the two supplied heads relies on the user's review record, not an independently inspected commit diff. [C4]

## Alternatives

- Add more ignore patterns: useful for preventing reintroduction after migration, but ineffective against already tracked files and embedded content. [C2]
- Delete only the round-2 quoted evidence fragment: removes one violation while leaving derived statistics, fingerprints and other copies. [C3]
- Keep aggregate results or hashes as anonymized documentation: section 1.4 explicitly includes dataset metadata and derived measurements; anonymization does not establish compliance with this contract. [C1]
- Delete all documentation or ban every hash and number: would remove permitted methodology, configuration and public model information. Classify content by origin and meaning instead. [C1, C5, C8]
- Start with a history rewrite: first identify and clean the current content and establish which historical objects would be published. Historical removal may also be necessary, but it has coordination costs and cannot recall other users' copies. An ordinary deletion commit must not be presented as historical erasure. [C7]

## Experiment

Have the implementation/server perform a before-and-after publication audit, keeping the inventory and findings under ignored artifacts/. First enumerate the complete index with git ls-files -z and identify tracked ignored paths with git ls-files -ci --exclude-standard; the latter is only a path check. Inspect all tracked content for original dataset material, embedded quotations, identifiers, fingerprints, split/mapping information and derived reports, including notebook outputs and .wiki records. Before cleanup, this must detect the research fragment and report locations cited here despite eval/golden/ being absent; otherwise it repeats the earlier blind spot. Preserve local originals under artifacts/, then remove data-only files from tracking and sanitize mixed documents with generic explanations or independently authored synthetic examples. Re-audit the staged content and resulting commit, including every before-audit location, and verify that preserved local artifacts remain untracked and ignored. Confirm the evaluation regressions still use synthetic temporary inputs, then have the server run the required repository checks. Separately inspect the commits and objects reachable through the proposed publication: if prohibited content remains in history that will be uploaded, a clean tip alone cannot satisfy the upload boundary, and a coordinated sanitized publication history is needed before publishing. Report current-tree compliance and historical exposure separately. Discovery only in the named release directory refutes the proposed audit's adequacy; detection and removal of the distributed copies supports the hypothesis. None of these commands or tests was executed in this research session. [C2, C3, C4, C6, C7, C8]

## Result

pending — the fix records what it observed here, with the tests and the commit.

## Unresolved limits

This is draft research, not an exhaustive clearance. pr_diff returned a read failure, so neither named historical patch was inspected. The broad tracked listing was truncated, although the cited documents and tests were read directly. Other tracked structured data and ignored-path entries need classification; their filenames alone do not establish their contents. No shell, tests, migration, index mutation or publication-history inspection ran. Whether earlier dataset-bearing commits are already remote, newly outgoing, or reachable through other refs remains unknown. GitHub's sensitive-data guidance explains removal limits; it does not establish that this dataset qualifies for GitHub Support removal. [C4, C7, C8]
