# RFP RAG — 공공기관 제안요청서 질의응답 (PDF · HWP · 하이브리드 검색 · gpt-5-mini · RAGAS)

RFP 문서(PDF · HWP · HWPX)를 파싱해 청크로 나누고, BM25 + 임베딩(FAISS) 하이브리드 검색으로 찾은 청크를 근거로 `gpt-5-mini` 가 답합니다.
답은 RAGAS 로 네 가지(Retrieval · Generation · Grounding · End-to-End)로 나눠 채점해, 나쁜 답이 어디서 왔는지 가립니다.

작업은 다섯 파이프라인으로 나뉘고, 파이프라인마다 담당자 한 명 · 노트북 하나 · `rag/` 아래 폴더 하나가 있습니다.
노트북은 설정 · 함수 호출 · 결과 표시만 하고, 로직은 모두 `rag/` 모듈에 있습니다.

## 설치 — GCP VM (SSH · Ubuntu · NVIDIA L4)
VM 사양: `g2-standard-4`(vCPU 4 · 메모리 16GB) + L4 1개, 디스크 200GB 이하, CUDA 드라이버가 든 이미지(예: `ubuntu-accelerator-2204-amd64-with-nvidia-550`).
리전은 `us-central1`, chunk4 배정이면 `us-east1` 입니다.

VS Code Remote-SSH 로 VM 에 접속해 저장소를 받고 `setup_vm.sh` 를 실행합니다.
`.venv` 를 만들고, 드라이버 550 에서 도는 PyTorch CUDA 12.6 빌드 → `requirements.txt` 순서로 설치한 뒤 GPU 가 잡히는지 확인합니다.

```bash
git clone -b feature/Retrieval https://github.com/LittleBitAI/rfg_rag.git
cd rfg_rag
bash setup_vm.sh            # 마지막 줄에 'torch … · NVIDIA L4' 가 나오면 성공
```

> PyPI 기본 `torch` 는 CUDA 13 빌드라 드라이버 580 이상이 필요합니다. `pip install -r requirements.txt` 만 먼저 하면 GPU 를 못 쓰니 꼭 `setup_vm.sh`(또는 cu126 torch 먼저)로 설치하세요.

RFP ZIP 은 로컬 PC 에서 VM 으로 올립니다 (VS Code 탐색기의 `data/` 폴더에 끌어다 놓아도 됩니다).

```bash
gcloud compute scp rfp.zip <VM이름>:~/rfg_rag/data/rfp.zip --zone <존>
```

저장소 최상위에 `.env` 를 만듭니다.

