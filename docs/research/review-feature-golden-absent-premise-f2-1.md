# 리뷰 조사 · F2, 1회차

집계 결과와 측정 조건은 Git에 보관하고, 실제 질문·정답·근거·OCR 텍스트와 레코드별 내보내기는 Git에서 제외된 로컬 `artifacts/`에 보관합니다.

복원 출처: 정리 전 `artifacts/review-round2/originals/` 또는 `d7d1682^`. 아래 수치와 검증 기록은 당시 실행에서 관측한 과거 기록이며, 이번 작업에서 다시 측정한 결과가 아닙니다.

PR #49 리뷰 2회차의 수정 전에 2026-10-16에 쓴 조사 초안입니다. 검증된 사실이나 공용 규칙이 아니며, 리뷰는 이 문서를 수정과 함께 읽습니다.

## 문제

'답 없음' 후보에 대해 `_absent_verdict`는 `document_batches`가 만든 어느 묶음으로 검증기를 불러도 질문에 답하지 못하면, 대상 문서에 그 속성이 없다고 인정합니다. 지켜야 할 규칙은 이렇습니다. 검증기가 대상 문서의 모든 단위를, 읽는 데 필요한 문맥과 함께 본 뒤에만 '없음'을 인정할 수 있습니다. 무엇보다 표의 행은 그 표의 머리글 행과 함께 봐야 합니다. `document_batches`는 구조와 상관없이 평평한 단위 목록을 `DOCUMENT_BATCH_CHARS`(60,000)자마다 자릅니다. 표의 머리글 행(0행)이 한 묶음에, 값 행이 다음 묶음에 들어가면 어느 묶음도 답할 수 없습니다. 예: 머리글 `시스템 | 하자담보책임기간 | ...`, 행 `A시스템 | 12개월 | ...`. 글자 그대로 보는 key_terms 검사는 동의어를 놓치고, 모든 호출은 올바르게 '답할 수 없음'을 돌려주며, 답할 수 있는 질문이 auto_validated로 출시됩니다.

발생: 반복, 1·2회차.

- [P1] [P1] golden_pipeline/validation.py:697 — 묶음 경계 때문에 답할 수 있는 질문이 여전히 '없음'으로 인정될 수 있습니다

## 실패한 수정

- 1회차(2686380, best_matching): 질문 단어와 가장 잘 맞는 단위 다섯 개만 검증기에 보냈습니다. 문서 아래쪽에 동의어로 쓰인 답은 한 번도 보이지 않았습니다. 리뷰어가 이를 재현했습니다.
- 2회차 수정(b8e4fa6/6007579, validation-5): best_matching을 document_batches로 바꿔 모든 단위를 60,000자 묶음으로 보냈습니다. 이제 빠짐없이 보내지만, 묶음마다 따로 판정하고 경계는 표를 무시합니다. plan.document_units는 {unit_id, text}만 돌려주고 location과 element_id를 버리므로, 묶는 쪽은 머리글과 행을 구별조차 못합니다. 칸 하나가 단위 하나이고 모든 청크 단위 뒤에 쓰이는 원본 격자 칸(evidence.py:48-49)도 같은 식으로 잘립니다. 수정은 이 구멍을 알고 ponytail 주석으로 미뤄 두었습니다(validation.py:680). 회귀 테스트는 DOCUMENT_BATCH_CHARS=1로 두고 혼자서 완결된 답을 마지막 단위에 넣으므로, 전달만 증명할 뿐 문맥을 잃는 경우에는 실패할 수 없습니다.

## 출처

### S1 — Unstructured 문서 — Chunking

