# 리뷰 조사 · F2, 1회차

집계 결과와 측정 조건은 Git에 보관하고, 실제 질문·정답·근거·OCR 텍스트와 레코드별 내보내기는 Git에서 제외된 로컬 `artifacts/`에 보관합니다.

복원 출처: 정리 전 `artifacts/review-round2/originals/` 또는 `d7d1682^`. 아래 수치와 검증 기록은 당시 실행에서 관측한 과거 기록이며, 이번 작업에서 다시 측정한 결과가 아닙니다.

PR #65 리뷰 5회차의 수정 전에 2026-10-18에 쓴 조사 초안입니다. 검증된 사실이나 공용 규칙이 아니며, 리뷰는 이 문서를 수정과 함께 읽습니다.

## 문제

F2는 key.json의 표본 review_id마다 RUBRIC 네 항목 모두에 대한 완전한 Y/N 판정이 정확히 하나씩 있을 때만 사람 품질을 '측정됨'으로 보고하라고 요구합니다. judgments.csv가 그 밖의 모양이면 멈추지 않고 {'measured': False, ...}로 돌아와야 합니다. 지금 `_human()`(golden_pipeline/comparison.py:237-263)은 머리글이 잘못되면 여전히 오류를 냅니다. RUBRIC 열이 빠진 머리글은 252행에서 KeyError를, review_id가 빠진 머리글은 246행에서 KeyError를 내며, 그러면 `compare`/`write`가 comparison.json을 쓰지 못하고 멈춥니다.

발생: 반복, 4·5회차.

- [P1] [P1] golden_pipeline/comparison.py:252 — RUBRIC 머리글이 빠지면 여전히 사람 검토 비교가 멈춥니다

## 실패한 수정

- 1회차 수정(62eeb95 → 이후에 고침): 246-250행에 Counter로 ID를 정확히 맞추는 확인을 더했습니다(빠진/모르는/중복 ID → 측정 안 됨). ID 집합은 확인했지만, 모든 행 사전에 RUBRIC 키가 모두 문자열 값으로 있다고 가정했습니다. 짧은 행과 빠진 열은 생각하지 않았으므로, 4회차에서 `None.strip()`에 걸렸습니다.
- 4회차 수정(cb3f3c1): 252행을 `(row[name] or "")`로 바꿔, DictReader가 짧은 행에 채우는 None을 빈 칸으로 셉니다. 이는 restval=None 경우를 다루며, 그 열이 머리글에 있을 때만 일어납니다. 머리글에 그 열이 없으면 사전에 키 자체가 없으므로, `or ""`가 돌기 전에 `row[name]`이 KeyError를 냅니다. tests/golden/test_experiment.py:86-91에 더한 테스트는 언제나 머리글을 다 쓰므로 이를 잡을 수 없었습니다. 두 수정 모두 증상이 나타난 줄에 놓였고, 보고된 잘못된 모양만 다뤘습니다.

## 출처

### S1 — csv — CSV File Reading and Writing (Python 3 문서), DictReader

- URL: https://docs.python.org/3/library/csv.html
- 확인일: 2026-10-18
- 위치: class csv.DictReader; DictReader.fieldnames
- 인용: If fieldnames is omitted, the values in the first row of file f will be used as the fieldnames and will be omitted from the results. ... If a row has more fields than fieldnames, the remaining data is put in a list and stored with the fieldname specified by restkey (which defaults to None). If a non-blank row has fewer fields than fieldnames, the missing values are filled-in with the value of restval (which defaults to None). ... DictReader.fieldnames: If not passed as a parameter when creating the object, this attribute is initialized upon first access or when the first record is read from the file.
- 적용: comparison.py:244는 fieldnames 없이 DictReader를 만들므로, judgments.csv의 머리글만으로 키가 정해집니다. restval None이 4회차를, 빠진 열에 키가 아예 없다는 것이 5회차를 설명합니다.
- 반대 근거: 이 문서는 빈 파일일 때 fieldnames 값(CPython에서는 None)을 말하지 않습니다. 실험 (c)가 이를 확인합니다.
- 검증: 머리글에서 열이 빠진 경우와 review_id가 빠진 경우의 테스트가 KeyError 대신 measured False를 돌려줍니다.

### S2 — golden_pipeline/comparison.py _human

- URL: golden_pipeline/comparison.py
- 확인일: 2026-10-18
- 위치: 237-263행
- 인용: ids = Counter(row["review_id"] for row in rows) ... if any((row[name] or "").strip().upper() not in ("Y", "N") for row in rows for name in RUBRIC):
- 적용: reader.fieldnames를 확인하는 곳이 없습니다. 모든 row[...] 조회가 머리글이 완전하다고 가정합니다.
- 반대 근거: 없음
- 검증: 수정 뒤에는 246행 앞에 fieldnames 관문이 있습니다.

