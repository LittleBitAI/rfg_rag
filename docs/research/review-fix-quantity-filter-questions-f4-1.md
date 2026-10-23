# 리뷰 조사 · F4, 1회차

집계 결과와 측정 조건은 Git에 보관하고, 실제 질문·정답·근거·OCR 텍스트와 레코드별 내보내기는 Git에서 제외된 로컬 `artifacts/`에 보관합니다.

복원 출처: 정리 전 `artifacts/review-round2/originals/` 또는 `d7d1682^`. 아래 수치와 검증 기록은 당시 실행에서 관측한 과거 기록이며, 이번 작업에서 다시 측정한 결과가 아닙니다.

PR #63 리뷰 3회차의 수정 전에 2026-10-17에 쓴 조사 초안입니다. 검증된 사실이나 공용 규칙이 아니며, 리뷰는 이 문서를 수정과 함께 읽습니다.

## 문제

F4는 전체 사업 수량 필터와 보통 하이브리드 검색의 경계 문제입니다. 범위를 정하지 않은 숫자 조건은 대상이 사업이면 사업 필터를 골라야 하며, `예산 1억원 이상인 전체 사업`도 마찬가지입니다. 요구사항이나 업체 자격 비교는 하이브리드 검색을 유지해야 합니다. 2회차 구현은 사업이 아닌 질문을 받아들였습니다. 그 수정은 이제 `사업` 앞에 수식어가 붙었다는 이유로 올바른 사업 질문을 거부합니다. 같은 의도 경계에서 서로 반대로 실패한 것입니다. [C1, C2, C3, C4]

발생: 반복, 2·3회차.

- [P1] [P1] rag/retrieval/quantity_filter.py:130 — 명사 수식어가 붙은 전체 사업 질의가 하이브리드 검색으로 폴백함 / `예산 1억원 이상인 전체 사업` 같은 질의 / 수량 조건이 적용되지 않음

## 실패한 수정

- 2회차 수정 전에는 숫자 조건을 파싱하기만 하면 전체 사업 의도라고 보고 경로를 정했습니다. 검증 보고서에는 범위 없는 응답 시간 요구사항이 하이브리드 순위 없이 `_filter`로 들어간 기록이 있습니다. 숫자 파싱은 비교는 확인했지만 그 대상은 확인하지 않았습니다. [C2]
- 2회차 수정은 `project_condition()`을 도입했습니다. 조건의 나머지 부분을 보고, `인`이나 `규모`가 아닌 첫 NNG/NNP를 고른 뒤, 그 토큰이 `사업`이어야 합니다. 보고된 요구사항·자격 질문은 막지만, 대상 인식을 첫 명사가 무엇인지로 대신합니다. 3회차에 보고된 토큰화에서는 `전체`가 뒤의 사업 명사를 가립니다. [C3, C4]
- 검증은 사업이 아닌 질문 다섯 개를 원래 입력과 다듬은 입력으로 다뤘고, `사업`이 첫 명사인 사업 질문 형태도 다뤘습니다. 보고서는 기존 사업 검색 네 개의 결과가 바뀌지 않았다고도 기록합니다. 이 확인은 고친 경우에 대해서는 근거가 되지만, 사업 대상 앞에 명사 수식어를 끼우는 경우는 시험하지 않습니다. 살펴본 함수에 3회차 수정은 없습니다. [C3, C5]

## 출처

### S1 — 수량 조건 파싱과 사업 대상 관문

- URL: rag/retrieval/quantity_filter.py
- 확인일: 2026-10-17
- 위치: 42–46행, 105–132행, 151–167행
- 인용: def project_condition(question):
    condition = parse_condition(question)
    if condition is None:
        return None
    target = next((t.form for t in tokens(condition.remainder)
                   if t.tag in ("NNG", "NNP") and t.form not in ("인", "규모")), None)
    return condition if target == "사업" else None

기본 발췌 선택:
words = subject_phrase(remainder).split()
if "개요" in words or not set(words) - {"사업", "인", "규모"}:
    return "사업 개요와 목적, 추진배경 및 주요 사업내용"
return remainder