- URL: https://docs.unstructured.io/open-source/core-functionality/chunking
- 확인일: 2026-10-16
- 위치: basic 전략; overlap 옵션
- 인용: Table은 "always isolated and never combined with another element." 최대 크기를 넘는 요소는 "divided into two or more chunks using text-splitting." 너무 큰 표는 "is divided into two or more TableChunk elements using text-splitting." overlap은 "only when using text-splitting to break up an oversized chunk"에만 적용되며 "this number of characters from the end of the prior chunk as a prefix on the next"를 담습니다. overlap_all은 보통 청크를 "pollute"할 수 있습니다. by_title: "a single chunk will never contain text that occurred in two different sections"(basic에는 섹션 규칙이 없음).
- 적용: 표를 한 묶음에 통째로 두고, 너무 클 때만 따로 다루는 방식을 뒷받침합니다. 겹침은 고정된 글자 수의 앞머리이므로, 더 위에 있는 머리글까지는 보장하지 못한다는 것도 보여 줍니다.
- 반대 근거: 표를 따로 떼어 청크로 둔다고 이어지는 TableChunk에 머리글이 따라가지는 않습니다. 그러려면 별도의 반복 옵션(S2)이 필요합니다.
- 검증: 단위 테스트에서 크기가 맞는 표는 한 묶음에 남는지 확인합니다.

### S2 — Unstructured 커밋 615782a — fix(chunking): preserve semantic headers in carried table chunks (#4313)

- URL: https://app.semanticdiff.com/gh/Unstructured-IO/unstructured/commit/615782a466f5e1b8a1e32183e133f8f9564fdb66
- 확인일: 2026-10-16
- 위치: 커밋 요약(받기가 HTTP 429를 돌려줘 검색 결과의 글을 씀)
- 인용: repeat_table_headers=True이고 표가 나뉘면, 앞쪽 머리글 행을 <thead>나 이어진 <th> 행으로 찾아내고, 이어지는 청크가 그 행을 <thead> 안에 되풀이합니다. 이어지는 청크의 .text에도 머리글 글이 들어가며, reconstruct_table_from_chunks()는 합친 표에 머리글이 겹치지 않도록 덧붙인 머리글 글을 지웁니다.
- 적용: 너무 큰 표에 대한 같은 처방입니다. 이어지는 묶음마다 맨 위에 0행을 되풀이합니다.
- 반대 근거: 직접 켜야 하고 최근 기능이라 모든 청커가 하지는 않습니다. 머리글 찾기에 기대는데, 여기서는 0행을 머리글로 가정하므로 여러 행 머리글은 놓칠 수 있습니다.
- 검증: 단위 테스트에서 같은 표의 행을 담은 모든 묶음에 0행 단위가 있는지 확인합니다.

### S3 — Chonkie — TableChunker

- URL: https://docs.chonkie.ai/oss/chunkers/table-chunker
- 확인일: 2026-10-16
- 위치: 개요 / 동작
- 인용: "splits large markdown or HTML tables into smaller, manageable chunks by row, always preserving the header"; "Each chunk is a valid markdown table segment, always including the header."; "If the table fits within the chunk size, it is returned as a single chunk."; "at least a header, separator, and one data row (for Markdown)"가 필요합니다.
- 적용: 같은 규칙의 독립된 구현입니다. 표가 맞으면 통째로 두고, 아니면 행으로 나누며 청크마다 머리글을 넣습니다.
- 반대 근거: 머리글이 명시된 markdown/HTML 표에서 동작합니다. 여기서는 머리글을 0행으로 추정합니다.
- 검증: 같은 단위 테스트.

### S4 — Anthropic — Introducing Contextual Retrieval

- URL: https://www.anthropic.com/news/contextual-retrieval
- 확인일: 2026-10-16
- 위치: 문제 설명; SEC 공시 예시
- 인용: "it can lead to problems when individual chunks lack sufficient context." ... "these traditional RAG systems have a significant limitation: they often destroy context." 예시 청크 "The company's revenue grew by 3% over the previous quarter" — "this chunk on its own doesn't specify which company it's referring to or the relevant time period." 단서: "well for many applications"에서 잘 동작한다고 함.
- 적용: 일반 원리입니다. 따로 읽은 청크는 이해에 필요한 것을 잃을 수 있습니다. 머리글 없는 표 행이 바로 이 경우입니다.
- 반대 근거: LLM이 읽는 경우가 아니라 검색 임베딩에 대해 쓴 글입니다. 처방(청크마다 LLM이 만든 문맥)은 유료 호출이 들고, 여기서는 제안하지 않습니다.
- 검증: 끝에서 끝까지 테스트에서, 머리글과 행이 다른 묶음에 있으면 수정 전에는 '없음'을 잘못 인정합니다.

