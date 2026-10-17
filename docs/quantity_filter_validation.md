# Corrected-index paid validation

## Frontend acceptance

On 2026-10-17 the person selected `61개 표 확인 완료 (Recommended)` in response to the frontend acceptance choices. The question asked whether submitting the reported budget question in a new thread showed all 61 projects with budgets and overviews and 10 excluded documents. This explicit confirmation satisfies the final human acceptance requirement; it is user-reported browser evidence, not an agent-driven frontend submission.

At acceptance the usage CSV contained two additional user calls for `1억 미만인 사업제안서 목록과 그 사업들이 무엇인지에 대해 알려줘.`: rewrite $0.0001039 and answer $0.0020553. These are separate below-threshold exploration, not another four-question validation or a newly observed exact-main-question frontend pair. No agent call was added to reproduce the person's confirmation. Total observed task usage is 52 calls and $0.07041149; the earlier frontend reservation is an estimate, not an additional charge. The acceptance record and final ledger are in `artifacts/quantity_filter/final_luna_recheck/frontend_acceptance.json` and `whole_work_accounting_at_acceptance.json`.

## Final four-answer recheck

On 2026-10-17 the person approved `전체 4개 재검증`. Four LUNA answers ran against commit `f131deb`, reusing the saved rewrites and frozen corrected contexts in `artifacts/quantity_filter/post_recheck_fix/`. All four outputs passed the checks below. The subsequently received frontend acceptance is recorded above.

| Question | Expected projects / table rows | Exclusions | Answer cost | Call time |
| --- | ---: | ---: | ---: | ---: |
| Budget ≥100 million won and overviews | 61 / 61 | 10 | $0.0034617 | 21.452 s |
| Project duration ≥6 months | 30 / 30 | 45 | $0.0019689 | 11.712 s |
| Budget 100–500 million won | 44 / 44 | 10 | $0.0029521 | 17.414 s |
| Largest budget | 1 / 1 | 10 | $0.0001921 | 2.609 s |
| Total | 136 / 136 | | $0.0085748 | 53.187 s |

Every expected citation appears once in its corresponding table row. All 136 value cells preserve the selected original value, including currency glyphs, without added tax clauses or other text. Every row has an overview, and all four answers state the supplied exclusion count. The main answer correctly says all 61 projects meet the threshold. Its medical-center overview now describes the emergency medical situation-management system, and its Bonghwa overview summarizes the disaster-response background. The maximum answer explicitly attributes its result to comparison across the available values, with no contradictory comparison disclaimer.

All 136 overview rows were compared with their supplied excerpts and project names. They stay within those sources; some remain brief descriptions based on the project name because the compact context contains little further detail. The duration answer's railway ISP description of current-state and environment analysis is supported by its provided scope section. This is a manual check of these particular outputs, not a formal faithfulness score or evidence of general model equivalence. No paid judges ran.

Usage was 44,873 input tokens, zero cached input and 8,175 output tokens including 596 reasoning tokens. The CSV grew from 503 to 507 rows, exactly four answer calls. Actual cost was 59.8% below the approved $0.02132399 estimate. History was empty; output limit remained 8,192 with `low` reasoning. No new rewrite, retrieval/indexing API, judge, OCR, embedding API or evaluation test-split calls ran. Recorded USD uses actual response tokens and configured rates rather than invoice reconciliation.

Evidence is preserved in `artifacts/quantity_filter/final_luna_recheck/`: `manifest.json` records approval, commit, prompt, settings, input estimates and context hashes; `calls.jsonl`, the four answer files and `usage_summary.json` preserve the outputs and charges; `audit.json`, `overview_review_pairs.json` and `manual_review.json` record the checks. The run log is `artifacts/quantity_final_luna_recheck.log`.

