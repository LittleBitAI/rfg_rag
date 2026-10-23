# 리뷰 조사 · F1, 2회차

집계 결과와 측정 조건은 Git에 보관하고, 실제 질문·정답·근거·OCR 텍스트와 레코드별 내보내기는 Git에서 제외된 로컬 `artifacts/`에 보관합니다.

복원 출처: 정리 전 `artifacts/review-round2/originals/` 또는 `d7d1682^`. 아래 수치와 검증 기록은 당시 실행에서 관측한 과거 기록이며, 이번 작업에서 다시 측정한 결과가 아닙니다.

PR #26 리뷰 3회차의 수정 전에 2026-10-14에 쓴 조사 초안입니다. 검증된 사실이나 공용 규칙이 아니며, 리뷰는 이 문서를 수정과 함께 읽습니다.

## 문제

F1: 비교 후보가 독립 검증기와 다른 대상에 답을 붙이거나 반대 결론을 말하는데도 auto_validated에 이르고 공개됩니다. 지켜야 할 규칙은 비교 주제의 요구 사항(configs/topics/comparison.json 'requires': 답은 각 대상의 값이나 내용을 밝힘)이며, 이를 강제할 수 있는 곳은 same_answer뿐입니다. check_structure는 structure.entities를 답이 아니라 근거에서 찾습니다. 6c334d7에서 same_answer('A안이 B안보다 예산이 많다', 'B안', ['A안','B안'])는 True입니다. 수량이 없는 독립 답은 대상 확인 전에 곧바로 부분 문자열 포함 검사(validation.py:184-185)로 가기 때문입니다. 이어서 _not_copied(validation.py:333-334)가 대상 이름만 있는 답을 예외로 두므로, 후보는 auto_validated에 이릅니다.

발생: 반복, 2·3회차.

- [P1] [P1] golden_pipeline/validation.py:185 — 글로만 된 비교 답은 대상 연결 확인을 건너뛰어 반대 결론도 승인할 수 있습니다

## 실패한 수정

- b49e0b0(1회차 수정): 순서 없는 (값, 단위) 쌍 집합을 각 값 앞의 대상 단어를 담은 facts()로 바꾸고, 후보의 대상에 다른 기대 값의 단어가 있을 때만 거부했습니다. 기본값이 여전히 받아들이기였으므로, 관계없는 대상(C안/D안)과 대상이 없는 경우('1억원, 2억원')가 통과했습니다(2회차).
- a41c9fb(2회차 수정): _attributed가 값 자신의 대상 단어를 요구하고, 남의 단어가 있으면 False, 그 밖에는 None을 돌려줬습니다. 하지만 모두 `if not rivals: return True` 뒤에 있어서, 단위마다 값이 하나이거나 단위를 건너 바뀐 경우는 대상 확인 없이 통과했습니다(1회차 조사, 그 문서에서 실행해 확인함).
- 2bfd9a3(1회차 조사의 수정): 비교 항목은 _anchored를 씁니다. _anchored는 값마다 그 앞에 쓴 대상 이름을 읽습니다. 숫자 경우는 모두 막았지만 `if not expected: return _contains(...)` 뒤에 있으므로, 글로만 된 독립 답은 여기에 오지 않습니다. 1회차 문서 스스로 이를 F1의 숫자 범위 밖 남은 한계로 적었고('독립 답 B안은 후보 A안이 B안보다 크다에 포함됨'), 수정은 이를 열어 두었습니다. _anchored는 또 값 앞의 이름만 보고, 결론 단어나 독립 답이 모든 대상을 다루는지는 보지 않습니다. 그래서 수정은 받아들이는 경로를 줄였지만, True가 주제의 규칙을 요구하게 만들지는 못했습니다.

## 출처

### S1 — 6c334d7 시점의 golden_pipeline/validation.py

- URL: golden_pipeline/validation.py
- 확인일: 2026-10-14
- 위치: same_answer 176-193행; _anchored 196-213행; _not_copied 328-335행; _verdict 251-268행
- 인용: expected = facts(independent)
    if not expected:
        return _contains(_norm(text), _norm(independent))
    found = facts(text)
    if entities:
        results = [_anchored(fact, found, entities) for fact in expected]