선택은 여전히 조건부입니다:
eligible = [{**r, "similarity": float(similarities[r["phrase"]])} for r in rows
            if _usable(r) and similarities[r["phrase"]] >= cutoff]
- 적용: 첫 명사 판단, 별도의 기본 내용 판단, 뒤쪽 유사도 자격을 담고 있습니다.
- 반대 근거: 지금 관문은 일부러 사업이 아닌 대상을 막습니다. 숫자 파싱은 따로 None을 돌려줄 수 있고, 사업 경로로 받아들여져도 값 제외는 여전히 일어날 수 있습니다.
- 검증: 실제 나머지 부분과 토큰을 따라가고, 수식어를 끼워도 파싱된 조건과 선택된 사업 집합이 유지되며 사업이 아닌 대상은 계속 거부되는지 확인합니다.

### S2 — 하이브리드 검색 분기와 필터 결과 만들기

- URL: rag/retrieval/retrieval.py
- 확인일: 2026-10-17
- 위치: 81–125행
- 인용: return self.search_with_candidates(question, query=query)[0]

query = query or question
route = self.router.route(query)
condition = project_condition(query) if not route and not re.match(r"^.*?」 사업에서 ", query) else None
if condition:
    return self._filter(condition)

대체 경로는 후보의 순위를 매기고, 스냅숏을 남기고, 토큰 예산에 맞춰 담습니다:
groups = [self._rank(query, codes, doc_ids) for doc_ids in (list(route.values()) or [None])]

필터 출력:
summary = f"[수량 필터] 조건 일치 {len(matched)}개 문서; 값 미표기·매칭 불가로 제외 {excluded}개 문서."
return FilterHits(hits, summary, matched, chosen), self._candidate_snapshot([ranked], ranked)
- 적용: 거부가 검색 방식을 바꾸는 곳, 실제 쓰는 질의 규칙, 기관 필터 막이, 공용 진입점을 보여 줍니다.
- 반대 근거: 기관 필터나 문서 접두어 막이는 일부러 전체 문서 필터링을 막습니다. `_filter()`도 문서별 발췌에 순위를 쓰므로, 실험은 발췌 순위와 보통의 전체 문서 대체 경로를 구별해야 합니다.
- 검증: 분기나 순위 범위를 관찰한 뒤, 순위 함수가 불리지 않았다는 것만 확인하지 말고 필터 메타데이터와 일치한 ID 전체를 확인합니다.

### S3 — 기존의 긍정·부정·범위 경로 회귀 테스트

- URL: tests/test_quantity_filter.py
- 확인일: 2026-10-17
- 위치: 107–134행, 190–200행, 235–244행, 439–455행
- 인용: 긍정 예시:
("예산 1억원 이상인 사업들의 개요", ["b", "c", "a"])
("예산 1억~2억 사업", ["a"])
("예산이 가장 큰 사업", ["b", "c"])
("예산 9억원 이상 사업", [])

사업이 아닌 매개변수:
"응답시간 3초 이하인 요구사항을 알려줘", "사업 응답시간 3초 이하인 요구사항을 알려줘",
"응답시간 1초~3초 사이 요구사항", "응답시간이 가장 짧은 요구사항",
"예산 1억원 이상인 업체의 자격을 알려줘"

@pytest.mark.parametrize("rewritten", [False, True])
index._filter = MagicMock(side_effect=AssertionError("Non-project question entered filter"))
index._rank.assert_called_once_with(question, set(), None)
assert hits == [index.chunks[0]] and not hasattr(hits, "summary")
- 적용: 의미 있는 기존 회귀 테스트와, 빠진 '대상 앞 수식어' 차원을 보여 줍니다.
- 반대 근거: 테스트는 기준값만이 아니라 범위, 극값, 빈 결과, 다듬은 부정 질문, 범위 경로도 다룹니다. 빈틈은 구체적인 한 곳이며, 회귀 테스트가 없는 것은 아닙니다.
- 검증: 기존 매개변수 테스트를 수식어를 유지한 긍정 경우와 그에 맞는 사업 아닌 대상으로 넓힙니다.

### S4 — 기록된 2회차 경로 수정과 검증

