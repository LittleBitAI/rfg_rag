# 리뷰 조사 · F6, 1회차

집계 결과와 측정 조건은 Git에 보관하고, 실제 질문·정답·근거·OCR 텍스트와 레코드별 내보내기는 Git에서 제외된 로컬 `artifacts/`에 보관합니다.

복원 출처: 정리 전 `artifacts/review-round2/originals/` 또는 `d7d1682^`. 아래 수치와 검증 기록은 당시 실행에서 관측한 과거 기록이며, 이번 작업에서 다시 측정한 결과가 아닙니다.

PR #65 리뷰 6회차의 수정 전에 2026-10-18에 쓴 조사 초안입니다. 검증된 사실이나 공용 규칙이 아니며, 리뷰는 이 문서를 수정과 함께 읽습니다.

> 잘못 분류됨(리뷰 7회차, F5). "## 문제"부터 "## 실험"까지는 F6가 아니라 F2(`_human`의 judgments.csv 읽기)를 분석합니다. 서버의 형식 재시도가 썼으며, 그 재시도는 지적이 아니라 파싱 오류만 담은 프롬프트로 새 세션에서 돌았습니다(`review-golden-abc-seven-topic-comparison-f5-1.md` 참고). 그 절들을 F6 수정의 근거로 인용하지 마세요. 수정 전에 쓴 F6 조사는 바로 다음 절입니다. 거부된 첫 조사 답에서 되살렸습니다.

## 수정 전에 쓴 F6 조사(되살림)

출처: wiki-agent 작업 대화 기록 `raw/work/rfg_rag/golden-abc-seven-topic-comparison.jsonl` 43행(셀 `e8e0948d…`, ts 1792283995). 서버의 첫 F6 조사 단계이며, 4·5·6회차 지적을 인용한 42행의 F6 프롬프트에 대한 답입니다. 서버는 출처 S5가 이 저장소 밖의 허브 위키 파일이라는 이유로만 거부했습니다(44행). 45행의 재시도(새 셀 `ae2c9fe9…`)가 아래의 F2 글을 만들었습니다. 이 답은 조사 커밋 `9458840`(ts 1792284182)과 수정 커밋 `f0ddd69`(ts 1792284592)보다 앞섭니다. 수정 세션은 이 답을 읽지 않았습니다. 수정은 스스로 같은 설계에 이르렀고, 이 문서는 그 답을 나중에 기록합니다. 여기서는 문구를 줄였으며, 43행의 기록이 기준입니다.

문제. 일부 검증된 후보를 이어할 때, 호출 한도는 아직 사야 할 유료 호출만 세야 합니다. `_reply`가 공짜로 재생할 호출은 이미 낸 것입니다. 4회차는 한도가 후보의 `_calls_needed` 전체를 센다는 것을 찾았습니다. 6회차는 `cb3f3c1` 전에 쓴, `role`이 없는 검증 기록에서도 같다는 것을 찾았습니다. 끝난 호출은 재생되지만 여전히 셉니다. 남은 허용치를 정확히 주고 이어하면(전체 근거 호출이 끝난 세 호출 multi_hop에 `max_calls=2`), 후보가 미판정인 채 `call_cap`에서 멈춥니다.

실패한 수정. 4회차(`cb3f3c1`)는 호출마다 `role`을 붙이고, attempt 0에서 `role == "validator"`인 호출을 이미 낸 것으로 셌습니다. 오래된 기록에 없는 표시에 기댑니다. `1884f73`은 role 없는 기록을 재생했지만 일부러 빼지 않았고(validation.py:109의 주석), 테스트는 자기 주석이 필요한 한도를 2라고 하면서도 `(True, 3)`으로 이를 고정했습니다. 재생과 한도 추정이 '이미 냄'을 서로 다른 두 규칙으로 정해 왔습니다.

