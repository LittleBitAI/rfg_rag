# 리뷰 조사 · F1, 1회차

집계 결과와 측정 조건은 Git에 보관하고, 실제 질문·정답·근거·OCR 텍스트와 레코드별 내보내기는 Git에서 제외된 로컬 `artifacts/`에 보관합니다.

복원 출처: 정리 전 `artifacts/review-round2/originals/` 또는 `d7d1682^`. 아래 수치와 검증 기록은 당시 실행에서 관측한 과거 기록이며, 이번 작업에서 다시 측정한 결과가 아닙니다.

PR #57 리뷰 2회차의 수정 전에 2026-10-16에 쓴 조사 초안입니다. 검증된 사실이나 공용 규칙이 아니며, 리뷰는 이 문서를 수정과 함께 읽습니다.

## 문제

F1은 저장된 답변 파일을 읽는 단계와 평가에 돈을 쓰는 단계 사이의 경계 문제입니다. 유료 채점 두 가지가 시작되기 전에 모든 행은 구조가 온전해야 하고, 평가가 쓸 수 있는 값을 담고 있어야 합니다. 지금은 `rewrite.cost_usd=null`인 행이 `_read_answers`를 통과하고, `evaluate_end_to_end`가 `_ragas`를 부른 뒤에야 답변 비용과 질문 다듬기 비용을 더하다가 실패합니다. 검사기는 키가 있는지와 일부 컨테이너 모양만 확인하고, 값의 자료형은 확인하지 않습니다. [C1, C2, C3]

발생: 반복, 1·2회차.

- [P1] [P1] rag/evaluation/evaluation.py:218 — 키가 있는지만 검사해, 안쪽 값이 잘못된 행도 유료 호출까지 갑니다

## 실패한 수정

- 1회차에 설명된 구현은 최상위 키가 있는지만 확인했습니다. `rewrite`라는 키는 있으므로 `rewrite={}`를 받아들였지만, End-to-End 평가는 나중에 그 안의 토큰·비용 필드를 필요로 했습니다. PR diff도 원래의 최상위 키 검사를 확인해 줍니다. [C2]
- 지금 코드에 보이는 수정은 필수 하위 키, 딕셔너리·리스트 검사, 행·항목별 오류 경로를 더했습니다. 테스트는 필수 키를 지우거나 하위 컨테이너를 null로 바꿉니다. 그러나 `_missing_record_fields`는 여전히 각 키가 있는지만 확인합니다. 키가 있으면 값은 검사하지 않으므로 `rewrite.cost_usd=null`이 같은 유료 호출 경계까지 갑니다. 받은 2회차 리뷰가 이 남은 경우를 보고했고, 두 번째 수정 패치는 보고되지 않았습니다. [C2, C3, C4]

## 출처

### S1 — JSON Schema — object

- URL: https://json-schema.org/understanding-json-schema/reference/object
- 확인일: 2026-10-16
- 위치: Required Properties, 특히 email 값이 null인 예시
- 인용: “In JSON a property with value `null` is not equivalent to the property not being present.”
- 적용: 디코딩한 값이 None이어도 `rewrite.cost_usd` 키는 있습니다. 필수 키 검사만으로는 숫자 자료형을 보장할 수 없습니다.
- 반대 근거: 이 구분이 null을 모두 금지하라는 뜻은 아닙니다. null 허용 여부는 각 필드의 자료형이 정합니다.
- 검증: 숫자 키가 없는 경우, 숫자 키에 null이 든 경우, 일부러 null을 허용하는 라벨을 구분합니다.

### S2 — OWASP — Input Validation Cheat Sheet

- URL: https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html
- 확인일: 2026-10-16
- 위치: Input Validation Strategies; Implementing Input Validation
- 인용: “Validate both syntax (the expected type and format) and semantics (whether the value makes sense for the operation).”
- 적용: 저장된 답변 기록은 유료 처리 전에 받는 쪽에서 안쪽 값까지 검사해야 합니다.
- 반대 근거: 일반적인 검사 지침일 뿐, 이 프로젝트의 숫자 범위를 정하거나 보안 기반 시설을 더하라는 지시가 아닙니다.
- 검증: 잘못된 값은 채점 호출 전에 거부하고, 정당한 예외 값은 계속 받아들여야 합니다.

