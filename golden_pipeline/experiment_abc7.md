# abc7 — 일곱 주제 A · B · C 비교 실험

골든 데이터 생성 방식 A (주제 전용 프롬프트 + 자기 개선), B (고정 프롬프트), C (사람이 웹 Pro 채팅으로 만든 결과)를
같은 근거 묶음 · 같은 독립 검증기로 일곱 주제 모두에서 작게 견줍니다.
비교 대상은 데이터셋 생성 방식이고 RAG 답변 시스템이 아닙니다. 출시본 · 분할은 만들지 않습니다.

## 1. 고정한 근거 계획

```
golden_pipeline\golden.cmd plan abc7-pool v11-20261014 --count numeric 30 --count table 30 --count condition 30 --count comparison 30 --count multi_hop 30 --count unanswerable 30 --count false_premise 30 --max-context-chars 4000
golden_pipeline\golden.cmd freeze abc7 abc7-pool
golden_pipeline\golden.cmd pro-packets abc7
```

- `abc7-pool` 은 주제마다 묶음 30개를 기존 규칙대로 고른 큰 계획입니다.
- `freeze` 는 그 차례대로 주제마다 train 6 · validation 2 · held-out 2 묶음(층화 10개)을 고릅니다.
  몫은 자기 개선과 같은 해시 나눔(`adoption.split`)이라, A loop 가 실제로 쓰는 몫과 같습니다.
  몫이 하나라도 모자라면 계획을 쓰지 않고 멈춥니다. 일곱 주제 모두 6 · 2 · 2 를 채웠습니다.
- 고정 기록은 `outputs/experiments/abc7/freeze.json` 입니다.
  `freeze` 는 근거 manifest 까지 다 읽은 뒤 고정 기록을 먼저, 실험 계획을 맨 나중에 내놓습니다. 그래서 실험 계획이 있으면 그 고정 기록도 있습니다.
  도중에 실패하면 둘 다 남기지 않아, 원인을 고친 뒤 같은 명령으로 다시 고정합니다. 이미 있는 계획 id 는 덮지 않고 멈춥니다.

| 항목 | SHA-256 |
|---|---|
| v11 `manifest.json` (근거 run `v11-20261014`) | `34905d57…c539` |
| 큰 계획 `abc7-pool` | `ccbabaca…82c9` |
| 실험 계획 `abc7` | `8e8f5dd5…0b52` |
| 프롬프트 `B.txt` · `C.txt` · `validator.txt` · `judge.txt` | `587776a3…` · `ce1ef8e1…` · `ed21685b…` · `a5b78950…` |

주제 명세 · A 프롬프트 파일별 해시와 몫별 묶음 id 는 `freeze.json` 에 모두 있습니다.

## 2. 실험 상태 분리

`--experiment abc7` 을 준 명령은 카탈로그 · run · 실패 기록 · loop 를 `outputs/experiments/abc7/` 아래에만 씁니다.
그래서 지난 실패 기록(`failure_memory`), 지난 통과 항목(중복 검사), 지난 근거 묶음 소유(카탈로그)가 어느 방식도 돕거나 막지 않습니다.
A 의 round 1 은 실패 기록 없이 시작하고, round 2 부터 이 실험의 round 1 실패만 읽습니다.
근거 run 과 계획은 함께 읽기만 합니다. 검증 기준(검증기 · 판정기 프롬프트, `validation-7`, 난도 규칙, 주제 명세)은 바꾸지 않았습니다.
validation · held-out 묶음의 결과는 기존 loop 규칙대로 실패 기록과 중복 검사에 들어가지 않습니다.

B 는 `run --method B --part train` 으로 A 의 round 1 과 같은 train 묶음 6개만 부릅니다.
C 의 Pro 프롬프트도 같은 6개 묶음과 같은 컨텍스트를 받습니다 (`prompts/C.txt`: B 처럼 고정 글에 주제 명세만 넣고, A 의 예방 규칙은 넣지 않음).

## 3. 실험 장부 (지출 상한)

