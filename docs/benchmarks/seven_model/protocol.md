# 로컬 임베딩 검색 비교 규약

Actual dataset records, questions, answers, evidence text, and returned contexts remain in ignored local artifacts. Aggregate counts, quality scores, latency, resource measurements, and reports discussing those values may be published without the underlying records. A JSONL extension is not the deciding factor: actual records embedded in another format remain private. Repository tests use independently authored synthetic temporary inputs.

## 범위와 통제

개발 자료만 사용하고 운영 모델·활성 색인·설정·Kiwi 규칙·사전은 변경하지 않는다. 추론·재작성·답변 생성·판정·OCR·원격 측정 API, 유료 컴퓨팅, test split, 추가 후보, 파인튜닝·리랭커·새 청킹, 모델 가중치 양자화·CPU offload는 사용하지 않는다.

Stage 1은 KURE를 고정해 공백 BM25, dense, 현재 Kiwi BM25, Kiwi+dense, 공백+dense를 비교한다. 공백 토큰화는 형태소 분석 없는 `str.split()`이며 BM25는 `k1=1.5`, `b=0.75`다. Stage 2는 일곱 모델 각각 dense와 Kiwi hybrid를 비교하고 동일한 KURE 결과를 재사용한다.

두 단계 모두 기관 라우팅과 교차 배치를 유지한다. isolated에서는 코드 승격·수량 필터 우회를 끄고, integrated에서는 운영 코드 승격·필터·중복 제거·패킹을 유지한다. 필터 경로는 일반 순위와 별도로 보고한다. `candidate_k=50`, 현행 min-max 융합, 수량 설정과 일반 컨텍스트 예산 2,500토큰을 유지한다. 모든 모델의 패킹 비용은 같은 revision KURE 토크나이저로 센다. 입력 임베딩에는 각 모델의 토크나이저를 쓴다.

원본 dev와 말뭉치·설정·근거를 바이트 그대로 보존하고 지문을 로컬 manifest에 고정한다. 검색에는 dev 전체를 사용하며 정답 문자열 평가용 `key_facts` 조건으로 질문을 제외하지 않는다. 근거는 원본 계획 ref와 context의 정확한 블록으로 확인하고, 기존 동일 문서·유일한 정규화 정확 포함 규칙으로만 재매핑한다. 부분 라벨을 완전한 정답 집합으로 채점하지 않는다.

점수 계산 전에 seed와 질문 ID를 로컬 split에 고정한다. 중복 질문·공유 원본/유효 재매핑 청크·bundle 그룹을 유지하고 주제 균형과 남은 중복 가능성을 공개한다. 기존 dev 개발·점수 노출이 있다면 명시한다. validation은 가중치 선택에서 제외하며 최종 test 결과로 부르지 않는다.

고정 hybrid `dense_weight=0.6`을 먼저 측정한 뒤 공통 그리드 `0.2/0.4/0.6/0.8`을 적용한다. 일반 경로·완전 청크 라벨 튜닝 질문의 평균 R@10으로 선택하며 동률이면 0.6에 가까운 값, 그다음 낮은 값을 택한다. 로컬 선택 파일을 동결한 다음 validation을 채점한다. 기존 선택이 바뀌면 집계를 중단한다.

## 공개 모델 규약

정확한 ID·revision·dtype·차원·입력 상한·배치 크기는 [models.json](models.json)에 고정한다. 아래는 발행자의 설명과 라이선스이며 로컬 데이터셋의 실측 결과가 아니다.

