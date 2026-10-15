# golden_pipeline — 골든 데이터 파이프라인

평가용 골든 질문·답변을 주제별로 만들고 검증해 출시하기 위한 패키지입니다.
③ 검증 파이프라인에 속하고 담당자도 같지만, `rag/validation/validation.py` 와는 일부러 분리했습니다
(`CLAUDE.md` · `AGENTS.md` 4절).
항목 스키마, 주제별 저장 규약, run·버전·상태 모델, 출력 경로 보호,
v11 패키지를 읽기만 하는 근거 어댑터, 분포 계획과 A · B · C 후보 생성, 독립 검증 · 난도 판정 · 출시,
A 만의 자기 개선(실패 기록과 round), 이 모두를 부르는 CLI 와 두 실행기, A · B · C 비교 보고서를 담습니다.

- `rag/` 에서 아무것도 import 하지 않고, `rag/`·`artifacts/`·`data/`·`eval/` 에 쓰지 않습니다. 노트북과 질문 화면 서버도 실행하지 않습니다.
- 표준 라이브러리와, numeric 검사의 형태소 분석에 `kiwipiepy`, API 호출에 `openai` · `python-dotenv` 를 씁니다 (모두 이미 `requirements.txt` 에 있어 변경 없음).
- API 를 부르는 곳은 `cli.py` 의 `api_client` 하나입니다. 생성 · 검증 모듈은 호출 함수(`client`)를 인자로 받고, 테스트는 가짜 API 만 씁니다.

## 구성

| 파일 | 내용 |
|---|---|
| `schema.py` | 항목 스키마와 검증 (`validate_item`) |
| `state.py` | 상태 전이와 전이 기록 (`transition`) |
| `storage.py` | run · release 저장, 공유 카탈로그, 출력 경로 보호 (`write_run`, `write_release`, `guard`) |
| `evidence.py` | v11 근거 어댑터: 패키지 SHA 고정, 청크 → 요소 → 레코드 → 원문 단위 연결, 근거 단위별 eligible / held 판정 (`run`) |
| `plan.py` | 분포 계획: 주제별 개수 · 문서 범위 · 근거 묶음을 고정한 파일 (`make_plan`, `load_plan`) |
| `generation.py` | 후보 생성: A · B (`generate`), C 가져오기 (`import_c`), 주제 구조 검사 (`check_structure`) |
| `validation.py` | 독립 검증 (`validate`), 난도 판정 (`difficulty`), 출시 (`release`) |
| `improvement.py` | A 의 자기 개선: round 반복 (`improve`), 실패 기록 (`record_failures`), 관련 실패 찾기 (`related_failures`) |
| `report.py` | A · B · C 비교 보고서 (`compare`, `write_report`, `render`) |
| `cli.py` | 하나뿐인 CLI (`python -m golden_pipeline.cli`)와 OpenAI 호출 (`api_client`) |
| `golden.cmd` · `golden.command` | Windows · macOS 실행기. 둘 다 받은 인자를 그대로 `cli.py` 에 넘깁니다 |
| `configs/` | 설정 파일. `topics/{topic}.json` 은 주제 명세입니다. run 마다 파일별 SHA-256 이 매니페스트에 남습니다 |
| `prompts/` | 생성 프롬프트. `A/{topic}.txt` 는 A 의 주제 전용, `B.txt` 는 B 의 고정 프롬프트입니다. run 마다 파일별 SHA-256 이 매니페스트에 남습니다 |
| `outputs/` | 모든 출력 (git 에서 제외, `.gitignore`) |

## 실행기와 CLI

Windows 는 `golden_pipeline\golden.cmd`, macOS 는 `golden_pipeline/golden.command` 를 씁니다.
두 실행기는 받은 인자를 모두 같은 CLI(`python -m golden_pipeline.cli`)에 넘기기만 하고, 다른 것은 실행하지 않습니다.
저장소의 `.venv` 로 돌고, 지금 폴더를 바꾸지 않으므로 `--export` 같은 상대 경로는 명령을 친 폴더 기준입니다.
인자 없이 열면(더블클릭) 명령 목록을 보여 줍니다. 아래 예는 Windows 이고, macOS 는 `golden.cmd` 를 `./golden_pipeline/golden.command` 로 바꿉니다.

| 명령 | 하는 일 | API 호출 |
|---|---|---|
| `evidence` | v11 근거 어댑터 run (아래 v11 근거 어댑터) | 없음 |
| `plan` | 주제 · 목표 개수를 정한 분포 계획 (아래 분포 계획) | 없음 |
| `run` | A: 자기 개선 loop (생성 → 검증 → 실패 기록을 round 마다). B: 고정 프롬프트 생성만 | 유료 |
| `import` | C 가져오기 | 없음 |
| `audit` | B · C run 의 독립 검증. A 는 loop 안에서 검증합니다 | 유료 |
| `resume` | 끊긴 A loop 잇기, 또는 한도에 닿은 B · C 검증의 pending 후보 검증 | 유료 |
| `release` | 검증한 run 들을 쓸모 판정을 거쳐 출시본으로 (아래 출시) | 유료 |
| `report` | A · B · C 비교 보고서 (아래 비교 보고서) | 없음 |

```
golden_pipeline\golden.cmd evidence v11-20261014 "<내려받은 압축>\RFP_Preprocessing_Final_v11_Team\RFP_Preprocessing_Final_v11_Team"
golden_pipeline\golden.cmd plan p1 v11-20261014 --count numeric 20 --count table 20 --max-context-chars 4000

golden_pipeline\golden.cmd run --topic numeric --method A --plan p1 --id a1 --model <모델> --reasoning-effort low --price <입력 단가> <출력 단가> --max-calls 200 --budget 5 --max-rounds 3 --validator-model <모델> --validator-reasoning-effort high --validator-price <입력 단가> <출력 단가>
golden_pipeline\golden.cmd run --topic numeric --method B --plan p1 --id b1 --model <모델> --reasoning-effort low --price <입력 단가> <출력 단가> --max-calls 40 --budget 2
golden_pipeline\golden.cmd audit --topic numeric --method B --id b1 --model <모델> --reasoning-effort high --price <입력 단가> <출력 단가> --max-calls 80 --budget 2
golden_pipeline\golden.cmd import --topic numeric --plan p1 --id c1 --export c_numeric.jsonl --sidecar c_sidecar.json
golden_pipeline\golden.cmd audit --topic numeric --method C --id c1 --model <모델> --reasoning-effort high --price <입력 단가> <출력 단가> --max-calls 80 --budget 2

golden_pipeline\golden.cmd resume --topic numeric --method A --id a1
golden_pipeline\golden.cmd resume --topic numeric --method B --id b1 --max-calls 40 --budget 1

golden_pipeline\golden.cmd release --topic numeric --version v1 --run A:a1-r1 --run A:a1-r2 --model <모델> --reasoning-effort high --price <입력 단가> <출력 단가> --max-calls 400 --budget 2
golden_pipeline\golden.cmd plan p2 v11-20261014 --count numeric 20 --max-context-chars 4000 --skip-plan p1
golden_pipeline\golden.cmd report --topic numeric --id cmp1 --a a1 --b b1 --c c1
```

