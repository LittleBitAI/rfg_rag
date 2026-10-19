# Review research — F1, cycle 2

Draft research before the fix of review round 3 of PR #67, written 2026-10-19. It is not a verified fact or a shared rule: the review reads it with the fix.

## Problem

F1의 불변식은 실제 데이터셋 레코드와 발췌를 공개 Git에 commit 또는 upload하지 않고, 레코드 없는 집계만 공개하는 것이다. 첫 수정은 현재 보고서의 내용을 정리했고, 다음 수정은 작업 브랜치 이력을 교체했지만, 이미 업로드된 내용의 원격 접근 차단까지 입증하지 못했다. 연구 문서는 그 상태에서 과거 내용을 찾는 위치와 명령을 공개했다. 이번 연구는 원문과 해당 식별자를 재기재하지 않는다. [C1, C3, C4, C7]

Trigger: repeat, rounds 2, 3.

- [P0] docs/research/review-restore-aggregate-measurements-f1-1.md — 아직 조회 가능한 비공개 레코드의 위치를 다시 공개함. 상세 조회 위치는 비공개 로컬 사고 목록에만 보관한다.

## Failed fixes

- Round 1 뒤 수정은 두 보고서의 실제 사례를 집계와 일반 설명으로 바꿨다. 현재 파일에서는 이 변경을 확인할 수 있다. 그러나 이전 연구의 관측 기록에 따르면 당시 오염된 커밋은 작업 브랜치의 조상이자 PR 커밋으로 남았다. 파일 삭제를 추가하는 커밋은 과거 내용을 제거하지 못했다. [C3, C4]
- Round 2 뒤 수정은 정리한 파일을 보존하면서 작업 이력을 교체했다. 이는 활성 조상에서 오염된 커밋을 제외하는 조치였지만, 연구 문서 자체가 공유 base·다른 참조·GitHub 캐시·과거 PR 참조의 제거를 입증하지 않았으며 Support 삭제 요청도 하지 않았다고 기록한다. 따라서 원격 제거를 완료하는 수정이 아니었다. [C4, C5, C7]
- 같은 수정에서 연구 문서에 과거 커밋 식별자, 민감 내용의 정확한 위치와 조회 명령을 남겼다. 원문을 다시 인용하지 않았다는 점만으로 이 안내의 노출 효과를 해소할 수는 없다. 이전 연구의 맥락 소실 가설도 실제 파일·이력 관측과 별개의 미확인 설명으로 남아 있어, F1 해결의 근거가 되지 못했다. [C4, C7]

## Sources

### S1 — Repository rules — dataset privacy boundary

- URL: AGENTS.md
- Retrieved: 2026-10-19
- Locator: §1.4, lines 45–57
- Fragment: Never commit or upload actual dataset records, such as real questions, answers, document or evidence text, saved OCR transcriptions, or exports that disclose those records. This includes JSONL files and actual records copied into other formats. Keep these under ignored `artifacts/` locally. Aggregate measurements and descriptive statistics may be committed, including dataset counts, quality scores, latency, resource usage, and reports discussing those values, provided they do not include actual dataset records or excerpts.
- Applicability: 파일 형식과 무관하게 실제 레코드는 비공개이며, 레코드 없는 집계는 공개할 수 있다는 F1의 기준이다.
- Counterevidence: 원격 서비스가 삭제를 지원할 조건이나 과거 업로드의 복구 절차는 규정하지 않는다.
- Validation: 공개 대상에서 실제 레코드·발췌를 제외하면서 허용된 집계를 보존한다.

### S2 — Seven-model publication contract

