# 수량 필터 검증 전체 견적서

Updated 2026-10-17, USD. The person approved the final four-answer recheck with `전체 4개 재검증`. All four outputs passed the recorded checks for $0.0085748 against $0.02132399 estimated. Observed task spending is now $0.06825229 across 50 calls, including the snapshot of 14 user frontend calls. The already approved frontend confirmation pair remains estimated at $0.00705974, giving a projected total of $0.07531203 across 52 calls. No further agent calls are proposed. [Validation evidence](quantity_filter_validation.md) records the output checks and remaining manual acceptance.

## Current whole-work accounting

| Work | Calls | Recorded cost or remaining estimate |
| --- | ---: | ---: |
| Original paired comparison and initial LUNA answer rechecks | 20 | Recorded $0.03569810 |
| User frontend calls, recorded snapshot | 14 | Recorded $0.00598239 |
| Corrected-index rewrite/answer validation | 8 | Recorded $0.00909840 |
| Previous four-answer recheck | 4 | Recorded $0.00889860 |
| Final approved four-answer recheck | 4 | Recorded $0.00857480 |
| Observed spending | 50 | Recorded $0.06825229 |
| Reserved user frontend confirmation | 2 | Estimated $0.00705974 |
| Recorded spending plus remaining estimate | 52 | $0.07531203 |

The final four calls used 44,873 input tokens, zero cached input and 8,175 output tokens including 596 reasoning tokens; paid call time summed to 53.187 seconds. Rates remain LUNA Standard input $0.10, cached input $0.01 and output $0.50 per million tokens, checked on 2026-10-17 against the official sources below. Recorded USD is calculated from actual response tokens and configured rates, not reconciled against an invoice. Any separate user calls after the recorded snapshot are outside this total.

The reserved frontend estimate assumes a new thread and empty history. It includes rewriting at 178 estimated input tokens and a 2,048-token output limit ($0.00104358), then answering at 17,456 estimated input tokens and an 8,192-token output limit ($0.00601616). Output limits include reasoning, effort is `low`, no cache discount is assumed, and input cost includes a 10% allowance. Input estimates use `o200k_base` plus 20 message-overhead tokens. This pair is already approved and has not been executed by the agent. The person submits the exact main question and confirms 61 complete table rows and 10 exclusions.

Local work adds no API charge. Paid judges, OCR, embedding APIs, the evaluation test split, further agent calls, extra questions, intentional additional retries and output-limit increases remain excluded. Taxes, exchange rates, fees, labor and electricity are excluded. These are estimates, not an API-enforced cap; any additional paid scope requires a new option-based approval. Final call evidence is in `artifacts/quantity_filter/final_luna_recheck/usage_summary.json`. Historical estimates below remain for comparison.

## Approved estimate: final four-answer recheck

The person selected the four-answer option below; it completed for $0.0085748. The two-answer alternative was not purchased. The following tables preserve the estimate as shown before approval; current actuals and the remaining frontend pair are above.

저장된 유료 재작성 4개를 그대로 재사용한다. 후보는 답변 4개 전체 재검증 또는 실패한 첫 질문·최대 예산 답변 2개 재검증이다. 이미 승인된 최종 사용자 화면의 재작성·답변 2회는 두 선택지 모두 별도로 남긴다. 최신 프롬프트는 네 질문에 공통으로 적용되므로 전체 4개 확인을 권장한다. 두 개만 실행하면 기간·범위 답변의 새 프롬프트 결과는 검증되지 않는다.

단가는 2026-10-17 확인한 LUNA Standard 입력 $0.10·캐시 입력 $0.01·출력 $0.50/100만 토큰이며 아래 공식 출처와 같다. 답변 한도 8,192토큰에는 추론을 포함하고 강도는 `low`다. 빈 이력, 캐시 할인 없음, 실제 프롬프트·수정 컨텍스트의 `o200k_base` 입력 수에 메시지 부대분 20토큰과 입력 비용 여유분 10%를 적용한다. 출력 비용은 최대 한도로 산정한다. 화면 확인에는 재작성 한도 2,048토큰을 추가한다.