### S3 — Python 3.10 — json encoder and decoder

- URL: https://docs.python.org/3.10/library/json.html
- 확인일: 2026-10-16
- 위치: JSONDecoder 기본 변환표; Infinite and NaN Number Values
- 인용: “null | None”; “Despite that, by default, this module accepts and outputs `Infinity`, `-Infinity`, and `NaN` as if they were valid JSON number literal values:”
- 적용: JSON 디코딩은 null을 그대로 두고, 기본 설정에서는 유한하지 않은 숫자도 받아들입니다. 파싱만으로는 비용 값을 검사할 수 없습니다. 바로 앞 문서는 RFC가 이런 표현을 허용하지 않는다고 분명히 적습니다.
- 반대 근거: 디코더 설정을 바꾸면 기본 동작이 달라질 수 있습니다. 이 저장소의 읽기 함수는 그런 설정 없이 `json.loads`를 씁니다.
- 검증: 대표 입력을 실제 JSONL 읽기 함수로 읽은 뒤, 받는 쪽 검사기가 잘못된 비용 값을 거부하는지 확인합니다.

### S4 — Python 3.10 — bool

- URL: https://docs.python.org/3.10/library/functions.html#bool
- 확인일: 2026-10-16
- 위치: Built-in Functions, bool
- 인용: “The bool class is a subclass of int”
- 적용: `isinstance(value, int)`나 `isinstance(value, (int, float))`만으로 검사하면 JSON 참·거짓 값도 비용 숫자로 받아들입니다.
- 반대 근거: 참·거짓 값으로 계산하는 것은 파이썬에서 정상입니다. 여기서 빼는 이유는 받는 필드의 뜻 때문입니다.
- 검증: 숫자 필드 테스트에서는 참·거짓 값을 분명히 거부하고, 참·거짓 필드에서는 받아들입니다.

### S5 — 평가 읽기 함수와 유료 호출 순서

- URL: rag/evaluation/evaluation.py
- 확인일: 2026-10-16
- 위치: 200–247행과 285–310행; 원래·현재 읽기 함수는 PR diff 839–889행
- 인용: return [f"{prefix}.{field}" for field in fields if field not in record]
ragas = _ragas(rows, [FactualCorrectness()], cfg, "end_to_end")
"cost_usd": r["cost_usd"] + r["rewrite"]["cost_usd"]
- 적용: 맨 끝 값은 키가 있는지만 검사하고, 계산은 채점이 끝난 뒤에 한다는 직접 증거입니다. `_read_answers`는 행을 돌려주기 전에 파일 전체를 훑습니다.
- 반대 근거: 빠진 필드와 일부 잘못된 컨테이너는 이미 채점 전에 실패합니다. 남은 결함은 값을 검사하지 않는 것입니다.
- 검증: 모의 채점 호출이 'TypeError 전에 호출됨'에서 '정확한 검사 오류와 함께 한 번도 호출되지 않음'으로 바뀌어야 합니다.

### S6 — 사용량·평가 회귀 테스트

- URL: tests/test_usage.py
- 확인일: 2026-10-16
- 위치: 192–206행, 237–242행, 274–325행
- 인용: del record[key]
write_jsonl([_answer_row(), row], answers)
calculate.assert_not_called()
("rewrite", None), ("retrieval_settings", None), ("ranked_candidates", None), ("evidence", None)
- 적용: 기존 거부 테스트는 키의 유무와 컨테이너를 바꿉니다. 두 행을 쓰고 유료 호출이 없는지 보는 유용한 틀을 주지만, 맨 끝 단일 값은 바꾸지 않습니다.
- 반대 근거: 이 테스트들은 정상 동작과 원래의 키 누락 실패를 다룹니다. 빈틈은 빠진 입력 종류이지, 쓸모 있는 검사가 없다는 뜻이 아닙니다.
- 검증: 같은 틀을 단일 값 자료형으로 넓히고, 모의 채점의 정상 비용 결과는 그대로 둡니다.

### S7 — 사용량 기록과 비용 계산