- URL: docs/quantity_filter_validation.md
- 확인일: 2026-10-17
- 위치: 리뷰 2회차, 5행, 9행, 15–17행
- 인용: The unscoped response-time requirement used `_filter` without calling hybrid ranking.

Project filtering now requires a project target in the parsed condition's remainder, ignoring connecting `인` and `규모`. A business word only in the field prefix is insufficient. Ten route regressions exercise five non-project comparisons as original and rewritten questions: requirement thresholds, ranges, extremes, a project-prefixed requirement and vendor qualification.

Four actual project searches retained 61/30/44/1 projects, 10/45/10/10 exclusions, all chosen values and complete source markers. Five actual non-project searches used hybrid retrieval and returned 14/17/15/23/15 hits.

The active index and server were not switched to the isolated artifacts.
- 적용: 앞서 실행해 본 증상, 의도한 수정, 보고된 검증 범위를 기록합니다.
- 반대 근거: 앞선 확인을 담은 추적 보고서이며, 따로 다시 돌린 실험이 아닙니다. 언급된 산출물 로그는 소스만 보는 이번 조사에서 볼 수 없었습니다.
- 검증: 새 수식어 재현은 앞선 성공 검색과 과거 실행 수와 따로 보고합니다.

### S5 — 문서로 정한 전체 사업 수량 검색 약속

- URL: README.md
- 확인일: 2026-10-17
- 위치: 42–48행과 63–65행
- 인용: Quantity conditions targeting projects (`사업`), without an agency or document-name prefix, filter the whole collection using indexed per-document values. Thresholds, ranges and max/min are supported, retaining ties.

Numeric comparisons targeting requirements or vendor qualifications use the existing hybrid search; mentioning a project in the field name alone does not select the project filter. Routing uses the stored rewrite, or the original question when it is empty.

색인·라우팅·필터에 LLM이나 API 호출을 추가하지 않습니다.

Values without an accepted matching field can still be omitted, and conflicting values within one document are not semantically reconciled.
- 적용: 경로 경계의 양쪽을 정하고, 빠짐없음 약속을 받아들여진 색인 값으로 제한합니다.
- 반대 근거: 수식어 전체 문법을 정하지 않으며, 모든 문서의 추출과 뜻 기반 조정을 보장하지 않습니다.
- 검증: 유료 의도 분류를 더하지 않고, 사업 필터, 사업 아닌 하이브리드 동작, 실제 질의 기준 경로, 기존 제외를 유지합니다.

### S6 — Kiwi Python API: 토큰 정보와 품사 태그

- URL: https://github.com/bab2min/kiwipiepy
- 확인일: 2026-10-17
- 위치: README 토큰 정보 예시와 품사 태그 표; 가져온 355–365행과 1318–1333행
- 인용: tokens[0].tag # 형태소의 품사 정보

세종 품사 태그를 기초로 하되, 일부 품사 태그를 추가/수정하여 사용하고 있습니다.

NNG | 일반 명사
NNP | 고유 명사
- 적용: 관문이 쓰는 토큰 필드와 명사 태그의 뜻을 문서로 보여 줍니다. 실제 웹 검색으로 찾아 관리자 저장소에서 가져왔습니다.
- 반대 근거: 문서는 `인 전체 사업`의 정확한 분석을 주지 않고, 설치된 모델과 버전마다 분석이 같다고 보장하지도 않습니다.
- 검증: 가정한 수식어 분석을 흉내 내지 말고, 실제로 설치된 분석기의 토큰 형태, 태그, 위치를 기록합니다.

### S7 — Universal Dependencies: Nominals

- URL: https://universaldependencies.org/u/overview/nominal-syntax.html
- 확인일: 2026-10-17
- 위치: Modifier Dependents, 첫 정의
- 인용: “An `nmod` is a nominal phrase modifying the head of another nominal phrase, with or without a special case marker.”
- 적용: 명사 수식어와 그것이 꾸미는 중심어를 일반적으로 구별합니다. 실제 웹 검색으로 찾아 프로젝트 문서에서 가져왔습니다.
- 반대 근거: 일반 주석 모델이며, 한국어 경로 알고리즘이나 보고된 Kiwi 분석의 증명이 아닙니다. 아무 수식어나 버려도 된다는 근거도 아닙니다.
- 검증: 대상/수식어 최소 쌍으로 제안한 로컬 인식 규칙을 시험합니다. 이 출처가 의존 구문 분석기 추가를 요구하지는 않습니다.

