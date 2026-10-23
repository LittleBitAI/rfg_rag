# 리뷰 조사 · F2, 2회차

집계 결과와 측정 조건은 Git에 보관하고, 실제 질문·정답·근거·OCR 텍스트와 레코드별 내보내기는 Git에서 제외된 로컬 `artifacts/`에 보관합니다.

편집 주의: 실제 자료에서 복사한 질문·답·근거 문구는 지웠습니다. 아래 합성 예제는 이번 문서 수정을 위해 따로 쓴 것이며, 실제 릴리스를 대신하는 기록이 아닙니다. 기존 집계 수치·실험 조건·한계는 당시 기록을 그대로 둡니다.

복원 출처: 정리 전 `artifacts/review-round2/originals/` 또는 `d7d1682^`. 아래 수치와 검증 기록은 당시 실행에서 관측한 과거 기록이며, 이번 작업에서 다시 측정한 결과가 아닙니다.

PR #49 리뷰 3회차의 수정 전에 2026-10-16에 쓴 조사 초안입니다. 검증된 사실이나 공용 규칙이 아니며, 리뷰는 이 문서를 수정과 함께 읽습니다.

## 문제

'답 없음' 후보에 대해 `_absent_verdict`는 `document_batches`가 만든 어느 묶음으로 검증기를 불러도 질문에 답하지 못하면, 대상 문서에 그 속성이 없다고 인정합니다. 묶음은 각각 따로 읽히므로 지켜야 할 규칙은 이렇습니다. 모든 단위는 이해에 필요한 단위들과 함께 한 묶음 안에서 적어도 한 번 읽혀야 합니다. 표 칸이라면 그 행을 알려 주는 칸과 열 머리글이 필요합니다. 원본 격자는 이 규칙을 깹니다. `evidence.grid_units`는 칸마다 단위를 하나씩 만들고, `document_batches`는 격자를 아무 두 칸 사이에서나 자를 수 있습니다. 그러면 행의 라벨 칸('A시스템')과 값 칸('1년')이 다른 묶음에 들어갑니다. 이어지는 묶음은 0행 머리글은 되풀이하지만 행 라벨은 되풀이하지 않습니다. 모든 묶음이 올바르게 '답할 수 없음'을 돌려주고, 답할 수 있는 질문이 auto_validated로 출시됩니다. 실제 운영에서는 격자가 `DOCUMENT_OVERLAP_CHARS`보다 긴 칸 바로 뒤에서 60,000자를 넘을 때 일어납니다. 그때 `_tail`은 아무것도 넘겨주지 않기 때문입니다.

발생: 반복, 2·3회차.

- [P1] [P1] golden_pipeline/validation.py:712 — 원본 격자의 행이 여전히 라벨과 값 사이에서 나뉠 수 있습니다

## 실패한 수정

- 1회차(2686380): best_matching이 질문 단어와 가장 잘 맞는 단위 다섯 개만 보냈습니다. 아래쪽에 동의어로 쓰인 답은 한 번도 보이지 않았습니다.
- 2회차 수정(b8e4fa6/6007579): document_batches가 모든 단위를 60,000자 묶음으로 보냈지만, 구조와 상관없이 글자 수로 잘라서 표 머리글과 그 행이 다른 묶음에 들어갈 수 있었습니다. 테스트는 혼자서 완결된 답 단위를 써서 전달만 증명했습니다.
- 1회차 조사 뒤 수정(24fe719, validation-6): 표마다 한 그룹으로 묶었습니다(논리 표는 element_id, 격자는 stream:control). 너무 큰 표는 단위 사이에서 나누고, 이어지는 묶음마다 0행 단위를 되풀이하며, 2,000자 겹침을 더했습니다. 단위 하나가 행 하나라고 가정했습니다. 논리 표(행마다 단위 하나, 칸은 ' | '로 이음)에는 맞지만 원본 격자(칸마다 단위 하나)에는 맞지 않아, '행 경계' 자르기가 실제로는 칸 경계였습니다. 겹침도 이를 구하지 못합니다. 마지막 단위가 2,000자보다 길면 `_tail`은 아무것도 돌려주지 않습니다. 테스트 test_every_batch_holding_a_table_row_also_holds_that_tables_header는 '머리글 ⊆ 묶음'만 확인했으므로, 한도 1에서 자기 TABLES 테스트 데이터가 GRID:1:0('A시스템')과 GRID:1:1('1년')을 다른 묶음으로 보내는데도 통과했습니다. 1회차 조사도 같은 실수를 했습니다. '행 경계에서 나눈다'고 하면서 '0행 단위를 되풀이한다'고 정했고, 머리글이 있는지만 시험했습니다.