가설. `_reply`는 이 후보의 (요청 SHA-256, 시도)가 저장된 호출과 맞으면 재생합니다. `_settled_calls`는 따로 저장한 `role` 표시로 이미 낸 호출을 세므로, 표시가 없으면 둘이 어긋납니다. 수정: 재생과 같은 방식으로 이미 냄을 정합니다. `_verdict`가 할 검증기 요청을 나열합니다. 전체 근거, 그리고 multi_hop이면 머리글이 아닌 단위마다 머리글을 붙인 단일 단위 하나, 답할 수 없음이면 `document_batches` 묶음마다 하나입니다. 각각을 `_reply`가 쓰는 함수로 해시하고, 후보의 재생 맵에 attempt-0 항목이 있는 해시를 셉니다. `_calls_needed`는 그 목록의 길이가 되고, `role`은 한도 논리에서 빠집니다.

원리. 재생 시스템은 결과 옆에 저장한 이름표가 아니라 요청을 기록된 이력과 맞춰서 이미 한 일을 정합니다. Temporal은 워크플로가 내는 명령을 Event History와 비교합니다. Stripe는 멱등 키에 대해 저장된 결과를 돌려주고, 들어온 인자를 원래 것과 대조합니다. 재생이 무엇을 다룰지 예측하는 것은 같은 키를 써야 하며, 그렇지 않으면 예측과 재생이 어긋납니다.

적용. 이어하기는 검증기 프롬프트 SHA나 `VALIDATOR_VERSION`이 바뀌면 돌지 않으므로(`_criteria`), 저장된 검증기 요청 해시는 이어하는 실행이 계산하는 해시와 여전히 맞습니다. 채점 요청은 두 답을 담고 채점 프롬프트를 쓰므로, role 없는 기록에서도 그 해시는 검증기 호출로 셀 수 없습니다.

반대 근거. (1) `_criteria`는 `validator_input`이나 `document_batches`의 코드를 다루지 않습니다. 버전을 올리지 않고 그 코드가 바뀌면 옛 해시가 맞지 않고, 재생도 맞지 않아 다시 냅니다. 그래도 추정은 실제 지출과 맞습니다. 보수적일 뿐 틀리지 않습니다. (2) 이 수는 후보가 할 수 있는 검증기 호출의 최대값입니다. 재시도와 채점 호출은 세지 않으며, 알려진 단순화 한계입니다. (3) 새 목록은 `_single_unit_verdict`와 `_absent_verdict`가 단위를 만드는 방식을 되풀이하므로, 코드를 함께 쓰지 않으면 사본이 어긋날 수 있습니다.

다른 방법(택하지 않음). 저장된 출력으로 역할을 추론하기: 파싱에 실패한 attempt-0 출력은 애매하고, 재생과 맞추지 않고 추측합니다. role 없는 attempt-0 호출을 모두 검증기 호출로 세기: 저장된 채점 호출을 빼게 되어 한도를 넘습니다. 옛 기록에 `role`을 더해 다시 쓰기: 기록된 근거를 바꿉니다. '옛 기록이면 한도를 올리라'고 문서에 적기: 6회차가 바로 이를 거부했습니다.

실험. `tests/golden/test_validation.py`에서 `(True, 3)`을 `(True, 2)`로 바꿉니다. 수정 전에는 `call_cap`에서 끝나고 새로 아무것도 보내지 않아야 합니다. 수정 뒤에는 정확히 `(E1,)`과 `(E2,)`를 보내고 auto_validated로 끝나야 합니다. 부정 경우를 더합니다. 저장된 attempt-0 호출이 채점 호출이면 수를 낮추면 안 됩니다.

출처. S1, Temporal Workflow Definition(결정성 제약과 재생), https://docs.temporal.io/workflow-definition.md. S2, Stripe API, Idempotent requests, https://docs.stripe.com/api/idempotent_requests. 둘 다 그 단계에서 검색 요약으로 읽었습니다. S3은 `1884f73` 시점의 `golden_pipeline/validation.py`: `_settled_calls`, `_reply`, `_batch`, `_calls_left`/`_calls_needed`. S4는 `1884f73` 시점의 `tests/golden/test_validation.py` 474-504행. 거부된 S5는 허브 규칙 `craft/measure-after-the-last-change`였으며, 외부 근거가 아니라 내부 규칙이라 여기서는 인용하지 않습니다.

## 문제

