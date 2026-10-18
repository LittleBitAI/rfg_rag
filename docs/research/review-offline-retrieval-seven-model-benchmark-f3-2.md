# Review research — F3, cycle 2

Draft research before the fix of review round 4 of PR #66, written 2026-10-19. It is not a verified fact or a shared rule: the review reads it with the fix.

After this draft was written, the owner explicitly clarified that actual dataset records must remain private while measurements and aggregate statistics may be published. The broader exclusion studied below is historical. The Result applies the clarified requirement; the benchmark goal and completion criteria are unchanged.

## Problem

F3의 불변식은 추적 파일 전체에서 데이터셋 내용·메타데이터·파생 측정값을 제외하는 것이다. 현재 README.md:424에는 실제 dev 근거·컨텍스트 블록의 집계와 과거 집계에 대한 정정이 남아 있다. 절차 설명 안에 들어 있는 관측값도 AGENTS.md 1.4의 예외가 아니다. 금지된 측정값 자체는 이 연구에 재인용하지 않는다. [C1, C2]

Trigger: oscillation, rounds 2, 3, 4.

- [P1] [P1] README.md:424 — 데이터셋 파생 측정값이 추적 문서에 남아 F3의 저장소 경계를 계속 위반한다

## Failed fixes

- 첫 수정은 ignore 규칙을 추가했지만 이미 추적된 데이터셋에는 적용되지 않았다. 이어진 수정은 원본 릴리스 파일을 제거하고 평가 테스트를 합성 입력으로 전환했다. 이는 필요한 조치였지만 다른 문서에 복사된 내용까지 제거했다는 증거는 아니었다. 초기 수정의 귀속은 제공된 리뷰 연혁과 cycle 1 기록에 근거한다. [C3, C5, C7]
- cycle 1 이후 수정은 실제로 범위를 넓혔다. Result에는 연구 인용·실측 보고서·노트북을 정리하고 전체 index와 게시 예정 새 blob을 검사했다고 기록되어 있다. 현재 Kiwi 문서도 일반 절차만 남아 있다. 따라서 이번 실패를 다시 단순한 경로 검사 실패라고만 설명하면 앞선 수정의 변화를 놓친다. [C3, C4]
- 그러나 앞선 완료 근거인 '알려진 데이터셋 서명이 없다'는 결과는 남은 문장 모두가 허용된 내용이라는 결론을 뒷받침하지 못한다. README의 절차 문단에는 실제 집계 문장이 여전히 존재한다. 이전 기록은 의미 검토도 수행했다고 하므로, 의미 검토가 없었다고 단정할 수는 없다. 확인되는 실패는 그 검토의 누락 또는 이후 변경에 대한 재검증 누락이다. [C2, C3, C6, C9]

## Sources

### S1 — Repository rules — dataset boundary

- URL: AGENTS.md
- Retrieved: 2026-10-19
- Locator: Section 1.4, lines 45-52
- Fragment: "Never commit or upload dataset content or metadata"; "candidate ranks, returned contexts, or dataset-derived measurements and reports." "Keep these under ignored `artifacts/` locally. Commit only source code, model configuration, generic instructions, and synthetic test fixtures."
- Applicability: 금지 대상과 허용 대상을 규정한다. 집계 관측에도 적용되며 일반 절차와 설정까지 금지하지 않는다.
- Counterevidence: 데이터셋을 언급하는 모든 문서나 모든 숫자를 금지하는 규칙은 아니다.
- Validation: 추적 내용의 출처와 의미를 허용 범주에 대조한다.

### S2 — README — evidence mapping instructions

- URL: README.md
- Retrieved: 2026-10-19
- Locator: Lines 407, 409-449; finding at line 424
- Fragment: 407행: "실제 질문·정답·개수·분할·측정값은 로컬 보고서에만 기록한다." 423행: "`evidence`는 선택한 근거만, `context`는 선택하지 않은 블록까지 담습니다." 425행: "각 참조의 `element_id`와 `location`으로 v11 요소에서 본문을 복원합니다." 이 두 절차 문장 사이 424행의 실제 집계값은 저장소 경계를 지키기 위해 재인용하지 않는다.
- Applicability: 일반 절차 속 실제 dev 집계와 과거 집계 정정이 남은 위치를 직접 확인했다.
- Counterevidence: 같은 절의 고정 임계값과 표본 표시 설정은 실제 데이터셋 집계와 구별해야 한다.
- Validation: 424행의 관측을 로컬로 옮기고 주변 복원·라벨링 절차가 유지되는지 확인한다.

