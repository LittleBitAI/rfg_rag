# Kiwi BM25 토크나이저 dev 검토

집계 결과와 측정 조건은 Git에 보관하고, 원시 질문·정답·근거·OCR 전사와 레코드별 내보내기는 무시된 로컬 `artifacts/`에 보관한다.

복원 출처: 정리 전 `artifacts/review-round2/originals/` 또는 `d7d1682^`. 아래 수치와 검증 기록은 당시 실행의 역사적 관측이며 이번 작업에서 재측정한 결과가 아니다.

## 범위와 입력

Kiwi `0.24.0`으로 현재 토크나이저 기준선, 다섯 개별 변경, 승자 조합을 로컬에서 비교했다.
`ISMS-P`와 `GS인증`은 합의에 따라 서로 다른 후보다. test 분할과 API는 실행하지 않았다.
실험 스크립트는 `artifacts/kiwi_review.py`인 임시 스크립트이며 새 모듈·CLI 플래그를 추가하지 않는다.

측정 전 `artifacts/eval_set.jsonl`의 골든 384행을 `eval/golden/dev.jsonl`의 candidate ID,
질문·정답·근거 문서 SHA·골든 청크 ID와 대조했다. 나머지 1행은 `eval/eval_questions.yaml`과 대조했다.
eval SHA-256: `1ffd9d3923b228c8ae130744b15447cc3468275916db5a9202ce8bb91e23f535`.

첫 기준선 점검에서 eval의 이전 RAG ID와 활성 v12 청크의 SHA ID가 달라 전부 0으로 계산되는 것을 발견했다.
그 점수는 폐기했다. 질문 385개를 유지하고, 저장된 각 근거 본문이 dev context의 완전한 [E] 블록과 같음을
`_context_labels`로 확인한 뒤, 활성 문서의 `doc_id == source_sha256 == evidence.doc_sha`를 확인했다.
기존 `normalize_evidence`와 `_chunk_label`로 같은 문서 안에서 유일한 정확 일치만 청크 라벨로 인정했다.
최소 20자·모호한 중복·미발견 제외 규칙을 바꾸지 않았다. 원래 eval 파일은 덮어쓰지 않았으며 새 라벨은
`artifacts/kiwi_review/eval_set.jsonl`에 보관했다. 없어진 v11 요소 패키지 대신 검증된 기존 근거 본문을 재사용했다.
기준선의 후보 순위는 질문·코퍼스·설정이 그대로이므로 보존한 검색 기록을 새 라벨로 재채점했다.

활성 코퍼스는 18,989청크다. 모든 변형은 원문 질문으로 검색한다. 임베딩 `nlpai-lab/KURE-v1`,
`dense_weight=0.6`, `candidate_k=50`, `token_budget=2500`, BM25 `k1=1.5`, `b=0.75`와 퓨전 코드는 고정했다.
기준선으로 다시 만든 전체 토큰이 저장된 `bm25_tokens.json`과 같음을 먼저 확인했다.
문서 Recall/MRR도 문서 중복 제거 전 청크 위치를 사용하며, 성분별 기관 교차 순위를 보존한다.
`ir_scores`, `_ranking`, `recall_at_k`, `mrr_at_k`, `label_state`를 재사용했고, 기존 표에 없는
dense/BM25 MRR만 같은 helper로 임시 스크립트에서 추가했다. 미라벨 질문도 검색하되 점수 평균에서는 제외한다.

## 라벨 범위와 제외율

답할 수 있는 골든 근거 질문 376개가 매핑 제외율의 분모다. 문서 376개, 청크 186개를 채점한다.
청크 일부 라벨 117개·미라벨 73개는 전체 질문을 제외하며, 청크 매핑 제외율은 190/376(50.53%)다.
답할 수 없음 8개와 골든 근거 없는 YAML 1개는 분모에서 별도로 제외한다.
기존 eval의 137개 청크 라벨/63.56% 제외율은 이전 ID 공간의 값이므로 아래 점수에 사용하지 않는다.

