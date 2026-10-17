# Corrected-index paid validation

## Review round 5: separate numbered header columns

At parent `f82129f`, the reported input `구분 | 2024년 | 예산(천원)\n--- | --- | ---\nA | 완료 | 100` emitted only the year row and omitted 100,000 won. Eight regression variants failed before production edits (`artifacts/quantity_review5_red.log`): year and ordinal headers, reordered budget columns, multiple numbered columns, boundary pipes and CRLF. This is a reproduced omission, not an inference from the previous round.

Schema detection now examines the following line. A same-width Markdown delimiter row and at least one unit declaration positively identify the header as a whole, before cell-level quantity guards run. The existing header flag suppresses header quantities and installs all sibling column declarations together. Unmarked rows retain the previous checks, avoiding a unit-list heuristic to distinguish years, ordinals and monetary data. A further regression covers simultaneous budget and period declarations, explicit-unit precedence and the existing table boundary.

The applicability count is separate from the reported example. One shared schema decision is called by one chunk-line loop; header suppression and implicit-cell extraction are the two existing downstream consumers. No other schema parser implements this rule. Rebuilding all 13,627 table-bearing chunks among 18,989 chunks, including 6,968 declaration-bearing chunks, changed zero rows, chunks or documents from the round-4 baseline. All 29,358 quantities and their numeric/declaration source spans were retained (`artifacts/quantity_review5_scope.log`, `artifacts/quantity_filter/review5/scope.json`). The supplied mixed-column fixture demonstrates a supported format that is absent from this saved corpus's changed rows.

After the production change, the isolated index rebuilt all 11,934 phrase embeddings locally. The four saved searches retained 61/30/44/1 projects, 10/45/10/10 exclusions and every chosen value; their whole-project modifier pairs retained identical candidates and contexts. Both upper-bound aliases retained their round-4 results, ten non-project questions used hybrid retrieval, and all 60 stored dev context-ID sequences were unchanged at weights .6/.5. Socket connections were blocked and the usage CSV remained byte-identical (`artifacts/quantity_review5_offline.log`). The active index was not replaced; earlier paid/browser acceptance remains historical.

The final test cleanup audited the quantity tests and indexing, retrieval, saved-record, IR, rewrite, server, notebook, usage and smoke consumers. All current regressions remain; no obsolete tests, skips or xfails were removed. The ten new cases passed, followed by the full repository gate: 1,321 passed, 12 warnings in 204.94 seconds (`artifacts/quantity_review5_cleanup_gate.log`). Ruff passed. The cleanup record is `artifacts/quantity_filter/review5/test_cleanup.json`.

## 검토 4차: 번호가 있는 선언 단위 머리글과 포함 상한

수정 전 `artifacts/reproduce_quantity_review4.py`에서 두 결함을 재현했습니다. `구분 | 1차 예산(천원)\n--- | ---\nA | 100`은 `1차`만 내보내고 100,000원을 누락했습니다. `사업기간 6개월 이내인 사업`과 `사업기간 6개월까지인 사업`은 조건 파싱 결과가 None이어서 일반 검색으로 진행했습니다. 수동으로 만든 두 상한 조건도 7개월을 허용했습니다. 기록은 `artifacts/quantity_review4_before.log`와 `artifacts/quantity_review4_before_lightweight.log`에 있습니다.

F2는 숫자가 발견되었다는 이유만으로 머리글을 거절하지 않고, 각 셀의 수식어 뒤 항목명과 끝의 단위 선언을 확인합니다. 확인된 머리글은 열 단위를 설치하고 차수·연도 수량을 내보내지 않습니다. 숫자 데이터 셀, 선언 뒤 명시 값, 본문 서술과 괄호 약어는 기존 데이터로 유지합니다. 실제 코퍼스 비교에서 발견한 BIS 사업명, TLS 서버 수량, DMZ 조항도 회귀 테스트로 남겼습니다. 별도로 확인한 적용 지점은 스키마 판정과 행 출력의 두 곳입니다.