- URL: docs/benchmarks/seven_model/protocol.md
- Retrieved: 2026-10-19
- Locator: 집계 결과 보관, lines 65–69
- Fragment: 두 기록은 완료 당시 v3 봉인이 없는 역사적 측정이다. 기존 추천을 현재 검증을 통과한 확정 결론으로 승격하지 않는다. 원시 질문·정답·근거, 문항별 순위/점수·시간 표본, split ID, 실제 사례별 감사는 원래 무시된 `artifacts/seven_model/record/`와 `artifacts/seven_model_full_dev/record/`에 둔다. 집계 파일은 Git에 보관하고 원시 레코드는 로컬에 보관한다.
- Applicability: 문항별 감사와 집계 보고서를 구분하는 이 작업의 구체적 계약이다.
- Counterevidence: 로컬 보관 위치를 정했다고 이미 업로드된 객체가 제거되지는 않는다.
- Validation: 문항별 감사는 로컬에만 두고 공개 보고서에는 집계와 측정 한계를 남긴다.

### S3 — Current full-dev audit paragraph

- URL: docs/benchmarks/seven_model/full_dev/report.md
- Retrieved: 2026-10-19
- Locator: 공백이 Kiwi보다 높은 이유에 대한 감사, current lines 75–77
- Fragment: 문항 ID·기관/질문 설명·개별 순위·토큰별 점수·문항별 진단 결과는 비공개 로컬 `artifacts/seven_model_full_dev/record/audit.json`과 원래 `report.md`에만 보관한다. 이 공개본은 위 분할별 집계와 일반적인 해석만 제공한다. ... 이 진단들은 알려진 세 사례의 원인 분석이며 새 정식 비교나 전체 개선율 추정이 아니다.
- Applicability: 현재 해당 문단에서 내용 정리와 해석의 한계를 직접 확인했다.
- Counterevidence: 현재 파일에 대한 관측이며 과거 커밋이나 원격 사본의 상태를 증명하지 않는다.
- Validation: 일반 설명과 집계를 보존하면서 개별 사례가 다시 들어오지 않았는지 확인한다.

### S4 — Current historical audit paragraph

- URL: docs/benchmarks/seven_model/historical/report.md
- Retrieved: 2026-10-19
- Locator: Stage 1 audit paragraph, current line 76
- Fragment: 이 공개본은 위 분할별 집계와 일반적인 해석만 제공한다. 이 감사가 공백의 일반적인 언어 이해 우위나 모든 역전의 원인을 입증하는 것은 아니다. 현재 Kiwi 규칙·사전·질문·융합은 진단 중 변경하지 않았다.
- Applicability: 두 번째 보고서도 현재 해당 문단에서 집계와 일반 해석만 제공하는지 확인했다.
- Counterevidence: 과거 버전의 제거 여부는 보여주지 않는다.
- Validation: 두 보고서를 함께 확인해 동일 사례의 재복제를 막는다.

### S5 — Earlier F1 research and appended correction observations

- URL: docs/research/review-restore-aggregate-measurements-f1-1.md
- Retrieved: 2026-10-19
- Locator: Sources; 수정 세션의 실험; Result; Unresolved limits. 민감 이력의 정확한 조회 위치는 생략
- Fragment: 이번 수정의 검증은 전자에 한정하며 후자의 완료를 주장하지 않는다. ... 이력 교체는 공유 base나 다른 브랜치·태그를 고치지 않으며 로컬 reflog·기존 clone·fork·GitHub 캐시와 옛 PR 참조의 제거를 입증하지 않는다. GitHub Support에 삭제를 요청하거나 삭제 완료를 확인한 상태도 아니다.
- Applicability: 현재 파일 정리 뒤에도 조상이 남았다는 당시 관측, 이후 이력 교체의 범위, 원격 제거 미완료를 기록한다. 현재 문서에 조회 식별자와 명령이 남아 있음도 직접 읽었다.
- Counterevidence: 당시 실행 기록이며 현재 원격 상태의 독립 증거가 아니다. 초기 맥락 소실 가설은 후반 관측과 구별해야 한다.
- Validation: 다음 결과는 내용 정리·이력 정리·원격 접근 차단을 구분하고, 공개 문서에서 조회 안내를 제거한다.