run 마다의 `--budget` 은 호출 묶음 사이에서만 보므로 함께 날아가는 호출 · 끊긴 호출의 비용을 막지 못합니다.
그래서 `--experiment` 명령의 모든 API 호출은 `outputs/experiments/abc7/ledger.jsonl` 장부를 거칩니다 (`experiment.Ledger`).

- 보내기 전에 최악 비용을 잡아 둡니다: 입력은 UTF-8 바이트 수(토큰 수의 상한) + 메시지마다 16, 출력은 `max_completion_tokens` (추론 토큰 포함 상한).
  확정 비용(정산한 비용 + 아직 정산하지 못한 잡아 둔 비용)에 이 호출의 최악 비용을 더해 상한을 넘으면 보내지 않고 멈춥니다 (`BudgetExceeded`).
  함께 보낸 다른 호출이 이미 정산됐으면 그 출력 · 판정은 run 에 남고, run 은 `ceiling` 상태로 멈춥니다. 거절된 묶음은 출력이 없고 거절된 후보는 pending 으로 남습니다.
  검증 호출은 출력까지 검증 기록에 남깁니다. 한 후보의 여러 호출 중 뒤 호출이 거절되면, `resume` 은 그 후보의 이미 정산된 호출을 다시 사지 않고 남은 출력을 씁니다.
  같은 요청을 보낸 다른 후보의 출력은 쓰지 않습니다. 출력은 후보마다, 같은 요청은 기록된 차례대로 꺼냅니다.
  호출 수 한도(`--max-calls`)에는 다시 쓸 정산된 검증기 호출을 빼고, 아직 사야 할 호출만 셉니다.
  검증기가 보낼 요청을 다시 만들어 기록의 요청 SHA-256 과 맞추므로, 호출 기록이 언제 쓰였든 같은 방식으로 셉니다.
  출시(`release`)는 판정을 다 해야 쓰므로 실험에서는 시작하지 않습니다.
- 응답이 오면 응답의 토큰 수로 정산합니다. 캐시 입력 할인은 빼고 모두 입력 단가로 셉니다.
- 429 는 처리되지 않은 요청이라 잡아 둔 비용을 풀고 다시 보냅니다. 연결 오류 · 시간 초과 · 5xx 는 청구됐을 수 있어 잡아 둔 비용을 그대로 남기고(`uncertain`), 새로 잡아 다시 보냅니다. 그 밖의 오류는 잡아 둔 채 멈춥니다.
- SDK 안의 다시 시도는 끕니다 (`max_retries=0`). 장부가 모르는 다시 보내기를 없애기 위해서입니다.
- 장부는 명령 · 방식 · 이어 돌기가 모두 함께 씁니다. 두 명령이 함께 열지 못하도록 `ledger.lock` 을 둡니다.
- 승인한 상한 · 출력 상한 · 단가는 `configs/experiments/abc7.json` 에 둡니다. 이 파일이 없으면 OpenAI 클라이언트를 열기 전에 멈춥니다.
  상한 · 단가가 0 보다 큰 수가 아니거나 출력 상한이 1 이상의 정수가 아니면 최악 비용을 잡을 수 없어 마찬가지로 멈춥니다.

## 4. 비용 어림 (승인 전)

```
golden_pipeline\golden.cmd estimate abc7 --price 0.25 2
```

단가는 2026-10-18 OpenAI 공식 가격표 Standard 의 `gpt-5-mini` (입력 0.25, 출력 2.00 USD / 100만 토큰)이고, `GET /v1/models` 에서 `gpt-5-mini` 가 쓸 수 있음을 확인했습니다.
호출당 토큰과 출력당 검증 호출 수 · 통과율은 지난 A run(gpt-5-mini, 생성 low · 검증 high)의 실제 기록입니다.
unanswerable 검증 호출 수는 고정한 묶음의 대상 문서를 실제로 나눈 묶음 수(1~3)로 봅니다.

| 주제 | 생성 호출 (기댓값) | 검증 호출 (기댓값) | 기댓값 USD | 높은 경우 USD |
|---|---|---|---|---|
| numeric | 21.9 | 27.5 | 0.129 | 0.582 |
| table | 24.7 | 11.5 | 0.079 | 0.371 |
| condition | 21.9 | 35.6 | 0.243 | 1.027 |
| comparison | 24.1 | 20.8 | 0.140 | 0.597 |
| multi_hop | 24.8 | 61.9 | 0.235 | 1.294 |
| unanswerable | 26.8 | 14.4 | 0.227 | 2.442 |
| false_premise | 27.3 | 23.2 | 0.175 | 0.538 |
| 합계 | | | **1.23** | 6.85 |