### S8 — 필터 문맥 서식과 생성 지시

- URL: rag/generation/generation.py
- 확인일: 2026-10-17
- 위치: 26–32행과 38–46행
- 인용: "- [수량 필터] 컨텍스트는 질문의 부가 요청이 없어도 제공된 모든 사업을 각각 한 행으로 하는 "
"'사업 | 값(원문 표기) | 개요 | 출처 [번호]' Markdown 표로 빠짐없이 나열하세요. "
"검색기가 전체 문서의 확인 가능한 값에 질문의 조건을 이미 적용했으므로 제공된 사업은 모두 조건을 만족하며, "
"최대·최소 질문의 결과는 이미 비교를 마친 극값 사업입니다. 이 판정을 그대로 설명하세요. "

context = "\n\n".join(parts) or "(검색된 문서 청크가 없습니다.)"
return f"{hits.summary}\n\n{context}" if hasattr(hits, "summary") else context
- 적용: 경로 결정이 생성이 받는 문맥 약속(빠짐없는 사업 표와 빈 결과 요약 포함)을 바꾼다는 것을 보여 줍니다.
- 반대 근거: 이 지시가 생성된 답이 실제로 따른다는 증거는 아닙니다. 경로와 문맥 확인은 생성 호출 없이 할 수 있습니다.
- 검증: 받아들여진 사업 질의(빈 결과 포함)에는 필터 요약이 있고, 사업 아닌 하이브리드 결과에는 없는지 확인합니다.

### S9 — 수량 파싱이 쓰는 실제 형태소 분석기

- URL: rag/retrieval/quantities.py
- 확인일: 2026-10-17
- 위치: 54–63행
- 인용: @lru_cache(maxsize=1)
def _kiwi():
    # 모델을 읽는 데 시간이 들어 한 번만 만든다.
    return Kiwi()


def tokens(text):
    """형태소 분석. 검증을 여러 스레드로 돌리므로 Kiwi 하나를 잠가 차례로 쓴다."""
    with _KIWI_LOCK:
        return _kiwi().tokenize(unicodedata.normalize("NFC", text))
- 적용: 관문이 구문상 대상 파서가 아니라 기본 Kiwi 인스턴스와 NFC 정규화에 이어져 있음을 보여 줍니다.
- 반대 근거: 소스를 보면 호출 경로는 알 수 있지만, 설치된 패키지/모델 버전이나 실행 시 정확한 토큰은 알 수 없습니다.
- 검증: 첫 재현에 이 함수를 쓰고, 인식 규칙을 바꾸기 전에 환경을 기록합니다.

## 주장

