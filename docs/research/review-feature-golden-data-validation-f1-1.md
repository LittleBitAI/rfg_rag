# 리뷰 조사 · F1, 1회차

집계 결과와 측정 조건은 Git에 보관하고, 실제 질문·정답·근거·OCR 텍스트와 레코드별 내보내기는 Git에서 제외된 로컬 `artifacts/`에 보관합니다.

복원 출처: 정리 전 `artifacts/review-round2/originals/` 또는 `d7d1682^`. 아래 수치와 검증 기록은 당시 실행에서 관측한 과거 기록이며, 이번 작업에서 다시 측정한 결과가 아닙니다.

PR #26 리뷰 2회차의 수정 전에 2026-10-14에 쓴 조사 초안입니다. 검증된 사실이나 공용 규칙이 아니며, 리뷰는 이 문서를 수정과 함께 읽습니다.

## 문제

F1: 답에 값이 여러 개 있으면, 후보 답은 각 값을 독립 답과 같은 대상에 붙여야 합니다. 그렇지 않으면 숫자는 맞지만 대상이 틀린 비교 후보가 auto_validated에 이르고 공개됩니다. 후보의 대상 연결을 비교하는 막이는 same_answer(golden_pipeline/validation.py:172) 하나뿐입니다. check_structure는 structure.entities가 근거에 나오는지만 확인하고, 답에 나오는지는 보지 않기 때문입니다.

발생: 반복, 1·2회차.

- [P1] [P1] golden_pipeline/validation.py:181 — 수량이 맞으면 대상이 틀려도 여전히 통과합니다

## 실패한 수정

- 1회차 수정(b49e0b0): 순서 없는 (값, 단위) 쌍 집합을 facts()로 바꿨습니다. facts()는 각 값 앞의 대상 단어도 돌려줍니다. 그러면 값은 후보의 대상에 다른 기대 값의 대상 단어가 있을 때만 실패합니다. 바뀐 것이 증명되지 않으면 통과하는 규칙이라, 관계없는 대상(C안/D안)이나 대상이 없는 경우('1억원, 2억원')는 여전히 통과했고, 2회차가 이를 지적했습니다.
- 2회차 수정(a41c9fb): 이제 _attributed는 값 자신의 단어(own)가 후보의 대상에 있어야 하고, 모든 등장에 남의 단어가 있으면 False, 그 밖에는 None(보류)을 돌려줍니다. 2회차의 두 반례는 모두 막습니다(test_validation.py:138-139의 테스트). 하지만 대상 확인 전체가 여전히 `if not rivals: return True`(validation.py:200-201) 뒤에 있습니다. 독립 답에 그 단위의 값이 하나뿐이면 대상을 전혀 비교하지 않습니다. 그래서 독립 답 'B안이 2억원으로 더 많다'에 대해 'A안이 2억원으로 더 많다'도 True가 나와야 하고, 단위를 건너 바뀐 경우('A안 1억원, B안 12개월'에 대해 'B안 1억원, A안 12개월')도 마찬가지입니다. 두 수정 모두 기본 결과를 바꾸지 않았으며, 기본은 여전히 통과입니다.

## 출처

### S1 — golden_pipeline/validation.py (a41c9fb)

- URL: golden_pipeline/validation.py
- 확인일: 2026-10-14
- 위치: _attributed 188-206행; same_answer 172-185행; _verdict 219-236행
- 인용: rivals = [other for other in expected if other is not fact and other[0][1] == pair[1]]
    if not rivals:
        return True
- 적용: 대상과 값의 연결을 막는 유일한 곳이며, 같은 단위의 다른 값이 없으면 대상을 확인하지 않고 True를 돌려줍니다.
- 반대 근거: 다른 값이 있는 분기 안에서는 2회차가 요청한 대로 관계없는 대상이나 대상이 없는 경우를 보류합니다.
- 검증: 값이 하나인 경우와 단위를 건넌 경우의 새 테스트 행은 True를 돌려주면 안 됩니다.

### S2 — tests/golden/test_validation.py