| 주제 | 수준 | 전체 | 전체 라벨 | 일부 라벨 | 미라벨 | 답할 수 없음 | 골든 없음 | 매핑 제외율 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ALL | doc | 385 | 376 | 0 | 0 | 8 | 1 | 0.00% |
| ALL | chunk | 385 | 186 | 117 | 73 | 8 | 1 | 50.53% |
| comparison | doc | 56 | 56 | 0 | 0 | 0 | 0 | 0.00% |
| comparison | chunk | 56 | 12 | 32 | 12 | 0 | 0 | 78.57% |
| condition | doc | 69 | 69 | 0 | 0 | 0 | 0 | 0.00% |
| condition | chunk | 69 | 67 | 1 | 1 | 0 | 0 | 2.90% |
| false_premise | doc | 4 | 4 | 0 | 0 | 0 | 0 | 0.00% |
| false_premise | chunk | 4 | 1 | 3 | 0 | 0 | 0 | 75.00% |
| multi_hop | doc | 47 | 47 | 0 | 0 | 0 | 0 | 0.00% |
| multi_hop | chunk | 47 | 3 | 21 | 23 | 0 | 0 | 93.62% |
| numeric | doc | 104 | 104 | 0 | 0 | 0 | 0 | 0.00% |
| numeric | chunk | 104 | 101 | 0 | 3 | 0 | 0 | 2.88% |
| table | doc | 96 | 96 | 0 | 0 | 0 | 0 | 0.00% |
| table | chunk | 96 | 2 | 60 | 34 | 0 | 0 | 97.92% |
| unanswerable | doc | 8 | 0 | 0 | 0 | 8 | 0 | — |
| unanswerable | chunk | 8 | 0 | 0 | 0 | 8 | 0 | — |
| yaml | doc | 1 | 0 | 0 | 0 | 0 | 1 | — |
| yaml | chunk | 1 | 0 | 0 | 0 | 0 | 1 | — |

## 후보 정의와 현재 토큰의 빈틈

개별 변경은 모두 같은 기준선에 하나만 적용했다. 누적 실험이 아니다.

| 후보 | 고정한 구현 |
| --- | --- |
| 복합명사 결합 | 원문 위치가 연속인 NNG/NNP의 최대 연속열을 결합해 추가하고 기존 분리 토큰 유지 |
| 잡음 제거 | `(및,MAG)`, `(하,VV)`, `(되,VV)`, `(있,VV)`, `(등,NNB)`, `(수,NNB)`만 제거; 부정어 유지 |
| 사전 확장 | CSV 기관명의 공백 제거본 85개 + 활성 청크의 연속 NNG/NNP 중 2~4형태소·4~20자·10문서 이상 등장한 2,620개; 정렬·중복 제거 후 2,705개를 NNP, score=1.0으로 등록 |
| 하이픈 식별자 | 영문자로 시작하는 영숫자 하이픈 연결열을 원문에서 추출하고 소문자 토큰 추가 (`ISMS-P`) |
| 혼합 문자 식별자 | 붙어 있는 SL + NNG/NNP를 합쳐 추가 (`GS인증`); 기존 분리 토큰 유지 |

잡음 제거는 형태·품사 쌍에만 적용한다. 같은 `있`이라도 `VA`는 유지하며, 회귀 테스트에서 이를 확인한다.

아래는 각각 기준선과 다섯 후보에서 얻은 실제 토큰이다. 예시는 형태소 누락을 보여주는 probe이며 성능 지표를 대신하지 않는다.

### `개인정보처리시스템 및 데이터베이스를 구축하여야 한다`

| 변형 | 토큰 |
| --- | --- |
| 기준선 | `개인, 정보, 처리, 시스템, 및, 데이터베이스, 구축` |
| 복합명사 결합 | `개인, 정보, 처리, 시스템, 및, 데이터베이스, 구축, 개인정보처리시스템` |
| 잡음 제거 | `개인, 정보, 처리, 시스템, 데이터베이스, 구축` |
| 사전 확장 | `개인정보처리시스템, 및, 데이터베이스, 구축` |
| 하이픈 식별자 | `개인, 정보, 처리, 시스템, 및, 데이터베이스, 구축` |
| 혼합 문자 식별자 | `개인, 정보, 처리, 시스템, 및, 데이터베이스, 구축` |

### `ISMS-P 인증과 GS인증을 받지 않는다`

| 변형 | 토큰 |
| --- | --- |
| 기준선 | `isms, p, 인증, gs, 인증, 받, 않` |
| 복합명사 결합 | `isms, p, 인증, gs, 인증, 받, 않` |
| 잡음 제거 | `isms, p, 인증, gs, 인증, 받, 않` |
| 사전 확장 | `isms, p, 인증, gs, 인증, 받, 않` |
| 하이픈 식별자 | `isms, p, 인증, gs, 인증, 받, 않, isms-p` |
| 혼합 문자 식별자 | `isms, p, 인증, gs, 인증, 받, 않, gs인증` |

### `한국지능정보사회진흥원과 정보시스템 유지관리`

| 변형 | 토큰 |
| --- | --- |
| 기준선 | `한국, 지능, 정보, 사회, 진흥원, 정보, 시스템, 유지, 관리` |
| 복합명사 결합 | `한국, 지능, 정보, 사회, 진흥원, 정보, 시스템, 유지, 관리, 한국지능정보사회진흥원, 정보시스템, 유지관리` |
| 잡음 제거 | `한국, 지능, 정보, 사회, 진흥원, 정보, 시스템, 유지, 관리` |
| 사전 확장 | `한국, 지능정보, 사회, 진흥원, 정보시스템, 유지관리` |
| 하이픈 식별자 | `한국, 지능, 정보, 사회, 진흥원, 정보, 시스템, 유지, 관리` |
| 혼합 문자 식별자 | `한국, 지능, 정보, 사회, 진흥원, 정보, 시스템, 유지, 관리` |

