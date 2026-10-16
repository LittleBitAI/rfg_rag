# Review research — F1, cycle 1

Draft research before the fix of review round 2 of PR #57, written 2026-10-16. It is not a verified fact or a shared rule: the review reads it with the fix.

## Problem

F1 concerns the boundary between loading saved answers and spending money on evaluation. Every row must be structurally complete and contain values usable by evaluation before either paid judge starts. Currently, rewrite.cost_usd=null passes _read_answers, evaluate_end_to_end calls _ragas, and the subsequent addition of answer and rewrite costs fails. The validator establishes key presence and selected container shapes, not the required value types. [C1, C2, C3]

Trigger: repeat, rounds 1, 2.

- [P1] [P1] rag/evaluation/evaluation.py:218 — Presence-only validation still permits malformed nested values to incur paid calls

## Failed fixes

- The implementation described in round 1 checked top-level key presence. It accepted rewrite={} because rewrite existed, although end-to-end evaluation later required nested token and cost fields. The PR diff corroborates the original top-level membership check. [C2]
- The corrective change visible in the current code added required nested keys, dictionary/list checks, and row/item-specific error paths. Its tests delete required keys or replace nested containers with null. However, _missing_record_fields still checks only whether each key exists. Present leaf values remain unchecked, so rewrite.cost_usd=null reaches the same paid-call boundary. The supplied round-2 review reports this remaining case; no second corrective patch was reported. [C2, C3, C4]

## Sources

### S1 — JSON Schema — object

- URL: https://json-schema.org/understanding-json-schema/reference/object
- Retrieved: 2026-10-16
- Locator: Required Properties, especially the null-valued email example
- Fragment: “In JSON a property with value `null` is not equivalent to the property not being present.”
- Applicability: rewrite.cost_usd exists even when its decoded value is None; required-key membership cannot establish its numeric type.
- Counterevidence: This distinction does not prohibit null universally. Each property's type determines whether null is permitted.
- Validation: Distinguish missing numeric keys, present null numeric values, and intentionally nullable labels.

### S2 — OWASP — Input Validation Cheat Sheet

- URL: https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html
- Retrieved: 2026-10-16
- Locator: Input Validation Strategies; Implementing Input Validation
- Fragment: “Validate both syntax (the expected type and format) and semantics (whether the value makes sense for the operation).”
- Applicability: Saved answer records need receiving-side checks before paid processing, including their nested values.
- Counterevidence: This is general validation guidance, not a specification for this project's numeric ranges or an instruction to add security infrastructure.
- Validation: Malformed values must be rejected before judge invocation while legitimate domain exceptions remain accepted.

### S3 — Python 3.10 — json encoder and decoder

- URL: https://docs.python.org/3.10/library/json.html
- Retrieved: 2026-10-16
- Locator: JSONDecoder default conversion table; Infinite and NaN Number Values
- Fragment: “null | None”; “Despite that, by default, this module accepts and outputs `Infinity`, `-Infinity`, and `NaN` as if they were valid JSON number literal values:”
- Applicability: JSON decoding preserves null and can accept non-finite numeric extensions by default; parsing alone is insufficient for cost validation. The preceding documentation explicitly says the RFC disallows those non-finite representations.
- Counterevidence: Custom decoder settings can alter default behavior; the repository's reader uses json.loads without those settings.
- Validation: Deserialize representative inputs through the real JSONL reader, then assert the receiving validator rejects invalid cost values.

### S4 — Python 3.10 — bool

- URL: https://docs.python.org/3.10/library/functions.html#bool
- Retrieved: 2026-10-16
- Locator: Built-in Functions, bool
- Fragment: “The bool class is a subclass of int”
- Applicability: An isinstance(value, int) or isinstance(value, (int, float)) check alone accepts JSON booleans as numeric accounting values.
- Counterevidence: Boolean arithmetic is valid Python; excluding it here follows the meaning of the receiving fields.
- Validation: Require explicit boolean rejection in numeric-field tests while accepting booleans in boolean fields.

### S5 — Evaluation reader and paid-call ordering

- URL: rag/evaluation/evaluation.py
- Retrieved: 2026-10-16
- Locator: Lines 200–247 and 285–310; PR diff lines 839–889 for the original/current reader
- Fragment: return [f"{prefix}.{field}" for field in fields if field not in record]
ragas = _ragas(rows, [FactualCorrectness()], cfg, "end_to_end")
"cost_usd": r["cost_usd"] + r["rewrite"]["cost_usd"]
- Applicability: Direct evidence of membership-only leaf checks and arithmetic after judge execution. _read_answers scans the file before returning rows.
- Counterevidence: Missing fields and selected malformed containers already fail before the judge; the remaining defect is unchecked values.
- Validation: Mocked judge invocation must change from reached-before-TypeError to never reached with a precise validation error.

