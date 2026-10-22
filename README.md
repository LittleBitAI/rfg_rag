# 입찰메이트

공공기관 제안요청서(RFP)를 읽고, 질문에 근거를 붙여 답하는 질의응답 시스템입니다.

## 결과 요약

처음 보는 test 질문으로 평가한 결과, 답할 수 있는 질문의 83.7%를 맞혔습니다.
질문 하나에 답하는 데 보통 5초가 걸리고, 질문 1,000개를 처리하는 언어 모델 이용료는 약 0.72달러입니다.

| 지표 | test 결과 | 뜻 |
| --- | --- | --- |
| 정답률 | 83.7% | 답할 수 있는 질문 872개 가운데 맞힌 비율 |
| Doc Recall@10 | 0.994 | 상위 10개 검색 결과에 정답 문서가 들어 있는 비율 |
| Chunk Recall@10 | 0.937 | 상위 10개 검색 결과에 정답 근거 조각이 들어 있는 비율 |
| Evidence Coverage | 0.915 | 정답 근거 가운데 답변 모델에 실제로 넘어간 비율 |
| Faithfulness | 0.769 | 답변 내용 가운데 넘겨받은 근거로 뒷받침되는 비율 |
| 응답 시간 | 5.0초 (p50) · 6.9초 (p90) | 질문 절반은 5.0초, 열에 아홉은 6.9초 안에 끝납니다 |

- 틀린 답은 여러 근거를 모아야 하는 질문에 몰려 있습니다.
- 응답 시간은 대부분 언어 모델을 두 번(질문 다듬기, 답변 작성) 부르는 데 쓰입니다.

평가 방법, dev 결과, 틀린 답 분석은 [보고서 3](docs/reports/rfg_rag_보고서3_dev와_test_set으로_rag를_평가한_결과.pdf)에 있습니다.

## 동작 방식

1. 질문 다듬기: 앞선 대화를 반영해, 질문을 검색하기 좋은 문장으로 고쳐 씁니다.
2. 문서 찾기: RFP 98건에서 질문과 관련된 조각을 찾습니다. 질문에 발주기관 이름이 있으면 그 기관 문서 안에서만 찾습니다.
3. 답변 작성: 찾은 조각만 보고 답하며, 답 안에 출처 번호를 붙입니다.

| 단계 | 사용한 것 |
| --- | --- |
| 문서 읽기 | PDF · HWP · HWPX 파싱, 그림 속 글자는 저장해 둔 OCR 결과 |
| 검색 | Kiwi 형태소 분석 BM25 + KURE-v1 임베딩, 두 결과를 RRF로 합침 |
| 답변 | gpt-6-luna, 앞선 대화를 최대 10개까지 참고 |
| 평가 | 검색 · 답변 · 근거 · 최종 정답의 네 가지로 나눠 채점 |
| 화면 | 브라우저 채팅 화면 (React + Vite) |

## 팀원

