# Review research — F1, cycle 1

초안 문헌 메모다. 독립적으로 검증된 규칙이나 실제 데이터셋의 성능 보고서가 아니다. 이전 원문과 로컬 관측은 무시된 `artifacts/review-round2/originals/`에 보존한다.

## 일반 원리

필드 존재 여부, 자료형, null 허용 여부는 서로 다른 제약이다. 저장 답변 전체를 파싱해 소비 가능한 형식으로 확정한 뒤 검색·심판·비용 합산·외부 전송을 시작한다. 잘못된 값은 정확한 필드 경로와 함께 거부하고 기본값으로 조용히 바꾸지 않는다.

## 공개 출처

- [공개 출처 1](https://json-schema.org/understanding-json-schema/reference/object)
- [공개 출처 2](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html)
- [공개 출처 3](https://docs.python.org/3.10/library/json.html)
- [공개 출처 4](https://docs.python.org/3.10/library/functions.html#bool)

## 적용과 검증

원문 질문·근거·문서 식별자와 실측값을 공개 예제로 재사용하지 않는다. 임시 폴더의 독립적인 합성 입력으로 실패와 정상 경로를 함께 재현한다. 형식·순서·소유권·부수 효과의 불변식을 검사하며 정확성 테스트를 실제 성능 측정으로 대체하지 않는다.

## Result

과거 데이터셋별 인용과 관측값은 공개본에서 제외했다. 이 페이지는 일반 원리와 재현 방법만 남긴 초안이며, 이전 실행을 검증된 규칙으로 제시하지 않는다.