### `부가세 지체 상금 SFR-001은 대상이 아니다`

| 변형 | 토큰 |
| --- | --- |
| 기준선 | `부가가치세, 지체상금, sfr, 001, 은, 대상, 아니, sfr-001` |
| 복합명사 결합 | `부가가치세, 지체상금, sfr, 001, 은, 대상, 아니, sfr-001` |
| 잡음 제거 | `부가가치세, 지체상금, sfr, 001, 은, 대상, 아니, sfr-001` |
| 사전 확장 | `부가가치세, 지체상금, sfr, 001, 은, 대상, 아니, sfr-001` |
| 하이픈 식별자 | `부가가치세, 지체상금, sfr, 001, 은, 대상, 아니, sfr-001` |
| 혼합 문자 식별자 | `부가가치세, 지체상금, sfr, 001, 은, 대상, 아니, sfr-001` |

## 채택 판정

fused 청크 Recall@10이 기준선보다 엄격히 높고, 문서·청크 × 세 성분 × Recall/MRR × k=5/10/20의 36개 지표 중 어느 것도 0.01 초과 하락하지 않을 때만 승자다. 조합에도 같은 규칙을 적용했다.

| 변형 | fused 청크 R@10 | 기준선 대비 | 최저 지표 차이 | 해당 지표 | 판정 |
| --- | --- | --- | --- | --- | --- |
| 복합명사 결합 | 0.755376 | +0.008065 | -0.032168 | `chunk_bm25_mrr_at_5` | 탈락 |
| 잡음 제거 | 0.755376 | +0.008065 | -0.008065 | `chunk_bm25_recall_at_10` | 통과 |
| 사전 확장 | 0.760753 | +0.013441 | -0.005376 | `chunk_fused_recall_at_20` | 통과 |
| 하이픈 식별자 | 0.747312 | +0.000000 | -0.005376 | `chunk_bm25_recall_at_10` | 탈락 |
| 혼합 문자 식별자 | 0.750000 | +0.002688 | -0.016129 | `chunk_fused_recall_at_5` | 탈락 |
| 승자 조합 | 0.760753 | +0.013441 | -0.005376 | `chunk_fused_recall_at_20` | 통과 |

개별 승자: `['noise', 'dictionary']`. 최종 채택: `['noise', 'dictionary']`.

잡음 제거와 사전 확장을 함께 채택한다. 조합의 fused 청크 Recall@10은 0.747312 → 0.760753으로
0.013441(1.34%p) 높아졌으며, 최저 차이는 fused 청크 Recall@20의 -0.005376으로 허용 범위 안이다.
복합명사 결합·하이픈·혼합 문자 변형은 제품 코드에 남기지 않는다.

### 사전 재생성

`rag/retrieval/kiwi_user_words.json`은 생성 결과를 그대로 복사한 UTF-8 without BOM JSON 배열이다.
생성 후 단어를 수동으로 수정하지 않았다. 아래 로컬 단계를 같은 활성 청크와 CSV에서 다시 실행한다.

```powershell
$env:PYTHONPATH = (Get-Location).Path
.venv\Scripts\python artifacts/generate_kiwi_dictionary.py
```

임시 생성 스크립트는 실험의 `dictionary` 함수를 재사용한다. 채택 이후 결과가 달라지지 않도록
`kiwi_review.py`는 Git `2f746f38dba1d5fdbdfc924fbce3eac3297081b7`의 기준선 `KiwiTokenizer`를 고정해 분석한다.
CSV SHA-256은 `3071dc571903ec2df27c82518ed93afae692642fc204532efe5d1fc35bb4a210`이다.
noun run의 원문 위치가 붙어 있는지 검사한 뒤 모든 시작점의 길이 2~4 부분열을 모으고,
각 단어의 청크 횟수 대신 서로 다른 doc_id의 수를 센다. 앞 표의 길이·문서 빈도 조건을 적용하고
공백 제거 기관명과 합집합을 만들어 Python 문자열 순서로 정렬한다. JSON indent=2와 마지막 LF도 고정한다.
최종 검증에서 다시 생성한 전체 배열과 파일 바이트가 보관된 사전과 같음을 확인했다.

## 문서 순위 지표

매핑 제외율 0/376(0%), 채점 376개.