## 출처

### S1 — Twig — Tables breaking across chunks (RAG scenarios and solutions)

- URL: https://www.twig.so/dev/rag-scenarios-and-solutions/chunking/table-splitting
- 확인일: 2026-10-16
- 위치: rowspan/colspan 절; 청크 경계 규칙
- 인용: HTML 표에서 청크 경계는 표를 나누거나, 머리글과 본문을 떼거나, 행을 깨서는 'must not'. 'Rowspan="2": Cell spans 2 rows'를 정의하고, 첫 행 뒤에서 나누면 'Misaligned columns in chunk 2'가 된다고 경고합니다. 큰 표: 'Keep headers, split rows', 대가는 'Header repetition, storage overhead'. 표를 통째로 두면 'Ensures no table is split'이지만 'Variable chunk sizes'가 됩니다. 긴 칸은 'Might trigger chunk split mid-cell'.
- 적용: 이번 수정에 필요한 두 규칙을 바로 말합니다. 행 안에서는 절대 나누지 않고, 걸친 칸이 행들을 묶으므로 rowspan을 따라가야 합니다.
- 반대 근거: HTML 표의 임베딩 청크에 대한 업체 안내서이지, LLM 검증 묶음에 대한 글이 아니며 측정도 없습니다. 긴 칸은 칸 중간에서 나눌 수 있다고도 인정합니다.
- 검증: 단위 테스트에서 모든 격자 칸이 rowspan 띠 전체와 머리글 띠와 함께 읽히는지 확인합니다.

### S2 — Ragie — Our approach to table chunking

- URL: https://www.ragie.ai/blog/our-approach-to-table-chunking
- 확인일: 2026-10-16
- 위치: 접근 방식 절
- 인용: 대부분의 보통 경우 'rows are never split mid-record'이고 'table data is never disassociated from its table headers'; 머리글은 'aren't repeated excessively'. 들어가지 않는 표는 'processed by row'로, 들어가는 만큼의 행으로 새 표와 청크를 만듭니다. 예외: 'a single row exceeds the maximum size for an embedding it is then split'. 병합 칸은 언급하지 않습니다.
- 적용: 같은 규칙의 독립된 구현입니다. 행은 쪼갤 수 없고, 행 사이에서만 나누며, 머리글을 남깁니다. 격자에서는 띠가 쪼갤 수 없는 단위에 해당합니다.
- 반대 근거: 너무 큰 행에 대한 예외가 있고 병합 칸은 말하지 않습니다. 여기서는 60k를 넘는 띠는 나누지 않고 너무 큰 채로 둡니다.
- 검증: 같은 단위 테스트. 너무 큰 띠는 나누지 않고 혼자 한 묶음에 넣습니다.

### S3 — Structure-Aware Chunking for Tabular Data in Retrieval-Augmented Generation (arXiv 2605.00318)

