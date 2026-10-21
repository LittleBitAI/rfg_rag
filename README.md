# RFP RAG — 공공기관 제안요청서 질의응답

## 팀원

| 이름 | 역할 | GitHub |
| --- | --- | --- |
| 황세희 | 전처리 및 파싱 | [@hwangsiiii](https://github.com/hwangsiiii) |
| 김민혁 | 기록 · 이슈 · 버그 처리, 발표 자료 제작 | [@minheouk](https://github.com/minheouk) |
| 이재웅 | Retrieval | [@mitguchin](https://github.com/mitguchin) |
| 서정철 | Generation | [@SeoJungCheol](https://github.com/SeoJungCheol) |
| 채윤휘빈센트 | Generation | — |
| 김민기 | 평가 및 검증 | [@LittleBitAI](https://github.com/LittleBitAI) |

팀원별 협업일지: [협업일지 (Google 스프레드시트)](https://docs.google.com/spreadsheets/d/1ciom4c4E7GuZnrYYwT71he4cOzB56T89PTy-Kf-rXu4/edit?gid=327834733#gid=327834733)

## 프로젝트 소개

공공기관 제안요청서(RFP, PDF · HWP · HWPX)를 청크로 나누고, BM25와 임베딩(FAISS) 하이브리드 검색으로 근거를 찾아 `gpt-6-luna`가 답합니다.
답은 네 가지(Retrieval · Generation · Grounding · End-to-End)로 나눠 채점해, 나쁜 답이 검색 · 생성 · 근거 중 어디서 왔는지 가립니다.

| 항목 | 내용 |
| --- | --- |
| 입력 | 공공기관 RFP 문서 약 100개 (PDF · HWP · HWPX) |
| 검색 | Kiwi 형태소 BM25 + KURE-v1 임베딩, RRF 결합, 발주기관 라우팅, 질문 재작성 |
| 생성 | `gpt-6-luna`, 이전 대화 최대 10개 참고 |
| 평가 | IR 지표(Recall@k · MRR@k · Evidence Coverage), 핵심 사실 문자열 일치, RAGAS Faithfulness · Factual Correctness |
| 화면 | 브라우저 채팅 화면(React + Vite), OCR 라벨링 · 검토 화면 |

## 목차

- [팀원](#팀원)
- [프로젝트 소개](#프로젝트-소개)
- [빠른 시작](#빠른-시작)
- [파이프라인](#파이프라인)
- [질문 화면](#질문-화면)
- [평가](#평가--하나의-답변-파일을-네-가지로)
- [API 사용량](#api-사용량)
- [알아둘 점](#알아둘-점)
- [개발 규칙](#개발-규칙)
- [폴더 구조](#폴더-구조)
- [자세한 문서](#자세한-문서)

## 빠른 시작

### 1. 설치 — Python 3.10 (Windows, NVIDIA GPU)

PyTorch를 먼저 CUDA 빌드로 설치한 뒤 `requirements.txt`를 설치합니다.

```bash
python3.10 -m venv .venv
.venv\Scripts\activate                       # Linux/WSL: source .venv/bin/activate
python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
python -m pip install -r requirements.txt
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"   # 2.x.x+cu128 True
```

- RTX 50 계열(Blackwell sm_120)은 CUDA 12.8 이상 빌드가 필요합니다. cu124 이하는 `no kernel image` 오류가 납니다.
- torchvision도 같이 설치합니다. `easyocr`가 torchvision을 요구해서, 먼저 설치해 두지 않으면 pip가 CPU 빌드 torchvision을 받으며 torch도 CPU 빌드로 바꿉니다. 그러면 임베딩이 CPU로 돌아 몇 시간이 걸립니다.
- macOS는 cu128 빌드 대신 일반 torch를 설치합니다: `.venv/bin/python -m pip install torch`

### 2. `.env`

저장소 최상위에 `.env`를 만듭니다. `LANGFUSE_*`는 선택 사항입니다(프로젝트 책임자용 추적). 키가 없어도 똑같이 동작합니다.

```dotenv
OPENAI_API_KEY=sk-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

### 3. 데이터 준비

| 파일 | 위치 | 설명 |
| --- | --- | --- |
| RFP ZIP | `data/rfp.zip` (`paths.input`, 폴더도 가능) | 원본 문서 |
| 기관 목록 | `data/data_list.csv` (`paths.org_csv`) | UTF-8 CSV, `파일명` · `발주기관` 열(Excel BOM도 읽음). 자동 생성하지 않으니 담당자에게 받으세요. |
| 전처리 패키지 (선택) | `data/` 아래 | 담당자의 저장 청크를 그대로 쓸 때 — [전처리 패키지 사용](docs/preprocessing_package.md) |

`data/` · `artifacts/` · `.env`는 git에 없으므로 팀원과 VM에 따로 전달합니다.

### 4. 노트북 실행

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
- 예외는 ③ 검증에 속한 `golden_pipeline/`(주제별 골든 데이터) 하나입니다 — [golden_pipeline/README.md](golden_pipeline/README.md).
- 공통 설정은 `config.yaml`(파이프라인별 구역), 읽기는 `rag/config.py`가 맡습니다.

### 노트북 설정 셀

01 · 02 · 04 · 05에는 직접 값을 바꾸는 설정 셀이 있습니다. 초기값은 `config.yaml`에서 읽고, 설정 셀은 `config.yaml`을 덮어쓰지 않습니다.

| 노트북 | 설정 셀에서 조절하는 값 |
|---|---|
| 01 전처리 | `OCR`, `OCR_MODEL`, `OCR_REASONING_EFFORT`, `OCR_MAX_TOKENS`, `OCR_PRICES`, `CHUNK_SIZE`, `PREPROCESSED` |
| 02 검색 | `REWRITE_MODEL`, `REWRITE_REASONING_EFFORT`, `REWRITE_MAX_TOKENS`, `REWRITE_PRICES`, `FUSION` (`"rrf"` 순위 합 / `"minmax"` 점수 가중합), `DENSE_WEIGHT` (`minmax`일 때) |
| 04 생성 | `LLM_MODEL`, `LLM_REASONING_EFFORT`, `LLM_MAX_TOKENS`, `LLM_PRICES` |
| 05 평가 | `JUDGE` (`"ragas"` gpt 심판 / `"local"` 로컬 리랭커, API 0원), `JUDGE_MODEL`, `JUDGE_REASONING_EFFORT`, `JUDGE_MAX_TOKENS`, `JUDGE_PRICES` (`ragas`일 때만) |

모델을 바꾸면 같은 셀의 `*_PRICES`도 그 모델의 단가(USD / 100만 토큰)로 맞추세요.

### 검색이 하는 일

1. 질문 재작성: 오타를 고치고, 이어 묻는 질문에 앞 대화의 기관명 · 사업명을 넣고, RFP가 쓰는 낱말(사업예산 · 사업개요 등)로 바꿉니다. 답변은 원래 질문으로 합니다.
2. 기관 라우팅: 질문에 발주기관이 나오면 그 기관 문서 안에서만 찾습니다.
3. 하이브리드 검색: BM25와 임베딩 후보(각 50개)를 RRF로 합치고, 요구사항 코드 일치 · 연결 청크(같은 요구사항 · 같은 표)를 함께 담습니다.
4. 담기: 거의 같은 본문을 빼고 `retrieval.token_budget`(기본 2500 토큰) 안에서 답변 모델에 보냅니다.

`예산 1억원 이상인 사업`처럼 전체 사업의 수량 조건은 별도 필터로 처리합니다. 자세한 동작은 [검색 문서](docs/retrieval.md)와 [수량 조건 검색](docs/quantity_filter.md)에 있습니다.

검색 코드(`indexing.py`)나 사전이 바뀌면 예전 색인으로는 검색이 멈춥니다. 02의 불러오기 · 설정 셀과 `build_index` 셀을 다시 실행하세요(로컬 작업, API 비용 없음).

## 질문 화면

브라우저 채팅 화면입니다. 질문하면 04와 같은 방식(재작성 → 하이브리드 검색 → 답변)으로 답하고, 답변 안의 `[n]` 번호와 출처 카드(파일 · 쪽)를 누르면 근거 청크 본문이 열립니다.

준비물
- 위 설치대로 만든 `.venv`와 `.env`의 `OPENAI_API_KEY`
- 01 · 02를 실행해 만든 `artifacts/chunks.jsonl` · `docs.jsonl` · `index/` · `retrieval_settings.jsonl`
- [Node.js](https://nodejs.org/) LTS

실행
- Windows: `frontend\start.cmd`를 더블클릭합니다. 창 하나에서 질문 API(포트 8767), OCR 화면 API(8766), Vite 개발 서버(5173)가 함께 돌고 브라우저가 열립니다. 처음 한 번은 `npm install` 때문에 오래 걸립니다. 화면을 쓰는 동안 이 창을 닫지 마세요.
- macOS: `frontend/start.command`를 더블클릭합니다.
- 직접 실행 — 저장소 최상위에서 터미널 두 개:
  ```bash
  .venv\Scripts\python -m uvicorn frontend.server:app --port 8767   # macOS: .venv/bin/python
  cd frontend/web && npm install && npm run dev                      # http://localhost:5173
  ```

알아둘 점
- API 서버는 켤 때 색인과 KURE-v1을 읽느라 수십 초 걸립니다. API 창에 `Application startup complete`가 뜬 뒤에 물어보세요.
- 코드나 색인을 바꾼 뒤에는 실행기를 닫고 다시 켜야 반영됩니다.
- 대화는 열린 탭에만 있고, `새 스레드`를 누르거나 탭을 닫으면 사라집니다. 이어서 질문하면 직전 질문 · 답변 최대 10개를 함께 보냅니다.
- 화면의 질문도 OpenAI API를 부르므로 `artifacts/api_usage.csv`에 `rewrite` · `answer` 행이 추가됩니다(노트북 행과는 `timestamp`로만 구분).
- 포트를 바꾸려면 `frontend/start.cmd` · `frontend/start.command`의 8767과 `frontend/web/vite.config.js`의 프록시 주소를 함께 바꿉니다.

같은 실행기에서 `설정` → `OCR 이미지 라벨링` · `OCR 결과 검토` 화면도 열 수 있습니다 — [OCR 화면 안내](docs/ocr_screens.md).

## 평가 — 하나의 답변 파일을 네 가지로

05의 네 평가는 모두 04가 만든 같은 `artifacts/answers.jsonl`을 채점합니다. 표마다 질문별 점수와 맨 아래 `평균` 행이 나오고, 점수 CSV는 답변 파일과 같은 폴더에 저장됩니다.

| 평가 | 판단하는 것 | 지표 | API |
|---|---|---|---|
| Retrieval | 검색이 골든 문서 · 청크를 찾고 컨텍스트에 담았나 | Recall@k · MRR@k · Evidence Coverage, `key_facts_in_context` | 없음 |
| Generation | 답에 핵심 사실 문자열이 있나 | `key_facts_in_answer` | 없음 |
| Grounding | 답이 검색한 청크 안에서만 나왔나 (환각) | RAGAS Faithfulness | 심판 |
| End-to-End | 최종 답이 정답과 맞나 · 얼마나 걸리고 들었나 | RAGAS Factual Correctness, `latency_s` · 토큰 · `cost_usd` | 심판 |

결과 읽는 법
- Retrieval이 낮으면 검색 문제입니다.
- Retrieval은 높은데 Grounding이 낮으면 환각입니다.
- 둘 다 높은데 End-to-End가 낮으면 정답 · 질문을 다시 볼 차례입니다.

알아둘 점
- 핵심 사실(`key_facts_*`)은 공백 · 수치 표기를 정규화한 문자열 일치이며 의미적 정확성 판정이 아닙니다. 답할 수 없음 질문의 `key_facts_in_context`는 평균에서 빼고, 답변 문자열 일치는 거절 문장도 채점합니다.
- 유료 심판은 Grounding과 End-to-End 두 셀뿐이며 `config.yaml`의 `evaluation` 설정을 씁니다.
- `JUDGE = "local"`이면 두 심판 지표를 02의 로컬 리랭커로 API 없이 계산합니다. 답 · 정답을 문장으로 나눠, 리랭커가 (문장, 근거)를 관련 있다고 보고(점수 0.5 이상) 문장 속 숫자 · 날짜가 근거에 모두 있으면 지지로 봅니다. 값의 크기가 RAGAS와 달라 local 점수끼리만 비교하세요. 기본값은 `ragas`입니다.
- 프로젝트 책임자는 Langfuse Cloud에서 질문마다 추적(`answer-question` 안에 `retrieve-context` · `generate-answer`)과 05 점수를 봅니다. 키가 없는 팀원은 노트북 표와 CSV로 봅니다.
- dev로 설정을 조절하고, test는 설정을 고정한 뒤 한 번만 실행합니다.

IR 공식 · 제외율, 검색 전용 재실행, 최종 test 평가, 평가 입력 복원, 골든 라벨 연결은 [평가 문서](docs/evaluation.md)에 있습니다.

## API 사용량

OCR · 질문 재작성 · 답변 생성 · RAGAS 심판의 호출마다 `artifacts/api_usage.csv`에 한 행이 자동으로 추가됩니다(Langfuse 키 없이도). 01 · 02 · 04 · 05의 마지막 셀에서 단계 · 모델별 누적 호출 수, 토큰, 예상 비용을 봅니다.

| `stage` | 기록 대상 | `subject` / `evaluation` |
|---|---|---|
| `ocr` | 이미지 분석 LLM 호출 | 원본 문서 파일명 |
| `rewrite` | 02 검색 예제와 04의 질문 재작성 | 원본 질문 |
| `answer` | 04 답변 생성 | 원본 질문 |
| `judge` | RAGAS 내부 심판 호출 | 평가 종류: grounding / end_to_end (이전 실행의 retrieval / generation 행은 역사 기록) |

- 캐시 입력 토큰은 입력 토큰에, 추론 토큰은 출력 토큰에 이미 포함되어 있습니다. 비용은 캐시 입력 단가를 따로 적용하고 추론 토큰을 이중 과금하지 않습니다.
- RAGAS 내부 재시도도 응답에 사용량이 있으면 기록합니다. Judge 호출은 평가 종류 단위로 집계하며 개별 질문 ID와 연결하지 않습니다.
- 03의 평가 데이터셋 생성 API와 로컬 KURE 임베딩은 기록 대상이 아닙니다. 응답을 받지 못한 요청은 토큰을 알 수 없어 기록하지 않습니다.
- `api_usage.csv`는 재실행해도 누적되고, 점수 CSV는 최신 결과로 덮어씁니다. 새 실험의 사용량만 보려면 실행 전에 기존 파일을 다른 곳에 옮겨 두세요. 파일은 UTF-8(BOM 없음)입니다.

## 알아둘 점

- `langchain-community`는 0.3.31로 고정합니다. ragas 0.4.3이 community 0.4에서 사라진 모듈을 import하기 때문입니다.
- langchain-community 0.3.31의 `PyMuPDFParser`는 그림을 저장하기 전에 빈 버퍼를 검사하는 버그로 모든 그림을 건너뜁니다. `parsing.py`가 OCR을 켤 때만 이 부분을 패치합니다.
- `hwp-hwpx-parser`의 하이퍼링크 컨트롤 무한 루프 버그도 `parsing.py`가 패치합니다.
- GPT-6 LUNA와 gpt-5-mini는 `max_tokens`(`max_completion_tokens`)에 추론 토큰을 포함합니다. 답이 비면 한도나 추론 강도를 바꾸기 전에 토큰 사용량을 먼저 보세요.
- 배포용(암호화) HWP는 본문을 읽을 수 없어 건너뜁니다. 한글에서 일반 `.hwp` · `.hwpx` · PDF로 저장해 넣으세요.
- HWP는 쪽 번호가 없어 HWP 청크의 출처는 섹션 경로로 표시됩니다.
- 그림 OCR은 기본으로 저장된 결과를 읽어 API를 부르지 않습니다(`OCR = False`) — [OCR 문서](docs/ocr.md).

## 개발 규칙

코딩 규칙은 `CLAUDE.md`(= `AGENTS.md`)에 있습니다. 커밋 전에:

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
  server.py                POST /api/ask — answer_question 을 감싸는 FastAPI
  web/                     React + Vite 화면 (ocr.html 라벨링, review.html OCR 결과 검토)
  ocr_select/              OCR 라벨링 · 검토 — extract.py · server.py · merge.py · review.py
  start.cmd · start.command  Windows · macOS 실행기
preprocessing/             전처리 담당자의 EDA · 청킹 비교 · 개선 이력 노트북
tools/                     paddle_ocr.py (PaddleOCR-VL 별도 환경)
docs/                      자세한 문서 · 측정 보고서
tests/                     게이트 (pytest)
eval/                      무시된 과거 논리 경로 — 실제 입력은 artifacts/local_inputs/
artifacts/                 (커밋 안 함) 노트북 사이에 주고받는 파일
```

## 자세한 문서

| 문서 | 내용 |
| --- | --- |
| [검색](docs/retrieval.md) | 재작성 · 하이브리드 검색 · 검색 글 머리말 · 색인 지문 · 04 검색 기록 |
| [수량 조건 검색](docs/quantity_filter.md) | `예산 1억원 이상인 사업` 같은 전체 사업 필터 |
| [평가](docs/evaluation.md) | IR 공식 · 제외율 · 검색 전용 재실행 · 최종 test · 골든 라벨 연결 |
| [전처리 패키지 사용](docs/preprocessing_package.md) | v11 · v12 패키지 출처 · 반영 범위 · 입력 전환 |
| [OCR](docs/ocr.md) | 엔진 선택 · 저장 결과 읽기 · Vision 호출 · CRAFT 선별 |
| [OCR 화면](docs/ocr_screens.md) | 이미지 라벨링 · 결과 검토 화면 |
| [색인 되돌리기](docs/index_rollback.md) | 코드를 되돌릴 때 색인도 맞추는 절차 |
| [측정 보고서](docs/) | Kiwi BM25 · 7모델 임베딩 · OCR 비교 · 수량 필터 검증 · 30문항 표본 |
