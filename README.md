# RFP RAG — 공공기관 제안요청서 질의응답 (PDF · HWP · 하이브리드 검색 · gpt-5-mini · RAGAS)

RFP 문서(PDF · HWP · HWPX)를 파싱해 청크로 나누고, BM25 + 임베딩(FAISS) 하이브리드 검색으로 찾은 청크를 근거로 `gpt-5-mini` 가 답합니다.
답은 네 가지(Retrieval · Generation · Grounding · End-to-End)로 나눠 채점해, 나쁜 답이 어디서 왔는지 가립니다. 채점은 기본으로 로컬 모델만 써서 API 비용이 없고, 원하면 RAGAS + gpt 심판으로 바꿀 수 있습니다.

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

증강 Golden dev 396 · v12 공유 평가 패키지 ZIP(`Golden_Dev396_v12_Team_Package_..._v2.zip`)을 `data/` 에 그대로 풉니다 → `data/Golden_Dev396_v12_Team_Package/`.
01 은 이 패키지의 검색 코퍼스(`corpus/chunks.jsonl` · `docs.jsonl` — v12 98문서 · 18,989청크)를, 02 는 기관 목록(`data/data_list.csv`)을, 03 은 평가 질문(`data/golden_dev.jsonl` 396문항)을 그대로 읽습니다.
패키지 파일은 고치지 않습니다 — 패키지 폴더에서 `python prepare.py` 를 실행하면 `PASS` 와 396문항 · 98문서 · 18,989청크 · F199/D194/B3 가 나와야 합니다.
RFP 그림 OCR 결과(`RFP_OCR_파싱.zip` 의 `data/ocr_captions.jsonl` — 79문서 · 그림 320장 · 391곳)는 패키지의 `corpus/` 에 그대로 복사합니다 → `data/Golden_Dev396_v12_Team_Package/corpus/ocr_captions.jsonl`.
01 이 패키지 코퍼스를 읽을 때 이 파일이 있으면 그림 설명을 `[그림/도표 설명] …` 청크(`kind = image_ocr`, 같은 문서의 같은 그림은 한 번, 1,400자 넘으면 줄 단위로 나눔 — 375청크)로 코퍼스 끝에 덧붙입니다. 기존 18,989청크의 순서 · id 는 그대로라 02 는 끝부분 임베딩만 새로 계산합니다.
문서는 원본 SHA(`document_sha256` = 패키지 `doc_id`)로 찾고, 원본이 고쳐져 SHA 가 다른 2문서(중앙선거관리위원회 · 한국원자력연구원, 8곳)는 같은 파일명으로 찾습니다. `images/`(그림 원본, 약 380MB)는 코드가 읽지 않으므로 복사하지 않아도 됩니다. 파일을 빼면 예전 18,989청크로 돌아갑니다.
RFP 원본으로 직접 파싱할 때만 RFP ZIP 을 `data/rfp.zip` 에 둡니다 (`config.yaml` 의 `paths.input`, 폴더도 가능).
기관 목록은 `paths.org_csv`(기본 패키지의 `data/data_list.csv`)입니다.
UTF-8 CSV에 `파일명`, `발주기관` 열이 있어야 합니다 (열 이름에 공백 없음). Excel이 붙인 BOM도 읽습니다. 목록은 자동 생성하지 않으며,
파일이 없으면 02 색인·검색과 질문 화면을 실행하기 전에 담당자에게 요청하세요.
기관명은 이 CSV와 문서 표지에서 모읍니다. 02의 `3. 기관 라우팅 점검` 셀이 기관명이 하나도 연결되지 않은 문서를 보여 줍니다.
이 문서들은 질문에 기관명이 나와도 전체 문서에서 찾으므로, 목록이 길면 CSV의 파일명을 확인하세요.
CSV 기관명은 담당자가 확인한 목록이라 자동 추출용 일반명 필터(…위원회 등)를 쓰지 않고, 앞뒤 법인 형태(`(사)` · `주식회사` · `㈜` · 괄호)를 떼어 맞춥니다.
여러 낱말 기관명은 기관 접미사나 시·군·구로 끝나는 낱말로도 찾습니다 (`경희대학교 산학협력단` → `경희대학교`, `경상북도 봉화군` → `봉화군`).
광역 지자체(`인천광역시 동구` 의 `인천광역시`)와 하위 조직 일반명(`산학협력단`, `조직위원회`)은 따로 쓰지 않습니다. 같은 기관 문서가 여러 개면 모두 검색합니다.
CSV가 정식 명칭(`한국국제협력단`, `수산업협동조합중앙회`)이어도 질문에는 흔한 이름이 나오므로, `발주기관_사업명` 파일명의 앞부분(`KOICA 전자조달` → `KOICA`, `수협중앙회`)도 같은 문서의 기관명으로 씁니다.
검색은 요구사항 코드 일치 청크를 먼저 담고, 같은 문서에서 숫자 · 부정어까지 같은 거의 같은 본문만 제외하며 (`2초/5초`, `포함한다/포함하지 않는다` 는 둘 다 남김),
`retrieval.token_budget`(기본 2500)으로 본문 토큰 합을 제한합니다. 첫 청크는 예산을 넘어도 유지합니다.
질문에 기관이 둘 이상 나오면(비교 질문) 기관마다 다른 기관 이름을 뺀 질문으로 따로 찾고, 토큰 예산도 기관마다 따로 써서(기관당 `token_budget`) 번갈아 담습니다. 같은 문서를 가리키는 기관명(`전북대학교` · `공유대학`)은 하나로 합칩니다. 한 기관에 사업 문서가 여럿이면 질문에 나온 사업명 고유 낱말(다른 사업 제목에 거의 안 나오는 낱말, 글자 수로 비교)이 가장 많은 문서의 후보를 먼저 담고, 같은 기관의 다른 사업은 그 뒤에 둡니다 (빼지는 않음).
전처리 패키지(`PREPROCESSED`)를 쓰면 청크의 연결 정보도 검색에 씁니다. 요구사항 ID · 명칭과 상세 내용이 다른 청크로 나뉘어도
① 색인 · 리랭커가 읽는 **검색 글**에서 상세 청크 앞에 `[요구사항 SER-001 보안관리 및 규정 준수]`(같은 `requirement_key` 청크의 ID · 명칭)를 붙여 요구사항 ID · 이름으로 상세 청크가 찾히고(답변 근거에는 원래 글),
② 질문의 요구사항 ID 로 상세 청크까지 정확 일치하며(`requirement_ids` · `requirement_key`),
③ 찾은 청크 바로 뒤에 연결 청크 — 같은 요구사항의 다른 청크와 여러 청크로 나뉜 같은 표(`table_refs`, 6청크 이하)의 다른 부분 — 를 찾은 청크 하나당 600토큰까지 함께 담습니다 (토큰 예산 안에서).
01 에서 직접 청크를 나눈 경우엔 연결 정보가 없어 본문 속 코드만 씁니다. 검색 글이 바뀌면 02 의 색인을 다시 만들어야 하며, 색인과 청크가 맞지 않으면 검색 때 알려 줍니다(`artifacts/index/texts.sha1`).
질문에 기관이 나오면 그 기관 문서 안에서는 질문에서 기관 · 사업을 가리킨 부분(`스포츠윤리센터의 「… LMS 기능개선」`)을 빼고 순위를 매깁니다 — 범위를 이미 좁혔으니 이 낱말들은 청크를 가르지 못하고 사업명을 되풀이하는 표지 · 서식 청크만 앞세웁니다. 사업명 낱말이 본문에서 다시 나오면(`ERP 행`) 남기고, 빼면 낱말이 거의 안 남는 질문은 그대로 씁니다.
토큰 예산으로 자르기 전에 하이브리드 상위 30개 후보(`rerank.top_n`)를 로컬 리랭커가 다시 정렬합니다.
리랭커(`rerank.model`, 기본 `dragonkue/bge-reranker-v2-m3-ko`)는 질문과 청크를 함께 읽는 크로스 인코더로, 임베딩처럼 GPU에서 돌아 API 비용이 없습니다.
요구사항 코드 일치 청크는 리랭커를 켜도 맨 앞에 둡니다. 02 설정 셀의 `RERANK = False`로 끄면 하이브리드 점수 순서 그대로 담습니다.
노트북은 VS Code · PyCharm · Jupyter 에서 `.venv` 커널로 **01 → 05 순서대로** 실행합니다.
처음 실행할 때 임베딩 모델 KURE-v1(약 2.3GB)과 리랭커 모델(약 2.3GB)을 내려받습니다.