| 변형 | 성분 | Recall@5 | Recall@10 | Recall@20 | MRR@5 | MRR@10 | MRR@20 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 기준선 | fused | 1.000000 | 1.000000 | 1.000000 | 0.998227 | 0.998227 | 0.998227 |
| 기준선 | dense | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| 기준선 | bm25 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| 복합명사 결합 | fused | 1.000000 | 1.000000 | 1.000000 | 0.998005 | 0.998005 | 0.998005 |
| 복합명사 결합 | dense | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| 복합명사 결합 | bm25 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| 잡음 제거 | fused | 1.000000 | 1.000000 | 1.000000 | 0.998227 | 0.998227 | 0.998227 |
| 잡음 제거 | dense | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| 잡음 제거 | bm25 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| 사전 확장 | fused | 1.000000 | 1.000000 | 1.000000 | 0.998227 | 0.998227 | 0.998227 |
| 사전 확장 | dense | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| 사전 확장 | bm25 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| 하이픈 식별자 | fused | 1.000000 | 1.000000 | 1.000000 | 0.998227 | 0.998227 | 0.998227 |
| 하이픈 식별자 | dense | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| 하이픈 식별자 | bm25 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| 혼합 문자 식별자 | fused | 1.000000 | 1.000000 | 1.000000 | 0.998227 | 0.998227 | 0.998227 |
| 혼합 문자 식별자 | dense | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| 혼합 문자 식별자 | bm25 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| 승자 조합 | fused | 1.000000 | 1.000000 | 1.000000 | 0.998227 | 0.998227 | 0.998227 |
| 승자 조합 | dense | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| 승자 조합 | bm25 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |

## 청크 순위 지표

매핑 제외율 190/376(50.53%), 채점 186개.

| 변형 | 성분 | Recall@5 | Recall@10 | Recall@20 | MRR@5 | MRR@10 | MRR@20 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 기준선 | fused | 0.553763 | 0.747312 | 0.943548 | 0.325627 | 0.351717 | 0.365849 |
| 기준선 | dense | 0.575269 | 0.741935 | 0.930108 | 0.350448 | 0.371738 | 0.386277 |
| 기준선 | bm25 | 0.411290 | 0.637097 | 0.841398 | 0.269265 | 0.299853 | 0.312924 |
| 복합명사 결합 | fused | 0.548387 | 0.755376 | 0.932796 | 0.318817 | 0.347295 | 0.360505 |
| 복합명사 결합 | dense | 0.575269 | 0.741935 | 0.930108 | 0.350448 | 0.371738 | 0.386277 |
| 복합명사 결합 | bm25 | 0.403226 | 0.658602 | 0.854839 | 0.237097 | 0.273009 | 0.285861 |
| 잡음 제거 | fused | 0.548387 | 0.755376 | 0.943548 | 0.327867 | 0.355929 | 0.369001 |
| 잡음 제거 | dense | 0.575269 | 0.741935 | 0.930108 | 0.350448 | 0.371738 | 0.386277 |
| 잡음 제거 | bm25 | 0.416667 | 0.629032 | 0.841398 | 0.269444 | 0.297807 | 0.311879 |
| 사전 확장 | fused | 0.575269 | 0.760753 | 0.938172 | 0.338530 | 0.362366 | 0.375570 |
| 사전 확장 | dense | 0.575269 | 0.741935 | 0.930108 | 0.350448 | 0.371738 | 0.386277 |
| 사전 확장 | bm25 | 0.456989 | 0.680108 | 0.852151 | 0.272939 | 0.303695 | 0.315601 |
| 하이픈 식별자 | fused | 0.553763 | 0.747312 | 0.943548 | 0.325627 | 0.351717 | 0.365849 |
| 하이픈 식별자 | dense | 0.575269 | 0.741935 | 0.930108 | 0.350448 | 0.371738 | 0.386277 |
| 하이픈 식별자 | bm25 | 0.411290 | 0.631720 | 0.841398 | 0.266577 | 0.296493 | 0.310053 |
| 혼합 문자 식별자 | fused | 0.537634 | 0.750000 | 0.954301 | 0.322581 | 0.351231 | 0.365874 |
| 혼합 문자 식별자 | dense | 0.575269 | 0.741935 | 0.930108 | 0.350448 | 0.371738 | 0.386277 |
| 혼합 문자 식별자 | bm25 | 0.405914 | 0.637097 | 0.841398 | 0.268100 | 0.299285 | 0.312502 |
| 승자 조합 | fused | 0.575269 | 0.760753 | 0.938172 | 0.339158 | 0.362837 | 0.376123 |
| 승자 조합 | dense | 0.575269 | 0.741935 | 0.930108 | 0.350448 | 0.371738 | 0.386277 |
| 승자 조합 | bm25 | 0.456989 | 0.677419 | 0.846774 | 0.268907 | 0.298805 | 0.310990 |

정확 코드 포함률은 순위가 아닌 집합으로 계산한다. 모든 변형에서 동일하며 하락이 없음을 확인했다.

| 변형 | 문서 코드 집합 Recall | 청크 코드 집합 Recall |
| --- | --- | --- |
| 기준선 | 0.220745 | 0.016129 |
| 복합명사 결합 | 0.220745 | 0.016129 |
| 잡음 제거 | 0.220745 | 0.016129 |
| 사전 확장 | 0.220745 | 0.016129 |
| 하이픈 식별자 | 0.220745 | 0.016129 |
| 혼합 문자 식별자 | 0.220745 | 0.016129 |
| 승자 조합 | 0.220745 | 0.016129 |

## 저장된 dev 30문항 재실행

