# ⑤ 평가 — 공식 · 재실행 · 데이터셋

README의 [평가](../README.md#평가) 요약을 자세히 적은 문서입니다.

## IR 공식과 제외율

### A. 순위 평가

중복 제거·토큰 예산 패킹 전의 후보 목록을 사용합니다. k는 5, 10, 20입니다.

| 수준 | Recall@k | MRR@k |
| --- | --- | --- |
| 문서 | top-k 청크가 속한 골든 문서 집합 크기 / 전체 골든 문서 집합 크기 | 골든 문서의 청크가 처음 나온 청크 위치의 역수 |
| 청크 | top-k에 든 골든 청크 집합 크기 / 전체 골든 청크 집합 크기 | 골든 청크가 처음 나온 위치의 역수 |

- MRR은 k 안에 적중이 없으면 0입니다. 문서 순위를 만들려고 청크를 먼저 문서별로 중복 제거하지 않습니다.
- 각 수준에서 fused, dense-only, BM25-only Recall@k와 exact-code membership Recall을 한 표로 봅니다.
- 성분별 순위는 원점수 순서이며 여러 기관이면 실제 검색처럼 기관별 목록을 번갈아 섞습니다. 가중치가 0인 성분은 후보를 내지 않습니다.
- exact-code는 코드 일치 후보 집합 속 골든 문서/청크 비율이며 k나 MRR을 붙이지 않습니다.

### B. 컨텍스트 평가

`context_chunk_ids`를 사용합니다.

- Evidence Coverage는 실제 보낸 골든 청크 수 / 전체 골든 청크 수, `full_evidence_coverage`는 모든 골든 청크를 보냈으면 1, 아니면 0입니다.
- 단일 근거와 다중 근거(`multi_hop`, `comparison` 또는 복수 근거 항목)를 별도로 보고합니다. MRR은 첫 근거의 위치를 볼 뿐 다중 근거의 완전성을 나타내지 않습니다.

### 채점 대상과 제외율

- 청크 평가는 모든 근거 항목에 청크 라벨이 있는 질문만 계산합니다. 일부 라벨만 있는 질문의 분모를 줄여 채점하지 않습니다. 문서도 모든 근거가 문서에 연결된 질문만 계산합니다.
- 각 주제의 전체/일부/미라벨 질문 수와 mapping exclusion rate = (일부 + 미라벨) / 답할 수 있는 골든 질문 수를 `retrieval_exclusions.csv`에 저장합니다. 성분 표에도 채점 질문 수와 제외율을 표시합니다.
- `unanswerable`과 골든 근거 없는 YAML은 IR에서 제외하고 각각 셉니다.
- `retrieval.csv`는 질문별 IR 지표·Evidence Coverage·`key_facts_in_context`·검색 설정을, `generation.csv`는 `key_facts_in_answer`를 담습니다. `grounding.csv`와 `end_to_end.csv`의 열은 유지합니다.

## dev 검색 전용 재실행

저장된 rewrite가 있는 dev 답변 파일에서 검색 설정만 바꿀 때 사용합니다. 재작성·답변 생성·심판 API를 호출하지 않습니다.

- 새 폴더의 answers는 05 Retrieval이 원본과 동일하게 읽으며 실제 사용한 청크 파일·검색 설정·k·rewrite 재사용 여부(True)를 기록합니다.
- 기존 답변은 재생성하지 않으므로 이 파일의 Generation·Grounding·End-to-End를 새 설정의 생성 성능으로 해석하지 마세요.
- 원래 Langfuse 추적에 실험 점수가 덮이지 않도록 새 행의 trace_id는 비웁니다.

```python
from rag.config import ARTIFACTS, load_config
from rag.retrieval.retrieval import HybridIndex
from rag.evaluation.evaluation import rerun_retrieval, evaluate_retrieval
from rag.evaluation.ir import component_table, coverage_table

cfg = load_config()
cfg["retrieval"].update(fusion="minmax", dense_weight=0.5, candidate_k=50, token_budget=2500)
path = ARTIFACTS / "dev_rerun" / "answers.jsonl"
rerun_retrieval(ARTIFACTS / "answers.jsonl", path, HybridIndex(ARTIFACTS, cfg))
scores = evaluate_retrieval(path, cfg)
display(component_table(scores, "doc"))
display(component_table(scores, "chunk"))
display(coverage_table(scores))
```

유료 확인은 모든 주제를 포함한 dev 30문항으로 제한합니다.
실행 전에 config 단가로 04 rewrite+answer와 05 두 심판의 견적을 표시하고 승인을 받은 뒤 실행합니다.
실제 비용은 해당 실행의 `api_usage.csv`로 계산합니다. 이전 per-evaluation 행의 질문당 심판 비용은 historical로 표시하며, 새 30문항과 질문·시점이 다르므로 동일 질문의 품질 비교로 해석하지 않습니다.

[30문항 표본 보고서](eval_ir_sample.md)에 표본 구성·라벨 제외율·비용 견적·historical 기준과 실제 실행 결과를 기록합니다.
보고서의 유료 표본은 dev `ab49a65`의 대화 기반 재작성·재작성 query 라우팅 통합 전 기록입니다. 통합 후 검색 보존 검사는 별도 절에 기록했으며, 추가 유료 평가를 실행한 결과가 아닙니다.

## 최종 test 평가 — 설정을 고정한 뒤 한 번

dev는 검색·생성 설정 조절용입니다. test 검색·생성 결과를 보고 설정을 조절하지 않습니다.

1. 최종 설정과 활성 chunks/index를 고정하고, 03의 첫 import·입력 경로 셀을 실행한 뒤 다음 코드로 test 전용 평가셋을 만듭니다. 근거 연결 규칙은 dev와 동일하며 원본 골든 파일을 바꾸지 않습니다.

   ```python
   test_items = load_eval_items(["eval/golden/test.jsonl"])
   test_labelled = label_evidence(test_items, chunks, raw_dir, package_dir, input_path)
   test_eval_set, test_report = check_eval_items(test_labelled)
   write_jsonl(test_eval_set, ARTIFACTS / "test_eval_set.jsonl")
   ```

2. 04의 `eval_set` 입력을 `test_eval_set.jsonl`, 답변 출력을 `artifacts/test/answers.jsonl`로 바꿉니다.
3. 고정한 02 설정으로 04를 한 번 실행하고, 05의 `ANSWERS`를 그 test 파일로 지정해 네 평가를 한 번 실행합니다.
4. 네 CSV와 제외율·사용량을 최종 결과로 보관합니다. test를 dev 검색 전용 재실행 셀에 넣지 않습니다.

## 로컬 평가 입력과 OCR 캡션 복원

평가 자료와 저장된 OCR 캡션은 Git의 현재 트리에서 내려받지 않습니다. 로컬 입력을 먼저 복원합니다.

```powershell
.venv\Scripts\python -m rag.validation.local_inputs
```

- 기존 전체 checkout에는 추적 해제 직전의 로컬 Git 객체에서 복원합니다. 기존 로컬 원본이 있으면 먼저 사용합니다. 네트워크를 사용하지 않으며 원본을 삭제하거나 덮어쓰지 않습니다. manifest의 dev/test 바이트 지문이 일치해야 새 파일을 만듭니다.
- 새로운 얕은 clone이나 정리된 이력에는 소유자가 제공한 비공개 묶음이 필요합니다.

  ```powershell
  .venv\Scripts\python -m rag.validation.local_inputs --from-directory C:/private/evaluation-bundle
  ```

- 평가 묶음 구조는 `golden/dev.jsonl`, `golden/test.jsonl`, `golden/manifest.json`, `eval_questions.yaml`입니다. OCR 캡션은 묶음 루트의 `ocr_captions.jsonl`로 제공합니다.
- 같은 `--from-directory` 명령으로 평가 전용·OCR 전용·둘 다 포함한 묶음을 복원할 수 있습니다. 평가 파일이 하나라도 있으면 평가 묶음 전체와 manifest 검증이 필요합니다.
- 파일은 무시된 `artifacts/local_inputs/`에 보관합니다. 기존 config의 논리 경로는 공통 로더가 이 로컬 경로로 연결하며, OCR 소비자는 평가 릴리스 없이 캡션만 복원합니다.
- test는 복원 중 바이트 지문만 검사하며 검색·튜닝하지 않습니다. 필요한 자료가 없으면 복원 명령을 안내하고 멈춥니다.

주제별 핵심 사실은 숫자·단위, 비교 선택, 조건 또는 표 칸 값에서 얻습니다. 다중 근거는 독립적으로 확인 가능한 사실을 사용합니다. 부분 라벨과 누락은 사유별로 분리합니다.

## 평가 데이터셋의 집계 (정리 전 측정)

| 입력 | 문서 | 문항 | 이전 분할과 추가 유형 |
| --- | ---: | ---: | --- |
| golden dev `final6` | 30 | 408 | `final2` 396 + unanswerable 8 + false_premise 4 |
| golden test `final6` | 68 | 943 | `final2` 930 + unanswerable 8 + false_premise 5 |

다중 근거 24문항은 핵심 사실 점검에서 제외되어 dev 384문항이 남았고, YAML 1문항과 함께 평가셋을 구성했습니다.
`manifest.json`은 두 분할의 개수와 해시를 기록합니다. 원시 릴리스·직접 작성한 질문·멀티턴 대화는 위 로컬 복원 경로로만 제공합니다.
test는 03의 라벨 품질 집계에만 사용했으며 검색·생성·설정 선택에 쓰지 않았습니다.

## 골든 문서·청크 라벨 연결 (03)

### 입력과 문서 신원

03에는 현재 `artifacts/chunks.jsonl`과 `data/RFP_Preprocessing_Final_v11_Team/final_elements.jsonl`이 필요합니다.

- 파서 출력은 `config.yaml`의 `paths.input`이 폴더·단일 파일이면 원본을 그 자리에서 읽습니다. ZIP이면 현재 아카이브의 항목만 열거해 01이 `artifacts/raw/`에 푼 정확한 위치를 찾고, 추출 파일의 SHA-256이 해당 아카이브 항목의 SHA-256과 같을 때만 사용합니다. 중첩 ZIP과 폴더 안 ZIP에도 같은 규칙을 적용합니다.
- 이전 실행의 다른 raw 하위 폴더는 검색하지 않습니다. 추출 파일이 현재 아카이브 본문과 다르거나, 현재 입력의 서로 다른 SHA 둘 이상이 같은 `source` 이름을 가지면 문서 신원을 확정할 수 없어 `doc_unmapped`로 남깁니다.
- 골든 `doc_sha`를 원본 파일의 SHA-256과 맞추고 NFC 파일명으로 현재 청크의 `source/doc_id`를 찾습니다.
- v11 출력은 요소 메타데이터의 원본 `sha256`·`doc_id`가 현재 청크의 `doc_id`와 같고 NFC `source`도 같을 때 연결합니다. 따라서 v11에는 원본 파일이나 `artifacts/raw/`가 필요하지 않습니다.
- 같은 파일명만으로 파서 출력에 v11의 SHA를 적용하지 않으며, 문서 제목이나 골든 청크 ID로 추측하지 않습니다. 입력을 바꾸면 01과 03에서 같은 원본 경로를 사용하세요.

### 골든 본문 복원

- `evidence`는 선택한 근거만, `context`는 선택하지 않은 블록까지 담습니다. 현재 dev는 근거 716항목과 `[E]` 1,400블록입니다. 앞서 가정한 573블록은 현재 파일과 맞지 않습니다.
- 각 참조의 `element_id`와 `location`으로 v11 요소에서 본문을 복원합니다. 글은 요소의 `[start:end]`, 표는 해당 행의 칸을 열 순서로 ` | `로 잇습니다.
- 복원 본문이 context 블록 전체와 일치하는지 확인하고 해당 라벨을 모두 보관합니다. dev 716/716, test 1,639/1,639항목이 확인됐으며, 같은 본문이 여러 블록에 반복된 항목은 각각 14개·26개입니다.
- 참조 순서와 블록 순서를 짝짓거나 근거 전체를 한 본문으로 합치지 않습니다. 이 좌표는 골든 본문 복원에만 사용하며 현재 청크의 좌표로 옮기지 않습니다.

### 청크 라벨 규칙

- 근거와 청크 `body`를 NFC로 정규화하고, `|`를 공백으로 바꾸고 연속 공백을 하나로 줄입니다.
- 정규화한 근거 본문이 같은 문서의 청크 안에 그대로 포함되고 해당 청크 ID가 하나일 때만 라벨을 붙입니다. 유사도 점수는 사용하지 않습니다.
- 정규화 후 20자 미만이거나 일치 청크가 둘 이상인 근거는 문맥 앵커로만 연결합니다. 같은 질문 context의 다른 `[E]` 블록 중 20자 이상인 것이 근거와 함께 든 청크가 정확히 하나일 때 그 청크를 라벨로 씁니다. 표 한 행처럼 짧은 근거를 행이 속한 표의 다른 근거 블록으로 확정하려는 규칙입니다.
- 그래도 정해지지 않으면 문서가 없을 때 `doc_unmapped`, 20자 미만이면 `too_short`, 일치 청크가 없으면 `not_found`, 둘 이상이면 `ambiguous`입니다.
- 20자 하한은 짧은 수·코드·항목 이름만으로 청크를 확정하지 않으려는 고정 규칙이며 test 결과에 맞춰 조절하지 않았습니다.

### 측정 결과 (2026-10-16, 로컬 현재 파서 출력 100문서·18,988청크)

v11 로더의 ID 보존은 코드상 유지되지만, 이 출력에서는 골든의 원래 청크 ID가 dev 0/716·test 0/1,639항목과 일치합니다.

| 분할 | 원본 SHA → 현재 문서 (서로 다른 SHA) | 문서 연결 근거 항목 | 유일 청크 연결 근거 항목 | 질문: 전체 / 일부 / 없음 |
| --- | --- | --- | --- | --- |
| dev | 35/36 (97.22%) | 692/716 (96.65%) | 306/716 (42.74%) | 140 / 125 / 143 |
| test | 69/70 (98.57%) | 1,620/1,639 (98.84%) | 708/1,639 (43.20%) | 328 / 255 / 360 |

| 분할 | 주제 | 근거 항목 | 청크 연결 | doc_unmapped | not_found | ambiguous | too_short | 질문: 전체 / 일부 / 없음 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dev | comparison | 137 | 61 (44.53%) | 7 | 3 | 5 | 61 | 9 / 31 / 16 |
| dev | multi_hop | 190 | 48 (25.26%) | 8 | 14 | 16 | 104 | 5 / 30 / 36 |
| test | comparison | 291 | 142 (48.80%) | 6 | 21 | 13 | 109 | 31 / 54 / 43 |
| test | multi_hop | 463 | 141 (30.45%) | 4 | 34 | 16 | 268 | 21 / 71 / 84 |

전체 dev 실패는 `doc_unmapped` 24 · `not_found` 64 · `ambiguous` 32 · `too_short` 290항목, test 실패는 각각 19 · 188 · 50 · 674항목입니다.

- 미연결 문서 2개의 파일명·SHA 목록은 로컬 `golden_documents.csv`에 보관합니다.
- 질문 대상 문서는 dev 30개·test 68개지만 `unanswerable`이 다른 사업의 근거도 인용하므로 인용 근거 SHA는 36개·70개입니다. 그 인용 근거의 라벨이 질문 대상 문서의 정답 근거라는 뜻은 아닙니다.
- 라벨 품질 집계는 핵심 사실 점검에서 빠지는 질문까지 포함한 전체 골든 분할을 기준으로 합니다.
- 전체 주제별 결과는 03과 `artifacts/golden_mapping.csv`, 문서별 결과는 `golden_documents.csv`, 블록 대응·ID 감사는 `golden_correspondence.csv`에서 확인합니다.

### 03 화면과 저장 결과

- 03에는 seed 42로 고른 dev 근거 최대 30쌍의 골든 본문과 연결한 청크 전체 본문이 나란히 표시됩니다. 라벨된 근거가 30쌍 미만이면 전부 표시하며 0쌍이면 열 이름이 있는 빈 표를 표시합니다. 미연결 사유와 집계는 그대로 저장합니다.
- 이 표들은 03을 실행할 때 확인합니다. 저장소의 노트북은 실행 횟수와 출력을 비워 커밋하며, 로컬 문서 본문과 실행 결과를 노트북에 넣어 게시하지 않습니다. CSV 결과는 `artifacts/`에 보관합니다.
- 입력 경로 회귀 검사는 이전 산출물이 없는 임시 폴더에서 실제 v11 로더 또는 PDF 파서·청킹·저장을 거쳐 03의 보고·평가셋 저장·표본 셀을 실행합니다. v11, 원본 폴더, 단일 파일, ZIP, 중첩 ZIP, ZIP을 포함한 폴더의 여섯 경로를 확인합니다.
- `eval_set.jsonl`에는 점검을 통과한 dev 384문항과 직접 작성한 질문 1문항이 들어 있습니다. dev 문항에는 정답 문서와 정답 근거가 붙어 있고, 근거마다 연결된 청크를 하나로 정했으면 그 청크를, 정하지 못했으면 그 이유를 적어 둡니다. 직접 작성한 질문에는 정답 근거가 없습니다.
- 이 라벨은 03이 고정해 저장하며, 05는 연결 규칙을 바꾸지 않고 해당 라벨 수준의 IR 지표를 계산합니다.
