# 리뷰 조사 · F1, 1회차

집계 결과와 측정 조건은 Git에 보관하고, 실제 질문·정답·근거·OCR 텍스트와 레코드별 내보내기는 Git에서 제외된 로컬 `artifacts/`에 보관합니다.

복원 출처: 정리 전 `artifacts/review-round2/originals/` 또는 `d7d1682^`. 아래 수치와 검증 기록은 당시 실행에서 관측한 과거 기록이며, 이번 작업에서 다시 측정한 결과가 아닙니다.

PR #65 리뷰 2회차의 수정 전에 2026-10-18에 쓴 조사 초안입니다. 검증된 사실이나 공용 규칙이 아니며, 리뷰는 이 문서를 수정과 함께 읽습니다.

## 문제

A/B/C 비교(`compare`, `review-packets`)는 고정한 실험이 정한 것만 써야 합니다. freeze.json에 SHA-256이 적힌 plan, 비교용(train) 묶음, 고정한 프롬프트와 주제 명세입니다. 1회차는 실행 결과를 이 확인 없이 채점한다는 것을 찾았습니다. 2회차는 `review_packets()`가 plan 파일을 지금 디스크 상태 그대로 읽고(comparison.py:177), `plan.load_plan`이 돌려준 해시를 버린 채, 표본 항목마다 인용할 근거를 거기서 가져온다는 것을 찾았습니다(`_packet` -> `validation.evidence_units(item, bundles[...])`). 실행 뒤에 plan 파일을 고치면, 방식을 가린 검토자는 후보를 만들고 검증한 것과 다른 근거를 보고 판단하게 됩니다.

발생: 반복, 1·2회차.

- [P1] [P1] golden_pipeline/comparison.py:177 — 검토 묶음이 고정한 해시와 더는 맞지 않는 plan을 쓸 수 있습니다

## 실패한 수정

- 1회차 수정(89f54e6)은 `_checked_runs`/`_check_run`을 더했습니다. 실행 manifest마다 기록된 `generation.plan_id/plan_sha256/topic_spec_sha256`을 freeze.json과 비교하고, 판단용(validation)이나 확인용(held-out) 묶음의 출력을 거부하며, 프롬프트 해시와 설정을 확인합니다. 그 비교의 양쪽은 모두 과거 기록이고, 어느 쪽도 묶음을 만들 때 읽는 plan 파일이 아닙니다. 수정은 지적을 '이 실행이 고정한 실행인가'로 받아들였고, `review_packets` 자신이 디스크에서 무엇을 읽는지는 적어 보지 않았습니다. plan 파일은 시간을 두고 두 번 읽힙니다. 한 번은 생성할 때(해시 기록), 한 번은 묶음을 만들 때(해시를 계산하고 버림)이며, 첫 번째 읽기만 확인됩니다.
- 1회차 테스트(tests/golden/test_cli.py:203-205)는 freeze.json에 틀린 해시를 써서(`write_freeze(plan_sha='0'*64)`) plan 불일치를 흉내 내며, `compare`에 대해서만 합니다. 올바른 실행 뒤에 디스크의 plan 파일을 고치지 않고, 그 상태에서 `review-packets`를 돌리지도 않으므로, 2회차가 제기한 경우는 시험되지 않았습니다.

## 출처

### S1 — CWE-367: Time-of-check Time-of-use (TOCTOU) Race Condition