`rerun_retrieval`로 `artifacts/ir_dev30/answers.jsonl`과 `rerun_05/answers.jsonl`의 저장 rewrite를 재사용했다.
`artifacts/quantity_filter/dev`의 청크가 `ir_dev30/input`과 바이트 단위로 같은 원래 100문서·18,988청크를 사용했다.
문서 26개(매핑 제외 0%), 청크 15개(11/26, 42.31% 제외)를 채점한다. 채택 전후 각 weight를 별도로 비교한다.
이 표는 기존 보고서의 원래 유료 점수를 재평가하거나 생성·심판 품질 비교로 해석하지 않는다.

### 문서

| 변형 | 성분 | Recall@5 | Recall@10 | Recall@20 | MRR@5 | MRR@10 | MRR@20 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dev30_before_0.6 | fused | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| dev30_before_0.6 | dense | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| dev30_before_0.6 | bm25 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| dev30_before_0.5 | fused | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| dev30_before_0.5 | dense | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| dev30_before_0.5 | bm25 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| dev30_after_0.6 | fused | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| dev30_after_0.6 | dense | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| dev30_after_0.6 | bm25 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| dev30_after_0.5 | fused | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| dev30_after_0.5 | dense | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |
| dev30_after_0.5 | bm25 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 | 1.000000 |

### 청크

| 변형 | 성분 | Recall@5 | Recall@10 | Recall@20 | MRR@5 | MRR@10 | MRR@20 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| dev30_before_0.6 | fused | 0.666667 | 0.800000 | 0.866667 | 0.488889 | 0.506746 | 0.512302 |
| dev30_before_0.6 | dense | 0.700000 | 0.866667 | 0.933333 | 0.444444 | 0.458519 | 0.462685 |
| dev30_before_0.6 | bm25 | 0.566667 | 0.666667 | 0.733333 | 0.438889 | 0.446296 | 0.451425 |
| dev30_before_0.5 | fused | 0.666667 | 0.733333 | 0.866667 | 0.522222 | 0.533333 | 0.544017 |
| dev30_before_0.5 | dense | 0.700000 | 0.866667 | 0.933333 | 0.444444 | 0.458519 | 0.462685 |
| dev30_before_0.5 | bm25 | 0.566667 | 0.666667 | 0.733333 | 0.438889 | 0.446296 | 0.451425 |
| dev30_after_0.6 | fused | 0.733333 | 0.800000 | 0.933333 | 0.488889 | 0.497222 | 0.506287 |
| dev30_after_0.6 | dense | 0.700000 | 0.866667 | 0.933333 | 0.444444 | 0.458519 | 0.462685 |
| dev30_after_0.6 | bm25 | 0.633333 | 0.666667 | 0.800000 | 0.516667 | 0.516667 | 0.527489 |
| dev30_after_0.5 | fused | 0.733333 | 0.800000 | 0.933333 | 0.494444 | 0.501852 | 0.509630 |
| dev30_after_0.5 | dense | 0.700000 | 0.866667 | 0.933333 | 0.444444 | 0.458519 | 0.462685 |
| dev30_after_0.5 | bm25 | 0.633333 | 0.666667 | 0.800000 | 0.516667 | 0.516667 | 0.527489 |

## 보존 확인과 한계

처음 요구한 수량 결과 전체 보존은 조합에서 성립하지 않았다. 사람의 명시적 선택에 따라
보존 범위를 선택 문서·수치·매칭 필드·요약으로 확정하고 개요 발췌 변경을 허용했다.
예산 하한·기간 하한·예산 범위·최대 예산의 기록된 4질문에서 그 보존 항목은 모두 동일하다.
문서 수는 각각 61, 30, 44, 1개다. 앞의 세 질문은 문서 한 개씩의 개요 본문이 달라졌고 마지막 질문은 같다.
반환되는 값 근거 chunk_id는 모두 같다. 개별 문서의 개요 출처·청크 ID·본문 분류 변화는 비공개 로컬 `artifacts/kiwi_review/`에만 보관한다.
이는 승인된 제한이며 생성 품질 개선으로 해석하지 않는다. 비교용 잡음 제거 단독 실험은 4질문 본문까지 모두 같았다.

수량 파서의 사전·토큰 필터는 수정하지 않았다. 채택 토크나이저로 BM25만 로컬 재구축했고,
`quantities.jsonl`·FAISS·활성 청크·원래 eval·30문항 입력·`api_usage.csv`는 아래 SHA와 같이 보존했다.
네트워크 연결을 차단한 상태로 검색·재실행했다. 모든 usage 파일의 전후 해시가 같으므로 API 추가 호출 0회, 비용 $0이다.