- URL: rag/usage.py
- 확인일: 2026-10-16
- 위치: record_usage, 16–37행
- 인용: "cost_usd": ((tokens["prompt_tokens"] - cached) * usd_in + cached * usd_cached
             + tokens["completion_tokens"] * usd_out) / 1e6
- 적용: 보통의 사용량 기록은 비용을 숫자로 계산합니다. 잘못 저장된 비용을 받아들였다고 해서 대신 쓸 금액을 지어내 고쳐서는 안 됩니다.
- 반대 근거: 기록하는 쪽의 동작은 나중에 평가가 읽는 저장 파일을 검사해 주지 않습니다.
- 검증: 정상 기록 비용과 합계는 그대로 두고, 잘못 저장된 비용 값은 거부합니다.

### S8 — 검색 후보 만들기

- URL: rag/retrieval/retrieval.py
- 확인일: 2026-10-16
- 위치: _candidate_snapshot과 _rank, 86–114행
- 인용: "dense_score": dense_raw.get(i), "dense_rank": dense_ranks.get(i),
"bm25_score": sparse_raw.get(i), "bm25_rank": sparse_ranks.get(i)
- 적용: 한쪽 검색에서 나오지 않은 후보는 그 검색의 점수와 순위가 null인 것이 정상입니다.
- 반대 근거: 특정 검색 필드에만 null을 허용한다는 뜻이며, 합친 순위나 비용 값까지 허용하는 것은 아닙니다.
- 검증: 한쪽 검색에 없는 정상 후보는 새 검사를 그대로 통과해야 합니다.

### S9 — 검색 지표의 라벨 제외 테스트 데이터

- URL: tests/test_ir_metrics.py
- 확인일: 2026-10-16
- 위치: 30–38행과 56–90행
- 인용: unmapped = {**full, "id": "unmapped", "evidence": [{"doc_id": None, "chunk_id": None}]}
yaml = {**full, "id": "yaml", "primary_topic": None, "evidence": []}
- 적용: null 근거 라벨, null 주제, 빈 근거는 평가가 지원하는 상태입니다. 공용 답변 테스트 데이터도 `trace_id=None`을 씁니다.
- 반대 근거: 이런 의도된 예외가 있다고 모든 필드가 null일 수 있다는 뜻은 아닙니다.
- 검증: 일부 라벨, 라벨 없음, 답할 수 없음, YAML 제외 동작이 새 검사 뒤에도 남아야 합니다.

### S10 — 저장소의 평가 규칙과 구현 제한

- URL: AGENTS.md
- 확인일: 2026-10-16
- 위치: 1·5·6절, 특히 141–148행
- 인용: “05 rejects incomplete answers before any paid call.” “It retains the old answers and clears trace IDs; score that file only for Retrieval.”
- 적용: 유료 호출 전 규칙, 검색만 다시 돌릴 때 trace ID를 지우는 정상 동작, 구현을 좁고 읽기 쉽게 두라는 요구를 정합니다.
- 반대 근거: 규칙은 검사 라이브러리나 단일 값 범위 전체를 정하지 않습니다.
- 검증: 오프라인 거부 테스트로 채점 호출 0회를 확인하고, 구현 뒤 필수 린트와 테스트를 통과해야 합니다.

### S11 — JSONL 저장·읽기 경계

- URL: rag/config.py
- 확인일: 2026-10-16
- 위치: write_jsonl과 read_jsonl, 24–32행
- 인용: return [json.loads(line) for line in f if line.strip()]
- 적용: 실제 읽기 함수는 앱별 자료형 검사 없이 기본 JSON 디코딩을 씁니다.
- 반대 근거: JSON 문법이 틀리면 디코딩에서 이미 실패합니다. F1은 문법은 맞지만 값이 부적절한 기록의 문제입니다.
- 검증: 인위적인 딕셔너리를 함수에 바로 넘기지 말고 write_jsonl/read_jsonl로 재현합니다.

## 주장