### S6 — GitHub Docs — Removing sensitive data from a repository

- URL: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository
- Retrieved: 2026-10-19
- Locator: About sensitive data exposure; Fully removing the data from GitHub; Support eligibility warning
- Fragment: “only assist in the removal of sensitive data in cases where we determine that the risk can't be mitigated by rotating affected credentials.”
- Applicability: 실제 웹 검색 후 원문을 열었다. 재작성 뒤에도 clone·fork·PR·SHA 접근이 남을 수 있다. 서버 제거 절차는 비PR 참조와 fork 정리를 전제로 하며, Support는 비민감 데이터 제거를 지원하지 않는다.
- Counterevidence: 문서의 가능성이 이 저장소의 실제 잔존 경로나 Support 수락을 입증하지는 않는다.
- Validation: 적격성·선행조건·서버 처리와 접근 결과를 별도로 확인한다.

### S7 — Git documentation — git-gc

- URL: https://git-scm.com/docs/git-gc
- Retrieved: 2026-10-19
- Locator: NAME; NOTES, object retention and git-notes exception
- Fragment: “Cleanup unnecessary files and optimize the local repository”; “a note (of the kind created by git notes) attached to an object does not contribute”
- Applicability: 로컬 GC는 브랜치·태그 외에도 index·remote-tracking 참조·reflog·refs 아래 참조가 가리키는 객체를 보존한다. git-notes 첨부 자체는 보존 참조가 아니라는 예외가 있다.
- Counterevidence: 일반 Git의 로컬 동작 설명이며 GitHub 내부 참조나 서버 처리 상태를 관측한 자료는 아니다.
- Validation: 브랜치 조상 검사와 객체·참조·원격 접근 검증을 구분한다.

## Claims

- C1 (source; S1): 저장소는 실제 레코드와 발췌의 commit·upload를 금지하며, 그 내용이 없는 집계의 공개는 허용한다.
- C2 (source; S2): 벤치마크 계약은 문항별 감사·순위·점수·split ID를 로컬에 보관하고 집계 파일을 Git에 보관하도록 구분한다.
- C3 (interpretation; S3, S4): 현재 두 보고서의 해당 감사 문단은 개별 사례 대신 집계와 일반 설명으로 정리되어 있다. 이것은 현재 내용 정리의 증거다.
- C4 (interpretation; S5): 이전 연구는 첫 내용 정리 이후 오염된 조상이 남았다고 기록하고, 후속 이력 교체는 원격 제거를 입증하지 않는다고 제한한다. 같은 문서에는 과거 내용을 찾는 식별자와 명령이 남아 있다.
- C5 (source; S6): GitHub는 이력 교체 후에도 외부 복사본과 PR·캐시 접근이 남을 수 있다고 설명한다. 서버 제거에는 선행조건과 Support의 민감성 판단이 있으며 지원은 보장되지 않는다.
- C6 (interpretation; S7): Git의 로컬 GC는 여러 참조가 가리키는 객체를 보존하므로 현재 브랜치 조상에서 제외됐다는 사실만으로 객체 삭제를 추론할 수 없다.
- C7 (interpretation; S5, S6, S7): 이번 반복의 직접적인 설명은 검증 범위와 F1의 공개 경계가 맞지 않았다는 것이다. 내용 정리와 조상 교체는 필요했지만, 공개 조회 안내와 원격 접근 가능성에 대한 별도 처리가 남았다.
- C8 (interpretation; S1, S2, S5, S6): 적절한 다음 조치는 공개 문서의 조회 안내 제거, 관리 가능한 오염 참조 조사·정리, 조건에 맞는 원격 제거 처리, 처리 후 접근 검증이다. 상세 증거는 비공개로 유지하며, 과거 업로드 취소나 모든 기존 복사본 삭제를 보장해서는 안 된다.

## Core theory