| 보존 파일 | SHA-256 |
| --- | --- |
| `C:\Users\dasdk\PycharmProjects\rfg_rag\artifacts\chunks.jsonl` | `7a4614a1e63f18a81107b657f25784e9ac012c50750cedc9547bb4d7bc171a2d` |
| `C:\Users\dasdk\PycharmProjects\rfg_rag\artifacts\index\faiss.index` | `bd9e8d0b7ae870c866091e92c0b3bf8e885ca3596d04c5d6c6d69bbd69313663` |
| `C:\Users\dasdk\PycharmProjects\rfg_rag\artifacts\index\quantities.jsonl` | `fadf8d2c16240da32f75ab039072e44c3f37a59bdeeacd0bf8a5023750442f20` |
| `C:\Users\dasdk\PycharmProjects\rfg_rag\CLAUDE.md` | `8399a776b5fc06522ae6a5080d488075629a72b0e27fc9d3e2ff1301e9981d2c` |
| `C:\Users\dasdk\PycharmProjects\rfg_rag\AGENTS.md` | `8399a776b5fc06522ae6a5080d488075629a72b0e27fc9d3e2ff1301e9981d2c` |
| `C:\Users\dasdk\PycharmProjects\rfg_rag\artifacts\api_usage.csv` | `771da8c8ee10645af51e693bd257c92d2ce1978b0cdef91a8621cc4a1d169f3c` |
| `C:\Users\dasdk\PycharmProjects\rfg_rag\artifacts\ir_dev30\api_usage.csv` | `ee8221073f6a117e32741c2cdf222fedf2a0847ce273e4d4bbf380f8c08126ea` |
| `C:\Users\dasdk\PycharmProjects\rfg_rag\artifacts\retrieval-port-comparison\after\artifacts\api_usage.csv` | `b3dcc1f600d5177c9771bbe05f97de29cfbea2eafb1ada417045f79adac87755` |
| `C:\Users\dasdk\PycharmProjects\rfg_rag\artifacts\retrieval-port-comparison\before\artifacts\api_usage.csv` | `b074ce5af05f12146bf4005b24d1f5174fba9d871736073490442336ed11b76c` |
| `C:\Users\dasdk\PycharmProjects\rfg_rag\artifacts\retrieval-port-filename-case-comparison\after\artifacts\api_usage.csv` | `f0bd1fb96545cef433cfa7c219c4703e47dc89b4b0aa71edf0f4badf95a95405` |
| `C:\Users\dasdk\PycharmProjects\rfg_rag\artifacts\retrieval-port-identifier-comparison\after\artifacts\api_usage.csv` | `d0d3d90a7e854b3aff39c8fc56a5330c6a72853303413024a7b7c74043e29e1e` |
| `C:\Users\dasdk\PycharmProjects\rfg_rag\artifacts\retrieval-port-main-comparison\after\artifacts\api_usage.csv` | `b6ed08affd4cb434fe79d86bfc75e9c97bc68cc26811ab3750f82d513fe24168` |
| `C:\Users\dasdk\PycharmProjects\rfg_rag\artifacts\retrieval-port-main-comparison\before\artifacts\api_usage.csv` | `63636989d5777f49e9aabe4703d2944412ee2e9f60ec4c7303f64402dc65d719` |
| `C:\Users\dasdk\PycharmProjects\rfg_rag\artifacts\retrieval-port-provenance-comparison\after\artifacts\api_usage.csv` | `88fd447c9677d194f32cb74aa8522e438a0a9fdb378c1651db5f6646c960c603` |
| `C:\Users\dasdk\PycharmProjects\rfg_rag\artifacts\retrieval-port-r1-comparison\after\artifacts\api_usage.csv` | `fe2244d2c1b6be1e63d3143bcc4fd9a2a43d6b93ad5ba6d0a3edcce7a881949f` |
| `C:\Users\dasdk\PycharmProjects\rfg_rag\artifacts\retrieval-port-r2-comparison\after\artifacts\api_usage.csv` | `b154f2ff1413d291a5264046b31825a0c45302a8d62198bd827b2fc559ea74f0` |
| `C:\Users\dasdk\PycharmProjects\rfg_rag\artifacts\review\pr52-halfbeak-20261016\api_usage.csv` | `9088273c3bd706db15c064591c416937dc1c67d2248272bc9ace2c97e08a2fdc` |
| `C:\Users\dasdk\PycharmProjects\rfg_rag\artifacts\v11_comparison\current\api_usage.csv` | `f6fa8bb84fbbd10bec5cea33019e1f5ec26735c84cb2cdf09f3cddefa779d8e2` |
| `C:\Users\dasdk\PycharmProjects\rfg_rag\artifacts\v11_comparison\v11\api_usage.csv` | `ecffca36c6af7a5f87b34ab2a2bad5393a33acb1ed413eadf3b61af427ebd599` |

측정 원본은 `artifacts/kiwi_review/{variant}/rankings.jsonl`, `scores.csv`, `metrics.csv`,
`exclusions.csv`, `summary.json`과 `dev30_before_*`, `dev30_after_*` 폴더에 보관했다.
전체 36개 수치를 담은 버전 관리 자료는 [kiwi_bm25_metrics.csv](kiwi_bm25_metrics.csv)다.
채택한 사전은 `rag/retrieval/kiwi_user_words.json`이며, 탈락 변형은 제품 코드에 남기지 않았다.

