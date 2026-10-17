# RFP RAG — Public institution RFP Q&A (PDF · HWP · Hybrid Search · GPT-6 LUNA · RAGAS)

RFP documents (PDF, HWP and HWPX) are parsed into chunks. BM25 and embedding-based FAISS search retrieve evidence for answers from `gpt-6-luna`.
답은 네 가지(Retrieval · Generation · Grounding · End-to-End)로 나눠 채점합니다. 검색은 결정적 IR 지표, 핵심 사실은 문자열 일치, 근거 충실도와 최종 정답은 RAGAS 심판으로 확인해 나쁜 답이 어디서 왔는지 가립니다.

작업은 다섯 파이프라인으로 나뉘고, 파이프라인마다 담당자 한 명 · 노트북 하나 · `rag/` 아래 폴더 하나가 있습니다.
노트북은 설정 · 함수 호출 · 결과 표시만 하고, 로직은 모두 `rag/` 모듈에 있습니다.
예외는 ③ 검증에 속한 `golden_pipeline/`(주제별 골든 데이터) 하나입니다 — [golden_pipeline/README.md](golden_pipeline/README.md).

## 설치 — Python 3.10 (Windows, NVIDIA GPU)
PyTorch 를 **먼저** CUDA 빌드로 설치한 뒤 `requirements.txt` 를 설치합니다.
RTX 50 계열(Blackwell sm_120)은 CUDA 12.8 이상 빌드가 필요합니다 (cu124 이하는 `no kernel image` 오류).
torchvision 도 같이 설치합니다. `easyocr` 가 torchvision 을 요구해, 먼저 설치해 두지 않으면 pip 가 PyPI 의
CPU 빌드 torchvision 을 받으면서 torch 도 CPU 빌드로 바꿉니다. 그러면 임베딩이 GPU 대신 CPU 로 돌아 몇 시간이 걸립니다.

```bash
python3.10 -m venv .venv
.venv\Scripts\activate                       # Linux/WSL: source .venv/bin/activate
python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
python -m pip install -r requirements.txt
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"   # 2.x.x+cu128 True
```

저장소 최상위에 `.env` 를 만듭니다.
프로젝트 책임자는 선택 사항인 `LANGFUSE_*` 키로 검색·생성 추적과 평가 점수를
Langfuse Cloud로 보낼 수 있습니다. 키가 없어도 보내지 않고 똑같이 동작합니다.

