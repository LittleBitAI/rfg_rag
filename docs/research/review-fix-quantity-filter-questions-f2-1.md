# Review research — F2, cycle 1

초안 문헌 메모다. 독립적으로 검증된 규칙이나 실제 데이터셋의 성능 보고서가 아니다. 이전 원문과 로컬 관측은 무시된 `artifacts/review-round2/originals/`에 보존한다.

## 일반 원리

표의 구조와 값 추출 성공 여부는 별개다. 값이 비어도 열 위치와 기존 단위를 유지하고, 개행이나 생략된 경계 파이프를 새로운 값 칸으로 세지 않는다. 소계와 전체 합계를 독립적으로 작성한 합성 표에서 구분한다.

## 공개 출처

- [공개 출처 1](https://docs.python.org/3.10/library/stdtypes.html#str.splitlines)
- [공개 출처 2](https://docs.python.org/3.10/library/re.html#regular-expression-syntax)
- [공개 출처 3](https://github.github.com/gfm/#tables-extension-)
- [공개 출처 4](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/organizing-information-with-tables)

## 적용과 검증

원문 질문·근거·문서 식별자와 실측값을 공개 예제로 재사용하지 않는다. 임시 폴더의 독립적인 합성 입력으로 실패와 정상 경로를 함께 재현한다. 형식·순서·소유권·부수 효과의 불변식을 검사하며 정확성 테스트를 실제 성능 측정으로 대체하지 않는다.

## Result

과거 데이터셋별 인용과 관측값은 공개본에서 제외했다. 이 페이지는 일반 원리와 재현 방법만 남긴 초안이며, 이전 실행을 검증된 규칙으로 제시하지 않는다.
