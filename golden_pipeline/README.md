# golden_pipeline — 골든 데이터 파이프라인 기반

평가용 골든 질문·답변을 주제별로 만들고 검증해 출시하기 위한 독립 패키지입니다.
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
| `tests/` | 오프라인 테스트 |
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
| `validator_version` | 검증 전이면 `null` |
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
- `golden_pipeline/outputs` 밖(`data/`, `artifacts/`, `eval/` 포함)으로 가는 경로는 `OutputPathError` 로 거절합니다.

## 테스트

```
python -m pytest -q golden_pipeline/tests
```

`.env` 키와 네트워크 없이 돌아갑니다. 출력은 임시 폴더에 쓰고, 마지막 테스트는
`git diff --name-only origin/dev...HEAD` 가 `golden_pipeline/` 경로만 내놓는지 확인합니다.

## 저장소 규칙과의 관계

`CLAUDE.md` 4절은 모든 로직이 `rag/` 아래에 있고 파이프라인이 다섯 개라고 적고 있습니다.
이 패키지는 그 밖에 있는 여섯 번째 흐름입니다. 팀 파이프라인을 바꾸지 않으려고 일부러 분리했으며,
`CLAUDE.md` · `AGENTS.md` 는 고치지 않았습니다.