F2: 사람 검토 품질은 key.json의 표본 review_id마다 RUBRIC 네 항목 모두에 대한 완전한 Y/N 판정이 정확히 하나씩 있을 때만 '측정됨'으로 보고할 수 있습니다. 손으로 고친 judgments.csv가 그 밖의 모양이면 오류를 내지 않고 {'measured': False, ...}를 돌려줘야, compare()/write()가 계속 comparison.json을 씁니다. 이 지적은 4·5회차에 이어 이번에 다시 나왔습니다. 매번 리뷰어는 golden_pipeline/comparison.py::_human(237-269행)이 여전히 오류를 내는 다른 잘못된 파일을 찾았습니다.

발생: 진동, 4·5·6회차.

- [P1] [P1] golden_pipeline/validation.py:110 — role 없는 끝난 호출이 여전히 이어하기 한도에 셈해집니다 / 옛 부분 기록을 남은 호출 허용치 그대로 이어할 때 / 이어할 수 있는 후보가 미판정으로 남습니다

## 실패한 수정

- 1회차(62eeb95): Counter로 ID를 정확히 맞추는 확인(지금 252-256행)을 더했습니다. 모든 행이 필요한 키마다 문자열을 갖는다고 가정했으므로, 짧은 행이 나중에 None.strip()에서 멈췄습니다.
- 4회차(cb3f3c1): Y/N 확인을 (row[name] or '')(지금 258행)로 바꿨습니다. RUBRIC 칸의 None만 다룹니다. 머리글에 열이 없으면 키 자체가 없으므로, `or ''`가 돌기 전에 row[name]이 KeyError를 냈습니다.
- 5회차(1884f73, 1회차 문서 뒤): review_id나 RUBRIC 열이 빠지면 측정 안 됨을 돌려주는 머리글 관문(246-250행)을 더했고, 파일이 열려 있는 동안 읽습니다. 빠진 키는 막지만, 칸에 무엇이 들었는지와 바이트가 무엇으로 디코딩되는지는 여전히 믿습니다. 세 파일 모양이 여전히 멈춥니다. (a) review_id가 첫 열이 아닌 머리글에 짧은 행. DictReader가 review_id를 None으로 채우고, 252행의 Counter가 이를 세며, 255행의 sorted(set(ids) - set(key))나 256행의 중복 ID sorted가 None과 문자열을 비교해 TypeError를 냅니다. (b) note에 한글이 있는, UTF-8이 아닌 인코딩으로 저장한 파일(예: 한국어 로캘 PC에서 Excel의 일반 'CSV' 저장). open(encoding='utf-8-sig')는 errors='strict'를 쓰므로, 246행의 list(reader)가 UnicodeDecodeError를 냅니다. (c) NUL 바이트. 예를 들어 우연히 디코딩되는 UTF-16 '유니코드 텍스트' 저장입니다. 저장소의 Python 3.10에서 csv는 csv.Error 'line contains NUL'을 냅니다. 1회차 것을 포함한 세 수정 모두 방금 보고된 모양을 지적된 줄에서 막았습니다. 어느 것도 읽기 자체를 빠짐없이 처리하게 만들지 않았습니다.

## 출처

### S1 — csv — CSV File Reading and Writing (Python 3 문서)

- URL: https://docs.python.org/3/library/csv.html
- 확인일: 2026-10-18
- 위치: class csv.DictReader; exception csv.Error; Dialect.strict
- 인용: If a row has more fields than fieldnames, the remaining data is put in a list and stored with the fieldname specified by restkey (which defaults to None). If a non-blank row has fewer fields than fieldnames, the missing values are filled-in with the value of restval (which defaults to None). ... exception csv.Error: Raised by any of the functions when an error is detected. ... Dialect.strict: When True, raise exception Error on bad CSV input. The default is False.
- 적용: review_id가 첫 열이 아닌 머리글 아래 짧은 행은 review_id를 None으로 만들고(comparison.py:252), 이것이 255-256행의 sorted()에 닿습니다. csv.Error는 246행에서 잘못된 입력에 대한 파서의 오류 형식입니다.
- 반대 근거: 이 문서는 strict가 False일 때 정확히 어떤 입력이 csv.Error를 내는지 나열하지 않습니다. 버전 안내에 NUL은 나오지 않습니다.
- 검증: (a) 경우가 TypeError 대신 measured False를 돌려줍니다.

