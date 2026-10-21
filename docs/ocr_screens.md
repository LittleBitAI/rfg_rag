# OCR 이미지 라벨링 · 결과 검토 화면

두 화면 모두 질문 화면과 같은 실행기(`frontend\start.cmd` · `frontend/start.command`)로 열고, 첫 화면 오른쪽 위 `설정`에서 들어갑니다. 서버는 실행기가 띄우는 8766 포트를 함께 씁니다.

## OCR 이미지 라벨링 화면

RFP 문서에서 꺼낸 그림마다 OCR이 필요한지 사람이 매기는 화면입니다(`http://localhost:5173/ocr.html`).

- 카드 하나가 그림이 나온 위치 하나입니다. 같은 그림(반복 로고 등)도 나온 곳마다 카드가 따로 있고 따로 매깁니다.
- 라벨은 `1` 꼭 인식해야 함 · `2` 인식해야 하나 어려움 · `3` 인식할 필요 없음 셋이고, 누르는 즉시 저장됩니다. 화면을 다시 열면 매긴 라벨이 그대로 보입니다.
- WMF · EMF처럼 미리보기를 만들 수 없는 그림도 자리표시 카드(형식 · 문서 이름 · 위치)로 나오고 라벨을 매길 수 있습니다.
- `artifacts/ocr_selection.jsonl`(CRAFT 선별 기록)이 있으면 카드에 CRAFT 분류를 함께 보여 줍니다. 없어도 화면은 그대로 동작합니다.
- 그림을 누르면 크게 보고(바깥 · Esc로 닫기, ◀ ▶ · ← →로 넘기기), `원본 보기`를 누르면 문서 속 자리를 봅니다. PDF는 새 탭에서 그 쪽으로 열리고, 쪽 번호가 없는 HWP는 그림 앞뒤 본문을 보여 줍니다.
- 라벨은 위치별로 기록합니다. OCR 벤치마크는 합친 라벨의 1·2 위치를 사용하며, 01은 벤치마크가 저장한 OCR 텍스트를 읽습니다.

### 실행 — 저장소 최상위에서

1. 그림 꺼내기: `.venv\Scripts\python -m frontend.ocr_select.extract` (macOS: `.venv/bin/python`). `config.yaml`의 `paths.input`(기본 `data/rfp.zip`)을 01과 같은 함수로 읽습니다. 당시 측정은 문서 100개에 1분 남짓 걸렸습니다.
2. 화면 열기: 실행기를 더블클릭하고 `설정` → `OCR 이미지 라벨링`을 누릅니다.
3. 묶음 고르기: 상단 바에서 맡은 `묶음 1` ~ `묶음 5`를 누릅니다. 카드를 문서 이름 · 문서 안 위치 순서로 세워 다섯으로 고르게 자르므로(당시 209 · 209 · 209 · 209 · 208곳) 같은 `data/rfp.zip`으로 extract 했다면 누구 컴퓨터에서나 같은 묶음입니다. 고른 묶음은 주소(`?batch=2`)에 남아 새로고침해도 그대로입니다.
4. 결과 내보내기: 다 매기면 상단 바의 `결과 내보내기`를 눌러 `ocr_labels_batchN.jsonl`을 내려받고, 합치는 사람에게 보냅니다. 저장 중인 라벨이 있으면 저장이 끝날 때까지 이 버튼이 잠기고, 진행 수는 저장을 마친 라벨만 셉니다.
5. 합치기 (한 사람): 받은 파일을 모두 넘겨 `.venv\Scripts\python -m frontend.ocr_select.merge ocr_labels_batch1.jsonl ocr_labels_batch2.jsonl ...`를 실행합니다. 묶음마다 매긴 수와 빠진 위치 수를 출력하고 `artifacts/ocr_labels/merged_labels.jsonl`에 씁니다. 같은 위치를 두 사람이 매겼으면 `labelled_at`이 늦은 라벨이 남습니다.

### 결과 — `artifacts/ocr_labels/`