### S3 — tests/golden/test_experiment.py 검토 품질 테스트

- URL: tests/golden/test_experiment.py
- 확인일: 2026-10-18
- 위치: 79-93행
- 인용: header = "review_id,evidence_support,answer_correct,topic_fit,useful,note" ... for rows in ([], ["R01"], ["R01", "R01", "R02"], ["R01", "R02", "R03"], ["R01 짧음", "R02 짧음"]):
- 적용: 모든 경우가 머리글을 다 쓰므로, 머리글 쪽은 한 번도 시험되지 않았습니다.
- 반대 근거: 없음
- 검증: 머리글을 바꾼 경우를 더합니다.

## 주장

- C1 (출처; S1): DictReader는 짧은 행의 빠진 값을 머리글에 있는 열에 대해서만 None으로 채웁니다. 머리글에 없는 열은 키 자체가 생기지 않습니다.
- C2 (해석; S1, S2): 앞선 두 수정 모두 오류가 난 줄에서 값을 막았습니다. 어느 쪽도 머리글을 확인하지 않아, RUBRIC 열이 없는 머리글(252행)이나 review_id가 없는 머리글(246행)은 여전히 KeyError를 냅니다.
- C3 (해석; S2, S3): 행을 읽기 전에 머리글에 {'review_id', *RUBRIC}가 있는지 한 번 확인하고 없으면 측정 안 됨을 돌려주는 것에, 기존 `or ""` 값 막이를 더하면 지금까지 제기된 잘못된 모양을 모두 다룹니다. 테스트는 행만이 아니라 머리글도 바꿔 봐야 합니다.

## 핵심 원리

Python csv 문서에 따르면 DictReader는 각 사전의 키를 fieldnames로 만들며, 기본값은 첫 행입니다. 짧은 행의 빠진 필드는 restval(기본 None)을 받고, 넘치는 필드는 restkey(기본 None) 아래 목록으로 들어갑니다. 그래서 값이 None이 되는 것은 그 열이 머리글에 있을 때뿐입니다. 머리글에 열이 없으면 어느 행에도 그 키가 없습니다. 서로 다른 두 실패 모양이며, 막이도 둘이 필요합니다. 키가 없을 때는 머리글 확인, None이나 빈 값일 때는 값 확인입니다.

## 적용

golden_pipeline/comparison.py:243-252입니다. judgments.csv는 review_packets(198-201행)가 `review_id,*RUBRIC,note` 머리글로 쓰지만, 그 뒤 사람이 손으로 고칩니다. 그래서 신뢰 경계이며, 사람이 열을 지우거나 이름을 바꿀 수 있습니다. 머리글 확인은 `csv.DictReader(f)`를 만든 바로 뒤, `rows` 목록을 쓰기 전에 둡니다. 그래야 review_id 열이 필요한 246행의 ID Counter보다 먼저 돕니다. 넘치는 칸(restkey None)은 지금 오류를 내지 않고 채점에도 쓰이지 않으므로 처리할 필요가 없습니다.

## 가설

근본 원인은 파일의 스키마를 한 번도 검증하지 않는 것입니다. `_human()`은 행 값은 확인하지만 머리글(`DictReader.fieldnames`)은 확인하지 않습니다. 모든 키 조회(246행의 `row['review_id']`, 252/257/262행의 `row[name]`)가 머리글에 review_id와 RUBRIC 전체가 있다는 확인하지 않은 가정에 기댑니다. DictReader를 만든 바로 뒤에 `if not {'review_id', *RUBRIC} <= set(reader.fieldnames or ()): return {'measured': False, 'reason': ..., 'missing_columns': ...}` 확인 하나를 두면, 이 종류의 실패를 모두 막습니다. RUBRIC 열이 빠진 경우, review_id 열이 빠진 경우, 0바이트 빈 파일(fieldnames None)입니다. 머리글이 완전해도 짧은 행은 None을 내므로 기존 `or ""`는 남깁니다. 두 관문을 지나면 257행과 262행은 'Y'/'N' 문자열만 보므로 바꿀 필요가 없습니다.

## 반대 근거

- 머리글에서 `note`를 빼는 것은 해가 없습니다. note를 읽는 곳이 없기 때문입니다. 확인이 이를 요구하면, note 열이 없는 올바른 파일이 측정 안 됨으로 잘못 보고됩니다.
- 공백이 섞인 머리글(예: ' useful')이나 중복된 열 이름은 값이 아니라 머리글 확인이 판단합니다. 공백은 측정 안 됨이 되며, 보수적이라 받아들일 만합니다. 중복된 이름은 DictReader가 뒤쪽 열을 남기게 하며, 확인은 이를 보지 못합니다. 드문 경우이고 지적에 들어 있지 않습니다.

