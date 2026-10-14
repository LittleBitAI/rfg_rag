# golden_pipeline — 골든 데이터 파이프라인 기반

평가용 골든 질문·답변을 주제별로 만들고 검증해 출시하기 위한 패키지입니다.
③ 검증 파이프라인에 속하고 담당자도 같지만, `rag/validation/validation.py` 와는 일부러 분리했습니다
(`CLAUDE.md` · `AGENTS.md` 4절).
지금은 항목 스키마, 주제별 저장 규약, run·버전·상태 모델, 출력 경로 보호와
v11 패키지를 읽기만 하는 근거 어댑터를 담습니다. 생성, 검증, 자기 개선, 실행기는 이후 단계에서 붙습니다.

- `rag/` 에서 아무것도 import 하지 않고, `rag/`·`artifacts/`·`data/`·`eval/` 에 쓰지 않습니다.
- 표준 라이브러리만 씁니다 (`requirements.txt` 변경 없음). API 호출이 없습니다.

## 구성

| 파일 | 내용 |
|---|---|
| `schema.py` | 항목 스키마와 검증 (`validate_item`) |
| `state.py` | 상태 전이와 전이 기록 (`transition`) |
| `storage.py` | run · release 저장, 공유 카탈로그, 출력 경로 보호 (`write_run`, `write_release`, `guard`) |
| `evidence.py` | v11 근거 어댑터: 패키지 SHA 고정, 청크 → 요소 → 레코드 → 원문 단위 연결, 근거 단위별 eligible / held 판정 (`run`) |
| `configs/` | run 설정 파일. run 마다 파일별 SHA-256 이 매니페스트에 남습니다 |
| `prompts/` | 생성·검증 프롬프트 파일. run 마다 파일별 SHA-256 이 매니페스트에 남습니다 |
| `outputs/` | 모든 출력 (git 에서 제외, `.gitignore`) |

## 항목 스키마

항목, 근거 참조, `location`, `state_history` 의 각 전이는 아래 필드를 정확히 가져야 합니다.
빠진 필드도, 선언되지 않은 필드도 `SchemaError` 입니다.

| 필드 | 값 |
|---|---|
| `candidate_id` · `run_id` | 비어 있지 않은 문자열 |
| `parent_candidate_id` | 다시 만든 항목이면 원래 항목 id, 아니면 `null` |
| `method` | `A` · `B` · `C` |
| `primary_topic` | 정확히 하나: `numeric` · `table` · `condition` · `comparison` · `multi_hop` |
| `secondary_tags` | 위 주제 중 0개 이상. `primary_topic` 은 다시 넣을 수 없습니다 |
| `question` · `answer` | 비어 있지 않은 문자열 |
| `evidence` | 근거 참조 1개 이상 (아래 표) |
| `generator_version` · `prompt_version` | 문자열 |
| `validator_version` | `candidate` 일 때만 `null` 일 수 있음 |
| `state` · `state_history` | 상태와 전이 기록 (아래 상태 모델) |

근거 참조(`evidence[]`)의 필드는 모두 있어야 합니다. 해당 없으면 `null` 이나 빈 리스트로 둡니다.

| 필드 | 값 |
|---|---|
| `doc_sha` | 원문 문서 SHA-256 |
| `chunk_id` · `element_id` · `record_id` | v11 청크 · 요소 · 레코드 id |
| `location` | `{"kind": "char", "start", "end"}` 또는 `{"kind": "table", "grid", "row", "cell"}` |
| `location.grid` | `logical_restored` (마크다운 논리 행으로 복원한 표) · `original_verified` (원본 격자를 확인한 표) · `original_reference` (검증되지 않은 원본 격자 참고 파일의 셀). 세 종류는 섞지 않습니다 |
| `page` | 1 이상의 정수 또는 `null` (v11 청크는 대부분 쪽 번호가 없음) |
| `requirement_ids` | `SFR-001` 같은 요구사항 id 리스트 |
| `image_sha` · `ocr_scope` | 이미지 근거일 때 둘 다: SHA-256 과 `full_visible_text` (보이는 글자 전체 검증) · `partial_region` (선언한 영역만 검증) · `hold` (검증 범위 없음). 아니면 둘 다 `null` |

## 상태 모델

| 현재 상태 | 갈 수 있는 상태 |
|---|---|
| `candidate` (후보) | `auto_validated` · `held` · `rejected` |
| `auto_validated` (자동 검증 통과) | `released` · `held` · `rejected` |
| `held` (보류, 사람 검토) | `released` (승인) · `rejected` |
| `rejected` (거절) | 없음 |
| `released` (출시 골든) | 없음 |