- C1 (출처; S5): 문서로 정한 약속은 범위 없는 사업 수량 필터와 요구사항/업체 하이브리드 검색을 나누고, 실제 질의 기준 경로를 유지하며, 받아들여진 일치 항목이 없는 수량은 제외합니다.
- C2 (출처; S4): 앞선 검증 보고서는 사업이 아닌 요구사항이 필터로 들어간 일, 그 뒤의 사업 대상 관문, 보고된 사업·사업 아닌 검색 각각의 성공 확인을 기록합니다.
- C3 (출처; S1): 지금 사업 관문은 파싱된 나머지 부분에서 `인`과 `규모`를 뺀 첫 NNG/NNP가 `사업`일 때만 받아들입니다.
- C4 (해석; S1, S2, S9): 리뷰가 보고한 `전체/NNG` 분석이라면, 정확한 수식어 질의는 사업 조건 없이 하이브리드 검색으로 갈 것으로 예측됩니다. 코드를 읽은 예측이며 실행으로 확인해야 합니다.
- C5 (해석; S3, S4): 기존 테스트와 기록된 검증은 사업을 바로 대상으로 한 경우와 몇 가지 사업 아닌 형태를 다루지만, 사업 대상 앞에 명사 수식어를 끼우는 경우는 시험하지 않습니다.
- C6 (해석; S6, S7, S9): Kiwi는 형태소의 명사 부류를 문서로 정하고, Universal Dependencies는 명사 중심어와 명사 수식어를 구별합니다. 이를 적용하면 첫 명사와 요청한 대상이 같을 필요가 없는 이유가 설명됩니다.
- C7 (해석; S1, S2, S3, S5, S6, S7): `사업` 앞의 드러난 범위 수식어를 인식하고, 다른 대상 거부와 기존 범위 막이를 유지하는 제한된 규칙이, 제한 없는 사업 단어 찾기나 아무 명사 건너뛰기, 새 파서 의존성보다 낫습니다.
- C8 (출처; S2, S8): 두 공용 검색 진입점은 실제 질의로 같은 분기를 씁니다. 필터 결과에는 요약이 붙어, 생성 프롬프트의 빠짐없는 사업 표 약속을 켭니다.
- C9 (해석; S1): 기본 발췌 선택은 `전체`가 빠진 제한된 단어 집합을 따로 인식합니다. 그래서 분기만 고쳐서는 같은 기본 사업 발췌가 나온다고 할 수 없습니다.
- C10 (해석; S1, S2, S3, S5, S6, S8, S9): 실제 토큰을 따라간 뒤 긍정/부정 경로와 결과를 짝으로 시험하면, 유료 API 호출 없이 제한된 수정과 지나치게 넓은 경로로 돌아가는 것을 구별할 수 있습니다.

## 핵심 원리

형태소 부류와 구문상 역할은 다른 정보입니다. Kiwi는 NNG와 NNP를 명사 부류로 정하지만, 이 이름표만으로는 요청한 대상 구의 중심어를 알 수 없습니다. Universal Dependencies는 명사 중심어와 그 수식어(명사 수식어 포함)를 따로 모델링합니다. 그러므로 명사는 대상이 아니라 다른 명사를 꾸밀 수 있습니다. 이 출처들은 첫 명사 고르기가 부족한 이유를 설명하지만, 한국어 의도 분류기를 정하거나 의존 구문 분석기 추가를 요구하지는 않습니다. [C6]

## 적용

숫자 파싱과 기존 기관/문서 막이는 유지하고 `project_condition()`의 사업 의도 판단을 고칩니다. 근거가 있는 가장 작은 수정은 보고된 사업 구를 로컬에서 인식하는 것입니다. 기존에 지원하는 연결 형태와 함께 `전체`를 사업 대상 앞의 범위 수식어로 허용하되, 다른 대상 명사는 계속 거부합니다. 질문 어디에서든 `사업`을 찾거나 아무 명사나 건너뛰는 방식으로 바꾸지 않습니다. 파싱된 대상, 비교, 값, 나머지 부분을 유지해야 하며, 대상을 받아들이면서 실질적인 선택 조건을 소리 없이 지우면 안 됩니다. 제한된 규칙은 제안하는 구현 선택이며, 충분한지는 짝지은 경로·결과 테스트로 보여야 합니다. [C7, C10]

## 가설

남은 원인은 조건 나머지 부분의 첫 명사가 반드시 고르는 대상이라는 가정입니다. `예산 1억원 이상인 전체 사업`을 파싱하면 나머지 부분은 `인 전체 사업`입니다. 리뷰가 관측한 대로 `전체`가 NNG이면 `next(...)`가 이를 고르고, `project_condition()`은 None을 돌려주며, `search_with_candidates()`는 하이브리드 순위와 담기로 갑니다. 리뷰와 맞는 코드 읽기 설명이며, 따로 실행한 재현은 아닙니다. [C3, C4]

## 반대 근거

