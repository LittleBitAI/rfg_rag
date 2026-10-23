# 리뷰 조사 · F2, 1회차

집계 결과와 측정 조건은 Git에 보관하고, 실제 질문·정답·근거·OCR 텍스트와 레코드별 내보내기는 Git에서 제외된 로컬 `artifacts/`에 보관합니다.

복원 출처: 정리 전 `artifacts/review-round2/originals/` 또는 `d7d1682^`. 아래 수치와 검증 기록은 당시 실행에서 관측한 과거 기록이며, 이번 작업에서 다시 측정한 결과가 아닙니다.

PR #28 리뷰 2회차의 수정 전에 2026-10-14에 쓴 조사 초안입니다. 검증된 사실이나 공용 규칙이 아니며, 리뷰는 이 문서를 수정과 함께 읽습니다.

## 문제

improve()는 반복을 이어서 할 때, manifest.json이 있는 {loop_id}-r{n} 이름의 실행이면 무엇이든 다시 씁니다. 그 실행을 이 반복이 고정된 plan, 설정, 기준으로 만들었는지는 확인하지 않습니다. 지켜야 할 규칙은 이렇습니다. 반복이 다시 쓰거나, 검증하거나, open_bundles에 쓰거나, report.json에 세는 모든 회차는 이 loop_id가 회차 n에서, start.json에 고정된 plan, plan 해시, 시작 기록으로 만든 것이어야 합니다. 이름만 같은 실행, 예를 들어 plan p1으로 따로 돌린 generate('A', ..., 'l1-r1')도 받아들여집니다. 그 실행은 자기 p1 기준으로 검증되고, p3의 회차로 보고됩니다.

발생: 반복, 1·2회차.

- [P1] [P1] golden_pipeline/improvement.py:165 — 새 반복이 다른 plan의 실행을 소리 없이 받아들일 수 있습니다

## 실패한 수정

- 1회차 수정(01212b1): _pin은 처음 부를 때 start.json(config, plan_id, plan_sha256, thresholds)을 쓰고, 나중에 부를 때는 지금 인자와 비교합니다. 인자를 기록에 묶지만, _round의 재사용 결정(improvement.py:165, `if not (run_dir / 'manifest.json').exists()`)과 _rounds의 훑기(improvement.py:269-274)는 여전히 이름만으로 주인을 정합니다. 처음 부를 때 start.json은 넘어온 인자로 만들어지므로 비교할 대상이 없고, 이미 있던 {loop_id}-r1은 소리 없이 받아들여집니다(2회차 재현). 회귀 테스트(tests/golden/test_improvement.py:206-228)는 이미 기록된 반복의 인자를 바꾸는 경우만 다룹니다.
- 1회차 리뷰어는 '회차를 다시 쓰기 전에 plan 정체와 해시를 고정하고 확인하라'고 했습니다. 수정은 다시 쓰는 회차가 아니라 호출의 plan 정체를 확인했고, 그래서 같은 지적이 다른 진입 경로로 다시 나왔습니다.

## 출처

### S1 — Requests that reuse idempotency tokens but alter request parameters now throw an error (Stripe 변경 기록 2015-09-03)

- URL: https://docs.stripe.com/changelog/2015-09-03/reuse-idempotency-tokens-alter-error
- 확인일: 2026-10-14
- 위치: What's new
- 인용: Returns an error if a request reuses an idempotency token with different parameters than the original request. Previously, errors were only returned for reusing the same idempotency token across different API endpoints. ... An error is now returned for reused idempotency tokens with different parameters, preventing unintended duplicate requests.
- 적용: {loop_id}-r{n}은 회차의 멱등 키 역할을 합니다. 다시 쓸 때는 저장된 요청(manifest의 plan과 정책)을 지금 요청과 비교해 다르면 거부해야 하며, _round가 그래야 합니다.
- 반대 근거: Stripe 키는 만료되며(제3자 출처에 따르면 24시간 뒤 정리), 그 뒤에 다시 쓰면 새 객체가 생깁니다. 여기의 실행 이름은 만료되지 않으므로 확인이 끝없이 유지돼야 합니다.
- 검증: 새 테스트에서, 반복의 이름을 쓰지만 다른 plan으로 만들었거나 반복 밖에서 만든 실행은 다시 쓰지 않고 거부합니다.