높은 경우는 A 의 세 round 가 train 묶음을 모두 다시 부르고 held-out 까지 재며, 모든 호출의 출력이 지난 기록의 99 백분위일 때라 함께 일어나기 어렵습니다.
그 경우에도 장부 상한에서 멈춥니다. 방식별 기댓값은 A 0.78 · B 0.25 · C 검증 0.19 USD 입니다.

제안: 상한 3.00 USD (목표 2.40 + 예비 0.60), 호출마다 출력 상한 20,000 토큰 (지난 검증 호출 최대 17,125), 명령별 한도는 아래 5절.
기존 Pro 구독은 비용에 넣지 않습니다. 승인 상태는 6절에 남깁니다.

## 5. 실행 명령

주제 `T` 마다 (아래 `%G%` 는 `golden_pipeline\golden.cmd --experiment abc7`, 모델 인자는 `--model gpt-5-mini --price 0.25 2`):

```
%G% run --topic T --method B --plan abc7 --id b1 --part train --model gpt-5-mini --reasoning-effort low --price 0.25 2 --max-calls 6 --budget 0.02
%G% audit --topic T --method B --id b1 --model gpt-5-mini --reasoning-effort high --price 0.25 2 --max-calls <B 검증 호출> --budget <B 검증 USD>
%G% run --topic T --method A --plan abc7 --id a1 --model gpt-5-mini --reasoning-effort low --price 0.25 2 --max-calls <A 호출> --budget <A USD> --max-rounds 3 --validator-model gpt-5-mini --validator-reasoning-effort high --validator-price 0.25 2
%G% import --topic T --plan abc7 --id c1 --export <T.jsonl> --sidecar <T.sidecar.json>
%G% audit --topic T --method C --id c1 --model gpt-5-mini --reasoning-effort high --price 0.25 2 --max-calls <C 검증 호출> --budget <C 검증 USD>
```

| 주제 | A 호출 · USD | B 생성 호출 · USD | B 검증 호출 · USD | C 검증 호출 · USD |
|---|---|---|---|---|
| numeric | 90 · 0.13 | 6 · 0.02 | 20 · 0.04 | 20 · 0.04 |
| table | 70 · 0.10 | 6 · 0.02 | 15 · 0.02 | 15 · 0.02 |
| condition | 110 · 0.24 | 6 · 0.02 | 25 · 0.08 | 25 · 0.08 |
| comparison | 90 · 0.15 | 6 · 0.02 | 20 · 0.03 | 20 · 0.03 |
| multi_hop | 160 · 0.25 | 6 · 0.02 | 45 · 0.07 | 45 · 0.07 |
| unanswerable | 110 · 0.26 | 6 · 0.02 | 40 · 0.06 | 40 · 0.06 |
| false_premise | 100 · 0.19 | 6 · 0.02 | 25 · 0.05 | 25 · 0.05 |
| 합계 | 730 · 1.32 | 42 · 0.14 | 190 · 0.35 | 190 · 0.35 |

명령별 한도의 합은 1,152 호출 · 2.16 USD 이고, 실험 장부가 3.00 USD 에서 모든 명령을 함께 막습니다.

## 6. 승인

2026-10-18 사용자가 승인했습니다: 모델 `gpt-5-mini`, 생성 추론 `low`, 검증기 · 판정기 추론 `high`,
호출마다 출력 상한 20,000 토큰, 기댓값 1.23 USD, 명령별 한도 합 1,152 호출 · 2.16 USD, 실험 상한 3.00 USD (목표 2.40 + 예비 0.60).
승인한 값은 `configs/experiments/abc7.json` 입니다.

## 7. C (Pro) 진행 방법

`outputs/experiments/abc7/pro/` 에 주제마다 붙여 넣을 프롬프트 `{주제}.txt` 와 빈 관측 기록 `{주제}.sidecar.json` 이 있습니다.

