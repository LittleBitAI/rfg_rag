# Review research — F1, cycle 1

집계 결과와 측정 조건은 Git에 보관하고, 원시 질문·정답·근거·OCR 전사와 레코드별 내보내기는 무시된 로컬 `artifacts/`에 보관한다.

복원 출처: 정리 전 `artifacts/review-round2/originals/` 또는 `d7d1682^`. 아래 수치와 검증 기록은 당시 실행의 역사적 관측이며 이번 작업에서 재측정한 결과가 아니다.

Draft research before the fix of review round 2 of PR #64, written 2026-10-17. It is not a verified fact or a shared rule: the review reads it with the fix.

## Problem

F1 concerns compatibility between persisted BM25 tokens and the code querying them. The original change allowed new query tokenization against old corpus tokens. Its repair prevents that forward mismatch, but changes bm25_tokens.json from an array into an object that the rollback revision cannot consume correctly. A safe transition must preserve both the token representation and the tokenizer semantics, or require a coordinated rebuild before the selected application revision starts searching. [C1, C2, C3, C4]

Trigger: repeat, rounds 1, 2.

- [P1] [P1] rag/retrieval/indexing.py:156 — The new BM25 payload makes a code rollback fail

## Failed fixes

- Original implementation at 1f1b041: adopted dictionary expansion and noise removal without identifying the tokenizer generation in persisted tokens. Existing-index reuse could combine old corpus segmentation with new query segmentation. The recorded 개인정보처리시스템 probe demonstrates the resulting loss of overlap. This was the original defect, rather than an earlier repair. [C2]
- Round-1 repair at 3ca3af0: stored {tokenizer, tokens}, rejected missing or mismatched fingerprints before loading FAISS or the embedding model, documented an upgrade rebuild, and tested rejection followed by successful current-generation searching. This repairs the forward transition. It does not prepare the existing rollback loader to read the new object or provide a verified downgrade procedure. [C3, C4, C6, C7]
- The repair relied on the existing staged directory publication boundary. That boundary preserves the previous index when construction or publication raises an exception; after successful publication, TemporaryDirectory cleanup removes the previous directory. It therefore supplies no retained artifact for a later application rollback. [C5]

## Sources

### S1 — AWS Builders' Library — Ensuring rollback safety during deployments

- URL: https://aws.amazon.com/builders-library/ensuring-rollback-safety-during-deployments/
- Retrieved: 2026-10-17
- Locator: Standalone vs. distributed software deployments; Verifying that a change is safe for rollback
- Fragment: "If the standalone software maintains state, then the new version must read ... data written ... by the old version and vice versa."
- Applicability: The index remains on disk across application revisions. The standalone persistent-state condition applies without assuming a distributed deployment.
- Counterevidence: The article's distributed rollout machinery is unnecessary here. Restoring or rebuilding compatible derived state is an application-specific alternative to mutual readability.
- Validation: Exercise actual old and new readers across the upgrade and downgrade, including the coordinated restoration or rebuild.

### S2 — Rank-BM25 — corpus and query preprocessing contract

- URL: https://raw.githubusercontent.com/dorianbrown/rank_bm25/master/README.md
- Retrieved: 2026-10-17
- Locator: Usage — Initializing and Ranking of documents, lines 45–58
- Fragment: "a list of lists of strings"; "apply the same preprocessing steps we did to the documents"
- Applicability: Explains why both the original tokenizer mismatch and an array-only downgrade conversion can produce incorrect retrieval.
- Counterevidence: Equivalent preprocessing need not require byte-identical implementation. Here the repository records an actual segmentation difference.
- Validation: Compare corpus tokens and BM25-only search behavior with the corresponding revision's query tokenizer.

### S3 — Rank-BM25 — constructor iteration and score allocation

- URL: https://raw.githubusercontent.com/dorianbrown/rank_bm25/master/rank_bm25.py
- Retrieved: 2026-10-17
- Locator: BM25.__init__, BM25._initialize, BM25Okapi.get_scores
- Fragment: "if tokenizer:\n            corpus = self._tokenize_corpus(corpus)"; "for document in corpus:"; "self.corpus_size += 1"; "score = np.zeros(self.corpus_size)"
- Applicability: The old loader supplies no tokenizer callback. Passing the two-key object consequently creates two corpus entries and two scores.
- Counterevidence: This is fetched upstream code, not verification of the installed package. Confirm its behavior in the actual rollback environment.
- Validation: Measure corpus_size and get_scores(...).shape using the actual rollback loader and package.

### S4 — NumPy — general broadcasting rules