- 적용: 글로만 된 답의 출구는 대상 확인 전에 돌려주고, _anchored는 값 앞의 대상 이름만 확인합니다. 이 둘이 비교 항목의 True 출구입니다.
- 반대 근거: 숫자 대상 경로는 앞선 리뷰가 든 바뀜 경우에 모두 False를 돌려줍니다.
- 검증: 수정 뒤 entities 분기는 독립 답이 모든 대상을 한 번씩 다루고 각 값이 같은 대상에 붙을 때만 True를 돌려줍니다. 글로만 된 분기는 포함되면 None을 돌려줍니다.

### S2 — tests/golden/test_validation.py

- URL: tests/golden/test_validation.py
- 확인일: 2026-10-14
- 위치: 145-152행과 230-245행
- 인용: ("B안이 2억원으로 더 많다", "auto_validated"), ("A안이 2억원으로 더 많다", "rejected"), ("2억원인 안이 더 많다", "held") ... Validator({"*": verdict("B안이 2억원으로 더 많다")})
- 적용: 모든 비교 테스트의 독립 답에 수량이 있습니다. 글로만 된 판정을 다루는 테스트가 없어서 우회가 테스트되지 않았습니다. 첫 행은 B안만 다루는 독립 답에 기댑니다.
- 반대 근거: 없음
- 검증: 리뷰어의 글로만 된 재현과 반대 결론 행을 더합니다. 첫 행의 판정이나 기대 상태를 고칩니다.

### S3 — golden_pipeline/configs/topics/comparison.json

- URL: golden_pipeline/configs/topics/comparison.json
- 확인일: 2026-10-14
- 위치: requires; structure.entities
- 인용: "requires": "둘 이상의 대상(항목, 안, 기관, 단계 등)을 견주는 질문. 답은 각 대상의 값이나 내용을 함께 밝힌다." ... "entities": "견주는 대상 이름 2개 이상의 리스트. 각각 근거에 적힌 그대로"
- 적용: True의 긍정 조건(각 대상의 값을 밝힘)을 정하고, 다루는 대상을 확인할 이름을 줍니다.
- 반대 근거: '값이나 내용'에는 글 내용도 들어가며, 숫자 기준 규칙은 이를 확인할 수 없습니다. 그런 답은 보류로 갑니다.
- 검증: 대상 확인은 structure.entities를 읽습니다.

### S4 — 리뷰 조사 · F1, 1회차

- URL: docs/research/review-feature-golden-data-validation-f1-1.md
- 확인일: 2026-10-14
- 위치: 남은 한계
- 인용: 숫자가 없는 답은 부분 문자열 규칙(_contains)을 유지합니다. 독립 답 'B안'은 후보 'A안이 B안보다 크다'에 포함되므로, F1의 숫자 범위 밖에서 같은 대상 연결 결함이 남습니다.
- 적용: 글로만 된 답의 우회는 2bfd9a3 수정 전에 이미 알려져 있었고, 놓친 것이 아니라 범위에서 뺀 것임을 보여 줍니다.
- 반대 근거: 없음
- 검증: 이번 수정은 비교 항목의 어떤 True 출구도 범위에서 빼면 안 됩니다.

### S5 — McCoy, Pavlick & Linzen (2019), Right for the Wrong Reasons: Diagnosing Syntactic Heuristics in Natural Language Inference

