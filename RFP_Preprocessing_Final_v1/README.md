# 최종 개선 전처리 데이터셋 v1

**전달 판정: CONDITIONAL PASS.** 원본 HWP/PDF 98개 문서를 포함하며, 제가 작업한 전처리 데이터의 원문·검색 텍스트와 Native에서 원본 대응이 검증된 구조를 결합했습니다. 기존 Git Native 파서를 교체하거나 팀 코드를 수정하는 패키지가 아닙니다.

## 기존 Native와의 차이

기존 Git Native 전처리는 96/98문서를 처리했습니다. 최종 개선 전처리 데이터셋은 Native에서 실패한 캄보디아 AFSIS와 대전대학교 MILE HWP를 포함해 98/98문서를 유지합니다. 포함 여부와 전체 원본 충실도는 구분해야 하며, 두 문서 전체 표를 복원한 것은 아닙니다.

Native 성공 문서 중 **HWP 92개 문서에 표 구조 4,909개를 투영**했습니다. 이 중 **3,756개 표는 실제 격자·병합·셀 구조가 변경**됐으며, 1,153개는 구조가 같고 원본 주소가 보강됐습니다. 원본 SHA, HWP 구조 주소, 셀 좌표·내용, 전체 요소 대응 및 순서를 확인한 경우만 적용했습니다. 단순 부분문자열 대응으로 결합하지 않았습니다.

추가 제목·목차 확대는 하지 않았고 기존 검증 범위를 유지했습니다. Native 성공 PDF 4개는 이번 표 구조 확대 대상이 아닙니다. 원본 HWP/PDF 파일은 ZIP에 포함하지 않습니다.

## 파일별 용도

| 파일 | 용도 |
|---|---|
| final_records.jsonl | 21,902개 원본 대응 레코드. 원문·검색 텍스트와 출처 유지 |
| final_elements.jsonl | 26,023개 청커 입력 요소. 검증된 table.cells와 병합 구조 반영 |
| final_chunks.jsonl | 18,976개 청크. 동일 structural-7-uniform 결과, 최대 800토큰 |
| structure_mapping.jsonl | 원본 셀 주소·구조와 요소의 연결, 이전 표현 및 검증 근거 |
| preservation_audit.json | 정보 보존, 보호 해시 및 기존 개발셋 회귀 확인 |
| regression_results.csv | 이전 결합본과 최종본의 개발셋 지표 비교 |
| final_regression_trace.jsonl | 61문항의 순위·점수·패킹·quote·제외 사유 |
| manifest.json | 데이터 버전, 수량, 코드 SHA, 파일별 SHA-256 |
| adapter/ | 동결된 요소 변환 및 청크 재현, 독립 메모리 인덱스 연결 도구 |
| QUICK_START.md | 청크 직접 사용 / 요소 재청킹의 두 연결 방법 |
| known_limitations.md | 미검증 범위와 사용 제한 |
| handoff_summary.md | 담당자용 요약 |
| verify_package.py | Python 표준 라이브러리만으로 파일·SHA 검사 |

## 빠른 시작

압축을 풀고 `RFP_Preprocessing_Final_v1` 폴더로 이동합니다. Python 3.9 이상이 필요합니다.

```sh
python verify_package.py
```

먼저 PASS를 확인한 뒤 QUICK_START.md의 방법 A 또는 B를 선택하십시오. 필요한 팀원 코드·Python 의존성·토큰 캐시는 외부에 이미 준비돼 있어야 하며 자동 설치나 다운로드는 하지 않습니다.

## Retriever 연결 원칙

- Native 데이터와 최종 데이터를 같은 인덱스에 중복 색인하지 마십시오.
- **final_records.jsonl만 임의로 변환하지 마십시오. 검증된 표 구조는 final_elements.jsonl에 반영돼 있습니다.**
- 기존 팀원 Retriever/Chunker 코드는 수정하지 마십시오.
- 운영 DB, 인덱스 또는 active_run에 자동 등록하지 마십시오. 별도 테스트 환경만 사용합니다.
- chunk의 payload/body/spans/section_path/location 및 요소의 provenance를 유지하십시오.
- 문서별 source SHA→extraction ID 대응과 질문 scope는 독립 테스트 코드에서 명시하십시오. 이 패키지는 기존 운영 문서 UUID 등록을 자동 수행하지 않습니다.

## 검증 결과

문서 98 / 레코드 21,902 / 요소 26,023 / 청크 18,976. 원본 raw_text/search_text/ID/source SHA를 유지했습니다. 셀 텍스트 보존을 입증하지 못한 표 58개는 이전 검증 표현을 유지했습니다. 기존 제목 텍스트 8개는 chunk.body에 보존됐습니다.

고정 비교 조건은 structural-7-uniform, Kiwi BM25, Top20, 근거 상한 6, 문서측별 3,000토큰입니다. 기존 개발셋에서 검색 성능 유지와 성공 문항의 악화 없음을 확인했습니다.

| 개발용 회귀 질문 | Complete@20 | Packed Complete |
|---|---:|---:|
| Dev55 | 55/55 | 53/55 |
| 기존 6문항 | 6/6 | 5/6 |

이는 이미 개발에 사용한 질문의 회귀 결과이며 독립 일반화 성능이 아닙니다. **실제 검색 성능 향상과 LLM 답변 개선은 미검증**입니다. 요소·청크 재현 SHA 확인은 완료됐습니다. 이번 ZIP 제작에서는 새로운 검색·전처리 평가를 실행하지 않았습니다.

## 알려진 한계

원본 HWP 구조 레코드로 확인한 범위이며 전체 화면 검증이 아닙니다. Native와 텍스트 디코더 계보가 같다는 한계가 있습니다. 병합 셀 내용은 기존 청커가 여러 행에 반복하며 quote는 원본 격자 전체를 담지 못합니다. 실제 LLM, Dense/Hybrid 및 운영 DB 통합도 미검증입니다. 자세한 내용은 known_limitations.md를 함께 읽으십시오.