### S2 — luigi 패키지 API — Task.complete

- URL: https://luigi.readthedocs.io/en/stable/api/luigi.html
- 확인일: 2026-10-14
- 위치: Task.complete 설명
- 인용: If the task has any outputs, return True if all outputs exist. Otherwise, return False. However, you may freely override this method with custom logic.
- 적용: _round도 같은 '있으면 끝난 것' 규칙(manifest.json이 있으면 생성을 건너뜀)을 씁니다. Luigi 문서도 있다는 것만으로 부족하면 재정의하라고 하며, 여기가 그런 경우입니다.
- 반대 근거: Luigi에서 이 기본값은 일부러 정한 관례이지 버그가 아닙니다. 이름이 겹칠 수 없으면 이름 기준 완료도 괜찮습니다.
- 검증: 수정 뒤 회차가 끝났다고 보려면 주인 확인과 있음이 모두 필요하며, 이어하기 테스트는 여전히 자기 회차를 다시 씁니다.

### S3 — 01212b1 시점의 golden_pipeline/improvement.py

- URL: golden_pipeline/improvement.py
- 확인일: 2026-10-14
- 위치: _round 161-178행; _rounds 269-274행; _pin 301-315행; _revision 193-205행
- 인용: if not (run_dir / "manifest.json").exists(): stop = _generate(...) ... path = loop_dir / "start.json"; if not path.exists(): storage._write_json(path, current); return
- 적용: 재사용 결정이 이름과 있음만으로 이뤄지고, 고정 기록이 없으면 지금 호출로 만들어지므로 이미 있는 실행을 걸러 낼 수 없다는 것을 보여 줍니다.
- 반대 근거: 없음
- 검증: 수정은 _round와 _rounds에서 부르는 주인 확인 함수 하나를 더합니다.

### S4 — golden_pipeline/generation.py의 manifest 필드

- URL: golden_pipeline/generation.py
- 확인일: 2026-10-14
- 위치: generate 33-84행
- 인용: info = {**_plan_info(plan_id, plan, plan_sha, topic, sent), ... "policy": revision["policy"] if revision else None, ...}
- 적용: manifest는 이미 plan_id, plan_sha256, 반복 정책(loop_id, round)을 기록하고, 따로 돌린 실행의 정책은 None입니다. 그래서 start_sha256 말고는 새 저장 없이 주인을 확인할 수 있습니다.
- 반대 근거: 없음
- 검증: 새 테스트에서 따로 돌린 실행(정책 None)은 거부됩니다.

### S5 — tests/golden/test_improvement.py 이어하기 테스트

- URL: tests/golden/test_improvement.py
- 확인일: 2026-10-14
- 위치: 188-228행
- 인용: test_resume_refuses_a_loop_whose_config_plan_or_criteria_changed: p3 반복 l1을 중단한 뒤 바뀐 config, plan, 검증기 프롬프트로 improve를 부르고 'is different from when it started' [{changed}]를 기대합니다
- 적용: 유일한 F2 막이는 기록된 반복의 인자를 바꿉니다. 반복이 만들지 않은 실행을 반복의 이름으로 만드는 테스트는 없습니다.
- 반대 근거: 없음
- 검증: 새 이름 겹침 테스트가 이 빈틈을 메웁니다.

## 주장

- C1 (출처; S1): 호출자가 고른 키로 저장된 결과를 요청 인자가 다른데 다시 쓰는 것은 재생이 아니라 오류여야 합니다.
- C2 (출처; S2): 출력이 있으면 완료로 보는 것은 기본값일 뿐이며, 도구 자신도 있음만으로 부족하면 재정의하라고 말합니다.
- C3 (출처; S3): _round와 _rounds는 실행 이름과 manifest.json이 있는지만으로 회차의 주인을 정합니다.
- C4 (해석; S3, S5): 1회차 수정은 호출 인자를 start.json에 묶었지만, 다시 쓰는 실행은 start.json에 묶지 않았습니다. start.json이 없으면 지금 호출로 만들어지므로, 이미 있던 실행이 확인 없이 받아들여집니다. 테스트는 인자 변경만 다뤘습니다.
- C5 (해석; S1, S3, S4): _round와 _rounds 모두에서 다시 쓰는 manifest마다 policy.loop_id, policy.round, plan_id, plan_sha256, 새 policy.start_sha256을 고정 기록과 비교하면, 두 재현과 나중에 끼어든 남의 회차를 모두 막습니다.