- `images/<그림 해시>.<확장자>`: 꺼낸 그림. 같은 바이트의 그림은 파일 하나입니다. extract를 다시 실행하면 이 폴더만 새로 만듭니다.
- `images.jsonl`: 서로 다른 그림 한 줄씩 — `image_sha256`, `file`, `viewable`, `reason`, `occurrences`(위치마다 `doc_id` · `source` · `document_sha256` · `format`, HWP는 `image_name` · `marker_start` · `repeated_occurrences`, PDF는 `page` · `image_index` · `xref` · `bbox_points` — CRAFT 기록과 같은 이름). 문서에 들어 있지만 본문에 `[IMAGE]` 표시가 없는 HWP 그림(쪽에 놓이지 않은 그림 등)은 `marker_start`가 `null`이고, 저장 OCR 결과가 있으면 01은 문서 끝에 설명을 넣습니다. CRAFT 선별 경로는 이 그림을 보지 않습니다.
- `labels.jsonl`: 라벨을 누를 때마다 `{image_sha256, label, labelled_at, occurrences}` 한 줄을 덧붙입니다. `occurrences`에는 매긴 위치 하나가 들어갑니다. 다시 매긴 라벨도 새 줄이고, 위치마다 마지막 줄이 지금 라벨입니다. extract를 다시 실행해도 지우지 않습니다.
- `merged_labels.jsonl`: 합친 결과. 매긴 위치마다 한 줄 — `labels.jsonl`과 같은 모양에 `batch`(묶음 번호)가 더해집니다. 내려받는 `ocr_labels_batchN.jsonl`도 같은 모양입니다.

## OCR 결과 검토 화면

저장된 OCR 결과를 사람이 확인하는 화면입니다(`설정` → `OCR 결과 검토`, `http://localhost:5173/review.html`).

- 저장된 캡션 391개 위치를 그림 해시로 묶어 서로 다른 그림 320장을 한 장씩 검토합니다.
- 과거 논리 경로 `data/ocr_captions.jsonl`은 공통 로더가 무시된 `artifacts/local_inputs/ocr_captions.jsonl`로 연결합니다. 파일이 없으면 로컬 Git에서 복원하며, 얕은 clone에는 소유자가 제공한 비공개 묶음이 필요합니다 — [로컬 평가 입력과 OCR 캡션 복원](evaluation.md#로컬-평가-입력과-ocr-캡션-복원).
- 왼쪽에는 `artifacts/ocr_labels/images/`의 원본, 오른쪽에는 저장된 OCR 텍스트를 Markdown 표 · 제목 · 목록으로 표시합니다. 엔진 · 이미지 유형과 모든 등장 위치(문서 이름, PDF 쪽 또는 HWP 그림 이름 · 표시 위치)를 함께 보여 줍니다.
- 문서 · 이미지 유형 · 엔진 · 판정 상태(미검토 포함)로 거르고, 이전/다음 버튼 또는 ← → 키로 이동합니다.

판정 저장 방식은 다음과 같습니다.

- `OK` · `일부 틀림` · `틀림`을 누르면 `artifacts/ocr_labels/reviews.jsonl`에 `{image_sha256, transcription_sha256, verdict, reviewed_at}` 한 줄을 덧붙입니다.
- `transcription_sha256`은 OCR 텍스트 · 엔진 · 이미지 유형의 해시입니다. `verdict` 값은 `ok` · `partly_wrong` · `wrong`이며, 같은 그림과 현재 OCR 텍스트에 매긴 마지막 판정이 표시됩니다.
- 본문 · 엔진 · 이미지 유형이 바뀌면 미검토로 표시하고, 이전 결과를 띄운 화면에서 저장하면 새로고침 안내와 함께 거부합니다.
- 해시가 없는 이전 판정은 파일에 보존하지만 미검토로 표시하므로 다시 검토해야 합니다. 새로고침해도 같은 OCR 텍스트에 저장한 판정은 유지됩니다.
- OCR 텍스트는 읽기 전용이며 OCR · VLM · LLM을 호출하지 않습니다. 판정은 01 전처리나 청킹에 반영하지 않고 라벨링 화면과 별도로 보관합니다.