### 중간에 끊겼을 때 — 이어서 실행
오래 걸리는 단계는 중간 결과를 `artifacts/` 아래에 저장하므로, 끊긴 셀부터 다시 실행하면 끝낸 부분은 건너뜁니다.

| 단계 | 저장 단위 · 위치 | 다시 처음부터 하는 경우 |
|---|---|---|
| 01 `2. 파싱` (OCR 켜도 꺼도) | 문서 하나마다 `artifacts/parsed/` | 원본 파일 크기, `parsing` · `ocr`(모델 · 토큰 한도 · 추론 강도) 설정, `OCR` 켜고 끔이 바뀐 문서 |
| 01 `3. 청크 분할` | 문서 하나마다 `artifacts/chunked/` | 그 문서의 파싱 결과나 `chunking`(`CHUNK_SIZE` 등) 설정이 바뀐 문서 |
| 02 `1. 색인 만들기` (임베딩) | 청크 1,000개마다 `artifacts/index/checkpoint/` | 청크 본문이나 `embedding`(모델 · 최대 길이) 설정이 바뀐 묶음 |
| 04 답변 생성 | 질문 하나마다 `artifacts/checkpoints/answers/<설정 해시>.jsonl` | 답변 · 재작성 · 검색 설정(`retrieval` · `rerank` · `embedding` · `bm25`), 청크 · 문서 목록 · 기관 CSV가 바뀌면 새 파일로 처음부터. 03에서 질문이 바뀌면 바뀐 질문부터 |
| 05 네 가지 평가 (`JUDGE = "ragas"` 일 때) | 16문항마다 `artifacts/checkpoints/judge/retrieval.jsonl` · `generation.jsonl` · `grounding.jsonl` · `end_to_end.jsonl` | 질문 · 근거 · 답 · 정답이나 심판 설정(모델 · 추론 강도 · 토큰 한도)이 바뀐 문항, 점수가 NaN인 문항 |

