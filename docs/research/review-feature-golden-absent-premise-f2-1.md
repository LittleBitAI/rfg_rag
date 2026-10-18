# Review research — F2, cycle 1

초안 문헌 메모다. 독립적으로 검증된 규칙이나 실제 데이터셋의 성능 보고서가 아니다. 이전 원문과 로컬 관측은 무시된 `artifacts/review-round2/originals/`에 보존한다.

## 일반 원리

표의 행과 병합 셀은 구조를 가진다. 문자를 기준으로 배치를 자르면 머리글이나 병합된 셀의 문맥이 없어질 수 있다. 스팬으로 연결된 행을 함께 보내고, 나눈 배치마다 필요한 머리글을 유지한다. 문자 겹침만으로 구조 보존을 입증하지 않는다.

## 공개 출처

- [공개 출처 1](https://docs.unstructured.io/open-source/core-functionality/chunking)
- [공개 출처 2](https://app.semanticdiff.com/gh/Unstructured-IO/unstructured/commit/615782a466f5e1b8a1e32183e133f8f9564fdb66)
- [공개 출처 3](https://docs.chonkie.ai/oss/chunkers/table-chunker)
- [공개 출처 4](https://www.anthropic.com/news/contextual-retrieval)
- [공개 출처 5](https://arxiv.org/abs/2307.03172v3)

## 적용과 검증

원문 질문·근거·문서 식별자와 실측값을 공개 예제로 재사용하지 않는다. 임시 폴더의 독립적인 합성 입력으로 실패와 정상 경로를 함께 재현한다. 형식·순서·소유권·부수 효과의 불변식을 검사하며 정확성 테스트를 실제 성능 측정으로 대체하지 않는다.

## Result

과거 데이터셋별 인용과 관측값은 공개본에서 제외했다. 이 페이지는 일반 원리와 재현 방법만 남긴 초안이며, 이전 실행을 검증된 규칙으로 제시하지 않는다.