- URL: https://ar5iv.labs.arxiv.org/html/1902.01007
- 확인일: 2026-10-14
- 위치: 표 1; HANS를 소개하는 1절 문단
- 인용: Subsequence: "Assume that a premise entails all of its contiguous subsequences." Example: "The doctor near the actor danced." Lexical overlap: "Assume that a premise entails all hypotheses constructed from words in the premise." Example: "The doctor was paid by the actor." These heuristics: "they are not valid inference strategies because they fail on many examples." (MNLI로 학습한 NLI 모델에 대한 내용이며, 실패하는 HANS 사례는 함의가 아닌 사례입니다.)
- 적용: same_answer의 글로만 된 출구는 '후보가 독립 답을 포함함'을 '후보가 그것을 주장함'으로 보며, 이는 부분 연속열 휴리스틱입니다. 'A안이 B안보다 예산이 많다'는 'B안'을 포함하지만 B안이 더 크다고 주장하지 않습니다.
- 반대 근거: 이 논문은 규칙 기반 답 확인이 아니라 학습된 NLI 모델을 진단하며, 이 휴리스틱은 많은 사례에서 맞기도 합니다. 그래서 옮겨 쓰는 것은 겉 문자열 포함으로 무엇을 보일 수 있는지에 대한 비유입니다.
- 검증: 독립 답을 포함하지만 같지 않은 글로만 된 비교 후보는 True가 아니라 None을 돌려줍니다.

### S6 — Saltzer & Schroeder (1975), The Protection of Information in Computer Systems

- URL: https://www.cs.virginia.edu/~evans/cs551/saltzer/
- 확인일: 2026-10-14
- 위치: I.A.3절, 설계 원칙 (b) Fail-safe defaults
- 인용: "Base access decisions on permission rather than exclusion." (가져오기 도구는 나머지를 바꿔 말한 형태로 돌려줬습니다. 허가 기반 장치의 실수는 거부하는 쪽으로 실패해 곧 눈에 띄고, 제외 기반 장치의 실수는 허용하는 쪽으로 실패해 모르고 지나갈 수 있다는 내용입니다. 접근 제어에 대한 원칙입니다.)
- 적용: 비교 항목에서 same_answer의 모든 True 출구는 제외 기반이며, 리뷰마다 허용 경로가 하나씩 더 나왔습니다. 주제 규칙이 보일 때만 True를 주면 남은 결함은 보류 쪽으로 실패합니다.
- 반대 근거: 접근 제어 원칙이므로 비유입니다. 여기서 안전하게 실패하는 대가는 사람 검토 시간입니다.
- 검증: 판단식이 확인할 수 없는 비교 경우는 None을 돌려주고 항목은 보류됩니다.

### S7 — Kamalloo, Dziri, Clarke & Rafiei (ACL 2023), Evaluating Open-Domain Question Answering in the Era of Large Language Models

- URL: https://ar5iv.labs.arxiv.org/html/2305.06984
- 확인일: 2026-10-14
- 위치: 3절(어휘 일치 정의); 초록; 4.4절
- 인용: EM: "A candidate answer is deemed correct iff it can be found in the set of gold answers." Lexical matching "fails completely when a plausible candidate answer does not appear in the list of gold answers"; more than 50% of lexical matching failures came from semantically equivalent answers; "the automated methods are prone to misjudging hallucinated long answers" (마지막 인용은 어휘 일치가 아니라 BEM과 InstructGPT-eval에 대한 것입니다).
- 적용: 두 방향 모두에 반대 근거가 됩니다. 겉 문자열 일치를 더 엄격하게 하면 맞는 답을 많이 보류하고(수정의 대가), 자동 LLM 채점은 긴 답에서 안전한 대체가 아닙니다(LLM 채점 방법을 먼저 택하지 않는 이유).
- 반대 근거: 한국어 제안요청서 비교 답이 아니라 영어 개방형 질의응답을 연구했고, 여기서 문제인 잘못된 통과가 아니라 잘못된 거부에 초점을 둡니다.
- 검증: 수정 뒤 비교 후보의 보류 비율을 재고, 보류 항목은 사람 확인을 공개 경로로 유지합니다.

## 주장