```dotenv
OPENAI_API_KEY=sk-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

RFP ZIP 은 `data/rfp.zip` 에 둡니다 (`config.yaml` 의 `paths.input`, 폴더도 가능).
검색에 필요한 `data/data_list.csv`도 담당자에게 받아 둡니다 (`paths.org_csv`).
UTF-8 CSV에 `파일명`, `발주기관` 열이 있어야 합니다. Excel이 붙인 BOM도 읽습니다. 목록은 자동 생성하지 않으며,
파일이 없으면 02 색인·검색과 질문 화면을 실행하기 전에 담당자에게 요청하세요.
검색은 요구사항 코드 일치 청크를 먼저 담고, 거의 같은 본문을 제외하며,
`retrieval.token_budget`(기본 2500)으로 본문 토큰 합을 제한합니다. 첫 청크는 예산을 넘어도 유지합니다.

### 전체 사업의 수량 조건 검색

Quantity conditions targeting projects (`사업`), without an agency or document-name prefix, filter the whole collection using indexed per-document values. Thresholds, ranges and max/min are supported, retaining ties. Examples: `사업 예산 1억원 이상인 사업들과, 그 사업들의 개요를 알려줘.`, `사업기간 6개월 이상인 사업`, `예산이 1억~5억인 사업`, `예산이 가장 큰 사업`. Numeric comparisons targeting requirements or vendor qualifications use the existing hybrid search; mentioning a project in the field name alone does not select the project filter. Routing uses the stored rewrite, or the original question when it is empty.

The scope modifier `전체` is supported before the project target: `예산 1억원 이상인 전체 사업` has the same filter and default overview context as its unmodified form. The same modifier before requirements or vendors keeps hybrid retrieval, including questions mentioning a project later. This bounded rule does not interpret arbitrary restrictive modifiers.

`이내`와 단독 `까지`는 `이하`와 같은 포함 상한입니다. `사업기간 6개월 이내인 사업`과 `사업기간 6개월까지인 사업`은 6개월을 포함하여 오름차순으로 모든 일치 사업을 반환합니다. `부터…까지`는 기존의 양 끝값 포함 범위를 유지합니다.

수량 추출을 바꾸면 02에서 색인을 다시 만드세요. `artifacts/index/quantities.jsonl`은 수량마다 문서·청크·값·단위·정리한 항목명·원문 범위를 저장합니다. 서로 다른 항목명은 기존 로컬 Embedder로 한 번씩 임베딩합니다. 띄어 쓴 항목명과 표 머리글을 복원하고, 단위는 Kiwi 품사로 읽습니다. 한글 금액, 앞쪽 통화 기호, 확인된 단위 중복 오타는 로컬에서 정규화합니다. 색인·라우팅·필터에 LLM이나 API 호출을 추가하지 않습니다.

Comparison expressions remain marked as bounds. Explicit labelled quantity ceilings, such as `사업예산: 230,000천원 이내` and `사업기간: 계약일로부터 24개월 이내`, can supply the document value; eligibility clauses, examples and explicit reference blocks cannot. Estimated prices (`추정가격`) remain excluded. Won values of 1 or less are unstated; valid one-month and one-item quantities remain usable. Parenthesized currency scales declare units, and counter-only labels such as `건당` cannot supply a budget field. Table-cell subjects take precedence over generic headers, and artificial project context is added only to monetary labels so unrelated periods retain their actual subjects.

Declared column units and a preceding `(단위: 천원)` apply to numeric table cells: `사업예산(천원) | 부문` followed by `10 | 운영` yields 10,000 won. The metadata preserves both the numeric cell and its unit declaration spans; the context displays `10 (천원)`. Explicit cell units take precedence, and inherited units end with the table or chunk. Component row labels remain distinct from a shortened total row. Slash-separated parallel fields such as `과업비/과업기간: 100,000천원/5개월` assign each value to its corresponding field; unit-internal slashes such as `MB/s` remain intact.

Optional boundary pipes, exterior whitespace and LF/CRLF endings do not add table columns. Interior empty cells retain their positions. A shortened total still uses the existing unique-declared-column recovery; this does not infer arbitrary merged cells or prefer totals over fields with higher similarity.

Missing or textual data values leave the active column labels and units intact. A table schema starts with a label-only row, changes on another label-only unit declaration, and resets at the existing non-pipe table boundary or chunk end. Numeric key/value rows remain data. Adjacent unmarked header changes in delimiter-free text remain ambiguous; they require a declaration or a supported boundary.

선언 단위 머리글에는 `1차 예산(천원)`이나 `2026년 1차 예산(천원)`처럼 숫자 수식어가 있어도 됩니다. 수식어 뒤의 항목명과 끝의 단위 선언을 확인하여 열 단위를 설치하며, 머리글의 차수·연도는 데이터 수량으로 내보내지 않습니다. 숫자 셀, 명시 단위 값, 괄호 약어가 섞인 본문은 데이터로 유지합니다.

A Markdown delimiter row also identifies a declared-unit header as a whole. For example, `구분 | 2024년 | 예산(천원)` above `--- | --- | ---` installs the budget column's thousand-won scale even though the year occupies a separate cell. Header numbers are not emitted as data. Without that structural marker, the existing cell-level checks remain in force; a numbered data row cannot install a sibling declaration merely because it contains parentheses.

Each delimiter cell must contain at least three hyphens, optionally surrounded by alignment colons. Single-hyphen missing-value rows and other shorter cells cannot install column units or suppress quantities in the preceding data row.

02 builds FAISS, BM25 tokens, quantity rows, phrase names and phrase vectors in a private sibling directory. It publishes the completed directory only after quantity embedding and summary calculation succeed, restoring the previous directory if the publication rename raises. This rollback covers the five index artifacts; preprocessing chunk files are unchanged. It is not a concurrent-reader or process-crash transaction.

Filtered hit metadata, candidate IDs and `context_chunk_ids` identify the selected value's source chunk. When the overview comes from another chunk, its filename, page or section, and chunk ID appear beside that excerpt in the body. Each project still contributes one hit with the existing schema; the overview's ID is recorded in that body rather than added to `context_chunk_ids`.

| 설정 | 의미 |
| --- | --- |
| `retrieval.field_similarity` | 질문 항목명과 색인 항목명의 최소 코사인 유사도. 필요한 단위의 사용 가능한 행 중 유사도가 가장 높은 행을 문서 값으로 선택합니다. |
| `retrieval.filter_token_budget` | 일치한 전체 문서의 본문 토큰 예산. 문서마다 균등하게 나누고 선택한 값의 원문과 실제 본문 발췌를 담습니다. |

항목명 정리와 사업 문맥 보정 후 측정한 기준값은 0.66입니다. `과업비`는 약 .668, `집행한도액`은 .710, `보상한도액`은 .650이며 추정가격은 별도 정책으로 제외합니다. 숫자 없는 최대·최소와 단위 없는 배율 범위는 문서별로 가장 잘 맞는 사용 가능한 행 하나씩을 뽑아 가장 흔한 단위를 추론합니다. 같은 문서의 서식이 반복되어도 단위 집계를 늘리지 않습니다.

Overview/default requests prefer substantive introduction, purpose and main-work excerpts, including a value-source chunk when it contains an introduction. Headings, TOCs and blank forms are skipped. Missing content is explicit. Context reports matching documents and `값 미표기·매칭 불가로 제외` counts separately from known values below the threshold. Values without an accepted matching field can still be omitted, and conflicting values within one document are not semantically reconciled. The 02 local-check cell prints values, fields and similarities without API calls. The [paid validation report](docs/quantity_filter_validation.md) records defects found in real answers and subsequent local corrections; it does not claim acceptance from table formatting alone.

답변 모델은 승인된 출력 한도 8,192토큰에 추론을 포함합니다. 제공된 모든 사업을 원문 값·개요·출처가 있는 표로 나열합니다. [전체 견적서](docs/quantity_filter_estimate.md)에 모델 비교, 유료 검증 및 한계를 기록합니다.
노트북은 VS Code · PyCharm · Jupyter 에서 `.venv` 커널로 **01 → 05 순서대로** 실행합니다.
처음 실행할 때 임베딩 모델 KURE-v1(약 2.3GB)을 내려받습니다.

## v11 전처리 패키지 사용

v11 전처리 패키지와 이 폴더의 연동 아이디어 출처는 Se hui Hwang
([@hwangsiiii](https://github.com/hwangsiiii))입니다. 전처리 담당자의
[PR #12](https://github.com/LittleBitAI/rfg_rag/pull/12)와 별도로 전달받은
`RFP_Preprocessing_Final_v11_Team`, `RFP_v11_Retriever_Compatibility`,
`v11_retriever_연동테스트.ipynb`를 이번 통합의 출처로 명시합니다.
이 저장소의 로더·노트북 입력 전환 구현과 ⑤ 비교 실험은
[PR #18](https://github.com/LittleBitAI/rfg_rag/pull/18)에서 수행한 통합 작업입니다.

담당자가 만든 저장 청크와 이미 검증된 OCR 텍스트를 재파싱·재청킹 없이 검색에 사용하는
아이디어를 실제 파이프라인에 가져왔습니다. 01의 `load_v11_package` → `save_chunks`가
`docs.jsonl`과 `chunks.jsonl`을 만들고, 이를 02 색인·검색 → 04 답변 생성 → 05 네 평가가 읽습니다.
NVIDIA L4 VM에서 이 경로를 실제 실행해 문서 98개·청크 18,984개로 고정 질문 16개를 평가했습니다.
현재 파서와의 네 CSV 전체 지표·비용·지연 시간 비교는 PR #18에 있습니다.

전달 폴더 전체의 기능을 가져온 것은 아닙니다. 반영 범위는 다음과 같습니다.

| 전달 자료·아이디어 | 이 저장소에 반영한 범위 |
| --- | --- |
| v11의 `final_chunks.jsonl` | `load_v11_package` 경로에서는 기존 청크 ID, `payload` → 검색용 `text`, `body` → 답변 근거, 섹션을 유지합니다. 현재 파서 경로의 청크 ID는 새로 만들어지므로 골든의 v11 ID를 그대로 쓸 수 없습니다. 본문 종류 `prose`는 저장소의 `text`로 바꾸고 다른 종류는 유지합니다. `[IMAGE]` 표시뿐인 8개 청크는 제외합니다. |
| `final_elements.jsonl`, `final_records.jsonl` | 문서 소속·NFC 파일명·제목·있는 쪽 번호·첫 레코드와 앞 세 레코드의 텍스트를 연결합니다. |
| 호환 패키지의 `adapt_v11.py` | `payload/body` 분리와 문서 메타데이터 연결 아이디어를 저장소의 작은 표준 라이브러리 로더로 구현했습니다. 어댑터 코드·전체 출력 파일은 복사하지 않았습니다. |
| 저장된 검증 OCR | 최종 청크에 들어 있는 검색 본문을 사용합니다. OCR 엔진과 미검증 OCR sidecar는 실행하거나 추가하지 않습니다. 패키지의 전체 정확성을 인증한 것은 아닙니다. |
| 구조·상세 출처 메타데이터 | `table_refs`, 표 셀 구조, `spans`, `linked`, `requirement_key`, `image_source`, 이미지 SHA·검증 영역 등은 현재 출력과 생성 문맥에 전달하지 않습니다. 원래 패키지에 남아 있습니다. |
| Elements 인덱싱 대안 | 도입하지 않았습니다. Chunks만 색인하며 두 입력을 섞지 않습니다. |
| 호환 패키지의 검색 코드·E5 샘플 색인·연동 테스트 노트북 | 참고 자료입니다. 기관 CSV 라우팅 등 별도 검색 로직은 가져오지 않았고, 이 저장소의 KURE 검색 코드로 새 색인을 만들었습니다. |
| 패키지 사용·OCR 검증 노트북과 검증 영수증 | 출처 자료로 보관합니다. 이 저장소의 노트북에 복제하거나 패키지의 보존·OCR 검증을 다시 실행하지 않았습니다. |

따라서 이번 작업은 담당자의 전처리 결과와 청크 연결 아이디어를 실행 가능한 기존 파이프라인으로
통합한 것이며, 전달 폴더 전체 기능이나 상세 이미지·표 출처 전달까지 완료했다는 뜻은 아닙니다.

### 입력 전환 방법

전처리 담당자에게 `RFP_Preprocessing_Final_v11_Team` 패키지를 받아 압축을 풉니다.
`final_chunks.jsonl`, `final_elements.jsonl`, `final_records.jsonl`이 바로 들어 있는 폴더를
`data/RFP_Preprocessing_Final_v11_Team/`에 둡니다. 압축에 같은 이름의 폴더가 두 겹 있으면 안쪽 폴더를 사용하세요.
패키지와 실행 결과(`data/`, `artifacts/`)는 git에 포함되지 않으므로 팀원과 VM에 별도로 전달해야 합니다.

`01_preprocessing.ipynb` 설정 셀에서 입력을 선택합니다.
기본값은 `data/rfp.zip`을 현재 파서로 처리합니다.

```python
PREPROCESSED = None
```

v11을 쓰려면 위 값을 다음 경로로 변경합니다.

```python
PREPROCESSED = "data/RFP_Preprocessing_Final_v11_Team"
```

01을 처음부터 실행하면 v11의 저장된 OCR 텍스트와 청크를 읽어
`artifacts/docs.jsonl`, `artifacts/chunks.jsonl`로 저장합니다. 파싱·OCR·청크 재분할은 하지 않습니다.
본문이 `[IMAGE]` 표시뿐인 청크는 제외하고, 패키지에 쪽 번호가 없는 HWP는 `page = None`을 유지합니다.
이후 02부터 다시 실행해 새 입력의 색인을 만드세요. 임베딩의 `max_seq_length` 기본값은 2048입니다.

현재 파서와 v11을 비교할 때는 03을 한 번 실행해 골든 dev 분할(`eval/golden/dev.jsonl`)과 `eval/eval_questions.yaml`로
만든 `eval_set.jsonl`의 질문을 두 입력에 똑같이 씁니다. 문서·청크 라벨은 입력에 종속되므로 입력을 바꾼 뒤 03을 다시 실행합니다. 골든 test 분할(`eval/golden/test.jsonl`)은 라벨 품질만 보고하며 검색·생성 비교에 쓰지 않습니다.
두 입력에 같은 질문 파일과 02 설정을 사용하고, 각각 02 → 04 → 05를 실행해 네 평가 CSV를 별도 보관합니다.

## 팀 VM `codeit` 에서 작업 (VS Code Remote-SSH, GPU NVIDIA L4)
코드는 그대로이고, VS Code 가 VM 에 접속해 VM 의 GPU 로 실행합니다. 임베딩은 GPU 가 있으면 알아서 `cuda` 를 씁니다.

1. 내 PC 의 `~/.ssh/config` 에 항목을 넣습니다 (`User` 는 본인 VM 계정, 키는 `gcloud compute ssh` 가 만든 것).
   ```
   Host codeit
       HostName 35.255.64.243
       User spai13xx
       IdentityFile ~/.ssh/google_compute_engine
       IdentitiesOnly yes
       ServerAliveInterval 30
   ```
2. VS Code 에서 `Remote-SSH: Connect to Host...` → `codeit` 을 고르고, 처음 한 번 VM 터미널에서 설치합니다.
   ```bash
   git clone https://github.com/LittleBitAI/rfg_rag ~/rfg_rag && cd ~/rfg_rag
   python3.10 -m venv .venv
   .venv/bin/python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
   .venv/bin/python -m pip install -r requirements.txt
   .venv/bin/python -c "import torch; print(torch.cuda.is_available())"   # True
   ```
3. `.env` 와 `data/` 는 git 에 없으므로 내 PC 에서 **한 번** 복사합니다. VM 은 여럿이 같이 쓰므로 `.env` 는 본인만 읽게 합니다.
   ```bash
   scp .env codeit:rfg_rag/.env
   scp -r data codeit:rfg_rag/
   ssh codeit chmod 600 rfg_rag/.env
   ```
4. VS Code 에서 폴더 `~/rfg_rag` 를 열고 노트북 커널로 `.venv` 를 고릅니다.

`artifacts/` 는 복사하지 않습니다. 기기마다 그 기기에서 돌린 노트북 결과가 쌓입니다 (내 PC 와 VM 의 결과는 따로).

## 파이프라인 · 담당

| 파이프라인 | 노트북 | 파일 | 다음 파이프라인에 넘기는 것 |
|---|---|---|---|
| ① 전처리 | `01_preprocessing.ipynb` | `rag/preprocessing/parsing.py` (PDF · HWP/HWPX 파싱 · 정제 · OCR), `rag/preprocessing/chunking.py` (청크 분할) | `artifacts/chunks.jsonl`, `artifacts/docs.jsonl` |
| ② 검색 | `02_retrieval.ipynb` | `rag/retrieval/indexing.py` (임베딩 · FAISS · BM25 색인), `rag/retrieval/rewrite.py` (질문 재작성 · API 사용량), `rag/retrieval/retrieval.py` (하이브리드 검색 · 발주기관 라우팅) | `artifacts/index/` · `artifacts/retrieval_settings.jsonl` |
| ③ 검증 | `03_validation.ipynb` | `rag/validation/validation.py` (골든 dev 분할 · 평가 질문 읽기 · 평가 항목 점검) | `artifacts/eval_set.jsonl` |
| ④ 생성 | `04_generation.ipynb` | `rag/generation/generation.py` (검색 → 이전 대화를 참고해 답변 · 토큰 · 지연 시간) | `artifacts/answers.jsonl` |
| ⑤ 평가 | `05_evaluation.ipynb` | `rag/evaluation/evaluation.py` (네 가지 평가) | `artifacts/retrieval.csv` · `generation.csv` · `grounding.csv` · `end_to_end.csv` |
| ⑥ 질문 화면 | — | `frontend/server.py` (`answer_question` 을 감싸는 `POST /api/ask`), `frontend/web/` (React + Vite 화면), `frontend/start.cmd` · `frontend/start.command` (실행기); `frontend/ocr_select/` (OCR 이미지 라벨링 · OCR 결과 검토 화면) | 브라우저 화면의 답변 · 출처, `artifacts/ocr_labels/labels.jsonl` · `reviews.jsonl` |

공통: `rag/config.py` (`config.yaml` · `.env` 읽기, jsonl 읽기/쓰기), `config.yaml` (모든 설정 — 파이프라인별 구역).

01·02·04·05에는 직접 값을 조절하는 설정 셀이 있습니다. 변수의 초기값은 `config.yaml`에서 읽으므로, 바꾸려는 변수의 오른쪽을 원하는 값으로 바꾸세요.

| 노트북 | 설정 셀에서 조절하는 값 |
|---|---|
| 01 전처리 | `OCR`, `OCR_MODEL`, `OCR_REASONING_EFFORT`, `OCR_MAX_TOKENS`, `OCR_PRICES`, `CHUNK_SIZE` |
| 02 검색 | `REWRITE_MODEL`, `REWRITE_REASONING_EFFORT`, `REWRITE_MAX_TOKENS`, `REWRITE_PRICES`, `DENSE_WEIGHT` (BM25는 `1 - DENSE_WEIGHT`) |
| 04 생성 | `LLM_MODEL`, `LLM_REASONING_EFFORT`, `LLM_MAX_TOKENS`, `LLM_PRICES` |
| 05 평가 | `JUDGE_MODEL`, `JUDGE_REASONING_EFFORT`, `JUDGE_MAX_TOKENS`, `JUDGE_PRICES` |

예를 들어 02 설정 셀의 `DENSE_WEIGHT = cfg["retrieval"]["dense_weight"]`를 `DENSE_WEIGHT = 0.8`로 바꾸면 Dense 80%·BM25 20%로 검색합니다.
설정 셀은 메모리의 설정을 바꾸며 `config.yaml`을 덮어쓰지 않습니다. 02는 적용한 rewrite·검색 설정을 `artifacts/retrieval_settings.jsonl`에 저장하고 04가 읽습니다.
기존 색인을 재사용할 때도 02의 설정 셀을 실행해 이 파일을 만든 뒤 04를 실행하세요. 단, 토크나이저 지문이 없거나 현재 코드·사전·패키지와 다르면 검색 시 오류로 중단합니다. 이번 Kiwi 변경 전 색인은 재사용할 수 없으므로 02의 불러오기·설정 셀과 `1. 색인 만들기`의 `build_index` 셀을 실행한 뒤 04나 질문 화면을 실행하세요. 이 색인 재구축은 로컬 작업이며 유료 질문 재작성 예제 셀을 실행할 필요가 없습니다.
`bm25_tokens.json`은 토큰과 지문을 함께 저장합니다. 지문은 줄바꿈을 정규화한 `indexing.py` 전체 코드, 생성 사전, `kiwipiepy`·모델 데이터·`hanja` 버전을 포함합니다. 따라서 이 모듈의 토큰 규칙 외 변경도 보수적으로 재구축을 요구합니다. 청킹 크기를 바꾸면 01부터 다시 실행합니다. 검색 설정 조절은 저장 rewrite가 있는 dev에서 아래 검색 전용 재실행으로 비교할 수 있습니다. 새 설정의 답변·심판 결과가 필요하면 04도 다시 실행합니다.
모델을 바꾸면 같은 설정 셀의 `*_PRICES`도 해당 모델의 입력 · 캐시 입력 · 출력 단가(USD / 100만 토큰)로 맞추세요.
재작성·답변 기본값은 [GPT-6 LUNA Standard 단가](https://developers.openai.com/api/docs/models/gpt-6-luna)를 사용하며 평가 심판은 [gpt-5-mini 단가](https://developers.openai.com/api/docs/models/gpt-5-mini)를 유지합니다. 설정 단가는 비용 추정용으로 실제 청구와 다를 수 있습니다. [수량 필터 전체 견적과 네 질문 비교](docs/quantity_filter_estimate.md)에 범위·실사용량·모델 선택의 한계를 기록합니다.

02 검색 예제와 04 답변 생성은 검색 전에 `rag/retrieval/rewrite.py`로 질문을 재작성합니다.
`config.yaml`의 `rewrite.model`, `rewrite.max_tokens`, `rewrite.reasoning_effort`가 이 API 호출에 적용됩니다.
검색과 기관 라우팅에는 재작성한 질문을 쓰고, 답변 생성·평가에는 원본 질문을 씁니다. 재작성 출력이 비면 원본 질문으로 검색합니다.
04는 평가셋 순서대로 답하며 직전 질문·답변 최대 10개를 다음 질문의 재작성 요청과 답변 생성 요청에 함께 전달합니다. 이전 대화는 질문 이해에만 사용하고 사실의 근거는 현재 검색한 문서로 제한합니다.
질문마다 재작성 API 호출 비용이 추가되며, 04의 `answers.jsonl`에는 검색용 질문·모델·토큰·비용·지연 시간을 `rewrite` 필드에 별도로 저장합니다.
답변 생성도 실제 응답 모델·캐시 입력 토큰·비용을 저장합니다. 05는 저장된 비용을 사용하므로 평가 시 설정을 바꿔도 이전 생성 비용이 바뀌지 않습니다.
`latency_s`는 재작성·검색·답변 생성 전체 시간입니다. `end_to_end.csv`의 `cost_usd`는 rewrite + 답변 생성 비용이며 `rewrite_cost_usd`, `answer_cost_usd`로 구분됩니다. OCR과 평가 비용은 별도로 집계합니다.
04는 `ranked_candidates`에 패킹 전 후보의 `chunk_id`, `doc_id`, `fused_rank`, `dense_score`, `dense_rank`, `bm25_score`, `bm25_rank`, `exact_code_match`를 저장합니다. 순위는 1부터 시작하며 해당 성분의 후보가 아니면 점수·순위는 null입니다. `context_chunk_ids`는 실제 LLM에 보낸 청크 ID입니다. `retrieval_settings`는 `dense_weight`, `candidate_k`, `token_budget`, 활성 `chunk_file`, `k_values`(5,10,20), `stored_rewrites_reused`를 기록합니다.
04는 라벨 필드가 없는 옛 eval_set을, 05의 네 함수는 새 검색 기록·rewrite 등이 없는 옛 answers를 유료 호출 전에 거부합니다. 빠진 필드를 확인하고 03 → 02 설정 셀 → 04 → 05를 실행하세요. `search()`의 반환값은 유지하며, `search_with_candidates()`는 같은 검색 결과와 읽기 전용 후보 스냅샷을 함께 반환합니다.

## 질문 화면 — 브라우저에서 묻고 답 받기
채팅 화면입니다. 내 질문은 오른쪽 말풍선, 답변은 왼쪽 `문서 도우미` 아래에 나옵니다.
질문하면 04 와 같은 방식(재작성 → 하이브리드 검색 → 답변)으로 답하고, 답변 안에 `[n]` 번호를, 답변 옆 출처 칸에 출처 카드(파일 · 쪽)를 보여 줍니다.
번호나 카드를 누르면 출처 칸에 그 청크 본문이 열립니다. 창 폭이 1024px 보다 좁으면 출처 카드는 답변 위에 나옵니다. 이어서 질문하면 이 탭의 직전 질문 · 답변 최대 10개를 함께 보냅니다.
대화는 열린 탭에만 있고, `새 스레드` 를 누르거나 탭을 닫으면 사라집니다. 서버는 대화를 저장하지 않습니다.
이전 대화는 질문 재작성과 답변 생성이 함께 참고합니다. 예를 들어 고려대학교 사업을 물은 뒤 "그 사업 예산은?" 이라고 물으면, 재작성이 이전 대화에서 기관 · 사업명을 채워 넣고 그 재작성 질문으로 기관을 골라 고려대학교 문서에서 검색합니다.

준비물
- 위 설치대로 만든 `.venv` (`requirements.txt` 에 `fastapi` · `uvicorn` 포함)와 `.env` 의 `OPENAI_API_KEY`
- 01 · 02 를 실행해 만든 `artifacts/chunks.jsonl` · `docs.jsonl` · `index/` · `retrieval_settings.jsonl` — 04 와 같은 설정(`config.yaml` + 02 설정 셀)으로 답합니다
- [Node.js](https://nodejs.org/) LTS
- macOS: `.venv` 를 만들 때 cu128 빌드 대신 일반 torch 를 설치합니다.
  ```bash
  python3.10 -m venv .venv
  .venv/bin/python -m pip install torch
  .venv/bin/python -m pip install -r requirements.txt
  ```

실행
- Windows: 탐색기에서 `frontend\start.cmd` 를 더블클릭합니다. 창 하나에서 API 서버(포트 8765), OCR 이미지 라벨링 화면의 API 서버(8766), Vite 개발 서버(5173)가 함께 돌고(먼저 `npm install` — 처음 한 번만 오래 걸림), 기본 브라우저로 화면을 엽니다. 화면을 쓰는 동안 이 창을 닫지 마세요. 창을 닫으면 모두 꺼집니다.
- macOS: Finder 에서 `frontend/start.command` 를 더블클릭합니다. 터미널 창 하나에서 둘 다 돌고, 창을 닫으면 API 서버도 꺼집니다.
- 직접 실행 — 저장소 최상위에서 터미널 두 개:
  ```bash
  .venv\Scripts\python -m uvicorn frontend.server:app --port 8765   # macOS: .venv/bin/python
  cd frontend/web && npm install && npm run dev                      # http://localhost:5173
  ```

API 서버는 켤 때 색인과 KURE-v1 을 읽느라 수십 초 걸립니다. API 창에 `Application startup complete` 가 뜬 뒤에 물어보세요.
포트를 바꾸려면 `frontend/start.cmd` · `frontend/start.command` 의 8765 와 `frontend/web/vite.config.js` 의 프록시 주소를 함께 바꿉니다.

화면에서 묻는 질문도 OpenAI API 를 부르므로 `artifacts/api_usage.csv` 에 `rewrite` · `answer` 행이 추가됩니다.
04 노트북의 행과 구분하는 열이 없어 `timestamp` 로만 가릴 수 있고, 노트북의 누적 사용량 표에 함께 잡힙니다. 평가 점수 CSV 에는 영향이 없습니다.

## OCR 이미지 라벨링 화면
RFP 문서에서 꺼낸 그림마다 OCR 이 필요한지 사람이 매기는 화면입니다. 카드 하나가 그림이 나온 위치 하나입니다. 같은 그림(반복 로고 등)도 나온 곳마다 카드가 따로 있고 따로 매깁니다.
라벨은 `1` 꼭 인식해야 함 · `2` 인식해야 하나 어려움 · `3` 인식할 필요 없음 셋이고, 누르는 즉시 저장됩니다. 화면을 다시 열면 매긴 라벨이 그대로 보입니다.
WMF · EMF 처럼 미리보기를 만들 수 없는 그림도 자리표시 카드(형식 · 문서 이름 · 위치)로 나오고 라벨을 매길 수 있습니다.
`artifacts/ocr_selection.jsonl`(CRAFT 선별 기록)이 있으면 카드에 CRAFT 분류를 함께 보여 줍니다. 없어도 화면은 그대로 동작합니다.
그림을 누르면 크게 보고(바깥 · Esc 로 닫기, ◀ ▶ · ← → 로 넘기기), `원본 보기` 를 누르면 문서 속 자리를 봅니다. PDF 는 새 탭에서 그 쪽으로 열리고, 쪽 번호가 없는 HWP 는 그림 앞뒤 본문을 보여 줍니다.
라벨은 위치별로 기록합니다. OCR 벤치마크는 합친 라벨의 1·2 위치를 사용하며, 01은 벤치마크가 저장한 전사 결과를 읽습니다.

실행 — 저장소 최상위에서
1. 그림 꺼내기: `.venv\Scripts\python -m frontend.ocr_select.extract` (macOS: `.venv/bin/python`). `config.yaml` 의 `paths.input`(기본 `data/rfp.zip`)을 01 과 같은 함수로 읽습니다. 문서 100개에 1분 남짓 걸립니다.
2. 화면 열기: 질문 화면과 같은 실행기(`frontend\start.cmd` · `frontend/start.command`)를 더블클릭하고, 첫 화면 오른쪽 위 `설정` → `OCR 이미지 라벨링` 을 누릅니다 (`http://localhost:5173/ocr.html`). 실행기가 라벨링 화면의 API 서버(포트 8766)도 함께 띄웁니다.
3. 묶음 고르기: 상단 바에서 맡은 `묶음 1` ~ `묶음 5` 를 누릅니다. 카드를 문서 이름 · 문서 안 위치 순서로 세워 다섯으로 고르게 자른 것이라(209 · 209 · 209 · 209 · 208곳), 같은 `data/rfp.zip` 으로 extract 했다면 누구 컴퓨터에서나 같은 묶음입니다. 고른 묶음은 주소(`?batch=2`)에 남아 새로고침해도 그대로입니다.
4. 결과 내보내기: 다 매기면 상단 바의 `결과 내보내기` 를 눌러 `ocr_labels_batchN.jsonl` 을 내려받고, 합치는 사람에게 보냅니다. 저장 중인 라벨이 있으면 저장이 끝날 때까지 이 버튼이 잠기고, 진행 수는 저장을 마친 라벨만 셉니다.
5. 합치기 (한 사람): 받은 파일을 모두 넘겨 `.venv\Scripts\python -m frontend.ocr_select.merge ocr_labels_batch1.jsonl ocr_labels_batch2.jsonl ...` 를 실행합니다. 묶음마다 매긴 수와 빠진 위치 수를 출력하고 `artifacts/ocr_labels/merged_labels.jsonl` 에 씁니다. 같은 위치를 두 사람이 매겼으면 `labelled_at` 이 늦은 라벨이 남습니다.