| 추가 답변 후보 | 사업 | 예상 입력 | 최대 출력 | 입력 여유 포함 견적 |
| --- | ---: | ---: | ---: | ---: |
| 예산 1억원 이상과 개요 | 61 | 17,456 | 8,192 | $0.00601616 |
| 사업기간 6개월 이상 | 30 | 10,928 | 8,192 | $0.00529808 |
| 예산 1억~5억원 | 44 | 15,615 | 8,192 | $0.00581365 |
| 최대 예산 | 1 | 910 | 8,192 | $0.00419610 |
| 전체 4개 답변 | | 44,909 | 32,768 | $0.02132399 |
| 실패한 2개 답변만 | | 18,366 | 16,384 | $0.01021226 |

화면 예약분은 재작성 예상 입력 178토큰·최대 출력 2,048토큰의 $0.00104358과 첫 답변 $0.00601616을 합친 $0.00705974다. 이전 승인분 $0.00707173보다 낮으며, 중복 승인이나 에이전트의 화면 제출은 필요하지 않다. 사용자가 `새 스레드`에서 제출하는 최종 확인으로 남긴다.

| 전체 작업 정산 | 호출 | 기록 비용 또는 견적 |
| --- | ---: | ---: |
| 최초 비교와 초기 LUNA 재확인 | 20 | 실제 $0.03569810 |
| 사용자 화면 호출 스냅샷 | 14 | 실제 $0.00598239 |
| 수정 색인의 재작성·답변 검증 | 8 | 실제 $0.00909840 |
| 이번 4개 답변 재검증 | 4 | 실제 $0.00889860 |
| 현재 관측 누계 | 46 | 실제 $0.05967749 |
| 전체 4개 추가 + 예약 화면 확인 | 6 | 예상 $0.02838373 |
| 전체 4개 선택 시 총계 | 52 | 실제 + 예상 $0.08806122 |
| 실패 2개 추가 + 예약 화면 확인 | 4 | 예상 $0.01727200 |
| 실패 2개 선택 시 총계 | 50 | 실제 + 예상 $0.07694949 |

이번 실행은 입력 44,736·캐시 0·출력 8,850·추론 736토큰, 호출 합계 61.123초다. 실제 응답 토큰과 설정 단가에 따른 기록액이며 청구서 대사는 아니다. 사용자의 별도 추가 실행은 이 스냅샷에 포함되지 않는다. 견적은 API 강제 상한이 아니다.

The historical estimate inputs are in `artifacts/quantity_filter/post_recheck_fix/recheck_estimate.json`. The four-answer option was approved before execution; exclusions and remaining-work assumptions are recorded in the current accounting above.

## 직전 승인 견적과 실행 이력

### 직전 4개 답변 재검증 견적

The person approved the following four-answer quote with `전체 4개 재검증 (Recommended)`. It completed for $0.0088986; the newer quote above covers the subsequent repair. The four saved paid rewrites were reused without new rewriting. A network-blocked replay preserved project order and exclusions for all four stored rewrites. Contexts matched 61 budget projects, 30 duration projects, 44 range projects and one maximum; exclusions were 10, 45, 10 and 10. All 30 recovered amounts and all 88 previously chosen budget values remained unchanged. The seven observed warranty or historical-period rows were omitted or replaced by actual project-period rows. Selected introductions replaced the country background, reference PDM, generic requirement paragraph and blank form identified in the earlier paid run.

The rates and assumptions remain LUNA Standard input $0.10, cached input $0.01 and output $0.50 per million tokens, `low` reasoning, empty history, no cache discount, a 10% input-cost allowance and maximum output including reasoning. Answer output remains 8,192 tokens. Input estimates include the final prompt and 20 message-overhead tokens. The frontend pair additionally includes a 2,048-token rewrite output limit. Prices were checked on 2026-10-17 against the official sources linked below.