- 지금 관문은 기존의 사업 직접 대상 테스트 데이터와 사업 아닌 회귀 테스트 다섯 개를 올바르게 구별합니다. 사업 의도 확인을 없애지 말고 좁은 인식 경계를 고쳐야 한다는 근거가 됩니다. [C5, C7]
- 검증 보고서는 실제 사업 검색 네 개가 결과를 유지하고 사업 아닌 검색 다섯 개가 하이브리드 검색을 썼다고 기록합니다. 그 입력에 대해서는 앞선 수정의 근거가 되지만, 언급된 실행 산출물은 여기서 따로 살피거나 다시 돌리지 않았습니다. [C2, C5]
- 정확한 로컬 Kiwi 출력은 이번 세션에서 실행하지 않았습니다. 배포된 분석기가 실제 나머지 부분에서 `전체`를 자격 있는 명사로 돌려주지 않으면, 이 실패 경로는 고쳐야 합니다. [C4, C6]
- 일반 명사 수식어 이론은 모든 수식어를 무시해도 된다는 근거가 아닙니다. 어떤 수식어는 요청 집합을 좁히며, 그 뜻을 반영하지 않고 받아들이면 다른 경로 오류가 생길 수 있습니다. [C7]

## 다른 방법

- `parse_condition()` 결과가 있으면 모두 사업 경로로 되돌리기: 드러난 요구사항 질문 회귀를 다시 만들므로 택하지 않았습니다. [C2, C7]
- 질문이나 나머지 부분 어디든 `사업`이 있으면 받아들이기: 사업 언급이 숫자 항목 접두어나 사업 아닌 대상 뒤에 올 수 있으므로 첫 선택이 아닙니다. 원래 회귀 테스트에 이미 사업 접두어가 붙은 요구사항 질문이 있습니다. [C5, C7]
- `사업`이 나올 때까지 모든 명사 건너뛰기: 같은 이유로 택하지 않았습니다. 조건의 대상이 요구사항이나 업체라는 근거를 버립니다. [C7]
- 완전한 의존 구문 분석기나 LLM 의도 분류기 추가: 드러난 구에 비해 과하고, LLM/API 호출을 더하지 않는다는 문서의 경로 약속과 맞지 않습니다. 언어학 출처는 구별의 필요를 보여 줄 뿐, 새 의존성을 요구하지 않습니다. [C1, C6, C7]
- 유사도 기준, 수량 메타데이터, 인덱스 만들기 바꾸기: 보고된 분기 결정은 `_filter()`와 값 선택보다 앞서므로 첫 선택이 아닙니다. 그 변경으로는 거부된 사업 조건이 필터에 닿지 않습니다. [C3, C4]
- 질문 다듬기로 `전체`를 없애기: 두 검색 진입점 모두 실제 질의로 바로 경로를 정하고, 문서 약속은 다듬은 질의가 없으면 원래 질의를 쓰도록 허용하므로 충분하지 않습니다. [C1, C8]

## 실험

먼저 구현 세션에서, 설치된 Kiwi 버전과 보고된 정확한 질의에 대한 `parse_condition(question)`의 실제 출력, 그 나머지 부분의 토큰, `project_condition(question)`, 기관 필터 결과, 선택된 검색 분기를 기록합니다. 예측하는 수정 전 경로는 나머지 부분 `인 전체 사업`, 첫 자격 명사 `전체`, 사업 조건 없음, 하이브리드 검색입니다. 경로가 다르면 고치기 전에 가설을 고칩니다. 그다음 기존 긍정 테스트 데이터를 기본/수식어 쌍 `예산 1억원 이상인 사업`과 `예산 1억원 이상인 전체 사업`으로 넓히고, 실제 토큰화와 통제한 인덱스를 씁니다. 조건의 대상/단위/방식/값이 같고, 일치하는 문서 ID 전체, 값, 후보, 필터 요약도 같아야 합니다. 같은 수식어로 기준값, 범위, 극값 형태를 시험하고, 원래 질의와 명시적으로 다듬은 질의 경로, 두 공용 검색 진입점을 모두 시험합니다. 기존 사업 아닌 테스트는 유지하고, 짝이 되는 대상 `응답시간 3초 이하인 전체 요구사항을 알려줘`와 `예산 1억원 이상인 전체 업체의 자격을 알려줘`, 그리고 뒤에 사업 언급이 있는 요구사항 대상 질문을 더해 제한 없는 단어 찾기를 막습니다. 기관/문서 접두어 대조군은 유지합니다. 일치하는 값이 없는 올바른 사업 조건도 넣습니다. 이 경우 하이브리드 결과로 소리 없이 바뀌지 않고 필터 결과와 요약을 유지해야 합니다. 경로를 받아들인 것만으로 뒤쪽 약속 전체가 확인되지 않으므로, 서식이 적용된 문맥과 기본 발췌도 살핍니다. 제안한 확인은 모두 질문 다듬기, 생성, 채점 API 호출 없이 로컬에서 돌릴 수 있습니다. 이번 조사 세션에서는 아무 확인도 돌리지 않았습니다. [C8, C9, C10]