### S3 — F3 cycle 1 research and recorded implementation result

- URL: docs/research/review-offline-retrieval-seven-model-benchmark-f3-1.md
- Retrieved: 2026-10-19
- Locator: Failed fixes, lines 15-19; Result and Unresolved limits, lines 175-181
- Fragment: "수정 후 전체 index와 모든 수정 전 검출 위치를 다시 검사했고 추적된 ignore 경로와 알려진 데이터셋 서명은 없었다." "서명 검사는 알려진 원문을 찾는 수단이므로 의미별 내용 검토를 함께 사용했다." "이는 새 게시 객체 검사이며 과거 노출을 지웠다는 주장이 아니다."
- Applicability: 앞선 수정이 경로 제거에서 내용 정리로 확장되었음과 당시 완료 근거의 범위를 보여준다.
- Counterevidence: 독립 검증된 실행 증거가 아니라 이전 구현 세션의 기록이다. 실제 패턴·감사 목록은 이번에 확인하지 못했다.
- Validation: 기록된 검사 대상과 최종 게시 tree를 비교하고 README 문장의 존속·재도입 시점을 확인한다.

### S4 — Kiwi BM25 comparison procedure after sanitization

- URL: docs/kiwi_bm25_review.md
- Retrieved: 2026-10-19
- Locator: Lines 3-7
- Fragment: "이 문서는 일반 절차만 설명한다." "질문·근거·문서/청크 ID·해시·분할·제외 집계·측정 점수·사용량·추천 결과는 Git에 넣지 않는다. 현재의 평가 결과나 승자를 이 문서로 입증하지 않는다."
- Applicability: 이전 실측 보고서를 일반 절차로 바꾼 실제 결과이며 README에도 적용할 수 있는 분리 방식이다.
- Counterevidence: 이 파일의 정리는 다른 혼합 문서의 준수를 보장하지 않는다.
- Validation: 일반 비교 절차는 유지하고 실제 관측은 로컬 보고서에만 보관한다.

### S5 — Synthetic evaluation item regression tests

- URL: tests/test_eval_items.py
- Retrieved: 2026-10-19
- Locator: Lines 1, 10-15, 29-35, 60-71
- Fragment: "실제 릴리스 대신 합성 행으로 주제별 핵심 사실 추출 회귀를 검사한다." "def test_golden_release_row_becomes_eval_item(tmp_path, topic, answer, structure, key_facts):" "def test_synthetic_multi_hop_facts_preserve_scoring_regressions(tmp_path, context, answer, question, expected):"
- Applicability: 실제 tracked dev 입력에 대한 테스트 의존성이 합성 임시 입력으로 대체된 현재 상태를 확인한다.
- Counterevidence: 기능 회귀 테스트는 README의 관측 문장이나 게시 내용의 적합성을 검사하지 않는다.
- Validation: 합성 입력 기반 회귀를 유지하고 내용 감사를 별도로 수행한다.

### S6 — Git git-grep documentation

- URL: https://git-scm.com/docs/git-grep
- Retrieved: 2026-10-19
- Locator: DESCRIPTION; OPTIONS: --cached
- Fragment: "Look for specified patterns in the tracked files in the work tree"; "search blobs registered in the index file." 전자는 DESCRIPTION의 발췌이며, 후자는 --cached를 선택했을 때의 검사 대상이다.
- Applicability: 패턴 일치 여부와 검사 대상 선택을 설명한다. 의미상 데이터셋 파생 정보의 부재까지 보장하는 명령은 아니다.
- Counterevidence: 이전 감사가 실제로 git grep을 사용했는지는 확인하지 못했다. 이 문서는 패턴 검사 결과를 해석하는 근거다.
- Validation: 검사 대상 tree/index를 명시하고 패턴에 없는 집계 문장도 내용 검토로 발견하는지 확인한다.

### S7 — Git gitignore documentation

- URL: https://git-scm.com/docs/gitignore
- Retrieved: 2026-10-19
- Locator: DESCRIPTION; NOTES
- Fragment: "Files already tracked by Git are not affected"; "To stop tracking a file that is currently tracked, use git rm --cached".
- Applicability: 최초 ignore 변경이 이미 추적된 릴리스를 제거하지 못한 이유를 설명한다.
- Counterevidence: 추적 해제 후 재추가 방지에는 ignore 규칙이 유효하다. 현재 README의 혼합 내용 문제는 별도다.
- Validation: ignore 일치 여부와 index 제거 여부를 구분하고 남은 문서 내용을 따로 확인한다.

