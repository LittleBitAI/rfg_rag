# 리뷰 조사 · F2, 2회차

집계 결과와 측정 조건은 Git에 보관하고, 실제 질문·정답·근거·OCR 텍스트와 레코드별 내보내기는 Git에서 제외된 로컬 `artifacts/`에 보관합니다.

복원 출처: 정리 전 `artifacts/review-round2/originals/` 또는 `d7d1682^`. 아래 수치와 검증 기록은 당시 실행에서 관측한 과거 기록이며, 이번 작업에서 다시 측정한 결과가 아닙니다.

PR #63 리뷰 3회차의 수정 전에 2026-10-17에 쓴 조사 초안입니다. 검증된 사실이나 공용 규칙이 아니며, 리뷰는 이 문서를 수정과 함께 읽습니다.

## 문제

F2는 표에 선언된 단위와 항목 이름이 언제까지 유지되느냐의 문제입니다. 숫자 칸은 앞선 데이터 행에 쓸 수 있는 수량이 없더라도, 지원하는 표 경계까지 지금 열 구성(스키마)을 물려받아야 합니다. 지금 코드에서는 '사업명 | 사업예산(천원)\n--- | ---\nA 사업 | -\nB 사업 | 100'이 'A 사업 | -'에서 예산 선언을 잃어 100,000원을 되찾지 못할 것으로 예측됩니다. 문서로 정한 물려받기 약속을 어기며, 문서 선택이나 제외 수를 바꿀 수 있습니다. [C1, C4, C9]

발생: 반복, 2·3회차.

- [P1] [P1] rag/retrieval/quantity_metadata.py:218 — 값이 비어 있는 데이터 행이 선언 단위 상태를 지움 / 선언 단위 표에서 앞 행의 값이 `-`인 경우 / 이후 숫자 셀이 색인에서 누락됨

## 실패한 수정

- 원래 구현은 선언처럼 보이는 통화 배율을 따로 떨어진 금액으로 쓰지 않게 막았지만, 숫자 칸에 물려주도록 남기지도 않았습니다. 1회차 수정은 열/기본 선언, 배율 적용, 원문 출처를 더했습니다. 원래의 누락은 고쳤지만, 수량을 하나도 못 뽑은 한글 파이프 행을 새 머리글로 보는 규칙은 남겼습니다. 앞선 조사가 이 규칙을 기록했고, 지금 코드에도 그대로 있습니다. [C2, C3]
- 1회차의 줄어든 합계 테스트 데이터는 바깥 파이프를 빼고 합계를 파일 끝에 두었습니다. 그래서 뒤쪽 줄바꿈이 추가 칸으로 세어져 줄어든 열 복구를 막는 문제를 드러내지 못했습니다. 앞선 조사와 수정 보고서가 이 별개의 실패를 기록합니다. [C2]
- 2회차 수정은 칸 파싱을 _cells()로 모아, 안쪽 빈 칸은 남기고 바깥 문법을 잘라 냈습니다. 넓힌 테스트는 서식과 정렬을 시험하지만, 구성 항목/합계 데이터 행에는 모두 되찾을 수 있는 수량이 있습니다. 따로 있는 빈 칸 테스트 데이터에도 되찾을 수 있는 예산이 있습니다. 수량이 전혀 없는 한글 데이터 행 뒤에 숫자 행이 오는 경우는 하나도 시험하지 않습니다. 그래서 칸 경계는 바로잡았지만, 상태를 지우는 머리글 전환은 그대로 남았습니다. [C3, C5]
- 기록된 2회차 코퍼스 비교에서 바뀐 수량 행은 없었고, 기존 검색 결과도 유지됐습니다. 이 관측은 시험한 코퍼스와 서식 수정에 대한 근거이지, 값이 빠진 행을 지나도 선언 상태가 남는다는 근거는 아닙니다. 언급된 실행 산출물은 이번 조사에서 볼 수 있는 추적 파일이 아닙니다. [C12]