- URL: https://numpy.org/doc/stable/user/basics.broadcasting.html
- Retrieved: 2026-10-17
- Locator: General broadcasting rules
- Fragment: "Two dimensions are compatible when"; "they are equal, or"; "one of them is 1."
- Applicability: A two-score vector cannot broadcast with the three-chunk regression mask or the recorded 18,989-chunk corpus mask.
- Counterevidence: One- and two-chunk fixtures can avoid this exception, which is why successful construction or a tiny search is insufficient evidence.
- Validation: Use at least three chunks and assert the score-vector length as well as successful search.

### S5 — Index construction, tokenizer fingerprint and temporary publication

- URL: rag/retrieval/indexing.py
- Retrieved: 2026-10-17
- Locator: KiwiTokenizer.__init__, lines 91–103; build_index/_publish_index, lines 124–144; _build_index, lines 147–158; PR diff removed array writer
- Fragment: self.fingerprint = {"source_sha256": sha256(source).hexdigest(), "dictionary_sha256": sha256(dictionary).hexdigest(), **{name: version(name) for name in ("kiwipiepy", "kiwipiepy_model", "hanja")}}; with TemporaryDirectory(prefix=f".{out_dir.name}-", dir=out_dir.parent) as folder: ... _publish_index(staged, out_dir, workspace / "previous"); except BaseException: if previous.exists(): previous.rename(out_dir); payload = {"tokenizer": tokenizer.fingerprint, "tokens": tokens}
- Applicability: Shows the new artifact shape, the coupled directory publication, and why previous artifacts survive publication failure but are not retained after successful context cleanup.
- Counterevidence: The existing exception restoration is useful and should remain. It makes no promise of a retained backup, process-crash recovery or concurrent-reader coordination.
- Validation: Test successful upgrade followed by downgrade separately from injected build/publication failures; verify complete artifact generations.

### S6 — HybridIndex — current guard, old loader and sparse ranking

- URL: rag/retrieval/retrieval.py
- Retrieved: 2026-10-17
- Locator: Current lines 62–76, 158–188; PR diff lines 3503–3505 expose the base loader
- Fragment: Current: if not isinstance(stored, dict) or stored.get("tokenizer") != self.tokenizer.fingerprint: raise ValueError(...); self.bm25 = BM25Okapi(stored["tokens"], ...). Removed base lines: tokens = json.loads((artifacts / "index" / "bm25_tokens.json").read_text(encoding="utf-8")); self.bm25 = BM25Okapi(tokens, ...). Ranking: sparse_raw = self._sparse(question, allowed) if w < 1 else {}; scores = np.where(allowed, self.bm25.get_scores(self.tokenizer(question)), 0.0).
- Applicability: Direct evidence of the two reader contracts and the point where a wrong corpus length reaches the chunk mask.
- Counterevidence: Dense-only ordinary ranking skips sparse scoring. Filter-route queries may also avoid that immediate failure.
- Validation: Run the actual base constructor and an ordinary query at dense_weight=0 against candidate-built artifacts, then repeat after the downgrade procedure.

### S7 — Index migration and publication regression coverage

- URL: tests/test_indexing.py
- Retrieved: 2026-10-17
- Locator: setup_index and publication tests, lines 36–109; fingerprint and legacy migration tests, lines 112–160
- Fragment: def test_failed_rebuild_preserves_complete_previous_index(...); def test_successful_rebuild_replaces_core_and_quantity_artifacts_together(...); def test_incompatible_bm25_index_is_rejected_before_loading_dense_model(...); def test_legacy_bm25_index_requires_rebuild_then_finds_dictionary_compound(...): ... indexing.build_index(rows, cfg, directory); loaded = retrieval.HybridIndex(directory.parent, cfg)
- Applicability: The fixtures build with the current implementation and load with the current implementation. The legacy test exercises old data entering the new loader, not new data entering the old loader.
- Counterevidence: These tests guard real forward and failed-publication behavior. Their scope is incomplete for downgrade compatibility rather than useless.
- Validation: Add a cross-revision upgrade/downgrade check using actual target-revision code and a semantic search assertion.

### S8 — Recorded tokenizer measurements and round-1 repair

- URL: docs/kiwi_bm25_review.md
- Retrieved: 2026-10-17
- Locator: Compound probe, lines 72–79; Review 1, lines 324–370
- Fragment: 기준선: 개인, 정보, 처리, 시스템, 및, 데이터베이스, 구축. 사전 확장: 개인정보처리시스템, 및, 데이터베이스, 구축. "기존 질문 토크나이저는 청크 `0`을 반환했고" is recorded as "이전 질문 토크나이저는 청크 `0`을 반환했고," followed by "채택 토크나이저는 질문을 한 토큰으로 만들어 후보를 전혀 반환하지 않았다." The repair record states: "기존 디렉터리 단위 발행·실패 시 복원 경계 안에서 지문과 토큰을 함께 발행한다."
- Applicability: Records the semantic mismatch, the repair's intended boundary, and its forward-only reproduction.
- Counterevidence: The document reports earlier measurements and passing checks; this research session did not rerun them. The migration measurements do not establish downgrade compatibility.
- Validation: Reproduce both directions on the same three-chunk corpus and compare each revision with its own pre-transition behavior.