결과 — `artifacts/ocr_labels/`
- `images/<그림 해시>.<확장자>`: 꺼낸 그림. 같은 바이트의 그림은 파일 하나입니다. extract 를 다시 실행하면 이 폴더만 새로 만듭니다.
- `images.jsonl`: 서로 다른 그림 한 줄씩 — `image_sha256`, `file`, `viewable`, `reason`, `occurrences`(위치마다 `doc_id` · `source` · `document_sha256` · `format`, HWP 는 `image_name` · `marker_start` · `repeated_occurrences`, PDF 는 `page` · `image_index` · `xref` · `bbox_points` — CRAFT 기록과 같은 이름). 문서에 들어 있지만 본문에 `[IMAGE]` 표시가 없는 HWP 그림(쪽에 놓이지 않은 그림 등)은 `marker_start` 가 `null` 이고, 저장 OCR 결과가 있으면 01은 문서 끝에 설명을 넣습니다. CRAFT 선별 경로는 이 그림을 보지 않습니다.
- `labels.jsonl`: 라벨을 누를 때마다 `{image_sha256, label, labelled_at, occurrences}` 한 줄을 덧붙입니다. `occurrences` 에는 매긴 위치 하나가 들어갑니다. 다시 매긴 라벨도 새 줄이고, 위치마다 마지막 줄이 지금 라벨입니다. extract 를 다시 실행해도 지우지 않습니다.
- `merged_labels.jsonl`: 합친 결과. 매긴 위치마다 한 줄 — `labels.jsonl` 과 같은 모양에 `batch`(묶음 번호)가 더해집니다. 내려받는 `ocr_labels_batchN.jsonl` 도 같은 모양입니다.