Production code and tests did not change in this recheck or acceptance record. The final code's existing gate remains 1,183 passed with 12 warnings (`artifacts/quantity_post_recheck_gate.log`), and its test-cleanup audit remains in `artifacts/quantity_filter/post_recheck_fix/test_cleanup.json`; the unchanged suite was not repeated. The frontend and backend returned HTTP 200 without an answer call. The person subsequently confirmed the required result for `사업 예산 1억원 이상인 사업들과, 그 사업들의 개요를 알려줘.` through the acceptance choices above.

## Previous four-answer recheck and repair

## 4개 답변 재검증 결과와 후속 수정

2026-10-17 사용자가 `전체 4개 재검증 (Recommended)`를 승인하여, `b51bd7f`의 저장된 재작성과 최종 컨텍스트로 LUNA 답변만 4회 호출했다. 실제 비용은 $0.0088986으로 견적 $0.02130892보다 58.2% 낮았다. 재작성·심판·OCR·임베딩 API와 평가 test split은 실행하지 않았다. 이번 실행 전체는 인수 통과가 아니다.

| 질문 | 표 행 / 기대 사업 | 제외 수 | 답변 비용 | 호출 시간 | 판정 |
| --- | ---: | ---: | ---: | ---: | --- |
| 예산 1억원 이상과 개요 | 61 / 61 | 10 | $0.0037121 | 26.395초 | 실패: 개요 2개 누락과 잘못된 안내 |
| 사업기간 6개월 이상 | 30 / 30 | 45 | $0.0020247 | 14.090초 | 이번 표·값·개요·출처 검사 통과 |
| 예산 1억~5억원 | 44 / 44 | 10 | $0.0029464 | 17.482초 | 이번 표·값·개요·출처 검사 통과 |
| 최대 예산 | 1 / 1 | 10 | $0.0002154 | 3.156초 | 실패: 극값 검색 결과를 비교 불가로 설명 |
| 합계 | 136 / 136 | | $0.0088986 | 61.123초 | 2개 질문 통과, 2개 질문 실패 |

입력 44,736토큰, 캐시 입력 0토큰, 출력 8,850토큰이며 출력에는 추론 736토큰이 포함된다. `api_usage.csv`는 499행에서 503행으로 정확히 4개 답변 행만 증가했다. 시간은 유료 호출의 합계다. 기록 비용은 실제 응답 토큰과 설정 단가로 계산하며 청구서 대사는 아니다.

모든 사업의 출처 번호와 선택 금액 문자열, 제외 수가 표시되었고 이전 통화기호 치환은 재발하지 않았다. 다만 첫 답변의 값 열 14개는 첫 줄의 선택 값에 다른 줄의 부가세·한글 금액·범위 문구 등을 덧붙였다. 숫자가 바뀐 것은 아니지만 선택 문자열만 복사하라는 조건에는 실패했다. 행은 7·9·22·28·30·34·38·41·45·46·49·50·54·55번이다.

첫 답변은 도입부에 `예산이 1억원 미만인 사업도 포함되어 있습니다`라고 썼다. 실제 61개는 모두 조건을 만족하므로 잘못된 설명이다. 6번 국립중앙의료원과 13번 봉화군의 개요는 `문서에 없음`이었다. 6번에는 제목 표식 없이 시작하는 작성 서식이 선택되었고, 13번에는 재난 피해에 관한 추진배경이 있었지만 답변이 이를 요약하지 않았다. 최대 예산 답변의 사업·금액은 맞지만, 마지막에 전체 사업 중 최대인지 비교할 수 없다고 덧붙여 이미 수행한 극값 필터를 부정했다.

136개 표 행을 각각 제공된 본문과 대조했다. 위 두 누락 외의 개요는 제공된 본문 또는 사업명 범위의 요약이며, 일부는 사업명을 간단히 풀어쓴 수준이다. 기간과 범위 답변에서도 기능·목적·배경 설명을 본문과 확인했다. 이는 해당 출력에 대한 수동 검사이며 정식 faithfulness 점수나 일반적인 모델 품질 동등성의 근거는 아니다. 원본 유료 출력은 보존한다.

