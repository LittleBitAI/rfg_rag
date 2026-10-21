# Review research — F1, cycle 1

Draft research before the fix of review round 2 of PR #67, written 2026-10-19. It is not a verified fact or a shared rule: the review reads it with the fix.

## Problem

The original F1 finding cannot be reliably identified from this retry. The supplied context contains the rejection of source conversation:F1/rounds/1-2, but neither the original finding nor the rejected research answer. Reconstructing F1 from an unrelated historical finding would risk filing research under the wrong issue, a failure already documented in this repository. [C2, C3]

Trigger: repeat, rounds 1, 2.

- [P0] 이전 PR 이력에 실제 레코드가 남아 과거 내용에 접근할 수 있음. 상세 식별자와 조회 위치는 비공개 로컬 사고 목록에만 보관한다.

## Failed fixes

- The earlier F1 implementation fixes are not available in the supplied context, so their changes and failure mechanisms cannot be established. The rejected conversation reference must not be replaced with a repository file unless that file actually records the same finding and chronology. [C3]
- A historical repository investigation records format retries that received only the rejection message and subsequently researched a different issue. Its reported document corrections did not establish that the retry preserved the original task context. This is evidence about the research process, not evidence identifying the current F1 implementation failure. [C2]

## Sources

### S1 — Anthropic — Using the Messages API

- URL: https://platform.claude.com/docs/en/build-with-claude/working-with-messages
- Retrieved: 2026-10-19
- Locator: Multiple conversational turns; official documentation returned by web search
- Fragment: The Messages API is stateless, which means that you always send the full conversational history to the API.
- Applicability: Supports the general need to carry prior context into stateless retries.
- Counterevidence: This describes a particular API. It does not prove how the current Codex host preserves or restores sessions.
- Validation: Inspect the actual retry input and establish whether it includes the finding and rejected answer, independently of session identity.

### S2 — Historical investigation of research misfiling on format retries

- URL: docs/research/review-golden-abc-seven-topic-comparison-f5-1.md
- Retrieved: 2026-10-19
- Locator: Hypothesis, lines 101–103; Counterevidence, lines 105–110; Experiment and Result, lines 120–128
- Fragment: The format retry in wiki-agent tool/main/recovery.py research() runs in a new session and sends no finding. ... Only two retries have occurred, and both misfiled (2 of 2). ... With the finding restored, a model could still drift in principle.
- Applicability: Records a historical failure in which a format-only retry researched another issue. It explains why choosing an arbitrary historical F1 would be unsafe.
- Counterevidence: The page is a historical draft, includes a small sample, and concerns another task. Its host-code observations were not independently verified in this turn.
- Validation: Recover the current original finding and rejected answer, compare subjects before and after the retry, and verify the current host's actual retry payload.

### S3 — 공개 집계와 비공개 사고 관측의 경계

- URL: docs/benchmarks/seven_model/protocol.md
- Retrieved: 2026-10-19
- Locator: 집계 결과 보관
- Fragment: 집계는 Git에 보관하고 실제 레코드·개별 감사는 로컬에 둔다.
- Applicability: 이전 구현의 비공개 대조는 두 보고서의 감사 문구 6곳을 확인했다. 이 공개 기록에는 건수와 처리 상태만 남긴다.
- Counterevidence: 현재 파일이나 활성 브랜치의 정리는 이미 게시된 원격 객체의 제거를 증명하지 않는다.
- Validation: 세부 이력 식별자·경로·행·조회 명령은 무시된 로컬 사고 목록으로 옮기고 공개 내용과 원격 처리 상태를 분리해 점검한다.

### S4 — GitHub의 민감 데이터 제거 절차

- URL: https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository
- Retrieved: 2026-10-19
- Locator: About sensitive data exposure; Fully removing the data from GitHub
- Fragment: 이력을 교체해도 SHA로 직접 조회하는 캐시, PR 참조, 다른 clone이나 fork에 데이터가 남을 수 있다. GitHub의 캐시와 PR 참조 제거는 Support의 별도 처리다.
- Applicability: 활성 작업 브랜치의 조상에서 제외하는 수정과 GitHub 저장소에서 객체를 완전히 제거하는 절차를 구분한다.
- Counterevidence: Support의 처리 가능성이나 다른 clone의 제거를 이 문서나 force-push만으로 입증할 수 없다.
- Validation: 교체 후 활성 PR 커밋 목록과 옛 SHA의 직접 조회 결과를 따로 보고하고 원격 삭제 완료로 표현하지 않는다.