## 출처

### S1 — 수량 메타데이터 추출과 표 상태 변경

- URL: rag/retrieval/quantity_metadata.py
- 확인일: 2026-10-17
- 위치: 15–64행, 143–145행, 166–180행, 210–236행
- 인용: quantities.extend(_implicit_cells(line, headers, declarations, default))
if not quantities and re.search(r"[가-힣]", line):
    cells = _cells(line)
    headers = [cell[0].strip() for cell in cells]
    declarations = [_declared_unit(cell[0], offset + cell.start()) for cell in cells]

else:
    declared = _declared_unit(line, offset) if "단위" in line else None
    default = declared if headers or declared else default
    headers, declarations = [], []

_implicit_cells()의 선언 대체 경로:
declaration = declaration or default
number = NUMBER_CELL.fullmatch(cell[0])
if declaration is None or number is None:
    continue
- 적용: 상태를 지우는 전환, 기본 단위가 가리는 경로, 항목/단위 짝 물려받기, 기존 파이프 없는 행 초기화를 담고 있습니다. _cells()는 이미 바깥 파이프를 처리합니다.
- 반대 근거: 명시 단위와 기본 선언은 어떤 경우에는 수량 추출을 지킬 수 있습니다. 지금 스키마를 가리지 않고 유지하면 진짜 뒤쪽 머리글을 막을 수 있습니다.
- 검증: 정확한 입력을 한 줄씩 따라간 뒤, 수량 없는 행을 지나도 항목 이름과 선언이 함께 유지되고 지원하는 경계에서 초기화되는지 확인합니다.

### S2 — 수량 필터 회귀 테스트 데이터

- URL: tests/test_quantity_filter.py
- 확인일: 2026-10-17
- 위치: 279–285행, 374–436행, 458–463행
- 인용: 선언 단위 데이터: ("사업예산(천원) | 부문\n10 | 운영", 10000, "원", "사업 예산")

적용 범위 데이터:
text = ("(단위: 천원)\n사업예산 | 사업기간(개월)\n10 | 5\n20원 | 6개월\n"
        "다음 본문\n사업예산 | 부문\n30 | 운영")

경계 데이터:
lines = ["예산과목 | 주요 내용 | 예산(천원)",
         "전산개발비 | 시스템 구축 | 140,000", "장비비 | 장비 구입 | 60,000", total]

안쪽 빈 칸 데이터:
text = "| 사업기간(개월) | 부문 | 예산(천원) |\n||운영|200,000|\n다음 본문"
- 적용: 기존의 배율, 일반 머리글, 명시 단위, 적용 범위, 서식, 빈 열 동작을 정합니다. 빈 열 행에도 되찾을 수 있는 수량이 있습니다.
- 반대 근거: 앞선 결함에 대한 의미 있는 회귀 테스트입니다. 이 테스트가 있다고 해서, 다른 행 앞의 수량이 전혀 없는 데이터 행까지 다룬다는 뜻은 아닙니다.
- 검증: 보고된 순차 상태 전환과 기준 경우와의 동등성을 더하되, 기존 확인은 그대로 둡니다.

### S3 — 문서로 정한 수량 필터 물려받기·선택 약속

- URL: README.md
- 확인일: 2026-10-17
- 위치: 46–65행
- 인용: Declared column units and a preceding `(단위: 천원)` apply to numeric table cells: `사업예산(천원) | 부문` followed by `10 | 운영` yields 10,000 won. The metadata preserves both the numeric cell and its unit declaration spans; the context displays `10 (천원)`. Explicit cell units take precedence, and inherited units end with the table or chunk. Component row labels remain distinct from a shortened total row.

A shortened total still uses the existing unique-declared-column recovery; this does not infer arbitrary merged cells or prefer totals over fields with higher similarity.