## OCR 결과 검토 화면

기존 실행기(`frontend\start.cmd` · `frontend/start.command`)를 열고 질문 화면의 `설정` → `OCR 결과 검토`로 들어갑니다 (`http://localhost:5173/review.html`).
`data/ocr_captions.jsonl`의 391개 위치를 그림 해시로 묶어 서로 다른 그림 320장을 한 장씩 검토합니다.
왼쪽에는 `artifacts/ocr_labels/images/`의 원본, 오른쪽에는 저장된 전사를 Markdown 표 · 제목 · 목록으로 표시합니다.
엔진 · 이미지 유형과 모든 등장 위치(문서 이름, PDF 쪽 또는 HWP 그림 이름 · 표시 위치)를 함께 보여 줍니다.
문서 · 이미지 유형 · 엔진 · 판정 상태(미검토 포함)로 거르고, 이전/다음 버튼 또는 ← → 키로 이동합니다.

`OK` · `일부 틀림` · `틀림`을 누르면 `artifacts/ocr_labels/reviews.jsonl`에 `{image_sha256, transcription_sha256, verdict, reviewed_at}` 한 줄을 덧붙입니다.
`transcription_sha256`은 전사 본문 · 엔진 · 이미지 유형의 해시입니다. `verdict` 값은 `ok` · `partly_wrong` · `wrong`이며, 같은 그림과 현재 전사에 매긴 마지막 판정이 표시됩니다.
본문 · 엔진 · 이미지 유형이 바뀌면 미검토로 표시하고, 이전 결과를 띄운 화면에서 저장하면 새로고침 안내와 함께 거부합니다.
전사 해시가 없는 이전 판정은 파일에 보존하지만 미검토로 표시하므로 다시 검토해야 합니다. 새로고침해도 같은 전사에 저장한 판정은 유지됩니다.
전사는 읽기 전용이며 OCR · VLM · LLM을 호출하지 않습니다. 판정은 01 전처리나 청킹에 반영하지 않고 기존 라벨링 화면과 별도로 보관합니다.
서버는 기존 8766을 그대로 쓰므로 추가 실행 명령은 필요 없습니다.