| 모델 / 고정 일차 출처 | 추론 규약 | 평가 관련성·제약 |
| --- | --- | --- |
| [nlpai-lab/KURE-v1](https://huggingface.co/nlpai-lab/KURE-v1/blob/8b418a58414668e75532ed045c22d9ca018ae2b2/README.md) | CLS, 프롬프트 없음, FP16, 1,024차원. 공개 한도 8,192와 구분해 배포 입력 상한 2,048을 유지한다. | 한국어 검색 기준선. MIT. |
| [nvidia/Nemotron-3-Embed-1B-BF16](https://huggingface.co/nvidia/Nemotron-3-Embed-1B-BF16/blob/c0c9fea93ea424587517f2c59e20db9f1d6bf615/README.md) | BF16, 질문 `query: ` / 문서 `passage: `, mean, 2,048차원, 32,768토큰. Transformers ≥5.2, Sentence Transformers ≥5.4.1, SDPA 지원. | 한국어가 포함된 공개 다국어 평가. OpenMDW-1.1이며 카드 metadata의 `other`와 구분한다. |
| [microsoft/harrier-oss-v1-0.6b](https://huggingface.co/microsoft/harrier-oss-v1-0.6b/blob/f9b9dc8d367d443f2479d27aa5d8d2850c0774ee/README.md) | BF16, 질문 `web_search_query`, 문서 프롬프트 없음, last-token, 1,024차원, 32,768토큰. | 공개 다국어 평가와 한국어 지원. MIT. |
| [jinaai/jina-embeddings-v5-text-small](https://huggingface.co/jinaai/jina-embeddings-v5-text-small/blob/dd76d535f5447ca3897a9c893fb1e612ead98192/README.md) | 고정 사용자 코드, BF16, `task="retrieval"` PEFT 어댑터, `Query: ` / `Document: `, last-token, 1,024차원, 32,768토큰. | 작업별 다국어 검색 후보. CC BY-NC 4.0의 비상업적 제한을 유지한다. |
| [perplexity-ai/pplx-embed-v1-0.6b](https://huggingface.co/perplexity-ai/pplx-embed-v1-0.6b/blob/2c4d510dd4a732063c31a0f70193e35067b51fd8/README.md) | 고정 사용자 코드, 원래 FP32 가중치, 프롬프트 없음, mean, 1,024차원, 32,768토큰. native 양자화 출력값을 float32로 변환하고 코사인 규약으로 정규화한다. | 독립 텍스트 검색 후보. MIT. 출력 벡터 양자화는 모델 가중치 양자화와 다르다. |
| [dragonkue/BGE-m3-ko](https://huggingface.co/dragonkue/BGE-m3-ko/blob/7074d66aa46562342193ca4feb3d89bf9dad71b4/README.md) | 저장된 CLS와 정규화, 프롬프트 없음, FP16, 1,024차원, 8,192토큰. | 한국어 파인튜닝·평가 후보. Apache-2.0. |
| [upskyy/bge-m3-korean](https://huggingface.co/upskyy/bge-m3-korean/blob/069ae0627320935e4b2879522edbb54650b59bf5/README.md) | 저장된 mean, 명시적 정규화, 프롬프트 없음, FP16, 1,024차원. 저장 설정 512와 카드 8,192의 차이를 공개하고 카드 한도를 적용한다. | 한국어 파인튜닝 후보. LICENSE가 없고 카드의 unknown-license 주석이 있어 이용 조건은 미해결이다. |

각 snapshot의 가중치·사용자 코드·프롬프트·풀링 설정 해시는 로컬 완료 기록에 저장한다. 벡터는 float32 L2 정규화와 FAISS 내적을 사용한다. 입력 상한·잘림 횟수·실제 출력 dtype·패키지 버전을 모델별로 기록한다.

## 실행과 로컬 산출물

애플리케이션 환경을 보존하는 별도 `.venv-benchmark310`에 CUDA PyTorch와 `requirements-benchmark.txt`를 준비한다. 모델 다운로드는 준비 단계이며 측정 중에는 HF 오프라인·추적 비활성 환경과 socket/DNS 차단을 적용한다. RTX 3080 10 GiB에서 여유 VRAM·디스크를 확인하고 모델별 새 프로세스로 순차 실행한다. 관련 없는 프로세스는 종료하지 않는다.

측정 소스를 먼저 커밋한 뒤 준비한다. manifest v3은 준비 시점의 커밋과 검색·검증·지표 코드의 SHA-256을 고정한다. 소스의 미커밋 변경, 준비 후 커밋 변경, 모델 간 소스 지문 차이는 준비 재사용·실행 완료·집계·기록 검증에서 거부한다. 원본 코드가 없는 기존 기록에 현재 지문을 덧붙여 같은 실행으로 취급하지 않는다.

```powershell
.venv-benchmark310\Scripts\python -m rag.validation.local_inputs
.venv-benchmark310\Scripts\python -m rag.retrieval.benchmark prepare
foreach ($model in @('kure','nemotron','harrier','jina','pplx','dragonkue','upskyy')) {
    .venv-benchmark310\Scripts\python -m rag.retrieval.benchmark run --model $model
    if ($LASTEXITCODE -ne 0) { throw "Benchmark failed: $model" }
}
.venv-benchmark310\Scripts\python -m rag.retrieval.benchmark summarize
```

입력과 측정은 `artifacts/seven_model_full_dev/`, frozen 질문·split·manifest와 집계·문항별 결과는 그 아래 `record/`에 쓴다. 원래 실행의 로컬 기록은 `artifacts/seven_model/record/`에 보존한다. 완료된 측정은 덮어쓰지 않는다. BM25 사례 감사를 다시 실행하려면 로컬 입력 `audit_probes.json`에 진단 질문 ID를 준비하고 `python -m rag.retrieval.benchmark.audit`를 사용한다. 실제 ID는 코드에 넣지 않는다.

평가 입력은 공통 로더가 `artifacts/local_inputs/`에서 읽는다. 기존 논리 경로는 유지하며 깨끗한 업데이트로 원본 파일이 사라져도 추적 해제 직전의 로컬 Git 객체에서 복원한다. 네트워크나 추론은 호출하지 않는다. 얕은 clone 또는 정리된 이력에는 소유자가 제공한 비공개 묶음을 `python -m rag.validation.local_inputs --from-directory PATH`로 먼저 복원한다. 묶음의 구조와 검증·덮어쓰기 금지 규칙은 [README](../../../README.md#로컬-평가-입력과-ocr-캡션-복원)를 따른다. 복원된 파일은 Git에서 무시한다.

각 설정은 예열을 제외하고 단건 입력·캐시 없는 질문 임베딩으로 섞인 질문 순서의 3패스를 측정한다. 입력부터 반환 컨텍스트까지 GPU 동기화를 포함하며 로딩·색인 구축·지표 계산은 타이머 밖이다. 원시 밀리초·p50/p90·표본 수·패스 변동과 각 단계의 시간·처리량·색인 크기·CUDA/RSS 피크를 로컬에 기록한다. 장치 전체 사용량에는 다른 프로세스가 포함되고 표본 메모리는 짧은 피크를 놓칠 수 있다.

문서/청크 Recall·MRR@5/10/20은 패킹 전 청크 위치로 계산하고 문서를 먼저 중복 제거하지 않는다. 정확 코드 membership은 별도 집합 지표다. 패킹 후 Coverage와 full coverage는 단일/다중 근거를 나누고 모든 적격·제외 분모를 정의한다. 전체 dev 집계는 기술 통계로 구분한다. 추천은 Kiwi hybrid validation 청크 R@10을 우선하되 R@20·다중 근거·주제별 회귀·p90·메모리·라이선스의 트레이드오프를 포함하고 모델을 자동 채택하지 않는다.

모델 완료 기록은 모든 설정의 결과 gzip과 원시 latency JSONL의 파일명·SHA-256을 봉인한다. 집계는 점수 계산과 가중치 선택 전에 모든 모델의 소스·파일 봉인을 검사한다. 결과 ID나 양의 시간 값을 바꾼 뒤 점수를 다시 계산해도 원본 봉인과 다르면 거부한다. 내보내기는 결과·latency·완료 기록을 바이트 그대로 복사하며 내보낸 기록도 같은 봉인을 검사한다. 원시 기록에 점수를 다시 써 넣지 않는다.

완료 시점의 소스·파일 봉인이 없는 기존 측정은 원본 그대로 역사적 기록으로 보존하되 v3 검증 통과나 현재 추천의 확정 근거로 표시하지 않는다. 사후 해시 생성은 완료 당시의 무결성을 입증하지 못하므로 새로 고정한 커밋에서 새 실측이 필요하다. 기존 기록을 덮어쓰지 않는다.

집계는 로컬 raw의 질문 분할·3패스 순서·모델 완료 상태·동결 가중치를 다시 검증하며 지표는 기존 IR 도우미로 계산한다. Git 테스트는 합성 임시 자료와 손상 사례만 사용한다. `eval/golden/`의 원본 릴리스는 추적하지 않고 로컬에서 제공하며 실제 dev 행을 저장소 테스트 fixture로 사용하지 않는다. 전체 pytest gate는 서버 소유이며 구현 세션에서는 영향받은 파일만 검사한다.

## 집계 결과 보관

기존 로컬 측정의 집계 결과는 [385문항 부분집합 보고서](historical/report.md)와 [408문항 전체 dev 보고서](full_dev/report.md)에 보관한다. 각 폴더의 `quality.csv`, `paired_differences.csv`, `latency.csv`, `exclusions.csv`, `chosen_weights.json`, `resources.json`, `sparse_build.json`은 질문별 레코드를 담지 않는 집계다. 각 `runtime-freeze.txt`는 당시 저장한 패키지 이름·버전 183개만 보존한 실행 환경 기록이며 프로젝트 설치 의존성을 바꾸지 않는다. 원래 점수·분모·시간·자원·추천과 한계를 함께 보존하며, 이번 복원에서 새로 실행하거나 점수를 다시 계산하지 않았다.

두 기록은 완료 당시 v3 봉인이 없는 역사적 측정이다. 기존 추천을 현재 검증을 통과한 확정 결론으로 승격하지 않는다. 원시 질문·정답·근거, 문항별 순위/점수·시간 표본, split ID, 실제 사례별 감사는 원래 무시된 `artifacts/seven_model/record/`와 `artifacts/seven_model_full_dev/record/`에 둔다. 집계 파일은 Git에 보관하고 원시 레코드는 로컬에 보관한다.