- C1 (출처; S1): 6c334d7에서 same_answer는 수량이 없는 독립 답에 대해 대상 확인 전에 _contains(...)를 돌려주므로, 글로만 된 답에서는 비교 대상을 전혀 보지 않습니다.
- C2 (해석; S4, S1): 1회차 수정은 글로만 된 경로를 알면서 열어 두었습니다. 수정은 _anchored의 버그가 아니라 범위 때문에 실패했습니다.
- C3 (해석; S1, S2): _anchored는 값 앞의 대상 이름만 비교합니다. 같은 값에 반대 결론('더 적다'와 '더 많다')인 답도 True가 나와야 하고, 이를 다루는 테스트가 없습니다.
- C4 (해석; S3, S6): 비교 항목에서는 주제 규칙이 보일 때만 True를 줘야 합니다. 독립 답이 structure.entities의 모든 대상에 값을 주고, 후보에서 각 값이 같은 대상에 붙어 있을 때입니다. 그 밖에는 None이고, 불일치가 증명되면 False입니다.
- C5 (출처; S5): 문자열 포함을 함의로 보는 것(부분 연속열 휴리스틱)은 올바른 추론 방법이 아니며 많은 사례에서 실패합니다.
- C6 (해석; S2): 수정은 기존 기대값 하나를 바꿉니다. 독립 답이 B안만 다루는 비교 테스트 행은, 판정이 두 대상을 모두 다루도록 바뀌지 않으면 auto_validated에서 held로 바뀝니다.
- C7 (출처; S6): 제외로 결정하는 장치는 허용하는 쪽으로 실패하고, 허가로 결정하는 장치는 거부하는 쪽으로 실패해 눈에 띕니다.
- C8 (출처; S7): 겉 문자열 일치는 뜻이 같은 답을 자주 거부하고, 자동 채점기는 지어낸 긴 답을 잘못 판정합니다. 그래서 수정은 보류 비율을 올리고, LLM 채점은 첫 선택이 아닙니다.

## 핵심 원리

출처는 두 가지입니다. (1) McCoy, Pavlick & Linzen(HANS)은 부분 연속열 휴리스틱('Assume that a premise entails all of its contiguous subsequences')과 어휘 겹침 휴리스틱을 들고, 'they are not valid inference strategies because they fail on many examples'라고 말합니다(예: 'The doctor near the actor danced'는 'The actor danced'를 함의하지 않음). 후보가 독립 답을 포함하는지 보는 것이 바로 그 휴리스틱입니다. (2) Saltzer & Schroeder의 안전한 기본값 원칙: 'Base access decisions on permission rather than exclusion.' 허가 기반 장치의 결함은 거부하는 쪽으로 실패해 눈에 띄고, 제외 기반 장치의 결함은 허용하는 쪽으로 실패해 모르고 지나칠 수 있습니다.

## 적용

same_answer는 비교 후보의 자동 검증 관문입니다(_same_as_independent, 그리고 _verdict의 None→보류 단계, validation.py:261-265). 글로만 된 출구(185행)는 부분 연속열 휴리스틱을 씁니다. 'A안이 B안보다 예산이 많다'는 'B안'을 포함하지만 B안의 예산이 더 많다고 주장하지 않습니다. 숫자 출구(_anchored, 196-213행)는 값 앞의 이름만 확인합니다. 둘 다 제외 장치(불일치를 찾지 못하면 받아들임)이므로, 결함은 리뷰 한 번에 하나씩 잘못 받아들인 답으로 드러납니다. comparison.json이 이미 긍정 조건(각 대상의 값을 밝힘)을 말하고 structure.entities가 이름을 주므로, 그 조건이 보일 때만 True를 줄 수 있습니다. 범위: same_answer의 entities 분기만이며, 이 분기는 _entities()를 통해 비교 항목만 탑니다. numeric, table, condition, multi_hop은 지금 규칙을 유지합니다.

## 가설