- C1 (출처; S10): 지켜야 할 규칙은 유료 평가 호출 전에 불완전한 답변 파일을 거부하는 것입니다.
- C2 (출처; S5): PR의 기준 코드는 최상위 키만 검사했습니다. 지금의 수정 코드는 하위 키와 컨테이너 검사를 더했지만 맨 끝 값은 여전히 검사하지 않습니다.
- C3 (해석; S5, S11, S3): 키는 있고 값이 null인 질문 다듬기 비용이 지금의 읽기 함수를 통과해 End-to-End 채점까지 간 뒤에야 비용 덧셈에서 실패합니다.
- C4 (출처; S6): 기존 거부 테스트는 빠진 키와 잘못된 하위 컨테이너를 다루고, 단일 값 변형은 다루지 않습니다.
- C5 (해석; S1, S2, S5, S6, S10): 오래 갈 수정은 이미 공용으로 쓰는 읽기 함수에서 파일 전체 값을 받는 쪽 규칙으로 검사하고, 정확한 거부 경로와 명시적인 null 허용을 유지하는 것입니다.
- C6 (출처; S1): JSON 필드가 있는지와 null 값을 받아들이는지는 서로 다른 조건입니다.
- C7 (출처; S2): 검사는 기대하는 자료형·형식과 함께 그 작업에 맞는 값인지도 다뤄야 합니다.
- C8 (해석; S3, S11): 저장소의 기본 JSON 디코딩은 null을 None으로 바꿀 뿐 필드가 유효한지는 확인하지 않습니다.
- C9 (해석; S3, S4, S7, S11): 숫자 허용 규칙은 참·거짓 값과 유한하지 않은 비용 값을 빼고, 보통의 정수·실수·0 비용은 받아들여야 합니다.
- C10 (해석; S6, S8, S9, S10): 한쪽 검색에 없는 점수·순위, 라벨 없는 근거, null 주제, 없는 trace ID는 지원하는 상태이므로, null 허용은 필드마다 따로 정해야 합니다.
- C11 (해석; S5, S6, S10): 일반 스키마 프레임워크, 추가 메타데이터 거부, 관계없는 일관성 규칙 없이도 좁은 검사기로 규칙을 지킬 수 있습니다.
- C12 (해석; S6, S7): 보통의 비용 계산은 숫자 비용을 만들고, 기존 모의 채점 테스트는 합계 비용 0.000101을 유지합니다. 증거가 보여 주는 것은 잘못된 파일이 들어올 수 있다는 위험이지, 기록하는 쪽의 결함이나 실제 과금이 관측됐다는 것이 아닙니다.

## 핵심 원리

필드가 있는지, 필드의 자료형, null 허용은 서로 다른 조건입니다. JSON Schema는 null인 필드와 없는 필드를 분명히 구분합니다. OWASP는 문법 검사와 그 작업에 맞는 값인지의 검사를 구분합니다. 파이썬 디코딩은 JSON null을 None으로 남기므로, 파싱이 성공했다고 계산에 쓸 수 있는 값이라는 뜻은 아닙니다. 그래서 필수 하위 키를 더하는 것만으로는 유료 호출 전 조건을 지킬 수 없습니다. [C6, C7, C8]

## 적용

규칙은 네 평가와 검색만 다시 돌리기가 이미 함께 쓰는 `_read_answers`에 둡니다. 어느 채점이든 부르기 전에 모든 행을 검사하며, 정상 행 뒤에 오는 마지막 잘못된 행도 포함합니다. `ANSWER_FIELDS`와 하위 필드 목록에서 이미 요구하는 필드를 다룹니다. question·reference·answer와 식별자는 문자열, contexts·key_facts·context_chunk_ids는 알맞은 문자열 항목을 담은 리스트, answerable과 stored_rewrites_reused는 참·거짓 값, 최상위와 질문 다듬기의 토큰 수는 정수, 비용과 지연 시간은 숫자, rewrite.question과 retrieval_settings.chunk_file은 문자열, 검색 설정과 후보 순위·점수는 실제 숫자 자료형, 근거·후보 항목은 맨 끝 값의 자료형이 정해진 기록이어야 합니다. 숫자 판정에서는 참·거짓 값을 뺍니다. 비용은 0과 정수·실수 표현을 모두 받아들이고, 유한하지 않은 비용은 쓸 수 없는 합계를 조용히 만들지 않도록 거부합니다. 필드별 예외가 꼭 필요합니다. trace_id, primary_topic, 근거 라벨은 null일 수 있고, 한쪽 검색에 없는 의미 검색·BM25 점수와 순위도 null일 수 있습니다. 기존 동작이 허용하는 곳에서는 빈 근거, 빈 후보·문맥 리스트도 그대로 쓸 수 있어야 합니다. model, sources, rewrite.latency_s 같은 기존 추가 메타데이터는 계속 받아들입니다. 이것들은 구현할 때 기록하는 쪽과 맞춰 볼 받는 쪽 규칙의 제안이며, 스키마 라이브러리나 관계없는 필드 간 제약을 들이라는 지시가 아닙니다. [C5, C9, C10, C11]