## 핵심 원리

호출자가 고른 키로 저장된 결과를 찾아 다시 쓸 때, 키만으로는 저장된 결과가 지금 요청에 대한 답이라는 증거가 되지 않습니다. 저장 기록은 원래 요청을 담아야 하고, 요청이 다른 재사용은 재생이 아니라 오류입니다. Stripe는 2015-09-03에 다른 인자로 다시 쓴 멱등 키에 대해 이렇게 바꿨습니다. '출력이 있음'을 '작업 끝남'으로 보는 시스템(Luigi의 기본 Task.complete)은 반대 동작을 물려받으므로, 있음만으로 부족하면 완료 판정을 직접 재정의해야 합니다.

## 적용

{loop_id}-r{n}은 호출자가 고른 키이고, 실행 폴더는 _round가 다시 쓰는 저장 결과입니다(golden_pipeline/improvement.py:161-178). generation.generate는 아무 run_id나 받는 공개 진입점이므로(generation.py:33), 반복이 만들지 않았어도 그 이름의 실행이 있을 수 있습니다. 실행 manifest는 이미 원래 요청(generation.plan_id, plan_sha256, loop_id와 round를 담은 policy; generation.py:70-80)을 저장하므로, 정책에 start.json 해시를 더하는 것 말고는 새 저장 없이 비교할 수 있습니다. 확인은 _round(생성 건너뛰기 분기)와 _rounds(141행의 open_bundles와 246행의 _report가 씀) 둘 다에 둬야 합니다. 한쪽에만 두면 다른 쪽 읽기가 남의 실행을 받아들입니다.

## 가설

회차의 주인을 실행 이름과 파일이 있는지로 추론합니다. 고정 기록은 반복의 입력만 덮고, 다시 쓰는 실행의 출처는 덮지 않습니다. 수정은 다시 쓰는 모든 회차가 거치는 주인 확인 하나입니다. 실행은 manifest.generation.policy의 loop_id == loop_id이고 round == n이며, generation.plan_id와 plan_sha256이 고정 값과 같고, policy.start_sha256(새 필드, _revision이 start.json의 sha256을 더함)이 지금 start.json의 sha256과 같을 때만 이 반복의 회차 n입니다. _round는 manifest가 있어 생성을 건너뛸 때마다 확인을 부릅니다. _rounds는 내주는 모든 폴더에 대해 확인을 부르므로, open_bundles와 _report는 남의 실행을 읽지 않습니다. 따로 돌린 실행은 정책이 None이라 거부됩니다.

## 반대 근거

- Luigi는 일부러 출력이 있으면 완료로 보므로, 이름 기준 재사용은 일부 파이프라인 도구에서 알려지고 받아들여진 관례입니다. 하지만 Luigi는 complete()를 재정의할 수 있다고 적고 있고, 여기서는 다시 쓰는 실행이 검증과 보고 수를 정하므로 이 관례가 맞지 않습니다.
- start.json, config, plan, thresholds가 바이트까지 같고 loop_id도 같으면, 앞서 지운 반복 기록이 만든 실행도 확인을 통과합니다. 같은 반복이라고 볼 수 있으니, 받아들이는 것은 구멍이 아니라 허용할 만한 일입니다.

## 다른 방법

- 시작할 때만 거부(start.json이 아직 없을 때 {loop_id}-r* 실행이나 목록 항목이 있으면 거부): 2회차 재현은 막지만, 중단과 이어하기 사이에 r{k+1}로 만들어진 남의 실행은 놓칩니다. manifest 확인이 그 경우를 덮으므로 이 방법은 필요 없습니다.
- 실행 ID에 반복 고유값(예: start.json에 저장한 uuid)을 붙여 겹침을 막기: 테스트와 보고가 기대는 실행 ID('l1-r1')가 바뀌고, 이어하기에서는 여전히 주인을 확인해야 하므로 확인을 없애지 못하고 일만 늘립니다.
- 다시 쓰는 manifest의 plan_id와 plan_sha256만 비교: 같은 plan을 쓴 다른 반복이나 반복 밖의 실행, 반복 기록을 다시 만들었을 때의 config/threshold 차이를 놓칩니다. loop_id, round, start_sha256도 똑같이 싸게 비교할 수 있습니다.