- URL: https://arxiv.org/abs/2605.00318
- 확인일: 2026-10-16
- 위치: 초록
- 인용: STC는 'operates on row-level units'이며 'each row is encoded as a key-value block', 'performs token-constrained splitting aligned with structural boundaries', 'preserves semantic relationships between fields within a row'. MAUD 데이터셋에서만 평가했고 진행 중인 연구로 표시돼 있으며, 초록에는 토큰 한도를 넘는 행에 대한 규칙이 없습니다.
- 적용: 행(여기서는 rowspan 띠)을 묶기에서 쪼갤 수 없는 단위로 삼아, 한 행의 필드가 함께 있게 하는 것을 뒷받침합니다.
- 반대 근거: CSV/Excel에서 잰 검색 지표이며 데이터셋 하나, 진행 중인 연구입니다. LLM의 '없음' 판정에 대한 것이 아닙니다.
- 검증: 끝에서 끝까지 테스트에서 한 행의 라벨과 값이 같은 검증기 요청에 도착합니다.

### S4 — Chonkie — TableChunker

- URL: https://docs.chonkie.ai/oss/chunkers/table-chunker
- 확인일: 2026-10-16
- 위치: 개요
- 인용: 큰 markdown이나 HTML 표를 'into smaller, manageable chunks by row, always preserving the header'로 나누고, 맞는 표는 한 청크로 돌려줍니다.
- 적용: 머리글을 남기는 행 단위 나누기로, 격자 단위가 행이 되면 기존 반복문과 같습니다.
- 반대 근거: 행이 이미 한 줄인 markdown/HTML에서 동작하며, rowspan은 말하지 않습니다.
- 검증: 기존 머리글 테스트와 새 띠 테스트.

### S5 — golden_pipeline/validation.py — document_batches, _table_groups, _tail, validator_input

- URL: golden_pipeline/validation.py
- 확인일: 2026-10-16
- 위치: 44-46행, 304-306행, 696-745행, 958행
- 인용: for unit in group: if fresh and size + len(unit['text']) > DOCUMENT_BATCH_CHARS: carried = _tail(batches[-1]); batches.append([header for header in headers if _row(unit) and header not in carried] + carried) ... _tail: if size > DOCUMENT_OVERLAP_CHARS: break ... validator_input은 {label, text}만 보냅니다.
- 적용: 그룹의 아무 두 단위 사이에서 나뉘고, 되풀이하는 문맥은 0행 단위뿐이며, 마지막 단위가 길면 `_tail`이 뒤를 모두 버리고, 검증기는 좌표를 보지 못한다는 것을 보여 줍니다.
- 반대 근거: 없음
- 검증: 수정은 document_batches를 바꾸고(반복문 전에 띠 합치기), document_units가 rowspan을 넘기게 합니다.

### S6 — golden_pipeline/evidence.py — grid_units, _cell_unit

- URL: golden_pipeline/evidence.py
- 확인일: 2026-10-16
- 위치: 152-173행, 247-261행
- 인용: return [_cell_unit(base, stream, control, cell, errors, pkg) for cell in grid['cells']] ... 'unit_id': f"grid:{doc_sha}:{stream}:{control}:{cell['row']}:{cell['col']}" ... 'location': {'kind': 'table', 'grid': 'original_reference', 'row': cell['row'], 'cell': cell['col']}
- 적용: 격자는 칸마다 단위 하나인데, 논리 표는 행마다 단위 하나입니다. 1회차 수정이 놓친 어긋남이 이것입니다.
- 반대 근거: 없음
- 검증: 띠 테스트는 이 모양으로 격자 단위를 만듭니다.

### S7 — v11 원본 격자 참고 파일의 첫 기록

