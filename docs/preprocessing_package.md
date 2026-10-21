# 전처리 패키지(v11 · v12) 사용

## 출처

v11 전처리 패키지와 이 폴더의 연동 아이디어 출처는 Se hui Hwang
([@hwangsiiii](https://github.com/hwangsiiii))입니다. 전처리 담당자의
[PR #12](https://github.com/LittleBitAI/rfg_rag/pull/12)와 별도로 전달받은
`RFP_Preprocessing_Final_v11_Team`, `RFP_v11_Retriever_Compatibility`,
`v11_retriever_연동테스트.ipynb`를 이번 통합의 출처로 명시합니다.
이 저장소의 로더·노트북 입력 전환 구현과 ⑤ 비교 실험은
[PR #18](https://github.com/LittleBitAI/rfg_rag/pull/18)에서 수행한 통합 작업입니다.

담당자가 만든 저장 청크와 이미 검증된 OCR 텍스트를 재파싱·재청킹 없이 검색에 사용하는
아이디어를 실제 파이프라인에 가져왔습니다. 01의 `load_package` → `save_chunks`가
`docs.jsonl`과 `chunks.jsonl`을 만들고, 이를 02 색인·검색 → 04 답변 생성 → 05 네 평가가 읽습니다.
NVIDIA L4 VM에서 이 경로를 실제 실행해 문서 98개·청크 18,984개로 고정 질문 16개를 평가했습니다.
현재 파서와의 네 CSV 전체 지표·비용·지연 시간 비교는 PR #18에 있습니다.

`load_package`는 두 형식을 읽습니다.

- v11 · v12 전처리 패키지(`final_chunks.jsonl` …): `load_v11_package`가 02 형식으로 옮깁니다.
- 이미 02 형식인 패키지(`chunks.jsonl` · `docs.jsonl`, 예: 증강 Golden dev 396 패키지의 `corpus/`): 그대로 읽고, `ocr_captions.jsonl`이 있으면 그림 설명 청크를 끝에 덧붙입니다.

## 반영 범위

전달 폴더 전체의 기능을 가져온 것은 아닙니다.

| 전달 자료·아이디어 | 이 저장소에 반영한 범위 |
| --- | --- |
| v11의 `final_chunks.jsonl` | `load_v11_package` 경로에서는 기존 청크 ID, `payload` → 검색용 `text`, `body` → 답변 근거, 섹션을 유지합니다. 현재 파서 경로의 청크 ID는 새로 만들어지므로 골든의 v11 ID를 그대로 쓸 수 없습니다. 본문 종류 `prose`는 저장소의 `text`로 바꾸고 다른 종류는 유지합니다. `[IMAGE]` 표시뿐인 8개 청크는 제외합니다. |
| `final_elements.jsonl`, `final_records.jsonl` | 문서 소속·NFC 파일명·제목·있는 쪽 번호·첫 레코드와 앞 세 레코드의 텍스트를 연결합니다. |
| 호환 패키지의 `adapt_v11.py` | `payload/body` 분리와 문서 메타데이터 연결 아이디어를 저장소의 작은 표준 라이브러리 로더로 구현했습니다. 어댑터 코드·전체 출력 파일은 복사하지 않았습니다. |
| 저장된 검증 OCR | 최종 청크에 들어 있는 검색 본문을 사용합니다. OCR 엔진과 미검증 OCR sidecar는 실행하거나 추가하지 않습니다. 패키지의 전체 정확성을 인증한 것은 아닙니다. |
| 구조·상세 출처 메타데이터 | 요구사항 소속(`requirement_key` · `requirement_ids`)과 표 연결(`table_refs`)은 청크 파일로 옮겨 02 검색이 씁니다 — 검색 글의 요구사항 머리말 · 요구사항 코드 정확 일치 · 연결 청크 함께 담기. 표 셀 구조, `spans`, `linked`, `image_source`, 이미지 SHA·검증 영역 등은 현재 출력과 생성 문맥에 전달하지 않습니다. 원래 패키지에 남아 있습니다. |
| Elements 인덱싱 대안 | 도입하지 않았습니다. Chunks만 색인하며 두 입력을 섞지 않습니다. |
| 호환 패키지의 검색 코드·E5 샘플 색인·연동 테스트 노트북 | 참고 자료입니다. 기관 CSV 라우팅 등 별도 검색 로직은 가져오지 않았고, 이 저장소의 KURE 검색 코드로 새 색인을 만들었습니다. |
| 패키지 사용·OCR 검증 노트북과 검증 영수증 | 출처 자료로 보관합니다. 이 저장소의 노트북에 복제하거나 패키지의 보존·OCR 검증을 다시 실행하지 않았습니다. |

따라서 이번 작업은 담당자의 전처리 결과와 청크 연결 아이디어를 실행 가능한 기존 파이프라인으로
통합한 것이며, 전달 폴더 전체 기능이나 상세 이미지·표 출처 전달까지 완료했다는 뜻은 아닙니다.

## 입력 전환 방법

1. 전처리 담당자에게 패키지를 받아 압축을 풉니다. `final_chunks.jsonl`, `final_elements.jsonl`, `final_records.jsonl`(또는 `chunks.jsonl` · `docs.jsonl`)이 바로 들어 있는 폴더를 `data/` 아래에 둡니다. 압축에 같은 이름의 폴더가 두 겹 있으면 안쪽 폴더를 사용하세요.
2. 패키지와 실행 결과(`data/`, `artifacts/`)는 git에 포함되지 않으므로 팀원과 VM에 별도로 전달해야 합니다.
3. `01_preprocessing.ipynb` 설정 셀에서 입력을 선택합니다. 기본값 `PREPROCESSED = None`은 `data/rfp.zip`을 현재 파서로 처리합니다. 패키지를 쓰려면 경로를 넣습니다.

   ```python
   PREPROCESSED = "data/RFP_Preprocessing_Final_v11_Team"
   ```

4. 01을 처음부터 실행하면 패키지의 저장된 OCR 텍스트와 청크를 읽어 `artifacts/docs.jsonl`, `artifacts/chunks.jsonl`로 저장합니다. 파싱·OCR·청크 재분할은 하지 않습니다. 본문이 `[IMAGE]` 표시뿐인 청크는 제외하고, 패키지에 쪽 번호가 없는 HWP는 `page = None`을 유지합니다.
5. 이후 02부터 다시 실행해 새 입력의 색인을 만드세요. 임베딩의 `max_seq_length` 기본값은 2048입니다.

## 현재 파서와 비교하기

03을 한 번 실행해 골든 dev 분할(`eval/golden/dev.jsonl`)과 `eval/eval_questions.yaml`로 만든 `eval_set.jsonl`의 질문을 두 입력에 똑같이 씁니다.
문서·청크 라벨은 입력에 종속되므로 입력을 바꾼 뒤 03을 다시 실행합니다. 골든 test 분할(`eval/golden/test.jsonl`)은 라벨 품질만 보고하며 검색·생성 비교에 쓰지 않습니다.
두 입력에 같은 질문 파일과 02 설정을 사용하고, 각각 02 → 04 → 05를 실행해 네 평가 CSV를 별도 보관합니다.