### S6 — Usage and evaluation regression tests

- URL: tests/test_usage.py
- Retrieved: 2026-10-16
- Locator: Lines 192–206, 237–242, and 274–325
- Fragment: del record[key]
write_jsonl([_answer_row(), row], answers)
calculate.assert_not_called()
("rewrite", None), ("retrieval_settings", None), ("ranked_candidates", None), ("evidence", None)
- Applicability: Existing negative tests mutate presence and containers. They provide a useful two-row and no-paid-call pattern but do not mutate scalar leaves.
- Counterevidence: The tests cover legitimate behavior and the original missing-key failure; their gap is a missing input category, not an absence of useful assertions.
- Validation: Extend the pattern to scalar types and retain the valid mocked-judge accounting result.

### S7 — Usage producer and accounting

- URL: rag/usage.py
- Retrieved: 2026-10-16
- Locator: record_usage, lines 16–37
- Fragment: "cost_usd": ((tokens["prompt_tokens"] - cached) * usd_in + cached * usd_cached
             + tokens["completion_tokens"] * usd_out) / 1e6
- Applicability: Ordinary usage output computes cost numerically; accepting an invalid saved cost should not be repaired by inventing a replacement amount.
- Counterevidence: Producer behavior does not validate a saved file when evaluation later reads it.
- Validation: Preserve valid recorded costs and totals while rejecting malformed saved accounting values.

### S8 — Retrieval candidate construction

- URL: rag/retrieval/retrieval.py
- Retrieved: 2026-10-16
- Locator: _candidate_snapshot and _rank, lines 86–114
- Fragment: "dense_score": dense_raw.get(i), "dense_rank": dense_ranks.get(i),
"bm25_score": sparse_raw.get(i), "bm25_rank": sparse_ranks.get(i)
- Applicability: A candidate absent from one retrieval component legitimately has null scores and ranks for that component.
- Counterevidence: This permits null for specific component fields, not for fused rank or accounting costs.
- Validation: Valid candidates with missing component membership must pass the new checks unchanged.

### S9 — IR label-exclusion fixtures

- URL: tests/test_ir_metrics.py
- Retrieved: 2026-10-16
- Locator: Lines 30–38 and 56–90
- Fragment: unmapped = {**full, "id": "unmapped", "evidence": [{"doc_id": None, "chunk_id": None}]}
yaml = {**full, "id": "yaml", "primary_topic": None, "evidence": []}
- Applicability: Null evidence labels, null topic, and empty evidence encode supported evaluation states. The shared answer fixture also uses trace_id=None.
- Counterevidence: These intentional exceptions do not establish that every field may be null.
- Validation: Existing partial-label, unlabelled, unanswerable, and YAML exclusion behavior must survive validation.

### S10 — Repository evaluation invariant and implementation limits

- URL: AGENTS.md
- Retrieved: 2026-10-16
- Locator: Sections 1, 5, and 6; especially lines 141–148
- Fragment: “05 rejects incomplete answers before any paid call.” “It retains the old answers and clears trace IDs; score that file only for Retrieval.”
- Applicability: Defines the paid-call invariant, legitimate rerun trace clearing, and the requirement to keep the implementation focused and readable.
- Counterevidence: The rules do not prescribe a validation library or a complete set of scalar ranges.
- Validation: Offline rejection tests must establish zero judge calls; implementation must subsequently pass required lint and tests.

### S11 — JSONL serialization boundary

- URL: rag/config.py
- Retrieved: 2026-10-16
- Locator: write_jsonl and read_jsonl, lines 24–32
- Fragment: return [json.loads(line) for line in f if line.strip()]
- Applicability: The real reader uses default JSON decoding without application-specific type checks.
- Counterevidence: Malformed JSON syntax already fails during decoding; F1 concerns syntactically accepted records with unsuitable values.
- Validation: Build the reproduction through write_jsonl/read_jsonl rather than passing an artificial dictionary directly to a helper.

## Claims