- OCR을 켠 경우 이미 끝낸 문서의 OCR 비용은 다시 들지 않습니다. 파싱 중 오류가 난 문서는 저장하지 않아 다음 실행에서 다시 시도합니다.
- 01의 `chunks.jsonl` · `docs.jsonl` 은 임시 파일에 쓴 뒤 바꿔치기해, 저장 도중 꺼져도 반쯤 쓰인 파일이 남지 않습니다.
- 02의 BM25 토큰은 수십 초면 끝나 저장하지 않고 매번 새로 만듭니다.
- 04는 저장된 답으로 이전 대화(직전 10개)를 되살린 뒤 다음 질문부터 생성하므로, 끊기지 않고 돌린 것과 같은 대화 기록으로 이어집니다.
  같은 설정으로 다시 실행하면 저장된 답을 그대로 씁니다 (API 호출 0회).
- 05는 남은 문항만 심판에 보내므로 이미 채점한 문항의 비용은 다시 들지 않습니다. 저장된 점수만으로 끝나면 OpenAI 키도 쓰지 않습니다.
- 완전히 처음부터 하려면 `artifacts/parsed/` · `artifacts/chunked/` · `artifacts/index/checkpoint/` · `artifacts/checkpoints/answers/` · `artifacts/checkpoints/judge/` 중 해당 폴더를 지우세요.

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
| 구조·상세 출처 메타데이터 | 요구사항 소속(`requirement_key` · `requirement_ids`)과 표 연결(`table_refs`, 증강 Golden dev 396 패키지 코퍼스)은 02 검색이 씁니다 — 검색 글의 요구사항 머리말 · 요구사항 코드 정확 일치 · 연결 청크 함께 담기. 표 셀 구조, `spans`, `linked`, `image_source`, 이미지 SHA·검증 영역 등은 생성 문맥에 전달하지 않습니다. |
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
기본값은 증강 Golden dev 396 패키지의 검색 코퍼스를 그대로 읽습니다(이미 02 형식이라 옮기지 않음).

```python
PREPROCESSED = "data/Golden_Dev396_v12_Team_Package/corpus"
```

`data/rfp.zip`을 현재 파서로 처리하려면 `None`, v12 · v11 전처리 패키지를 옮기려면 그 폴더 경로로 바꿉니다.

```python
PREPROCESSED = None                                        # 현재 파서
PREPROCESSED = "data/RFP_Preprocessing_Final_v11_Team"     # v11 (v12 는 "data/RFP_v12")
```

01을 처음부터 실행하면 v11의 저장된 OCR 텍스트와 청크를 읽어
`artifacts/docs.jsonl`, `artifacts/chunks.jsonl`로 저장합니다. 파싱·OCR·청크 재분할은 하지 않습니다.
본문이 `[IMAGE]` 표시뿐인 청크는 제외하고, 패키지에 쪽 번호가 없는 HWP는 `page = None`을 유지합니다.
이후 02부터 다시 실행해 새 입력의 색인을 만드세요. 임베딩의 `max_seq_length` 기본값은 2048입니다.