- 주제(`--topic`)는 명령마다 하나, 목표 개수는 `plan` 의 `--count` 로 정합니다. A · B · C 는 같은 계획을 받아야 견줄 수 있습니다.
- 유료 명령은 모델(`--model`), 추론 강도(`--reasoning-effort`, 예: `low` · `medium` · `high`), 단가(`--price`, USD / 100만 토큰), 최대 호출 수(`--max-calls`), 총예산(`--budget`, USD)을
  모두 받아야 시작합니다. 하나라도 빠지면 API 클라이언트를 열기 전에 멈춥니다. 기본값은 없습니다.
  A 는 최대 round 수(`--max-rounds`)와 검증기 모델 · 추론 강도 · 단가(`--validator-model`, `--validator-reasoning-effort`, `--validator-price`)도 받고,
  호출 수 · 예산은 loop 전체(생성 + 검증)의 한도입니다.
- 키는 저장소 `.env` 의 `OPENAI_API_KEY` 입니다. 명령 하나 동안 OpenAI 클라이언트 하나를 열어 생성기 · 검증기가 함께 쓰고 명령이 끝나면 닫습니다.
  기록하는 모델 이름은 요청한 이름이 아니라 API 응답이 알려 준 이름입니다.
- 플래그로 받은 설정은 `outputs/` 아래 임시 파일로 넘기고 지웁니다. 내용과 SHA-256 은 run 매니페스트 · `validation.json` · loop `start.json` 에 남습니다.
- `resume --method A` 는 `start.json` 에 고정된 설정 · 계획으로 loop 를 잇고 한도를 받지 않습니다. 이미 끝난(`report.json` 이 있는) loop 는 잇지 않습니다.
- `resume --method B|C` 는 아래 독립 검증의 "이어서 검증" 입니다. 모델 · 추론 강도 · 단가는 앞 검증 기록의 것을 그대로 쓰고, 이번에 쓸 `--max-calls` · `--budget` 만 받습니다.
- `release` 의 A run 은 loop 의 round run(`{loop_id}-r{n}`)입니다.

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
| `difficulty` | `easy` · `medium` · `hard`. 검증기가 `validator_version` 과 함께 남기며, 둘은 함께 있거나 함께 `null` 입니다 |
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
| `candidate` (후보) | `auto_validated` · `rejected` |
| `auto_validated` (자동 검증 통과) | `released` · `rejected` |
| `rejected` (거절) | 없음 |
| `released` (출시 골든) | 없음 |

`rejected` 와 `released` 는 끝 상태입니다. 애매한 항목을 사람이 볼 보류 상태는 없습니다. 검증은 통과나 거절로만 끝납니다. 허용되지 않은 전이는 `StateError` 로 막고,
허용된 전이는 `{from, to, reason, at}` 을 `state_history` 에 덧붙인 새 항목을 돌려줍니다.
`candidate` 를 떠나는 전이는 검증기가 하므로 `transition(item, to, reason, validator_version="...", difficulty="...")` 처럼
검증기 버전과 난도를 반드시 받아 남기고, 그 뒤의 전이는 이 값들을 받지 않습니다.
`validate_item` 은 `state_history` 가 `candidate` 에서 시작해 허용된 전이만 거쳐 지금 `state` 에 닿는지,
전이마다 이유와 ISO-8601 UTC 시각(`at`)이 있는지 확인합니다. 그래서 `state` 만 고쳐 검증을 건너뛸 수 없습니다.

## 저장 규약

```
golden_pipeline/outputs/
  catalog.jsonl                         모든 주제가 함께 쓰는 카탈로그
  plans/{plan_id}.json                  분포 계획 (A · B · C 가 함께 읽음)
  goldens/{topic}/
    runs/{A|B|C}/{run_id}/
      candidates.jsonl                  run 의 모든 항목
      accepted.jsonl                    auto_validated
      rejected.jsonl                    rejected 항목, 그리고 항목이 되지 못한 생성 출력 {bundle_id, reason, raw}
      manifest.json                     설정·프롬프트 파일별 SHA-256, 코드 커밋, 개수, 생성 정보(generation)
      validation.json                   검증 기록: 검증기 버전, 난도 규칙, 호출, 상태 파일별 SHA-256 (run 마다 한 번)
      validation-{n}.json               이어서 검증한 기록 (B · C 의 pending 후보, n = 2, 3, ...)
    failure_memory/A_{run_id}.jsonl     A run 의 실패 코드 · 참조 · 예방 규칙 · 규칙 버전 (질문 · 답은 넣지 않음)
    failure_memory/screen_{version}.jsonl  출시에서 규칙 검사 · 쓸모 판정이 뺀 A 항목의 같은 기록 (record_screen)
    loops/{loop_id}/
      start.json                        처음 받은 loop 설정 · 계획 id · 계획 SHA-256 · 통과 기준 (이어 돌 때 같아야 함)
      calls.jsonl                       돌아온 생성 · 검증 호출마다 한 줄: 모델 · 토큰 · 비용 (끊긴 run 의 호출 포함)
      r{n}-generator.json · r{n}-validator.json   round 의 run 설정 (남은 호출 수 · 예산)
      report.json                       멈춘 이유, round 별 상태 · policy, 호출 · 비용, 목표 대비 모자란 수, 기준 해시
    releases/{version}/
      golden.jsonl                      released 항목
      manifest.json                     개수, golden.jsonl SHA-256, 원본 run 과 그 파일별 SHA-256, 코드 커밋
    reports/{report_id}.json            A · B · C 비교 보고서
```

- 이미 있는 `run_id` 나 `version`, 보고서 id 는 덮어쓰지 않고 `FileExistsError` 로 거절합니다.
- 카탈로그는 항목마다 한 줄(`candidate_id`, 소유 주제, 근거 묶음 키)을 남깁니다.
  같은 `candidate_id` 는 다시 등록할 수 없고, 같은 근거 묶음은 다른 주제가 가질 수 없습니다.
  근거 묶음 키는 근거 참조들의 SHA-256 이라 순서와 무관합니다.
- 출시본에는 같은 주제로 카탈로그에 등록된 `released` 항목만 들어갑니다.
  출시 항목은 카탈로그가 가리키는 run 의 `candidates.jsonl` 기록과 같아야 하고, 상태만 더 나아갈 수 있습니다
  (`state_history` 는 그 기록에 이어 붙인 것, `validator_version` · `difficulty` 는 비어 있던 경우에만 새로 채움).
  질문·답·근거·방법·run 을 바꿔 끼우면 `CatalogError` 로 거절합니다.