### S8 — Presidio FAQ — automated detection warning

- URL: https://presidio.dataprivacystack.org/faq/
- Retrieved: 2026-10-19
- Locator: General → What is Presidio? → Warning
- Fragment: "because it is using automated detection mechanisms, there is no guarantee that Presidio will find all sensitive information." 이 경고의 적용 대상은 Presidio의 비정형·구조화 텍스트 민감정보/PII 탐지다.
- Applicability: 자동 탐지의 무검출 결과를 완전한 제거 증명으로 취급하지 않는다는 참고 사례다.
- Counterevidence: 이 저장소는 Presidio를 사용하지 않으며 데이터셋 집계가 PII라는 뜻도 아니다. 저장소 금지 범위는 S1에서 나온다.
- Validation: 알려진 패턴 검색과 별개로 실제 관측 주장 및 허용 설정을 구별하는 대조 검토를 수행한다.

## Claims

- C1 (source; S1): 저장소 규칙은 데이터셋 파생 측정값을 금지하면서 일반 절차·설정·합성 fixture를 허용한다.
- C2 (interpretation; S1, S2): 현재 README:424의 실제 dev 집계와 과거 집계 정정은 절차 문단에 포함되어 있어도 금지된 데이터셋 파생 관측이다.
- C3 (source; S3): cycle 1 Result는 전체 index·알려진 서명·새 게시 blob 검사와 의미 검토를 기록한다. 이번 연구는 그 실행을 독립 검증하지 않았다.
- C4 (interpretation; S4): 현재 Kiwi 문서는 일반 절차와 로컬 보관 경계만 남아 있어 이전 내용 정리가 일부 유효했음을 보여준다.
- C5 (interpretation; S5): 현재 평가 테스트는 합성 임시 릴리스를 생성하지만 추적 문서의 게시 적합성을 검증하지 않는다.
- C6 (interpretation; S2, S3, S6): 전체 파일에 대한 알려진 패턴의 무검출은 전체 의미 범주의 부재를 입증하지 않는다. 현재 README와 이전 완료 기록의 공존은 검사 누락 또는 이후 재도입을 구분할 필요를 만든다.
- C7 (source; S7): Git ignore는 이미 추적된 파일에 영향을 주지 않으며 추적 해제와 이후 재추가 방지는 별개의 조치다.
- C8 (source; S8): Presidio 공식 문서는 자체 자동 민감정보 탐지의 완전성을 보장하지 않는다. 이는 이 저장소의 구체적 탐지 성능에 대한 증거는 아니다.
- C9 (interpretation; S1, S2, S3, S4, S5, S6): 다음 수정은 혼합 문서의 관측 주장을 출처별로 분류하고 마지막 변경 이후 실제 게시 내용에 대해 재검증해야 한다. 역사적 비교로 잔존과 재도입을 구분하며 감사 결과와 원본은 로컬에 보관해야 한다.

## Core theory

Git 문서는 grep을 지정된 패턴의 검색으로 설명하고, 작업 트리·index·tree 객체라는 검사 대상을 구분한다. 따라서 전체 파일을 검색했다는 범위의 완전성과 금지된 의미를 모두 알아낸다는 판별의 완전성은 다르다. Presidio의 공식 문서도 자동 탐지가 모든 민감 정보를 찾는다는 보장을 하지 않는다. 후자는 탐지 한계의 참고 사례이며, 이 저장소의 집계값을 PII라고 주장하는 근거는 아니다. 여기서 금지 범위를 정하는 근거는 AGENTS.md이다. [C1, C6, C8]

## Applicability

README.md:409-449는 입력 연결·본문 복원·라벨링 절차를 설명한다. 그 사이의 424행만 현재 데이터셋의 집계와 과거 관측 정정을 게시한다. 해당 관측 문장을 로컬 보고서로 옮기고 주변의 일반 알고리즘 설명을 유지하면 기능 설명을 보존하면서 경계를 지킬 수 있다. 같은 검토를 README 전체, 연구 페이지의 Result, 표·주석·노트북 출력에도 적용해야 한다. 숫자의 존재 자체로 삭제하지 말고 설정값·공개 모델 사양·합성 fixture와 실제 데이터셋 관측을 구분해야 한다. [C1, C2, C4, C5, C9]