## Claims

- C1 (source; S1): Anthropic documents its Messages API as stateless and requires callers to send conversational history.
- C2 (source; S2): A repository research page records historical format retries that omitted the finding and produced research about another issue; it explicitly limits that observation to a small historical sample.
- C3 (interpretation; S1, S2): The present format-only retry is insufficient to reconstruct the original F1 or justify substituting an unrelated repository citation. Recovering the original finding and rejected answer is necessary to correct attribution without changing the research subject. The historical context-loss explanation is plausible but unconfirmed for this host.
- C4 (관측; S3): 이전 구현은 현재 파일에서 실제 감사 문구를 제외했지만 오염된 작업 조상을 유지했다. 이후 작업 조상을 교체했어도 원격 객체 제거를 입증하지 못했다. 세부 이력 식별자와 조회 안내는 공개 기록에서 제외한다.
- C5 (출처와 수정 범위; S4): 작업 브랜치의 오염된 조상을 교체하는 것과 GitHub의 캐시·PR 참조·다른 clone을 제거하는 것은 별도 작업이다. 이번 수정의 검증은 전자에 한정하며 후자의 완료를 주장하지 않는다.

## Core theory

Stateless message requests require the caller to supply conversational history. A retry that needs an earlier finding and answer must receive that context explicitly or through a verified session continuation. The cited API documentation establishes the stateless-request principle; it does not establish this host's current behavior. [C1, C3]

## Applicability

The principle applies to recovering the research context for this format retry. It does not identify any defect in the code originally reviewed as F1. The original finding, earlier fixes, and rejected answer must be recovered before substantive F1 research or another implementation change is justified. [C3]

## Hypothesis

There is insufficient evidence to propose a cause or code fix for the original F1. The missing original finding and rejected answer are consistent with the context-loss failure documented in the repository, but the current host implementation has not been inspected and that explanation remains unconfirmed. [C2, C3]

## Counterevidence

- The repository's retry investigation describes historical sessions and a different task; it does not prove the current host still has the same defect. [C2, C3]
- The public documentation describes Anthropic's Messages API, not this Codex session or wiki-agent's current session-continuation implementation. [C1, C3]
- The rejected answer may still exist in app-owned state even though it is absent from the context available here. Its absence here does not establish that it was lost permanently. [C3]

## Alternatives

- Infer F1 from a historical F1 research page. Rejected because finding identifiers recur across tasks, and the repository documents precisely this kind of misfiling. [C2, C3]
- Replace the invalid conversation source with a plausible repository path. Rejected unless that file actually supports the original claims; a valid path alone does not repair unsupported attribution. [C3]
- Recover the original finding and rejected answer from app-owned task state and retry with both included. This preserves the requested subject and allows a narrow correction of the invalid citation. [C3]

## Experiment

The host should reconstruct this retry with the original task identifier, F1 finding text, review chronology, and rejected answer included. Verify that the replacement for the invalid source is an existing repository file or a fetched web URL that supports the same claims. Then check that the corrected answer still addresses the original finding. No checks or implementation tests were executed in this read-only research turn. [C3]

### 수정 세션의 실험

이번 입력은 작업 `restore-aggregate-measurements`, F1 전문, round 1·2 경위와 과거 응답의 “Previous history was not rewritten” 문구를 제공했다. 거절된 연구 응답 전체나 현재 host의 재시도 구현은 제공되지 않았으므로, 그 부분의 맥락 소실 가설은 검증하지 않았다. 대신 F1 자체를 S3의 실제 저장소 파일과 Git 객체로 재현했다. 관련 없는 F1이나 존재하지 않는 conversation 출처로 대체하지 않았다.