- C1 (source; S10): The required invariant is rejection of incomplete answer artifacts before any paid evaluation call.
- C2 (source; S5): The PR base used top-level membership checks; the current corrective code adds nested presence and container checks but still does not validate leaf values.
- C3 (interpretation; S5, S11, S3): A present null rewrite cost passes the current reader and reaches the end-to-end judge before incompatible cost addition fails.
- C4 (source; S6): Existing rejection tests cover missing keys and malformed nested containers, leaving scalar-value mutations uncovered.
- C5 (interpretation; S1, S2, S5, S6, S10): The durable repair is a whole-file receiving-side value contract at the existing shared reader, retaining precise rejection paths and explicit nullability.
- C6 (source; S1): JSON property presence and acceptance of a null value are separate constraints.
- C7 (source; S2): Validation should address expected types and formats as well as suitability for the intended operation.
- C8 (interpretation; S3, S11): The repository's default JSON decoding maps null to None without establishing application field validity.
- C9 (interpretation; S3, S4, S7, S11): Numeric acceptance rules should exclude booleans and non-finite accounting values while preserving ordinary integer, floating-point, and zero costs.
- C10 (interpretation; S6, S8, S9, S10): Nullability must remain field-specific because absent component scores/ranks, unlabelled evidence, null topics, and missing trace IDs are supported states.
- C11 (interpretation; S5, S6, S10): A focused validator can establish the invariant without a general schema framework, rejection of extra metadata, or unrelated consistency rules.
- C12 (interpretation; S6, S7): Normal accounting produces numeric costs, and existing mocked-judge tests preserve a total cost of 0.000101; the evidence establishes invalid-artifact exposure rather than an observed producer defect or actual charge.

## Core theory

Property presence, property type, and nullability are separate constraints. JSON Schema explicitly distinguishes a null property from an absent property. OWASP distinguishes syntactic validation from whether a value makes sense for its operation. Python decoding preserves JSON null as None, so successful parsing does not establish suitability for arithmetic. These principles explain why adding nested required keys alone cannot establish the paid-call precondition. [C6, C7, C8]

## Applicability

Apply the contract at _read_answers, already shared by all four evaluations and retrieval reruns. Validate every row before either judge is invoked, including an invalid last row following valid rows. Cover the fields already required by ANSWER_FIELDS and the nested field lists: question/reference/answer and identifiers as strings; contexts, key_facts, and context_chunk_ids as lists with appropriately typed string items; answerable and stored_rewrites_reused as booleans; top-level and rewrite token counts as integers; costs and latency as numeric values; rewrite.question and retrieval_settings.chunk_file as strings; retrieval settings and candidate ranks/scores with their actual numeric types; and every evidence/candidate item as a record with typed leaves. Numeric predicates must exclude booleans. Costs should accept zero and both integer and floating-point representations; reject non-finite costs rather than silently producing unusable totals. Field-specific exceptions are essential: trace_id may be null, primary_topic may be null, evidence labels may be null, and absent dense/BM25 scores and ranks may be null. Empty evidence and empty candidate/context lists must remain usable where existing behavior permits them. Keep existing extra metadata such as model, sources, and rewrite.latency_s accepted. These are proposed receiving-side rules, to be checked against the producers during implementation, rather than a mandate to introduce a schema library or unrelated cross-field constraints. [C5, C9, C10, C11]

## Hypothesis

The first fix treated completeness as a list of required keys rather than a contract for the values consumed downstream. It extended validation depth without extending validation meaning. A focused fix should make _read_answers validate required value types, nested collection items, and field-specific nullability across the entire file before returning any rows. Preserve rejection with a precise field path; do not silently coerce, default, or skip malformed rows. [C5]

## Counterevidence

- The first fix did improve the boundary: missing nested keys and malformed nested containers now produce ValueError before the judge. Its whole-file scan and row/item paths are useful and should be retained. [C2, C4]
- record_usage calculates a numeric cost, and the normal fixture contains numeric costs. The evidence does not show that the normal producer emits null costs or that users have already incurred charges from this case. The demonstrated exposure is evaluation accepting an invalid saved artifact. [C3, C12]
- Null is intentionally meaningful in several neighboring fields. A blanket recursive rejection of null would break legitimate label exclusions, absent retrieval components, and operation without tracing keys. [C10]

## Alternatives