세 수정 모두, 출구의 기본값이 True인 판단식 안에서 리뷰어가 짚은 분기만 고쳤습니다. 부분 문자열 포함과 값 앞의 이름은 겉 확인이라, 비교 답이 주장하는 관계(어느 대상을 골랐는지, 어느 방향인지)를 보지 못합니다. 그래서 회차마다 비교 항목의 True 출구가 하나씩 남습니다. 처음은 순서 없는 값, 다음은 값 하나짜리 단위, 이번은 글로만 된 답입니다. 다음으로 예상되는 것은 같은 값에 반대 결론인 답입니다. 'B안이 2억원으로 더 많다'에 대한 'B안이 2억원으로 더 적다'는 6c334d7에서 True를 돌려줍니다(코드를 읽어서 얻었고 돌려 보지는 않음). 버티는 수정은 비교 항목의 True가 주제 규칙을 긍정적으로 요구하게 만듭니다. 독립 답이 structure.entities의 모든 대상을 자기 값과 함께 정확히 한 번씩 대고, 그 값마다 후보에서 같은 대상에 붙어 있어야 합니다. False는 값이 다른 대상 아래에서만 나오거나 글이 아예 포함되지 않을 때 그대로 둡니다. 포함되지만 같지 않은 글로만 된 비교 답을 포함해, 그 밖의 모든 경우는 None(보류)을 돌려줍니다.

## 반대 근거

- 여기서는 실행하지 않았습니다(셸 없음). 리뷰어의 재현은 3회차에서 인용했습니다. 'B안이 2억원으로 더 적다' 쌍은 코드를 읽어서 얻었습니다. facts()는 두 글 모두에서 2억원에 대해 'B안이' 구간을 주므로 _anchored는 True를 돌려줍니다.
- 대상 확인 규칙은 기존 기대값 하나를 바꿉니다. test_comparison_values_must_belong_to_the_same_entity_as_in_the_independent_answer에는 B안만 다루는 판정 'B안이 2억원으로 더 많다'에 대해 'B안이 2억원으로 더 많다' → auto_validated 행이 있습니다. 규칙대로라면 held가 됩니다. 그 행을 held로 바꾸거나, 테스트 검증기가 'A안 1억원, B안 2억원'으로 답하게 해야 합니다.
- Kamalloo 외 2023에 따르면 어휘 일치는 주로 반대쪽으로 틀립니다(맞는 답을 거부함, 실패의 'more than 50%'가 뜻이 같은 답). 겉 규칙을 엄격하게 하면 맞는 비교 답을 많이 보류하고, 사람 검토 대기열이 늘어납니다.
- 3회차 리뷰어는 '같은 결론을 확인하거나 보류로 보내라'고 요구합니다. 글로만 된 답을 모두 보류하는 것이 너무 거칠다고 볼 수도 있지만, '보류로 보내라'는 조건은 분명히 만족합니다.

## 다른 방법

- 글로만 된 비교: 후보가 독립 답이 댄 대상만 대면 True. 보류 부담은 작지만 여전히 부분 연속열 휴리스틱을 씁니다. 'B안은 예산이 많지 않다'가 통과합니다. 또 하나의 받아들이기 기본값 땜질이므로 택하지 않았습니다.
- 값 표기를 정규화한 뒤 같은지 비교(각 수량을 (값, 단위)로 바꾼 뒤 후보 == 독립 답). 정확하지만 facts()에서 구간을 따로 기록해야 하고, 문장형 후보를 거의 모두 보류합니다. 대상 확인 규칙이 있으면 필요 없습니다.
- LLM 함의 채점이나 검증기의 {대상: 값} 구조 출력. 가장 강하게 묶지만 VERDICT_FIELDS, validator.txt, 프롬프트 SHA가 바뀌고 호출이 늘며, Kamalloo 외는 자동 채점기가 지어낸 긴 답을 잘못 판정한다고 보고합니다. 이 지적에는 너무 큽니다.
- 대체가 아닌 보조 방법: validator.txt에 비교 답은 각 대상 앞에 그 값을 쓰라는 줄을 하나 더합니다(prompts/A/comparison.txt가 이미 생성기에 요구하는 방식). 대상 확인 규칙에서 보류 비율을 낮춥니다. 프롬프트 SHA가 바뀌며, manifest가 이미 이를 기록합니다.

## 실험