F6는 `이내`와 단독 `까지`를 포함 상한으로 처리합니다. 별도 적용 지점 네 곳은 비교 표현 앞 공백 정규화, 조건 생성, 값의 포함 여부, 결과 오름차순 정렬입니다. 기존 메타데이터의 여섯 비교 표현과 상한 표시는 이미 두 표현을 지원하여 유지했습니다. `부터…까지` 범위, 기관·문서 접두어, 비사업 대상, 일치 0개인 필터도 기존 경로를 유지합니다.

별도 코퍼스 집계는 18,989개 청크 중 표가 있는 13,627개를 다시 읽고 단위 선언이 있는 6,968개를 확인했습니다. 이전 29,359개 수량 중 한 문서·한 청크의 무항목 행 하나만 제거되어 29,358개가 남았습니다. 제거된 `2.2 농업정보`는 `2.2 농업정보 활용 농가비율(%) | 연간실적`이라는 머리글에서 읽은 번호입니다. 추가 수량과 항목명 변경은 0개이며 모든 숫자·단위 선언 범위가 원문과 일치합니다. 이는 제보 사례의 합성 회귀 테스트와 별개로 센 실제 코퍼스 영향입니다. 기록은 `artifacts/quantity_filter/review4_checked/scope.json`, `scope_summary.json`과 `artifacts/quantity_review4_published_scope.log`입니다.

코드 확정 후 테스트 정리에서 변경한 수량 필터 테스트와 이를 사용하는 색인·검색·저장 레코드·IR·재작성·서버·노트북·사용량·스모크 테스트를 점검했습니다. 현재 동작을 보호하는 테스트는 유지하고 삭제한 테스트나 만료된 skip/xfail은 없습니다. 전체 저장소 게이트 `.venv\Scripts\python -m pytest -q tests`는 1,311개 통과, 경고 12개, 134.80초입니다(`artifacts/quantity_review4_final_repository_gate.log`). 수량 필터 파일 단독 검사는 215개 통과했습니다. 이전 중간 검사 실패는 본문 오인식 방지를 보강하기 전 결과이므로 최종 통과로 제시하지 않습니다.

격리된 색인에서 29,358개 수량의 11,934개 항목명을 로컬에서 다시 임베딩했습니다. 기존 네 질문은 61/30/44/1개 사업과 제외 10/45/10/10개를 유지했고, 선택 금액·기간과 사업 추가·제거는 모두 변경 0개입니다. `전체` 수식어 쌍도 같은 후보·문맥을 반환했습니다. `6개월 이내`와 `6개월까지`는 각각 37개 사업·제외 45개, `1억원 이내`와 `1억원까지`는 각각 30개 사업·제외 10개이며, 모두 `이하`와 같은 값·정렬·문맥입니다. 비사업 질문 10개는 일반 검색을 유지했습니다. 저장된 dev 질문을 가중치 .6/.5로 각각 30개씩 재실행하여 60개 문맥 청크 ID가 모두 같았습니다. 소켓 연결을 차단하고 사용량 CSV의 바이트 불변을 확인했습니다(`artifacts/quantity_review4_checked_offline.log`). 기존 유료 답변과 화면 확인은 이 수정 전의 기록이며, 이번 수정은 API 호출이나 활성 색인 전환을 추가하지 않습니다.

## Review round 3: table schema lifetime and whole-project scope

Both draft research pages were read before the experiments: `docs/research/review-fix-quantity-filter-questions-f2-2.md` and `docs/research/review-fix-quantity-filter-questions-f4-1.md`. At parent `51629a7`, `artifacts/reproduce_quantity_review3.py` traced headers, column declarations, default units and quantities after every line. Without the missing row, `B 사업 | 100` inherited thousand-won units and yielded 100,000 won. Inserting `A 사업 | -` replaced headers and declarations with the data row and `[None, None]`, so the next value disappeared. Kiwi 0.24.0 returned `인/NNG 전체/NNG 사업/NNG`; the condition parsed correctly, the router returned no agency, but project recognition returned None and selected hybrid retrieval. The log is `artifacts/quantity_review3_before.log`. New regressions initially failed in 35 cases.

