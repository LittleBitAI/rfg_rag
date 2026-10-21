# OCR — 저장 결과와 선택적 Vision 호출

## 엔진 선택

그림 유형(table · text · diagram)마다 기준 이미지에서 측정한 품질과 이미지당 비용으로 OCR 엔진을 고릅니다.

- 허용 엔진은 OpenAI API, OpenAI 호환 엔드포인트를 쓰는 Gemini API, 로컬 Windows PC의 별도 환경에서 실행하는 PaddleOCR-VL-1.5입니다.
- 유료 OCR 호출은 모두 `rag/usage.py`의 `record_usage`로 비용을 기록하고, PaddleOCR는 이미지당 실행 시간을 기록합니다.
- 벤치마크 첫 유료 호출과 전체 실행 전에는 모델별 토큰·단가 예상액을 보여 주고 승인을 기다립니다.
- 이번 비교에서 표·글은 Gemini, 도식은 GPT를 채택했고, 320개 이미지의 결과를 391개 위치로 저장했습니다. 측정값과 비용은 [OCR 비교 보고서](ocr_benchmark.md)에 있습니다.

## `OCR = False` (기본값) — 저장 결과 읽기

01은 `config.yaml`의 `paths.ocr_captions`(기본 논리 경로 `data/ocr_captions.jsonl`)를 공통 로더로 복원·해석한 뒤 그림 위치에 `[그림/도표 설명] …` 레코드를 넣습니다. 이 결과를 읽는 데 API 키나 호출은 필요 없습니다.

- HWP 본문 표시가 없는 그림은 문서 끝에, PDF 그림은 해당 쪽의 이미지 위 본문 다음에 들어갑니다.
- 기본 원본 입력(`PREPROCESSED = None`)에서는 설명 청크도 해당 위치에 넣고, 그림 경계에서 나뉜 짧은 본문도 유지합니다.
- 기본 캡션을 복원할 수 없으면 안내와 함께 멈추므로 설명이 조용히 빠지지 않습니다. 별도로 지정한 사용자 캡션 경로와 `OCR = True` 경로는 자동 복원 대상이 아닙니다. 01의 위치별 청킹도 복원 후의 실제 파일을 기준으로 결정합니다.
- `False`면 그림은 API로 가지 않습니다.

## `OCR = True` — Vision 모델 호출

`01_preprocessing.ipynb`의 `OCR = False`를 `True`로 바꾸면, 문서 속 그림을 LangChain `LLMImageBlobParser` + 선택한 OpenAI 비전 모델(`OCR_MODEL`, `.env`의 `OPENAI_API_KEY`)로 글로 바꿔 청크에 넣습니다.

- 저장 캡션 파일이 있어도 읽지 않고, 기존 Vision OCR·CRAFT 설정과 청크 분할 방식을 사용합니다.
- OCR 모델·추론 강도·출력/추론 토큰 한도의 기본값은 `config.yaml`의 `ocr` 구역에서 읽으며 01의 설정 셀에서 바꿀 수 있습니다.
- 여러 쪽에 반복되는 그림(로고 · 장식, `parsing.max_repeat_image_pages` 쪽 이상)은 청크에 넣지 않습니다. HWP는 아예 보내지 않고, PDF는 설명을 받은 뒤 반복된 설명을 뺍니다.

## CRAFT로 OCR 전에 이미지 선별하기

CRAFT는 글자를 읽는 OCR이 아니라, 글자가 있을 법한 영역을 찾는 탐지기입니다. CRAFT를 켜면 그림을 먼저 살펴본 뒤 후보만 기존 OpenAI Vision OCR에 보냅니다. 기존 Vision 모델과 응답 형식은 유지합니다. 자세한 구현 범위는 [CRAFT 선별 안내](craft_ocr_selection.md)를 참고하세요.

### 1. 필요한 파일 준비

- 설치 절차대로 `python -m pip install -r requirements.txt`를 실행합니다. 선별 기능은 `easyocr==1.7.2`, 기존 `torch`, `pillow`를 사용합니다. 실제 글자 인식은 OpenAI Vision이 담당하며 EasyOCR의 문자 인식기는 로드하지 않습니다.
- 사전에 확보한 `craft_mlt_25k.pth`를 `models/easyocr/`에 둡니다. 코드가 모델을 자동 다운로드하지 않습니다. 모델 파일·이미지·캐시는 Git이나 PR에 넣지 마세요. 저장소 최상위 폴더를 작업 폴더로 사용합니다.

### 2. 두 스위치 설정

| 노트북 `OCR` | `parsing.craft.enabled` | 실제 동작 |
|---|---|---|
| `False` | 어느 값이든 | 그림을 Vision에 보내지 않으며 CRAFT 선별도 실행하지 않음 |
| `True` | `false` — 기본값 | 기존 Vision OCR 경로 사용 |
| `True` | `true` | CRAFT로 먼저 선별한 후보만 Vision OCR에 전달 |