수정 전 6c334d7에서 돌립니다. (a) 리뷰어의 재현(비교 후보 'A안이 B안보다 예산이 많다', 검증기 판정 verdict('B안')) → 예측 auto_validated. (b) same_answer('B안이 2억원으로 더 적다', 'B안이 2억원으로 더 많다', ['A안','B안']) → 예측 True. (c) same_answer('B안은 예산이 많지 않다', 'B안', ['A안','B안']) → 예측 True. 수정 뒤에는 (a) held, (b) None, (c) None입니다. same_answer('A안은 1억원, B안은 2억원', 'A안 1억원, B안 2억원', ['A안','B안']) → True. 같은 독립 답에 대한 'A안은 2억원, B안은 1억원' → False. test_comparison_attribution_is_read_from_the_entity_names_for_every_value의 모든 행은 독립 답이 두 대상을 모두 다루므로 결과를 유지합니다. test_same_answer_compares_after_value_and_unit_normalization과 test_each_check_sends_the_candidate_to_its_state의 비교 아닌 행은 entities를 넘기지 않으므로 모두 결과를 유지합니다. 그다음 same_answer와 _anchored를 부르는 곳을 grep해 entities 분기만 바뀌었는지 확인합니다. _single_unit_verdict는 entities 없이 부르므로 영향이 없습니다.

## 결과

관측했지만 검증하지 않은 초안입니다. 수정 전 c9ff991(코드는 6c334d7과 같음)에서:
- (b) `same_answer('B안이 2억원으로 더 적다', 'B안이 2억원으로 더 많다', ['A안','B안'])`은 True를 돌려줬습니다.
- (c) `same_answer('B안은 예산이 많지 않다', 'B안', ['A안','B안'])`은 True를 돌려줬습니다.
- `same_answer('A안이 B안보다 예산이 많다', 'B안', ['A안','B안'])`은 True를 돌려줬습니다.
- (a) 행마다 자기 검증기 답을 갖도록 고쳐 쓴 `test_comparison_values_must_belong_to_the_same_entity_as_in_the_independent_answer`는 리뷰어의 행(검증기 `B안`)과 `더 적다` 행에서 실패했습니다. 둘 다 held를 기대했는데 auto_validated에 이르렀습니다.

수정(`_comparison_same`, 이 결과를 더하는 커밋) 뒤에 비교 항목은 두 경우에만 True를 돌려줍니다. 두 글이 같을 때, 또는 검증기의 답이 모든 대상을 자기 값 앞에 정확히 한 번씩 대고, 그 값마다 후보에서 같은 이름에 붙어 있을 때입니다.
- (a)는 held, (b)는 None, (c)는 None입니다.
- `same_answer('A안은 1억원, B안은 2억원', 'A안 1억원, B안 2억원', ['A안','B안'])`은 True이고, 바뀐 후보는 False입니다.
- `test_comparison_attribution_is_read_from_the_entity_names_for_every_value`의 모든 행이 결과를 유지합니다. entities를 넘기지 않는 `test_same_answer_compares_after_value_and_unit_normalization`과 `test_each_check_sends_the_candidate_to_its_state`의 모든 행도 마찬가지입니다.
- tests/golden/test_validation.py: 55 passed.
- grep으로 확인한 결과, entities를 넘기는 곳은 두 답 비교 지점뿐입니다. `_verdict`의 None→보류 단계와 `_same_as_independent`입니다. `_single_unit_verdict`와 `_not_copied`는 entities 없이 부르며 바뀌지 않았습니다.
- 보류 비율을 낮추려고 `validator.txt`에 비교 대상마다 값을 쓰라고 요청하는 줄을 하나 더했습니다. 보류 비율 자체는 재지 않았습니다.

## 남은 한계

후보는 독립 답 밖의 주장을 더할 수 있습니다(예: 대상별 목록은 맞는데 뒤에 반대되는 문장이 붙음). same_answer는 모든 주제에서 독립 답이 다뤄졌는지만 확인하며, 이 수정은 그것을 바꾸지 않습니다. 대상 이름은 여전히 부분 문자열로 맞추며('AB안' 안의 'B안'), 값 앞의 이름만 셉니다('2억원(A안)'은 보류). 글로만 된 내용 비교('A안은 클라우드, B안은 온프레미스')는 같지 않으면 모두 보류됩니다. 사람 검토 대기열이 얼마나 늘지는 재지 않았습니다.