| Proposed answer | Projects | Estimated input | Maximum output | Estimate with input allowance |
| --- | ---: | ---: | ---: | ---: |
| Budget ≥100 million won | 61 | 17,565 | 8,192 | $0.00602815 |
| Duration ≥6 months | 30 | 10,846 | 8,192 | $0.00528906 |
| Budget 100–500 million won | 44 | 15,533 | 8,192 | $0.00580463 |
| Largest budget | 1 | 828 | 8,192 | $0.00418708 |
| Four new answers | | 44,772 | 32,768 | $0.02130892 |

| Whole-work accounting | Calls | Recorded cost or estimate |
| --- | ---: | ---: |
| Original comparison and earlier LUNA answer rechecks | 20 | Recorded $0.03569810 |
| User frontend calls before this validation | 14 | Recorded $0.00598239 |
| Approved corrected-index validation | 8 | Recorded $0.00909840 |
| Observed spending so far | 42 | Recorded $0.05077889 |
| Proposed four-answer recheck | 4 | Estimated $0.02130892 |
| Already reserved frontend confirmation, revised input estimate | 2 | Estimated $0.00707173 |
| Remaining proposed work including the reserved pair | 6 | Estimated $0.02838065 |
| Recorded spending plus all remaining estimates | 48 | $0.07915954 |

The revised frontend pair separates into $0.00104358 for rewriting (178 estimated input tokens) and $0.00602815 for answering (17,565 estimated input tokens). Its estimate is slightly below the previously approved $0.00708647. Use `새 스레드` for that confirmation.

A narrower main-question-only answer recheck would add one agent call at $0.00602815. Including the reserved frontend pair, remaining work would be $0.01309988 and the projected full total $0.06387877 across 45 calls; the other three repaired contexts would have no fresh paid answer evidence. This alternative changes recheck coverage and is not assumed approved.

Exactly four answer calls ran under this approved proposal. Local repairs, index rebuilding, unit tests and dev reruns add no API charge. Paid judges, OCR, embedding APIs, the evaluation test split, extra questions, intentional additional runs, output-limit increases, taxes, exchange rates, fees, labor and electricity remain excluded. These amounts are estimates, not an API-enforced cap. Recorded USD uses actual response tokens and configured rates rather than invoice reconciliation. The historical recheck inputs and calculations are saved in `artifacts/quantity_filter/post_paid_final/recheck_estimate.json`.

## 수정 후 검증과 전체 추가 견적

기존 제외 40개에서 항목 매칭 20개, 단위 추출 7개, 실제 예산 상한 3개를 복구했다. 복구한 금액 30개는 모두 원문 감사 값과 같고, 그중 19개는 1억원 이상, 11개는 미만이다. 금액 확인 불가 9개와 추정가격 정책 제외 1개는 유지한다. [40개 문서별 판정](quantity_filter_exclusions.md)에 전체 내역을 기록했다. 기존 일치 42개 사업의 금액은 바뀌지 않았다.

1원 이하 금액은 미표기로 처리하고 정상적인 1개월·1개는 유지한다. 표 구분자는 단위로 읽지 않는다. 단위가 없는 범위·최대·최소는 문서마다 가장 잘 맞는 항목 하나씩으로 단위를 집계하므로 반복 서식이 결과를 뒤집지 않는다. 저장된 dev 60건은 API 없이 다시 검색했으며 모든 `context_chunk_ids` 순서가 같다.

새 검증은 원본 질문에서 실제 재작성 → 검색 → 답변을 실행한다. 조건 보존, 사업 누락, 표·원문 값·개요 근거·출처·제외 수, 지연 시간과 사용량을 기록한다. 이후 사용자가 새 스레드에서 첫 질문을 제출하고 표와 수정한 제외 수를 확인해야 완료할 수 있다.

단가는 2026-10-17 확인한 GPT-6 LUNA Standard 입력 $0.10·캐시 입력 $0.01·출력 $0.50/100만 토큰이다. 재작성 2,048·답변 8,192토큰 한도에 추론을 포함하며 강도는 `low`다. 빈 이력으로 실제 프롬프트·질문·수정 컨텍스트를 `o200k_base`로 계산하고 메시지 부대분 20토큰, 입력 비용 여유분 10%를 더했다. 출력은 최대 한도로, 캐시 할인은 없이 계산했다. 단가 출처와 계산식은 아래 역사 기록에도 남겼다.