- URL: data/RFP_Preprocessing_Final_v11_Team/validation/복구표_원본그리드_참고.jsonl
- 확인일: 2026-10-16
- 위치: 1행, control 1974
- 인용: 원래 v11 격자 칸의 원문 인용은 지웠습니다. 따로 만든 합성 예제는 `{row: 3, col: 0, rowspan: 2, text: "종이별 꾸러미"}`, `{row: 3, col: 1, text: "리본 색"}`, `{row: 3, col: 2, text: "자주색"}`, `{row: 4, col: 1, text: "포장 재료"}`, `{row: 4, col: 2, text: "무늬 종이"}`입니다. 아래 행이 위 행의 라벨을 함께 쓰는 구조만 설명하며, 실제 기록을 대신하는 값이나 측정 입력으로 쓰지 않았습니다. 당시 확인한 원본의 구조 집계는 rows 8, cols 3, level 1, parent_control null이었습니다.
- 적용: 실제 데이터에 rowspan이 있으므로 4행은 3행의 칸이 라벨을 붙여 주며, 행 번호로만 묶으면 둘이 갈라집니다. 이 기록은 세로 키-값 양식이라, 0행이 늘 열 머리글은 아니라는 것도 보여 줍니다. 0행을 되풀이해도 해롭지는 않지만, 중요한 것은 행 라벨입니다.
- 반대 근거: 기록 하나만 살폈고, 격자 전체에서 rowspan이 얼마나 흔한지는 세지 않았습니다.
- 검증: 테스트는 실제 본문을 복사하지 않고, rowspan으로 이어진 행을 함께 보내야 한다는 구조를 따로 만든 합성 입력으로 검사합니다.

### S8 — tests/golden/test_validation.py — TABLES 테스트 데이터와 머리글 테스트

- URL: tests/golden/test_validation.py
- 확인일: 2026-10-16
- 위치: 575-602행
- 인용: doc_unit(f'{GRID}:1:0', 'A시스템', row=1), doc_unit(f'{GRID}:1:1', '1년', row=1) ... @pytest.mark.parametrize('limit', [40, 70, 1]) ... assert header <= sent
- 적용: 테스트는 머리글이 있는지만 확인하므로, 한도 1에서 자기 테스트 데이터가 격자 행의 라벨과 값을 떼어 놓는데도 통과합니다.
- 반대 근거: 없음
- 검증: 새 테스트는 띠 전체가 함께 있는지 확인하며, 같은 테스트 데이터로 지금 코드에서 실패합니다.

### S9 — 앞선 조사 — review-feature-golden-absent-premise-f2-1.md

- URL: docs/research/review-feature-golden-absent-premise-f2-1.md
- 확인일: 2026-10-16
- 위치: 가설; 실험 1; 반대 근거
- 인용: When a table cannot fit, split it at row boundaries and repeat its row-0 units ... Assert that every batch containing a row of table X also contains X's row-0 unit(s), and the same for the grid ... original grid cells reach the validator as isolated cell texts without row and column coordinates ... That is a separate weakness this fix does not address.
- 적용: 정해 둔 테스트는 머리글만 확인했고, 격자 칸의 약점은 적어 두고 미뤘습니다. 3회차가 찾은 빈틈이 바로 이것입니다.
- 반대 근거: 없음
- 검증: 이번 회차의 실험이 머리글만 보는 확인을 바꿉니다.

## 주장

- C1 (출처; S5, S6): document_batches는 그룹을 아무 두 단위 사이에서나 나누고, 원본 격자 단위는 칸 하나이므로, 격자 행의 라벨 칸과 값 칸이 다른 묶음에 들어갈 수 있습니다. 이어지는 묶음은 0행 단위만 되풀이하고, `_tail`은 DOCUMENT_OVERLAP_CHARS보다 긴 단위 뒤에서는 아무것도 넘기지 않습니다.
- C2 (출처; S1, S2, S3, S4): 표를 아는 청커는 행을 쪼갤 수 없는 단위로 다루고, 큰 표는 행 사이에서만 나누며, 청크마다 머리글을 남깁니다. 혼자서 너무 큰 행만 대비책으로 나눕니다.
- C3 (해석; S1, S7): rowspan은 이어진 행들을 묶고, v11 격자 파일에는 rowspan 칸이 있습니다. 그래서 격자에서 쪼갤 수 없는 단위는 행 번호가 아니라 rowspan 띠입니다.
- C4 (해석; S5, S8, S9): 실패한 수정마다 규칙보다 약한 성질을 강제하고 시험했습니다. 2회차는 전달, 1회차 조사 뒤 수정은 머리글이 있는지였습니다. 리뷰마다 시험한 성질과 '답을 읽는 데 필요한 단위가 한 묶음에 도착한다' 사이의 빈틈을 찾았습니다. 1회차 조사 뒤 수정은 단위 == 행이라고 가정했고, 격자에서는 틀렸습니다.
- C5 (해석; S1, S2, S5, S7): 기존 나누기 반복문 전에 원본 격자마다 rowspan 띠당 단위 하나로 합치면, 모든 나누기가 띠 사이에서 일어나고, 여러 행 머리글이 0행 띠로 함께 남으며, `_tail`이 띠 전체를 넘기고, 떨어진 칸으로는 볼 수 없던 행 구조를 검증기가 보게 됩니다.