## 다른 방법

- 모든 곳의 `row[name]`을 `row.get(name)`으로 바꾸기. 오류는 멈추지만, 모든 경로가 지나는 한 곳에 막이를 두지 않고 246, 252, 257, 262행에 흩어 놓게 되며, review_id 열이 빠진 경우가 헷갈리는 'ID가 맞지 않음' 이유로 나타납니다. 첫 선택이 아닙니다.
- DictReader에 `fieldnames=('review_id', *RUBRIC, 'note')`를 명시하고 첫 행을 건너뛰기. 순서가 바뀌거나 이름이 바뀐 머리글을 숨기고 값을 엉뚱한 열에 묶어, 소리 없이 틀린 판정을 만듭니다. 측정을 거부하는 것보다 나쁩니다.
- 함수 전체를 try/except KeyError/AttributeError로 감싸기. 근거 없는 예외 처리(CLAUDE.md 1.1)이며, 진짜 버그도 숨깁니다.

## 실험

tests/golden/test_experiment.py:79를 넓혀, 기대 ID R01/R02가 있을 때 다음 각 경우가 오류 없이 `_human('x1')['measured'] is False`가 되는지 확인합니다. (a) RUBRIC 열을 하나씩 돌아가며 뺀 머리글, (b) review_id가 빠진 머리글, (c) 0바이트 judgments.csv. 완전한 머리글 아래 짧은 행인 기존 경우와 긍정 경우(완전한 머리글과 행 → A · all = 1/2)는 유지합니다. `note`가 없는 머리글에 RUBRIC 행이 다 있으면 여전히 측정되는지도 확인합니다. 수정 전에는 (a)와 (b)가 KeyError를 내야 하고, 수정 뒤에는 모두 통과해야 합니다. 그 테스트만 pytest로 한 번 돌린 뒤 검사를 돌립니다.

## 결과

제안한 실험을 `tests/golden/test_experiment.py::test_review_quality_is_unmeasured_unless_every_sampled_output_is_judged_exactly_once`에서 돌렸습니다. `review_id`와 RUBRIC 네 열을 하나씩 빼는 반복으로 (a)와 (b)를, 0바이트 파일로 (c)를, 그리고 `note` 없는 머리글을 더했습니다. 짧은 행 경우와 긍정 경우는 유지했습니다. 수정 전(`1513ad5`)에는 첫 머리글 경우에서 테스트가 실패했습니다. `review_id`를 빼면 comparison.py:246에서 `KeyError: 'review_id'`가 났습니다. 지적에 나온 머리글 `review_id,evidence_support,answer_correct,topic_fit`로 HEAD의 `_human`을 임시로 돌리면 `KeyError 'useful'`이 났습니다. 수정은 가설대로 `csv.DictReader` 바로 뒤의 머리글 관문 하나이며, `reader.fieldnames or ()`를 쓰고 `{'measured': False, 'reason': ..., 'missing_columns': [...]}`를 돌려줍니다. 값의 `or ""`는 남깁니다. (c) 경우 때문에 관문 위치가 바뀌었습니다. 첫 버전은 `with` 블록 뒤에서 `reader.fieldnames`를 읽었고, 그러면 0바이트 파일이 `ValueError: I/O operation on closed file`을 냈습니다. 빈 파일에서는 `fieldnames`가 None으로 남고, 읽을 때마다 파일을 다시 읽습니다. 이제 관문은 파일이 열려 있는 동안 `fieldnames`를 읽습니다. 그 뒤 같은 임시 실행은 `measured False, missing_columns ['useful']`를 돌려주고, 0바이트 파일과 `note` 없는 머리글(여전히 측정됨, A · all = 1/2)을 포함해 테스트가 통과합니다. `tests/golden/test_validation.py`와 `tests/golden/test_experiment.py`의 나머지도 통과했습니다(108). 결과는 이 문서를 담은 커밋에 있으며, 전체 검사는 서버가 돌리고 아직 기다리는 중입니다.

## 남은 한계

문서는 빈 파일일 때 DictReader.fieldnames가 무엇인지 말하지 않습니다. CPython은 None을 돌려주므로 확인에 `or ()`가 필요하며, 실험 (c)가 이를 확인합니다. 이 조사는 스키마와 값 모양만 다룹니다. judgments.csv가 있을 때 key.json 자체가 없거나 잘못됐을 수 있는지(242행이 오류를 냄)는 다루지 않습니다. 지적이 이를 제기하지 않았고, review_packets는 두 파일을 함께 씁니다.