| 수정 후 질문 | 일치 | 제외 | 재작성 입력 | 답변 입력 | 2회 예상액 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 사업 예산 1억원 이상·개요 | 61 | 10 | 178 | 17,699 | $0.00708647 |
| 사업기간 6개월 이상 | 31 | 45 | 166 | 11,556 | $0.00640942 |
| 예산 1억~5억원 | 44 | 10 | 169 | 16,255 | $0.00692664 |
| 최대 예산 | 1 | 10 | 164 | 1,108 | $0.00525992 |
| 네 질문 검증 소계 | | | | | $0.02568245 |
| 사용자 최종 화면 확인 2회 | 61 | 10 | 178 | 17,699 | $0.00708647 |
| 추가 전체 10회 | | | | | $0.03276892 |

첫 질문의 재작성 예상은 $0.00104358, 답변은 $0.00604289로 입력 여유분을 포함한다. 재작성 결과에 따라 컨텍스트 길이도 달라질 수 있어 실제 비용을 함께 비교한다. 오프라인 결과와 입력 산정은 `artifacts/quantity_filter/repaired_final/`, 검증 로그는 `artifacts/quantity_repair_final_verification3.log`에 있다.

| 전체 작업 | 호출 수 | 실제 비용 또는 예상액 |
| --- | ---: | ---: |
| 최초 네 질문·두 모델 비교 | 16 | 실제 $0.0298906 |
| 승인된 LUNA 답변 재확인 | 4 | 실제 $0.0058075 |
| 사용자가 화면에서 실행한 질문 | 14 | 실제 $0.00598239 |
| 기존 관측 합계 | 34 | 실제 $0.04168049 |
| 이번 수정 후 검증 | 8 | 예상 $0.02568245 |
| 최종 화면 확인 | 2 | 예상 $0.00708647 |
| 기존 실제 + 남은 전체 예상 | 44 | $0.07444941 |

화면 호출 14회는 에이전트 검증과 구분했다. `frontend_before.json`의 기준 477행 이후 `api_usage.csv` 집계이며 입력 44,101·캐시 입력 14,519·출력 5,758·추론 1,138토큰이다. 이후 사용자가 별도로 실행하는 호출은 이 스냅샷에 포함되지 않는다. 새 검증 직전 기준 행을 저장해 검증 비용을 구분한다.

로컬 추출·임베딩·색인·검색·테스트·저장 dev 재검색의 API 비용은 $0다. 유료 심판·OCR·임베딩 API·평가 test split·추가 질문·의도적인 추가 재실행·토큰 한도 증가는 제외한다. 세금·환율·카드 수수료·인건비·전기료도 제외한다. 위 금액은 API가 강제하는 지출 상한이 아니며 추가 유료 범위나 예산 증가는 선택지로 승인받는다.

예산 질문의 전체 98개는 일치 61개, 확인 값이 조건 미달인 27개, 값 미표기·매칭 불가 또는 정책 제외 10개다. 제외 수에 조건 미달 27개를 넣지 않는다. 아래의 42개·제외 40개 결과와 견적은 수정 전 역사 기록이다. 이번 컨텍스트가 바뀌었으므로 예전 유료 결과를 새 61개 답변의 검증으로 간주하지 않는다. LUNA 선택은 네 질문에 한정된 비용·조건 보존 비교이며 일반적인 성능 동등성을 뜻하지 않는다. 심판·OCR 설정은 유지한다.

## 수정 전 기록: Scope and assumptions

For each of four questions, the initial comparison made one rewrite and one answer call with each model. Both models received identical frozen contexts and empty history. Rewrites were also replayed through retrieval locally. After approval, four LUNA answers were rechecked with a clarified table rule and the same frozen contexts; stored rewrites were reused without paid rewriting.

The final two calls are reserved for the person to submit the reported question in the frontend and confirm its table. No frontend call has been made by this verification script.