## Hypothesis

이번 재발의 핵심은 검사 결과의 의미를 과대해석한 데 있다. 원문·식별자·해시 같은 알려진 서명과 이미 발견한 위치를 제거한 사실을 저장소 전체의 의미상 준수로 확대했다. 실제 집계를 설명문으로 재서술하면 원본 행의 서명이 없어도 금지된 파생 정보가 남는다. 문서 전체를 '일반 절차'로 분류하는 대신 혼합 문서 안의 각 관측 주장까지 출처와 의미로 분류해야 한다. 다만 README 문장이 정리 당시부터 남았는지 이후 다시 들어왔는지는 아직 구분되지 않았다. [C1, C2, C3, C6, C9]

## Counterevidence

- 이전 수정 기록은 전체 index 검사와 의미 검토를 명시한다. 따라서 검사 범위가 처음부터 특정 디렉터리뿐이었다거나 자동 검색만 사용했다고 단정할 수 없다. [C3]
- 현재 Kiwi 문서는 실측값을 제거하고 로컬 보관 경계를 명시한다. 평가 테스트도 합성 임시 릴리스를 생성한다. 앞선 수정에는 유효한 결과가 있다. [C4, C5]
- README에는 고정 임계값과 표본 표시 설정 등 허용 가능한 숫자도 있다. 모든 숫자나 dev 언급을 금지하는 검사는 저장소 규칙보다 넓고 부정확하다. [C1, C2]
- 역사적 README와 실제 검사 입력을 확보하지 못했다. 발견된 문장이 검사 후 재도입되었다면 직접 원인은 최초 분류 누락보다 검사 시점과 최종 게시 내용의 불일치에 가깝다. [C3, C9]

## Alternatives

- 이번에 지적된 한 문장만 삭제하면 알려진 위반은 없앨 수 있다. 그러나 다른 설명문 속 관측값에 대한 검토 없이 F3 전체를 해결했다고 판단하면 같은 완료 기준을 반복한다. [C2, C6, C9]
- 이번 숫자들을 검색 목록에 추가하면 재발 위치를 찾는 보조 수단은 된다. 다른 값·표기·재서술을 포함한 파생 정보의 부재를 입증하지는 못한다. [C6, C9]
- README 전체를 ignore하거나 모든 문서를 삭제하면 일반 절차까지 잃는다. 혼합 문서는 금지된 관측 주장만 분리하는 편이 규칙의 허용 범위에 맞는다. [C1, C2]
- 새 DLP 서비스나 영구적인 범용 검사기를 도입할 필요는 아직 입증되지 않았다. 우선 로컬 감사 목록과 내용 검토로 이번 누락을 재현하고 수정 범위를 검증한다. Presidio 인용은 도입 권고가 아니다. [C6, C8, C9]
- 공유 이력 재작성은 현재 README의 분류 오류를 해결하지 않는다. 기존 노출과 앞으로 게시할 객체는 별도로 확인해야 하며, 이번 연구는 과거 노출의 삭제를 검증하지 않았다. [C3, C9]

## Experiment

구현 세션 또는 서버가 다음 검사를 수행한다. (1) 이전 정리 커밋과 round 3·4의 README를 비교해 해당 문장이 계속 남았는지 재도입되었는지 확인하고, 당시 검사 대상·패턴·최종 검사 시점을 대조한다. (2) 수정 전 전체 추적 파일 목록을 만들고, 검색 결과가 없는 파일까지 포함하여 혼합 문서의 데이터셋 관련 주장을 읽는다. 각 주장을 일반 절차·설정·공개 출처·독립 합성 예제·실제 데이터셋 관측으로 분류하며 목록은 ignored artifacts/에만 보관한다. 이 절차는 실제 숫자를 검색어로 먼저 알려주지 않아도 README:424를 발견해야 한다. (3) 로컬 검토용 합성 대조 사례에서 가상의 '현재 dev 집계'와 단순 고정 설정을 구분하고, 집계값의 쉼표·표현·숫자를 바꿔도 관측이라는 분류가 유지되는지 확인한다. 이를 저장소에 새 기능으로 추가할 필요는 없다. (4) 로컬 원본을 보존한 뒤 금지된 관측만 제거하고 모든 최초 발견 위치를 재검토한다. 마지막 문서·연구 결과 추가 후 staged blob과 최종 commit tree에 대해 다시 검사하며 알려진 서명 검색은 보조 증거로만 사용한다. (5) 게시 예정 객체와 기존 원격 이력의 노출 범위를 구분해 기록하고 서버가 필요한 저장소 검사를 실행한다. 수정 전 문장을 발견하지 못하면 감사 방법이 불충분하다. 역사적 비교에서 정리 후 재도입이 확인되면 원인 가설을 최종 변경 후 재검증 누락으로 수정한다. 이 연구에서는 해당 검사나 테스트를 실행하지 않았다. [C1, C2, C3, C5, C6, C7, C9]

