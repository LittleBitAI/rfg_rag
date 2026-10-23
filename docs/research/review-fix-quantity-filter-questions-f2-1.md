# 리뷰 조사 · F2, 1회차

집계 결과와 측정 조건은 Git에 보관하고, 실제 질문·정답·근거·OCR 텍스트와 레코드별 내보내기는 Git에서 제외된 로컬 `artifacts/`에 보관합니다.

복원 출처: 정리 전 `artifacts/review-round2/originals/` 또는 `d7d1682^`. 아래 수치와 검증 기록은 당시 실행에서 관측한 과거 기록이며, 이번 작업에서 다시 측정한 결과가 아닙니다.

PR #63 리뷰 2회차의 수정 전에 2026-10-17에 쓴 조사 초안입니다. 검증된 사실이나 공용 규칙이 아니며, 리뷰는 이 문서를 수정과 함께 읽습니다.

## 문제

F2는 선언된 단위 물려받기를 깹니다. 표의 숫자 칸은 지원하는 행 서식이 무엇이든 그 열의 단위 배율, 항목 이름, 원문 위치를 유지해야 합니다. 첫 수정은 선언 상태를 되살렸지만, 지금 파서는 양끝 파이프(`|`)와 줄바꿈 때문에 칸 수가 부풀면 줄어든 합계 행을 여전히 버릴 수 있습니다. 구성 항목 행은 남아 있어 문서 값이 될 수 있습니다. [C1, C2, C4]

발생: 반복, 1·2회차.

- [P1] [P1] rag/retrieval/quantity_metadata.py:41 — 표준 Markdown 표의 줄어든 행에서 선언 단위를 여전히 놓칩니다

## 실패한 수정

- 588577d에서, 받은 리뷰에 따르면 선언처럼 보이는 통화 배율은 금액으로 쓰지 않도록 막혔지만 숫자 칸에 물려주도록 남지도 않았습니다. 따로 떨어진 잘못된 금액은 막았지만 실제 예산도 잃었습니다. 수정 보고서가 이 재현을 확인합니다. 과거 코드는 diff 도구로 따로 확인할 수 없었습니다. [C2]
- 1회차 수정은 열 선언, 앞선 기본 선언, 배율 적용, 원문 위치, 구성 항목 이름표, 줄어든 행 다시 맞추기를 더했습니다. 원래 예시는 고쳤지만, 다시 맞추기는 논리적인 행 너비가 아니라 정규식 일치 개수에 기댑니다. 머리글 파싱은 양끝 문법을 잘라 내지만, 암묵적 데이터 칸 파싱은 그러지 않습니다. [C2, C3]
- 줄어든 합계 회귀 테스트는 파일 끝에 양끝 파이프 없이 '계 | 200,000'을 씁니다. 숫자 칸은 두 일치 중 두 번째로 남아, 세 번째 머리글 열로 다시 맞춰집니다. 뒤쪽 파이프 다음의 추가 일치는 한 번도 시험하지 않으므로, 수정 보고서의 더 넓은 줄어든 행 주장을 뒷받침하지 못합니다. [C3, C5]

## 출처

### S1 — 수량 메타데이터 추출

- URL: rag/retrieval/quantity_metadata.py
- 확인일: 2026-10-17
- 위치: 32–55행, 135–137행, 158–171행, 202–223행
- 인용: if count < len(declarations):
    remaining = [i for i in range(column, len(declarations)) if declarations[i] is not None]
    return remaining[0] if len(remaining) == 1 else None
return column

cells = list(re.finditer(r"[^|]+", line))

for line in body.splitlines(keepends=True):
    quantities = [(quantity, None) for quantity in _read(line)]
    if "|" in line:
        quantities.extend(_implicit_cells(line, headers, declarations, default))
        if not quantities and re.search(r"[가-힣]", line):
            cells = list(re.finditer(r"[^|]+", line.strip().strip("|")))

 offset += len(line)
- 적용: 데이터 칸을 날것 그대로 세는 것, 조건부 다시 맞추기, 머리글과 다른 정규화, 날것 줄 기준 위치 계산을 보여 줍니다. 수량을 하나도 못 찾은 한글 이름표 행은 머리글 교체로 들어갈 수도 있습니다.
- 반대 근거: 열 다시 맞추기가 실패해도 기본 선언이 단위를 줄 수 있고, 단위를 명시한 수량은 다른 경로를 탑니다.
- 검증: 실패하는 행의 칸 위치와 목표 열을 살핀 뒤, 서식과 관계없는 값, 이름표, 원문 조각을 확인합니다.