| Item | Quantity or assumption |
| --- | --- |
| Questions | Budget at least 100 million won; duration at least six months; budget 100–500 million won; largest budget |
| Initial comparison | 4 questions × 2 models × rewrite and answer = 16 calls |
| Approved recheck | 4 LUNA answer calls, no new rewrite calls |
| Frontend acceptance | 1 rewrite + 1 answer with the selected model |
| Rewrite output limit | 2,048 tokens per call, including reasoning |
| Answer output limit | 8,192 tokens per call, including reasoning |
| Reasoning effort | `low` for both models |
| Input estimate | `o200k_base` tokens for prompts, context and question, plus 20 message-overhead tokens |
| Input allowance | 10% added to input cost; output is already estimated at its maximum limit |
| Cache assumption | No cache discount; actual cache hits can lower cost |
| History | Empty for comparison and acceptance estimates; use a new frontend conversation |

Local quantity extraction, embeddings, indexing, retrieval, unit tests and stored dev retrieval reruns add $0 in API charges. This quote excludes paid judges, OCR, embedding APIs, the test split, additional questions, intentional extra retries and token-limit increases. Taxes, exchange rates, card fees, labor and electricity are excluded. Any further paid scope or budget increase requires approval through options.

## Rates and calculation

Rates below are USD per million tokens for Standard calls with input below 272,000 tokens. Cached input replaces regular input; it is not charged twice. Reasoning tokens are included in output tokens.

| Model | Input | Cached input | Output |
| --- | ---: | ---: | ---: |
| gpt-5-mini | $0.25 | $0.025 | $2.00 |
| GPT-6 LUNA | $0.10 | $0.01 | $0.50 |