### S2 — Built-in Functions — open() (Python 3.10 문서)

- URL: https://docs.python.org/3.10/library/functions.html
- 확인일: 2026-10-18
- 위치: open(), errors 매개변수
- 인용: 'strict' to raise a ValueError exception if there is an encoding error. The default value of None has the same effect.
- 적용: comparison.py:243은 encoding='utf-8-sig'와 기본 errors로 judgments.csv를 여므로, 246행에서 list(reader)가 돌 때 UTF-8이 아닌 바이트가 오류를 냅니다.
- 반대 근거: UTF-8이 아닌 파일이라도 ASCII 바이트만 있으면 잘 디코딩됩니다. 한글 note처럼 ASCII가 아닌 글만 오류를 일으킵니다.
- 검증: 한글 note가 있는 cp949 파일인 (b) 경우가 UnicodeDecodeError 대신 measured False를 돌려줍니다.

### S3 — Parse, don't validate (Alexis King)

- URL: https://lexi-lambda.github.io/blog/2019/11/05/parse-don-t-validate/
- 확인일: 2026-10-18
- 위치: 파서와 검증기를 정의하는 절; 'Ideally, this should happen at the boundary'
- 인용: a parser is just a function that consumes less-structured input and produces more-structured output. ... Ideally, this should happen at the boundary of your system, before any of the data is acted upon. ... Sometimes, making an illegal state truly unrepresentable is just plain impractical ... Consider the principles in this blog post ideals to strive for, not strict requirements to meet.
- 적용: _human은 데이터를 확인하는 일과 쓰는 일을 번갈아 하므로(머리글, Counter, sorted, Y/N), 확인하지 않은 단계마다 새 지적이 됐습니다. Counter 앞의 243-258행에 파싱 단계 하나를 두는 것이 이 생각과 맞습니다.
- 반대 근거: 저자는 이 방식을 이상으로 제시합니다. Python에는 증명을 담을 형식이 없으므로, 보장은 확인 순서로만 유지됩니다.
- 검증: 바꾼 뒤 Counter부터의 줄은 문자열 값만 봅니다. 새 세 경우와 옛 경우가 뒤쪽 줄에 새 막이 없이 모두 measured False를 돌려줍니다.

### S4 — denoland/deno_std PR 3143(Excel CSV 내보내기와 BOM 논의)

- URL: https://github.com/denoland/deno_std/pull/3143
- 확인일: 2026-10-18
- 위치: Excel 'CSV UTF-8'과 'CSV'에 대한 웹 검색 결과 요약
- 인용: The 'CSV UTF-8' option in Excel's Save As list adds a byte order mark; the plainly labeled 'CSV' option does not add a BOM and transforms all non-Windows-1252 characters into question marks (lossy). (검색 결과에서 가져왔으며, PR 페이지 자체는 가져오지 않음)
- 적용: 팀원이 judgments.csv를 Excel의 일반 'CSV' 옵션으로 다시 저장하면, UTF-8이 아니라 ANSI 코드 페이지 파일이 됩니다. 한국어 로캘에서는 CP949라고 가정하며, 그러면 한글 note가 UTF-8이 아닌 바이트가 됩니다.
- 반대 근거: Windows-1252 로캘을 설명하고, BOM과 함께 연 파일을 기본 저장할 때는 시험하지 않습니다. 한국어 로캘의 동작은 나오지 않습니다.
- 검증: (b) 경우는 encoding='cp949'로 그 결과 바이트를 직접 재현하므로, 수정이 Excel의 정확한 동작에 달려 있지 않습니다.

### S5 — docutils py311 테스트 패치(Adélie Linux 패키지)