`rejected` 와 `released` 는 끝 상태입니다. 허용되지 않은 전이는 `StateError` 로 막고,
허용된 전이는 `{from, to, reason, at}` 을 `state_history` 에 덧붙인 새 항목을 돌려줍니다.
`candidate` 를 떠나는 전이는 검증기가 하므로 `transition(item, to, reason, validator_version="...")` 처럼
검증기 버전을 반드시 받아 `validator_version` 에 남기고, 그 뒤의 전이는 이 값을 받지 않습니다.
`validate_item` 은 `state_history` 가 `candidate` 에서 시작해 허용된 전이만 거쳐 지금 `state` 에 닿는지,
전이마다 이유와 ISO-8601 UTC 시각(`at`)이 있는지 확인합니다. 그래서 `state` 만 고쳐 검증이나 사람 검토를 건너뛸 수 없습니다.

## 저장 규약

```
golden_pipeline/outputs/
  catalog.jsonl                         모든 주제가 함께 쓰는 카탈로그
  goldens/{topic}/
    runs/{A|B|C}/{run_id}/
      candidates.jsonl                  run 의 모든 항목
      accepted.jsonl                    auto_validated
      review.jsonl                      held (사람 검토 대상)
      rejected.jsonl                    rejected
      manifest.json                     설정·프롬프트 파일별 SHA-256, 코드 커밋, 개수
    failure_memory/{method}_{run_id}.jsonl   거절된 항목과 거절 이유
    releases/{version}/
      golden.jsonl                      released 항목
      manifest.json                     개수, golden.jsonl SHA-256, 원본 run, 코드 커밋
```

- 이미 있는 `run_id` 나 `version` 은 덮어쓰지 않고 `FileExistsError` 로 거절합니다.
- 카탈로그는 항목마다 한 줄(`candidate_id`, 소유 주제, 근거 묶음 키)을 남깁니다.
  같은 `candidate_id` 는 다시 등록할 수 없고, 같은 근거 묶음은 다른 주제가 가질 수 없습니다.
  근거 묶음 키는 근거 참조들의 SHA-256 이라 순서와 무관합니다.
- 출시본에는 같은 주제로 카탈로그에 등록된 `released` 항목만 들어갑니다.
  출시 항목은 카탈로그가 가리키는 run 의 `candidates.jsonl` 기록과 같아야 하고, 상태만 더 나아갈 수 있습니다
  (`state_history` 는 그 기록에 이어 붙인 것, `validator_version` 은 비어 있던 경우에만 새로 채움).
  질문·답·근거·방법·run 을 바꿔 끼우면 `CatalogError` 로 거절합니다.
- `golden_pipeline/outputs` 밖(`data/`, `artifacts/`, `eval/` 포함)으로 가는 경로는 `OutputPathError` 로 거절합니다.

## v11 근거 어댑터

`evidence.py` 는 `data/RFP_Preprocessing_Final_v11_Team` 을 읽기만 합니다.
패키지를 고치지 않고, 패키지의 `verify_package.py` · `load_retriever_inputs.py` 를 import 하거나 실행하지 않으며, OCR 을 다시 돌리지 않습니다.
`artifacts/docs.jsonl` · `artifacts/chunks.jsonl` 은 입력으로 쓰지 않습니다.

```
python -m golden_pipeline.evidence <run_id> "<내려받은 압축>/RFP_Preprocessing_Final_v11_Team/RFP_Preprocessing_Final_v11_Team"
```

실행 순서와 멈추는 조건은 다음과 같습니다.

1. 두 사본(`data/` 와 내려받은 압축의 안쪽 폴더)의 `manifest.json`, `final_chunks/elements/records.jsonl`,
   `validation/source_status_merged.csv`, `validation/복구표_원본그리드_참고.jsonl` 을 SHA-256 으로 해시합니다.
   두 사본이 다르거나 `manifest.json` 의 `files` 선언과 다르면 멈춥니다.
2. 파일에서 센 문서 · 레코드 · 요소 · 청크 수와 검색 입력 청크 수를 `manifest.json` 과 비교하고, 다르면 멈춥니다.
   검색 입력에서 빠지는 청크는 본문이 `[IMAGE]` 표시뿐인 것이며, id 와 이유를 매니페스트에 남깁니다.
3. 근거 단위를 만들고 단위마다 판정을 남깁니다 (아래).
4. `artifacts/raw` 파일은 SHA-256 이 v11 문서 SHA 와 같을 때만 잇습니다. 이름만 같은 파일은 `unlinked_filename_only` 로 표시하고 잇지 않습니다.

출력은 `golden_pipeline/outputs/evidence/{run_id}/` 에 쓰고, 이미 있는 `run_id` 는 거절합니다.