Git의 도달 가능성 변경과 객체 삭제는 별도 작업이다. Git은 브랜치 이외 참조와 reflog 등이 가리키는 객체도 보존한다. GitHub 역시 이력 재작성 이후의 접근 가능성과 서버 측 제거를 구분하며, Support 지원에는 민감성 판단과 제거 선행조건이 있다. [C5, C6]

## Applicability

현재 두 벤치마크 보고서의 해당 감사 문단은 집계와 일반 설명으로 정리되어 있다. 다음 편집의 직접 대상은 이전 연구 문서에 남은 오염 이력 식별자·정확한 위치·조회 명령이다. 같은 안내가 공개 색인이나 PR 설명에 복제되었는지도 확인해야 한다. 상세 사고 목록은 무시된 로컬 artifacts에 두고, 공개 문서에는 범위·처리 상태·검증 한계만 남기는 것이 적절하다. 별도로 관리 가능한 오염 참조와 fork를 조사하고, 필요한 원격 제거는 GitHub의 조건부 Support 절차로 처리해야 한다. Support 수락이나 삭제 완료를 문서 편집으로 대신할 수 없다. [C1, C2, C3, C5, C7, C8]

## Hypothesis

반복 실패의 원인은 완료 기준을 현재 파일, 활성 브랜치 조상, 원격 공개 접근으로 차례로 좁혀 검증한 데 있다. 마지막 수정은 브랜치 정리를 입증하면서도 원격 잔존을 미해결로 남겼고, 공개 연구 문서에는 잔존 내용을 찾는 안내를 추가했다. 다음 수정은 공개 안내 제거와 원격 잔존 처리·검증을 함께 다뤄야 한다. 실제 잔존 원인이 PR 내부 참조인지 캐시인지 다른 참조인지는 아직 특정할 수 없다. [C4, C5, C6, C7]

## Counterevidence

- 현재 보고서의 해당 문단에서는 실제 사례 대신 집계와 일반 해석을 확인했다. 첫 내용 정리 자체가 실패했다고 볼 근거는 없다. [C3]
- 이전 연구는 원격 제거를 완료했다고 명시하지 않고 한계를 기록했다. 문제는 한계를 숨겼다는 데 있지 않고, 그 한계가 남은 상태에서 F1 해결로 취급된 데 있다. [C4, C7]
- GitHub 문서는 가능한 잔존 경로를 설명할 뿐, 이 저장소의 실제 잔존 경로를 특정하지 않는다. 이번 세션은 과거 원격 응답을 재현하지 않았다. [C5, C7]
- 저장소의 비공개 계약과 GitHub Support의 민감 데이터 판정은 동일한 기준이라고 단정할 수 없다. Support 지원이 거절될 가능성도 남는다. [C1, C5, C8]

## Alternatives

- 보고서나 연구 문서의 현재 내용만 다시 삭제하기: 공개 안내를 줄이는 데 필요하지만 원격 과거 객체의 접근 차단을 증명하지 못하므로 단독 해결책으로는 부족하다. [C5, C7]
- 작업 브랜치를 다시 squash하거나 force-push하기: 오염된 조상이 실제 남아 있다면 필요하지만, 이미 조상을 교체한 상태에서 반복해도 원격 잔존 문제를 해결했다는 증거는 늘지 않는다. 먼저 남은 참조와 접근 경로를 확인해야 한다. [C4, C5, C7]
- 로컬 garbage collection 실행 또는 자동 삭제 대기: 로컬 저장소 정리는 GitHub 서버 처리의 증거가 아니며, 객체 보존은 참조와 설정에도 좌우된다. [C5, C6]
- 자격증명 회전으로 해결하기: 이번 대상은 데이터셋 내용이므로 회전 가능한 비밀키처럼 무효화할 수 없다. 다만 이 판단이 Support의 지원 수락을 보장하지는 않는다. [C1, C5, C8]
- 이전 연구의 host 맥락 소실 가설을 먼저 조사하기: 그 문서 자체가 미확인이라고 제한하며, 이미 기록된 파일·이력 노출을 해소하지 못한다. 현재 F1에서는 공개 경계와 원격 제거를 먼저 다루는 것이 타당하다. [C4, C7]