- `golden_pipeline/outputs` 밖(`data/`, `artifacts/`, `eval/` 포함)으로 가는 경로는 `OutputPathError` 로 거절합니다.

## v11 근거 어댑터

`evidence.py` 는 `data/RFP_Preprocessing_Final_v11_Team` 을 읽기만 합니다.
패키지를 고치지 않고, 패키지의 `verify_package.py` · `load_retriever_inputs.py` 를 import 하거나 실행하지 않으며, OCR 을 다시 돌리지 않습니다.
`artifacts/docs.jsonl` · `artifacts/chunks.jsonl` 은 입력으로 쓰지 않습니다.

```
golden_pipeline\golden.cmd evidence <run_id> "<내려받은 압축>/RFP_Preprocessing_Final_v11_Team/RFP_Preprocessing_Final_v11_Team"
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
golden_pipeline\golden.cmd plan <plan_id> <근거 어댑터 run_id> --count numeric 20 --count table 20 --max-context-chars 4000
```

1. 근거 어댑터 run 의 `manifest.json` 에 고정된 파일 SHA-256 과 지금 패키지 파일이 같은지 확인하고, 다르면 멈춥니다.
2. `judgments.jsonl` 에서 `eligible` 인 단위만 씁니다. `held` 단위는 어떤 묶음에도 들어가지 않습니다.
   단위 본문은 패키지 `final_elements.jsonl` 에서 읽습니다 (글자 span 은 그 구간, 표 행은 칸을 ` | ` 로 이은 것).
3. 주제 순서(`numeric` → `table` → `condition` → `comparison` → `multi_hop`)대로, 주제 명세의 `pattern` · `table_only` 에 맞는 단위를
   문서마다 패키지 순서로 `bundle_units` 개씩 묶습니다. 컨텍스트가 `--max-context-chars` 를 넘는 묶음은 버립니다.
   multi_hop 은 청크 둘 이상에 걸친 묶음만 냅니다 (`_spanning`). 이어진 단위는 대개 한 표의 이웃 행이라
   그대로 묶으면 절반 넘게(night 계획 300개 중 162개) 한 청크 안에 들었고, 그 묶음의 후보 431개는 하나도 출시되지 못했습니다.
   한 단위는 한 주제의 묶음에만 들어갑니다 (카탈로그가 같은 근거를 두 주제에 두지 않기 때문).
   표 행이 든 묶음에는 그 표의 머리글 행(논리 표 0행)을 맨 앞에 붙입니다. 열 이름 없이는 칸을 가리킬 수 없기 때문입니다.
   머리글 행이 `eligible` 이 아니거나 앞 주제의 묶음이 이미 가졌으면 그 묶음을 버립니다.
   줄의 절반 이상이 쪽 번호로 끝나는 목차 줄(`1. 용역개요 02`)인 단위는 묶지 않습니다. 목차로 만든 질문은 RFP 내용을 묻지 않습니다.
4. 문서를 돌아가며 하나씩 골라 개수를 채웁니다. 모자라면 기준을 낮추지 않고 `planned` 에 실제 개수를 남깁니다.
   그래서 한 문서에 묶음이 몰리지 않습니다.
5. 묶음마다 문서 이름 `doc` (`agency`, `title`)을 남깁니다. 발주 기관은 패키지 옆 `data_list.csv` 의 정리된 `발주 기관` 을
   v11 레코드의 원본 파일 이름으로 찾고, 사업 이름은 파일 이름의 `_` 뒤에서 `[재공고]` 같은 앞 표시를 뺀 것입니다.
   원본 파일 이름 일부는 한글 자모가 풀린 NFD 라 두 이름 모두 NFC 로 맞춘 뒤 찾습니다.

묶음은 늘 같은 순서로 고르므로, 같은 개수로 새 계획을 만들면 앞 계획의 묶음이 다시 뽑힙니다.
새 근거로 재생성하려면 `--skip-plan <앞 계획 id>` 를 줍니다 (여러 번 줄 수 있음). 그 계획이 쓴 단위는 1번 다음에 바로 빼고,
계획 파일의 `skipped_plans` 에 계획 id → SHA-256 을 남깁니다. 머리글 행을 앞 계획이 가졌던 표의 나머지 행도 3번 규칙대로 빠집니다.

계획 파일(`outputs/plans/{plan_id}.json`)은 덮어쓰지 않으며, run 은 이 파일의 SHA-256 을 남깁니다.

| 필드 | 값 |
|---|---|
| `evidence_run` · `v11_manifest_sha256` | 근거 어댑터 run 과 v11 `manifest.json` SHA-256 |
| `topic_specs` | 주제 명세 파일별 SHA-256. 생성 때 명세가 바뀌었으면 멈춥니다 |
| `skipped_plans` | 단위를 뺀 앞 계획 id → 그 계획 파일 SHA-256 (없으면 `{}`) |
| `max_context_chars` | 묶음 컨텍스트 글자 수 한도 (A · B 의 입력 한도) |
| `counts` · `planned` · `coverage` | 요청 개수, 실제 묶음 수, 주제별 문서 SHA → 묶음 수 |
| `bundles[]` | `bundle_id`, `topic`, `doc_sha`, `doc` (`agency`, `title`), `units[]` (`label` `E1`…, `unit_id`, 근거 참조 `ref`, `text`), `context` |

`context` 는 `[E1]\n본문\n\n[E2]\n본문` 형식이며 생성기에 이 문자열을 그대로 보냅니다. 문서 이름은 컨텍스트에 넣지 않습니다.

2026-10-14 실제 v11 근거 run(`v11-20261014`)으로 주제마다 20개를 요청한 계획은 약 8초에 만들어졌고,
다섯 주제 모두 20개 묶음을 서로 다른 문서 20개에서 골랐습니다.

## 주제 명세

`configs/topics/{topic}.json` 은 `version`, `requires` (프롬프트에 넣는 요구 설명), `structure` (출력 구조 필드와 설명),
묶음 선택 규칙 `pattern` · `table_only` · `bundle_units` 를 가집니다.
출력의 `structure` 는 명세의 필드를 정확히 가져야 하고, 주제마다 아래를 지켜야 후보가 됩니다.
값은 근거에 적힌 그대로여야 합니다 (공백 · 쉼표 차이만 허용).
수로 시작하거나 끝나는 값은 수 전체가 맞아야 합니다. 예를 들어 조건 `1년 이내` 는 `11년 이내` 에 맞지 않습니다.
수의 경계는 공백을 지우기 전의 글에서 봅니다. 띄어 쓴 두 수는 다른 수라, 목차 `13\n 1. 입찰참가자격 13` 의 `1. 입찰참가자격 13` 은 맞습니다.
다만 쉼표 앞뒤가 줄바꿈 등으로 벌어진 세 자리 묶음은 한 수라, `1,\n300,000원` 안의 `300,000원` 은 맞지 않습니다.