### S5 — Liu 외, Lost in the Middle: How Language Models Use Long Contexts (TACL 2024)

- URL: https://arxiv.org/abs/2307.03172v3
- 확인일: 2026-10-16
- 위치: 초록
- 인용: 관련 정보가 입력 문맥의 처음이나 끝에 있을 때 성능이 가장 높은 경우가 많고, 긴 문맥 한가운데 있는 정보를 써야 하면 긴 문맥용 모델이라도 성능이 크게 떨어집니다. 입력 문맥이 길어질수록 성능도 떨어집니다.
- 적용: 문서 전체를 한 번에 보내 묶음을 아예 없애는 것에 반대하는 근거입니다. 한가운데서 답을 놓치면 같은 '조용한 잘못된 없음'이 됩니다.
- 반대 근거: 2023년 모델로 여러 문서 QA와 키-값 찾기에서 잰 결과입니다. 새 모델은 덜 떨어질 수 있고, gpt-5-mini에서는 시험하지 않았습니다.
- 검증: 이번 수정에서는 시험하지 않습니다.

### S6 — golden_pipeline/validation.py — _absent_verdict, document_batches, _calls_needed

- URL: golden_pipeline/validation.py
- 확인일: 2026-10-16
- 위치: 44행, 674-702행, 915-925행
- 인용: DOCUMENT_BATCH_CHARS = 60_000 ... if batches[-1] and size + len(unit["text"]) > DOCUMENT_BATCH_CHARS: batches.append([]) ... ponytail: 묶음 경계에 걸친 답(표 머리글과 그 행이 다른 묶음)이나 묶음 사이의 충돌은 보지 못한다. 놓치면 묶음을 겹쳐 나눈다. ... if item["primary_topic"] == "unanswerable": return len(document_batches(document))
- 적용: 글자 수로 자르는 방식, 2회차 수정이 스스로 표시한 구멍, 같은 함수에 기대는 호출 수 계산을 보여 줍니다.
- 반대 근거: 없음
- 검증: 수정은 document_batches(와 document_units의 필드)만 바꿉니다.

### S7 — golden_pipeline/plan.py — document_units, _with_headers; golden_pipeline/evidence.py — 단위 순서

- URL: golden_pipeline/plan.py
- 확인일: 2026-10-16
- 위치: plan.py:101-118, 249-263; evidence.py:48-49, 236-256
- 인용: found[unit["doc_sha"]].append({"unit_id": unit["unit_id"], "text": text}) ... _with_headers: 표 행이 든 묶음 앞에 그 표의 머리글 행(논리 표 0행)을 붙인다 ... pairs += [pair for grid in pkg["grids"] for pair in grid_units(grid, pkg)] ... grid unit location {kind: table, grid: original_reference, row, cell}
- 적용: 문서 단위는 location과 element_id를 잃으므로, 묶는 쪽은 표를 머리글과 함께 둘 수 없습니다. 격자 칸은 칸마다 따로이고 모든 청크 단위 뒤에 옵니다. 코드에는 근거 묶음용으로 머리글을 붙이는 함수가 이미 있습니다.
- 반대 근거: 없음
- 검증: 수정 뒤 document_units는 element_id와 location을 담고, 단위 테스트는 두 종류의 표를 모두 시험합니다.

### S8 — tests/golden/test_validation.py — 문서 전체 '없음' 테스트