## 핵심 원리

표를 아는 청커는 행을 쪼갤 수 없는 가장 작은 단위로 다루고, 행 사이에서만 나누며, 청크마다 머리글을 남깁니다. 병합 칸(rowspan/colspan)은 따라가야 합니다. 걸친 행 뒤에서 나누면 문맥을 잃고 열이 어긋나기 때문입니다. 행 하나가 혼자서 크기 한도를 넘을 때만 대비책으로 그 행을 나눕니다.

## 적용

golden_pipeline/validation.py:696-718의 document_batches가 묶음을 만드는 유일한 곳이며, _absent_verdict(:685)와 _calls_needed(:958)가 모두 이를 읽습니다. _table_groups(:721-730)는 이미 unit_id에서 ':row:col'을 뺀 값으로 격자를 묶습니다. 격자 단위는 evidence.py:152-173과 _cell_unit(:247-261)에서 칸마다 하나씩 나오며, location은 {kind: table, grid: original_reference, row, cell}입니다. 격자 출처(data/RFP_Preprocessing_Final_v11_Team/validation/복구표_원본그리드_참고.jsonl)는 칸마다 row, col, rowspan, colspan을 줍니다. plan.document_units(plan.py:101-121)는 칸 글을 얻으려고 이 파일을 읽으며, 같은 식으로 rowspan을 넘길 수 있습니다. validator_input(validation.py:304-306)은 label과 text만 보내므로, 합친 띠 글이 검증기가 어느 칸들이 한 행인지 볼 수 있는 유일한 길이기도 합니다.

## 가설

이번에도 수정은 규칙보다 약한 성질을 강제했습니다. 이번에는 '행을 읽는 데 필요한 칸들이 함께 읽힌다' 대신 '머리글이 있다'였습니다. 구조적 원인은 격자의 묶기 단위가 칸인데, 혼자서 완결된 가장 작은 조각은 행 띠, 즉 rowspan으로 묶인 이어진 행들이라는 것입니다. 실제 격자 파일에 rowspan이 있습니다. 예를 들어 aea2b415… control 1974에서 3행 0열 '요구사항 세부내용'은 rowspan 2이고, 자기 0열 칸이 없는 4행의 라벨이 됩니다. 그래서 리뷰어 제안처럼 행 번호로만 묶어도 병합 라벨이 두 번째 행과 떨어집니다. 수정: document_batches 시작에서 원본 격자 그룹마다 행 띠당 단위 하나로 바꿉니다. 띠 글은 행 안의 칸을 ' | '로, 행끼리는 줄바꿈으로 잇습니다. location.row는 띠의 첫 행이므로, 0행을 담은 띠가 기존 반복문이 되풀이하는 머리글로 남고 여러 행 머리글도 다룹니다. element_id/unit_id는 같은 방식으로 묶입니다. 그러면 기존 단위별 나누기 반복문은 띠 사이에서만 나누고, `_tail`은 띠 전체를 넘기며, _calls_needed는 같은 묶음을 셉니다. document_units는 격자 칸의 rowspan을 넘겨야 하며, 이미 그 글을 얻으려고 격자 파일을 읽습니다.