Values without an accepted matching field can still be omitted, and conflicting values within one document are not semantically reconciled.
- 적용: 단위/이름표 출처, 우선순위, 적용 범위를 정합니다. 46행은 수량 추출이 바뀌면 인덱스를 다시 만들라고 요구합니다.
- 반대 근거: 이 약속은 병합 칸 추론과 뜻 기반 조정을 제한하고, 합계 우선을 보장하지 않습니다.
- 검증: 되찾은 숫자 값과 원래 위치를 확인하고 적용 범위/우선순위 회귀 테스트를 유지한 뒤, 앱 결과를 판단하기 전에 영향받는 저장 메타데이터와 임베딩을 다시 만듭니다.

### S4 — 기록된 1·2회차 수정과 검증

- URL: docs/quantity_filter_validation.md
- 확인일: 2026-10-17
- 위치: 리뷰 2회차, 5–17행; 리뷰 1회차, 21–39행
- 인용: Four quantity-cell parsing sites now share one boundary/offset reader: inherited numeric cells, explicit quantity reading, field assignment and header declarations. It removes exterior table syntax before counting and retains interior empty cells.

Rebuilding every table-bearing chunk changed zero quantity rows or documents; all 29,339 rows and their numeric/declaration source spans were retained (`artifacts/quantity_filter/review2/scope.json`). The raw boundary-pipe omission is a demonstrated regression fixture, not a claimed change to this corpus's selected budgets.

Both a column declaration `사업예산(천원)` and a preceding `(단위: 천원)` lost numeric-only cells.

The paid answers and user-reported browser acceptance below predate these review repairs. They remain historical evidence for those saved contexts, not new paid or browser acceptance of the repaired contexts.
- 적용: 각 수정이 노린 것, 보고된 확인, 그리고 합성 재현·코퍼스 관측·과거 화면 승인의 구분을 기록합니다.
- 반대 근거: 보고서는 영향받는 테스트가 통과했고 오프라인 결과가 바뀌지 않았다고 기록합니다. 언급된 산출물 로그는 여기서 추적 근거로 볼 수 없고, 따로 다시 돌리지도 않았습니다.
- 검증: 새 전환 재현은 코퍼스 빈도와 따로 보고하고, 마지막 상태 유지 변경 뒤에 비교를 다시 돌립니다.

### S5 — 앞선 F2 조사와 기록된 결과

- URL: docs/research/review-fix-quantity-filter-questions-f2-1.md
- 확인일: 2026-10-17
- 위치: 실패한 수정, 13–17행; 소스 인용, 33–41행; 결과와 남은 한계, 194–200행
- 인용: if "|" in line:
    quantities.extend(_implicit_cells(line, headers, declarations, default))
    if not quantities and re.search(r"[가-힣]", line):
        cells = list(re.finditer(r"[^|]+", line.strip().strip("|")))

수량을 하나도 못 찾은 한글 이름표 행은 머리글 교체로 들어갈 수도 있습니다.

줄어든 합계 회귀 테스트는 파일 끝에 양끝 파이프 없이 '계 | 200,000'을 씁니다.

기록된 구현 관측이며, 이 문서는 여전히 초안이고 검증된 결과나 공용 규칙이 아닙니다.
- 적용: 1회차가 일관되지 않은 칸 세기를 진단할 때 이미 머리글 교체 조건이 있었다는 것을 보여 줍니다. 기록된 결과는 수량 없는 데이터 행을 지나는 선언 유지가 아니라 경계 서식을 다룹니다.
- 반대 근거: 앞선 초안이자 구현 기록이며, 따로 실행한 과거 근거가 아닙니다.
- 검증: 새 회귀 테스트가 앞서 고친 칸 세기 장치가 아니라, 남아 있는 머리글 교체 조건에 닿는지 확인합니다.

### S6 — W3C Model for Tabular Data and Metadata on the Web