## API 사용량 자동 기록

Langfuse 키 없이도 OCR·질문 재작성·답변 생성·Judge/RAGAS의 호출마다 `artifacts/api_usage.csv`에 한 행이 자동 추가됩니다.
01·02·04·05의 마지막 셀에서 단계·모델별 누적 호출 수, 입력·캐시 입력·출력·추론 토큰과 예상 비용을 확인합니다.

| `stage` | 기록 대상 | `subject` / `evaluation` |
|---|---|---|
| `ocr` | 이미지 분석 LLM 호출 | 원본 문서 파일명 |
| `rewrite` | 02 검색 예제와 04의 질문 재작성 | 원본 질문 |
| `answer` | 04 답변 생성 | 원본 질문 |
| `judge` | RAGAS 내부 심판 호출 | 평가 종류: grounding / end_to_end (이전 실행의 retrieval / generation 행은 역사 기록) |

Judge는 RAGAS가 사용하는 모델이므로 같은 요청을 두 비용으로 더하지 않습니다. RAGAS의 내부 재시도도 응답에 사용량이 있으면 기록합니다.
Judge 호출은 평가 종류 단위로 집계하며 개별 질문 ID와 연결하지 않습니다. 03의 평가 데이터셋 생성 API와 로컬 KURE 임베딩은 이 CSV의 대상이 아닙니다.
캐시 입력 토큰은 입력 토큰에, 추론 토큰은 출력 토큰에 이미 포함되어 있습니다. 비용 계산은 캐시 입력 단가를 따로 적용하고 추론 토큰을 이중 과금하지 않습니다.

`api_usage.csv`는 재실행할 때도 누적되며 평가 점수 CSV는 최신 결과로 덮어씁니다. 새 실험의 사용량만 보고 싶으면 실행 전에 기존 `api_usage.csv`를 다른 위치에 보관하세요.
API 응답을 받지 못한 요청은 소비 토큰을 확인할 수 없어 기록하지 않습니다. OCR을 끄면 새 OCR 호출이 없지만 이전 사용량은 표에 남습니다.
CSV는 UTF-8 without BOM입니다.

## 평가 — 하나의 답변 파일을 네 가지로

05 의 네 평가는 모두 04 가 만든 같은 `artifacts/answers.jsonl` 을 채점합니다. 표마다 질문별 점수와 맨 아래 `평균` 행이 나옵니다.
각 평가 함수가 답변 파일과 같은 폴더에 점수 CSV를 자동 저장하므로 노트북 밖에서 호출해도 저장됩니다.

| 평가 | 판단하는 것 | 지표 |
|---|---|---|
| Retrieval | 검색이 골든 문서·청크를 찾고 컨텍스트에 담았나 | 결정적 Recall@k · MRR@k · Evidence Coverage, `key_facts_in_context` 문자열 일치 |
| Generation | 답에 핵심 사실 문자열이 있나 | `key_facts_in_answer` 문자열 일치 |
| Grounding | 답이 검색한 청크 안에서만 나왔나 (환각) | RAGAS `faithfulness` |
| End-to-End | 최종 답이 정답과 맞나 · 얼마나 걸리고 들었나 | RAGAS `factual_correctness`, 질문당 `latency_s` · 입력/출력/추론 토큰 · 예상 비용 `cost_usd` |

- Retrieval과 Generation은 API 호출 없이 계산합니다. 두 `key_facts_*`는 공백·수치 표기를 정규화한 문자열 일치이며 의미적 정확성 판정이 아닙니다. 답할 수 없음 질문의 `key_facts_in_context`는 평균에서 빼고, 답변 문자열 일치는 거절 문장도 채점합니다.
- Retrieval 이 낮으면 검색 문제, Retrieval 은 높은데 Grounding 이 낮으면 환각, 둘 다 높은데 End-to-End 가 낮으면 정답 · 질문을 다시 볼 차례입니다.
- 유료 심판은 Grounding의 `faithfulness`와 End-to-End의 `factual_correctness`만 남습니다. 모델·프롬프트·채점 방식은 유지하며 `config.yaml`의 `evaluation` 설정을 사용합니다. 두 심판 셀을 실행할 때 OpenAI 비용이 듭니다.
- 프로젝트 책임자는 Langfuse Cloud 에서 질문마다 추적 하나(`answer-question` 안에 검색 `retrieve-context` · 생성 `generate-answer` — 모델 · 토큰 · 비용 포함)를 보고, 05 의 질문별 점수도 그 추적에 붙어 있습니다. 키가 없는 팀원은 노트북 표와 CSV 로 봅니다.

### IR 공식과 제외율

A. 순위 평가는 중복 제거·토큰 예산 패킹 전의 후보 목록을 사용합니다. k는 5, 10, 20입니다.

| 수준 | Recall@k | MRR@k |
| --- | --- | --- |
| 문서 | top-k 청크가 속한 골든 문서 집합 크기 / 전체 골든 문서 집합 크기 | 골든 문서의 청크가 처음 나온 청크 위치의 역수 |
| 청크 | top-k에 든 골든 청크 집합 크기 / 전체 골든 청크 집합 크기 | 골든 청크가 처음 나온 위치의 역수 |

MRR은 k 안에 적중이 없으면 0입니다. 문서 순위를 만들려고 청크를 먼저 문서별로 중복 제거하지 않습니다.
각 수준에서 fused, dense-only, BM25-only Recall@k와 exact-code membership Recall을 한 표로 봅니다.
성분별 순위는 원점수 순서이며 여러 기관이면 실제 검색처럼 기관별 목록을 번갈아 섞습니다. 가중치가 0인 성분은 후보를 내지 않습니다.
exact-code는 코드 일치 후보 집합 속 골든 문서/청크 비율이며 k나 MRR을 붙이지 않습니다.

B. 컨텍스트 평가는 `context_chunk_ids`를 사용합니다. Evidence Coverage는 실제 보낸 골든 청크 수 / 전체 골든 청크 수,
`full_evidence_coverage`는 모든 골든 청크를 보냈으면 1, 아니면 0입니다. 단일 근거와 다중 근거(`multi_hop`, `comparison` 또는 복수 근거 항목)를 별도로 보고합니다. MRR은 첫 근거의 위치를 볼 뿐 다중 근거의 완전성을 나타내지 않습니다.