| 주제 | `structure` | 후보가 되는 조건 |
|---|---|---|
| `numeric` | `value` · `unit` | 값에 숫자가 있고, (`value`, `unit`) 이 답과 인용한 근거에 모두 수 · 단위 쌍으로 있음. 쌍은 Kiwi 형태소 분석으로 읽습니다. 수(SN) 앞의 부호는 띄어 써도 값에 들고, 수 뒤에 붙어 이어지는 단위 형태소는 끝까지 한 단위가 되며 더 짧은 단위로 물러나지 않습니다. 단위는 조사 · 어미 · 문장부호 · 띄어쓰기에서 끝납니다. 그래서 부호 · 수 · 단위가 통째로 맞아야 합니다 (`30,000,000원` ≠ `130,000,000원`, `-130,000,000원` · `- 130,000,000원` ≠ `130,000,000원`, `12개` ≠ `12개월` · `12개월간`, `5%` ≠ `5%p` · `5%포인트`, `5MB` ≠ `5MB/s`, `12개월이다` 는 `12` · `개월`, `5만원` 은 `5` · `만원`). 범위 표시 · 다른 수 · 쉼표 · 접두사에 붙은 수(`10~12개월`, `2024년-2025년`, `1,2,3개월`, `제3회`)는 쌍이 아닙니다. 한글로만 쓴 수(`삼천만원`)는 쌍이 없어 거절됩니다. 줄머리 기호 `- 12개월` 도 음수로 읽혀 거절됩니다. 값 없이 설명만 하는 답은 `유형 불일치` 로 거절 |
| `table` | `row` · `column` | 인용한 근거에 표 행이 있고, 행 · 열 이름이 근거에 있음 |
| `condition` | `condition` | 조건 · 예외 문구가 근거에 있음 |
| `comparison` | `entities` · `values` · `choice` | 서로 다른 대상 2개 이상, 각각 근거에 있음. `values` 는 대상마다 값이고 값도 근거에 있음. 값이 대상 이름이면(`A안 A안`, `A안 B안`) 견줄 값이 없어 거절. `choice` 는 대상 중 하나 (고르지 않는 비교는 나란한 조회라 거절). 답은 `structure` 로 만든 글(`A안 1억원, B안 2억원. 답: B안`)과 같음 (공백 · 쉼표 차이만 허용) |
| `multi_hop` | 없음 (`{}`) | 인용한 근거 단위가 2개 이상 |

## 후보 생성

A · B · C 는 같은 출력 계약과 같은 검사를 거쳐 같은 `write_run` 으로 저장됩니다.
모든 출력은 `candidate` 상태이고, 이 단계의 어떤 코드도 `auto_validated` · `released` 로 옮기지 않습니다.
`accepted.jsonl` 은 비어 있습니다.

질문에는 문서 98개 가운데 어느 문서를 묻는지가 드러나야 합니다. 프롬프트는 질문에 기관 · 사업 이름을 쓰지 말라고 하고,
A · B 는 항목을 만들 때 계획의 `doc` 으로 질문 앞에 `{발주 기관}의 「{사업 이름}」 사업에서 ` 를 붙입니다 (`with_document`).
생성기가 이름을 잘못 옮겨 쓰는 일을 막기 위해서입니다.

출력 한 행은 정확히 `question`, `answer`, `evidence` (묶음의 근거 라벨 리스트), `structure`, `secondary_tags` 를 가집니다 (C 는 `bundle_id` 도).
아래 중 하나라도 어기면 항목이 되지 않고 원문 · 이유와 함께 `rejected.jsonl` 로 갑니다:
JSON 아님, 필드 불일치, 계획에 없는 묶음(C), 묶음에 없는 · 겹치는 라벨, 항목 스키마 위반 (`스키마: ...`), 주제 구조 위반 (`유형 불일치: ...`),
카탈로그에서 다른 주제가 이미 가진 근거 묶음 인용 (`근거 묶음이 이미 ... 주제 소유입니다`).
항목은 인용한 단위의 근거 참조, `bundle_id`, 보낸 컨텍스트 원문(`context`)을 가집니다.

| 방식 | 입력 | 프롬프트 | 기록 |
|---|---|---|---|
| A (첫 생성) | `generate("A", topic, plan_id, run_id, config, client)` | `prompts/A/{topic}.txt` | 그대로 부르면 실패 기록을 읽지 않습니다. 자기 개선 round 는 `revision` 으로 예방 규칙을 붙입니다 (아래 자기 개선) |
| B (고정 프롬프트) | `generate("B", ...)` | `prompts/B.txt` 하나 | 실패 기록을 읽지 않습니다. 같은 모델 · 계획 · 주제 명세를 받고 프롬프트만 고정 |
| C (가져오기) | `import_c(topic, plan_id, run_id, exports, sidecar)` | 관측 불가 → `unobserved` | 사람이 웹 환경에서 받아 내보낸 JSONL 파일들과 관측 기록 |

A · B 는 묶음마다 한 번 `client(model=..., reasoning_effort=..., messages=[system: 프롬프트, user: context])` 를 부릅니다.
`reasoning_effort` 는 OpenAI 호출에 그대로 실립니다.
`client` 는 `{"model", "text", "input_tokens", "output_tokens"}` 를 돌려주며, `model` 은 API 응답이 알려 준 이름이어야 합니다.

`run_id` 가 경로 한 칸 이름이 아니거나 이미 쓴 run 이면 호출 전에 멈춥니다.
run 설정(JSON 파일)은 아래 여섯 값을 모두 가져야 하고, 빠지면 호출 전에 멈춥니다. 기본값이 없으므로 설정 없이 유료 호출이 나가지 않습니다.

| 키 | 값 |
|---|---|
| `model` | 요청할 모델 이름 |
| `reasoning_effort` | 추론 강도 (예: `low` · `high`). run 매니페스트 · 검증 기록 · loop `start.json` 의 설정에 남습니다 |
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
| `policy` | 자기 개선 round 의 예방 규칙 버전 · 실패 코드별 기록 · 붙인 글 SHA-256, 아니면 `null` | 없음 |
| 호출 | `status`, `cost_usd`, `calls[]` (묶음, 응답 모델, 토큰) | 없음 (토큰 · 비용을 0 으로 채우지 않음) |

LLM 출력은 같은 입력에도 달라질 수 있어 결정성을 주장하지 않습니다.
대신 보낸 컨텍스트, 프롬프트 · 설정 · 계획 해시, 응답 모델을 남겨 무엇을 넣어 무엇이 나왔는지 추적합니다.

## 독립 검증

```python
validate(topic, method, run_id, config_path, client)
```