- URL: https://cgit.adelielinux.org/packages/tree/user/py3-docutils/py311-test.patch
- 확인일: 2026-10-18
- 위치: 웹 검색 결과에 따른 패치 커밋 메시지
- 인용: changed for Python 3.11: Null char valid in CSV ... 3.11.0a2 ... csv module supports null character (검색 결과에서 가져옴)
- 적용: 저장소의 .venv는 Python 3.10이며(CLAUDE.md 6절), 거기서 csv는 comparison.py:246의 NUL 바이트에 여전히 csv.Error 'line contains NUL'을 냅니다.
- 반대 근거: CPython 릴리스 안내가 아니라 하위 배포판의 메모입니다. 3.11 이상에서는 (c) 경우가 오류를 내지 않으므로, 예외 처리는 다른 csv.Error 원인만 다루게 됩니다.
- 검증: 3.10 .venv에서 (c) 경우는 수정 전에 csv.Error를 내고 수정 뒤에 measured False를 돌려줍니다.

### S6 — golden_pipeline/comparison.py _human

- URL: golden_pipeline/comparison.py
- 확인일: 2026-10-18
- 위치: 237-269행
- 인용: columns, rows = set(reader.fieldnames or ()), list(reader) ... missing_columns = sorted({"review_id", *RUBRIC} - columns) ... ids = Counter(row["review_id"] for row in rows) ... "unknown": sorted(set(ids) - set(key)), "duplicated": sorted(review_id for review_id, n in ids.items() if n > 1)} ... if any((row[name] or "").strip().upper() not in ("Y", "N") for row in rows for name in RUBRIC):
- 적용: 머리글 관문은 있습니다. 디코딩이나 csv 오류에 대한 막이가 없고, Counter와 sorted() 이유 목록 앞에 review_id의 None 확인이 없습니다.
- 반대 근거: 없음
- 검증: 수정 뒤에는 243행과 Counter 사이에 파싱 단계 하나가 있고, 252-269행은 `or ''`를 지운 것 말고는 바뀌지 않습니다.

### S7 — tests/golden/test_experiment.py 검토 품질 테스트

- URL: tests/golden/test_experiment.py
- 확인일: 2026-10-18
- 위치: 79-103행
- 인용: header = "review_id,evidence_support,answer_correct,topic_fit,useful,note" ... for dropped in range(5): ... (folder / "judgments.csv").write_bytes(b"") ... write_text(..., encoding="utf-8-sig")
- 적용: 모든 경우가 review_id를 첫 열로 두고 BOM 있는 UTF-8로 쓰므로, 순서가 바뀐 머리글에 짧은 행, UTF-8이 아닌 파일, NUL 바이트를 시험하지 않습니다.
- 반대 근거: 없음
- 검증: (a), (b), (c) 경우와, 여전히 측정되는 순서가 바뀐 완전한 머리글을 더합니다.

### S8 — 리뷰 조사 · F2, 1회차

- URL: docs/research/review-golden-abc-seven-topic-comparison-f2-1.md
- 확인일: 2026-10-18
- 위치: 실패한 수정; 가설; 남은 한계
- 인용: 두 수정 모두 증상이 나타난 줄에 놓였고, 보고된 잘못된 모양만 다뤘습니다. ... 이 조사는 스키마와 값 모양만 다룹니다.
- 적용: 1회차 스스로 범위를 스키마와 값 모양으로 제한했습니다. 인코딩, csv 토큰화, 순서가 바뀐 머리글 아래 review_id의 None은 그 범위 밖이었습니다.
- 반대 근거: 1회차는 머리글 관문과 `or ''`가 지금까지 제기된 잘못된 모양을 모두 다룬다고 주장했으며, 그때까지 제기된 모양에 대해서는 맞았습니다.
- 검증: 이번 회차 실험은 1회차가 빼놓은 모양을 다룹니다.

## 주장