- URL: tests/golden/test_validation.py
- 확인일: 2026-10-16
- 위치: 553-565행
- 인용: monkeypatch.setattr(validation, "DOCUMENT_BATCH_CHARS", 1) ... validator = Validator({(last,): verdict("2년"), "*": verdict("", answerable=False)}) ... assert [Validator.labels(request) ...][-1] == (last,)
- 적용: 유일한 회귀 테스트는 혼자서 완결된 단위 하나로 답하므로, 관계 문맥을 잃는 경우를 잡지 못합니다.
- 반대 근거: 없음
- 검증: 새 끝에서 끝까지 테스트는 머리글과 행 라벨이 같은 요청에 있어야 합니다.

## 주장

- C1 (출처; S4): 문서를 청크로 나누면 이해에 필요한 문맥이 없는 청크가 남을 수 있습니다.
- C2 (출처; S1, S2, S3): 문서 청커는 한 청크에 맞는 표는 통째로 두고, 너무 큰 표는 행 경계에서 나누며, 이어지는 청크마다 머리글 행을 되풀이합니다.
- C3 (출처; S6, S7): document_batches는 표 위치가 없는 단위들을 글자 수로 자르므로, 표 머리글과 그 행이 다른 묶음에 들어갈 수 있습니다. 2회차 수정은 이를 미룬 한계로 표시했습니다.
- C4 (해석; S1, S2, S7): document_units에 element_id와 location을 남기고, 표 단위로 묶고, 이어지는 묶음에 0행 단위를 되풀이하면 논리 표와 원본 격자 모두에서 리뷰어의 재현을 막습니다.
- C5 (해석; S5): 문서 전체를 한 번에 보내 묶음을 없애면, 경계 손실 대신 긴 문맥 한가운데의 재현율 손실을 얻을 뿐이며 같은 '조용한 잘못된 없음'으로 이어집니다.
- C6 (해석; S6, S8): 앞의 두 수정은 모두 읽을 수 있는지(각 묶음을 따로 읽을 수 있는지)가 아니라 빠짐없음(어떤 단위를 보내는지)을 다뤘습니다. 혼자서 완결된 답 단위로 만든 회귀 테스트는 둘을 구별할 수 없었고, 그래서 지적이 다시 나왔습니다.

## 핵심 원리

문서를 청크로 나누면 문맥이 깨집니다. 청크는 이해에 필요한 것을 잃을 수 있습니다(Anthropic, Contextual Retrieval). 그래서 문서 청커는 표를 한 단위로 다룹니다. Unstructured는 Table 요소를 따로 떼고, 너무 큰 표는 먼저 행 경계에서 나누며, #4313에서 repeat_table_headers를 더해 이어지는 청크가 앞쪽 머리글 행을 되풀이하게 했습니다. Chonkie의 TableChunker는 행으로 나누면서 늘 머리글을 남기고, 맞는 표는 한 청크로 돌려줍니다. 글자 겹침만으로는 '앞 청크 끝의 이만큼의 글자'만 덮으므로, 겹침보다 위에 있는 머리글은 되살리지 못합니다.

## 적용

golden_pipeline/validation.py:693의 document_batches가 묶음을 만드는 유일한 곳입니다. _absent_verdict(:674)와 _calls_needed(:923)가 모두 이를 읽으므로, 여기 한 곳만 바꾸면 둘 다 고쳐집니다. 입력은 golden_pipeline/plan.py:101의 document_units에서 오며, 이 함수는 element_id와 location이 있는 단위(units.jsonl, evidence.py:236-256)로 {unit_id, text}를 만듭니다. 논리 표 행은 location.kind=='table'이고 0행이 머리글이며, plan._table_row와 plan._with_headers도 이 관례를 씁니다. 격자 칸의 unit_id는 grid:sha:stream:control:row:col이고, location에 row/cell이 있습니다.

## 가설