입력끼리 비교할 때는 03을 한 번 실행해 만든 `eval_set.jsonl`(증강 Golden dev 396 패키지 396문항)의 질문을 두 입력에 똑같이 씁니다.
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
| ① 전처리 | `01_preprocessing.ipynb` | `rag/preprocessing/parsing.py` (PDF · HWP/HWPX 파싱 · 정제 · OCR), `rag/preprocessing/chunking.py` (청크 분할) | `artifacts/chunks.jsonl`, `artifacts/docs.jsonl`, `artifacts/parsed/` · `artifacts/chunked/` (문서별 파싱 결과 · 청크 — 끊겨도 이어서 실행) |
| ② 검색 | `02_retrieval.ipynb` | `rag/retrieval/indexing.py` (임베딩 · FAISS · BM25 색인), `rag/retrieval/rewrite.py` (질문 재작성 · API 사용량), `rag/retrieval/retrieval.py` (하이브리드 검색 · 발주기관 라우팅) | `artifacts/index/` (`checkpoint/` = 임베딩 묶음 — 끊겨도 이어서 실행) · `artifacts/retrieval_settings.jsonl` |
| ③ 검증 | `03_validation.ipynb` | `rag/validation/validation.py` (증강 Golden dev 396 패키지 평가 질문 읽기 · 평가 항목 점검 · 근거 보존 판정 집계) | `artifacts/eval_set.jsonl` |
| ④ 생성 | `04_generation.ipynb` | `rag/generation/generation.py` (검색 → 이전 대화를 참고해 답변 · 토큰 · 지연 시간) | `artifacts/answers.jsonl`, `artifacts/checkpoints/answers/` (질문별 답 — 끊겨도 이어서 실행) |
| ⑤ 평가 | `05_evaluation.ipynb` | `rag/evaluation/evaluation.py` (네 가지 평가) | `artifacts/retrieval.csv` · `generation.csv` · `grounding.csv` · `end_to_end.csv`, `artifacts/checkpoints/judge/` (문항별 RAGAS 점수 — 끊겨도 이어서 실행) |
| ⑥ 질문 화면 | — | `frontend/server.py` (`answer_question` 을 감싸는 `POST /api/ask`), `frontend/web/` (React + Vite 화면), `frontend/start.cmd` · `frontend/start.command` (실행기); `frontend/ocr_select/` (OCR 이미지 라벨링 화면) | 브라우저 화면의 답변 · 출처, `artifacts/ocr_labels/labels.jsonl` |

공통: `rag/config.py` (`config.yaml` · `.env` 읽기, jsonl 읽기/쓰기), `config.yaml` (모든 설정 — 파이프라인별 구역).

01·02·04·05에는 직접 값을 조절하는 설정 셀이 있습니다. 변수의 초기값은 `config.yaml`에서 읽으므로, 바꾸려는 변수의 오른쪽을 원하는 값으로 바꾸세요.

| 노트북 | 설정 셀에서 조절하는 값 |
|---|---|
| 01 전처리 | `OCR`, `OCR_MODEL`, `OCR_REASONING_EFFORT`, `OCR_MAX_TOKENS`, `OCR_PRICES`, `CHUNK_SIZE` |
| 02 검색 | `REWRITE_MODEL`, `REWRITE_REASONING_EFFORT`, `REWRITE_MAX_TOKENS`, `REWRITE_PRICES`, `DENSE_WEIGHT` (BM25는 `1 - DENSE_WEIGHT`), `RERANK` (로컬 리랭커 사용) |
| 04 생성 | `LLM_MODEL`, `LLM_REASONING_EFFORT`, `LLM_MAX_TOKENS`, `LLM_PRICES` |
| 05 평가 | `JUDGE` (`"local"` 로컬 채점 API 0원 / `"ragas"` gpt 심판), `JUDGE_MODEL`, `JUDGE_REASONING_EFFORT`, `JUDGE_MAX_TOKENS`, `JUDGE_PRICES` (`ragas` 일 때만) |