### S2 — 선언 단위와 줄어든 합계 회귀 테스트 데이터

- URL: tests/test_quantity_filter.py
- 확인일: 2026-10-17
- 위치: 68–73행과 374–420행
- 인용: def embed_query(self, text):
    return [1, 0] if "예산" in text else [0, 1]

text = ("예산과목 | 주요 내용 | 예산(천원)\n"
        "전산개발비 | 시스템 구축 | 140,000\n장비비 | 장비 구입 | 60,000\n계 | 200,000")
rows = quantity_rows([chunk("a", text)])
assert [(row["value"], row["phrase"]) for row in rows] == [
    (140000000, "사업 예산 전산 개발비"), (60000000, "사업 예산 장비 비"), (200000000, "사업 예산 계")]
assert all(text[slice(*row["span"])] == row["original"] for row in rows)
- 적용: 의도한 구성 항목/합계 추출을 정하고, 양끝 파이프와 줄바꿈 경우가 빠졌다는 것을 드러냅니다. 근처 테스트가 선언 배율, 명시 단위, 적용 범위를 다룹니다.
- 반대 근거: 이 테스트 데이터는 구분자 없는 파일 끝 표기를 실제로 다룹니다. 임시 임베딩은 예산 항목 간 유사도를 구별하지 못합니다.
- 검증: 이 동작 회귀 테스트를 보고된 표기로 넓히고, 이름표와 위치 확인은 그대로 둡니다.

### S3 — 문서로 정한 수량 필터 약속

- URL: README.md
- 확인일: 2026-10-17
- 위치: 46–61행
- 인용: Declared column units and a preceding `(단위: 천원)` apply to numeric table cells: `사업예산(천원) | 부문` followed by `10 | 운영` yields 10,000 won. The metadata preserves both the numeric cell and its unit declaration spans; the context displays `10 (천원)`. Explicit cell units take precedence, and inherited units end with the table or chunk. Component row labels remain distinct from a shortened total row.

Values without an accepted matching field can still be omitted, and conflicting values within one document are not semantically reconciled.
- 적용: 단위 물려받기, 원문 출처, 적용 범위, 서로 다른 이름표를 의도한 동작으로 정합니다. 46행은 추출이 바뀌면 인덱스를 다시 만들라고도 요구합니다.
- 반대 근거: 이 약속은 뜻 기반 조정을 분명히 제한하며, 합계가 언제나 모든 구성 항목보다 앞선다고 약속하지 않습니다.
- 검증: 추출과 화면에 보이는 근거를 확인한 뒤, 앱 동작을 평가하기 전에 저장된 수량 인덱스를 다시 만듭니다.

### S4 — 1회차 수량 수정과 검증 보고서

- URL: docs/quantity_filter_validation.md
- 확인일: 2026-10-17
- 위치: 리뷰 1회차, 5–23행
- 인용: Both a column declaration `사업예산(천원)` and a preceding `(단위: 천원)` lost numeric-only cells.

Shortened total rows retain their column unit, and component labels prevent a partial cost from replacing the project's total.

Of 119 chunks with parenthesized currency declarations and tables, 4 documents gained 8 inherited numeric rows. Seven have labels; one KOICA row remains unlabelled and cannot supply a budget.

The paid answers and user-reported browser acceptance below predate these review repairs. They remain historical evidence for those saved contexts, not new paid or browser acceptance of the repaired contexts.
- 적용: 앞선 실패, 시도한 수정, 전수 조사, 승인 근거의 한계를 기록합니다.
- 반대 근거: 박물관 합계 확인이 성공했고 네 질의의 선택 값이 바뀌지 않았다고 보고합니다. 그 기록이 2회차 서식까지 다룬다는 근거는 되지 않으며, 그 산출물은 여기서 볼 수 없었습니다.
- 검증: 정확히 실패하는 표기를 더한 뒤 관련 오프라인 비교를 다시 하고, 합계가 그대로라고 가정하지 말고 바뀐 값과 제외를 보고합니다.

### S5 — 문서 값 선택