후속 수정은 기존 범위 안에서 유료 호출 없이 했다. `◎ 작성요령:`이 포함된 서식은 개요 후보에서 제외하고, 기존 회귀 테스트에 제목 없는 서식 사례를 합쳤다. 필터용 단일 프롬프트 규칙에는 전체 문서의 확인 가능한 값에 조건 적용과 극값 비교가 이미 끝났음을 명시했다. 값 열은 첫 줄 문자열만 복사하고, 개요는 본문의 목적·배경·내용을 요약하도록 명확히 했다. 추가 API 경로·설정·토큰 한도는 만들지 않았다.

네트워크를 막은 수정 후 재검색은 선택 값·사업 순서·제외 수를 모두 보존했다. 첫 질문의 6번만 서식에서 실제 사업명·기간·예산이 적힌 본문으로 바뀌었으며, 나머지 질문 컨텍스트는 같다. 국립중앙의료원은 이 본문이 제공하는 차세대 응급의료 상황관리시스템 구축 수준까지만 요약할 수 있다. 관련 개요 테스트 13개가 통과했고, 테스트 정리 감사 후 전체 게이트는 1,183개 통과·경고 12개로 끝났다(126.57초, `artifacts/quantity_post_recheck_gate.log`). 새 서식 사례는 기존 개요 회귀 테스트에 합쳤으며 삭제할 중복·폐기 경로·만료된 skip/xfail은 없었다. 수정된 프롬프트와 컨텍스트의 새 유료 검증 및 사용자 화면 확인은 아직 남아 있다.

실행 증거는 `artifacts/quantity_filter/post_paid_luna_recheck/`의 `manifest.json`, `calls.jsonl`, `usage_summary.json`, 답변 4개, `audit.json`, `overview_review_pairs.json`, `manual_review.json`에 있다. 수정 후 오프라인 컨텍스트·변경 비교·견적은 `artifacts/quantity_filter/post_recheck_fix/`에 있으며, [전체 견적서](quantity_filter_estimate.md)에 새 승인이 필요한 범위와 기존 화면 확인 예약분을 구분했다.

## 이전 8회 검증 기록

On 2026-10-17 the person approved four questions through GPT-6 LUNA rewriting and answering, plus a separate final frontend pair. The eight agent calls completed for $0.0090984 against an estimate of $0.02568245. They exposed defects, so this run is not an acceptance pass.

## Execution and usage

The run used commit `69bacea`, empty history, `low` reasoning, rewrite output limit 2,048 and answer output limit 8,192, including reasoning. Each rewritten query was searched against the active corrected index before generation. No paid judges, OCR, embedding API or evaluation test split ran.

The evidence writer initially could not serialize the read-only candidate mappings after saving the first rewrite response. It was corrected to copy those mappings for serialization. The saved response was reused: there were exactly eight paid usage rows, with no duplicate rewrite charge.

| Case | Rewrite cost | Answer cost | Paid call time | Table rows | Exclusions |
| --- | ---: | ---: | ---: | ---: | ---: |
| Budget ≥100 million won and overviews | $0.0000793 | $0.0035685 | 26.397 s | 61 | 10 |
| Duration ≥6 months | $0.0000631 | $0.0021402 | 14.599 s | 31 | 45 |
| Budget 100–500 million won | $0.0000809 | $0.0028921 | 19.215 s | 44 | 10 |
| Largest budget | $0.0000499 | $0.0002244 | 4.121 s | 1 | 9 |
| Total | $0.0002732 | $0.0088252 | 64.332 s | 137 | |

Usage: 47,219 input tokens, zero cached input, 8,753 output tokens including 860 reasoning tokens. Times sum paid calls only; local index loading, retrieval and the resumed writer are excluded. Actual usage was 64.6% below the approved estimate.

Recorded USD uses actual response tokens and the approved configured rates; it is not invoice reconciliation.