예를 들어 02 설정 셀의 `DENSE_WEIGHT = cfg["retrieval"]["dense_weight"]`를 `DENSE_WEIGHT = 0.8`로 바꾸면 Dense 80%·BM25 20%로 검색합니다.
설정 셀은 메모리의 설정을 바꾸며 `config.yaml`을 덮어쓰지 않습니다. 02는 적용한 rewrite·검색 설정을 `artifacts/retrieval_settings.jsonl`에 저장하고 04가 읽습니다.
기존 색인이 있어도 이번 변경 후에는 02의 설정 셀을 실행해 이 파일을 만든 뒤 04를 실행하세요. 청킹 크기를 바꾸면 01부터, 검색 설정을 바꾸면 02부터 후속 노트북을 다시 실행해야 합니다.
모델을 바꾸면 같은 설정 셀의 `*_PRICES`도 해당 모델의 입력 · 캐시 입력 · 출력 단가(USD / 100만 토큰)로 맞추세요.
기본 단가는 [OpenAI 공식 gpt-5-mini 문서](https://developers.openai.com/api/docs/models/gpt-5-mini)의 Standard 요금입니다. 비용은 설정한 단가에 따른 추정값이며 실제 청구서와는 다를 수 있습니다.

02 검색 예제와 04 답변 생성은 검색 전에 `rag/retrieval/rewrite.py`로 질문을 재작성합니다.
`config.yaml`의 `rewrite.model`, `rewrite.max_tokens`, `rewrite.reasoning_effort`가 이 API 호출에 적용됩니다.
검색과 기관 라우팅에는 재작성한 질문을 쓰고, 답변 생성·평가에는 원본 질문을 씁니다. 재작성 출력이 비면 원본 질문으로 검색합니다.
04는 평가셋 순서대로 답하며 직전 질문·답변 최대 10개를 다음 질문의 재작성 요청과 답변 생성 요청에 함께 전달합니다. 이전 대화는 질문 이해에만 사용하고 사실의 근거는 현재 검색한 문서로 제한합니다.
질문마다 재작성 API 호출 비용이 추가되며, 04의 `answers.jsonl`에는 검색용 질문·모델·토큰·비용·지연 시간을 `rewrite` 필드에 별도로 저장합니다.
답변 생성도 실제 응답 모델·캐시 입력 토큰·비용을 저장합니다. 05는 저장된 비용을 사용하므로 평가 시 설정을 바꿔도 이전 생성 비용이 바뀌지 않습니다.
`latency_s`는 재작성·검색·답변 생성 전체 시간입니다. `end_to_end.csv`의 `cost_usd`는 rewrite + 답변 생성 비용이며 `rewrite_cost_usd`, `answer_cost_usd`로 구분됩니다. OCR과 평가 비용은 별도로 집계합니다.
이번 변경 전에 만든 `answers.jsonl`은 새 사용량 필드가 없으므로 02 설정 셀 → 04 → 05를 다시 실행하세요.
평가 항목에 `answerable` 이 생기기 전에 만든 `eval_set.jsonl` · `answers.jsonl` 은 04 · 05 가 API 호출 전에 빠진 필드를 알리고 멈춥니다. 03 → 02 설정 셀 → 04 → 05 를 다시 실행하세요.

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
라벨은 기록만 합니다. 01 전처리가 라벨을 읽어 OCR 대상을 고르게 하는 일은 전처리 담당의 별도 변경입니다.

실행 — 저장소 최상위에서
1. 그림 꺼내기: `.venv\Scripts\python -m frontend.ocr_select.extract` (macOS: `.venv/bin/python`). `config.yaml` 의 `paths.input`(기본 `data/rfp.zip`)을 01 과 같은 함수로 읽습니다. 문서 100개에 1분 남짓 걸립니다.
2. 화면 열기: 질문 화면과 같은 실행기(`frontend\start.cmd` · `frontend/start.command`)를 더블클릭하고, 첫 화면 오른쪽 위 `설정` → `OCR 이미지 라벨링` 을 누릅니다 (`http://localhost:5173/ocr.html`). 실행기가 라벨링 화면의 API 서버(포트 8766)도 함께 띄웁니다.
3. 묶음 고르기: 상단 바에서 맡은 `묶음 1` ~ `묶음 5` 를 누릅니다. 카드를 문서 이름 · 문서 안 위치 순서로 세워 다섯으로 고르게 자른 것이라(209 · 209 · 209 · 209 · 208곳), 같은 `data/rfp.zip` 으로 extract 했다면 누구 컴퓨터에서나 같은 묶음입니다. 고른 묶음은 주소(`?batch=2`)에 남아 새로고침해도 그대로입니다.
4. 결과 내보내기: 다 매기면 상단 바의 `결과 내보내기` 를 눌러 `ocr_labels_batchN.jsonl` 을 내려받고, 합치는 사람에게 보냅니다. 저장 중인 라벨이 있으면 저장이 끝날 때까지 이 버튼이 잠기고, 진행 수는 저장을 마친 라벨만 셉니다.
5. 합치기 (한 사람): 받은 파일을 모두 넘겨 `.venv\Scripts\python -m frontend.ocr_select.merge ocr_labels_batch1.jsonl ocr_labels_batch2.jsonl ...` 를 실행합니다. 묶음마다 매긴 수와 빠진 위치 수를 출력하고 `artifacts/ocr_labels/merged_labels.jsonl` 에 씁니다. 같은 위치를 두 사람이 매겼으면 `labelled_at` 이 늦은 라벨이 남습니다.

결과 — `artifacts/ocr_labels/`
- `images/<그림 해시>.<확장자>`: 꺼낸 그림. 같은 바이트의 그림은 파일 하나입니다. extract 를 다시 실행하면 이 폴더만 새로 만듭니다.
- `images.jsonl`: 서로 다른 그림 한 줄씩 — `image_sha256`, `file`, `viewable`, `reason`, `occurrences`(위치마다 `doc_id` · `source` · `document_sha256` · `format`, HWP 는 `image_name` · `marker_start` · `repeated_occurrences`, PDF 는 `page` · `image_index` · `xref` · `bbox_points` — CRAFT 기록과 같은 이름). 문서에 들어 있지만 본문에 `[IMAGE]` 표시가 없는 HWP 그림(쪽에 놓이지 않은 그림 등)은 `marker_start` 가 `null` 이고, 01 전처리 · CRAFT 는 이 그림을 보지 않습니다.
- `labels.jsonl`: 라벨을 누를 때마다 `{image_sha256, label, labelled_at, occurrences}` 한 줄을 덧붙입니다. `occurrences` 에는 매긴 위치 하나가 들어갑니다. 다시 매긴 라벨도 새 줄이고, 위치마다 마지막 줄이 지금 라벨입니다. extract 를 다시 실행해도 지우지 않습니다.
- `merged_labels.jsonl`: 합친 결과. 매긴 위치마다 한 줄 — `labels.jsonl` 과 같은 모양에 `batch`(묶음 번호)가 더해집니다. 내려받는 `ocr_labels_batchN.jsonl` 도 같은 모양입니다.

## API 사용량 자동 기록

Langfuse 키 없이도 OCR·질문 재작성·답변 생성·Judge/RAGAS의 호출마다 `artifacts/api_usage.csv`에 한 행이 자동 추가됩니다.
01·02·04·05의 마지막 셀에서 단계·모델·추론 강도별 누적 호출 수, 입력·캐시 입력·출력·추론 토큰과 예상 비용을 확인합니다.
`reasoning_effort` 열은 그 호출에 보낸 추론 강도입니다. `none` 이면 추론 토큰(`reasoning_tokens`)은 0 이어야 하지만, 질문 · 근거를 읽는 입력 토큰과 답을 쓰는 출력 토큰은 그대로 듭니다 —
`none` 은 "생각" 토큰만 없앨 뿐 호출 자체를 공짜로 만들지 않습니다. 이 열이 생기기 전에 기록한 행은 빈 칸이며, 예전 파일은 첫 기록 때 열을 추가해 다시 씁니다.

| `stage` | 기록 대상 | `subject` / `evaluation` |
|---|---|---|
| `ocr` | 이미지 분석 LLM 호출 | 원본 문서 파일명 |
| `rewrite` | 02 검색 예제와 04의 질문 재작성 | 원본 질문 |
| `answer` | 04 답변 생성 | 원본 질문 |
| `judge` | RAGAS 내부 심판 호출 (`JUDGE = "ragas"` 일 때만) | 평가 종류: retrieval / generation / grounding / end_to_end |

Judge는 RAGAS가 사용하는 모델이므로 같은 요청을 두 비용으로 더하지 않습니다. RAGAS의 내부 재시도도 응답에 사용량이 있으면 기록합니다.
Judge 호출은 평가 종류 단위로 집계하며 개별 질문 ID와 연결하지 않습니다. 03의 평가 데이터셋 생성 API와 로컬 KURE 임베딩은 이 CSV의 대상이 아닙니다.
캐시 입력 토큰은 입력 토큰에, 추론 토큰은 출력 토큰에 이미 포함되어 있습니다. 비용 계산은 캐시 입력 단가를 따로 적용하고 추론 토큰을 이중 과금하지 않습니다.
비용은 설정의 단가(`*_usd_per_1m_tokens`, 노트북의 `*_PRICES`)로 계산하므로 모델을 바꾸면 단가도 그 모델 것으로 바꾸세요 — 토큰 수는 맞아도 비용이 틀립니다.
05 의 `end_to_end.csv` 토큰 열(`reasoning_tokens` · `rewrite_reasoning_tokens` 등)은 04 의 답변 생성 · 질문 재작성 토큰이며, 심판(Judge) 토큰은 여기 `judge` 행에만 있습니다.

`api_usage.csv`는 재실행할 때도 누적되며 평가 점수 CSV는 최신 결과로 덮어씁니다. 새 실험의 사용량만 보고 싶으면 실행 전에 기존 `api_usage.csv`를 다른 위치에 보관하세요.
API 응답을 받지 못한 요청은 소비 토큰을 확인할 수 없어 기록하지 않습니다. OCR을 끄면 새 OCR 호출이 없지만 이전 사용량은 표에 남습니다.
CSV는 UTF-8 without BOM입니다.

## 평가 — 하나의 답변 파일을 네 가지로

05 의 네 평가는 모두 04 가 만든 같은 `artifacts/answers.jsonl` 을 채점합니다. 표마다 질문별 점수와 맨 아래 `평균` 행이 나옵니다.
각 평가 함수가 답변 파일과 같은 폴더에 점수 CSV를 자동 저장하므로 노트북 밖에서 호출해도 저장됩니다.

| 평가 | 판단하는 것 | 지표 |
|---|---|---|
| Retrieval | 검색한 청크가 정답에 필요한 내용을 담았나 | `context_precision` · `context_recall`, 검색 청크 속 핵심 사실 비율 `key_facts_in_context` |
| Generation | 답이 질문에 맞고 핵심 사실을 담았나 | `answer_relevancy` (KURE-v1 임베딩), 답 속 핵심 사실 비율 `key_facts_in_answer` |
| Grounding | 답이 검색한 청크 안에서만 나왔나 (환각) | `faithfulness` |
| End-to-End | 최종 답이 정답과 맞나 · 얼마나 걸리고 들었나 | `factual_correctness`, 질문당 `latency_s` · 입력/출력/추론 토큰 · 예상 비용 `cost_usd` |

`context_precision` · `context_recall` · `answer_relevancy` · `faithfulness` · `factual_correctness` 는 심판이 매깁니다. 05 설정 셀의 `JUDGE`(`config.yaml` 의 `evaluation.judge`)로 고릅니다.

| 지표 | `JUDGE = "local"` (기본 · API 0원) | `JUDGE = "ragas"` (gpt 심판 · 유료) |
|---|---|---|
| `context_recall` | 정답 문장 중 검색 청크로 지지되는 비율 | gpt 가 정답 문장마다 판정 |
| `context_precision` | 정답 문장을 지지하는 청크의 순위 평균 정밀도 (RAGAS 와 같은 식) | gpt 가 청크마다 판정 |
| `faithfulness` | 답 문장 중 검색 청크로 지지되는 비율 | gpt 가 답을 주장으로 나눠 판정 |
| `factual_correctness` | 정답으로 지지되는 답 문장 비율(정밀도)과 답으로 지지되는 정답 문장 비율(재현율)의 F1 | gpt 가 답 · 정답을 주장으로 나눠 F1 |
| `answer_relevancy` | 질문과 답의 KURE-v1 임베딩 코사인 유사도 | 답에서 거꾸로 만든 질문과 원래 질문의 유사도 |

- local 의 "지지"는 02 의 로컬 리랭커(`rerank.model`, 크로스 인코더)가 (문장, 근거)를 관련 있다고 보고(점수 0.5 이상), 문장 속 숫자 · 날짜가 근거에 모두 있다는 뜻입니다 (`3초`/`5초` 처럼 숫자만 다른 문장은 지지 안 됨). 질문에 나온 숫자는 근거에 없어도 됩니다 — `5초가 아니라 3초` 처럼 잘못된 전제를 바로잡는 문장 때문입니다.
- local 은 출처 표시 `[1]` · 목록 기호 · 표 머리글과 구분선 · 짧은 제목 · "제공된 문서에서 확인할 수 없습니다" 문장을 빼고 채점합니다. 답에 채점할 문장이 없으면 `faithfulness` 는 NaN 입니다.
- local 은 KURE-v1 과 리랭커를 GPU 에서 돌려 88문항 기준 몇 분이면 끝납니다 (02 · 04 에서 이미 내려받은 모델이라 새로 받지 않음).
- 두 방식은 지표 이름이 같아도 값의 크기가 다릅니다. local 점수끼리, ragas 점수끼리만 비교하세요. 보고서용 최종 수치가 필요할 때만 `ragas` 로 한 번 돌리는 것을 권합니다.

- 답할 수 없음(`unanswerable`) 질문은 찾아 올 정답 근거가 없고 맞는 답이 거절 문장이라, 그 질문의 `context_precision` · `context_recall` · `key_facts_in_context` · `answer_relevancy`(거절을 0 으로 매김)는 잘 해도 0 이 나옵니다. 평가 항목의 `answerable` 이 `false` 인 질문은 이 지표를 빈 칸(NaN)으로 두어 평균에서 뺍니다.
- Retrieval 이 낮으면 검색 문제, Retrieval 은 높은데 Grounding 이 낮으면 환각, 둘 다 높은데 End-to-End 가 낮으면 정답 · 질문을 다시 볼 차례입니다.
- `ragas` 의 심판 LLM 은 `config.yaml` 의 `evaluation.judge_model`(`gpt-6-luna`, 추론 강도 `none`, 단가 `judge_usd_per_1m_tokens`)이고, 평가할 때마다 OpenAI 비용이 듭니다. 토큰 대부분은 `context_precision` 이 검색 청크마다 심판을 한 번씩 부르는 입력 토큰입니다.
- 프로젝트 책임자는 Langfuse Cloud 에서 질문마다 추적 하나(`answer-question` 안에 검색 `retrieve-context` · 생성 `generate-answer` — 모델 · 토큰 · 비용 포함)를 보고, 05 의 질문별 점수도 그 추적에 붙어 있습니다. 키가 없는 팀원은 노트북 표와 CSV 로 봅니다.

### 평가 데이터셋 (03 검증) — 증강 Golden dev 396 패키지만
03은 증강 Golden dev 396 · v12 공유 평가 패키지(`Golden_Dev396_v12_Team_Package`)의 `data/golden_dev.jsonl` 396문항과 기존 골든 88문항(`eval/gold_dev.jsonl` 55 · `eval/gold_needle.jsonl` 33 — 두 문서 비교 7문항 포함)을 평가셋으로 씁니다 (`validation.golden_sets`, 484문항).
질문 · 정답(`reference`) · 핵심 사실(`key_facts`)은 바꾸지 않고 그대로 옮기며, 다른 평가 질문 파일(`eval/` 아래 골든 분할 · yaml)은 섞지 않습니다.
05 결과에서는 문항 id 앞부분으로 셋을 가릅니다 — 패키지 `numeric-…` · `table-…` · `condition-…` · `comparison-…` · `multi_hop-…`, `gold_dev` 는 `refresh50-…` · `cutover-…`, `gold_needle` 은 `needle-…`.
- 패키지 396문항: numeric 104 · table 96 · multi_hop 71 · condition 69 · comparison 56 (30개 문서). 484문항 모두 `reset_context = true` 라 04 생성은 질문마다 새 대화로 답합니다.
- 패키지 396문항의 근거 보존 판정(`evidence/question_status.json`)을 03 마지막 표에서 질문 유형별로 셉니다 — F 199 (근거 경로 입증) · D 194 (추가 확인 필요) · B 3 (골든 검토 후보). 검색 성능 점수가 아니며, 05 결과를 나눠 읽을 때 씁니다.
- `comparison` 56문항은 모두 문서 하나 안의 비교입니다(두 문서 비교 아님).
- 질문 없음 · 중복 질문 · 정답 없음 · 핵심 사실 없음은 사유와 함께 제외하는데, 484문항 모두 통과합니다.
- `rag/validation/evidence.py`(골든 릴리스 근거를 v11 · v12 요소로 복원해 청크 라벨 붙이기)는 골든 릴리스 형식(`eval/golden/`)용이라 지금 03은 쓰지 않습니다.

## OCR (선택, 기본 꺼짐)
`01_preprocessing.ipynb` 의 `OCR = False` 를 `True` 로 바꾸면, 문서 속 그림을 LangChain `LLMImageBlobParser` + 선택한 OpenAI 비전 모델(`OCR_MODEL`, `.env` 의 `OPENAI_API_KEY`)로 글로 바꿔 청크에 넣습니다.
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
- `gpt-5-mini` 는 추론 모델이라 `max_tokens`(= `max_completion_tokens`)에 추론 토큰이 포함됩니다. 답이 비면 값을 늘리거나 `reasoning_effort` 를 낮추세요.
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
  golden/                  골든 분할 final6 복사본 — 지금 03 평가셋은 쓰지 않음 (rag/validation/evidence.py 와 tests 용)
  eval_questions.yaml      직접 만든 평가 질문 세트 (지금 03 평가셋은 쓰지 않음)
  gold_dev.jsonl · gold_needle.jsonl   기존 골든 88문항 (03 평가셋 — 패키지 396문항과 함께)
data/Golden_Dev396_v12_Team_Package/   증강 Golden dev 396 패키지 (git 제외, ZIP 을 그대로 풂) — corpus/ (01) · data/data_list.csv (02) · data/golden_dev.jsonl (03)
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
  web/                     React + Vite 화면 (/api 는 server.py, /ocr-api 는 ocr_select/server.py 로 프록시; ocr.html 은 라벨링 화면)
  start.cmd · start.command  Windows · macOS 실행기
  ocr_select/              OCR 이미지 라벨링 — extract.py (그림 꺼내기) · server.py (API, 위 실행기가 8766 에 띄움) · merge.py (묶음 결과 합치기)
tests/test_smoke.py        게이트: rag/ 모든 모듈 import
artifacts/                 (커밋 안 함) 노트북 사이에 주고받는 파일
```