## Experiment

다음 수정 세션에서 다음을 분리해 검증한다. ① 비공개 로컬 사고 목록으로 알려진 원문과 오염 이력 식별자를 대조하되, 결과에는 일치 건수와 처리 상태만 남긴다. 현재 추적 파일·공개 색인·게시 설명에 원문과 조회 안내가 없는지 확인하고 허용된 집계가 보존되는지도 확인한다. ② 관리 가능한 브랜치·태그·PR 이력과 fork의 오염 참조를 조사해 정리 범위를 확정한다. ③ 필요한 Support 처리에는 상세 식별자를 비공개로 제공하고, 처리 완료 여부와 예외를 기록한다. ④ 처리 뒤 기존 접근 경로를 통제된 환경에서 다시 검사한다. 오류 응답은 정상적인 공개 대조 요청과 비교해 인증 실패나 rate limit과 구분한다. 브랜치에서 제외됐는데 과거 내용이 계속 반환되면 가설이 지지된다. 공개 접근 불가와 서버 처리 증거를 함께 확보하면 관리 가능한 원격 범위의 복구를 뒷받침한다. 이 검사는 아직 실행하지 않았다. [C5, C7, C8]

## Result

구현 세션에서 관측했으며 여전히 독립 검증 전 초안이다. 수정 커밋은 이 페이지와 공개 안내 제거·검토 설명 수정을 함께 포함하는 `docs: remove disclosure guides and correct review evidence`다. 비공개 로컬 사고 목록 대조에서 지적한 이전 연구 페이지에 조회 식별자 11회, 별도 게시 표면인 PR 본문에 15회를 확인했다. 공개 색인과 PR 댓글·리뷰의 추가 일치는 없었다. 현재 페이지의 조회 식별자·과거 위치·명령을 제거하고 PR 본문도 처리 상태와 건수만 남기도록 정리한다. 9개 공개 브랜치에는 조사한 오염 커밋의 조상이 없었으며 공개 태그와 fork는 각각 0개였다. 무인증 HTTP 대조에서는 정상 공개 파일이 200이었고 과거 객체 두 건도 모두 200으로 실제 감사 문구 4개와 2개를 반환했다. 남은 rate limit도 확인했으므로 인증 실패나 요청 제한 때문에 접근 결과를 오판한 경우는 아니었다. 이 관측은 브랜치 정리와 원격 접근 차단을 동일시한 가설을 반박하며 원격 잔존의 존재를 지지하지만, 잔존 원인이 내부 PR 참조인지 캐시인지는 특정하지 못한다. 상세 식별자와 응답 원문은 공개하지 않는다. Support 처리는 접수·완료하지 않았고 원격 접근 차단은 미해결이다. F1을 해결로 분류하지 않는다. 초기 수정에서는 제품·테스트 코드를 바꾸거나 pytest를 실행하지 않았으며, 후속 집중 실행은 아래에 따로 기록한다. 서버 소유 전체 게이트는 pending이다. [C4, C5, C6, C7, C8]