## 결과

고치기 전 부모 `51629a7`에서 Kiwi 0.24.0으로 관측한 결과, `parse_condition`은 대상 `사업 예산`, 단위 `원`, 방식 `이상`, 값 100000000, 나머지 부분 `인 전체 사업`을 돌려줬습니다. 실제 나머지 부분 토큰은 `인/NNG 전체/NNG 사업/NNG`였고, `project_condition`은 None, 기관 필터는 `{}`를 돌려줬으며, 분기는 `_filter`를 부르지 않고 하이브리드 순위를 한 번 불렀습니다. 추적은 `artifacts/quantity_review3_before.log`에 있습니다. 수정은 이 초안과 함께 고유 제목 `retrieval: preserve table schemas and whole-project modifiers`로 커밋됐습니다. `tests/test_quantity_filter.py::test_whole_project_modifier_preserves_condition_results_and_default_context`는 기준값/범위/극값/빈 결과, 원래/다듬은 입력, 두 진입점에 걸친 짝 경우 16개를 통과하며, 조건 정체, 값, 후보, 요약, 서식이 적용된 문맥, 기본 발췌 질의를 확인합니다. 넓힌 `test_non_project_quantity_questions_keep_hybrid_retrieval`은 전체 요구사항/업체와 뒤쪽 사업 언급을 하이브리드 검색에 둡니다. `test_agency_and_document_prefix_keep_current_route`는 범위 수식어 대조군을 유지합니다. 대상 인식과 기본 발췌 선택은 뒤쪽 사업 명사를 찾지 않고 같은 제한된 수식어 집합을 씁니다. 마지막으로 영향받는 파일 열 개 실행은 740개 테스트가 통과했고, 경고 12개, 54.12초였습니다(`artifacts/quantity_review3_checked_cleanup_gate.log`). 구현 관측이며, 이 문서는 검증된 지식이나 일반 한국어 의도 파서가 아니라 여전히 초안입니다.

마지막 확인 실행에서 `전체`를 붙인 실제 사업 질문 네 개는 다듬은 질의 경로와 공용 `search` 경로 모두에서 기본 질문과 같은 값, 후보, 서식 문맥을 냈습니다. 사업이 아닌 실제 질문 여덟 개는 전체 요구사항/업체와 뒤쪽 사업 언급을 포함해 하이브리드 검색을 유지했습니다. 고정된 dev 문맥 ID 순서 60개는 모두 그대로였습니다. 마지막 메타데이터와 새로 임베딩한 구문 11,934개를 썼고, 네트워크 연결은 막혀 있었으며 사용량 CSV는 바뀌지 않았습니다(`artifacts/quantity_review3_offline_checked.log`). 유료 호출이나 새 브라우저 승인은 주장하지 않습니다.

## 남은 한계

소스, 받은 지적, 위에 기록한 실험에 바탕을 둔 초안이며, 따로 하는 리뷰나 공용 규칙이 되지 않았습니다. 제한된 수정은 `전체 사업`과 기존 연결 형태를 다루고, 다른 대상 명사에 대한 제외는 유지합니다. 아무 제한 수식어나 해석하거나 일반적인 한국어 명사구를 이해하지는 않습니다. 경로가 맞아도 코퍼스의 모든 문서에 자격 있는 수량이 있다는 보장은 없으며, 단위, 쓸 수 있음, 항목 유사도에 따른 제외는 남습니다. 별도의 기본 내용 판단도 분기와 함께 바꾸고 시험했습니다. 유료 호출은 하지 않았습니다. [C1, C4, C9, C10]