- URL: rag/retrieval/quantity_filter.py
- 확인일: 2026-10-17
- 위치: 126–158행
- 인용: if row["doc_id"] not in chosen or row["similarity"] > chosen[row["doc_id"]]["similarity"]:
    chosen[row["doc_id"]] = row

eligible = [{**r, "similarity": float(similarities[r["phrase"]])} for r in rows
            if _usable(r) and similarities[r["phrase"]] >= cutoff]

chosen = _document_values(eligible, unit)
matched = [r for r in chosen.values() if condition.accepts(r["value"])]
- 적용: 합계 추출이 실패하면 남은 구성 항목이 문서 값이 되어 기준값 일치를 바꿀 수 있음을 설명합니다.
- 반대 근거: 구성 항목도 쓸 수 있음, 단위, 유사도 조건을 만족해야 합니다. 추출된 합계도 자동으로 우선되지는 않습니다.
- 검증: 통제한 서로 다른 항목 유사도를 써서, 빠진 합계를 되찾는 효과만 따로 봅니다.

### S6 — Python 3.10 str.splitlines 문서

- URL: https://docs.python.org/3.10/library/stdtypes.html#str.splitlines
- 확인일: 2026-10-17
- 위치: str.splitlines, 893–919행
- 인용: Line breaks are not included in the resulting list unless keepends is given and true.
- 적용: _chunk_rows()는 keepends=True를 명시하므로, 각 날것 줄에 LF와 CRLF가 남습니다.
- 반대 근거: 줄 끝을 남기는 것은 원문 위치 계산에 쓸모 있으며, 그 자체가 오류는 아닙니다.
- 검증: 날것 합계 줄에 줄 끝이 들어 있는지 확인하고, 칸 파싱을 바꾼 뒤에도 뒤쪽 위치를 유지합니다.

### S7 — Python 3.10 정규식의 여집합 문자 집합

- URL: https://docs.python.org/3.10/library/re.html#regular-expression-syntax
- 확인일: 2026-10-17
- 위치: Regular Expression Syntax, complemented sets, 82행
- 인용: If the first character of the set is '^', all the characters that are not in the set will be matched.
- 적용: 실제 패턴 [^|]+는 칸 내용뿐 아니라 줄바꿈과 바깥 공백도 받아들입니다.
- 반대 근거: 뒤쪽 파이프가 없으면 줄 끝은 새 조각을 만들지 않고 앞 칸 일치 안에 남습니다.
- 검증: 뒤쪽 파이프와 줄 끝이 있을 때와 없을 때 합계 행의 칸 일치를 비교합니다.

### S8 — GitHub Flavored Markdown 명세

- URL: https://github.github.com/gfm/#tables-extension-
- 확인일: 2026-10-17
- 위치: 4.10절; 표 인식과 예제 204
- 인용: If there are a number of cells fewer than the number of cells in the header row, empty cells are inserted.
- 적용: 구조 비교 기준이 됩니다. GFM 표로 인식되려면 머리글과 구분 행의 너비가 같아야 하고, 짧은 본문 행은 빈 칸으로 채우며 넘치는 칸은 무시합니다. 예제 204는 빈 칸을 기존 칸 뒤에 둡니다.
- 반대 근거: 이 저장소는 구분 행 없는 평평한 표를 받아들이고, 줄어든 행을 선언된 유일한 열로 다시 맞춥니다. 이 동작은 GFM에서 나오지 않습니다.
- 검증: 제대로 된 구분 행이 있는 경우를 더하되, 저장소의 기존 구분 행 없는 회귀 테스트와 명시적 복구 기대값은 유지합니다.

### S9 — GitHub Docs: 표로 정보 정리하기

- URL: https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/organizing-information-with-tables
- 확인일: 2026-10-17
- 위치: Creating a table, 46행
- 인용: The pipes on either end of the table are optional.
- 적용: 바깥 파이프를 추가 데이터 열이 아니라 행 문법으로 다룰 근거가 됩니다.
- 반대 근거: 이 서식 안내는 통화 단위 물려받기나 평평하게 펼친 병합 칸 복구를 정하지 않습니다.
- 검증: 바깥 파이프만 다른 같은 행을 비교해, 수량 메타데이터가 같아야 합니다.

## 주장