## 가설

첫 수정은 '빠짐없음'을 뒤에서 쓰는 값의 규칙이 아니라 필수 키 목록으로 다뤘습니다. 검사의 깊이는 늘렸지만 검사의 뜻은 넓히지 않았습니다. 좁은 수정은 `_read_answers`가 어떤 행이든 돌려주기 전에 파일 전체에서 필수 값의 자료형, 하위 모음의 항목, 필드별 null 허용을 검사하게 하는 것입니다. 정확한 필드 경로로 거부하는 동작은 유지하고, 잘못된 행을 조용히 바꾸거나 기본값을 넣거나 건너뛰지 않습니다. [C5]

## 반대 근거

- 첫 수정도 경계를 개선했습니다. 빠진 하위 키와 잘못된 하위 컨테이너는 이제 채점 전에 ValueError를 냅니다. 파일 전체를 훑는 동작과 행·항목 경로는 쓸모가 있으니 유지해야 합니다. [C2, C4]
- `record_usage`는 숫자 비용을 계산하고, 보통의 테스트 데이터도 숫자 비용을 담습니다. 보통의 기록이 null 비용을 내거나 이 경우로 실제 과금이 생겼다는 증거는 없습니다. 드러난 위험은 평가가 잘못 저장된 파일을 받아들이는 것입니다. [C3, C12]
- 이웃한 여러 필드에서는 null에 일부러 뜻이 있습니다. null을 모두 재귀적으로 거부하면 정당한 라벨 제외, 한쪽 검색에 없는 경우, 추적 키 없이 돌리는 동작이 깨집니다. [C10]

## 다른 방법

- `rewrite.cost_usd=null`만 거부: 보고된 예는 막지만, 최상위 cost_usd와 다른 필수 단일 값의 같은 자료형 빈틈은 남습니다. 평가가 실제로 쓰는 필드에서 규칙을 끌어내는 편이 낫습니다. [C3, C5]
- 비용 덧셈을 `_ragas` 앞으로 옮기기: 이 계산 실패는 더 일찍 드러나지만, 다른 사용처나 유료 Grounding 평가의 입력이 유효하다는 보장은 되지 않습니다. 미리 준비하는 데는 도움이 되지만 공용 검사 규칙으로는 부족합니다. [C3, C5]
- `value or 0`, `float(value)`, 넓은 예외 처리: 잘못된 출처를 숨기거나 저장된 비용 기록을 바꿀 수 있습니다. 기존의 '거부하고 다시 만들기' 동작도 약해집니다. [C5, C12]
- `_ragas` 뒤에서 TypeError 잡기: 그 시점에는 이미 비용이 생길 수 있습니다. 채점 재시도나 사용량 계산을 바꿔도 입력 경계는 고쳐지지 않습니다. [C1, C3]
- 일반 스키마 프레임워크 도입이나 모르는 키 전부 거부: 지금 필드 규칙을 세우는 데 둘 다 필요 없습니다. 보통의 답변에는 이미 추가 메타데이터가 있습니다. 저장소의 단순함 규칙 아래에서는 작고 명시적인 검사기가 알맞은 첫 구현입니다. [C11]

## 실험