## 반대 근거

- 한 묶음보다 큰 실제 격자는 아주 적을 수 있습니다(문서 중앙값 약 66k자). final6에서 얼마나 자주 일어나는지는 재지 않았고, 수정이 출시 항목을 하나도 바꾸지 않을 수도 있습니다.
- 논리 표의 행도 같은 식으로 위 행에 기댈 수 있습니다. 빈 칸으로 시작하는 복원된 markdown 행(BLANK_CELL 패턴, validation.py:38)은 위 행의 병합 라벨을 이어 갑니다. 그런 논리 행 사이에서 나누면 둘이 떨어집니다. 격자만 띠로 묶으면 이 경우는 남습니다.
- 중첩 격자(parent_control이 있음)는 다른 그룹에 있는 부모 칸의 행에서 뜻을 얻습니다. 띠로 묶어도 함께 두지 못합니다.
- DOCUMENT_BATCH_CHARS를 넘는 띠 하나는 여전히 혼자 너무 큰 묶음에 들어갑니다(fresh==0 분기). 출처들은 너무 큰 행을 대비책으로 나누는데, 그러면 그 띠에서 문제가 되살아납니다.

## 다른 방법

- 격자를 행 번호 사이에서만 나누기(리뷰어의 글자 그대로의 제안): 더 작지만, rowspan 라벨(3행의 '요구사항 세부내용', rowspan 2)이 여전히 4행과 떨어집니다. 실제 데이터에 그런 칸이 있습니다.
- 칸은 따로 두고 나눌 자리만 띠 경계로 제한하기: 덮는 범위는 같지만 반복문이 두 단계가 되고, 검증기는 여전히 행 구조 없는 떨어진 칸 글을 받습니다. 띠를 합치는 쪽이 코드가 적고 읽기 쉽습니다.
- 격자 띠를 document_batches가 아니라 document_units에서 합치기: 이것도 되지만, 다른 호출 쪽과 tests/golden/test_validation.py:550의 기존 테스트가 대상 문서에 기대하는 글이 바뀝니다. document_batches에서 하면 변경이 '없음' 경로 안에 머뭅니다.
- DOCUMENT_OVERLAP_CHARS 늘리기: 긴 칸이 여전히 `_tail`을 비우므로 아무것도 보장하지 못합니다. 리뷰어가 짚은 운영 경우가 이것입니다.
- 대상 문서에 한 묶음보다 큰 격자가 있는 '답 없음' 후보는 모두 거부: 타당하고 최소한이지만, 띠로 묶으면 공짜로 없어지는 구조적 이유로 후보를 버립니다.

## 실험

1) document_batches 단위 테스트: 0행 머리글, 0열에 rowspan 2 라벨 칸이 있는 1행, 값 칸만 있는 2행, 경계 바로 앞의 긴 칸(> DOCUMENT_OVERLAP_CHARS)으로 격자를 만듭니다. 한도 1, 40, 70을 겹침 0과 20으로 돌립니다. 모든 격자 칸에 대해, 그 띠의 모든 칸과 머리글 띠를 함께 담은 묶음이 있는지 확인합니다. 지금 코드는 한도 1에서 기존 TABLES 테스트 데이터로도 이미 실패합니다(GRID:1:0과 GRID:1:1이 다른 묶음). 2) _absent_verdict를 거치는 끝에서 끝까지 테스트: 가짜 요청은 행 라벨 글과 값 글이 한 묶음에 올 때만 '1년'으로 답합니다. 지금 코드는 auto_validated를 돌려주고, 수정 뒤에는 'rejected', '대상 문서에 있음: 검증기'를 돌려줘야 합니다. 기존 테스트 test_every_batch_holding_a_table_row_also_holds_that_tables_header와 test_absence_is_certified_only_after…도 계속 통과해야 하며, 띠 묶기로 번호가 바뀌면 라벨 기대값을 고칩니다. 3) 오프라인, 유료 호출 없음: final6에서 출시한 '답 없음' 항목 16개에 대해 지금 코드로 근거 실행 v11-20261014의 document_batches를 다시 만들고, 묶음 사이에서 나뉜 격자 띠를 셉니다. 있으면 다시 검증할 항목을 나열하고, API를 부르기 전에 값을 매깁니다. BLANK_CELL과 맞는 논리 행이 위 행과 떨어진 경우도 세어, 그 경우에 같은 처리가 필요한지 정합니다.