Sources checked on 2026-10-17: [gpt-5-mini model documentation](https://developers.openai.com/api/docs/models/gpt-5-mini), [GPT-6 LUNA model documentation](https://developers.openai.com/api/docs/models/gpt-6-luna) and [API pricing](https://developers.openai.com/api/docs/pricing). Future price changes are excluded.

Cost = `(regular input × input rate + cached input × cached rate + output × output rate) / 1,000,000`.

## Original per-question estimate

Each price combines one rewrite and one answer, using the full combined output limit of 10,240 tokens. The input allowance is added once in the total, rather than in each row.

| Question | Matching documents | No matching value | Combined estimated input | gpt-5-mini | LUNA |
| --- | ---: | ---: | ---: | ---: | ---: |
| Budget ≥100 million won, with overviews | 42 | 40 | 14,638 | $0.0241395 | $0.0065838 |
| Duration ≥6 months | 20 | 62 | 6,153 | $0.02201825 | $0.0057353 |
| Budget 100–500 million won | 29 | 40 | 7,150 | $0.0222675 | $0.0058350 |
| Largest budget | 1 | 40 | 1,193 | $0.02077825 | $0.0052393 |
| Four-question subtotal | | | 29,134 per model | $0.0892035 | $0.0233934 |

The exclusion count means documents without a matching labelled value, rather than documents whose known value fails the condition.

For the reported question, the estimate separates as follows.

| Stage | Estimated input | Maximum output | gpt-5-mini | LUNA |
| --- | ---: | ---: | ---: | ---: |
| Rewrite | 178 | 2,048 | $0.0041405 | $0.0010418 |
| Answer | 14,460 | 8,192 | $0.0199990 | $0.0055420 |

## Whole-work estimate and actual spending

| Item | Estimate at full output limits | Actual |
| --- | ---: | ---: |
| Initial comparison, 16 calls | $0.1125969 before input allowance | $0.0298906 |
| Approved LUNA recheck, 4 answers | $0.01954551 including input allowance | $0.0058075 |
| Remaining LUNA frontend pair | Below $0.00675 including input allowance | Awaiting user submission |
| Actual spent, 20 calls | | $0.0356981 |
| Current projected total after frontend acceptance | Below $0.04245 | Pending |

The original 18-call estimate including the frontend pair and input allowance was $0.12034677 if LUNA was selected, or $0.13812204 if gpt-5-mini was retained. The approved four-call recheck adds at most $0.020. Including that recheck and the slightly longer final prompt, the prospective full-output estimate for the selected LUNA plan is approximately $0.140; the current projection is lower because completed calls used much less output than their limits.

These are estimates for the stated calls, not an API-enforced spending cap. No intentional extra calls or token-limit increases are included.

## Actual usage and initial paired results

Usage is recorded in `artifacts/api_usage.csv`, including stage, model, input, cached input, output, reasoning tokens and USD. Individual comparison calls and outputs are in `artifacts/quantity_filter/model_comparison/`. The initial paired comparison used code commit `d96a372`.

| Model | Calls | Input | Cached input | Output including reasoning | Reasoning | Summed call time | Actual cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| gpt-5-mini | 8 | 29,066 | 0 | 8,391 | 2,624 | 68.01 s | $0.0240485 |
| GPT-6 LUNA | 8 | 29,066 | 0 | 5,871 | 874 | 43.63 s | $0.0058421 |
| Initial total | 16 | 58,132 | 0 | 14,262 | 3,498 | 111.64 s | $0.0298906 |
| LUNA answer recheck | 4 | 28,705 | 0 | 5,874 | 365 | 39.66 s | $0.0058075 |
| All completed calls | 20 | 86,837 | 0 | 20,136 | 3,863 | 151.30 s | $0.0356981 |

In the initial paired sample, LUNA cost 75.7% less and summed call time was 35.8% shorter. Output length differed, and every call ran only once; this does not establish equal quality or general latency superiority beyond these four questions.

| Question | Initial gpt-5-mini output | Initial LUNA output |
| --- | --- | --- |
| Budget ≥100 million won | Listed 37 of 42 projects without a table; stated 40 exclusions | All 42 projects in a table, with values, overviews, citations and 40 exclusions |
| Duration ≥6 months | All 20 in a list; no overview column | All 20 in a table; values, citations and 62 exclusions; no overview column |
| Budget 100–500 million won | All 29 in a table; no overview column | All 29 in a table; no overview column or individual citations |
| Largest budget | Correct project and value in prose; no exclusion count | Correct project, value, overview, citation and exclusions in a table |

A network-blocked replay of stored rewrites found that, after the local parser correction for `1억 원`, all four LUNA rewrites retained the original project order and exclusion counts. gpt-5-mini added `공공기관 RFP(제안요청서)` to the range question, changing field similarity and returning zero instead of 29 projects. Its largest-budget rewrite retained the winning project but changed exclusions from 40 to 49. Fixed-context generation comparisons do not include these retrieval differences.

## Approved recheck and model selection

The person approved the recommended four LUNA answer rechecks, estimated below $0.020. No second set of gpt-5-mini answers was purchased. Recheck evidence is in `artifacts/quantity_filter/luna_recheck/`, including a manifest with the prompt, settings, input estimates and context hashes.

| Case | Expected projects | Table rows | Original values and citations | Overview column | Excluded count |
| --- | ---: | ---: | --- | --- | ---: |
| Budget ≥100 million won | 42 | 42 | All present | Present | 40 |
| Duration ≥6 months | 20 | 20 | All present | Present | 62 |
| Budget 100–500 million won | 29 | 29 | All present | Present | 40 |
| Largest budget | 1 | 1 | All present | Present | 40 |

The reported question's 42 overview rows were checked against their provided excerpts; some are brief descriptions based on the project name. Longer claims about data use, system functions and project purpose are supported by the cited excerpts. Other cases exposed a retrieval limitation: generic condition tails could rank contract forms, so some frozen-context summaries described those forms or said information was absent. The local fallback was corrected after the paid recheck. The frozen outputs remain unchanged as evidence. Network-blocked verification of final contexts changed 19 duration excerpts and all 29 range excerpts while preserving their project order and values; the reported-question and largest-budget contexts are byte-identical to the paid recheck inputs. All 60 stored dev context ID sequences remain unchanged. The changed duration and range contexts have no additional paid generation evidence.

Select `gpt-6-luna` for rewriting and answering because it preserved the four stored query conditions and final required output structure at lower measured cost. Judge and OCR settings are unchanged. This is a narrow four-question decision, not a claim of equal performance on all questions. The user's separate frontend confirmation remains required.