청크 평가는 모든 근거 항목에 청크 라벨이 있는 질문만 계산합니다. 일부 라벨만 있는 질문의 분모를 줄여 채점하지 않습니다.
문서도 모든 근거가 문서에 연결된 질문만 계산합니다. 각 주제의 전체/일부/미라벨 질문 수와
mapping exclusion rate = (일부 + 미라벨) / 답할 수 있는 골든 질문 수를 `retrieval_exclusions.csv`에 저장합니다.
성분 표에도 채점 질문 수와 제외율을 표시합니다. `unanswerable`과 골든 근거 없는 YAML은 IR에서 제외하고 각각 셉니다.
`retrieval.csv`는 질문별 IR 지표·Evidence Coverage·`key_facts_in_context`·검색 설정을,
`generation.csv`는 `key_facts_in_answer`를 담습니다. `grounding.csv`와 `end_to_end.csv`의 열은 유지합니다.

### dev 검색 전용 재실행

저장된 rewrite가 있는 dev 답변 파일에서 검색 설정만 바꿀 때 사용합니다. 재작성·답변 생성·심판 API를 호출하지 않습니다.
새 폴더의 answers는 05 Retrieval이 원본과 동일하게 읽으며 실제 사용한 청크 파일·검색 설정·k·rewrite 재사용 여부(True)를 기록합니다.
기존 답변은 재생성하지 않으므로 이 파일의 Generation·Grounding·End-to-End를 새 설정의 생성 성능으로 해석하지 마세요.
원래 Langfuse 추적에 실험 점수가 덮이지 않도록 새 행의 trace_id는 비웁니다.

```python
from rag.config import ARTIFACTS, load_config
from rag.retrieval.retrieval import HybridIndex
from rag.evaluation.evaluation import rerun_retrieval, evaluate_retrieval
from rag.evaluation.ir import component_table, coverage_table

cfg = load_config()
cfg["retrieval"].update(dense_weight=0.5, candidate_k=50, token_budget=2500)
path = ARTIFACTS / "dev_rerun" / "answers.jsonl"
rerun_retrieval(ARTIFACTS / "answers.jsonl", path, HybridIndex(ARTIFACTS, cfg))
scores = evaluate_retrieval(path, cfg)
display(component_table(scores, "doc"))
display(component_table(scores, "chunk"))
display(coverage_table(scores))
```

유료 확인은 모든 주제를 포함한 dev 30문항으로 제한합니다. 실행 전에 config 단가로 04 rewrite+answer와 05 두 심판의 견적을 표시하고 승인을 받은 뒤 실행합니다. 실제 비용은 해당 실행의 `api_usage.csv`로 계산합니다. 이전 per-evaluation 행의 질문당 심판 비용은 historical로 표시하며, 새 30문항과 질문·시점이 다르므로 동일 질문의 품질 비교로 해석하지 않습니다.

[30문항 표본 보고서](docs/eval_ir_sample.md)에 표본 구성·라벨 제외율·비용 견적·historical 기준과 실제 실행 결과를 기록합니다.
보고서의 유료 표본은 dev `ab49a65`의 대화 기반 재작성·재작성 query 라우팅 통합 전 기록입니다. 통합 후 검색 보존 검사는 별도 절에 기록했으며, 추가 유료 평가를 실행한 결과가 아닙니다.

### 최종 test 평가 — 설정을 고정한 뒤 한 번

dev는 검색·생성 설정 조절용입니다. test 검색·생성 결과를 보고 설정을 조절하지 않습니다. 이 변경 작업에서는 test를 실행하지 않습니다.
최종 설정과 활성 chunks/index를 고정하고, 03의 첫 import·입력 경로 셀을 실행한 뒤 다음 코드로 test 전용 평가셋을 만듭니다.
근거 연결 규칙은 dev와 동일하며 원본 골든 파일을 바꾸지 않습니다.

```python
test_items = load_eval_items(["eval/golden/test.jsonl"])
test_labelled = label_evidence(test_items, chunks, raw_dir, package_dir, input_path)
test_eval_set, test_report = check_eval_items(test_labelled)
write_jsonl(test_eval_set, ARTIFACTS / "test_eval_set.jsonl")
```

04의 `eval_set` 입력을 `test_eval_set.jsonl`, 답변 출력을 `artifacts/test/answers.jsonl`로 바꿉니다.
고정한 02 설정으로 04를 한 번 실행하고, 05의 `ANSWERS`를 그 test 파일로 지정해 네 평가를 한 번 실행합니다.
네 CSV와 제외율·사용량을 최종 결과로 보관합니다. test를 dev 검색 전용 재실행 셀에 넣지 않습니다.

### 평가 데이터셋 (03 검증)
- `eval/golden/dev.jsonl`: `golden_pipeline` 분할 `final6` 의 dev 분할(30개 문서 408문항). `final2` 의 다섯 주제 396문항을 그대로 두고, 질문이 묻는 문서가 dev 에 있는 새 두 유형 12문항을 더했습니다 — 답할 수 없음(`unanswerable` 8문항: 다른 사업 문서의 속성을 묻고 정답은 `제공된 문서에서 확인할 수 없습니다.`. 검증기가 묻는 문서 전체를 표는 머리글과 함께 읽고도 답하지 못한 질문만 남김)과 틀린 전제(`false_premise` 4문항: 질문의 금액 · 기간 · 개수 · 날짜가 문서와 다르고 정답이 문서의 값으로 바로잡음). 정답은 `answer`, 핵심 사실은 주제별로 뽑습니다 — 수치형은 값+단위(`180일`), 비교형은 고른 쪽(`MAR-006`), 조건형은 조건 문장, 답할 수 없음은 `확인할 수 없`, 틀린 전제는 문서의 값+단위(`12개월`), 표형은 정답 칸(` | ` 로 나뉜 칸은 각각), 다중 근거형은 정답이 언급한 근거 표 칸 값과 칸 속 글머리 항목(◦ · - · o 로 나뉜 줄)(근거 단위마다 따로 찾힘. 문서 3개 이상에서 행 첫 칸으로 되풀이되는 `요구사항 분류` 같은 항목 이름은 빼고, 맨 수는 정답의 단위도 받음 — `47|47개`). 표 칸 값이 없거나, 정답을 바꿔 말해 사실이 정답의 60% 를 못 덮거나, 묻는 항목의 값이 질문에도 다른 뜻으로 나와 질문이 준 값인지 가를 수 없는(분류 '기능' 과 질문의 '지도기반 기능') 다중 근거 24문항은 핵심 사실 없음으로 빠져 384문항이 남습니다.
- `eval/golden/test.jsonl`: 같은 분할의 test 분할(68개 문서 943문항: `final2` 930문항 + 답할 수 없음 8 · 틀린 전제 5). 03은 검색·생성 없이 근거 라벨 품질만 보고하며 평가셋에는 넣지 않습니다. 설정 선택에 test 검색·생성 결과를 쓰지 않습니다. `manifest.json` 은 두 분할의 개수 · 해시입니다.
- `eval/eval_questions.yaml`: 직접 만든 RFP 질문(멀티턴 대화 포함). 핵심 사실은 `must_include` (`'A|B'` = 둘 중 하나).
- 질문 없음 · 중복 질문 · 대화의 후속 질문 · 정답 없음 · 핵심 사실 없음은 사유와 함께 제외합니다.
- `eval/golden/` 은 `golden_pipeline/outputs/splits/final6/` 를 그대로 복사한 것입니다(`outputs/` 는 커밋되지 않음). 새 릴리스로 바꿀 때는 다시 복사합니다.

### 골든 문서·청크 라벨 연결 (03)

03에는 현재 `artifacts/chunks.jsonl`과
`data/RFP_Preprocessing_Final_v11_Team/final_elements.jsonl`이 필요합니다.
파서 출력은 `config.yaml`의 `paths.input`이 폴더·단일 파일이면 원본을 그 자리에서 읽고,
ZIP이면 현재 아카이브의 항목만 열거해 01이 `artifacts/raw/`에 푼 정확한 위치를 찾고,
추출 파일의 SHA-256이 해당 아카이브 항목의 SHA-256과 같을 때만 사용합니다. 중첩 ZIP과 폴더 안 ZIP에도 같은 규칙을 적용합니다.
이전 실행의 다른 raw 하위 폴더는 검색하지 않습니다. 추출 파일이 현재 아카이브 본문과 다르거나,
현재 입력의 서로 다른 SHA 둘 이상이 같은 `source` 이름을 가지면 문서 신원을 확정할 수 없어 `doc_unmapped`로 남깁니다.
골든 `doc_sha`를 원본 파일의 SHA-256과 맞추고 NFC 파일명으로 현재 청크의 `source/doc_id`를 찾습니다.
v11 출력은 요소 메타데이터의 원본 `sha256`·`doc_id`가 현재 청크의 `doc_id`와 같고 NFC `source`도 같을 때 연결합니다.
따라서 v11에는 원본 파일이나 `artifacts/raw/`가 필요하지 않습니다. 같은 파일명만으로 파서 출력에 v11의 SHA를 적용하지 않으며,
문서 제목이나 골든 청크 ID로 추측하지 않습니다. 입력을 바꾸면 01과 03에서 같은 원본 경로를 사용하세요.