활성화하려면 `01_preprocessing.ipynb`의 `OCR = False`를 `OCR = True`로 바꾸고, `config.yaml`의 기존 `parsing.craft` 항목을 다음과 같이 설정합니다. 같은 항목을 두 번 추가하지 마세요.

```yaml
parsing:
  # 기존 parsing 설정은 그대로 둡니다.
  craft:
    enabled: true
    model_dir: models/easyocr
    cache_dir: artifacts/ocr_detector
    review_queue: artifacts/ocr_review.jsonl
```

끄려면 `enabled: false`로 되돌립니다. 다른 설정은 유지합니다. 이후 `01_preprocessing.ipynb`를 실행합니다. 코드 변경 후에는 커널을 재시작하세요. `OCR = True`에서는 후보 이미지의 Vision 호출에 API 키와 비용이 필요합니다.

### 3. ON일 때 처리 흐름

`문서 속 이미지 → CRAFT 영역 탐지 → 상태 판정 → 후보만 기존 Vision OCR`

| 상태 | 뜻 | 처리 |
|---|---|---|
| `OCR_CANDIDATE` | 글자처럼 보이는 영역이 탐지됨 | 기존 Vision OCR에 전달 |
| `REVIEW_REQUIRED` | 글자 여부가 불확실하거나 처리 오류가 있음 | 자동 OCR하지 않고 검토 큐에 기록 |
| `OCR_UNNECESSARY` | 이미지 전체 픽셀이 균일해 보이는 정보가 없음 | OCR에서 제외 |

- 탐지 영역이 없거나 점수가 낮다는 이유만으로 불필요하다고 판정하지 않습니다. 표·도식의 작은 글자도 놓칠 수 있으므로 불확실하면 검토 대상으로 남깁니다.
- CRAFT ON에서는 HWP 반복 이미지도 반복 횟수만으로 삭제하지 않고, 각 발생 위치를 기록하면서 같은 이미지의 Vision 결과를 재사용합니다. PDF의 기존 반복 설명 정리 동작은 유지합니다.

### 4. 검토 큐와 출처 확인

- `artifacts/ocr_review.jsonl`을 텍스트 편집기로 엽니다. 한 줄이 한 번의 이미지 발생에 대한 검토 항목입니다. `classification`, `reason`, `source`, `location`으로 상태·사유·원본 문서·위치를 확인합니다. 검토가 끝나도 이 목록이 자동으로 OCR되거나 검색 본문에 반영되지는 않습니다.
- 모든 선별 판정은 기본 경로 `artifacts/ocr_selection.jsonl`에 저장됩니다. 이 파일은 `cache_dir`의 상위 폴더에 만들어집니다. 검토 큐와 판정 기록은 실행할 때 덧붙이므로 재실행 항목이 중복될 수 있습니다.
- HWP: 문서 SHA, 추출 이미지명, 본문 마커 문자 위치를 기록합니다. 원본 바이너리 record나 페이지 번호를 추정하지 않습니다.
- PDF: 문서 SHA, 페이지, 이미지 번호, xref, 배치 사각형을 기록합니다.

### 5. 캐시와 오류 처리

- CRAFT 탐지 결과는 `artifacts/ocr_detector/`에 저장합니다. 이미지 raster SHA, CRAFT 모델 SHA, 탐지 설정, EasyOCR 버전이 같으면 재사용합니다. 이 중 하나가 바뀌면 이전 결과를 재사용하지 않고 해당 탐지를 다시 수행합니다. 기존 OCR 결과와 승인 데이터는 변경하지 않습니다.
- `parsing.craft.settings`로 탐지 설정을 바꿀 수도 있습니다. 이번 검증은 코드의 기본 설정을 사용했으며 설정을 바꾸면 별도 확인이 필요합니다.
- CRAFT 캐시는 Vision 응답의 영구 캐시가 아닙니다. HWP의 같은 이미지에 대한 Vision 응답 재사용은 한 번의 문서 처리 안에서 이루어집니다.
- 모델 부재, 탐지 실패, 지원하지 않는 형식, 이미지 디코딩 실패는 `REVIEW_REQUIRED`로 기록합니다. 해당 이미지를 자동으로 불필요 처리하거나 Vision에 우회 전송하지 않습니다.

### 6. 검증 범위와 주의사항

- 외부 API를 차단한 합성 테스트로 상태별 안전한 전달과 검토 보존을 검사합니다. 실제 이미지나 과거 분류 식별자를 fixture로 사용하지 않습니다.
- CRAFT는 사진·로고·표의 의미를 판단하는 분류기가 아닙니다. 작은 글자·스타일 문자·체크기호를 놓칠 수 있고, 일반 사진의 분류 성능은 아직 미검증입니다.
- **OCR 정확도 향상이나 비용 절감을 검증한 결과가 아니며, 실제 운영 환경 검증도 완료되지 않았습니다.** 검토 큐를 승인된 검색 데이터로 사용하지 마세요.