- C1 (해석; S2, S3): 선언된 표 숫자 값은 지원하는 줄어든 합계 표기를 포함해 배율, 항목 이름, 원문 출처를 유지해야 합니다.
- C2 (출처; S1, S4): 수정 보고서는 원래의 선언 손실을 확인하며, 지금 구현은 선언 상태 유지, 배율 적용, 줄어든 행 복구를 더합니다.
- C3 (해석; S1, S6, S7): 기본 선언 없이 뒤쪽 파이프와 줄바꿈이 있는 합계 행에서는, 지금 코드가 가짜 세 번째 칸을 만들고 다시 맞추기를 건너뛰어 금액을 빠뜨릴 것으로 예측됩니다. 온전한 구성 항목 행은 그대로 추출됩니다.
- C4 (해석; S2, S3, S5): 합계 메타데이터가 빠지면 선택되는 문서 값과 일치가 바뀔 수 있습니다. 하지만 선택이 항목 유사도를 쓰고 동점이면 첫 행을 남기므로, 되찾는다고 합계가 우선된다는 보장은 없습니다.
- C5 (출처; S2): 기존 줄어든 합계 회귀 테스트는 파일 끝의 구분자·바깥 파이프 없는 행을 다루고, 근처의 긍정 테스트가 배율, 위치, 명시 단위, 적용 범위를 다룹니다.
- C6 (출처; S6, S7, S9): Python은 keepends=True일 때 줄 끝을 남기고, 파이프 여집합은 그 줄 끝도 받아들이며, Markdown 표의 바깥 파이프는 선택 사항입니다.
- C7 (해석; S1, S2, S8): GFM의 짧은 행 채우기는 저장소의 뒤쪽 열 다시 맞추기를 정당화하지 않습니다. 다시 맞추기는 평평한 입력을 위한 이 분야의 복구 휴리스틱입니다.
- C8 (해석; S1, S2, S5, S6, S8, S9): 수정은 칸을 세기 전에 일관된 칸 경계를 정하고, 원래 위치와 안쪽 빈 칸 자리를 유지하며, 선택 정책을 넓히지 않고 서식에 관계없이 같은 결과인지 확인해야 합니다.
- C9 (해석; S2, S4): 1회차의 코퍼스 확인은 기록된 입력에 대해서는 근거가 되지만, 그 범위와 과거 승인에 대한 단서 때문에 2회차 표기까지 다룬다고 볼 수는 없습니다.
- C10 (출처; S3): 추출이 바뀌면, 앱 결과로 수정이 적용됐다고 보기 전에 저장된 수량 인덱스를 다시 만들어야 합니다.

## 핵심 원리

Python은 splitlines(keepends=True)를 쓰면 줄 끝을 남기고, 여집합 문자 집합은 지정한 문자만 뺍니다. 파이프를 뺀다고 줄바꿈이 빠지지는 않습니다. Markdown의 양끝 파이프는 선택 문법입니다. 그래서 칸 수로 열을 추론하기 전에 논리적 칸부터 정해야 합니다. 별개로, GFM은 짧은 행을 빈 칸으로 채울 뿐 두 번째 칸의 금액을 세 번째 예산 열로 옮기라고 하지 않습니다. 그 옮기기는 이 저장소의 평평한 표 복구 휴리스틱입니다. [C6, C7]

## 적용

_cell_column()이 행 너비를 재기 전에, _implicit_cells()가 쓰는 행 경계 해석을 고칩니다. 머리글과 데이터 파싱은 선택적인 바깥 파이프와 바깥 공백에 대해 같은 판단을 하되, 원래 줄 안의 위치는 유지해야 합니다. 진짜 안쪽 빈 칸은 자리를 유지합니다. 공백뿐인 조각을 모두 지우면 또 다른 정렬 오류가 생깁니다. 줄어든 행의 유일한 선언 열 제한, 명시 단위 우선, 구성 항목 이름표, 선언 적용 범위는 그대로 둡니다. 나머지 세 칸 파싱 지점도 일관성을 점검하되, 이 수정을 일반 Markdown 파서로 키우지는 않습니다. 확인한 뒤에는 화면 결과를 판단하기 전에 수량 메타데이터와 구문 임베딩을 다시 만듭니다. [C3, C8, C10]

## 가설