`evidence`는 선택한 근거만, `context`는 선택하지 않은 블록까지 담습니다.
현재 dev는 근거 716항목과 `[E]` 1,400블록입니다. 앞서 가정한 573블록은 현재 파일과 맞지 않습니다.
각 참조의 `element_id`와 `location`으로 v11 요소에서 본문을 복원합니다.
글은 요소의 `[start:end]`, 표는 해당 행의 칸을 열 순서로 ` | `로 잇습니다.
복원 본문이 context 블록 전체와 일치하는지 확인하고 해당 라벨을 모두 보관합니다.
dev 716/716, test 1,639/1,639항목이 확인됐으며, 같은 본문이 여러 블록에 반복된 항목은 각각 14개·26개입니다.
참조 순서와 블록 순서를 짝짓거나 근거 전체를 한 본문으로 합치지 않습니다.
이 좌표는 골든 본문 복원에만 사용하며 현재 청크의 좌표로 옮기지 않습니다.

근거와 청크 `body`를 NFC로 정규화하고, `|`를 공백으로 바꾸고 연속 공백을 하나로 줄입니다.
정규화한 근거 본문이 같은 문서의 청크 안에 그대로 포함되고 해당 청크 ID가 하나일 때만 라벨을 붙입니다.
유사도 점수는 사용하지 않습니다. 문서가 없으면 `doc_unmapped`, 정규화 후 20자 미만이면 `too_short`,
나머지는 일치 청크가 없으면 `not_found`, 둘 이상이면 `ambiguous`입니다.
20자 하한은 짧은 수·코드·항목 이름만으로 청크를 확정하지 않으려는 고정 규칙이며 test 결과에 맞춰 조절하지 않았습니다.

2026-10-16 로컬 현재 파서 출력(100문서·18,988청크)에서 측정한 결과입니다.
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

전체 dev 실패는 `doc_unmapped` 24 · `not_found` 64 · `ambiguous` 32 · `too_short` 290항목,
test 실패는 각각 19 · 188 · 50 · 674항목입니다. 문서 미연결 목록은 다음과 같습니다.

| 분할 | 골든 원본 문서 | doc_sha |
| --- | --- | --- |
| dev | 한국원자력연구원_한국원자력연구원 선량평가시스템 고도화.hwp | `3b643668220fa1ccaec14adea446bb8b7c604c46dfd9b9b428936e6fb06178db` |
| test | 중앙선거관리위원회_2025년도 행정정보시스템 위탁운영사업.hwp | `73abf8e4f78c36a19e2345a3e2a0be5afd0e8a5a1d27363f665e701b7ecade8d` |

질문 대상 문서는 dev 30개·test 68개지만 `unanswerable`이 다른 사업의 근거도 인용하므로 인용 근거 SHA는 36개·70개입니다.
그 인용 근거의 라벨이 질문 대상 문서의 정답 근거라는 뜻은 아닙니다.
라벨 품질 집계는 핵심 사실 점검에서 빠지는 질문까지 포함한 전체 골든 분할을 기준으로 합니다.
전체 주제별 결과는 03과 `artifacts/golden_mapping.csv`, 문서별 결과는 `golden_documents.csv`,
블록 대응·ID 감사는 `golden_correspondence.csv`에서 확인합니다.
03에는 seed 42로 고른 dev 근거 최대 30쌍의 골든 본문과 연결한 청크 전체 본문이 나란히 표시됩니다.
라벨된 근거가 30쌍 미만이면 전부 표시하며 0쌍이면 열 이름이 있는 빈 표를 표시합니다. 미연결 사유와 집계는 그대로 저장합니다.
이 표들은 03을 실행할 때 확인합니다. 저장소의 노트북은 실행 횟수와 출력을 비워 커밋하며,
로컬 문서 본문과 실행 결과를 노트북에 넣어 게시하지 않습니다. CSV 결과는 `artifacts/`에 보관합니다.

입력 경로 회귀 검사는 이전 산출물이 없는 임시 폴더에서 실제 v11 로더 또는 PDF 파서·청킹·저장을 거쳐
03의 보고·평가셋 저장·표본 셀을 실행합니다. v11, 원본 폴더, 단일 파일, ZIP, 중첩 ZIP, ZIP을 포함한 폴더의 여섯 경로를 확인합니다.

`eval_set.jsonl`에는 기존 점검을 통과한 dev 384문항과 YAML 1문항이 저장됩니다.
골든 항목은 현재 `doc_ids`와 각 `evidence`의 `text`, `doc_id`, 유일한 `chunk_id` 또는 `reason`을 가지며,
원래 ID는 `golden_chunk_id`에 남깁니다. YAML 항목은 `evidence_source = "none"`, `doc_ids = []`, `evidence = []`입니다.
이 라벨은 03이 고정해 저장하며, 05는 연결 규칙을 바꾸지 않고 해당 라벨 수준의 IR 지표를 계산합니다.

## OCR (저장 결과와 선택적 Vision 호출)

그림 유형(table · text · diagram)마다 기준 이미지에서 측정한 품질과 이미지당 비용으로 OCR 엔진을 고릅니다.
허용 엔진은 OpenAI API, OpenAI 호환 엔드포인트를 쓰는 Gemini API,
로컬 Windows PC의 별도 환경에서 실행하는 PaddleOCR-VL-1.5입니다.
유료 OCR 호출은 모두 `rag/usage.py`의 `record_usage`로 비용을 기록하고, PaddleOCR는 이미지당 실행 시간을 기록합니다.
벤치마크 첫 유료 호출과 전체 실행 전에는 모델별 토큰·단가 예상액을 보여 주고 승인을 기다립니다.
이번 비교의 승자는 표·글의 Gemini와 도식의 GPT이며, 320개 이미지의 결과를 391개 위치로 저장했습니다. 측정값과 비용은 [OCR 비교 보고서](docs/ocr_benchmark.md)에 있습니다.

`OCR = False`이고 `config.yaml`의 `paths.ocr_captions`(기본 `data/ocr_captions.jsonl`)가 있으면
01은 그 파일을 읽어 그림 위치에 `[그림/도표 설명] …` 레코드를 넣습니다. 이 결과를 읽는 데 API 키나 호출은 필요 없습니다.
HWP 본문 표시가 없는 그림은 문서 끝에, PDF 그림은 해당 쪽의 이미지 위 본문 다음에 들어갑니다.
기본 원본 입력(`PREPROCESSED = None`)에서는 설명 청크도 해당 위치에 넣고, 그림 경계에서 나뉜 짧은 본문도 유지합니다.
결과 파일이 없으면 저장 OCR을 추가하지 않으며 기존 전처리 출력을 유지합니다.

`01_preprocessing.ipynb` 의 `OCR = False` 를 `True` 로 바꾸면, 문서 속 그림을 LangChain `LLMImageBlobParser` + 선택한 OpenAI 비전 모델(`OCR_MODEL`, `.env` 의 `OPENAI_API_KEY`)로 글로 바꿔 청크에 넣습니다.
`True`에서는 저장 캡션 파일이 있어도 읽지 않고, 기존 Vision OCR·CRAFT 설정과 청크 분할 방식을 사용합니다.
OCR 모델·추론 강도·출력/추론 토큰 한도의 기본값은 `config.yaml`의 `ocr` 구역에서 읽으며 01의 설정 셀에서 바꿀 수 있습니다.
여러 쪽에 반복되는 그림(로고 · 장식, `parsing.max_repeat_image_pages` 쪽 이상)은 청크에 넣지 않습니다 — HWP 는 아예 보내지 않고, PDF 는 설명을 받은 뒤 반복된 설명을 뺍니다.
`False` 면 그림은 API 로 가지 않습니다.

### CRAFT로 OCR 전에 이미지 선별하기

CRAFT는 **글자를 읽는 OCR이 아니라, 글자가 있을 법한 영역을 찾는 탐지기**입니다. CRAFT를 켜면 그림을 먼저 살펴본 뒤 후보만 기존 OpenAI Vision OCR에 보냅니다. 기존 Vision 모델과 응답 형식은 유지합니다.

#### 1. 필요한 파일 준비

위 설치 절차대로 `python -m pip install -r requirements.txt`를 실행합니다. 선별 기능은 `easyocr==1.7.2`, 기존 `torch`, `pillow`를 사용합니다. 실제 글자 인식은 OpenAI Vision이 담당하며 EasyOCR의 문자 인식기는 로드하지 않습니다.

사전에 확보한 `craft_mlt_25k.pth`를 `models/easyocr/`에 둡니다. 코드가 모델을 자동 다운로드하지 않습니다. 모델 파일·이미지·캐시는 Git이나 PR에 넣지 마세요. 저장소 최상위 폴더를 작업 폴더로 사용합니다.

#### 2. 두 스위치 설정