- URL: https://www.w3.org/TR/tabular-data-model/
- 확인일: 2026-10-17
- 위치: 1절 Introduction; 4.3 Columns, 4.5 Cells, 6.4 Parsing Cells
- 인용: Each row contains the same number of cells (although some of these cells may be empty)
- 적용: 빠진 칸 값과 열 구조를 구별할 근거가 됩니다. 이 모델은 열 메타데이터와 칸 값을 따로 나타내며, 빈 값과 설정한 null 값도 담습니다.
- 반대 근거: 일반 표 모델이며, 한국어 제안요청서 머리글을 알아보는 알고리즘이 아닙니다. 기본값과 설정한 null 표시가 칸 해석에 영향을 주며, '-'를 언제나 null로 보거나 천원 단위 물려받기를 정하지 않습니다.
- 검증: 수량이 없는 행을 끼워 넣어도 뒤쪽 칸은 정해진 열 구성에 붙어 있어야 하고, 빈 칸에 값을 지어내지 않아야 합니다.

### S7 — GitHub Flavored Markdown 명세

- URL: https://github.github.com/gfm/#tables-extension-
- 확인일: 2026-10-17
- 위치: 4.10절 Tables; 2991–2993행, 3067행, 3126–3139행
- 인용: Each row consists of cells containing arbitrary text

The table is broken at the first empty line, or beginning of another block-level structure:
- 적용: GFM 표로 인식되면, 본문 행인지는 숫자를 뽑았는지에 달려 있지 않습니다. 머리글/구분 행 구조와 블록 경계가 구조적 근거가 됩니다.
- 반대 근거: GFM은 머리글과 구분 행 너비가 같아야 하고, 줄어든 본문 행은 값을 유일한 선언 열로 다시 맞추지 않고 빈 칸으로 채웁니다. 저장소는 구분 행 없는 추출 표도 지원하고 자체 경계 휴리스틱을 쓰므로, GFM은 대체 약속이 아니라 비교 기준입니다.
- 검증: 제대로 된 구분 행 재현을 두되, 저장소의 구분 행 없는 경우와 줄어든 합계 회귀 테스트를 유지합니다.

### S8 — 수량을 쓸 수 있는지와 문서 값 선택

- URL: rag/retrieval/quantity_filter.py
- 확인일: 2026-10-17
- 위치: 135–167행
- 인용: def _usable(row):
    return ((not row["bound"] or row["declared_cap"]) and not row["illustrative"]
            and not row["estimated_price"]
            and row["unit"] and row["phrase"] and (row["unit"] != "원" or row["value"] > 1))

if row["doc_id"] not in chosen or row["similarity"] > chosen[row["doc_id"]]["similarity"]:
    chosen[row["doc_id"]] = row

chosen = _document_values(eligible, unit)
matched = [r for r in chosen.values() if condition.accepts(r["value"])]
- 적용: 값이나 받아들여진 항목을 잃으면 일치가 바뀔 수 있고, 남은 다른 행이 문서 값이 될 수 있는 이유를 설명합니다.
- 반대 근거: 되찾은 행도 쓸 수 있음, 단위, 유사도 조건을 만족해야 합니다. 선택은 합계나 더 큰 금액을 자동으로 우선하지 않습니다.
- 검증: 통제한 유사도로, 되찾은 행이 문서 선택과 기준값 일치에 주는 효과만 따로 봅니다.

### S9 — 저장 수량 인덱스 만들기

- URL: rag/retrieval/indexing.py
- 확인일: 2026-10-17
- 위치: 151–157행, build_quantity_index
- 인용: rows = quantity_rows(chunks)
phrases = list(dict.fromkeys(r["phrase"] for r in rows))
vectors = embedder.encode(phrases, progress=True) if phrases else np.empty((0, 0), dtype=np.float32)
write_jsonl(rows, out_dir / "quantities.jsonl")
(out_dir / "quantity_phrases.json").write_text(json.dumps(phrases, ensure_ascii=False), encoding="utf-8")
np.save(out_dir / "quantity_vectors.npy", vectors)
- 적용: 추출과 구문 변경은 저장되는 행, 구문 이름, 임베딩에 들어갑니다. 소스만 바꿔서는 이미 만든 산출물이 바뀌지 않습니다.
- 반대 근거: 추출 수준 재현에는 전체 의미 검색/BM25 인덱스를 다시 만들 필요가 없습니다. 앱 수준 결론에는 맞는 수량 산출물이 필요합니다.
- 검증: 마지막 변경 뒤에 따로 떨어진 수량 산출물을 만들고, 선택 값, 일치, 제외를 비교합니다.