원인은 이제 어떤 단위를 보내느냐가 아닙니다. 묶기가 문서를 각각 따로 읽을 수 없는 조각으로 나누는 것이 원인입니다. document_units가 location과 element_id를 지우므로 document_batches는 구조 없는 목록을 다루고, 글자 수로 자릅니다. 그러면 표 행이 열 이름을 알려 주는 머리글 행 없이 검증기에 갑니다. 수정: document_units가 element_id와 location을 남기게 합니다. document_batches에서는 표마다 한 묶음에 둡니다. 논리 표는 element_id로, 격자는 (stream, control)로 구분합니다. 표가 들어가지 않으면 행 경계에서 나누고, 그 표의 0행 단위를 원래 라벨 그대로 이어지는 묶음 맨 위에 되풀이합니다. plan._with_headers가 근거 묶음에 이미 하는 방식과 같습니다. _calls_needed는 계속 document_batches로 세야, 호출 예산에 되풀이한 머리글이 들어갑니다.

## 반대 근거

- 대부분의 경계는 표에 걸리지 않을 수 있습니다. 문서 크기의 중앙값이 약 66k자라 대부분 묶음 한두 개면 되고, 경계는 많아야 하나입니다. 실제 데이터에서 얼마나 자주 일어나는지는 재지 않았습니다.
- 머리글 되풀이는 표 문맥만 고칩니다. 한 묶음에 있는 섹션 제목과 다음 묶음의 문단(예: 'A시스템' 다음 '하자담보책임기간: 12개월')은 여전히 떨어질 수 있습니다. 요소를 통째로 두는 것은 따로 떨어진 요소인 제목까지 다루지 못합니다.
- 한 묶음 안에서도 원본 격자 칸은 행·열 좌표 없이 떨어진 칸 글로 검증기에 가므로, 머리글이 있어도 읽기 어려울 수 있습니다. 이번 수정이 다루지 않는 별도의 약점입니다.

## 다른 방법

- 문서마다 호출 한 번으로 경계 없애기: 가장 큰 문서가 약 200k자라 아마 gpt-5-mini의 문맥에 들어가고, 전체 입력 토큰도 비슷합니다. 먼저 하지 않는 이유는 긴 문맥 한가운데서 재현율이 떨어지기 때문입니다(Lost in the Middle). 거기서 답을 놓치면 같은 '조용한 잘못된 인정'이 되고, 60k 한도를 고른 이유도 기록이 없습니다.
- 묶음 사이의 고정 글자 겹침(ponytail 주석이 말한 다음 단계): 싸지만, 겹침보다 긴 표는 여전히 머리글을 잃습니다. 보장이 아닙니다.
- 묶음이 둘 이상 필요한 문서의 '답 없음' 후보는 모두 거부(리뷰어의 대비책): 타당하고 최소한이지만, 문서 중앙값이 66k자쯤이라 이 주제에서 문서의 절반가량이 빠집니다. 문맥과 함께 둘 수 없는 묶음이 발견되면 그때의 대비책으로만 둡니다.
- Anthropic의 contextual retrieval처럼 LLM으로 단위마다 문맥 되살리기: 단위마다 함께 쓰는 키로 유료 호출이 하나씩 듭니다. 구조가 이미 units.jsonl에 있으니 정당하지 않습니다.

## 실험

1) document_batches 단위 테스트: 문단 하나, 표 요소 하나(0행 머리글과 1..n행), 0행과 1행에 칸이 있는 격자 하나로 문서를 만듭니다. 단순히 자르면 머리글과 행 사이에서 잘리도록 DOCUMENT_BATCH_CHARS를 정합니다. 표 X의 행을 담은 모든 묶음에 X의 0행 단위도 있는지 확인하고, 격자도 같은 식으로 확인합니다. 2) tests/golden/test_validation.py의 끝에서 끝까지 테스트: 핵심어의 동의어를 쓰는 머리글과 값 행이 든 대상 문서를 둡니다. 가짜 검증기는 머리글 라벨과 행 라벨이 같은 요청에 올 때만 '12개월'로 답합니다. 지금 코드에서는 auto_validated로 나오고, 수정 뒤에는 '대상 문서에 있음: 검증기'로 거부돼야 합니다. 기존 test_absence_is_certified_only_after...도 계속 통과해야 합니다. 3) 실제 근거 실행에 대해, feabfe5에서 출시한 '답 없음' 항목 중 60k 묶음 경계에 표가 잘린 것이 몇 개인지 셉니다. 그런 항목은 다시 검증해야 합니다.

