# Review research — F5, cycle 1

초안 문헌 메모다. 독립적으로 검증된 규칙이나 실제 데이터셋의 성능 보고서가 아니다. 이전 원문과 로컬 관측은 무시된 `artifacts/review-round2/originals/`에 보존한다.

## 일반 원리

상태를 공유하지 않는 새 모델 세션에는 이전 요청의 문맥이 없다. 형식 오류 뒤 재시도할 때도 원래 finding과 수락 조건을 전달하고 반환된 연구가 그 finding을 다루는지 확인한다.

## 공개 출처

- [공개 출처 1](https://platform.claude.com/docs/en/build-with-claude/working-with-messages)
- [공개 출처 2](https://github.com/anthropics/claude-code/issues/43696)

## 적용과 검증

원문 질문·근거·문서 식별자와 실측값을 공개 예제로 재사용하지 않는다. 임시 폴더의 독립적인 합성 입력으로 실패와 정상 경로를 함께 재현한다. 형식·순서·소유권·부수 효과의 불변식을 검사하며 정확성 테스트를 실제 성능 측정으로 대체하지 않는다.

## Result

과거 데이터셋별 인용과 관측값은 공개본에서 제외했다. 이 페이지는 일반 원리와 재현 방법만 남긴 초안이며, 이전 실행을 검증된 규칙으로 제시하지 않는다.
