# golden_pipeline — 골든 데이터 파이프라인 기반

평가용 골든 질문·답변을 주제별로 만들고 검증해 출시하기 위한 패키지입니다.
③ 검증 파이프라인에 속하고 담당자도 같지만, `rag/validation/validation.py` 와는 일부러 분리했습니다
(`CLAUDE.md` · `AGENTS.md` 4절).
지금은 항목 스키마, 주제별 저장 규약, run·버전·상태 모델, 출력 경로 보호,
v11 패키지를 읽기만 하는 근거 어댑터, 분포 계획과 A · B · C 후보 생성을 담습니다.
검증, 자기 개선, 실행기는 이후 단계에서 붙습니다.

- `rag/` 에서 아무것도 import 하지 않고, `rag/`·`artifacts/`·`data/`·`eval/` 에 쓰지 않습니다.
- 표준 라이브러리만 씁니다 (`requirements.txt` 변경 없음).
- API 를 부르는 코드가 없습니다. 생성은 호출 함수(`client`)를 인자로 받고, 테스트는 가짜 클라이언트만 씁니다.

## 구성

| 파일 | 내용 |
|---|---|
| `schema.py` | 항목 스키마와 검증 (`validate_item`) |
| `state.py` | 상태 전이와 전이 기록 (`transition`) |
| `storage.py` | run · release 저장, 공유 카탈로그, 출력 경로 보호 (`write_run`, `write_release`, `guard`) |
| `evidence.py` | v11 근거 어댑터: 패키지 SHA 고정, 청크 → 요소 → 레코드 → 원문 단위 연결, 근거 단위별 eligible / held 판정 (`run`) |
| `plan.py` | 분포 계획: 주제별 개수 · 문서 범위 · 근거 묶음을 고정한 파일 (`make_plan`, `load_plan`) |
| `generation.py` | 후보 생성: A · B (`generate`), C 가져오기 (`import_c`), 주제 구조 검사 (`check_structure`) |
| `configs/` | 설정 파일. `topics/{topic}.json` 은 주제 명세입니다. run 마다 파일별 SHA-256 이 매니페스트에 남습니다 |
| `prompts/` | 생성 프롬프트. `A/{topic}.txt` 는 A 의 주제 전용, `B.txt` 는 B 의 고정 프롬프트입니다. run 마다 파일별 SHA-256 이 매니페스트에 남습니다 |
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
| `bundle_id` · `context` | 생성에 준 근거 묶음 id 와 생성기에 보낸 컨텍스트 원문 (비어 있지 않은 문자열) |
| `structure` | 주제가 요구하는 구조 (객체, 아래 주제 명세) |
| `generator_version` · `prompt_version` | 문자열. A · B 의 `prompt_version` 은 프롬프트 파일 SHA-256, C 는 `unobserved` |
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
  plans/{plan_id}.json                  분포 계획 (A · B · C 가 함께 읽음)
  goldens/{topic}/
    runs/{A|B|C}/{run_id}/
      candidates.jsonl                  run 의 모든 항목
      accepted.jsonl                    auto_validated
      review.jsonl                      held (사람 검토 대상)
      rejected.jsonl                    rejected 항목, 그리고 항목이 되지 못한 생성 출력 {bundle_id, reason, raw}
      manifest.json                     설정·프롬프트 파일별 SHA-256, 코드 커밋, 개수, 생성 정보(generation)
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

## 분포 계획

A · B · C 를 같은 조건에서 비교하려고, 주제별 개수 · 문서 범위 · 근거 묶음을 한 파일로 먼저 고정합니다.
API 를 부르지 않습니다.

```
python -m golden_pipeline.plan <plan_id> <근거 어댑터 run_id> --count numeric 20 --count table 20 --max-context-chars 4000
```

1. 근거 어댑터 run 의 `manifest.json` 에 고정된 파일 SHA-256 과 지금 패키지 파일이 같은지 확인하고, 다르면 멈춥니다.
2. `judgments.jsonl` 에서 `eligible` 인 단위만 씁니다. `held` 단위는 어떤 묶음에도 들어가지 않습니다.
   단위 본문은 패키지 `final_elements.jsonl` 에서 읽습니다 (글자 span 은 그 구간, 표 행은 칸을 ` | ` 로 이은 것).