Schema updates now preserve labels and declarations together. A quantity-free data row does not replace an established schema; initialization and positively declared header changes remain supported, and the existing non-pipe/chunk boundaries reset it. Numeric key/value rows and purely numeric cells are data rather than headers. Missing-value spelling is not used as a classifier. A first implementation incorrectly classified a numeric key/value row as a header; a later noun-only header guard rejected the real label `비고`, which Kiwi parses with verb endings. Both were observed and corrected before the final measurements. Their intermediate census runs are superseded by the checked run.

The F2 transition tests cover dash, empty and textual values before and after valid rows in column-unit, default-unit and explicit-unit tables (18 cases). They compare later value/unit/phrase/declaration identity with the baseline, verify the shifted numeric offsets and exact source slices, and check a restored document at a controlled 100,000-won threshold. Additional regressions cover declaration changes, explicit-unit precedence, following-table reset, numeric key/value rows and the real six-column EA header. Existing pipe/LF/CRLF/EOF fixtures remain intact. Generic adjacent headers without a declaration or supported boundary remain ambiguous; no general merged-cell or semantic table parser was added.

`전체` is a bounded, nonrestrictive scope modifier shared by project-target recognition and default excerpt selection. The target check still stops at the first other noun, so a later project mention cannot turn a requirement/vendor question into whole-project filtering. Sixteen paired cases compare threshold/range/extreme/zero-match conditions through original and explicit rewritten queries and both public search entry points. They preserve values, candidate order, filter summary, formatted context and default excerpt queries. The existing non-project fixture gains the two whole-scope non-project targets and a requirement target with a later project mention; agency/document-prefix controls also include the modifier.

The separate applicability audit follows one paired schema update and its table/chunk resets across three inheritance modes. Routing has one shared dispatch, four direct callers and two downstream record consumers (generation and retrieval-only rerun); both noun-interpretation sites now share the modifier set. Earlier paid/browser acceptance remains historical, and these repairs add no paid calls or active-index switch.

The checked corpus census (`artifacts/quantity_filter/review3_checked/scope.json`) covers 18,989 chunks, including 13,627 table-bearing chunks and 6,968 with declaration-like text. Compared with the round-2 metadata, 185 chunks in 79 documents changed. Separately counted: 34 added inherited rows, 14 removed inherited rows and 372 existing subject phrases changed. The total is 29,359 rows, up from 29,339. Added/removed rows are noncurrency; 21 existing currency labels changed. Added units include scoring and person-month/day tables, but the POS-based reader also retains heuristic units such as `동작` or `기준`. These counts do not certify every row's semantic correctness. Exact numeric and declaration spans were checked throughout. The full local row/label diff is `scope_summary.json`; the summary log is `artifacts/quantity_review3_scope_checked_summary.log`.

After the final production change and test-cleanup audit, the ten affected files passed 740 tests with 12 warnings in 54.12 seconds (`artifacts/quantity_review3_checked_cleanup_gate.log`). Current regressions remain; scoped and non-project fixtures were extended, the existing boundary matrix was reused, and no obsolete/duplicate tests or expired skips/xfails were found. The cleanup record is `artifacts/quantity_filter/review3_checked/test_cleanup.json`. The full suite is not repeated per review round. The final offline search run uses newly rebuilt phrase embeddings; its observations are recorded separately from the intermediate, superseded runs.

`artifacts/verify_quantity_review3_checked.py` re-embedded all 11,934 distinct phrases after the last production change. Four actual questions retain 61/30/44/1 projects, 10/45/10/10 exclusions, every chosen value and the source/token-budget checks. Their whole-project modifier variants preserve values, candidates and formatted context through rewritten queries and `search`. Eight non-project questions use hybrid retrieval, returning 14/17/15/23/15/18/14/17 hits respectively. Both stored dev reruns keep all 60 context-ID sequences (weights .6/.5). Socket connections are blocked and the usage CSV remains byte-identical. Logs and outputs are in `artifacts/quantity_review3_offline_checked.log` and `artifacts/quantity_filter/review3_checked/`; the active index and existing server were not changed. Both research pages record the observations and the fix commit's unique subject and parent, and remain drafts.

## Review round 2: table boundaries, route intent and index rollback