## 실험

기존 테스트 데이터로 테스트 하나를 더합니다. plan p1(numeric: 1)을 만들고 generation.generate('A', 'numeric', 'p1', 'l1-r1', ...)을 따로 돌린 뒤 improve('numeric', 'p3', 'l1', loop_config(max_rounds=1), Generator(), Validator())를 부릅니다. l1-r1을 이름으로 대는 ValueError가 나야 하고, 생성기나 검증기 호출이 없어야 하며, report.json도 쓰지 않아야 합니다. 두 번째 경우: Validator(crash_on=3)로 p3의 반복 l1을 중단하고, 'l1-r3'을 따로 만들거나(또는 loops/l1을 지우고 다른 max_calls로 다시 만들고) 이어합니다. 이것도 거부해야 합니다. 기존 이어하기 테스트(test_improvement.py:188)는 그대로 통과해야 하며, 반복 자신의 회차는 여전히 다시 쓴다는 것을 보여 줍니다.

## 결과

관측했지만 검증하지 않았으며, 아직 초안입니다. 수정은 이 문서를 담은 2회차 커밋("golden_pipeline 자기 개선 리뷰 2 수정: ...")에 8363fa8 위로 들어갔습니다. 수정 전 재현(plan p1, 따로 돌린 `generate('A', 'numeric', 'p1', 'l1-r1', ...)`, 이어서 `improve('numeric', 'p3', 'l1', max_rounds=1)`)에서는 plan_id p3, rounds ['l1-r1']인 보고서가 나왔고, l1-r1/validation.json의 plan_id는 p1이었습니다. 수정은 가설을 따릅니다. `_generated(topic, loop_id, n)`가 manifest의 policy.loop_id, policy.round, policy.start_sha256, generation.plan_id, plan_sha256을 반복과 start.json에 비교합니다. `_round`는 생성을 건너뛰기 전에, `_rounds`는 내주는 모든 폴더에 대해 이를 부르므로, `open_bundles`와 `_report`도 이를 거칩니다. `_revision`은 정책에 start_sha256을 더합니다. 테스트: `tests/golden/test_improvement.py::test_a_loop_refuses_a_run_under_its_name_that_it_did_not_make`의 세 경우입니다. 다른 plan으로 따로 돌린 실행(다섯 키 모두 다름), 중단 뒤 따로 만든 l1-r3(loop_id, round, start_sha256), 다른 max_calls로 다시 만든 start.json(start_sha256)입니다. 각각 실행 이름을 대는 ValueError를 내고, 생성기를 부르지 않으며, report.json을 쓰지 않습니다. 세 경우 모두 01212b1의 improvement.py에서 실패하고 수정에서 통과합니다. 바꾸지 않은 이어하기 테스트(`test_resume_continues_after_the_last_completed_round_without_duplicate_ids`)는 둘 다에서 통과하므로, 반복 자신의 회차는 여전히 다시 씁니다. 반대 근거 절의 예측대로, 같은 바이트로 다시 만든 start.json은 같은 반복으로 받아들여집니다. 남은 한계 절의 manifest 없는 중단 구간은 다루지 않았습니다.

## 남은 한계

여기서는 돌리지 않았습니다(셸 없음). 이 확인 밖에 중단 구간 하나가 남습니다. write_run은 manifest.json을 쓰기 전에 실행 폴더를 만듭니다(storage.py:51-57). 그 사이에 중단되면 manifest 없는 폴더가 남고, 이어할 때 _round가 생성을 시도하면 new_run_dir가 FileExistsError를 냅니다. 받아들임과는 다른 문제입니다. start_sha256이 start.json의 원래 바이트를 해시할지, 정규화한 JSON 덤프를 해시할지는 수정의 세부 사항입니다. _pin이 파일을 한 번만 쓰므로 원래 바이트가 가장 단순합니다.