1. 주제마다 새 채팅을 엽니다. 메모리 · 맞춤 지침 · 웹 검색 · 파일 · 다른 도구를 끕니다.
2. `{주제}.txt` 전체를 한 메시지로 붙여 넣습니다. 다른 글, A · B 의 답, 검증 결과는 넣지 않습니다.
3. 첫 응답을 그대로 둡니다. 다시 생성하거나 고쳐 달라고 하지 않습니다.
4. 응답 전체를 `pro/returned/{주제}.response.txt` 에, 코드 블록 안의 JSON 줄만 `pro/returned/{주제}.jsonl` 에 UTF-8 로 저장합니다.
   형식이 어긋나도 고치지 않고 그대로 저장합니다. 고칠 일이 있으면 원본은 그대로 두고 고친 내용을 따로 기록합니다.
5. `{주제}.sidecar.json` 을 `pro/returned/` 에 복사해 채웁니다. 필드는 다섯 개뿐입니다:
   `model_label` (화면에 보인 모델 이름 그대로), `run_date`, `provided_files` (예: `none`), `tool_use` (예: `none`), `input_limits` (모르면 빈 값).
6. 주제마다 걸린 시간(분)은 `pro/returned/handling_minutes.json` 에 `{"numeric": 4, ...}` 로 따로 적습니다.

가져오기는 5절의 `import` 이고, 묶음이 빠졌거나 계획에 없는 줄은 그대로 거절 행으로 남습니다.
`pro-packets` 는 계획 · `prompts/C.txt` · 주제 명세가 고정 기록(`freeze.json`)의 SHA-256 과 다르면 쓰지 않습니다.

## 8. 블라인드 검토와 지표

```
golden_pipeline\golden.cmd review-packets abc7
golden_pipeline\golden.cmd compare abc7
```

- `review-packets` 는 주제 · 방식(A round 1 · B · C)마다 첫 시도 출력 둘을 고릅니다. 표본 규칙: 판정 층을
  `auto_validated` → `rejected` → `candidate`(pending) 차례로 하나씩, 층 안에서는 고정 시드(20261018)로 무작위.
  거절이 있으면 반드시 하나 들어가므로 표본은 거절이 많게 치우친 것이고, 전체 품질의 추정이 아닙니다.
  항목이 되지 못한 출력(JSON 아님 등)은 질문 · 답이 없어 표본에 넣지 않습니다.
- `review/packet.md` 에는 주제 · 질문 · 답 · 인용 근거만 보이고, 방식 · run · 판정 · 층은 `review/key.json` 에만 있습니다.
  `review/judgments.csv` 에 출력마다 `evidence_support` · `answer_correct` · `topic_fit` · `useful` 을 Y · N 으로 적습니다.
  표본의 모든 출력을 꼭 한 번씩 판정해야 잽니다. 빠지거나 겹치거나 표본에 없는 행이 있으면 검토한 품질은 값 없음입니다.
  `review_id` 나 네 판정 열 가운데 하나가 머리글에 없거나, 칸이 모자란 행이 있거나, 파일이 비어도 값 없음입니다. `note` 열은 없어도 됩니다.
  엑셀에서 고쳤다면 'CSV UTF-8' 로 저장합니다. UTF-8 로 읽을 수 없거나 CSV 로 읽을 수 없는 파일도 값 없음입니다.
- `compare` 는 `comparison.json` 에 주제마다와 전체의 지표를 분자 · 분모와 함께 씁니다.
- `compare` 와 `review-packets` 는 먼저 비교할 run (A loop 의 round 전부 · B · C) 이 고정 기록대로 만들어졌는지 봅니다.
  계획 · 그 SHA-256 · 주제 명세, A · B 의 생성 프롬프트, 검증기 · 판정기 프롬프트가 같아야 하고, 출력이 train 몫 밖의 묶음을 가리키지 않아야 하며,
  A · B 의 생성 설정과 세 방식의 검증 설정이 같아야 합니다 (한도 · 예산은 빼고). 하나라도 어긋나면 쓰지 않고 멈춥니다.
  `review-packets` 는 인용 근거를 계획 파일에서 읽으므로, 지금 계획 파일의 SHA-256 도 고정 기록과 같아야 검토지를 씁니다.