- URL: https://cwe.mitre.org/data/definitions/367.html
- 확인일: 2026-10-18
- 위치: Description; Potential Mitigations
- 인용: "The product checks the state of a resource before using that resource, but the resource's state can change between the check and the use in a way that invalidates the results of the check." Mitigation: "Ensure that locking occurs before the check, as opposed to afterwards, such that the resource, as checked, is the same as it is when in use." Also: "The most basic advice for TOCTOU vulnerabilities is to not perform a check before the use. This does not resolve the underlying issue of the execution of a function on a resource whose state and identity cannot be assured, but it does help to limit the false sense of security given by the check."
- 적용: 실행을 만들 때 plan 파일의 상태는 (기록된 manifest 해시로) 확인됐지만, 바뀌었을 수 있는 뒤에 comparison.py:177에서 쓰입니다. 쓰는 시점에는 확인 결과가 낡은 것입니다.
- 반대 근거: CWE는 이를 프로세스 사이의 동시성 경쟁으로 다룹니다. 여기서의 틈은 나중의 손 편집이므로, 잠금 같은 대책이 아니라 '쓰는 자원을 확인하라'는 원칙만 옮겨 옵니다.
- 검증: 수정은 `_packet`에 들어가는 plan을 읽을 때 해시를 계산하고, 같은 호출에서 freeze.json과 비교합니다. 실험은 올바른 실행 뒤에 plan을 고치고 거부를 기대합니다.

### S2 — SLSA v1.2 — Build: Verifying artifacts

- URL: https://slsa.dev/spec/v1.2/verifying-artifacts
- 확인일: 2026-10-18
- 위치: 1단계, "Given an artifact and its provenance"
- 인용: "Verify the envelope's signature using the roots of trust ..." then "Verify that statement's `subject` matches the digest of the artifact in question." These steps apply after the verifier has been bootstrapped with roots of trust. If the provenance is not in the recommended format, "the verifier SHOULD perform equivalent checks".
- 적용: freeze.json은 신뢰 기준, 실행 manifest는 출처 기록과 같은 역할을 합니다. 1회차는 출처 기록을 신뢰 기준과 대조했지만, 손에 든 산출물(묶음을 만들 때 읽는 plan 파일)이 믿는 해시와 맞는지는 확인하지 않았습니다.
- 반대 근거: SLSA는 서명이 있는 공급망 증명에 관한 것입니다. golden_pipeline에는 서명이 없고, 비유는 '손에 든 산출물의 해시' 단계에만 해당합니다.
- 검증: 수정 뒤 review_packets는 파싱하는 plan의 해시를 freeze.json의 plan.sha256과 비교합니다. 'subject matches artifact in question' 단계에 해당합니다.

### S3 — golden_pipeline/comparison.py (review_packets, _check_run)

- URL: golden_pipeline/comparison.py
- 확인일: 2026-10-18
- 위치: 85-92행(_check_run 고정 튜플), 175-178행(review_packets), 218-230행(_packet)
- 인용: `pinned = (record["plan"]["plan_id"], record["plan"]["sha256"], record["topic_specs"][topic])` compared with the manifest's `generation` fields; `planned, _ = plan.load_plan(record["plan"]["plan_id"])`; `units = validation.evidence_units(item, bundles[item["bundle_id"]])`
- 적용: 유일한 확인이 manifest와 freeze.json을 비교하며, 묶음 근거에 쓰는 plan 내용은 해시를 버린 채 읽는다는 것을 보여 줍니다.
- 반대 근거: 없음
- 검증: 고친 줄은 해시를 남겨, 쓰기 전에 record['plan']['sha256']과 비교합니다.

### S4 — golden_pipeline의 기존 plan 해시 막이

- URL: golden_pipeline/experiment.py
- 확인일: 2026-10-18
- 위치: experiment.py:79-86(pro_packets); report.py:43-45(compare); plan.py:146-148(asked_document)
- 인용: pro_packets: `planned, sha = plan.load_plan(experiment_id)` ... `frozen = {"계획": record["plan"]["sha256"], ...}` ... `raise ValueError(f"실험 {experiment_id} 를 고정한 뒤 바뀌었습니다: {changed}")`. report.compare: `planned, current_sha = plan.load_plan(plan_id)` / `if current_sha != plan_sha: raise ValueError(...)`
- 적용: 저장소는 plan 내용을 쓰는 곳마다 이미 이 방식을 씁니다. review_packets만 예외이므로, 수정은 이 방식을 따라 합니다.
- 반대 근거: 없음
- 검증: 수정의 모양과 오류 문구가 이 호출 지점들과 맞습니다.

### S5 — tests/golden/test_cli.py 1회차 테스트