The F2 draft at `docs/research/review-fix-quantity-filter-questions-f2-1.md` was read before the experiment. `artifacts/reproduce_quantity_review2.py` reproduced all three findings before production edits at `684c463`: a trailing-pipe total produced raw cells `[' 계 ', ' 200,000 ', '\n']`, its amount targeted column 1 instead of budget column 2, and only 140-million/60-million components survived. The unscoped response-time requirement used `_filter` without calling hybrid ranking. Failure on the second embedding call replaced FAISS/BM25 while preserving old quantity rows. The log is `artifacts/quantity_review2_before.log`. New regressions then produced 22 failures and 2 passes before the fixes.

Four quantity-cell parsing sites now share one boundary/offset reader: inherited numeric cells, explicit quantity reading, field assignment and header declarations. It removes exterior table syntax before counting and retains interior empty cells. The existing shortened-total regression now checks ten combinations of boundary pipes, LF/CRLF, EOF, following text, exterior whitespace and a missing interior cell; the delimiter-free EOF case remains. A separate mixed-unit test verifies an empty first column. Each numeric and unit-declaration span slices its original text. Distinct controlled similarities place the total above both components; a 150-million threshold then selects `200,000 (천원)` in every formatting variant. The selector's similarity policy is unchanged.

Project filtering now requires a project target in the parsed condition's remainder, ignoring connecting `인` and `규모`. A business word only in the field prefix is insufficient. Ten route regressions exercise five non-project comparisons as original and rewritten questions: requirement thresholds, ranges, extremes, a project-prefixed requirement and vendor qualification. Both public search entry points use the same decision. Other direct consumers are retrieval-record export, the notebook's local check and its shared inspection helper; generation and retrieval-only reruns consume the exported records. Agency/document-prefix behavior remains covered.

The publication repair stages five coupled artifacts: `faiss.index`, `bm25_tokens.json`, `quantities.jsonl`, `quantity_phrases.json` and `quantity_vectors.npy`. The one notebook build entry point now publishes their completed directory after all work, including summary calculation. Four injected failures cover second-call quantity embedding, quantity-vector writing, summary calculation and publication rename. Every previous artifact remains byte-identical and `HybridIndex` loads and searches the old generation. A failed first build leaves no published directory; a successful rebuild loads both new chunks. This is an exception rollback boundary, not crash recovery or concurrent-reader coordination, and does not roll back preprocessing's separate files.

The related corpus census is separate from the synthetic reproductions: 18,989 chunks were examined, including 13,627 table-bearing chunks and 6,968 with unit declarations. Rebuilding every table-bearing chunk changed zero quantity rows or documents; all 29,339 rows and their numeric/declaration source spans were retained (`artifacts/quantity_filter/review2/scope.json`). The raw boundary-pipe omission is a demonstrated regression fixture, not a claimed change to this corpus's selected budgets.

`artifacts/verify_quantity_review2.py` re-embedded all 11,949 phrases after the final production change, with socket connections blocked and the usage CSV checked byte-for-byte. Four actual project searches retained 61/30/44/1 projects, 10/45/10/10 exclusions, all chosen values and complete source markers. Five actual non-project searches used hybrid retrieval and returned 14/17/15/23/15 hits. Both frozen dev reruns preserved every context-ID sequence (60 questions, weights .6/.5). The log is `artifacts/quantity_review2_offline.log`; the active index and server were not switched to the isolated artifacts.

After test cleanup, the ten affected test files passed 694 tests with 12 warnings in 131.46 seconds (`artifacts/quantity_review2_cleanup_gate.log`). The original separator-free EOF variant was then retained explicitly in the expanded table fixture and that changed test file was rerun separately: 130 passed in 12.06 seconds (`artifacts/quantity_review2_final_test_cleanup.log`). The existing regression was expanded rather than duplicated; all valid current checks remain, with no obsolete tests or skips/xfails removed. No new API calls, paid generation, judges or evaluation test-split runs were made. The F2 research page stays a draft and is committed with the fix.

## Review round 1: provenance and quantity metadata repairs

All three findings were reproduced before production edits at `588577d`. A page-1 budget combined with a page-2 overview produced a hit and candidate attributed to page 2. Both a column declaration `사업예산(천원)` and a preceding `(단위: 천원)` lost numeric-only cells. In `과업비/과업기간: 100,000천원 / 착수일로부터 5개월`, both values were labelled `과업비`. The new regressions initially failed in nine cases (`artifacts/quantity_review1_red.log`).