### S9 — README — existing-index reuse and mandatory upgrade rebuild

- URL: README.md
- Retrieved: 2026-10-17
- Locator: Notebook settings and existing-index workflow, lines 198–199
- Fragment: 이번 Kiwi 변경 전 색인은 재사용할 수 없으므로 02의 불러오기·설정 셀과 `1. 색인 만들기`의 `build_index` 셀을 실행한 뒤 04나 질문 화면을 실행하세요. 이 색인 재구축은 로컬 작업이며 유료 질문 재작성 예제 셀을 실행할 필요가 없습니다.
- Applicability: Provides an upgrade procedure that can serve as the starting point for an explicit downgrade procedure.
- Counterevidence: The inspected guidance explains upgrade rebuilding, but gives no corresponding downgrade ordering, restore procedure or verified rollback target.
- Validation: Follow the documented downgrade literally in a fresh target-revision process and require search success before restarting consumers.

## Claims

- C1 (source; S1): Persistent-state compatibility must be assessed across both deployment directions; current-version functionality alone does not establish rollback safety.
- C2 (interpretation; S2, S8): This tokenizer update changes corpus/query segmentation, so preserving a parseable file shape alone cannot guarantee correct BM25 retrieval after rollback.
- C3 (source; S5, S6, S8): The round-1 repair stores a fingerprint with tokens and makes the new loader reject legacy or mismatched artifacts before loading the dense model.
- C4 (interpretation; S3, S4, S6): The base loader passes the new two-key object directly to BM25Okapi; under the fetched implementation this creates two corpus entries, causing a mask/score shape failure for ordinary BM25-enabled ranking with more than two chunks.
- C5 (interpretation; S5): The current publication boundary restores the previous directory on publication failure but does not retain it after a successful build for a later code rollback.
- C6 (interpretation; S7, S8): Existing regressions cover current-generation operation, fingerprint rejection, upgrade rebuilding and failed publication; they do not exercise the actual old reader after a successful new-generation build.
- C7 (interpretation; S9): The inspected migration guidance requires an upgrade rebuild but does not specify a coordinated downgrade procedure.
- C8 (interpretation; S1, S2, S5, S6, S9): A stopped-reader downgrade that restores a matching artifact bundle or rebuilds with the exact rollback revision can address both structural and tokenizer-semantic compatibility without teaching the immutable old loader a new format.
- C9 (interpretation; S1, S3, S4, S6, S7): The decisive check uses actual revisions in fresh processes, at least three chunks, BM25-enabled semantic assertions, and an upgrade/downgrade sequence; constructor success or one- and two-chunk shape checks are insufficient.

## Core theory

AWS describes persistent-state upgrades as bidirectional compatibility problems even for standalone applications: both revisions must understand the other's persisted state, unless deployment also restores compatible state. Its recommended evidence includes upgrade-downgrade testing. Rank-BM25 separately requires tokenized document lists and equivalent query preprocessing. These are distinct requirements: an old-readable JSON shape does not establish matching tokenizer semantics. [C1, C2, C4]

## Applicability

Keep the current forward rejection. The smallest corrective direction consistent with the repository's existing notebook workflow is a documented and tested coordinated downgrade rebuild, rather than another compatibility layer. Stop the frontend and all notebook consumers; select the exact rollback revision and its dependency environment; rebuild the complete index using that revision's build_index and the intended chunks; verify it with that revision's HybridIndex; restart consumers in fresh processes only after success. For verification before publication, build in an isolated artifacts tree containing the matching chunks/docs, then publish the complete index while readers remain stopped. If rebuilding or verification fails, do not start the rollback application against head artifacts. Preserve a coherent code/environment/artifact bundle when recovery without rebuilding is required. This procedure must explicitly cover the downgrade direction and retain the existing forward-migration checks. It does not promise live-reader or crash-safe switching. [C3, C5, C7, C8]

## Hypothesis

The repair treated compatibility as a property enforceable entirely by the new reader. Compatibility actually belongs to the reader/writer transition across revisions. The old reader remains unchanged: it passes the decoded object directly to BM25Okapi, which iterates the two object keys as documents and produces two scores. With a real corpus larger than two chunks, the first ordinary BM25-enabled ranking attempts to combine those scores with a differently sized chunk mask and fails. The fingerprint cannot protect execution after rolling back to code that does not inspect it. [C3, C4]

## Counterevidence