남은 결함은 열을 정하기 전의 칸 구조 파싱이 일관되지 않은 것입니다. '| 계 | 200,000 |\n'에서 keepends=True는 줄바꿈을 _implicit_cells()에 넘기고, [^|]+는 [' 계 ', ' 200,000 ', '\n']에 일치합니다. 선언이 세 개이면 _cell_column(1, 3, declarations)은 예산 열 2로 다시 맞추지 않고 열 1을 돌려줍니다. 기본 선언이 없으면 금액이 빠집니다. 온전한 구성 항목 행은 여전히 열 2에 닿아 남습니다. 코드를 읽어서 따라간 것이며, 실행으로 확인하기를 기다립니다. [C3]

## 반대 근거

- 원래의 선언 예시에는 이제 배율, 위치, 적용 범위를 확인하는 긍정 회귀 테스트가 있습니다. 선언 상태 수정은 실질적이며, 전혀 효과가 없는 것은 아닙니다. [C2, C5]
- 수정 보고서는 박물관의 2억 원 합계가 유지되고 네 질의의 선택 값이 바뀌지 않았다는 오프라인 코퍼스 확인을 기록합니다. 그 기록된 입력에 대해서는 근거가 되지만, 있는 테스트 데이터에는 실패하는 양끝 파이프 표기가 없습니다. 언급된 실행 산출물은 추적되는 파일로 볼 수 없었습니다. [C5, C9]
- 정확한 누락 경로는 앞선 기본 선언이 없다고 가정합니다. 기본 선언이 있으면 항목이 잘못 붙더라도 단위는 물려받을 수 있습니다. [C3]
- 합계를 되찾아도 선택된다는 보장은 없습니다. 선택기는 유사도가 가장 높은 쓸 수 있는 항목을 고르고 동점이면 첫 행을 남기며, 지금 테스트 임베딩은 예산 구문에 같은 벡터를 줍니다. 선택 동작은 통제한 유사도나 기존 로컬 모델로 따로 확인해야 합니다. [C4]
- 엄격한 GFM이라면 이 줄어든 행의 세 번째 열은 비어 있게 됩니다. 원하는 합계 복구는 Markdown 의미만이 아니라 저장소가 문서로 정한 추출 동작에서 나옵니다. [C1, C7]

## 다른 방법

- Kiwi 토큰화나 통화 배율 인식을 바꾸는 것은 첫 수정이 아닙니다. 긍정 회귀 테스트에서 선언 인식은 성공하고, 실패하는 분기는 숫자 배율 적용 전에 설명됩니다. [C3, C5]
- 정규식에서 줄바꿈 문자만 빼면 보고된 LF 경우는 해결되지만, 뒤쪽 파이프 뒤의 바깥 공백과 앞쪽 파이프 앞의 들여쓰기가 여전히 칸 수를 부풀릴 수 있습니다. 문자 하나가 아니라 구조적 경계를 다뤄야 합니다. [C3, C6, C8]
- splitlines()가 줄 끝을 버리도록 전체를 바꾸면, _chunk_rows()가 len(line)만큼 위치를 옮기므로 뒤쪽 원문 위치가 틀어질 위험이 있습니다. 날것 줄 계산은 유지하고 그 안에서 칸을 파싱합니다. [C3, C8]
- 비었거나 공백뿐인 칸을 모두 버리면 바깥 문법과 진짜 빈 열을 혼동합니다. 안쪽 자리는 유지합니다. [C7, C8]
- 구성 항목 합산, 가장 큰 금액 고르기, 합계 우선 선택은 문서 값 정책을 바꾸며 빠진 메타데이터를 고치지 못합니다. 추출부터 고치고, 선택 결함이 따로 남는지 잽니다. [C4]
- 완전한 Markdown 파서는 드러난 결함에 비해 과하고, 평평하게 펼친 병합 칸을 저절로 복구하지도 않습니다. 기존 테스트 데이터는 GFM 구분 행 없는 파이프 구분 표도 일부러 받아들입니다. [C5, C7]

## 실험