이는 dev에서 정한 고정 후보의 결과다. 원문 질문 실험과 저장 rewrite 표본은 질의·코퍼스·라벨 범위가 다르므로
숫자를 서로 직접 비교하지 않는다. 청크 라벨이 numeric·condition에 집중되어 있고 table·multi_hop의 완전 라벨 수는
각각 2개·3개뿐이다. 전체 dev의 검색 품질이나 test 성능을 보장하지 않는다.
새 잡음 목록·사전 임계값·다른 결합 규칙을 추가 탐색하지 않았으며, 이번 탈락은 여기 정의한 구현에 대한 판정이다.

## 최종 검증

`artifacts/verify_kiwi_final.py`로 385개 질문의 일곱 실험 행을 다시 채점하고 판정을 재확인했다.
생성 사전의 결정적 재생성, 제품 토크나이저와 측정 조합의 전체 코퍼스·질문 토큰 일치,
BM25 재구축, 승인된 수량 보존 항목과 usage 바이트 보존을 확인했다.

기존 토크나이저 테스트를 확장해 새 기관명·복합어가 실제 토큰으로 남고 잡음 형태소가 빠지는지 확인하며,
기존 별칭·사용자 단어·부정어·요구사항 코드와 batch/query 동일성 assertion을 유지했다.
관련 색인·수량·IR·근거 매핑·골든 수량 테스트도 정리 감사했으며 삭제할 오래된 테스트·중복·skip/xfail은 없었다.

| 검사 | 결과 |
| --- | --- |
| `.venv\Scripts\python -m pytest -q tests` | `1330 passed, 12 warnings in 269.86s` |
| `.venv\Scripts\ruff check .` | `All checks passed!` |
| `git diff --no-index CLAUDE.md AGENTS.md` | 출력 없음, 바이트 동일 |

## 리뷰 1 — 기존 BM25 색인과 질문 토크나이저의 세대 불일치 (F1)

수정 전에 `artifacts/reproduce_kiwi_index_generation.py`로 문제를 재현했다. 기준선 커밋
`2f746f3`의 실제 색인 생성 함수를 로컬 임베딩 대역과 세 문서에 적용했다. 저장 토큰은
`개인`, `정보`, `처리`, `시스템`이었다. 같은 파일을 읽고 `dense_weight=0`으로
`개인정보처리시스템`을 검색하면 이전 질문 토크나이저는 청크 `0`을 반환했고,
채택 토크나이저는 질문을 한 토큰으로 만들어 후보를 전혀 반환하지 않았다.
이 재현은 코드 변경 전에 실행했으며 유료 호출은 없었다.

`indexing.py`의 유일한 제품 BM25 작성 경로가 이제 `bm25_tokens.json` 한 파일 안에
`tokenizer` 지문과 `tokens`를 함께 저장한다. 지문은 줄바꿈을 정규화한 이 모듈의 SHA-256,
실제로 읽은 생성 사전의 SHA-256, `kiwipiepy`·`kiwipiepy_model`·`hanja` 버전이다.
전체 모듈을 포함하므로 규칙 변경 때 지문 버전을 수동으로 올리는 누락을 피하지만,
색인 생성 코드나 주석만 바뀌어도 보수적으로 재구축을 요구한다.
기존 디렉터리 단위 발행·실패 시 복원 경계 안에서 지문과 토큰을 함께 발행한다.

유일한 제품 BM25 읽기 경로인 `HybridIndex.__init__`은 지문 없는 옛 목록이나 불일치를
FAISS·임베딩 모델 로드 전에 거부하고 `02_retrieval.ipynb`의 `build_index` 셀로 재구축하라고 안내한다.
오류가 난 파일에 지문만 덧붙여서 재사용하지 않는다. README의 설정 셀만 실행하라는 설명도
호환 색인 재사용과 최초 마이그레이션을 구분하도록 수정했다. 불러오기·설정·색인 만들기 셀만
실행하면 되고, 유료 재작성 예제 셀은 이 마이그레이션에 필요하지 않다.

같은 규칙의 다른 적용 지점은 아래와 같이 별도 집계했다. 다른 제품 로더는 0개이며,
다섯 앱 호출부와 한 문서 예제 모두 공통 생성자 검사로 보호된다.

| 구분 | 개수 | 위치 |
| --- | ---: | --- |
| 공통 제품 작성·읽기 경계 | 각각 1 | `indexing._build_index`, `HybridIndex.__init__` |
| 앱 생성자 호출부 | 5 | 02 노트북 2곳, 04 노트북 1곳, 05 노트북 1곳, `frontend/server.py` 1곳 |
| 문서 실행 예제 | 1 | README의 `rerun_retrieval` 예제 |