## 주장

- C1 (해석; S2, S3): 저장소의 선언 단위 약속은 지원하는 표 범위 안에서 열 단위, 항목 이름, 원문 출처가 안정적이기를 요구하며, 명시 단위 우선과 제한된 줄어든 행 복구도 유지합니다.
- C2 (출처; S4, S5): 기록된 수정은 먼저 단위 물려받기를 되살리고, 이어서 바깥 파이프 칸 세기를 바로잡았습니다. 원래 줄어든 합계 회귀 테스트는 뒤쪽 표기를 다루지 않았습니다.
- C3 (출처; S1, S5): 지금 추출 반복문과 앞서 기록된 반복문은 한글 파이프 행에서 수량을 하나도 못 뽑으면 머리글을 바꿉니다. 지금 반복문은 거기서 선언도 바꿉니다.
- C4 (해석; S1): 3회차의 정확한 입력은 대시 행에서 천원 선언을 지우고 뒤의 맨 숫자 100을 빠뜨릴 것으로 코드를 읽어 예측됩니다. 이번 세션에서 실행하지는 않았습니다.
- C5 (해석; S2, S4): 지금 서식과 안쪽 빈 칸 테스트 데이터는 수량이 전혀 없는 한글 데이터 행 뒤에 다른 숫자 행이 오는 경우를 시험하지 않아, 상태를 지우는 전환이 다뤄지지 않습니다.
- C6 (출처; S6, S7): W3C 모델은 안정된 열 안의 빈 칸을 허용하고, GFM은 글로 된 본문 칸을 허용하며 표 경계를 구조로 정합니다. 둘 다 이 저장소의 한국어 단위 물려받기나 평평한 행 복구를 정하지 않습니다.
- C7 (해석; S1, S3, S6, S7): 제한된 수정은 스키마 전환과 수량 추출을 구별해야 합니다. 보통의 수량 없는 데이터 행을 지나도 머리글과 선언을 짝으로 유지하고, 정당한 초기화, 선언 변경, 경계 초기화는 그대로 둬야 합니다.
- C8 (해석; S1, S8): 기본 선언과 명시 칸 단위는 항목 이름을 지키지 못한 채 빠진 숫자 출력을 가릴 수 있으므로, 금액 추출이 성공했다고 유지가 증명되지는 않습니다.
- C9 (해석; S3, S8): 빠지거나 이름표가 잘못된 메타데이터는 쓸 수 있음과 유사도 조건 안에서 문서 선택과 기준값 일치를 바꿀 수 있습니다. 추출을 되살려도 합계 우선은 보장되지 않습니다.
- C10 (출처; S3, S9): 수량 추출은 저장 행, 서로 다른 구문, 구문 벡터를 만들며, README는 추출이 바뀌면 다시 만들라고 요구합니다.
- C11 (해석; S1, S2, S8, S9): 끼워 넣기 전후 실험, 원문 위치 확인, 범위를 정한 경계 대조군, 통제한 뒤쪽 유사도로, 스키마 유지 수정과 항목 손상을 가리기만 하는 숫자 복구를 구별할 수 있습니다.
- C12 (해석; S4, S5): 앞선 문서는 성공한 확인과 바뀌지 않은 코퍼스 결과를 기록하지만 근거 범위를 분명히 제한합니다. 그 기록이 새 빈 값 전환을 따로 보여 주지는 않습니다.

## 핵심 원리