- URL: tests/golden/test_validation.py
- 확인일: 2026-10-14
- 위치: test_same_answer_compares_after_value_and_unit_normalization, 127-142행
- 인용: ("C안은 2억원, D안은 1억원", "A안 2억원, B안 1억원", None),
    ("2억원, 1억원", "A안 2억원, B안 1억원", None),
- 적용: 모든 대상 연결 테스트에 같은 단위의 값이 두 개씩 있고, 단위마다 값이 하나인 테스트는 없다는 것을 보여 줍니다.
- 반대 근거: 없음
- 검증: 빠진 행을 더합니다.

### S3 — golden_pipeline/configs/topics/comparison.json

- URL: golden_pipeline/configs/topics/comparison.json
- 확인일: 2026-10-14
- 위치: requires, structure.entities
- 인용: "requires": "둘 이상의 대상(항목, 안, 기관, 단계 등)을 견주는 질문. 답은 각 대상의 값이나 내용을 함께 밝힌다." … "entities": "견주는 대상 이름 2개 이상의 리스트. 각각 근거에 적힌 그대로"
- 적용: 지켜야 할 규칙(각 대상의 값을 밝힘)과, 대상 연결의 기준으로 삼을 이미 아는 대상 이름입니다.
- 반대 근거: 대상 이름은 '근거에 적힌 그대로'이므로 답에서는 다르게 쓸 수 있고, 그러면 보류가 됩니다.
- 검증: 대상 이름 기준 확인이 이 이름을 읽습니다.

### S4 — 관계 삼중항 추출 채점(Wei 외, A Novel Cascade Binary Tagging Framework for Relational Triple Extraction)

- URL: https://ar5iv.labs.arxiv.org/html/1909.03227
- 확인일: 2026-10-14
- 위치: 4.1절 Experimental Setting, Datasets and Evaluation Metrics
- 인용: [an extracted relational triple] is regarded as correct only if the relation and the heads of both subject and object are all correct.
- 적용: 대상 없이 맞힌 값은 맞는 사실이 아닙니다. same_answer는 (대상, 값)을 한 단위로 채점해야 합니다.
- 반대 근거: 추출 벤치마크의 채점 관례이며(머리 토큰 부분 일치도 씀), 자유 서술 답을 비교하는 규칙은 아닙니다.
- 검증: 수정은 모든 기대 사실에 대해 대상과 값을 함께 비교합니다.

### S5 — Saltzer & Schroeder, The Protection of Information in Computer Systems (1975)

- URL: https://www.cs.virginia.edu/~evans/cs551/saltzer/
- 확인일: 2026-10-14
- 위치: Design principles, b) Fail-safe defaults
- 인용: Base access decisions on permission rather than exclusion. … A design or implementation mistake in a mechanism that gives explicit permission tends to fail by refusing permission, a safe situation, since it will be quickly detected. On the other hand, a design or implementation mistake in a mechanism that explicitly excludes access tends to fail by allowing access, a failure which may go unnoticed in normal use. (접근 제어에 대한 원칙입니다. 가져오기 도구는 이 부분을 바꿔 말한 형태로 돌려줬고, 위 문구는 논문에서 널리 인용되는 원문입니다.)
- 적용: _attributed는 제외되지 않으면 받아들이며, 리뷰마다 받아들이는 경로가 하나씩 더 나왔습니다. '같은 답'에 대상 연결이 확인될 것을 요구하면 결함이 보류 쪽으로 실패합니다.
- 반대 근거: 접근 제어에 대한 원칙이므로 답 검증에 옮기는 것은 비유입니다. 여기서 안전하게 실패하는 대가는 사람 검토 대기열이 늘어나는 것입니다.
- 검증: 수정 뒤 판단식이 이해하지 못하는 경우는 None을 돌려주고, 항목은 auto_validated가 아니라 보류됩니다.

## 주장