오프라인 테스트만 씁니다. 먼저 기존 `_answer_row` 테스트 데이터로 지금의 실패를 재현합니다. 정상 첫 행과 `rewrite.cost_usd`가 None인 둘째 행을 쓰고, `_ragas`는 factual_correctness 점수 두 개를 돌려주도록, `_send_scores`도 모의로 둡니다. 지금은 `_ragas`가 한 번 호출된 뒤 TypeError가 날 것으로 예상합니다. 따로 `_read_answers`가 지금 그 파일을 받아들이는지도 확인합니다. 수정 뒤에는 `row[2].rewrite.cost_usd`를 가리키는 ValueError, `_ragas` 호출 0회, 점수 게시 호출 0회, 결과 CSV 없음을 요구합니다. 최상위 비용, 하위 토큰 수, 문자열 필드, 리스트 항목, 뒤쪽 후보·근거 항목 안의 단일 값까지, 선언된 필드 종류마다 잘못된 자료형을 대표로 넣어 봅니다. 공용 읽기 함수 테스트를 네 평가 함수와 검색 다시 돌리기에 함께 쓰고, 검사에 실패하면 검색 다시 돌리기가 검색하거나 출력을 쓰지 않아야 합니다. 정상 대조군으로 0인 숫자, 정당하게 null인 라벨과 검색 순위·점수, null trace·주제, 허용된 빈 리스트, 추가 메타데이터를 넣습니다. 모의 채점 점수로 돌린 보통의 End-to-End 행은 열과 합계 비용 0.000101을 그대로 지켜야 합니다. 수정 전 코드가 모의 채점까지 가지 못하거나 제안한 규칙이 정상 대조군을 거부하면 가설이나 규칙을 고칩니다. 구현 뒤 저장소의 필수 린트와 테스트를 돌립니다. 이 조사 단계에서는 아무것도 실행하지 않았습니다. [C4, C5, C9, C10, C11, C12]

## 결과

오프라인 관측 — 교정 전에는 정상 첫 행과 `rewrite.cost_usd=null`인 둘째 행을 `_read_answers`가 모두 받아들였고, 모의 `_ragas`와 `_send_scores`가 각각 1회 호출된 뒤 비용 합산에서 `TypeError`가 발생했습니다. 교정 후 `tests/test_answer_records.py::test_invalid_saved_values_stop_all_consumers_before_side_effects`는 네 평가와 검색 재실행 모두에서 `row[2].rewrite.cost_usd`를 명시한 `ValueError`, 심판·점수 게시·검색 호출 0회, 결과 파일 없음과 함께 자료형 오류를 거부합니다. `tests/test_answer_records.py::test_valid_saved_values_preserve_nullability_metadata_and_end_to_end_cost`는 0인 정수·실수 비용, 허용된 null, 빈 목록, 추가 생산자 메타데이터와 기존 열·합계 비용 `0.000101`을 보존했습니다. 기본 표본과 검색 재실행의 실제 생산자 출력도 각각 30행씩 그대로 읽었습니다. 보고된 rewrite 비용 외의 적용 지점은 최상위 16개, rewrite의 나머지 5개, 검색 설정 6개, 후보 8개, 근거 2개로 총 37개 필드 계약입니다. `tests/test_usage.py`의 누락 키 회귀는 유지하고 기존 컨테이너 오류 검사는 더 강한 전체 파일·전체 소비자 검사로 접었습니다. 대상 테스트 461개와 전체 `.venv\Scripts\python -m pytest -q tests`의 `1053 passed, 12 warnings in 107.43s`를 확인했고 `ruff check .`와 debt 검사도 통과했습니다. 이 결과와 교정은 이 페이지를 함께 담는 커밋 `evaluation: enforce saved answer value types`에 기록합니다. 이는 초안의 실험 기록이며 검증된 공용 규칙으로 승격하지 않습니다.

## 남은 한계

이 문서는 초안입니다. 결과 절의 실험은 이 브랜치에서 수행한 오프라인 관측이며 실제 과금이나 배포 동작을 관측한 것이 아닙니다. 정확한 라운드 이력은 제공된 리뷰 보고서에 근거하며 과거 모든 커밋을 독립적으로 재검증하지 않았습니다. 허용된 null과 현재 생산자 표현은 표본·회귀 테스트에서 보존되었지만, 이 결과가 설정·심판 출력·네트워크·추적·파일 시스템의 별개 실패까지 방지한다는 뜻은 아닙니다.