표 구조와 개별 칸 값은 별개의 문제입니다. W3C 모델은 열 위치와 속성 관계를 유지한 채 빈 칸을 허용합니다. GFM은 글로 된 본문 칸을 허용하고 표 경계를 구조로 정합니다. 행에 숫자가 없어도 데이터 행으로 남습니다. 이 출처들은 값이 빠졌을 때 정해진 스키마를 유지하는 것을 뒷받침합니다. 이 저장소의 한국어 단위 인식, 대시의 뜻, 평평한 표 복구 휴리스틱을 정하지는 않습니다. [C6]

## 적용

숫자 파싱에 특수 경우를 더하지 말고, _chunk_rows()에서 지금 표 스키마를 바꾸는 결정을 고칩니다. 정해진 표 안에서는 수량 없는 보통 데이터 행이 머리글과 선언을 모두 유지해야 합니다. 머리글은 표에 들어갈 때 정하고, 정해진 스키마는 머리글/선언 근거가 분명히 있거나 지원하는 표 경계에서만 바꿉니다. 기존의 일반 머리글, 기본 단위, 명시 단위, 줄어든 합계, 원문 위치 동작은 유지합니다. 선언은 유지하지만 머리글은 계속 덮어쓰는 막이는 항목 이름 손상을 남기고, 대시만 예외로 두면 다른 숫자 아닌 값에서 같은 결함이 남습니다. 제안하는 제한된 수정이며, 정확한 머리글 판단식은 기존 지원 입력에 대해 확인해야 합니다. [C7, C8]

## 가설

남은 원인은 추출 성공과 행의 구조적 정체를 섞은 것입니다. quantity_metadata.py:218–221에서 '수량 없음, 한글 있음'이 머리글과 선언을 모두 바꾸게 합니다. 보고된 입력에서 첫 머리글은 열 1에 천원 선언을 정하고, 구분 행은 이를 그대로 두며, 'A 사업 | -'는 수량을 만들지 못해 선언을 [None, None]으로 바꿉니다. 뒤의 맨 숫자 100은 명시 단위도 물려받은 선언도 없으므로 사라집니다. 같은 상태 지우기 조건은 경계 수정 전에도 있었습니다. 받은 리뷰와 맞는 코드 읽기 추적이며, 따로 실행한 재현은 아닙니다. [C3, C4]

## 반대 근거

- 공용 _cells() 읽기는 앞선 바깥 파이프/줄바꿈 문제를 다루며, 지금 회귀 테스트가 그 표기를 다룹니다. 3회차는 스키마 유지에서 남은 다른 실패이며, 경계 수정이 효과가 없었다는 근거가 아닙니다. [C2, C5]
- 앞선 '(단위: 천원)'은 default가 파이프 행 머리글 교체를 지나도 남으므로 빠진 금액을 가릴 수 있습니다. 그래도 열 이름표는 덮어써질 수 있으므로, 숫자 출력만 지키는 것으로는 부족합니다. [C8]
- 명시 칸 단위는 다른 추출 경로를 쓰므로 상태 지우기 전환 뒤에도 행을 만들 수 있습니다. 그래도 물려받은 항목 이름은 잃을 수 있으므로, 추출과 뒤쪽 쓸 수 있음을 따로 확인해야 합니다. [C8, C9]
- 머리글 교체는 지금 구분 행 없는 추출 글에서 머리글을 찾는 데 도움이 됩니다. 모든 머리글을 영원히 고정하면 진짜 뒤쪽 선언을 막을 수 있습니다. 유지는 지금 표로 범위를 좁히고, 기존 경계 초기화와 정당한 선언 변경은 남겨야 합니다. [C7]
- 이번 읽기 전용 세션에서는 실행 확인을 할 수 없었습니다. 보고된 정확한 실패는 지금 제어 흐름과 맞지만, 제안한 교체 정책은 코퍼스에서 실행해 보지 않았습니다. [C4, C11]

## 다른 방법