`artifacts/verify_kiwi_round1.py`는 네트워크를 차단하고 실제 활성 옛 형식이 거부되는지 확인했다.
이어서 18,989개 청크를 다시 토큰화해 기존 채택 토큰 내용과 전부 같음을 확인한 뒤 새 형식으로 저장했다.
실제 `HybridIndex`의 BM25 단독 검색에서 같은 질의는 50개 후보·35개 결과를 반환했다.
FAISS, 수량 색인의 모든 파일, 활성 청크, eval 입력, 두 규칙 파일과 14개 usage CSV는 바이트 그대로다.
측정한 토큰과 검색 규칙은 바꾸지 않았으며 새 품질 측정이나 test 분할 실행을 하지 않았다.
결과는 `artifacts/kiwi_review/round1.json`과 `round1.log`에 보관했다.

테스트 정리에서 색인 발행·복원, 토크나이저, 검색 및 수량 색인 작성 회귀를 감사했다.
중간 단계의 옛 형식 거부 단독 사례는 거부 → 재구축 → BM25 단독 검색까지 확인하는 한 회귀에 합쳤다.
코드·사전·세 패키지 버전 변경은 실제 지문 입력을 바꿔 모델 로드 전 거부와 기존 파일 보존을 각각 확인한다.
현재 동작을 지키는 기존 테스트와 별칭·사용자 단어·부정어·코드 assertion은 유지했다.

정리 후 `.venv\Scripts\python -m pytest -q tests`는
`1336 passed, 12 warnings in 130.56s (0:02:10)`으로 통과했다.
`.venv\Scripts\ruff check .`는 `All checks passed!`,
`git diff --no-index CLAUDE.md AGENTS.md`는 출력 없이 통과했다.

## Review 2 — coordinated index downgrade (F1)

The research draft [F1, cycle 1](research/review-review-kiwi-bm25-tokenizer-f1-1.md) was read before
the experiment. It remains a draft, not a verified rule. Before editing the migration guidance,
`artifacts/kiwi_round2_experiment.py` ran the actual base `2f746f3` and candidate `5b2773f` code
in separate fresh Python processes. Connections were blocked and embeddings used a local substitute.
The three chunks were `개인정보처리시스템`, `네트워크 보안` and `계약 기간`.

| Transition | Observed result |
| --- | --- |
| Base build and search | Three corpus entries and three scores; split query tokens; BM25 IDs `[0]`, hybrid IDs `[0, 1, 2]` |
| Candidate loading base artifacts | Fingerprint rejection; all five index files unchanged |
| Candidate rebuild and search | Three entries/scores; whole compound query token; BM25 IDs `[0]` |
| Base loading candidate artifacts | Two entries/scores; search failed with `operands could not be broadcast together with shapes (3,) (2,) ()` |
| Downgrade build failure after quarantine | Active index absent; a fresh base reader failed to load `faiss.index`; quarantined candidate files unchanged |
| Isolated base rebuild, fresh verification and publication | All five files byte-identical to the original base build; original tokens, BM25 and hybrid results restored in a fresh base process |

The first repair only protected the newer reader. A plain JSON array would fix parsing while
leaving old query tokenization incompatible with the new corpus. The corrective path is therefore
the [stopped-reader downgrade procedure](index_rollback.md): quarantine the newer bundle, build
and verify using the exact rollback code/environment, then rename the complete verified directory
into the absent active path. Any failure leaves readers stopped and the active path absent.
Production writer, loader and tokenizer code remain unchanged in this repair.

The separate applicability census is one product writer, one product loader, five application
constructor sites (two in 02, one each in 04, 05 and the frontend), and one README execution example.
There are zero additional product loaders. All five coupled index artifacts must move together;
no caller-specific fallback or conversion was added.

The persisted regression is `tests/test_index_migration.py` with a fresh-process worker in
`tests/index_migration_worker.py`. It extracts the actual frozen base from Git and uses current
candidate code. The synthetic forward-only migration test was folded into this stronger lifecycle
test. Existing publication rollback and source/dictionary/package fingerprint regressions remain.
The initial experiment is recorded in `artifacts/kiwi_review/round2/result.json` and
`round2_experiment.log`; the committed regression also checks a distinct fresh staging directory
after the injected failure, following the documented retry procedure.

This rehearses code and artifacts in Python 3.10.11 with Kiwi/model 0.24.0, Hanja 0.15.1,
rank-bm25 0.2.2, NumPy 2.2.6 and FAISS 1.15.1. It does not reproduce every historical dependency
environment, downgrade the active 18,989-chunk corpus, switch live readers or establish crash safety.
Code, environment, config and frozen inputs must still be selected together during a real rollback.

After test cleanup, `.venv\Scripts\python -m pytest -q tests/test_index_migration.py tests/test_indexing.py tests/test_retrieval.py`
reported `61 passed in 139.91s`. Ruff and the repository debt check passed; `CLAUDE.md` and
`AGENTS.md` remain byte-identical and unchanged. The earlier full-suite result is historical;
this repair ran the affected scope rather than repeating the whole suite during review.
