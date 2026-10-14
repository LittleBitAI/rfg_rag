# golden_pipeline — 골든 데이터 파이프라인 기반

평가용 골든 질문·답변을 주제별로 만들고 검증해 출시하기 위한 패키지입니다.
③ 검증 파이프라인에 속하고 담당자도 같지만, `rag/validation/validation.py` 와는 일부러 분리했습니다
(`CLAUDE.md` · `AGENTS.md` 4절).
이 단계(기반)는 **항목 스키마, 주제별 저장 규약, run·버전·상태 모델, 출력 경로 보호**만 담습니다.
v11 읽기, 생성, 검증, 자기 개선, 실행기는 이후 단계에서 붙습니다.

- `rag/` 에서 아무것도 import 하지 않고, `rag/`·`artifacts/`·`data/`·`eval/` 에 쓰지 않습니다.
- 표준 라이브러리만 씁니다 (`requirements.txt` 변경 없음). API 호출이 없습니다.

## 구성

| 파일 | 내용 |
|---|---|
| `schema.py` | 항목 스키마와 검증 (`validate_item`) |
| `state.py` | 상태 전이와 전이 기록 (`transition`) |
| `storage.py` | run · release 저장, 공유 카탈로그, 출력 경로 보호 (`write_run`, `write_release`, `guard`) |
| `configs/` | run 설정 파일. run 마다 파일별 SHA-256 이 매니페스트에 남습니다 |
| `prompts/` | 생성·검증 프롬프트 파일. run 마다 파일별 SHA-256 이 매니페스트에 남습니다 |
| `outputs/` | 모든 출력 (git 에서 제외, `.gitignore`) |

## 항목 스키마

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
| `location.grid` | `logical_restored` (마크다운 논리 행으로 복원한 표) · `original_verified` (원본 격자를 확인한 표) |
| `page` | 1 이상의 정수 또는 `null` (v11 청크는 대부분 쪽 번호가 없음) |
| `requirement_ids` | `SFR-001` 같은 요구사항 id 리스트 |
| `image_sha` · `ocr_scope` | 이미지 근거일 때 둘 다: SHA-256 과 `human_verified` · `unverified`. 아니면 둘 다 `null` |

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
`validate_item` 은 `state_history` 가 `candidate` 에서 시작해 허용된 전이만 거쳐 지금 `state` 에 닿는지,
전이마다 이유가 있는지 확인합니다. 그래서 `state` 만 고쳐 검증이나 사람 검토를 건너뛸 수 없습니다.

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

## 테스트

테스트는 `tests/golden/` 에 있어 저장소 게이트(`.venv\Scripts\python -m pytest -q tests`)가 함께 돌립니다.
이 패키지만 돌리려면:

```
python -m pytest -q tests/golden
```

`.env` 키와 네트워크 없이 돌아가고, 출력은 임시 폴더에 씁니다.
