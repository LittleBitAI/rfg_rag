# Kiwi BM25 비교 절차

공백 분할과 현재 Kiwi 규칙의 기여를 같은 BM25 매개변수에서 비교한다. 사전과 입력을 먼저 고정하고 패킹 전 순위와 패킹 후 근거 커버리지를 구분한다. 코드 승격과 수량 필터가 있는 통합 경로는 순수 순위 비교와 별도로 보고한다. 운영 토크나이저를 바꿀 때는 새 색인을 격리 구축하고 [롤백 절차](index_rollback.md)를 준비한다.

## 기록 보관

This page describes the procedure. Earlier report originals remain in ignored `artifacts/review-round2/originals/`. Actual questions, answers, evidence text, and dataset records must remain private. Aggregate counts, quality scores, latency, resource usage, and reports discussing those measurements may be published without the underlying records. This procedure page alone does not establish a measured winner.