- URL: tests/golden/test_cli.py
- 확인일: 2026-10-18
- 위치: 180-205행(write_freeze, test_compare_refuses_runs_outside_the_frozen_plan_or_train_assignment)
- 인용: `write_freeze(plan_sha="0" * 64)` / `with pytest.raises(ValueError, match="고정한 계획"): golden("compare", "x1")`
- 적용: 테스트는 plan 파일이 아니라 freeze 쪽을 바꾸고 compare만 확인하므로, review_packets가 바뀐 plan을 읽는 것을 잡을 수 없습니다.
- 반대 근거: 없음
- 검증: 새 테스트는 실행 뒤에 outputs/plans/p3.json을 고치고 review-packets를 확인합니다.

## 주장

- C1 (출처; S1): 확인은 확인한 자원이 쓰는 시점에도 확인할 때와 같을 때만 유효합니다.
- C2 (해석; S1, S2): 기록된 출처를 확인하는 것으로는 부족하며, 실제로 쓰는 산출물의 해시가 믿는 해시와 맞아야 합니다.
- C3 (출처; S3): 1회차 막이는 실행 manifest에 기록된 plan 해시와 freeze.json, 즉 두 기록만 비교하고, 나중에 읽는 plan 파일은 해시하지 않습니다.
- C4 (출처; S3): review_packets는 지금 plan 파일로 묶음 근거를 만들고 load_plan이 돌려준 해시를 버리므로, 실행 뒤의 편집을 알아채지 못합니다.
- C5 (출처; S4): golden_pipeline에서 plan 내용을 쓰는 다른 곳은 이미 load_plan의 해시를 고정 해시와 비교하며, review_packets만 예외입니다.
- C6 (해석; S5): 1회차 테스트는 freeze 쪽에서, compare에 대해서만 불일치를 흉내 내므로 2회차 지적을 잡을 수 없었습니다.

## 핵심 원리

확인은 그 뒤에 쓰는 자원에 대해, 쓰는 시점의 상태로만 유효합니다. CWE-367: 확인과 사용 사이에 상태가 바뀔 수 있는 자원은 확인을 무효로 만듭니다. SLSA 검증은 출처 기록을 확인하고, 그 출처 기록의 대상이 쓰려는 산출물의 해시와 맞는지도 확인합니다. 올바른 출처 기록만으로는 손에 든 산출물을 보증하지 못합니다.

## 적용

comparison.py에서 freeze.json은 신뢰 기준, 실행 manifest는 출처 기록 역할을 합니다. 1회차는 출처 기록을 신뢰 기준과 대조했지만(SLSA 1단계 비슷한 것), 묶음을 만들 때 쓰는 산출물, 곧 comparison.py:177에서 읽는 outputs/plans/{plan_id}.json의 대상 해시 단계는 건너뛰었습니다. '상태가 바뀌는' 틈은 실행을 만든 때와 review-packets를 돌리는 때 사이이며, 며칠일 수 있습니다. `compare()`는 plan 내용을 읽지 않으므로(freeze.json 항목, report._collect/read_validated로 읽는 실행 상태 파일, 반복 report.json을 씀) plan 내용 막이가 필요 없습니다. 막이는 review_packets에만 두면 됩니다.

## 가설

막이가 실제로 쓰는 바이트가 아니라 기록된 출처(manifest 대 freeze)에 붙어 있습니다. comparison.py에서 plan 파일 내용을 파싱하는 경로는 `review_packets`뿐이며, 그 내용을 고정 해시에 묶지 않습니다. 수정: `planned, sha = plan.load_plan(record['plan']['plan_id'])`로 받고, `folder.mkdir()` 전, 어떤 묶음도 쓰기 전에 `sha != record['plan']['sha256']`이면 ValueError를 냅니다. experiment.pro_packets(experiment.py:79-86)와 report.compare(report.py:43-45)를 그대로 따릅니다.

## 반대 근거