1. 이전 구현에서 작업 조상과 활성 PR 목록을 대조했다. 파일 내용을 지우는 후속 커밋만으로는 과거 객체를 제거하지 못했다.
2. 내용을 출력하지 않는 비공개 로컬 원본 대조에서 두 보고서의 실제 감사 문구 6곳을 확인했다. 원문·오염 식별자·정확한 조회 위치는 공개하지 않는다.
3. 이전 정리의 경로별 diff를 대조해 지적 경로 외 11개 적용 지점을 집계했다. 아래 목록은 현재 문서의 정리 범위이며 과거 버전을 회수하는 안내가 아니다.
4. 후속 구현은 정리된 최종 파일로 작업 조상을 교체했다. 집계 보존과 활성 조상 정리는 확인했지만 원격 객체의 공개 접근 차단은 확인하지 못했다. 이 조치만으로 F1을 해결한 것으로 취급해서는 안 된다.

| 적용 경로 | 보존하는 내용 | 계속 제외하는 내용과 이유 |
| --- | --- | --- |
| `docs/benchmarks/seven_model/full_dev/report.md` | 모델·주제·분할별 집계와 감사 표본 수 | 실제 문항 ID·기관/질문 설명·개별 순위·토큰 점수·사례별 진단 |
| `docs/benchmarks/seven_model/historical/report.md` | 과거 집계와 일반적 감사 해석 | 동일한 실제 사례 감사 |
| `docs/kiwi_bm25_review.md` | 토크나이저 품질·시간·선택 근거 | 개별 문서의 청크 출처 |
| `docs/ocr_benchmark.md` | 유형별 품질·비용·시간·제외 수 | 개별 제외 이미지 번호 |
| `docs/quantity_filter_estimate.md` | 전체 비용 견적과 조건 | 실제 사용자 질문 문구 |
| `docs/quantity_filter_exclusions.md` | 제외 집계와 한계 | 개별 문서의 상충 값 |
| `docs/quantity_filter_validation.md` | 품질·비용·시간·검증 집계 | 기관·개별 값·실제 질문/답 문구·행별 진단 |
| `golden_pipeline/experiment_abc7.md` | 생성 방식별 집계와 결론 | 개별 검토 레코드 ID |
| `docs/research/review-feature-eval-golden-input-f4-1.md` | 당시 실험 결과와 독립 합성 설명 | 실제 문항 ID와 인용·반복 문구 |
| `docs/research/review-feature-eval-golden-input-f4-2.md` | 당시 실험 결과와 독립 합성 설명 | 실제 문구를 복사한 테스트·설명·실험 인용 |
| `docs/research/review-feature-golden-absent-premise-f2-2.md` | 당시 집계와 독립 합성 예제 | 실제 질문·근거 발췌 |
| `.wiki/corpus.json` | 정리된 문서의 색인 | 원문 제목·도입부에 포함된 실제 레코드의 색인 사본 |

## Result

관측 기록이며 독립 검증된 결론이 아닌 초안이다. 이전 구현은 두 보고서의 실제 감사 문구 6곳과 별도 적용 경로 11개를 확인하고 현재 내용과 작업 조상을 정리했다. Ruff·규칙 파일 일치·diff 공백 검사와 공개 집계·runtime·상대 링크 검사는 통과했지만, 공개 원격 접근 차단이나 Support 처리는 완료하지 않았다. 따라서 이전 처리 보고가 F1을 해결로 분류한 것은 잘못이었다. Round 3에서는 이 페이지의 조회 식별자·정확한 과거 위치·조회 명령을 제거하고 상세 사고 목록을 비공개 로컬에만 보관한다. 원격 공개 접근과 Support 처리 상태는 cycle 2 초안의 Result에서 별도로 보고하며, F1을 해결로 분류하지 않는다. 제품·테스트 코드를 바꾸지 않았고 서버 소유 전체 pytest 게이트는 pending이다. [C4, C5]

## Unresolved limits

초기 연구는 맥락이 부족했으며 이번 실험도 거절된 연구 응답 전체나 현재 host 구현을 복원하지 않았다. 따라서 초기 맥락 소실 가설은 미확인이다. 새 관측은 F1의 실제 파일·작업 이력에 한정한다. 이력 교체는 공유 base나 다른 브랜치·태그를 고치지 않으며 로컬 reflog·기존 clone·fork·GitHub 캐시와 옛 PR 참조의 제거를 입증하지 않는다. GitHub Support에 삭제를 요청하거나 삭제 완료를 확인한 상태도 아니다. 실제 레코드와 발췌를 이 페이지에 재인용하지 않았으며 새 벤치마크·유료 API 호출·제품 코드·테스트 추가는 없다. [C4, C5]