3. 주제 순서(`numeric` → `table` → `condition` → `comparison` → `multi_hop`)대로, 주제 명세의 `pattern` · `table_only` 에 맞는 단위를
   문서마다 패키지 순서로 `bundle_units` 개씩 묶습니다. 컨텍스트가 `--max-context-chars` 를 넘는 묶음은 버립니다.
   한 단위는 한 주제의 묶음에만 들어갑니다 (카탈로그가 같은 근거를 두 주제에 두지 않기 때문).
   표 행이 든 묶음에는 그 표의 머리글 행(논리 표 0행)을 맨 앞에 붙입니다. 열 이름 없이는 칸을 가리킬 수 없기 때문입니다.
   머리글 행이 `eligible` 이 아니거나 앞 주제의 묶음이 이미 가졌으면 그 묶음을 버립니다.
4. 문서를 돌아가며 하나씩 골라 개수를 채웁니다. 모자라면 기준을 낮추지 않고 `planned` 에 실제 개수를 남깁니다.

계획 파일(`outputs/plans/{plan_id}.json`)은 덮어쓰지 않으며, run 은 이 파일의 SHA-256 을 남깁니다.

| 필드 | 값 |
|---|---|
| `evidence_run` · `v11_manifest_sha256` | 근거 어댑터 run 과 v11 `manifest.json` SHA-256 |
| `topic_specs` | 주제 명세 파일별 SHA-256. 생성 때 명세가 바뀌었으면 멈춥니다 |
| `max_context_chars` | 묶음 컨텍스트 글자 수 한도 (A · B 의 입력 한도) |
| `counts` · `planned` · `coverage` | 요청 개수, 실제 묶음 수, 주제별 문서 SHA → 묶음 수 |
| `bundles[]` | `bundle_id`, `topic`, `doc_sha`, `units[]` (`label` `E1`…, `unit_id`, 근거 참조 `ref`, `text`), `context` |

`context` 는 `[E1]\n본문\n\n[E2]\n본문` 형식이며 생성기에 이 문자열을 그대로 보냅니다.

2026-10-14 실제 v11 근거 run(`v11-20261014`)으로 주제마다 20개를 요청한 계획은 약 8초에 만들어졌고,
다섯 주제 모두 20개 묶음을 서로 다른 문서 20개에서 골랐습니다.

## 주제 명세

`configs/topics/{topic}.json` 은 `version`, `requires` (프롬프트에 넣는 요구 설명), `structure` (출력 구조 필드와 설명),
묶음 선택 규칙 `pattern` · `table_only` · `bundle_units` 를 가집니다.
출력의 `structure` 는 명세의 필드를 정확히 가져야 하고, 주제마다 아래를 지켜야 후보가 됩니다.
값은 근거에 적힌 그대로여야 합니다 (공백 · 쉼표 차이만 허용).
수로 시작하거나 끝나는 값은 수 전체가 맞아야 합니다. 예를 들어 조건 `1년 이내` 는 `11년 이내` 에 맞지 않습니다.

| 주제 | `structure` | 후보가 되는 조건 |
|---|---|---|
| `numeric` | `value` · `unit` | 값에 숫자가 있고, (`value`, `unit`) 이 답과 인용한 근거에 모두 수 · 단위 쌍으로 있음. 쌍은 명세 `pattern` 의 단위 목록으로 원문에서 읽으므로 부호 · 수 · 단위가 통째로 맞아야 합니다 (`30,000,000원` ≠ `130,000,000원`, `-130,000,000원` ≠ `130,000,000원`, `12개` ≠ `12개월`, `12개월이다` 는 `12` · `개월`). 범위 표시나 다른 수 뒤의 수(`10~12개월`), 목록 밖의 더 긴 단위로 이어지는 단위(`5%p`, `5%포인트`, `3개년`, `MB/s`)는 쌍이 아닙니다. 목록에 없는 단위나 `3천만원` 같은 한글 수도 쌍이 없어 거절됩니다. 값 없이 설명만 하는 답은 `유형 불일치` 로 거절 |
| `table` | `row` · `column` | 인용한 근거에 표 행이 있고, 행 · 열 이름이 근거에 있음 |
| `condition` | `condition` | 조건 · 예외 문구가 근거에 있음 |
| `comparison` | `entities` | 서로 다른 대상 2개 이상, 각각 근거에 있음 |
| `multi_hop` | 없음 (`{}`) | 인용한 근거 단위가 2개 이상 |

## 후보 생성

A · B · C 는 같은 출력 계약과 같은 검사를 거쳐 같은 `write_run` 으로 저장됩니다.
모든 출력은 `candidate` 상태이고, 이 단계의 어떤 코드도 `auto_validated` · `released` 로 옮기지 않습니다.
`accepted.jsonl` · `review.jsonl` 은 비어 있습니다.