## Observations

All four answers contained a Markdown table, an overview column, citations for every supplied row, the supplied original numeric amounts and the supplied exclusion count. These structural observations do not establish that the selected field or overview is correct.

| Check | Finding |
| --- | --- |
| Project order and chosen numeric values after rewriting | Preserved for all four questions |
| Exclusions after rewriting | Preserved for the first three. Adding `규모` changed the maximum query's field phrase and reduced exclusions from 10 to 9, although its winning project and value stayed the same |
| Exact original text | One budget row changed the equivalent currency glyph `￦` to `₩`. Numeric value was unchanged; the literal-copy audit failed that row |
| Main-question overviews | Rows 3, 11, 20 and 23 said `문서에 없음`. Inspection found country background, a reference PDM and a blank proposal form among the excerpts; the HDIMS excerpt contained a work schedule that the answer did not summarize |
| Range overview faithfulness | The university operations row described the supplied blank form rather than the project. It was grounded in the excerpt but did not answer the requested project overview |
| Duration field correctness | Six rows used warranty or maintenance periods instead of the project period, including a 12-month warranty in a project whose labelled implementation period is 24 months within a ceiling. One further row used a historical research phase. The answer itself warned about these mismatches |

Manual inspection established these failures. The deterministic audit checks row count, citations, original value strings, overview headers and exclusion text; it is not a semantic faithfulness score. No paid judge score is claimed. Original answers remain unchanged as evidence.

## Local corrections after this run

The local repair removes the filler `규모` from quantity-field questions, prefers substantive introductions before unrelated value-source excerpts, rejects blank form candidates, and clarifies literal value copying in the existing filter prompt rule. Metadata now preserves subjects inside table cells instead of generic column headers and adds project context only to monetary labels. Explicit labelled quantity ceilings can be used for project periods as well as budgets; relative eligibility clauses remain excluded. Explicit reference blocks are not used as a project's own value.

These corrections add no API calls. They require fresh offline verification and an approved answer recheck on the resulting contexts. The four paid rewrite responses can be reused for that recheck, including the `규모` case, without purchasing new rewrites. Final frontend acceptance remains outstanding.

The final network-blocked replay passes with 61/30/44/1 projects and 10/45/10/10 exclusions. All four stored rewrites preserve the selected project order and exclusions. All 30 recovered amounts and all 88 previously chosen budget values are unchanged. The seven observed wrong period rows are absent or replaced, including the 24-month implementation period replacing the 12-month warranty. Introductions are recognized at section headings, with purpose/background preferred and mixed TOC prefixes trimmed; incidental mentions of project contents in requirement paragraphs do not qualify as introductions. The earlier 60 stored dev reruns retain every context ID sequence; subsequent excerpt-only changes do not enter their agency/document-prefixed route.

Final inputs and checks for that revision are in `artifacts/quantity_filter/post_paid_final/` and `artifacts/quantity_post_paid_final2.log`. The subsequent approved four-answer run and its findings are recorded above.

Final local checks: 92 quantity-filter tests passed; the full gate passed with 1,182 tests and 12 warnings in 407.29 seconds (`artifacts/quantity_validation_repair_gate5.log`); `ruff check .` passed; `CLAUDE.md` and `AGENTS.md` are byte-identical. The test cleanup audit retained the current regressions and found no obsolete cases, superseded duplicates, or expired skips/xfails. The frontend was restarted with the final metadata, and both its page and backend OpenAPI endpoint returned HTTP 200 without an answer call.

Full evidence is under `artifacts/quantity_filter/repaired_paid_validation/`: `manifest.json` records prompts, settings, commit, index hashes and the starting usage row; `calls.jsonl` and `usage_summary.json` record all eight calls; per-case retrieval, context and answer files preserve the inputs and outputs. `audit.json` contains structural checks, and `overview_review_pairs.json` pairs rows with their supplied excerpts.