- Reject only rewrite.cost_usd=null: this closes the reported example but leaves the same type gap for top-level cost_usd and other required scalar values. Prefer rules derived from the fields evaluation actually consumes. [C3, C5]
- Move cost addition before _ragas: this would expose this arithmetic failure earlier, but would not establish validity for the other consumers or paid grounding evaluation. It can support early preparation, but is insufficient as the shared validation contract. [C3, C5]
- Use value or 0, float(value), or broad exception recovery: these can conceal malformed provenance or change saved accounting. They also weaken the existing reject-and-regenerate behavior. [C5, C12]
- Catch TypeError after _ragas: payment has already become possible at that point. Changing judge retries or usage accounting does not repair the input boundary. [C1, C3]
- Introduce a general schema framework or reject all unknown keys: neither is necessary to establish the current field contract. Additional producer metadata is already present in ordinary answers. Small explicit validators are a reasonable first implementation under the repository's simplicity rules. [C11]

## Experiment

Use offline tests only. First reproduce the current failure using the existing _answer_row fixture: write a valid first row and a second row whose rewrite.cost_usd is None; mock _ragas to return two factual_correctness scores, and mock _send_scores. The predicted current result is a TypeError after one _ragas invocation. Separately, confirm that _read_answers currently accepts that file. After the fix, require ValueError identifying row[2].rewrite.cost_usd, zero _ragas calls, zero score-publication calls, and no result CSV. Exercise representative wrong types from each declared field family, including top-level cost, nested token counts, string fields, list items, and scalar leaves inside a later candidate/evidence item. Reuse the shared-reader tests across the four evaluation functions and rerun; rerun must not search or write output when validation fails. Add positive controls for zero numeric values, legitimate nullable labels/component ranks and scores, null trace/topic, empty permitted lists, and additional producer metadata. With mocked judge scores, an ordinary valid end-to-end row must still preserve its columns and total cost of 0.000101. If the baseline cannot reach the mocked judge, or the proposed rules reject legitimate positive controls, revise the hypothesis or contract. Run the repository's required lint and test gate after implementation; none was executed in this research turn. [C4, C5, C9, C10, C11, C12]

## Result

오프라인 관측 — 교정 전에는 정상 첫 행과 `rewrite.cost_usd=null`인 둘째 행을 `_read_answers`가 모두 받아들였고, 모의 `_ragas`와 `_send_scores`가 각각 1회 호출된 뒤 비용 합산에서 `TypeError`가 발생했습니다. 교정 후 `tests/test_answer_records.py::test_invalid_saved_values_stop_all_consumers_before_side_effects`는 네 평가와 검색 재실행 모두에서 `row[2].rewrite.cost_usd`를 명시한 `ValueError`, 심판·점수 게시·검색 호출 0회, 결과 파일 없음과 함께 자료형 오류를 거부합니다. `tests/test_answer_records.py::test_valid_saved_values_preserve_nullability_metadata_and_end_to_end_cost`는 0인 정수·실수 비용, 허용된 null, 빈 목록, 추가 생산자 메타데이터와 기존 열·합계 비용 `0.000101`을 보존했습니다. 기본 표본과 검색 재실행의 실제 생산자 출력도 각각 30행씩 그대로 읽었습니다. 보고된 rewrite 비용 외의 적용 지점은 최상위 16개, rewrite의 나머지 5개, 검색 설정 6개, 후보 8개, 근거 2개로 총 37개 필드 계약입니다. `tests/test_usage.py`의 누락 키 회귀는 유지하고 기존 컨테이너 오류 검사는 더 강한 전체 파일·전체 소비자 검사로 접었습니다. 대상 테스트 461개와 전체 `.venv\Scripts\python -m pytest -q tests`의 `1053 passed, 12 warnings in 107.43s`를 확인했고 `ruff check .`와 debt 검사도 통과했습니다. 이 결과와 교정은 이 페이지를 함께 담는 커밋 `evaluation: enforce saved answer value types`에 기록합니다. 이는 초안의 실험 기록이며 검증된 공용 규칙으로 승격하지 않습니다.

## Unresolved limits

이 문서는 초안입니다. Result의 실험은 이 브랜치에서 수행한 오프라인 관측이며 실제 과금이나 배포 동작을 관측한 것이 아닙니다. 정확한 라운드 이력은 제공된 리뷰 보고서에 근거하며 과거 모든 커밋을 독립적으로 재검증하지 않았습니다. 허용된 null과 현재 생산자 표현은 표본·회귀 테스트에서 보존되었지만, 이 결과가 설정·심판 출력·네트워크·추적·파일 시스템의 별개 실패까지 방지한다는 뜻은 아닙니다.