- '-'를 막거나 빈 값 문자열을 나열: 표기 하나만 고치고, 비었거나 글이거나 그 밖에 파싱할 수 없는 칸에서는 구조 오류가 남습니다. 스키마는 추출 성공과 관계없이 유지해야 합니다. [C7]
- 선언은 유지하되 머리글은 계속 교체: 금액은 되찾을 수 있지만 엉뚱한 항목이 붙어 유사도와 쓸 수 있음에 영향을 줍니다. 여기서는 머리글과 선언이 한 스키마입니다. [C7, C8, C9]
- 열 선언이 없을 때마다 교체 허용: 기본 단위 표에도 안정된 항목 이름이 필요하고, 일반 명시 단위 표도 머리글 물려받기를 씁니다. 이 조건은 표의 정체를 나타내지 못합니다. [C7, C8]
- Kiwi 토큰화나 통화 배율 변경: 기존 긍정 회귀 테스트가 이미 그 장치를 시험합니다. 실패하는 전환은 곱하기 전에 선언을 지웁니다. [C4, C5]
- 칸 경계 파싱을 되돌리거나 넓히기: 지금 공용 읽기는 앞선 세기 결함을 다루고, 보고된 행은 보통의 두 열 구조입니다. 바꿔도 스키마 교체는 고쳐지지 않습니다. [C3, C5]
- 가장 큰 값 고르기, 구성 항목 합산, 합계 우선: 선택 정책을 바꾸며 빠진 추출 메타데이터를 되살리지 못합니다. 기존 선택은 항목 유사도를 쓰고, 유사도가 같으면 첫 행을 남깁니다. [C9]
- 완전한 Markdown 파서 도입: 저장소는 일부러 구분 행 없는 평평한 표와 유일한 선언 열 복구를 지원합니다. 엄격한 GFM만으로는 이 분야 동작을 재현하지 못하고, 이 상태 유지 가설을 시험하는 데 파서 교체는 필요 없습니다. [C1, C6, C7]

## 실험

고치기 전에 리뷰의 정확한 입력과, 'A 사업 | -\n'을 뺀 기준 입력에 quantity_rows를 돌립니다. 줄마다 headers, declarations, default, quantities를 기록합니다. 가설은 기준 입력이 100000원을 내고, 보고된 입력은 대시 행에서 스키마를 바꿔 그 금액을 빠뜨린다고 예측합니다. 선언이 그대로 남거나 누락이 다른 곳에서 일어나면 가설을 버리거나 고칩니다. 고친 뒤에는 수량 없는 데이터 행을 끼워 넣어도 뒤쪽 값, 단위, 구문, 선언 정체가 기준과 같아야 합니다. 절대 숫자 위치는 끼워 넣은 글만큼 옮겨 가되, 저장된 모든 위치는 여전히 자기 원문을 잘라 내야 합니다. 대시 행은 지어낸 금액을 내면 안 됩니다. 드러난 전환은 '-'와 빈 값으로 다루고, 올바른 숫자 데이터 행 뒤에 끼워 넣는 경우도 넣습니다. 양끝 파이프/LF/CRLF는 전체 조합을 반복하지 말고 기존 테스트 데이터로 유지합니다. 이름표 손상을 잡는 기본 단위 경우, 우선순위를 지키는 명시 단위 경우, 단위나 이름표가 새는지 잡는 지원 경계 뒤의 다음 표를 넣습니다. 뒤쪽 확인에서는 받아들여지는 항목 유사도를 통제하고 기준값을 100000원으로 두어, 되찾은 행이 선택 값과 일치 문서를 내야 합니다. 따로 떨어진 산출물에서 수량 행과 구문 임베딩을 다시 만들고, 기존 오프라인 코퍼스 확인에서 바뀐 값, 일치, 제외를 보고합니다. 영향받는 테스트와 저장소 필수 검사는 구현 세션에서 돌립니다. 여기서는 테스트나 코퍼스 재생성을 돌리지 않았습니다. [C11, C10]