- C1 (해석; S1, S6): DictReader는 비어 있지 않은 짧은 행의 빠진 값을 None으로 채우며, review_id가 첫 열이 아니면 review_id도 그렇습니다. 그러면 _human이 그 None을 세고 문자열 ID 옆에서 정렬해 TypeError를 냅니다.
- C2 (해석; S2, S4, S6): UTF-8이 아닌 바이트(예: CP949 한글 note)를 담은 judgments.csv는 open()의 기본 errors가 strict이므로 utf-8-sig 읽기에서 UnicodeDecodeError를 냅니다.
- C3 (해석; S1, S5, S6): csv는 잘못된 입력을 찾으면 csv.Error를 내고, Python 3.10에서는 NUL 바이트가 그런 입력입니다. _human은 이를 잡지 않습니다.
- C4 (해석; S3, S6): 데이터를 쓰기 전에 경계에서 파싱한다는 것은, Counter 앞에서 파일을 한 번에 문자열만 있는 행이나 측정 안 됨 이유로 바꾼다는 뜻입니다. 회차마다 모양 하나씩이 아니라 실패 전체를 막습니다.
- C5 (해석; S7, S8): 기존 테스트와 1회차 조사는 언제나 review_id를 첫 열에 두고 UTF-8 인코딩으로, 머리글과 값 모양만 다뤘습니다. 그래서 남은 모양을 잡지 못했습니다.

## 핵심 원리

Alexis King, 'Parse, don't validate': 파서는 덜 구조화된 입력을 받아, 알게 된 것을 유지하는 더 구조화된 출력을 냅니다. 파싱은 'should happen at the boundary of your system, before any of the data is acted upon'. 저자는 이를 엄격한 규칙이 아니라 이상으로 제시하며, 잘못된 상태를 아예 나타낼 수 없게 만드는 것이 때로 비현실적이라고 말합니다. Python 문서는 구체적인 실패 모양을 줍니다. DictReader는 비어 있지 않은 짧은 행의 빠진 값을 restval(None)로 채우고, 넘치는 값은 restkey(None) 아래 목록에 넣습니다. 기본 errors의 open()은 디코딩 오류에 ValueError(UnicodeDecodeError)를 냅니다. csv는 오류를 찾으면 csv.Error를 내며, Python 3.11 전에는 NUL 바이트가 이를 일으켰습니다.

## 적용

judgments.csv는 review_packets(comparison.py:198-201)가 BOM 있는 UTF-8과 review_id,*RUBRIC,note 머리글로 쓰고, 그다음 사람이 손으로 고칩니다. 그래서 신뢰 경계이며, F2 규칙은 그 위에서 빠짐없이 처리하는 함수를 요구합니다. 파싱 단계는 _human의 243-258행, Counter(252) 앞에 둡니다. Counter가 review_id를 문자열로 가정하는 첫 사용처이기 때문입니다. DictReader는 이름으로 키를 정하므로 열 순서는 자유이며, 기존 테스트도 열을 빼면서 순서를 바꾸므로 순서가 바뀐 머리글은 실제로 있는 모양입니다. 팀은 한국어 Windows에서 일하고 note는 자유 글이므로, UTF-8이 아닌 저장은 있을 법합니다. 저장소의 .venv는 Python 3.10이며, 거기서는 NUL이 여전히 오류를 냅니다.

## 가설

근본 원인은 _human이 값을 쓰기 전에 파일을 한 번에 믿을 수 있는 형태로 파싱하지 않고, 조각조각 검증하는 것입니다. 읽는 단계마다 잘못된 입력에 오류를 낼 수 있습니다. 디코딩, csv 토큰화, 머리글 키, 행별 None 값, 그다음 Counter, sorted, Y/N 확인입니다. 회차마다 단계 하나를 막았습니다. 버티는 수정은 처음에 파싱 단계 하나를 둡니다. (1) open/DictReader/list(reader) 블록을 감싸, 파일 내용이 거기서 일으킬 수 있는 유일한 오류인 UnicodeDecodeError와 csv.Error를 이유와 함께 measured False로 돌려줍니다(예: 'CSV UTF-8'로 저장하라는 안내). (2) 머리글 관문은 유지합니다. (3) Counter 전에, review_id나 RUBRIC 열에 None이 있는 행(짧은 행)이 있으면 측정 안 됨을 돌려주어, 뒤의 모든 값이 문자열이 되게 합니다. 그 뒤 ID 확인, sorted() 이유 목록, Y/N 확인은 문자열에서만 돌고 더 막을 필요가 없습니다. 그러면 258행의 `or ''`를 지울 수 있습니다.

## 반대 근거