이번 읽기 전용 조사에서는 테스트를 돌리지 않았습니다. 구현 단계에서는 기존 줄어든 합계 회귀 테스트를 '| 예산과목 | 주요 내용 | 예산(천원) |\n| --- | --- | --- |\n| 전산개발비 | 시스템 구축 | 140,000 |\n| 장비비 | 장비 구입 | 60,000 |\n| 계 | 200,000 |\n다음 본문'으로 넓힙니다. 고치기 전에 합계의 날것 일치에 세 번째 줄바꿈 조각이 있고 숫자 목표 열이 1인지 확인합니다. 구성 항목은 남고 합계는 빠질 것으로 예상합니다. 고친 뒤에는 '사업 예산 계' 이름표가 붙은 200000000원을 포함해 의도한 금액 행 세 개가 정확히 나와야 하고, 숫자와 선언 위치가 원문을 그대로 잘라 내야 합니다. LF, CRLF, 파일 끝, 뒤쪽 바깥 공백이 있는 양끝 파이프 경우를 비교하고, 기존 구분자 없는 형식도 유지합니다. 과하게 잘라 내는지 잡기 위해 안쪽 빈 칸이 명시된 행을 하나 넣습니다. 기존 명시 단위와 적용 범위 회귀 테스트도 다시 돌립니다. 뒤쪽 확인에서는 합계에 구성 항목보다 높은 통제 유사도를 주고 기준값을 1억 4천만과 2억 사이로 정해, 선택된 원래 값과 일치가 서식에 관계없이 같은지 확인합니다. 기존의 같은 벡터 예산 임시 임베딩으로 합계 우선을 추론하지 않습니다. 끝으로 영향받는 테스트와 저장소 필수 검사를 돌리고, 기록된 코퍼스 질의에 대해 영향받는 수량 메타데이터와 임베딩을 다시 만듭니다. [C3, C4, C5, C8, C10]

## 결과

`684c463`에서 고치기 전에 관측한 결과, 합계의 날것 일치는 `[' 계 ', ' 200,000 ', '\n']`였고 숫자 목표 열은 1이었으며, 1억 4천만/6천만 구성 항목만 남았습니다(`artifacts/quantity_review2_before.log`). 수정은 이 초안과 함께 고유 제목 `retrieval: fix table boundaries, project routing and index rollback`(부모 `684c463`)으로 커밋됐습니다. `tests/test_quantity_filter.py::test_declared_table_units_preserve_component_labels_and_collapsed_total_cells`는 원래의 구분자 없는 파일 끝 형식을 포함해 서식·빈 칸 경우 열 가지를 확인합니다. `test_interior_empty_cells_keep_positions_between_different_declared_units`는 열 이름을 확인하고, `test_table_units_are_column_specific_and_end_with_the_table`은 명시 단위와 적용 범위를 계속 다룹니다. 숫자와 선언 위치는 원문을 그대로 잘라 냅니다. 통제한 유사도에서는 합계가 우선되고, 1억 5천만 기준값은 모든 경우에 2억을 돌려줍니다. 영향받는 파일 열 개 실행은 694개 테스트가 통과했고 경고는 12개였습니다. 원래의 구분자 없는 형식을 명시적으로 남긴 뒤, 바뀐 테스트 파일은 130개 테스트를 12.06초에 다시 모두 통과했습니다. 표가 있는 청크 13,627개(선언이 있는 것 6,968개)를 모두 다시 만들었을 때 바뀐 코퍼스 행은 0개였습니다. 결과로 나온 구문 11,949개를 다시 임베딩해도 네 질의의 값·개수·제외와 dev 문맥 ID 순서 60개가 모두 그대로였습니다. 로그: `artifacts/quantity_review2_cleanup_gate.log`, `quantity_review2_final_test_cleanup.log`, `quantity_review2_scope.log`, `quantity_review2_offline.log`. 기록된 구현 관측이며, 이 문서는 여전히 초안이고 검증된 결과나 공용 규칙이 아닙니다.

## 남은 한계

조사할 때는 받은 리뷰로 시간 순서를 정했고, 과거 diff 조회는 실패했으며, 지금 동작은 코드를 읽어서만 따라갔습니다. 위 구현 관측이 이제 실행 범위와 로컬 코퍼스 전수 조사를 기록하지만, 생성된 산출물은 로컬에만 있고 추적되는 소스 근거가 아닙니다. 애매한 줄어든 행, 이스케이프된 파이프, 일반적인 병합 칸 복구는 드러난 수정 범위 밖에 남습니다. 유사도 정책은 합계가 모든 구성 항목보다 앞선다고 보장하지 않습니다. 여전히 가설과 실험 기록 초안이며, 따로 검증된 수정이 아닙니다. [C3, C7, C9]