## 결과

24fe719(validation-6)의 수정으로 관측했고, 데이터는 이 결과를 더한 커밋에서 다시 만들었습니다. 아직 초안이며 검증된 규칙이 아닙니다.

1) 단위 테스트 `tests/golden/test_validation.py::test_every_batch_holding_a_table_row_also_holds_that_tables_header`(한도 40, 70, 1, 겹침 0)가 통과합니다. 수정 전 HEAD의 `document_batches`로 한도 70이면 묶음은 `[p1, t0] [t1, t2, grid…]`였고, 머리글 `t0`와 행 `t1`이 떨어졌습니다. 수정 뒤에는 `[p1] [t0, t1, t2] [t2, grid…]`입니다. 이 테스트는 옛 코드에서 세 한도 모두 실패했습니다.
2) `test_absence_is_not_certified_when_the_answer_needs_units_on_both_sides_of_a_batch_boundary`는 표 머리글/행 쌍과 섹션 제목/문단 쌍에서 통과합니다. 두 경우 모두 옛 코드에서는 실패(auto_validated)합니다. 제목 경우에는 새로 넣은 2,000자 겹침이 필요합니다. 겹침이 없으면 묶음이 `[E1, E2] [E3]`, 있으면 `[E1, E2] [E2, E3]`입니다. `test_absence_is_certified_only_after…`는 겹침을 0으로 두고 계속 통과합니다.
3) 근거 실행 v11-20261014에 옛 묶기를 적용하면, feabfe5(분할 final5)에서 출시한 '답 없음' 항목 11개 중 9개가 60k 경계에 잘린 표를 하나 이상(항목마다 1~12개) 가졌습니다. 이 항목들은 교체했습니다. validation-6에서 새 반복 ap7-dev($0.57, 8개 채택)와 ap7-test($0.58, 8개 채택), 릴리스 final6(16개 중 16개, $0.038), split final6 --base final2를 거쳐 eval/golden(dev 408, test 943)에 복사했습니다.
관측한 반대 근거: 새 묶기에서도 새 항목 16개 중 7개는 어떤 묶음에 머리글 없는 표 행이 있습니다(27행). 27행 모두, 앞 묶음에서 머리글을 포함한 표 전체를 이미 읽은 행의 겹침 꼬리 복사본입니다. 정확한 규칙, 즉 모든 표 행을 머리글과 함께 적어도 한 번 읽는다는 것은 16개 중 16개에서 지켜집니다(final5 항목 11개를 다시 묶어도 마찬가지). 위에 적은 다른 반대 근거(좌표 없이 읽는 원본 격자 칸, 경계에서 2,000자보다 먼 제목)는 시험하지 않았습니다.

## 남은 한계

여기에는 셸이 없어 아무것도 돌리지 않았고, 실제 데이터에서 표가 얼마나 자주 잘리는지는 모릅니다. 본문과 떨어진 섹션 제목, 묶음 사이의 충돌, 좌표 없이 보내는 격자 칸은 여전히 다루지 못합니다. Unstructured #4313 페이지가 HTTP 429를 돌려줘, 그 문구는 검색 결과 요약에서 가져왔습니다. DOCUMENT_BATCH_CHARS가 왜 60,000인지는 저장소 어디에도 없습니다. 0행이 늘 유일한 머리글 행인지(여러 행 머리글)는 확인하지 않았습니다.
