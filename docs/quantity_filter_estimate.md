# Quantity-filter verification: complete paid-call estimate

Date: 2026-10-17. Currency: USD. The approved work is 16 initial comparison calls, four LUNA answer rechecks and two frontend acceptance calls: 22 calls in total. Twenty calls have cost $0.0356981. The remaining frontend pair is estimated below $0.00675, giving a current projected total below $0.04245.

## Scope and assumptions

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