## 결과

초안이며, 여기 적은 것 외에는 검증하지 않았습니다. 커밋 8723a5e(validation-7)에서 관측했습니다.

- 수정 전 재현: 옛 `document_batches`로 한도 1, 겹침 0이면 `TABLES` 격자의 `:7:1:0`과 `:7:1:1` 칸이 다른 묶음으로 갔습니다.
- 수정: `_grid_bands`가 라벨을 붙이기 전에 원본 격자 그룹마다 rowspan 띠당 단위 하나로 바꿉니다. 행 안의 칸은 ' | '로, 행끼리는 줄바꿈으로 잇고, 띠는 첫 칸의 `unit_id`와 `location`을 가지므로 0행 띠가 머리글이 됩니다. 이제 `plan.document_units`가 격자 칸의 `rowspan`을 넘깁니다.
- 실험 1: `tests/golden/test_validation.py::test_every_table_row_is_read_in_one_batch_with_the_rest_of_its_row_and_its_header`, 한도 1, 40, 70 × 겹침 0과 20. 테스트 데이터에는 rowspan 2 라벨 `C시스템`, 경계 앞의 긴 칸, 값만 있는 2행이 있습니다. 옛 코드에서는 한도 1(두 겹침 모두)에서 실패하고, 새 코드에서는 통과합니다. 한도 40과 70은 이 테스트 데이터로 옛 코드에서도 통과했습니다.
- 실험 2: `test_absence_is_not_certified_when_the_answer_needs_units_on_both_sides_of_a_batch_boundary`의 `(1, 0, TABLES, {"C시스템", "유지보수 1년"}, …)` 경우. 옛 코드는 `auto_validated`를 돌려줬고, 새 코드는 `대상 문서에 있음: 검증기`와 함께 `rejected`입니다. 기존 테스트도 통과합니다: `.venv\Scripts\python -m pytest -q tests` → 569 passed.
- 실험 3(오프라인, 옛 코드, final6에서 출시한 '답 없음' 항목 16개): 본 rowspan 띠 245개 중 묶음 사이에서 나뉜 격자 띠 0개, 위 행과 떨어진 빈 칸 시작 논리 행 0개, 중첩 격자 0개, 영향받은 항목 0개였습니다. 띠가 나뉜 채 읽힌 출시 항목이 없으므로 eval/golden은 그대로 두고, 유료 재검증은 돌리지 않았습니다.

## 남은 한계

여기에는 셸이 없어 아무것도 돌리지 않았습니다. 실제 데이터에서 너무 큰 격자, rowspan 띠, 빈 칸 시작 논리 행이 얼마나 자주 나오는지는 모릅니다. colspan이 중요한지는 시험하지 않았습니다. colspan은 띠 안의 칸 위치를 바꾸지만 띠에 속하는지는 바꾸지 않습니다. 중첩 격자와 60,000자를 넘는 띠는 여전히 다루지 못합니다. 웹 출처들은 HWP 격자에 대한 LLM의 '없음' 인정이 아니라 HTML이나 CSV 표의 검색 청킹을 설명하므로, 행을 쪼갤 수 없는 단위로 삼는 규칙을 유추로만 뒷받침합니다.