검증기는 생성기와 같은 `client` 계약으로 부르며, run 설정도 생성과 같은 여섯 값을 기본값 없이 받습니다.
검증기가 받는 것은 system 메시지 `prompts/validator.txt` 와 user 메시지 `{"question", "evidence": [{"label", "text"}]}` 뿐입니다.
근거 단위는 후보가 인용한 단위를 계획의 근거 묶음에서 찾은 것이고, 표 행에는 그 표의 머리글 행을 붙입니다.
계획 파일의 SHA-256 이 생성 run `manifest.json` 의 `generation.plan_sha256` 과 다르면 검증기를 부르기 전에 멈춥니다.
생성기의 답 · 구조 · 프롬프트 · 보낸 컨텍스트 전체 · 자기 평가는 보내지 않습니다.
검증기는 `{"answerable", "answer", "conditions", "conflict", "comparison"}` 를 돌려줍니다
(독립 답, 답을 제한하는 조건 · 예외, 근거끼리의 값 충돌, 견주는 질문이면 `{"values": {이름: 값}, "choice": 이름 또는 null}` 아니면 `null`).
검증기는 주제를 모르므로 견주는 질문인지도 질문과 근거만 보고 스스로 정합니다.

후보마다 아래 순서로 보고, 처음 걸린 곳에서 멈춥니다. 돈이 들지 않는 검사를 먼저 합니다.

| 순서 | 검사 | 걸리면 |
|---|---|---|
| 1 | 주제 구조 (`check_structure`, 생성과 같은 검사) | `rejected` `유형 불일치` |
| 1 | 규칙 검사 (`rule_reason`, 아래 출시에서도 다시 봄): 답은 맞지만 평가에 쓸 수 없던 꼴. 대상을 이름으로 밝히지 않은 numeric 질문의 `값과 단위` · `수치와 단위` · `첫 번째 값`, table 질문의 줄바꿈, 인용한 표 행·머리글의 빈 칸(빈 칸으로 시작하거나 이어짐), condition 답의 `(조건:` 덧붙임, comparison 의 `choice` 없음 (1 이 먼저 막지만 그 전에 검증한 run 을 출시할 때 걸림), multi_hop 근거가 모두 한 청크. 무료 검사는 호출 한도 확인 전에 모든 후보에 적용합니다 | `rejected` `모호한 대상` · `끊긴 질문` · `빈 칸 표` · `답 덧붙임` · `비교 아님` · `multi_hop 아님` |
| 2 | 표: 인용한 표에서 행 이름 · 열 이름이 만나는 칸의 값이 답에 있음 | `rejected` `표 관계` |
| 2 | 조건: 구조의 조건 · 예외 문구가 답에 있음 | `rejected` `조건 · 예외 누락` |
| 3 | 같은 주제 · 같은 방식에서 이미 통과한 항목과 근거 묶음이나 질문(공백 · 쉼표 무시)이 같음 | `rejected` `중복` |
| 4 | 검증기 출력이 계약에 맞음 (어기면 한 번 다시 부름) | `rejected` `검증기 출력 오류` |
| 5 | 검증기가 근거 충돌을 알리지 않음 | `rejected` `근거 충돌` |
| 6 | 검증기가 근거만으로 답할 수 있음 | `rejected` |
| 7 | numeric: 독립 답에 수 · 단위가 있고, 후보 구조의 값 · 단위가 독립 답에 있음 | `rejected` `유형 불일치` · `독립 답과 다릅니다` |
| 8 | 질문에 독립 답이 이미 들어 있지 않음. 비교 질문이 선택지로 든 대상 이름 하나를 답하는 것은 예외 | `rejected` `복사형` |
| 9 | 독립 답이 후보 답과 같음 (아래 정규화, 정하지 못하면 판정기). 비교는 대상별 값 · 고른 대상이 같음 | `rejected` `독립 답과 다릅니다` |
| 9 | 독립 답이 단 조건 · 예외 중 후보 답에 글자로 없는 것이 있으면 판정기가 그 조건이 답을 제한하는지까지 보고 정함 | `rejected` `조건 · 예외 누락` |
| 10 | multi_hop: 근거 단위를 하나씩만 준 검증기 답이 어느 것도 독립 답과 같지 않음 | `rejected` `multi_hop 아님` |

나머지는 `auto_validated` 입니다. 애매한 판정을 사람에게 넘기는 상태는 없습니다.
검증기 출력이 두 번 다 계약을 어기거나 근거끼리 값이 다르면 틀린 문제로 보고 거절하고,
값 · 글자로 같은지 정하지 못하면 판정기(`prompts/judge.txt`)가 같은지 다른지 둘 중 하나로 정합니다.
판정기는 `{"question", "evidence", "answer_a": 독립 답, "answer_b": 후보 답}` 을 받아 `{"same": true|false}` 만 돌려주며,
정하지 못하면 다른 답이라고 하도록 되어 있습니다. 판정기 출력도 계약을 두 번 어기면 `검증기 출력 오류 (판정기)` 로 거절합니다.
비교의 정규화:

- 독립 답에 수가 있으면 (부호 포함 값, 단위) 쌍으로 맞춥니다. 쌍은 numeric 검사와 같이 Kiwi 형태소로 읽고,
  쉼표를 지운 십진수로 바꾸며 천 · 만 · 억 · 조는 값에 곱합니다. `1억 3천만원` = `130,000,000원`, `5만원` = `50,000원`,
  `12개` ≠ `12개월`, `5%` ≠ `5%p`. 독립 답의 쌍이 모두 후보 답에 있어야 같은 답입니다.
- 비교(`comparison`) 항목은 답 글을 견주지 않고 필드를 견줍니다. 결론(어느 대상을 골랐는지)은 글자로 읽을 수 없기 때문입니다
  (`A안 1억원, B안 2억원으로 A안이 더 많다` 는 값이 모두 맞아도 결론이 틀립니다).
  후보 `structure` 의 `values` (대상마다 값) · `choice` (고른 대상) 를 검증기의 `comparison` 과 맞춥니다.
  대상마다 값은 담기가 아니라 같음을 봅니다 (`미지원` 은 `지원` 을 담지만 반대 뜻).
  글이 같으면(공백 · 쉼표 차이만) 같고, 수 · 단위 값이 다르면 다르며, 수 표기만 다르면 같습니다 (`1억원` = `100,000,000원`).
  수가 여럿이면 쓴 차례로 견줍니다. 수 밖의 글이 같은데 자리마다 수가 다르면 다른 값입니다
  (`구축 2억원, 운영 1억원` ≠ `구축 1억원, 운영 2억원`).
  수 밖의 글은 수 · 단위 쌍으로 읽은 자리만 지우고 견주므로, 쌍이 아닌 수는 남습니다
  (`제3회 회의 1억원` 과 `제4회 회의 1억원` 은 수 밖의 글이 달라 판정기로).
  그 밖에 글이 다른 값(`지원 가능` · `지원`, `1억원 이상` · `1억원`)은 판정기가 정합니다. `choice` 는 같은 대상이어야 합니다 (검증기가 고르지 않으면 다름).
  값이나 `choice` 가 다르면 `rejected` `독립 답과 다릅니다`, 검증기가 `comparison` 을 주지 않았거나
  대상 이름이 `entities` 와 꼭 같지 않으면 판정기가 정합니다.
  답 글은 생성 검사에서 `structure` 로 만든 글(`A안 1억원, B안 2억원. 답: B안`)과 같아야 하므로 필드와 다른 결론을 쓸 수 없습니다.