- C1 (출처; S1): a41c9fb에서 _attributed는 독립 답에 같은 단위의 다른 값이 없으면 대상을 비교하지 않고 True를 돌려줍니다.
- C2 (해석; S1, S2): 그래서 대상이 틀린 값 하나짜리 비교 답이나, 단위가 다른 값끼리 바뀐 답도 auto_validated에 이를 것이며, 기존 테스트는 이 경우를 다루지 않습니다.
- C3 (해석; S3, S1): 비교 항목은 structure.entities에 대상 이름을 담고 있으므로, 대상 연결을 다른 값과의 대비로 추론하지 않고 이미 아는 이름으로 확인할 수 있습니다.
- C4 (출처; S4): 사실은 대상과 값이 함께 맞을 때만 맞는 것으로 셉니다.
- C5 (출처; S5): 불일치를 찾지 못하면 받아들이는 확인은 받아들이는 쪽으로 실패하고, 긍정 근거가 있을 때만 받아들이는 확인은 거부하는 쪽으로 실패합니다. 여기서는 거부 쪽이 안전합니다.

## 핵심 원리

Saltzer와 Schroeder의 안전한 기본값 원칙: 결정을 제외가 아니라 허가에 두라는 것입니다. 명시적으로 허가하는 장치의 결함은 거부하는 쪽으로 실패해 눈에 띄고, 제외하는 장치의 결함은 허용하는 쪽으로 실패해 모르고 지나칠 수 있습니다. 관계 추출 채점은 사실을 묶인 튜플로 다룹니다. 삼중항은 관계와 두 대상이 모두 맞을 때만 맞으므로, 대상이 틀린 값은 부분 정답이 아니라 오답입니다.

## 적용

_attributed는 제외 장치입니다. 다른 값이 없으면 언제나 True를 돌려주고(validation.py:200), 다른 값이 있는 분기 안에서는 남의 단어가 있을 때만 거부합니다. 그래서 결함은 허용하는 쪽으로 실패하고, 리뷰마다 허용 경로가 하나씩 더 나왔습니다. 비교 항목은 대상을 미리 알고 있으므로(structure.entities, generation._comparison이 근거와 대조함) 대상 연결을 직접 요구할 수 있습니다. 기대 사실마다 대상 구간에 어떤 대상 이름이 나오는지를 독립 답에서, 그리고 같은 값의 후보 등장마다 찾습니다. 정확히 같은 대상 하나면 True, 다른 대상만 있으면 False, 없거나 여럿이면 None입니다. 이 규칙은 다른 값이 있든 없든 적용합니다. 다른 주제에는 지금 규칙을 남겨, '1억원'과 '총 사업비는 1억원' 같은 숫자 답이 모두 보류되지 않게 합니다. 호출하는 곳(_same_as_independent, _verdict의 None→보류 단계, _single_unit_verdict, _not_copied)은 이미 None을 보류로 다루므로, entities만 넘겨주면 됩니다.

## 가설

두 수정 모두 기본값이 받아들이기인 판단식 안에서 리뷰어의 특정 반례만 고쳤습니다. 대상 연결은 독립 답 속 같은 단위의 다른 값과 대비해서만 추론하고, 그 분기 밖(단위마다 값이 하나, 단위가 다른 값들)은 대상 확인 없이 통과합니다. 버티는 수정은 비교 항목의 모든 값에 대해, 이미 아는 대상 이름(structure.entities)을 기준으로 긍정적인 대상 연결을 요구하고, '확인할 수 없음'은 True가 아니라 None(보류)으로 보내야 합니다.

## 반대 근거

- 코드를 돌려 보지 않았습니다. 값 하나짜리 반례는 Kiwi가 두 글에서 '2억원으로'를 같은 방식으로 태깅하는 데 달려 있습니다. 단위가 다르게 나오면 쌍이 맞지 않아 True가 아니라 False가 됩니다.
- a41c9fb는 2회차가 든 두 반례를 실제로 만족하며, 리뷰어의 표현('hold answers whose attribution cannot be established')은 값이 여러 개인 답에만 해당한다고 읽을 수도 있습니다. 3회차 리뷰어가 받아들일 수도 있습니다.
- 대상 이름 일치는 근거와 이름을 다르게 쓴 맞는 답(예: 대상 'A안(기본형)'에 대한 'A안')이나 대상을 값 뒤에 쓴 답('2억원(A안)')을 보류합니다. 사람 검토 부담이 늘지만, 더 엄격한 규칙이 잘못 받아들이는 경우를 만들지는 않습니다.