| 지표 | 분자 | 분모 |
|---|---|---|
| 쓸 수 있는 묶음 커버리지 | `auto_validated` 질문이 하나라도 있는 배정 묶음 | 배정한 비교 묶음 (train 6) |
| 출력 수용률 | `auto_validated` 질문 | 돌아온 모든 출력 (JSON 아님 · 필드 오류 포함) |
| 전달 완결성 | 출력이 하나라도 돌아온 배정 묶음 | 배정한 묶음 |
| 검토한 품질 | 네 검사를 모두 통과한 표본 출력 | 검토한 출력 (방식 · 주제 · 층별) |
| 유일한 유효 질문당 API 비용 | 생성 · 검증 · 판정 · 채택 · held-out · 다시 보낸 호출까지 그 방식의 비용 | 공백 · 쉼표만 다른 것을 하나로 센 `auto_validated` 질문. 0 이면 값 없음 |

거절 이유(실패 코드)와 pending 수, A 의 held-out 통과 차이(%p), 장부 정산 비용과 run 기록 비용의 차이도 함께 남깁니다.
C 의 생성 토큰 · 비용 · 총비용 · 유효 질문당 총비용은 웹이라 `unobserved` 이고, C 는 검증 비용과 사용자 처리 시간을 따로 보고합니다.

## 9. 결과 (2026-10-18)

`outputs/experiments/abc7/comparison.json` 의 값입니다. 비교 묶음은 주제마다 train 6개, 전체 42개입니다.
표본이 작아 차이는 방향만 보여 주며, 결론이 나지 않을 수 있습니다.

### 9.1 첫 시도: 쓸 수 있는 묶음 커버리지 (A round 1 · B · C)

| 주제 | A1 | B | C |
|---|---|---|---|
| numeric | 6/6 | 3/6 | 5/6 |
| table | 3/6 | 2/6 | 4/6 |
| condition | 3/6 | 1/6 | 3/6 |
| comparison | 2/6 | 3/6 | 6/6 |
| multi_hop | 3/6 | 2/6 | 2/6 |
| unanswerable | 0/6 | 0/6 | 0/6 |
| false_premise | 4/6 | 3/6 | 0/6 |
| 전체 | 21/42 (50%) | 14/42 (33%) | 20/42 (48%) |

- 묶음마다 질문 하나를 요청했으므로 출력 수용률도 같은 값입니다 (A1 21/42, B 14/42, C 20/42).
- 전달 완결성은 세 방식 모두 42/42 이고, pending 은 0 입니다.
- 거절 이유 (전체):
  - A1: type_mismatch 5, present_in_target 5, missing_condition 3, not_multi_hop 2, 그 밖 각 1.
  - B: type_mismatch 9, present_in_target 5, missing_condition 3, single_chunk 3, table_relation 2, premise_in_document 2, 그 밖 각 1.
  - C: present_in_target 6, missing_condition 4, answer_mismatch 3, type_mismatch 3, single_chunk 2, 그 밖 각 1.
- unanswerable 은 세 방식 모두 0 이고, 거절은 대부분 present_in_target (대상 문서에 답이 있음) 입니다.
- C 의 false_premise 0/6 은 type_mismatch 3, answer_mismatch 2, premise_in_document 1 입니다.

### 9.2 A 의 전체 흐름 (최대 3 round)

| 주제 | 멈춘 이유 | 커버리지 A1 → 전체 | 전체 수용률 | 호출 | USD |
|---|---|---|---|---|---|
| numeric | no_open_bundles | 6/6 → 6/6 | 6/6 | 14 | 0.0229 |
| table | max_rounds | 3/6 → 4/6 | 4/12 | 29 | 0.0431 |
| condition | no_open_bundles | 3/6 → 6/6 | 6/9 | 24 | 0.0656 |
| comparison | max_rounds | 2/6 → 3/6 | 3/14 | 29 | 0.0946 |
| multi_hop | max_rounds | 3/6 → 5/6 | 5/12 | 60 | 0.1690 |
| unanswerable | max_rounds | 0/6 → 2/6 | 2/17 | 41 | 0.2977 |
| false_premise | max_rounds | 4/6 → 4/6 | 4/10 | 30 | 0.0980 |
| 전체 | | 21/42 → 30/42 | 30/80 (38%) | 227 | 0.7911 |