- CLAUDE.md 1.1은 근거 없는 예외 처리를 금지합니다. UnicodeDecodeError/csv.Error를 잡는 것을 그렇게 볼 수도 있습니다. 하지만 규칙이 분명히 요구하는 신뢰 경계의 입력 검증이며, 예외 처리는 함수 전체가 아니라 읽기 블록만 감싸야 합니다.
- Excel의 기본 저장이 BOM CSV를 ANSI 코드 페이지로 바꾸는지는 확인하지 않았습니다. 찾은 출처는 일반 'CSV' 옵션이 BOM을 빼고 정보를 잃는다고만 말합니다(Windows-1252를 언급). 한국어 로캘의 ANSI 페이지가 CP949라는 것은 제 해석입니다.
- 저장소에서 6회차 지적 글을 읽을 수 없었습니다. 리뷰어가 이 세 모양 말고 다른 것(예: key.json)을 짚었다면, 이 가설은 그것을 놓칩니다.

## 다른 방법

- errors='replace'로 열기: CP949 note는 U+FFFD가 되지만 ASCII ID와 Y/N 칸은 남으므로, 파일은 여전히 측정됩니다. 3.10의 NUL이나 UTF-16은 다루지 못하고, 잘못 인코딩된 파일을 소리 없이 받아들입니다. 나중에 할 수 있는 일이지 첫 선택이 아닙니다.
- 255-256행의 sorted(...)를 sorted(..., key=str)로 바꾸기: (a) 모양만 증상 줄에서 고치며, 세 번 실패한 방식과 같습니다.
- _human 전체를 try/except Exception으로 감싸기: 진짜 버그를 숨기고 CLAUDE.md 1.1을 어깁니다.
- DictReader에 fieldnames를 명시하기: 머리글 순서가 바뀌면 값을 엉뚱한 열에 묶어 소리 없이 틀린 판정을 냅니다. 1회차에서 이미 택하지 않았습니다.

## 실험

key R01/R02를 유지한 채, tests/golden/test_experiment.py::test_review_quality_is_unmeasured_unless_every_sampled_output_is_judged_exactly_once를 파일 세 개로 넓힙니다. (a) 머리글 'evidence_support,answer_correct,topic_fit,useful,review_id'와 행 'Y,Y,Y,Y,R01', 'N,Y,Y,Y', 'Y,Y,Y,Y,R03'. (b) 완전한 머리글과, note에 한글이 있는 R01/R02 행을 encoding='cp949'로 씀. (c) 완전한 머리글과 note 칸 안의 NUL 바이트. 각각 measured False를 돌려줘야 합니다. HEAD(af5aa9f)에서 저장소의 .venv(3.10)로 돌리면, 수정 전에는 (a) TypeError, (b) UnicodeDecodeError, (c) csv.Error를 예상합니다. 파싱 단계가 지나치게 거부하지 않도록, 행이 완전한 순서가 바뀐 머리글은 여전히 측정되는지(A · all = 1/2)도 확인합니다. 이 테스트만 pytest로 한 번 돌린 뒤 검사를 돌립니다.

## 결과

이 문서는 6회차 F6 지적이 아니라 F2(`_human`의 judgments.csv 읽기)를 분석합니다. F6는 `golden_pipeline/validation.py:110`(`_settled_calls`)의 이어하기 호출 한도에 관한 것입니다. 둘 다 같은 커밋에서 다뤘고, 둘 다 여기에 기록합니다.

F2에 대한 이 문서의 실험: `tests/golden/test_experiment.py::test_review_quality_is_unmeasured_unless_every_sampled_output_is_judged_exactly_once`를 (a), (b), (c)와 순서가 바뀐 완전한 머리글로 넓혔습니다. 저장소의 3.10 `.venv`에서 `af5aa9f`의 `_human`을 임시로 돌리면 예측한 오류가 났습니다. (a) `TypeError '<' not supported between instances of 'NoneType' and 'str'`, (b) `UnicodeDecodeError 'utf-8' codec can't decode byte 0xb1`, (c) `csv.Error line contains NUL`. 순서가 바뀐 완전한 머리글은 이미 측정됐습니다(A · all = 1/2). 수정은 가설의 파싱 단계 하나, `comparison._judgment_rows`입니다. 읽기 블록만 감싸 `UnicodeDecodeError`와 `csv.Error`를 잡습니다. 머리글 관문은 유지합니다. 어떤 행이든 `review_id`나 RUBRIC 열에 None이 있으면 측정 안 됨을 돌려줍니다. `or ""`는 지웠습니다. 수정 뒤 (a)는 짧은 행으로 측정 안 됨, (b)와 (c)는 "'CSV UTF-8'로 저장"하라는 안내와 함께 읽을 수 없음으로 측정 안 됨이 되고, 순서가 바뀐 완전한 머리글은 여전히 측정됩니다.