- CWE-367은 동시 경쟁을 중심으로 합니다. 여기서의 '변경'은 확인과 경쟁하는 공격자가 아니라 사람이 나중에 고친 것이므로, 위협 모델이 아니라 원칙에 대한 비유입니다.
- plan.load_plan은 파일을 두 번 읽습니다(read_json, 그다음 경로에 _sha256). 그래서 수정 뒤에도 이론상 두 읽기 사이에 바뀔 수 있습니다. 좁은 틈이고 기존 호출 지점 모두에서 같으며, 리뷰어가 제기한 문제가 아닙니다.

## 다른 방법

- `plan.load_plan(plan_id, expected_sha)`로 바꿔 모든 호출에서 확인: 확인을 한곳에 모으지만, 이미 자기 오류 문구를 가진 호출 지점이 다섯 곳(report.compare, plan.asked_document, validation.py:188/255, experiment.pro_packets) 있으므로, 지적에 비해 넓은 리팩터링입니다. 첫 선택이 아닙니다.
- 묶음마다 근거 글을 실행(또는 freeze.json)에 스냅숏으로 담고 그것으로 검토 묶음을 만들기: plan 파일 의존을 없애지만 저장이 늘고 형식이 바뀝니다. 해시 거부가 golden_pipeline의 나머지가 바뀐 plan을 다루는 방식('새 실행을 만든다')과 맞습니다.
- `_checked_runs`에서 확인을 불러 compare도 바뀐 plan 파일을 거부하게 하기: compare의 수치에 영향이 없는 상태를 거부하게 됩니다. 일관성을 위해 원할 수는 있지만, 지적이 요구하지는 않습니다.

## 실험

tests/golden/test_cli.py에서 `planned`/`api` 테스트 준비물을 다시 씁니다. p3에서 B b1을 `--part train`으로 돌리고, `write_freeze()`(올바른 해시)를 부른 뒤, 비교용 묶음의 단위 글이 바뀌도록 outputs/plans/p3.json을 다시 씁니다(한 바이트만 바뀌어도 SHA-256이 바뀜). `golden('review-packets', 'x1')`은 고정한 plan을 말하는 ValueError를 내야 하고, outputs/experiments/x1/review는 없어야 합니다. 지금 코드(89f54e6)에서는 같은 단계가 고친 글을 인용한 packet.md를 써야 하며, 그러면 가설이 확인됩니다. 이 테스트만 돌린 뒤 검사를 한 번 돌립니다.

## 결과

관측했지만 검증하지 않은 초안입니다. 제안한 실험을 `tests/golden/test_cli.py::test_review_packets_refuse_a_plan_file_changed_after_the_freeze`로 돌렸습니다. p3에서 B b1을 `--part train`으로 돌리고 `write_freeze()`를 부른 뒤, outputs/plans/p3.json에서 `130,000,000원`을 `140,000,000원`으로 바꿉니다. 89f54e6 + 조사 문서(9272eca)에서는 `DID NOT RAISE ValueError`로 실패했고, `outputs/experiments/x1/review`가 고친 plan으로 쓰였으므로 가설이 확인됩니다. 9272eca 다음 커밋("golden: tie review packets to the frozen plan and reuse settled validation calls on resume")의 수정은 `review_packets`가 `plan.load_plan`의 해시를 남기고, 그것이 `freeze.json`과 다르면 `_checked_runs`와 `folder.mkdir()` 전에 오류를 내게 합니다. 그 뒤 이 테스트와 test_cli.py, test_experiment.py 전체가 통과했습니다(39 passed). grep으로 보니 comparison.py에서 실행 뒤에 plan 내용을 읽는 다른 곳은 없었습니다.

## 남은 한계

아무것도 실행해 검증하지 않았습니다. 이 단계에는 셸이 없었습니다. review_packets나 compare가 읽는 다른 입력이 freeze에 묶여 있는지는 확인하지 않았습니다. `_costs`/`_reconcile`이 쓰는 반복 report.json의 비용 항목과, 검증하지 않은 실행에 대해 `_sample`이 읽는 candidates.jsonl입니다. 나중에 같은 종류의 지적을 받을 수 있지만 F1과는 별개입니다. freeze.json은 신뢰 기준으로 보며, 그 자체는 보호하지 않습니다.
