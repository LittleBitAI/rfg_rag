# Review research — F6, cycle 1

초안 문헌 메모다. 독립적으로 검증된 규칙이나 실제 데이터셋의 성능 보고서가 아니다. 이전 원문과 로컬 관측은 무시된 `artifacts/review-round2/originals/`에 보존한다.

## 일반 원리

CSV 헤더 누락, 짧은 행의 빈 값, 넘치는 열과 인코딩 오류는 서로 다른 실패다. 소비 전에 전체 파일을 신뢰 가능한 형태로 파싱하고, 완전한 입력만 측정된 사람 검토로 집계한다.

## 공개 출처

- [공개 출처 1](https://docs.python.org/3/library/csv.html)
- [공개 출처 2](https://docs.python.org/3.10/library/functions.html)
- [공개 출처 3](https://lexi-lambda.github.io/blog/2019/11/05/parse-don-t-validate/)
- [공개 출처 4](https://github.com/denoland/deno_std/pull/3143)
- [공개 출처 5](https://cgit.adelielinux.org/packages/tree/user/py3-docutils/py311-test.patch)

## 적용과 검증

원문 질문·근거·문서 식별자와 실측값을 공개 예제로 재사용하지 않는다. 임시 폴더의 독립적인 합성 입력으로 실패와 정상 경로를 함께 재현한다. 형식·순서·소유권·부수 효과의 불변식을 검사하며 정확성 테스트를 실제 성능 측정으로 대체하지 않는다.

## Result

과거 데이터셋별 인용과 관측값은 공개본에서 제외했다. 이 페이지는 일반 원리와 재현 방법만 남긴 초안이며, 이전 실행을 검증된 규칙으로 제시하지 않는다.