- The forward repair is effective within its tested scope: the current loader rejects legacy arrays and changed fingerprint inputs before loading the dense model. The hypothesis does not require removing that protection. [C3, C6]
- The broadcasting exception is conditional. Dense-only ranking skips _sparse, and corpora with one or two chunks can conceal the shape failure through broadcasting or equal dimensions. Such cases still do not demonstrate correct corpus interpretation. [C4]
- Existing publication failure tests demonstrate preservation during a failed build. They do not demonstrate recovery after a successful build followed by a code downgrade. [C5, C6]
- A complete compatible artifact backup restored with the old code would avoid the reported failure. The inspected implementation and migration guidance do not provide that retained backup or restoration procedure. [C5, C7]

## Alternatives

- Restore the array format and put the fingerprint in a sidecar: this can make the JSON structurally readable by the old loader, but old queries would still be tokenized differently from the new corpus. It is insufficient without compatible old tokens or a mandatory downgrade rebuild. [C2, C4, C8]
- Retain a complete pre-upgrade index bundle and restore it with its matching chunks, configuration and dependency environment: a sound alternative when fast rollback matters. It requires retention before the successful upgrade replaces the active directory; the current temporary previous directory is not such retention. [C5, C8]
- Deploy a preparatory reader before changing the writer: appropriate when every rollback target can first be upgraded. It cannot repair an already existing dev revision, and structural support alone would still leave tokenizer-generation compatibility unresolved. [C1, C2, C8]
- Catch the NumPy error, resize scores, or disable BM25: these hide or bypass invalid corpus interpretation and fail to restore the supported BM25-only behavior. [C2, C4]
- Convert the new object to its tokens array during downgrade: insufficient because it preserves the new-generation tokens. Regenerate tokens using the rollback revision or restore an artifact actually produced by it. [C2, C8]

## Experiment

In a later implementation session, use the actual base revision and candidate revision in separate fresh Python processes, with network/API calls blocked and a local embedding substitute. Use at least three chunks: 개인정보처리시스템, 네트워크 보안, 계약 기간. First build and search with the base revision at dense_weight=0, recording tokens, score-vector length and returned chunk IDs. Upgrade without rebuilding and verify that the candidate rejects the old artifact without modifying it. Rebuild with the candidate and verify its compound search. Then run the actual base HybridIndex directly against those new artifacts: expect corpus_size=2 and a shape failure on ordinary BM25-enabled search. This is the negative control. Finally perform the documented stopped-reader downgrade rebuild using the actual base builder; start a fresh base loader and require corpus_size and score length to equal three, corpus tokens and BM25-only results to match the initial base run, and all five index artifacts to belong to the rebuilt generation. Inject a downgrade-build failure and verify that startup remains blocked rather than exposing a mixed code/artifact state. Repeat a normal hybrid search to cover the usual configuration. Preserve the existing fingerprint rejection regressions. These are proposed checks, not executed results. [C3, C4, C5, C6, C8, C9]

## Result

Implementation observation, still a draft: `artifacts/kiwi_round2_experiment.py` ran before the correction on candidate code commit `5b2773f` against actual base `2f746f3` in fresh offline Python processes. Base build/search had three corpus entries/scores and BM25 IDs `[0]`; forward loading was rejected without changing any index file; the candidate rebuild searched successfully; the base reader of that new object produced two scores and `operands could not be broadcast together with shapes (3,) (2,) ()`. After quarantining the new index, an injected downgrade-build failure left the active path absent and a fresh base startup failed at `faiss.index`. A successful isolated base rebuild, fresh verification and directory publication restored all five artifact bytes, original tokens, BM25 IDs `[0]` and hybrid IDs `[0, 1, 2]`. The committed `tests/test_index_migration.py::test_stopped_reader_downgrade_restores_base_artifacts_and_search_after_upgrade` repeats the lifecycle; `.venv\Scripts\python -m pytest -q tests/test_index_migration.py tests/test_indexing.py tests/test_retrieval.py` reported `61 passed in 139.91s`. This Result and the correction are recorded together in the commit named `retrieval: document and rehearse atomic index downgrade`; the production writer/reader code remains the tested `5b2773f` generation.

## Unresolved limits

The source claims above remain draft research. The implementation rehearsal recorded in Result uses actual historical/current source in one installed environment: Python 3.10.11, Kiwi/model 0.24.0, Hanja 0.15.1, rank-bm25 0.2.2, NumPy 2.2.6 and FAISS 1.15.1, with a local embedding substitute and blocked network connections. It does not recreate every historical package environment, migrate the active corpus or switch live application readers. The documented migration requires stopped readers and publishes into an absent active path with one same-filesystem directory rename; it does not establish crash recovery. The existing builder's two-rename exception-restoration boundary is retained, not generalized into a live deployment guarantee. [C5, C9]