제기된 F6: `max_calls=2`에서 `tests/golden/test_validation.py::test_resume_counts_only_the_calls_a_candidate_has_not_already_settled_against_the_call_cap`의 role 없는 경우를 같은 테스트 파일 실행으로 돌리면 수정 전에 실패했습니다. `[('E1','E2')]`만 보냈고 후보는 미판정으로 남았습니다. 수정은 `role` 필드를 추론하지 않고 없앱니다. `_calls_left`는 `_verdict`가 쓰는 같은 단위 목록(`_calls_needed`를 대신하는 `_validator_unit_lists`)으로 후보가 보낼 검증기 요청을 다시 만듭니다. 첫 시도가 그 후보의 재생에 있으면, 요청 SHA-256으로 맞춰 이미 낸 것으로 셉니다. 채점 요청은 두 답도 담으므로 맞을 수 없습니다. 옛 기록(8326cee)과 새 기록이 이제 같은 방식으로 셉니다. 테스트는 한도 2인 한 경우로 다시 합쳤고 통과합니다. `tests/golden/test_validation.py`, `test_experiment.py`, `test_cli.py`는 137 passed, `test_improvement.py`는 41 passed였습니다. 전체 검사는 서버가 돌리며 아직 기다리는 중입니다.

7회차(F5), 위에서 되살린 F6 조사에 대해. 그 실험의 첫 경우는 위의 `(True, 2)` 실행입니다. `f0ddd69` 전에는 `[('E1','E2')]`만 보내고 `call_cap`에서 멈췄고, 수정 뒤에는 한도 2로 `(E1,)`과 `(E2,)`를 보내고 auto_validated로 끝납니다. 빠져 있던 부정 경우는 이제 `tests/golden/test_validation.py::test_a_settled_judge_call_does_not_count_as_a_paid_validator_call`입니다. 같은 질문과 근거에 대한 채점 호출만 저장하고, multi_hop 후보가 여전히 검증기 호출 3번이 모두 필요하다고 기대합니다. 저장된 attempt-0 호출을 모두 세면(택하지 않은 방법) 2가 됩니다. 반대 근거 (3), 센 요청과 보낸 요청의 어긋남은 실제로 해당했습니다. `_single_unit_verdict`가 머리글을 붙인 단일 단위를 따로 만들고 있었습니다. 이제 둘 다 `validation._single_units`에서 가져오며, 답할 수 없음은 이미 `document_batches`를 함께 썼습니다. `tests/golden/test_validation.py`, `test_cli.py`, `test_improvement.py`가 통과했습니다(다른 163개 테스트, 그다음 부정 경우와 이어하기 테스트 2 passed). 이 안내를 담은 커밋에 있습니다.

## 남은 한계

6회차 지적 글을 볼 수 없었으므로, 이 모양들은 리뷰어의 말이 아니라 코드를 읽어서 얻었습니다. 한국어 로캘에서 Excel의 정확한 저장 동작은 확인하지 않았습니다. Python 3.11부터의 NUL 지원은 CPython 릴리스 안내가 아니라 하위 배포판 패치 메모에서 왔으며, venv가 3.10을 넘어갈 때만 의미가 있습니다. judgments.csv가 있을 때 key.json이 없거나 잘못되면 여전히 242행에서 오류가 납니다. review_packets가 두 파일을 함께 쓰고 key.json은 고치는 파일이 아니므로 뺐지만, 엄격한 리뷰어는 이를 '어떤 모양이든'에 넣을 수 있습니다. csv.field_size_limit(131072자를 넘는 필드)도 csv.Error를 내며, 같은 예외 처리로 다뤄집니다.