오프라인 점검에서 `.venv/Scripts/ruff check .`는 `All checks passed!`, `git diff --no-index CLAUDE.md AGENTS.md`와 `git diff --check`는 exit 0이었다. 비공개 목록 기반 Python 대조는 현재 추적 파일·공개 색인의 알려진 조회 식별자와 실제 감사 문구가 각각 0개임을 확인했다. 기존 정리된 작업 파일 61개 중 연구 두 페이지·검토 보고서·문서 색인 두 파일을 제외한 56개는 바이트가 같았고, 모든 집계 파일은 보존했다. 공개 보고서·protocol의 상대 링크 26개는 추적 파일로 연결되었다. 제품·테스트·설정·의존성 변경은 0개이며, 변경 다섯 파일은 UTF-8 without BOM이다. F2의 diff 접기 주장은 `git check-attr linguist-generated` 네 경로 모두 unspecified와 비공개 provenance 파일의 미추적 상태로 재현했고 같은 주장의 별도 문서는 0개였다. 보고서는 실제 속성과 공개 검토 범위에 맞게 고쳤다. 공개 안내가 이전 활성 작업 커밋에도 있으므로 이 작업 이력만 다시 교체하지만 원격 제거 증거로 취급하지 않는다. 상세 사고·참조·지원 요청 초안은 무시된 로컬에만 보관한다. Support에 제출하지 않았으며 F1 전체 해결은 보류한다.

### 후속 테스트 정리와 집중 재실행

후속 요청에 따라 실제 diff와 관련 테스트를 다시 감사했다. `git diff --name-status d7d1682 HEAD -- rag frontend tests config.yaml 'requirements*' ':(glob)golden_pipeline/**/*.py'`는 출력 없이 exit 0으로 제품·테스트·설정·의존성 변경이 없음을 확인했다. 그렇더라도 비공개 로컬 입력과 산출물 경계에 관련된 다음 세 파일을 읽고 현재 동작을 지키는지 확인했다.

- `tests/test_local_inputs.py`: 비공개 입력의 무손실 복원·덮어쓰기 방지·독립 소비자와 CLI 경로를 유지한다.
- `tests/test_notebook_settings.py`: 저장 실행 결과가 없는 상태와 OCR·검색·생성 설정 전달을 유지한다.
- `tests/test_retrieval_benchmark_artifacts.py`: 독립 합성 자료의 봉인·고정 가중치·순위·컨텍스트·시간 표본·경로 일관성을 유지한다. 실제 레코드를 공개하지 않더라도 로컬 파이프라인의 이 동작은 남아 있다.

세 파일의 테스트 함수 16개에 만료된 skip·xfail은 0개였고, 제거된 경로·형식·옵션을 검사하거나 더 강한 검사로 대체된 중간 테스트·중복 관측은 없었다. 테스트는 추가·삭제·통합하지 않았다. 정리 후 `.venv/Scripts/python -m pytest -q tests/test_local_inputs.py tests/test_notebook_settings.py tests/test_retrieval_benchmark_artifacts.py`는 `46 passed, 4 warnings in 68.17s (0:01:08)`로 종료했다. 경고 네 개는 기존 RAGAS deprecation이다. `.venv/Scripts/ruff check .`는 `All checks passed!`, 규칙 파일 대조도 exit 0이었다. 감사 기록 커밋은 이 페이지와 해당 색인을 포함하는 `docs: record test cleanup audit for review repairs`다. 이 집중 실행은 원격 삭제나 전체 게이트 통과의 증거가 아니며 F1은 여전히 미해결이다.

## Unresolved limits

초기 조사는 읽기 전용이었고 위 Result는 그 뒤 구현 세션의 관측이다. 현재 내용·공개 안내·브랜치 정리만으로 원격 제거 완료를 주장하지 않는다. 필요한 비공개 Support 요청과 서버 측 처리 완료 증거가 없으므로 처리 뒤 접근 불가 대조는 실행할 수 없었다. 캐시·내부 PR 참조 중 실제 보존 원인, 모든 복제본의 범위, Support 지원 가능성은 미확인이다. 이 환경의 Git·gh로는 Support의 처리나 서버 garbage collection을 실행할 수 없다. 복구는 지속적인 공개 접근을 줄이는 조치이며 이미 발생한 업로드 사실을 소급해 없애거나 제3자의 기존 복사본 삭제를 보증할 수 없다. 유료 호출·벤치마크·제품 코드·테스트 추가는 없고 최종 게이트는 서버 소유로 pending이다. [C4, C5, C6, C7, C8]