- 늘어난 9개 묶음은 같은 묶음을 다시 시도해 얻은 것이고, 학습했다는 증거가 아닙니다.
- 어느 주제에서도 예방 규칙이 채택되지 않았습니다.
- 그래서 held-out 기준선과 최종 정책 측정은 하지 않았고 (`채택한 예방 규칙이 없습니다`), held-out 커버리지 변화(%p)는 측정값이 없습니다.
- A 가 개선되었다는 근거는 이 실험에 없습니다.
- unanswerable 루프는 0.2977 USD 로 명령 한도 0.26 USD 를 넘었습니다. 기존 한도 검사는 배치 사이에만 하기 때문이며, 실험 장부 상한 안입니다.

### 9.3 비용 (gpt-5-mini, 실제 장부)

| 주제 | A1 USD · 유효 질문당 | B USD · 유효 질문당 | A 전체 USD · 유효 질문당 | C 검증 USD |
|---|---|---|---|---|
| numeric | 0.0229 · 0.0038 | 0.0163 · 0.0054 | 0.0229 · 0.0038 | 0.0247 |
| table | 0.0120 · 0.0040 | 0.0083 · 0.0042 | 0.0431 · 0.0108 | 0.0092 |
| condition | 0.0229 · 0.0076 | 0.0141 · 0.0141 | 0.0656 · 0.0109 | 0.0202 |
| comparison | 0.0235 · 0.0118 | 0.0497 · 0.0166 | 0.0946 · 0.0315 | 0.0490 |
| multi_hop | 0.0516 · 0.0172 | 0.0295 · 0.0147 | 0.1690 · 0.0338 | 0.0858 |
| unanswerable | 0.0773 · 값 없음 (0개) | 0.0612 · 값 없음 (0개) | 0.2977 · 0.1489 | 0.0216 |
| false_premise | 0.0438 · 0.0109 | 0.0195 · 0.0065 | 0.0980 · 0.0245 | 0.0172 |
| 전체 | 0.2539 · 0.0121 (21) | 0.1986 · 0.0142 (14) | 0.7911 · 0.0264 (30) | 0.2277 |

- 비용에는 생성 · 검증 · 판정 · 다시 보낸 호출이 모두 들어갑니다. A 전체는 루프가 기록한 모든 호출이고, A1 은 그 안의 첫 round 몫입니다.
- 유효 질문이 0 이면 비율은 0 이 아니라 값 없음입니다.
- 장부 정산: 예약 355건 = 정산 355건, uncertain 0건.
  - 정산 1.2173 USD = B 0.1986 + A 전체 0.7911 + C 검증 0.2277.
  - run 기록 합과의 차이는 0.
  - 승인 상한 3.00 USD 의 41%, 목표 2.40 USD 안입니다.

### 9.4 C (Pro) 처리

- 모델: 사용자가 가져오기 뒤에 알려 준 화면 표시 이름 `gpt 6 pro` 입니다 (`pro/reported-c1.json`).
  관측 기록(sidecar)은 돌아오지 않아 run manifest 의 다섯 필드는 비어 있습니다 (`pro/sidecar-c1.json`). API 대응 모델은 추정하지 않습니다.
- 가져오기: 사용자가 저장한 원래 응답 `pro/returned/{주제}.response.txt` 를 그대로 `import` 에 넣었습니다. 형식을 고친 것은 없습니다.
  빠진 묶음도 없습니다 (전달 42/42). 항목이 되지 못한 줄은 거절 행(schema 1)으로 남았습니다.
- 사용자 처리 시간은 주제마다 약 3분, 전체 약 21분입니다 (사용자 보고, `pro/returned/handling_minutes.json`).
- C 의 생성 토큰 · 생성 비용 · 총비용 · 유효 질문당 총비용은 웹 채팅이라 관측하지 못했습니다 (`unobserved`). 측정한 것은 검증 비용 0.2277 USD 뿐입니다.