- 그 밖의 주제는 독립 답에 단위가 같은 값이 여럿일 때 값마다 그 대상(단위가 같은 앞 값 뒤부터 이 값 앞까지의 내용 형태소)도 맞춥니다.
  그 값의 대상에만 있는 낱말이 후보 답의 같은 값 앞에 모두 있어야 같은 답입니다.
  다른 값의 대상 낱말 뒤에 쓰면 다른 답(`A안 1억원, B안 2억원` ≠ `A안 2억원, B안 1억원`)이고,
  대상이 없거나 다른 이름이면(`1억원, 2억원`, `C안 2억원, D안 1억원`) 확인하지 못한 답이라 판정기가 정합니다.
  대상은 값 앞에서만 읽으므로 `validator.txt` 는 대상을 값 앞에 쓰라고 합니다.
- 수가 없는 답은 공백 · 쉼표만 지우고 글자로 맞추고, 글자가 다르면 표현만 다를 수 있어 판정기가 정합니다.
  조건 · 예외 문구 비교는 글자로 맞춥니다.

거절은 끝 상태라 사람이 되돌릴 수 없습니다.

중복은 카탈로그로 같은 주제 · 같은 방식의 다른 run 을 찾아, 그 run 의 `accepted.jsonl` 과 맞춥니다.
거절된 항목은 맞추지 않습니다 (같은 근거로 다시 만든 항목이 막히지 않도록).
다른 방식(A · B · C)은 같은 계획의 같은 근거 묶음을 받는 것이 비교의 전제라 중복으로 보지 않고, 대신 출시본 하나에 함께 들어가지 못합니다.

난도는 `DIFFICULTY_RULE` (`difficulty-2`) 대로 정하고 모든 검증 항목에 `validator_version` 과 함께 남깁니다.

| 난도 | 규칙 |
|---|---|
| `hard` | multi_hop 이고 10번 검사를 통과함 (근거 둘 이상이 필요함이 확인됨) |
| `easy` | 그 밖에, 질문의 내용 형태소(NNG · NNP · SL · SN, 의문사 제외)가 모두 근거 본문에 그대로 있음. 앞에 붙인 문서 이름은 근거에 없으므로 빼고 봄 |
| `medium` | 나머지 (질문이 근거와 다른 말로 물음) |

결과는 run 의 `accepted.jsonl` (`auto_validated`)을 채우고,
거절 항목은 `rejected.jsonl` 뒤에 붙입니다. `validation.json` 에는 검증기 버전, 난도 규칙, 모델(요청 · 응답),
설정 · 검증기 프롬프트 · 판정기 프롬프트 해시, 호출, 비용, 상태별 개수, 두 상태 파일의 SHA-256 을 남깁니다.
후보는 `WORKERS` (8) 개씩 함께 판정합니다. 중복 검사는 판정이 끝난 뒤 후보 차례대로 하므로 함께 판정한 후보끼리도 막힙니다.
run 마다 한 번만 검증하며, 이미 검증한 run 은 호출 전에 막습니다.
호출 수 한도와 예산은 후보를 시작하기 전에 보고, 닿으면 남은 후보를 검증하지 않은 채 `pending` 에 남깁니다
(한 후보의 multi_hop 검사를 도중에 끊지 않음).
실패 기록(`failure_memory`)은 아래 자기 개선이 채웁니다.

### 이어서 검증 (B · C)

```python
resume_validation(topic, method, run_id, config_path, client)
```

B · C run 의 마지막 검증 기록에 `pending` 이 남았으면 그 후보만 새 한도로 검증합니다. 생성을 다시 하지 않으므로 생성 비용을 또 내지 않습니다.
A 의 검증은 자기 개선 loop 가 맡으므로 받지 않습니다.

1. 상태 파일이 마지막 검증 기록의 SHA-256 과 같은지 보고, 다르면 멈춥니다.
2. 검증기 버전 · 난도 규칙 · 검증기 프롬프트 SHA-256 · 모델 · 추론 강도 · 단가가 앞 기록과 다르면 호출 전에 바뀐 키를 밝히고 멈춥니다.
   한 run 의 후보를 서로 다른 기준으로 판정하지 않기 위해서입니다. 바뀌는 것은 호출 수 한도와 예산뿐입니다.
3. 중복 검사에 같은 run 에서 앞서 통과한 항목도 넣습니다.
4. 판정한 항목은 상태 파일 뒤에 붙이고, `validation-{n}.json` 에 이번 호출 · 비용 · 남은 `pending` 과
   앞 기록의 이름 · SHA-256(`continues`)을 남깁니다. 출시와 비교 보고서는 마지막 기록의 SHA-256 으로 상태 파일을 확인하고,
   출시 매니페스트의 `sources` 에는 모든 검증 기록의 SHA-256 이 들어갑니다.
5. `pending` 이 없으면 멈춥니다. 같은 후보를 두 번 판정하지 않습니다.

## 자기 개선 (A 만)

```python
improve(topic, plan_id, loop_id, config_path, generator, validator)
```

A 를 round 마다 생성 → 독립 검증 → 실패 기록 순서로 돌립니다. round n 의 run 은 `{loop_id}-r{n}` 입니다.
B · C 와 출시는 실패 기록을 읽지 않고, `generate("B", ..., revision=...)` 는 거절합니다.

1. 다시 부를 묶음: 계획의 주제 묶음 중 loop 의 앞 round 에서 `auto_validated` 가 되지 않은 묶음.
   남은 묶음이 없으면 멈춥니다 (`no_open_bundles`).
2. 관련 실패: 그 주제의 `failure_memory/A_*.jsonl` 과 `screen_*.jsonl` 을 실패 코드별로 묶고 (`related_failures`),
   코드마다 정해 둔 예방 규칙을 A 프롬프트 뒤에 `지난 실패에서 정한 예방 규칙` 으로 붙입니다.
   다른 주제의 기록과, 실패한 후보의 답은 붙이지 않습니다.
   묶음마다 그 묶음의 지난 실패(`bundle_notes`)도 user 메시지 뒤에 붙입니다. 최근 3개까지
   `- 질문 '{그 묶음에서 거절된 질문}': {예방 규칙}` 또는 `- 출력 (항목이 되지 못함): {예방 규칙}` 입니다.
   같은 묶음이 같은 이유로 거듭 거절되지 않게 하려는 것이고, 고친 답은 주지 않습니다. 붙인 글은 run 매니페스트의 `policy.notes` 에 남습니다.