출력 한 행은 정확히 `question`, `answer`, `evidence` (묶음의 근거 라벨 리스트), `structure`, `secondary_tags` 를 가집니다 (C 는 `bundle_id` 도).
아래 중 하나라도 어기면 항목이 되지 않고 원문 · 이유와 함께 `rejected.jsonl` 로 갑니다:
JSON 아님, 필드 불일치, 계획에 없는 묶음(C), 묶음에 없는 · 겹치는 라벨, 항목 스키마 위반 (`스키마: ...`), 주제 구조 위반 (`유형 불일치: ...`),
카탈로그에서 다른 주제가 이미 가진 근거 묶음 인용 (`근거 묶음이 이미 ... 주제 소유입니다`).
항목은 인용한 단위의 근거 참조, `bundle_id`, 보낸 컨텍스트 원문(`context`)을 가집니다.

| 방식 | 입력 | 프롬프트 | 기록 |
|---|---|---|---|
| A (첫 생성) | `generate("A", topic, plan_id, run_id, config, client)` | `prompts/A/{topic}.txt` | 실패 기록을 읽지 않습니다 (자기 개선은 다음 단계) |
| B (고정 프롬프트) | `generate("B", ...)` | `prompts/B.txt` 하나 | 실패 기록을 읽지 않습니다. 같은 모델 · 계획 · 주제 명세를 받고 프롬프트만 고정 |
| C (가져오기) | `import_c(topic, plan_id, run_id, exports, sidecar)` | 관측 불가 → `unobserved` | 사람이 웹 환경에서 받아 내보낸 JSONL 파일들과 관측 기록 |

A · B 는 묶음마다 한 번 `client(model=..., messages=[system: 프롬프트, user: context])` 를 부릅니다.
`client` 는 `{"model", "text", "input_tokens", "output_tokens"}` 를 돌려주며, `model` 은 API 응답이 알려 준 이름이어야 합니다.

`run_id` 가 경로 한 칸 이름이 아니거나 이미 쓴 run 이면 호출 전에 멈춥니다.
run 설정(JSON 파일)은 아래 다섯 값을 모두 가져야 하고, 빠지면 호출 전에 멈춥니다. 기본값이 없으므로 설정 없이 유료 호출이 나가지 않습니다.

| 키 | 값 |
|---|---|
| `model` | 요청할 모델 이름 |
| `max_calls` | 최대 호출 수 (1 이상의 정수) |
| `budget_usd` | 총예산 (0 보다 큼) |
| `usd_per_million_input_tokens` · `usd_per_million_output_tokens` | 단가. 응답 토큰 수로 비용을 계산합니다 |

호출 수가 `max_calls` 에 닿거나 누적 비용이 `budget_usd` 에 닿으면 남은 묶음을 부르지 않고 `status` 에 `call_cap` · `budget` 을 남깁니다.
예산은 호출 사이에만 보므로 마지막 호출 하나만큼 넘을 수 있습니다.

C 의 sidecar(JSON)는 `model_label` (화면에 보인 모델 표시), `run_date`, `provided_files`, `tool_use`, `input_limits` 만 받습니다.
없거나 비어 있는 값은 `unobserved` 로 남기고, API 모델과 같다고 추정하지 않습니다. 다른 필드가 있으면 멈춥니다.

run 매니페스트의 `generation`:

| 필드 | A · B | C |
|---|---|---|
| `plan_id` · `plan_sha256` · `evidence_run` · `v11_manifest_sha256` · `topic_spec_sha256` | 같음 | 같음 |
| `bundle_ids` · `document_scope` | 실제로 보낸 묶음과 그 문서 SHA | 행이 가리킨 묶음과 그 문서 SHA |
| 모델 | `model_requested` (설정), `model_reported` (응답) | `model.observed_label` (관측값 또는 `unobserved`) |
| 프롬프트 · 설정 | `prompt_file`, `prompt_sha256`, `run_config`, `run_config_sha256` | `observed`, `sidecar_sha256`, `exports` (파일별 SHA-256) |
| `input_limits` | `{"max_context_chars": ...}` | sidecar 의 관측값 또는 `unobserved` |
| 호출 | `status`, `cost_usd`, `calls[]` (묶음, 응답 모델, 토큰) | 없음 (토큰 · 비용을 0 으로 채우지 않음) |

LLM 출력은 같은 입력에도 달라질 수 있어 결정성을 주장하지 않습니다.
대신 보낸 컨텍스트, 프롬프트 · 설정 · 계획 해시, 응답 모델을 남겨 무엇을 넣어 무엇이 나왔는지 추적합니다.

## 테스트

테스트는 `tests/golden/` 에 있어 저장소 게이트(`.venv\Scripts\python -m pytest -q tests`)가 함께 돌립니다.
이 패키지만 돌리려면:

```
python -m pytest -q tests/golden
```

`.env` 키와 네트워크 없이 돌아가고, 출력은 임시 폴더에 씁니다.