### 9.5 블라인드 검토 (에이전트 판정)

- 사용자가 블라인드 검토를 에이전트에게 맡겼습니다. 아래 값은 사람이 확인한 품질이 아니라 에이전트가 판정한 품질입니다.
- 에이전트는 `review/key.json` 을 열지 않고 `review/packet.md` 만 보고 `review/judgments.csv` 를 채웠습니다.
- 다만 에이전트는 가져오기 때 C 의 numeric · table · unanswerable 원래 응답 일부를 이미 보았으므로, C 에 대한 눈가림은 완전하지 않습니다.
- unanswerable 두 항목(R39 · R42)은 대상 문서 원문을 검색해 확인했습니다.
- 네 검사를 모두 통과한 비율:

| 방식 | 전체 | 층: auto_validated | 층: rejected |
|---|---|---|---|
| A1 | 8/14 | 6/8 | 2/6 |
| B | 5/14 | 3/7 | 2/7 |
| C | 8/14 | 3/6 | 5/8 |

주제별로 네 검사를 모두 통과한 수 (각 /2):

| 주제 | A1 | B | C |
|---|---|---|---|
| numeric | 2 | 2 | 2 |
| table | 1 | 0 | 0 |
| condition | 1 | 1 | 2 |
| comparison | 0 | 0 | 0 |
| multi_hop | 1 | 0 | 2 |
| unanswerable | 1 | 1 | 0 |
| false_premise | 2 | 1 | 2 |

- 표본은 거절이 많게 치우쳐 있으므로 (8절 표본 규칙), 위 비율은 모집단 품질의 추정이 아닙니다.
- C 는 검증기가 거절한 출력 8개 중 5개가 네 검사를 통과했습니다. 네 검사는 검증기의 주제별 형식 계약(type_mismatch 등)을 보지 않기 때문입니다.
- 실패한 검사는 주로 useful (개인 연락처 · 목차 · 형식 문구) 과 topic_fit (억지 비교 · 억지 다단계) 입니다.
- evidence_support 는 42개 모두 Y 입니다.

### 9.6 해석

- 첫 시도 커버리지는 A1 (50%) ≈ C (48%) > B (33%) 이지만, 주제마다 순서가 바뀝니다.
  - C 가 comparison · table 에서 앞섭니다.
  - A1 이 numeric · false_premise 에서 앞섭니다.
  - 주제마다 6개 묶음이라 한 묶음이 17%p 입니다. 이 차이들은 방향만 보여 줍니다.
- 주제별 프롬프트(A1)가 고정 프롬프트(B)보다 나은 방향이고, 에이전트 판정 품질도 같은 방향입니다 (8/14 대 5/14).
- A 의 반복은 커버리지를 30/42 로 올렸지만, 비용이 0.25 → 0.79 USD 로 약 3배가 되었습니다.
  - 예방 규칙이 하나도 채택되지 않아, 이것은 개선이 아니라 재시도로 얻은 수확입니다.
  - held-out 개선은 측정되지 않았습니다.
- C 는 생성 API 비용 없이 (검증 0.23 USD 만) 사용자 시간 약 21분으로 A1 과 비슷한 커버리지를 냈습니다.
  - 그러나 C 는 다른 모델(`gpt 6 pro`)과 다른 인터페이스(웹 채팅, 한 메시지에 주제의 6묶음)를 썼습니다.
  - 따라서 C 와 A · B 의 차이에는 방식의 차이와 모델 · 인터페이스 차이가 섞여 있습니다 (교란).
- unanswerable 은 세 방식 모두 첫 시도에 실패했습니다.
- 결론: 이 표본으로는 어느 방식이 확실히 낫다고 말할 수 없습니다. A1 과 C 가 B 보다 낫다는 방향만 보입니다.

### 9.7 다시 돌리기

5절의 명령을 주제마다 차례로 실행한 뒤 아래 명령을 실행합니다. 검토 판정은 `review/judgments.csv` 에 들어 있습니다.

```
golden_pipeline\golden.cmd review-packets abc7
golden_pipeline\golden.cmd compare abc7
```