The hit, candidate and stored context identity now use the value's source chunk. A different overview keeps an explicit filename, page or section, and chunk ID in the body. Hit/candidate schemas and one hit per project are preserved. Declared units now scale numeric cells while retaining the original cell and declaration spans; context shows the inherited unit. Column overrides, explicit cell units and table/chunk boundaries are covered. Shortened total rows retain their column unit, and component labels prevent a partial cost from replacing the project's total. Parallel labels and values are paired by position, including reversed fields, unspaced separators, numbered headings and compound units. Later clauses and numbered glossaries keep their own field scope.

The related-site census is separate from the three reproductions:

| Finding | Other applicable places and observations |
| --- | --- |
| F1 | The four saved queries contained 9, 10, 6 and 0 cross-chunk hits: 25 occurrences across 15 distinct documents. In 24 occurrences the overview text did not contain the selected original value. Four identity consumers were checked: formatted generation context, generated-answer sources, retrieval-rerun sources, and retrieval record/candidate export. |
| F2 | Of 119 chunks with parenthesized currency declarations and tables, 4 documents gained 8 inherited numeric rows. Seven have labels; one KOICA row remains unlabelled and cannot supply a budget. Cases include two PDM tables and a museum table with 140-million/60-million components and a 200-million total. The four query results retain the museum's 200-million budget. |
| F3 | One actual parallel-field chunk had three date rows (`2025년`, `11월`, `14일`) corrected from `과업비` to `과업 기간`. Separately, reading cells independently changed six subject phrases across two other chunks: three scoring rows and three equipment-count rows. These are not counted as parallel-field corrections. A system/menu paragraph and an I/O glossary were checked to prevent unrelated later quantities receiving parallel labels. |

The census is recorded in `artifacts/quantity_review1_scope.json`; its final run is `artifacts/quantity_review1_scope_final_boundary.log`. The isolated local check rebuilds affected quantity metadata and distinct subject embeddings, then runs the four actual searches against the existing dense/BM25 index. Socket connections are blocked, the usage CSV must remain byte-identical, and the active index is not changed. It checks original spans, hit/candidate/value identity, primary source metadata, complete secondary-location markers and each body's token allowance. Stored dev answers are rerun against their own frozen dev index, with 30 questions at each of dense weights .6 and .5.

After final code and test cleanup, the nine affected files passed: `tests/test_quantity_filter.py`, `tests/test_retrieval.py`, `tests/test_answer_records.py`, `tests/test_ir_metrics.py`, `tests/test_rewrite.py`, `tests/test_server.py`, `tests/test_notebook_settings.py`, `tests/test_usage.py` and `tests/test_smoke.py` (**668 passed, 12 warnings in 31.08s**, `artifacts/quantity_review1_cleanup_gate.log`). The full-suite result below is historical; this review repair uses the affected suite. The obsolete assertion that declared-unit cells disappear was replaced by positive unit/span/scope regressions; its valid fines and standalone-scale checks remain. The money-only parallel-format case was folded into tests checking both fields and original spans. Existing overview tests now assert value-source identity and the separately identified overview. No current behavior checks or skips/xfails were discarded.

The final offline run (`artifacts/verify_quantity_review1_boundary.py`, log `artifacts/quantity_review1_offline_boundary.log`) passed with 29,339 quantity rows and 11,949 distinct subject phrases. The four queries retained 61/30/44/1 projects and 10/45/10/10 exclusions, with no added/removed projects or changed chosen values. Their 9/10/6/0 secondary overview locations are now explicit. All 60 stored dev `context_chunk_ids` sequences were unchanged. `ruff check .` passed, the rules files remained byte-identical, and the debt check exited 0. The final cleanup record is `artifacts/quantity_filter/review1_test_cleanup.json`.

The paid answers and user-reported browser acceptance below predate these review repairs. They remain historical evidence for those saved contexts, not new paid or browser acceptance of the repaired contexts. This repair makes no additional paid calls. Rebuild the active quantity index with 02 before using the repaired extraction in the frontend.

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
