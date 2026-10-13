# 빠른 연결 안내

## 공통 준비

1. ZIP을 풀고 `RFP_Preprocessing_Final_v1` 폴더에서 명령을 실행합니다.
2. Python 3.9 이상으로 `python verify_package.py`를 실행해 PASS를 확인합니다.
3. DB·active_run을 사용하는 운영 프로젝트가 아닌 독립 테스트 폴더를 준비합니다.
4. 팀원 수정 코드의 `src/` 사본을 외부 경로에 둡니다. 필요한 기존 의존성이 설치된 Python 환경을 사용합니다. 팀 코드·패키지·토큰 캐시는 ZIP에 없으며 자동 설치/다운로드하지 않습니다.

아래 `../team_project_copy/src`와 `../tokenizer-cache`는 **경로 예시**입니다. 실제 기존 코드 사본과 캐시 위치로 바꾸십시오. `python`은 해당 기존 의존성이 설치된 환경의 Python으로 바꾸거나 그 환경을 활성화해야 합니다.

## 방법 A: 저장된 청크로 독립 테스트 인덱스 구성

필요 파일: `final_chunks.jsonl`, `final_elements.jsonl`, `manifest.json`, `verify_package.py`, `adapter/build_memory_index.py`.

외부 의존성: 동일한 팀원 수정 코드 전체 `src/`, 해당 프로젝트의 기존 의존성(예: kiwipiepy, rank_bm25 및 코드가 import하는 모듈). 청킹을 다시 하지 않으므로 청킹용 토큰 캐시는 이 도구에서 필요하지 않습니다. Kiwi 모델은 로컬에 준비돼 있어야 합니다. 운영 DB는 필요하지 않습니다.

```sh
python -B adapter/build_memory_index.py --team-src ../team_project_copy/src
```

이 도구는 저장된 chunk.payload를 Kiwi 토큰화해 **기존 KeywordIndex/BM25Okapi 구현으로 메모리 인덱스만 구성**합니다. 검색 질문·평가·LLM 호출은 실행하지 않습니다. DB 연결이나 KeywordIndex.load()도 사용하지 않습니다. 네트워크는 차단하며 의존성이 없으면 중단합니다. 프로세스가 끝나면 인덱스는 해제됩니다.

같은 프로세스에서 인덱스를 사용하려면 독립 테스트 스크립트에서 다음 helper를 호출하십시오.

```python
from adapter.build_memory_index import build_index
index, analyzer = build_index("../team_project_copy/src")
# 이후 기존 retrieve() 호출은 담당자의 별도 테스트 코드에서 연결합니다.
```

문서명·기관 scope terms를 사용하는 비교에는 기존에 검증한 별도 scope 파일도 필요합니다. 이 ZIP에는 포함되지 않습니다. 있는 경우 다음처럼 명시적으로 전달합니다.

```sh
python -B adapter/build_memory_index.py --team-src ../team_project_copy/src --scope-terms ../test_inputs/scope_terms.json
```

scope 파일 없이 생성된 인덱스는 과거의 scope 설정을 재현한 것으로 간주하지 마십시오. query의 문서 UUID/source SHA, Top20, unit_limit=6 및 문서측별 3,000토큰은 담당자의 테스트 코드에서 명시해야 합니다. 이 패키지는 서비스나 운영 인덱스 등록 명령을 제공하지 않습니다. 이 helper는 이번 패키징에서 실행 평가하지 않았으며 보존된 인덱스 구성 호출 경로를 바탕으로 작성했습니다.

## 방법 B: 요소에서 기존 청커로 청크 재생성

필요 파일: `final_elements.jsonl`, `final_chunks.jsonl`(기대 SHA 확인용), `manifest.json`, `adapter/rebuild_chunks.py`.

외부 의존성: 동일한 팀원 수정 코드 전체 `src/`, 해당 코드의 기존 import 의존성 및 tiktoken, 로컬 `o200k_base` 토큰 캐시. 팀 코드 SHA가 다르면 중단합니다. 캐시가 없으면 설치/다운로드하지 말고 담당자에게 준비를 요청하십시오.

```sh
python -B adapter/rebuild_chunks.py --team-src ../team_project_copy/src --token-cache ../tokenizer-cache --output ./local_test/rebuilt_chunks.jsonl
```

이 명령은 extraction_id별 요소를 원래 순서로 묶어 기존 `build_profile(..., "structural")`을 호출합니다. 해당 코드 버전은 structural-7-uniform입니다. 생성된 청크 SHA가 패키지의 final_chunks SHA와 일치해야 PASS입니다. 기존 파일을 덮어쓰지 않으므로 output이 이미 있으면 새 경로를 사용하십시오. 검색·인덱스 등록·LLM 호출은 하지 않습니다.

`final_elements.jsonl`의 table.cells에는 검증된 row/col/rowspan/colspan이 있습니다. 다른 어댑터로 다시 변환하거나 코드/하이퍼파라미터를 바꾸면 이 재현 조건과 달라집니다. 재생성 후 청크 사용은 방법 A와 동일하게 별도 테스트 코드에서 연결합니다.

## 선택 사항: 동결 어댑터 재현

외부 패키지 없이 ZIP 내부 기준 요소와 전후 패치를 통해 최종 요소를 재생성합니다. 내부 기술 파일명은 원래 참조를 유지합니다.

```sh
python -B adapter/reproduce_elements.py --output ./local_test/reproduced_elements.jsonl
```

원본 문서를 새로 파싱하는 범용 어댑터가 아닙니다. 패키지 내부의 `adapter/baseline_stage11_elements.jsonl`과 `adapter/patches.jsonl`에서 동결된 변환만 재현합니다.

## 중단해야 하는 경우

파일 검증 실패, 코드 SHA 불일치, 필요한 기존 환경/캐시 부재 시 운영 환경으로 대체하지 마십시오. Native와 최종 데이터를 함께 중복 색인하지 말고, final_records만 임의 변환하지 마십시오. 실제 검색 성능 향상·Generation 개선을 검증한 패키지는 아닙니다.