| 이름 | 역할 | GitHub |
| --- | --- | --- |
| 황세희 | 전처리 및 파싱 | [@hwangsiiii](https://github.com/hwangsiiii) |
| 김민혁 | 기록 · 이슈 · 버그 처리, 발표 자료 제작 | [@minheouk](https://github.com/minheouk) |
| 이재웅 | 검색 (Retrieval) | [@mitguchin](https://github.com/mitguchin) |
| 서정철 | 답변 생성 (Generation) | [@SeoJungCheol](https://github.com/SeoJungCheol) |
| 채윤휘빈센트 | 답변 생성 (Generation) | [@mackievboy](https://github.com/mackievboy) |
| 김민기 | 평가 및 검증 | [@LittleBitAI](https://github.com/LittleBitAI) |

팀원별 협업일지는 [Google 스프레드시트](https://docs.google.com/spreadsheets/d/1ciom4c4E7GuZnrYYwT71he4cOzB56T89PTy-Kf-rXu4/edit?gid=327834733#gid=327834733)에 있습니다.

## 보고서

파트별 담당자가 작성한 보고서와 발표 자료입니다. 파일은 [docs/reports/](docs/reports/)에 있습니다.

| 파트 | 담당 | 보고서 | 내용 |
| --- | --- | --- | --- |
| 전처리 | 황세희 | [RFP EDA · 전처리 보고서](docs/reports/RFP_EDA_Processing_보고서.pdf) | 원본 EDA부터 표 · 이미지 · 문자 정제, 청킹 비교, v12 원문 보존 확인까지 |
| 전처리 | 황세희 | [EDA 최종 발표 · 회고](docs/reports/EDA_최종발표본_회고.pptx) | 중복 문서 확인, 본문 · 표 중복, 이미지 추출, 요구사항 번호 처리, 회고 |
| 검색 | 이재웅 | [Retrieval 발표](docs/reports/Retrieval_이재웅.pdf)| 검색 다섯 단계, 하이브리드 검색, 임베딩 모델 선택, 재작성 추론 강도 비교 |
| 생성 | 서정철 | [Generation 발표](docs/reports/generation_발표자료.pptx) | 답변 생성의 입력 · 처리 흐름 · 모델 설정 |
| 평가 | 김민기 | [보고서 1 · 평가 방법](docs/reports/rfg_rag_보고서1_평가방법.pdf) | 네 가지 평가와 지표를 정한 방법 |
| 평가 | 김민기 | [보고서 2 · 평가 데이터셋](docs/reports/rfg_rag_보고서2_평가데이터셋.pdf) | dev · test 평가 데이터셋을 만들고 검증한 과정 |
| 평가 | 김민기 | [보고서 3 · dev와 test 평가 결과](docs/reports/rfg_rag_보고서3_dev와_test_set으로_rag를_평가한_결과.pdf) | 청킹 · 기관 필터 비교, 최종 정답률 · 응답 시간 · 비용 |
| 평가 | 김민기 | [보고서 3 · 골든 데이터셋 A·B·C 비교](docs/reports/rfg_rag_보고서3_골든데이터셋_ABC_비교_보고서.pdf) | 골든 데이터셋을 만드는 세 방식을 일곱 주제에서 비교 |

## 목차

- [빠른 시작](#빠른-시작)
- [파이프라인](#파이프라인)
- [질문 화면](#질문-화면)
- [평가](#평가)
- [API 사용량](#api-사용량)
- [알아둘 점](#알아둘-점)
- [개발 규칙](#개발-규칙)
- [폴더 구조](#폴더-구조)
- [자세한 문서](#자세한-문서)

## 빠른 시작

### 1. 설치하기

Python 3.10과 NVIDIA GPU가 있는 Windows를 기준으로 합니다. PyTorch를 먼저 CUDA 빌드로 설치한 뒤 `requirements.txt`를 설치합니다.

```bash
python3.10 -m venv .venv
.venv\Scripts\activate                       # Linux/WSL: source .venv/bin/activate
python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
python -m pip install -r requirements.txt
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"   # 2.x.x+cu128 True
```

- RTX 50 계열(Blackwell sm_120)은 CUDA 12.8 이상 빌드가 필요합니다. cu124 이하는 `no kernel image` 오류가 납니다.
- torchvision도 같이 설치합니다. `easyocr`가 torchvision을 요구해서, 먼저 설치해 두지 않으면 pip가 CPU 빌드 torchvision을 받으며 torch도 CPU 빌드로 바꿉니다. 그러면 임베딩이 CPU로 돌아 몇 시간이 걸립니다.
- macOS에서는 cu128 빌드 대신 일반 torch를 설치합니다. 명령은 `.venv/bin/python -m pip install torch`입니다.

### 2. API 키 넣기

저장소 최상위에 `.env` 파일을 만들고 OpenAI 키를 넣습니다. Langfuse 키는 프로젝트 책임자가 실행 기록을 볼 때만 쓰는 선택 사항이며, 없어도 똑같이 동작합니다.

```dotenv
OPENAI_API_KEY=sk-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

### 3. 데이터 준비

| 파일 | 위치 | 설명 |
| --- | --- | --- |
| RFP 원본 | `data/rfp.zip` (폴더도 됩니다) | 원본 문서 |
| 기관 목록 | `data/data_list.csv` | `파일명` · `발주기관` 열이 있는 CSV입니다. 자동으로 만들지 않으니 담당자에게 받으세요. |
| 전처리 패키지 (선택) | `data/` 아래 | 담당자가 만든 청크를 그대로 쓸 때 필요합니다. [전처리 패키지 사용](docs/preprocessing_package.md)을 보세요. |

`data/` · `artifacts/` · `.env`는 git에 올리지 않으므로 팀원과 VM에 따로 전달합니다.

### 4. 노트북 실행하기

VS Code · PyCharm · Jupyter에서 `.venv` 커널로 01 → 05 순서대로 실행합니다. 처음 실행할 때 임베딩 모델 KURE-v1(약 2.3GB)을 내려받습니다.
각 노트북은 앞 노트북이 `artifacts/`에 남긴 결과를 읽습니다.

<details>
<summary>팀 VM <code>codeit</code>에서 작업하기 (VS Code Remote-SSH, GPU NVIDIA L4)</summary>

코드는 그대로이고, VS Code가 VM에 접속해 VM의 GPU로 실행합니다. 임베딩은 GPU가 있으면 알아서 `cuda`를 씁니다.

1. 내 PC의 `~/.ssh/config`에 항목을 넣습니다 (`User`는 본인 VM 계정, 키는 `gcloud compute ssh`가 만든 것).
   ```
   Host codeit
       HostName 35.255.64.243
       User spai13xx
       IdentityFile ~/.ssh/google_compute_engine
       IdentitiesOnly yes
       ServerAliveInterval 30
   ```
2. VS Code에서 `Remote-SSH: Connect to Host...` → `codeit`을 고르고, 처음 한 번 VM 터미널에서 설치합니다.
   ```bash
   git clone https://github.com/LittleBitAI/rfg_rag ~/rfg_rag && cd ~/rfg_rag
   python3.10 -m venv .venv
   .venv/bin/python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
   .venv/bin/python -m pip install -r requirements.txt
   .venv/bin/python -c "import torch; print(torch.cuda.is_available())"   # True
   ```
3. `.env`와 `data/`는 내 PC에서 한 번 복사합니다. VM은 여럿이 같이 쓰므로 `.env`는 본인만 읽게 합니다.
   ```bash
   scp .env codeit:rfg_rag/.env
   scp -r data codeit:rfg_rag/
   ssh codeit chmod 600 rfg_rag/.env
   ```
4. VS Code에서 폴더 `~/rfg_rag`를 열고 노트북 커널로 `.venv`를 고릅니다.

`artifacts/`는 복사하지 않습니다. 기기마다 그 기기에서 돌린 노트북 결과가 쌓입니다.

</details>

## 파이프라인

```
RFP 문서 ──① 전처리──▶ 청크 ──② 검색──▶ 근거 청크 ──④ 생성──▶ 답변 ──⑤ 평가──▶ 점수 CSV
                                   ③ 검증 ──▶ 평가 데이터셋 ──────────────────┘
```

| 파이프라인 | 노트북 | 주요 파일 | 넘기는 것 |
|---|---|---|---|
| ① 전처리 | `01_preprocessing.ipynb` | `rag/preprocessing/parsing.py` (PDF · HWP 파싱 · OCR), `chunking.py` (청크 분할 · 패키지 읽기) | `artifacts/chunks.jsonl`, `docs.jsonl` |
| ② 검색 | `02_retrieval.ipynb` | `rag/retrieval/indexing.py` (색인), `rewrite.py` (질문 재작성), `retrieval.py` (하이브리드 검색 · 기관 라우팅) | `artifacts/index/`, `retrieval_settings.jsonl` |
| ③ 검증 | `03_validation.ipynb` | `rag/validation/validation.py` (골든 dev · 평가 질문 · 근거 라벨) | `artifacts/eval_set.jsonl` |
| ④ 생성 | `04_generation.ipynb` | `rag/generation/generation.py` (재작성 → 검색 → 답변) | `artifacts/answers.jsonl` |
| ⑤ 평가 | `05_evaluation.ipynb` | `rag/evaluation/evaluation.py`, `ir.py` (네 가지 평가) | `artifacts/retrieval.csv` · `generation.csv` · `grounding.csv` · `end_to_end.csv` |
| ⑥ 화면 | — | `frontend/` (질문 화면 · OCR 라벨링 · OCR 결과 검토) | 브라우저 화면, `artifacts/ocr_labels/` |

- 노트북은 설정 · 함수 호출 · 결과 표시만 하고, 로직은 모두 `rag/` 모듈에 있습니다.
- 예외는 ③ 검증에 속한 `golden_pipeline/`(주제별 골든 데이터) 하나입니다. 설명은 [golden_pipeline/README.md](golden_pipeline/README.md)에 있습니다.
- 공통 설정은 `config.yaml`에 있고, `rag/config.py`가 읽습니다.

### 노트북 설정 셀

01 · 02 · 04 · 05에는 값을 직접 바꾸는 설정 셀이 있습니다. 처음 값은 `config.yaml`에서 읽고, 설정 셀에서 바꿔도 `config.yaml`은 그대로 남습니다.

| 노트북 | 설정 셀에서 바꿀 수 있는 것 |
|---|---|
| 01 전처리 | OCR 사용 여부 · OCR 모델 · 청크 크기 · 전처리 패키지 사용 여부 |
| 02 검색 | 질문 다듬기 모델 · 검색 결과를 합치는 방식 (`"rrf"`는 순위로, `"minmax"`는 점수로 합칩니다) |
| 04 생성 | 답변 모델 · 출력 토큰 한도 |
| 05 평가 | 채점 방식 (`"ragas"`는 GPT가 채점하고, `"local"`은 로컬 모델이 API 비용 없이 채점합니다) · 채점 모델 |

모델을 바꾸면 같은 셀의 단가(`*_PRICES`, 100만 토큰당 달러)도 그 모델에 맞게 바꾸세요.

### 검색이 하는 일

1. 질문 다듬기: 오타를 고치고, 이어 묻는 질문에는 앞 대화의 기관명 · 사업명을 넣고, RFP에서 쓰는 낱말(사업예산, 사업개요 등)로 바꿉니다. 답변은 원래 질문을 보고 씁니다.
2. 기관으로 좁히기: 질문에 발주기관이 나오면 그 기관 문서 안에서만 찾습니다.
3. 두 방식으로 찾기: BM25와 임베딩으로 후보를 50개씩 찾아 RRF로 합칩니다. 요구사항 번호가 정확히 맞는 조각과, 같은 요구사항 · 같은 표에서 나온 조각도 함께 담습니다.
4. 넘기기: 거의 같은 내용은 빼고, 2,500토큰 안에서 답변 모델에 넘깁니다.

`예산 1억원 이상인 사업`처럼 여러 사업을 수량 조건으로 고르는 질문은 별도 필터가 처리합니다. 자세한 내용은 [검색 문서](docs/retrieval.md)와 [수량 조건 검색](docs/quantity_filter.md)에 있습니다.

검색 코드(`indexing.py`)나 사전이 바뀌면 예전 색인으로는 검색이 멈춥니다. 그때는 02의 불러오기 · 설정 셀과 `build_index` 셀을 다시 실행하세요. 내 PC에서만 도는 작업이라 API 비용은 들지 않습니다.

## 질문 화면

브라우저 채팅 화면입니다. 질문하면 04와 같은 순서(질문 다듬기 → 검색 → 답변)로 답합니다. 답변 안의 `[n]` 번호나 출처 카드(파일 · 쪽)를 누르면 근거 본문이 열립니다.

준비물
- 위 설치대로 만든 `.venv`와 `.env`의 `OPENAI_API_KEY`
- 01 · 02를 실행해 만든 `artifacts/chunks.jsonl` · `docs.jsonl` · `index/` · `retrieval_settings.jsonl`
- [Node.js](https://nodejs.org/) LTS

실행
- Windows: `frontend\start.cmd`를 더블클릭합니다. 창 하나에서 질문 API(포트 8767), OCR 화면 API(8766), Vite 개발 서버(5173)가 함께 돌고 브라우저가 열립니다. 처음 한 번은 `npm install` 때문에 오래 걸립니다. 화면을 쓰는 동안 이 창을 닫지 마세요.
- macOS: `frontend/start.command`를 더블클릭합니다.
- 직접 실행하려면 저장소 최상위에서 터미널 두 개를 엽니다.
  ```bash
  .venv\Scripts\python -m uvicorn frontend.server:app --port 8767   # macOS: .venv/bin/python
  cd frontend/web && npm install && npm run dev                      # http://localhost:5173
  ```

알아둘 점
- API 서버는 켤 때 색인과 KURE-v1을 읽느라 수십 초 걸립니다. API 창에 `Application startup complete`가 뜬 뒤에 물어보세요.
- 코드나 색인을 바꾼 뒤에는 실행기를 닫고 다시 켜야 반영됩니다.
- 대화는 열린 탭에만 있고, `새 스레드`를 누르거나 탭을 닫으면 사라집니다. 이어서 질문하면 직전 질문 · 답변 최대 10개를 함께 보냅니다.
- 화면에서 한 질문도 OpenAI API를 부르므로 `artifacts/api_usage.csv`에 기록됩니다.
- 포트를 바꾸려면 `frontend/start.cmd` · `frontend/start.command`의 8767과 `frontend/web/vite.config.js`의 프록시 주소를 함께 바꿉니다.

같은 실행기에서 `설정` → `OCR 이미지 라벨링` · `OCR 결과 검토` 화면도 열 수 있습니다. 사용법은 [OCR 화면 안내](docs/ocr_screens.md)에 있습니다.

## 평가

05는 04가 만든 답변 파일 하나를 네 가지로 채점합니다. 그래서 틀린 답이 검색, 답변, 근거 중 어디서 잘못됐는지 가릴 수 있습니다. 표마다 질문별 점수와 맨 아래 평균이 나오고, 점수 CSV는 답변 파일과 같은 폴더에 저장됩니다.

| 평가 | 보는 것 | 지표 | API 비용 |
|---|---|---|---|
| 검색 (Retrieval) | 정답 문서 · 근거를 찾아 답변 모델에 넘겼는가 | Recall@k · MRR@k · Evidence Coverage, 넘긴 글의 핵심 문구 일치 | 없음 |
| 답변 (Generation) | 답에 정답의 핵심 문구가 있는가 | 답변의 핵심 문구 일치 | 없음 |
| 근거 (Grounding) | 답이 넘겨받은 근거 안에서만 나왔는가 | Faithfulness (RAGAS) | 있음 |
| 최종 (End-to-End) | 최종 답이 정답과 맞는가, 시간과 비용은 얼마인가 | Factual Correctness (RAGAS), 응답 시간 · 토큰 · 비용 | 있음 |

결과 읽는 법
- 검색 점수가 낮으면 검색 문제입니다.
- 검색 점수는 높은데 근거 점수가 낮으면, 근거에 없는 내용을 지어낸 것입니다.
- 둘 다 높은데 최종 점수가 낮으면 정답이나 질문을 다시 볼 차례입니다.

알아둘 점
- 핵심 문구 일치는 띄어쓰기와 숫자 표기를 맞춘 뒤 글자를 비교합니다. 뜻이 맞는지는 보지 않습니다.
- 답할 수 없는 질문은 넘긴 글의 핵심 문구 점수 평균에서 뺍니다.
- 비용이 드는 채점은 근거와 최종 두 가지뿐입니다.
- `JUDGE = "local"`로 두면 이 두 채점을 로컬 모델로 API 비용 없이 합니다. 점수 크기가 RAGAS와 달라서 local 점수끼리만 비교하세요. 기본값은 `"ragas"`입니다.
- 프로젝트 책임자는 Langfuse에서 질문마다 실행 기록과 점수를 봅니다. 키가 없는 팀원은 노트북 표와 CSV 파일로 봅니다.
- 설정은 dev로 조절하고, test는 설정을 고정한 뒤 한 번만 실행합니다.

지표 계산식, 검색만 다시 돌리는 방법, 최종 test 평가 순서는 [평가 문서](docs/evaluation.md)에 있습니다.

## API 사용량

OCR, 질문 다듬기, 답변 작성, RAGAS 채점에서 API를 부를 때마다 `artifacts/api_usage.csv`에 한 줄씩 기록됩니다. Langfuse 키가 없어도 기록됩니다. 01 · 02 · 04 · 05의 마지막 셀에서 단계별 · 모델별 호출 수, 토큰, 예상 비용을 볼 수 있습니다.

| 단계 (`stage`) | 기록하는 호출 | `subject` 열에 들어가는 값 |
|---|---|---|
| `ocr` | 그림 속 글자 읽기 | 원본 문서 파일 이름 |
| `rewrite` | 질문 다듬기 (02 예제, 04) | 원래 질문 |
| `answer` | 답변 작성 (04) | 원래 질문 |
| `judge` | RAGAS 채점 | 평가 종류 (grounding, end_to_end) |

- 비용은 캐시 입력 단가를 따로 적용해 계산하고, 추론 토큰을 두 번 세지 않습니다.
- 03에서 평가 데이터셋을 만들 때 쓴 API와 로컬 임베딩은 기록하지 않습니다.
- `api_usage.csv`는 다시 실행해도 계속 쌓이고, 점수 CSV는 최신 결과로 덮어씁니다. 새 실험의 사용량만 보려면 실행 전에 기존 파일을 다른 곳으로 옮겨 두세요.

## 알아둘 점

- `langchain-community`는 0.3.31로 고정합니다. ragas 0.4.3이 0.4 버전에서 없어진 모듈을 불러오기 때문입니다.
- langchain-community 0.3.31의 PDF 파서에는 그림을 모두 건너뛰는 버그가 있어, OCR을 켤 때만 `parsing.py`가 이 부분을 고쳐 씁니다.
- `hwp-hwpx-parser`가 하이퍼링크에서 멈추는 버그도 `parsing.py`가 고쳐 씁니다.
- gpt-6-luna와 gpt-5-mini는 출력 토큰 한도에 추론 토큰도 포함합니다. 답이 비어 있으면 한도를 바꾸기 전에 토큰 사용량부터 확인하세요.
- 배포용(암호화) HWP는 본문을 읽을 수 없어 건너뜁니다. 한글에서 일반 `.hwp` · `.hwpx` · PDF로 다시 저장해 넣으세요.
- HWP는 쪽 번호가 없어서 출처가 쪽 대신 제목 경로로 표시됩니다.
- 그림 속 글자는 저장해 둔 OCR 결과를 읽으므로, 기본 설정에서는 API를 부르지 않습니다. 자세한 내용은 [OCR 문서](docs/ocr.md)에 있습니다.

## 개발 규칙

코딩 규칙은 `CLAUDE.md`(`AGENTS.md`와 내용이 같습니다)에 있습니다. 커밋하기 전에 아래 두 명령을 실행합니다.

```bash
ruff check .                              # 함수 복잡도 (C901 ≤ 8, PLR0915 ≤ 50)
.venv\Scripts\python -m pytest -q tests   # Linux: .venv/bin/python -m pytest -q tests
```

- `.env` · `data/` · `artifacts/`는 커밋하지 않습니다. 실제 질문 · 정답 · 문서 본문 · OCR 텍스트도 커밋하지 않고, 집계 수치만 올립니다.
- 노트북은 출력을 지우고 커밋합니다.
- `rag/*.py`를 고친 뒤에는 커널을 재시작하고 다시 실행합니다.

## 폴더 구조

```
01_preprocessing.ipynb … 05_evaluation.ipynb   파이프라인별 노트북 (설정 · 호출 · 표만)
config.yaml                설정 (① 전처리 ~ ⑤ 평가 구역)
rag/
  config.py                config.yaml · .env 읽기, jsonl 읽기/쓰기
  usage.py                 API 사용량 기록 (api_usage.csv)
  preprocessing/           ① parsing.py · chunking.py · OCR 캡션 · CRAFT 선별
  retrieval/               ② indexing.py · rewrite.py · retrieval.py · 수량 필터 · benchmark/
  validation/              ③ validation.py · evidence.py · local_inputs.py
  generation/              ④ generation.py
  evaluation/              ⑤ evaluation.py · ir.py
golden_pipeline/           ③ 주제별 골든 데이터 (테스트는 tests/golden/)
frontend/                  ⑥ 화면
  server.py                질문 API 서버 (FastAPI)
  web/                     React + Vite 화면 (ocr.html 라벨링, review.html OCR 결과 검토)
  ocr_select/              OCR 라벨링 · 검토 (extract.py · server.py · merge.py · review.py)
  start.cmd · start.command  Windows · macOS 실행기
preprocessing/             전처리 담당자의 EDA · 청킹 비교 · 개선 이력 노트북
tools/                     paddle_ocr.py (PaddleOCR-VL 별도 환경)
docs/                      자세한 문서 · 측정 보고서 · 팀 보고서(reports/)
tests/                     게이트 (pytest)
eval/                      예전 경로 (실제 평가 입력은 artifacts/local_inputs/)
artifacts/                 (커밋 안 함) 노트북 사이에 주고받는 파일
```

## 자세한 문서

| 문서 | 내용 |
| --- | --- |
| [검색](docs/retrieval.md) | 질문 다듬기 · 두 방식 검색 · 색인 다시 만들기 · 04의 검색 기록 |
| [수량 조건 검색](docs/quantity_filter.md) | `예산 1억원 이상인 사업`처럼 여러 사업을 고르는 필터 |
| [평가](docs/evaluation.md) | 지표 계산식 · 검색만 다시 돌리기 · 최종 test 평가 · 정답 근거 연결 |
| [전처리 패키지 사용](docs/preprocessing_package.md) | v11 · v12 패키지를 받아 쓰는 방법 |
| [OCR](docs/ocr.md) | OCR 엔진 선택 · 저장 결과 읽기 · Vision 호출 · CRAFT 선별 |
| [OCR 화면](docs/ocr_screens.md) | 이미지 라벨링 · 결과 검토 화면 |
| [색인 되돌리기](docs/index_rollback.md) | 코드를 되돌릴 때 색인도 맞추는 절차 |
| [측정 보고서](docs/) | Kiwi BM25 · 7모델 임베딩 · OCR 비교 · 수량 필터 검증 · 30문항 표본 |