| 노트북 `OCR` | `parsing.craft.enabled` | 실제 동작 |
|---|---|---|
| `False` | 어느 값이든 | 그림을 Vision에 보내지 않으며 CRAFT 선별도 실행하지 않음 |
| `True` | `false` — 기본값 | 기존 Vision OCR 경로 사용 |
| `True` | `true` | CRAFT로 먼저 선별한 후보만 Vision OCR에 전달 |

활성화하려면 `01_preprocessing.ipynb`의 `OCR = False`를 `OCR = True`로 바꾸고, `config.yaml`의 **기존 `parsing.craft` 항목**을 다음과 같이 설정합니다. 같은 항목을 두 번 추가하지 마세요.

```yaml
parsing:
  # 기존 parsing 설정은 그대로 둡니다.
  craft:
    enabled: true
    model_dir: models/easyocr
    cache_dir: artifacts/ocr_detector
    review_queue: artifacts/ocr_review.jsonl
```

끄려면 `enabled: false`로 되돌립니다. 다른 설정은 유지합니다. 이후 기존 안내대로 `01_preprocessing.ipynb`를 실행합니다. 코드 변경 후에는 커널을 재시작하세요. `OCR = True`에서는 후보 이미지의 Vision 호출에 API 키와 비용이 필요합니다.

#### 3. ON일 때 처리 흐름

`문서 속 이미지 → CRAFT 영역 탐지 → 상태 판정 → 후보만 기존 Vision OCR`

| 상태 | 뜻 | 처리 |
|---|---|---|
| `OCR_CANDIDATE` | 글자처럼 보이는 영역이 탐지됨 | 기존 Vision OCR에 전달 |
| `REVIEW_REQUIRED` | 글자 여부가 불확실하거나 처리 오류가 있음 | **자동 OCR하지 않고 검토 큐에 기록** |
| `OCR_UNNECESSARY` | 이미지 전체 픽셀이 균일해 보이는 정보가 없음 | OCR에서 제외 |

탐지 영역이 없거나 점수가 낮다는 이유만으로 불필요하다고 판정하지 않습니다. 표·도식의 작은 글자도 놓칠 수 있으므로 불확실하면 검토 대상으로 남깁니다. CRAFT ON에서는 HWP 반복 이미지도 반복 횟수만으로 삭제하지 않고, 각 발생 위치를 기록하면서 같은 이미지의 Vision 결과를 재사용합니다. PDF의 기존 반복 설명 정리 동작은 유지합니다.

#### 4. 검토 큐와 출처 확인

`artifacts/ocr_review.jsonl`을 텍스트 편집기로 엽니다. 한 줄이 한 번의 이미지 발생에 대한 검토 항목입니다. `classification`, `reason`, `source`, `location`으로 상태·사유·원본 문서·위치를 확인합니다. 검토가 끝나도 이 목록이 자동으로 OCR되거나 검색 본문에 반영되지는 않습니다.

모든 선별 판정은 기본 경로 `artifacts/ocr_selection.jsonl`에 저장됩니다. 이 파일은 `cache_dir`의 상위 폴더에 만들어집니다. 검토 큐와 판정 기록은 실행할 때 덧붙이므로 재실행 항목이 중복될 수 있습니다.

- HWP: 문서 SHA, 추출 이미지명, 본문 마커 문자 위치를 기록합니다. 원본 바이너리 record나 페이지 번호를 추정하지 않습니다.
- PDF: 문서 SHA, 페이지, 이미지 번호, xref, 배치 사각형을 기록합니다.

#### 5. 캐시와 오류 처리

CRAFT 탐지 결과는 `artifacts/ocr_detector/`에 저장합니다. 이미지 raster SHA, CRAFT 모델 SHA, 탐지 설정, EasyOCR 버전이 같으면 재사용합니다. 이 중 하나가 바뀌면 이전 결과를 재사용하지 않고 해당 탐지를 다시 수행합니다. 기존 OCR 결과와 승인 데이터는 변경하지 않습니다.

`parsing.craft.settings`로 탐지 설정을 바꿀 수도 있습니다. 이번 검증은 코드의 기본 설정을 사용했으며 설정을 바꾸면 별도 확인이 필요합니다. CRAFT 캐시는 Vision 응답의 영구 캐시가 아닙니다. HWP의 같은 이미지에 대한 Vision 응답 재사용은 한 번의 문서 처리 안에서 이루어집니다.

모델 부재, 탐지 실패, 지원하지 않는 형식, 이미지 디코딩 실패는 `REVIEW_REQUIRED`로 기록합니다. 해당 이미지를 자동으로 불필요 처리하거나 Vision에 우회 전송하지 않습니다.

#### 6. 검증 범위와 주의사항

최신 dev 기반 로컬 전체 테스트 **453/453 PASS**, Ruff 검사 통과를 확인했습니다. 외부 API를 차단하고 Vision을 Mock으로 대체한 테스트입니다. 기존 50개 판정은 안전한 전달 동작을 확인하는 자료로 재사용했으며, 신규 OCR이나 실제 Vision 정확도 평가를 수행하지 않았습니다.

CRAFT는 사진·로고·표의 의미를 판단하는 분류기가 아닙니다. 작은 글자·스타일 문자·체크기호를 놓칠 수 있고, 일반 사진의 분류 성능은 아직 미검증입니다. **OCR 정확도 향상이나 비용 절감을 검증한 결과가 아니며, 실제 운영 환경 검증도 완료되지 않았습니다.** 검토 큐를 승인된 검색 데이터로 사용하지 마세요.

자세한 구현 범위는 [CRAFT 선별 안내](docs/craft_ocr_selection.md)를 참고하세요.

## 알아둘 점
- `langchain-community` 는 **0.3.31 로 고정**합니다. ragas 0.4.3 이 community 0.4 에서 사라진 모듈을 import 하기 때문입니다.
- langchain-community 0.3.31 의 `PyMuPDFParser` 는 그림을 저장하기 전에 빈 버퍼를 검사하는 버그로 모든 그림을 건너뜁니다. `parsing.py` 가 OCR 을 켤 때만 이 부분을 패치합니다.
- `hwp-hwpx-parser` 의 하이퍼링크 컨트롤 무한 루프 버그도 `parsing.py` 가 패치합니다.
- GPT-6 LUNA and gpt-5-mini include reasoning tokens in `max_tokens` (`max_completion_tokens`). If an answer is empty, inspect token usage before changing the limit or reasoning effort.
- 배포용(암호화) HWP 는 본문을 읽을 수 없어 건너뜁니다. 한글에서 일반 `.hwp` · `.hwpx` · PDF 로 저장해 넣으세요.
- HWP 는 쪽 번호가 없어 HWP 청크의 출처는 섹션 경로로 표시됩니다.

## 개발 규칙
코딩 규칙은 `CLAUDE.md`(= `AGENTS.md`)에 있습니다. 커밋 전에:

```bash
ruff check .                              # 함수 복잡도 (C901 ≤ 8, PLR0915 ≤ 50)
.venv\Scripts\python -m pytest -q tests   # rag/ 모든 모듈 import 확인 (Linux: .venv/bin/python -m pytest -q tests)
```

- `.env` · `data/` · `artifacts/` 는 커밋하지 않습니다.
- 노트북은 출력을 지우고 커밋합니다.
- `rag/*.py` 를 고친 뒤에는 커널을 재시작하고 다시 실행합니다.



## 구조
```
01_preprocessing.ipynb … 05_evaluation.ipynb   파이프라인별 노트북 (설정 · 호출 · 표만)
config.yaml                설정 (① 전처리 ~ ⑤ 평가 구역)
eval/
  golden/                  골든 분할 final6 복사본 — dev.jsonl (03 평가셋) · test.jsonl (03은 라벨 품질만 확인) · manifest.json
  eval_questions.yaml      평가 질문 세트 (질문 · 정답 · must_include)
rag/
  config.py                config.yaml · .env 읽기, jsonl 읽기/쓰기
  preprocessing/           ① parsing.py · chunking.py
  retrieval/               ② indexing.py · retrieval.py
  validation/              ③ validation.py
  generation/              ④ generation.py
  evaluation/              ⑤ evaluation.py
golden_pipeline/           ③ 주제별 골든 데이터 스키마 · 상태 · 저장 규약 · v11 근거 어댑터 (테스트는 tests/golden/)
frontend/                  ⑥ 질문 화면
  server.py                POST /api/ask — answer_question 을 감싸는 FastAPI
  web/                     React + Vite 화면 (/api 는 server.py, /ocr-api 는 ocr_select/server.py 로 프록시; ocr.html 은 라벨링, review.html 은 저장 OCR 결과 검토)
  start.cmd · start.command  Windows · macOS 실행기
  ocr_select/              OCR 이미지 라벨링 — extract.py (그림 꺼내기) · server.py (API, 위 실행기가 8766 에 띄움) · merge.py (묶음 결과 합치기)
tests/test_smoke.py        게이트: rag/ 모든 모듈 import
artifacts/                 (커밋 안 함) 노트북 사이에 주고받는 파일
```