3. 생성: 그 묶음만 `WORKERS` (8) 개씩 함께 부릅니다. 같은 묶음에서 거절된 앞 후보가 있으면 새 후보의 `parent_candidate_id` 가 그 id 이고,
   새 후보는 새 `candidate_id` 를 받습니다. 앞 round 의 파일은 바꾸지 않습니다.
   run 매니페스트의 `generation.prompt_sha256` (프롬프트 파일)과 `generation.policy`
   (`version`, `loop_id`, `round`, `start.json` 의 `start_sha256`, 코드별 기록 `failures`, 붙인 글의 `prevention_sha256`)로
   무엇을 보냈는지 남깁니다.
4. 검증: 독립 검증과 같습니다. 기준은 바꾸지 않습니다.
5. 실패 기록: `rejected.jsonl` 한 줄마다 항목 하나를 `failure_memory/A_{run_id}.jsonl` 에 씁니다 (`record_failures`).

실패 기록 항목은 정확히 아래 필드이고, 고친 답은 넣을 수 없습니다.
검증하지 않은 답이 다음 프롬프트에 사실로 들어가면 다음 후보가 오염되기 때문입니다.

| 필드 | 값 |
|---|---|
| `entry_id` | `{run_id}:{rejected.jsonl 줄 번호}` |
| `failure_code` | 거절 이유의 앞부분으로 정한 코드 (`FAILURE_CODES`). 코드가 없는 이유는 기록하지 않고 멈춥니다 |
| `evidence` | 보존된 실패를 가리킴: `run` (`A/{run_id}`), `line`, `candidate_id` (항목이 되지 못한 출력이면 `null`), `bundle_id` |
| `prevention_rule` · `rule_version` | 그 코드의 정해 둔 규칙 글과 `PREVENTION_VERSION` (`prevention-7`). 글을 바꾸면 버전을 올립니다 |

| 실패 코드 | 거절 이유 |
|---|---|
| `output_format` · `evidence_label` · `schema` | 생성 출력이 JSON · 필드 · 근거 라벨 · 스키마를 어김 |
| `type_mismatch` · `evidence_owned` | 주제 구조 위반, 다른 주제가 가진 근거 묶음 |
| `table_relation` · `missing_condition` · `duplicate` | 표 칸, 조건 · 예외 누락, 중복 |
| `unanswerable` · `answer_mismatch` · `copied` · `not_multi_hop` | 검증기가 답할 수 없음, 독립 답과 다름, 복사형, multi_hop 아님 |
| `validator_output` · `evidence_conflict` | 검증기 · 판정기 출력이 두 번 다 계약을 어김, 근거끼리 값이 다름 |

A run 의 실패 기록은 `record_failures` 가 그 run 의 `rejected.jsonl` 줄에서만 만듭니다.
그래서 항목의 글은 정해 둔 규칙 글뿐이고, 출시본의 질문 · 답 · 전이 이유가 들어올 자리가 없습니다.

검증을 통과했지만 출시에서 빠진 항목도 다음 생성이 피해야 할 실패입니다. 사람이 읽고 정하는 단계는 없습니다.
`release` 명령은 출시본을 쓴 뒤 `record_screen` 으로 매니페스트 `release.dropped` 의 A 항목을 `failure_memory/screen_{version}.jsonl` 에 같은 꼴로 씁니다.
`entry_id` 는 `screen-{version}:{n}`, `evidence` 는 `{release, run, candidate_id}` 이고, 질문 · 답은 넣지 않습니다.
출시 매니페스트는 항목이 모두 빠진 run 을 포함한 모든 입력 run 의 파일 해시를 고정합니다.
코드는 판정기가 고른 `code`, 규칙 검사 · 판정기 출력 오류로 빠진 항목은 이유 문구의 코드입니다.

| 출시 실패 코드 | 빠진 이유 |
|---|---|
| `structure_question` · `ordinal_reference` · `evidence_reference` | 목차 · 위치 · 표 형식을 물음, 순번 · '첫 번째 값' 으로 가리킴, 질문자가 볼 수 없는 근거('E1 · E2' · '근거들' · '이 요구사항')를 가리킴 |
| `answer_dump` · `useless_answer` · `copied` | 답이 원문 · 덧붙임을 늘어놓음, 답이 양식 빈칸 · 안내 문구, 답이 질문에 있음 |
| `malformed_question` · `personal_info` · `invalid_comparison` | 끊긴 질문, 사람 이름 · 연락처 · 결재란, 견줄 까닭이 없는 비교 |
| `broken_table` | 근거 표에 빈 칸 행이 있어 칸의 뜻이 정해지지 않음 (규칙 검사) |

loop 설정(JSON)은 아래를 기본값 없이 모두 가져야 합니다.

| 키 | 값 |
|---|---|
| `max_rounds` · `max_calls` | 최대 round 수, loop 전체(생성 + 검증)의 최대 호출 수 (1 이상의 정수) |
| `budget_usd` | loop 전체 예산 (0 보다 큼) |
| `generator` · `validator` | 각각 정확히 `model` · `reasoning_effort` · `usd_per_million_input_tokens` · `usd_per_million_output_tokens` |

round 의 생성 · 검증은 loop 한도에서 이미 쓴 호출 · 비용을 뺀 run 설정(`loops/{loop_id}/r{n}-*.json`)으로 돕니다.
쓴 호출 · 비용은 호출이 돌아올 때마다 `calls.jsonl` 에 남기므로, 생성 · 검증이 도중에 끊겨도 이어 돌 때 그만큼 한도에서 빠집니다.
멈춘 이유는 `max_rounds` · `call_cap` · `budget` · `no_open_bundles` 중 하나로 `report.json` 에 남습니다.
생성이나 검증이 한도에 닿아 끝나지 않은 round 가 있으면 그 round 에서 멈추고, 검증 전에 한도에 닿은 round 는 `not_validated` 로 남습니다.

멈춘 loop 를 같은 인자로 다시 부르면 이어 돕니다. 생성 run · `validation.json` · 실패 기록이 이미 있는 단계는 건너뛰므로
끝난 round 를 다시 부르지 않고 같은 `candidate_id` 가 두 번 생기지 않습니다.
loop 설정, 계획(id 와 SHA-256), 통과 기준(`thresholds`)은 처음 시작할 때 `start.json` 에 고정하고,
round 마다와 `report.json` 을 쓰기 전에 지금 값과 맞춰 봅니다. 하나라도 다르면 바뀐 키를 밝히고 멈춥니다.
이미 있는 `{loop_id}-r{n}` run 은 이 loop 가 만든 것일 때만 이어 씁니다: 매니페스트의 `generation.policy` 의 `loop_id` · `round` ·
`start_sha256` 과 `generation.plan_id` · `plan_sha256` 이 이 loop 와 `start.json` 의 값과 같아야 합니다.
따로 만든 run (`policy` 가 `null`)이나 다른 계획 · 다른 시작 기록의 run 이 그 이름에 있으면 다른 키를 밝히고 멈춥니다.
`report.json` 이 있는 loop 는 다시 돌지 않습니다.