## Result

Observed, still a draft: the aggregate sentence persisted unchanged in README.md across `400f768`, `7371896`, `9063678`, `d26c9f1`, and `500eae4`; it was not reintroduced. The complete pre-change index and local originals were preserved under ignored `artifacts/review-round4/`. Claim review found aggregate observations without using the reported numbers as search keys. During that experiment, the owner's explicit clarification changed the publication boundary: those observations are allowed, while actual dataset records remain private. Accordingly, the README measurements are retained and F3 is disputed under the current requirement. `clarified_controls.py` checked ten independently authored, manually classified control claims: aggregate values remain publishable when commas, wording, or numbers change; actual records remain private in JSONL or embedded prose. This is a local research check, not an automated privacy guarantee. The documentation change is identified by the commit subject `docs: clarify that aggregate measurements may be published` (based on `500eae4`); its exact commit ID is recorded with the final publication check. No product code or tests were changed; pytest was not rerun for this documentation correction. Final staged/committed document review, Ruff, rule-file byte equality, whitespace checks, and the outgoing-object audit are recorded separately. Existing public history was not erased, and this draft does not claim independent verification of the benchmark measurements.

Publication record: `abeba03` implements the clarified publication rule and retains the cited README measurement. The local control review passed ten cases; the staged document check passed for all indexed files, Ruff reported `All checks passed!`, and rule-file equality and whitespace checks passed. `git diff --exit-code d26c9f1 -- rag frontend tests config.yaml requirements.txt requirements-benchmark.txt` found no product-code, configuration, dependency, or test changes, so the prior focused test evidence is unaffected. The final commit-tree and outgoing-object checks follow this record update before pushing. The narrower owner instruction, rather than an assertion that the aggregate was absent, is the reason for the disagreement disposition.

Follow-up test cleanup: after the request to include an explicit cleanup record, the implementation audited all nine test files changed by the task plus four affected regression files. Source/artifact binding, legacy rejection, independent input readers, OCR state and review behavior, notebook forwarding, mapping, and retrieval metric checks all guard current behavior. No obsolete paths, redundant cases, or outdated skips/xfails were identified, so no further tests were removed. The structural check found no identical test bodies or skip/xfail markers in these thirteen files. On the product code at `bc3a16b`, `.venv/Scripts/python -m pytest -q tests/test_local_inputs.py tests/test_eval_items.py tests/test_retrieval_benchmark.py tests/test_retrieval_benchmark_full_dev.py tests/test_retrieval_benchmark_artifacts.py tests/test_retrieval_benchmark_integrity.py tests/test_evidence_mapping.py tests/test_notebook_settings.py tests/test_ocr_selection.py tests/test_ocr_review.py tests/test_ocr_captions.py tests/test_ir_metrics.py tests/test_retrieval.py --tb=short` returned `198 passed, 4 warnings in 46.04s`; the warnings are existing RAGAS deprecations. Ruff, whitespace, and rule-file equality checks also passed. This is focused regression evidence, not the server-owned full gate, a fresh GPU benchmark, or independent review. Aggregate publication remains allowed and F3 remains disputed under the owner's clarification.

## Unresolved limits

현재 추적 소스와 이전 연구의 기록을 읽었으며 파일을 수정하거나 shell·테스트를 실행하지 않았다. 과거 커밋별 README, 실제 감사 목록·검색 패턴, 게시 객체 그래프는 독립 검증하지 못했다. 이전 Result의 성공 주장은 구현 세션의 기록으로 취급한다. README의 위반은 직접 확인했지만 다른 모든 추적 파일의 준수 여부를 인증하는 연구는 아니다. 이 페이지 자체에도 실제 데이터셋 값이나 원문을 복사하지 않아야 한다. [C2, C3, C9]