## 다른 방법

- `if not rivals: return True`만 지우고 모든 값에 독립 답의 대상 단어를 요구: 가장 단순하지만, 숫자·표 항목에도 적용됩니다. 그 항목에서는 검증기가 후보에 없는 대상 단어('총 사업비는 …')를 자주 더하므로 모두 보류됩니다. 비교 주제로 범위를 좁히는 편이 낫습니다.
- 검증기에 {대상: 값} 구조 출력을 요구하고 사전을 비교: 가장 강하게 묶지만 validator.txt, 판정 스키마(VERDICT_FIELDS), manifest의 프롬프트 SHA가 바뀝니다. 지적에 비해 큰 변경입니다.
- 단어 집합 판단식(own/foreign)을 계속 다듬기: 두 번 실패한 방법입니다. 기본값이 여전히 받아들이기입니다.
- 값이 둘 미만인 비교 답은 모두 보류: 거칠고, 맞는 대상을 댄 '어느 쪽이 더 큰가' 답까지 보류합니다.

## 실험

수정 전 a41c9fb에서 same_answer('A안이 2억원으로 더 많다', 'B안이 2억원으로 더 많다')와 same_answer('B안은 1억원, A안은 12개월', 'A안은 1억원, B안은 12개월')을 돌립니다. 가설은 둘 다 True를 예측합니다. 이어서 비교 후보(entities ['A안','B안'], 답 'A안이 2억원으로 더 많다')와 검증기 판정 'B안이 2억원으로 더 많다'로 validate()를 돌립니다. 예측은 auto_validated입니다. 수정 뒤에는 같은 세 경우가 False/False/rejected여야 하고, test_same_answer_compares_after_value_and_unit_normalization의 기존 행은 모두 결과를 유지해야 합니다.

## 결과

관측했지만 검증하지 않은 초안입니다. 수정 전 a41c9fb에서 `same_answer('A안이 2억원으로 더 많다', 'B안이 2억원으로 더 많다')`와 `same_answer('B안은 1억원, A안은 12개월', 'A안은 1억원, B안은 12개월')`은 예측대로 둘 다 True였습니다. 새 테스트 `test_comparison_values_must_belong_to_the_same_entity_as_in_the_independent_answer`(비교 후보, entities ['A안','B안'], 검증기 답 'B안이 2억원으로 더 많다')는 후보 'A안이 2억원으로 더 많다'에 대해 auto_validated를 냈고(예측대로), '2억원인 안이 더 많다'에 대해서도 그랬습니다. 이 결과를 더하는 커밋의 수정 뒤에는 비교 항목이 각 값을 `_anchored`로 비교합니다. `_anchored`는 두 글에서 값 앞에 쓴 대상 이름을 읽습니다. entities를 넘기면 위의 두 호출은 False와 False를 돌려줍니다. validate() 경우는 rejected, 대상 없는 후보는 보류이고, 'B안이 2억원으로 더 많다'는 auto_validated로 남습니다. `test_comparison_attribution_is_read_from_the_entity_names_for_every_value`는 단위를 건넌 바뀜(False), 맞는 순서(True), C안/D안(None)을 다룹니다. 실험에 적힌 그대로 entities 없이 부르면 두 호출은 여전히 True입니다. 의도한 것입니다. 이 문서의 적용 절대로, 다른 주제는 다른 값의 단어 규칙을 유지합니다. `test_same_answer_compares_after_value_and_unit_normalization`의 기존 행은 모두 결과를 유지합니다(tests/golden/test_validation.py: 51 passed).

## 남은 한계

실행하지 않았으며, 반례는 코드를 읽어서 얻었습니다. 숫자가 없는 답은 부분 문자열 규칙(_contains)을 유지합니다. 독립 답 'B안'은 후보 'A안이 B안보다 크다'에 포함되므로, F1의 숫자 범위 밖에서 같은 대상 연결 결함이 남습니다. 서로를 포함하는 대상 이름('AB안' 안의 'B안')은 가장 긴 일치 처리가 필요합니다. 대상 구간은 여전히 값 앞만 읽습니다.