## 결과

고치기 전 부모 `51629a7`에서 관측한 결과, 기준 입력은 원래 예산 이름표와 선언으로 100000원을 냈습니다. `A 사업 | -`를 끼워 넣으면 머리글이 데이터 칸으로, 선언이 `[None, None]`으로 바뀌어 뒤쪽 수량이 남지 않았습니다. 줄별 추적은 `artifacts/quantity_review3_before.log`에 있습니다. 수정은 이 초안과 함께 고유 제목 `retrieval: preserve table schemas and whole-project modifiers`로 커밋됐습니다. `tests/test_quantity_filter.py::test_quantity_free_data_rows_preserve_schema_and_later_values`는 대시/빈 값/글, 올바른 행 앞/뒤 위치, 열/기본/명시 단위에 걸친 끼워 넣기 경우 18개를 다루며, 이름표·단위·선언 정체와 옮겨 간 원문 위치를 유지합니다. `test_schema_changes_need_a_declaration_or_table_boundary_and_explicit_units_win`은 지원하는 변경/초기화와 우선순위를 확인합니다. `test_numeric_key_value_rows_are_not_headers`와 `test_declared_headers_do_not_require_every_label_to_have_noun_only_pos_tags`는 중간 구현에서 관측된 문제 두 개를 막습니다. 마지막으로 영향받는 파일 열 개 실행은 740개 테스트가 통과했고, 경고 12개, 54.12초였습니다(`artifacts/quantity_review3_checked_cleanup_gate.log`). 확인한 전수 조사에서 표가 있는 청크 13,627개를 모두 다시 만들었습니다. 청크 185개/문서 79개에 걸쳐 물려받은 행 34개가 더해지고 14개가 빠졌으며, 기존 대상 372개가 바뀌어 행은 29359개가 됐습니다. 통화 금액은 하나도 더해지거나 빠지지 않았고, 통화 행 이름표 21개가 바뀌었습니다. 모든 숫자/선언 원문 위치를 확인했습니다. 이 수는 구현 관측이며, 휴리스틱으로 정한 단위나 항목이 모두 뜻까지 맞다는 주장이 아닙니다. 근거: `artifacts/quantity_filter/review3_checked/scope.json`, `scope_summary.json`, `artifacts/quantity_review3_scope_checked_summary.log`. 이 문서는 여전히 초안이며, 검증된 결과나 공용 규칙이 아닙니다.

마지막 확인 검색 실행은 마지막 코드 변경 뒤에 서로 다른 구문 11,934개를 다시 임베딩했습니다. 실제 질의 네 개는 사업 61/30/44/1개, 제외 10/45/10/10개, 선택된 모든 값을 유지했고, 두 dev 재실행은 문맥 ID 순서 60개를 모두 유지했습니다. 소켓 연결은 막혀 있었고 사용량 CSV는 바이트까지 같았습니다(`artifacts/quantity_review3_offline_checked.log`). 사용 중인 인덱스는 바꾸지 않았습니다. 이 로컬 관측이 따로 하는 리뷰를 대신하지는 않습니다.

## 남은 한계

여전히 진단과 실험 기록 초안입니다. 조사 당시의 과거 소스 한계는 그대로이며, 로컬 실행 관측은 이제 위와 검증 보고서에 기록돼 있습니다. 정해진 표 안에서 제한된 수정은 스키마를 바꾸려면 분명한 단위 선언을 요구합니다. 구분 행 없는 글에서 표시 없는 일반 머리글이 이어지면 여전히 애매하며, 지원하는 경계가 필요합니다. 품사 기반 단위 읽기가 추론한 모든 단위의 뜻이 맞다는 근거는 되지 않습니다. 일반 병합 칸, 이스케이프된 파이프, 충돌하는 예산 조정, 합계 우선 보장은 이 수정 범위 밖에 남습니다. [C1, C6, C7, C9, C12]