| 파일 | 내용 |
|---|---|
| `units.jsonl` | 근거 단위. 데이터에서 읽은 연결만 담습니다 |
| `judgments.jsonl` | 단위마다 `eligible` · `held` 판정과 보류 이유. 원본과 따로 둔 판정 기록입니다 |
| `raw_links.jsonl` | `artifacts/raw` 파일별 SHA-256, 연결된 문서 SHA, 상태 |
| `manifest.json` | 고정한 SHA, 개수, 제외 청크, 원본 그리드 파일 판정, raw 연결 수, 단위·판정 수, 코드 커밋 |

근거 단위는 세 종류입니다.

| 단위 | 출처 | `location` |
|---|---|---|
| `chunk:{청크}:{요소}:char:{start}-{end}` | 청크의 글자 span | `char` (요소 `search_text` 기준) |
| `chunk:{청크}:{요소}:row:{행}` | 청크의 표 행 span | `table`, `grid = logical_restored`, `cell = null` |
| `grid:{문서 SHA}:{stream}:{표 컨트롤}:{행}:{열}` | 원본 그리드 참고 파일의 셀 | `table`, `grid = original_reference` |

단위의 필드는 `unit_id`, `doc_sha`, `chunk_id`, `element_id`, `record_id`, `location`, `page`, `raw_start`, `raw_end`,
`requirement_ids`, `image_sha`, `ocr_scope`, `source_units`, `ids_linked`, `meaning_verified` 입니다.
`ids_linked` (ID 가 모두 이어짐)와 `meaning_verified` (원문 의미가 검증됨)는 따로 계산하고, 연결만으로 검증이 참이 되지 않습니다.
`eligible` 은 둘 다 참이고 보류 이유가 없을 때뿐입니다.

| 보류 이유 | 조건 |
|---|---|
| 연결 오류 | 요소 · 레코드 id 가 없음, 요소와 레코드의 문서 SHA 가 다름, 레코드 SHA 가 `doc_id` 와 다름, span 이 본문 · 표 밖 |
| `UNVERIFIED` 원문 단위 | `source_status_merged.csv` 에서 이 단위에 걸린 원문 단위 중 하나라도 `UNVERIFIED` |
| 근거 없음 | 이 단위를 덮는 원문 단위가 없음 |
| 같은 사실의 값이 다름 | 청크의 `requirement_key` 가 레코드 · 요소의 `requirement_ids` 에 없음 |
| 이미지 | 이미지 SHA 가 없음, OCR 범위 `hold`, 본문 줄이 검증 전사(`verified_region_text`) 밖 |
| 원본 그리드 미검증 | 원본 그리드 참고 파일의 모든 셀 |

- 청크 단위의 원문 단위는 그 요소에 걸리고 청크 id 가 이 청크이거나 비어 있는 것입니다. 원문 단위에 표 행 번호가 없어서 표 행은 요소 · 청크 단위로 판단합니다.
- 그리드 셀의 원문 단위는 셀 텍스트 레코드의 `source_unit_id` 로 바로 찾습니다.
- 이미지 OCR 은 `source_status_merged.csv` 의 분모에 들어가지 않으므로 레코드의 `image_source.scope` 로만 판단합니다.
  `FULL_VISIBLE_TEXT` → `full_visible_text`, `PARTIAL_REGION(S)` → `partial_region`, 범위 선언이 없으면 `hold` 입니다.
- 원본 그리드 참고 파일은 레코드에 검증 상태 필드가 없고 패키지 노트북 7절이 원본 구조를 증명하지 않는 참고 근거라고 적어,
  검증되지 않은 것으로 매니페스트 `original_grid_file` 에 기록합니다.

2026-10-14 실제 v11 실행 결과 (두 사본 SHA 일치):

| 항목 | 값 |
|---|---|
| 개수 | 문서 98 · 레코드 23,761 · 요소 26,040 · 청크 18,992 · 검색 입력 청크 18,984 (`manifest.json` 과 같음) |
| 제외 청크 | 8개, 모두 본문이 `[IMAGE]` 표시뿐 |
| `artifacts/raw` | 100개 모두 SHA 로 연결 (문서 98개, 두 파일은 다른 파일과 바이트가 같음), 이름만 같은 파일 0 |
| 근거 단위 | 136,581 (청크 86,995 · 그리드 셀 49,586), `eligible` 64,904 · `held` 71,677 |
| 이미지 | v11 검증 OCR 12개는 범위 안이라 검증, 범위 선언이 없는 7개(v10 OCR 1 · 이미지 패널 6)는 `hold` |

## 테스트

테스트는 `tests/golden/` 에 있어 저장소 게이트(`.venv\Scripts\python -m pytest -q tests`)가 함께 돌립니다.
이 패키지만 돌리려면:

```
python -m pytest -q tests/golden
```

`.env` 키와 네트워크 없이 돌아가고, 출력은 임시 폴더에 씁니다.