```dotenv
OPENAI_API_KEY=sk-...
# (선택 · 프로젝트 책임자만) 검색 · 생성 추적과 평가 점수를 Langfuse Cloud 로 보냄. 없으면 보내지 않고 똑같이 동작
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

RFP ZIP 은 `data/rfp.zip` 에 둡니다 (`config.yaml` 의 `paths.input`, 폴더도 가능).
발주 기관 목록 `data/data_list.csv`(`paths.org_csv`)는 없으면 02 검색이 문서 표지 · 파일명으로 자동으로 만듭니다.
이미 있는 파일은 덮어쓰지 않으니, 빈 칸이나 틀린 기관명은 직접 고쳐 저장하고 02 를 다시 실행하면 됩니다 (다시 만들려면 파일을 지우세요).
노트북은 VS Code Remote-SSH 에서 `.venv` 커널로 **01 → 05 순서대로** 실행합니다.
처음 실행할 때 임베딩 모델 KURE-v1(약 2.3GB)을 내려받습니다.

## 파이프라인 · 담당

| 파이프라인 | 노트북 | 파일 | 다음 파이프라인에 넘기는 것 |
|---|---|---|---|
| ① 전처리 | `01_preprocessing.ipynb` | `rag/preprocessing/parsing.py` (PDF · HWP/HWPX 파싱 · 정제 · OCR), `rag/preprocessing/chunking.py` (청크 분할) | `artifacts/chunks.jsonl`, `artifacts/docs.jsonl` |
| ② 검색 | `02_retrieval.ipynb` | `rag/retrieval/indexing.py` (임베딩 · FAISS · BM25 색인), `rag/retrieval/retrieval.py` (하이브리드 검색 · 발주기관 라우팅) | `artifacts/index/` |
| ③ 검증 | `03_validation.ipynb` | `rag/validation/validation.py` (QA 생성 · 근거 키워드 정리 · 분할 · 평가 항목 점검) | `artifacts/eval_set.jsonl` |
| ④ 생성 | `04_generation.ipynb` | `rag/generation/generation.py` (검색 → 답변 · 토큰 · 지연 시간) | `artifacts/answers.jsonl` |
| ⑤ 평가 | `05_evaluation.ipynb` | `rag/evaluation/evaluation.py` (네 가지 평가) | `artifacts/retrieval.csv` · `generation.csv` · `grounding.csv` · `end_to_end.csv` |

공통: `rag/config.py` (`config.yaml` · `.env` 읽기, jsonl 읽기/쓰기), `config.yaml` (모든 설정 — 파이프라인별 구역).

## 평가 — 하나의 답변 파일을 네 가지로

05 의 네 평가는 모두 04 가 만든 같은 `artifacts/answers.jsonl` 을 채점합니다. 표마다 질문별 점수와 맨 아래 `평균` 행이 나옵니다.

| 평가 | 판단하는 것 | 지표 |
|---|---|---|
| Retrieval | 검색한 청크가 정답에 필요한 내용을 담았나 | RAGAS `context_precision` · `context_recall`, 검색 청크 속 핵심 사실 비율 `key_facts_in_context` |
| Generation | 답이 질문에 맞고 핵심 사실을 담았나 | RAGAS `answer_relevancy` (KURE-v1 임베딩), 답 속 핵심 사실 비율 `key_facts_in_answer` |
| Grounding | 답이 검색한 청크 안에서만 나왔나 (환각) | RAGAS `faithfulness` |
| End-to-End | 최종 답이 정답과 맞나 · 얼마나 걸리고 들었나 | RAGAS `factual_correctness`, 질문당 `latency_s` · 입력/출력/추론 토큰 · 예상 비용 `cost_usd` |

- Retrieval 이 낮으면 검색 문제, Retrieval 은 높은데 Grounding 이 낮으면 환각, 둘 다 높은데 End-to-End 가 낮으면 정답 · 질문을 다시 볼 차례입니다.
- 심판 LLM 은 `config.yaml` 의 `evaluation.judge_model`(`gpt-5-mini`)입니다. 평가할 때마다 OpenAI 비용이 듭니다.
- 프로젝트 책임자는 Langfuse Cloud 에서 질문마다 추적 하나(`answer-question` 안에 검색 `retrieve-context` · 생성 `generate-answer` — 모델 · 토큰 · 비용 포함)를 보고, 05 의 질문별 점수도 그 추적에 붙어 있습니다. 키가 없는 팀원은 노트북 표와 CSV 로 봅니다.

### 평가 데이터셋 (03 검증)
- `eval/golden_set.jsonl`: 직접 만든 질문 · 정답(`reference`) · 핵심 사실(`key_facts`).
- `eval/eval_questions.yaml`: 오타 · 한영 자판 · 한자 · 영어 혼용 · 잘못된 전제 질문(연말정산)과 RFP 질문. 핵심 사실은 `must_include` (`'A|B'` = 둘 중 하나).
- 청크로 만든 QA 의 test 분할 (최대 `validation.max_qa` 개, 핵심 사실 = 근거 키워드).
- 질문 없음 · 중복 질문 · 대화의 후속 질문 · 정답 없음 · 핵심 사실 없음은 사유와 함께 제외합니다.

> ⚠️ 연말정산 질문의 근거(국세청 연말정산 안내 등)가 ZIP 에 없으면 "제공된 문서에서 확인할 수 없습니다" 가 정상 답입니다.

## OCR (선택, 기본 꺼짐)
`01_preprocessing.ipynb` 의 `OCR = False` 를 `True` 로 바꾸면, 문서 속 그림을 LangChain `LLMImageBlobParser` + OpenAI 비전 모델(`gpt-5-mini`, `.env` 의 `OPENAI_API_KEY`)로 글로 바꿔 청크에 넣습니다.
여러 쪽에 반복되는 그림(로고 · 장식, `parsing.max_repeat_image_pages` 쪽 이상)은 청크에 넣지 않습니다 — HWP 는 아예 보내지 않고, PDF 는 설명을 받은 뒤 반복된 설명을 뺍니다.
`False` 면 그림은 API 로 가지 않습니다.

## 알아둘 점
- `langchain-community` 는 **0.3.31 로 고정**합니다. ragas 0.4.3 이 community 0.4 에서 사라진 모듈을 import 하기 때문입니다.
- langchain-community 0.3.31 의 `PyMuPDFParser` 는 그림을 저장하기 전에 빈 버퍼를 검사하는 버그로 모든 그림을 건너뜁니다. `parsing.py` 가 OCR 을 켤 때만 이 부분을 패치합니다.
- `hwp-hwpx-parser` 의 하이퍼링크 컨트롤 무한 루프 버그도 `parsing.py` 가 패치합니다.
- `gpt-5-mini` 는 추론 모델이라 `max_tokens`(= `max_completion_tokens`)에 추론 토큰이 포함됩니다. 답이 비면 값을 늘리거나 `reasoning_effort` 를 낮추세요.
- 배포용(암호화) HWP 는 본문을 읽을 수 없어 건너뜁니다. 한글에서 일반 `.hwp` · `.hwpx` · PDF 로 저장해 넣으세요.
- HWP 는 쪽 번호가 없어 HWP 청크의 출처는 섹션 경로로 표시됩니다.

## 개발 규칙
코딩 규칙은 `CLAUDE.md`(= `AGENTS.md`)에 있습니다. 커밋 전에:

```bash
ruff check .                              # 함수 복잡도 (C901 ≤ 8, PLR0915 ≤ 50)
.venv/bin/python -m pytest -q tests       # rag/ 모든 모듈 import 확인
```

- `.env` · `data/` · `artifacts/` 는 커밋하지 않습니다.
- 노트북은 출력을 지우고 커밋합니다.
- `rag/*.py` 를 고친 뒤에는 커널을 재시작하고 다시 실행합니다.



## 구조
```
01_preprocessing.ipynb … 05_evaluation.ipynb   파이프라인별 노트북 (설정 · 호출 · 표만)
config.yaml                설정 (① 전처리 ~ ⑤ 평가 구역)
setup_vm.sh                GCP VM 설치 (.venv · torch cu126 · requirements.txt · GPU 확인)
eval/
  golden_set.jsonl         골든 셋 (질문 · 정답 · 핵심 사실)
  eval_questions.yaml      평가 질문 세트 (질문 · 정답 · must_include)
rag/
  config.py                config.yaml · .env 읽기, jsonl 읽기/쓰기
  preprocessing/           ① parsing.py · chunking.py
  retrieval/               ② indexing.py · retrieval.py
  validation/              ③ validation.py
  generation/              ④ generation.py
  evaluation/              ⑤ evaluation.py
tests/test_smoke.py        게이트: rag/ 모든 모듈 import
artifacts/                 (커밋 안 함) 노트북 사이에 주고받는 파일
```