`report.json` 은 목표(계획의 요청 개수)와 `auto_validated` 묶음 수, 모자란 수(`shortfall`)를 남깁니다.
목표에 못 미쳐도 기준을 낮추지 않고 모자란 수만 보고합니다. 기준 해시(`thresholds`: 주제 명세 파일별 SHA-256,
검증기 · 판정기 프롬프트 SHA-256, 검증기 버전, 난도 규칙)를 함께 남깁니다. 이 값은 `start.json` 에 고정한 값과 같습니다.

## 출시

```python
release(topic, version, [(method, run_id), ...], config_path, client)
```

고른 run 들의 `auto_validated` 항목 중 쓸모 판정을 통과한 것을 `released` 로 옮겨 `releases/{version}/golden.jsonl` 에 씁니다.
사람이 확인하는 단계는 없습니다.

검증은 답이 근거와 맞는지만 봅니다. 목차 · 쪽 번호 · 순번 · 표 머리글 · 연락처를 묻는 질문도 답은 맞아 통과하므로,
출시 전에 먼저 검증의 규칙 검사(`rule_reason`)를 다시 봅니다. 규칙이 생기기 전에 검증한 run 도 같은 기준으로 내기 위해서입니다.
그다음 판정기(`prompts/screen.txt`)가 질문 · 답만 받아 RFP 를 읽는 사람이 물을 만한 질문인지 `{"useful": 참거짓, "code", "reason"}` 으로 정합니다.
`code` 는 쓸모 있으면 `null`, 없으면 위 출시 실패 코드 중 하나입니다 (`SCREEN_CODES`).
출력이 두 번 다 계약을 어기면 쓸모 없다고 봅니다. 빠진 항목은 `candidate_id` · 방식 · `run_id` · 질문 · 코드 · 이유와 함께 매니페스트 `release.dropped` 에,
판정 설정 · 프롬프트 SHA-256 · 호출 수 · 비용은 `release` 에 남습니다. CLI 는 다른 유료 명령처럼 모델 · 추론 강도 · 단가 · 한도를 받고,
한도에 닿으면 일부만 판정한 출시본을 만들지 않고 멈춥니다.
2026-10-15 실제 표본(비교 40 · 표 30)에서 `low` 는 같은 기준을 들쭉날쭉 적용해, 출시에는 `high` 를 씁니다.

| 거절 | 이유 |
|---|---|
| 이미 있는 `version` | 출시본을 덮어쓰지 않음 (`FileExistsError`) |
| 검증 뒤 바뀐 상태 파일 | `validation.json` 의 SHA-256 과 다르면 막음. 거절 항목을 `accepted.jsonl` 로 옮겨 넣지 못하게 |
| 같은 근거 묶음이나 같은 질문의 항목 둘 | 방식을 섞어 낼 때도 |
| run 에 등록된 기록과 다른 내용 | 위 저장 규약 |

출시 매니페스트의 `sources` 에는 원본 run 마다 `candidates.jsonl` · 상태 파일 · `manifest.json` · 검증 기록들의 SHA-256 을 남깁니다.

## 비교 보고서

```python
write_report(topic, report_id, {"A": [round run_id, ...], "B": [run_id, ...], "C": [run_id, ...]})
```

비교 대상은 데이터셋 생성 방식(A · B · C)이고, RAG 답변 시스템이 아닙니다. API 를 부르지 않습니다.
CLI 의 `report --a` 는 loop id 를 받아 그 loop 의 round run 들을 넣습니다.
모든 run 은 같은 계획(id 와 SHA-256)으로 만든 것이어야 하고, 계획 파일이 그 뒤 바뀌었어도 멈춥니다.
검증한 run 은 상태 파일이 마지막 검증 기록과 같은지 먼저 확인합니다.
결과는 `reports/{report_id}.json` 에 쓰고 마크다운 표로 보여 줍니다. 비율은 모두 분자 · 분모 · 값으로 남깁니다.

생성 출력 하나는 생성기 응답 한 번(C 는 내보낸 파일의 한 줄)이고, 항목이 된 것과 되지 못한 것(`rejected.jsonl` 의 `{bundle_id, reason, raw}`)을 모두 셉니다.
A 는 모든 round 의 출력을 셉니다. 거절 이유는 자기 개선의 실패 코드로 나눕니다 (C 의 계획에 없는 묶음만 `unplanned_bundle`).

| 지표 | 분자 | 분모 |
|---|---|---|
| 유효 문항률 | `auto_validated` 항목 | 생성 출력 |
| 출처 정확성 | 근거 대조를 마친 항목 중 근거와 답이 맞지 않아(`table_relation` · `unanswerable` · `answer_mismatch`) 거절되지 않은 것 | 근거 대조를 마친 항목: 검증한 항목에서 대조 전에 걸릴 수 있는 거절(`type_mismatch` · `missing_condition` · `duplicate`)을 뺀 것 |
| 유형 준수 | 주제 구조 검사를 통과한 출력 (생성 · 검증의 `type_mismatch` 를 뺀 것) | 주제 구조 검사까지 간 출력: 모든 항목과, 항목이 되지 못한 출력 중 `type_mismatch` · `evidence_owned` |
| 중복 | `duplicate` 로 거절된 항목 | 검증한 항목 |
| 커버리지 | `auto_validated` 항목이 하나라도 있는 계획의 근거 묶음 | 계획의 그 주제 근거 묶음 |
| 난도 분포 | `easy` · `medium` · `hard` 각각의 `auto_validated` 항목 | `auto_validated` 항목 |
| 유효 문항당 비용 | 총비용 | `auto_validated` 항목 |

- 아직 검증하지 않은 후보 수(`pending`)도 함께 보여 줍니다. 이 후보는 유효 문항에 들지 않습니다.
- 비용과 토큰은 생성(A · B 의 run 매니페스트 `calls` · `cost_usd`)과 검증(모든 검증 기록)으로 나누고, 총비용은 둘의 합입니다.
  기록을 남기기 전에 끊긴 호출은 들지 않습니다.
- C 의 생성 토큰 · 비용은 웹 환경이라 관측할 수 없어 `unobserved` 로 남기고, 그래서 C 의 총비용과 유효 문항당 비용도 `unobserved` 입니다.
  0 으로 채우면 C 가 공짜처럼 보여 유효 문항당 비용을 견줄 수 없게 되기 때문입니다. C 의 검증 비용은 관측한 값이라 숫자로 남습니다.

## 테스트

테스트는 `tests/golden/` 에 있어 저장소 게이트(`.venv\Scripts\python -m pytest -q tests`)가 함께 돌립니다.
이 패키지만 돌리려면:

```
python -m pytest -q tests/golden
```

`.env` 키와 네트워크 없이 돌아가고, 출력은 임시 폴더에 씁니다. CLI 테스트는 `api_client` 를 가짜 API 로 바꿔
A · B 실행, C 가져오기, 검증, 출시, 비교 보고서, 이어 돌기를 끝까지 돌립니다.
