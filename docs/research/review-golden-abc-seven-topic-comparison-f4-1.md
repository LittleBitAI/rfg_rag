# 리뷰 조사 · F4, 1회차

집계 결과와 측정 조건은 Git에 보관하고, 실제 질문·정답·근거·OCR 텍스트와 레코드별 내보내기는 Git에서 제외된 로컬 `artifacts/`에 보관합니다.

복원 출처: 정리 전 `artifacts/review-round2/originals/` 또는 `d7d1682^`. 아래 수치와 검증 기록은 당시 실행에서 관측한 과거 기록이며, 이번 작업에서 다시 측정한 결과가 아닙니다.

PR #65 리뷰 2회차의 수정 전에 2026-10-18에 쓴 조사 초안입니다. 검증된 사실이나 공용 규칙이 아니며, 리뷰는 이 문서를 수정과 함께 읽습니다.

> F4 조사가 아닙니다(리뷰 3회차, F5). 이 문서는 F4로 분류돼 있지만, 아래 모든 절은 review-packets의 plan 해시, 곧 2회차 F1을 분석하며 `review-golden-abc-seven-topic-comparison-f1-1.md`와 같은 주제입니다. F4, 즉 이어할 때 후보 하나의 끝난 하위 호출 결과에 대해서도, 2회차 F4 수정이 쓴 재사용 키에 대해서도 아무 말도 하지 않습니다. 그 키는 후보끼리 겹쳤고 3회차에서 발견됐습니다. 이 문서를 F4 수정의 근거로 인용하지 마세요. F4 조사는 `review-golden-abc-seven-topic-comparison-f4-2.md`입니다.

## 문제

`review_packets()`는 고정한 실험의 근거, 곧 freeze.json에 SHA-256이 적힌 plan의 근거만 인용해야 합니다. comparison.py:177에서 outputs/plans/{plan_id}.json을 지금 디스크 상태 그대로 다시 읽고, `plan.load_plan`이 돌려준 해시를 버립니다. 표본 항목마다 인용하는 근거는 그 사본에서 옵니다(`_packet` -> `validation.evidence_units(item, bundles[...])`, comparison.py:227). 실행 뒤에 plan 파일을 고치면, 방식을 가린 검토자는 후보를 만들고 검증한 것과 다른 근거를 판단합니다. 어기는 규칙: 비교가 읽는 모든 것은 읽는 순간에 고정한 해시에 묶여 있어야 합니다.

발생: 반복, 1·2회차.

- [P1] [P1] golden_pipeline/validation.py:122 — 한도에 걸려 중단되면 후보 하나 안에서 끝난 하위 호출 결과를 여전히 버립니다

## 실패한 수정

- 1회차(89f54e6)는 `_checked_runs`/`_check_run`(comparison.py:65-105)을 더했습니다. 실행 manifest마다 기록된 `generation.plan_id/plan_sha256/topic_spec_sha256`을 freeze.json과 비교하고, 비교용 밖 묶음의 출력을 거부하며, 프롬프트 해시와 설정을 확인합니다. 그 비교의 양쪽은 모두 과거에 쓴 기록입니다. 어느 쪽도 `review_packets`가 묶음을 만들 때 파싱하는 plan 파일이 아닙니다. 수정은 '이것이 고정한 실행인가?'에 답했을 뿐 `review_packets` 자신이 디스크에서 무엇을 읽는지는 적어 보지 않았으므로, plan 파일의 두 번째 읽기(comparison.py:177)는 확인되지 않은 채 남았습니다.
- 1회차 테스트(tests/golden/test_cli.py 180-205행 부근)는 freeze.json에 틀린 해시를 써서(`write_freeze(plan_sha='0'*64)`) 불일치를 흉내 내고 `compare`만 돌립니다. 올바른 실행 뒤에 plan 파일을 고치지 않고 `review-packets`도 돌리지 않으므로, 2회차가 제기한 경우는 시험되지 않았습니다.
- 1회차 조사(291ed08)는 같은 원인을 찾았지만 코드 수정이 뒤따르지 않았습니다. HEAD의 comparison.py:177은 여전히 `planned, _ = plan.load_plan(...)`입니다. 지적이 남은 것은 수정을 시도했다가 실패해서가 아니라 수정을 하지 않았기 때문입니다.

## 출처

### S1 — CWE-367: Time-of-check Time-of-use (TOCTOU) Race Condition

- URL: https://cwe.mitre.org/data/definitions/367.html
- 확인일: 2026-10-18
- 위치: Description; Potential Mitigations
- 인용: "The product checks the state of a resource before using that resource, but the resource's state can change between the check and the use in a way that invalidates the results of the check." Mitigation: "Ensure that locking occurs before the check, as opposed to afterwards, such that the resource, as checked, is the same as it is when in use." Also: "The most basic advice for TOCTOU vulnerabilities is to not perform a check before the use. This does not resolve the underlying issue of the execution of a function on a resource whose state and identity cannot be assured, but it does help to limit the false sense of security given by the check." Shrinking the window "will not fix the problem, but it could make it more difficult for an attack to succeed."
- 적용: 생성할 때 plan 파일의 상태는 기록된 manifest 해시로 확인됐지만, 바뀌었을 수 있는 뒤에 comparison.py:177/227에서 쓰입니다. 쓰는 시점에는 확인 결과가 낡은 것입니다.
- 반대 근거: CWE는 이를 프로세스나 스레드 사이의 경쟁으로 다룹니다. 여기서의 틈은 나중의 손 편집이므로 잠금 대책은 맞지 않고, '확인한 자원이 쓰는 자원이어야 한다'는 원칙만 옮겨 옵니다.
- 검증: 수정 뒤 review_packets는 `_packet`에 들어가는 같은 plan 읽기를 해시하고, 같은 호출에서 freeze.json과 비교합니다. 새 테스트는 올바른 실행 뒤에 p3.json을 고치고, 검토 폴더를 쓰지 않은 채 ValueError가 나기를 기대합니다.

### S2 — SLSA v1.2 — Build: Verifying artifacts

- URL: https://slsa.dev/spec/v1.2/verifying-artifacts
- 확인일: 2026-10-18
- 위치: 1단계, "Given an artifact and its provenance"
- 인용: "Verify the envelope's signature using the roots of trust ..." then "Verify that statement's `subject` matches the digest of the artifact in question." These steps assume the verifier has been bootstrapped with roots of trust. If provenance is not in the recommended format, "the verifier SHOULD perform equivalent checks".
- 적용: freeze.json은 신뢰 기준, 실행 manifest는 출처 기록 역할을 합니다. 1회차는 출처 기록을 신뢰 기준과 대조했지만, 손에 든 산출물, 곧 묶음을 만들 때 읽는 plan 파일이 믿는 해시와 맞는지는 확인하지 않았습니다.
- 반대 근거: SLSA는 서명된 공급망 증명을 다룹니다. golden_pipeline에는 서명이 없으므로, 비유는 손에 든 산출물의 해시를 맞추는 단계에만 해당합니다.
- 검증: 수정 뒤 review_packets는 파싱하는 plan의 SHA-256을 freeze.json의 plan.sha256과 비교합니다. 'subject matches the artifact in question' 단계입니다. 새 테스트는 바뀐 파일이 거부되는 것을 보여 줍니다.

### S3 — golden_pipeline/comparison.py (review_packets, _check_run, _packet)

- URL: golden_pipeline/comparison.py
- 확인일: 2026-10-18
- 위치: 85-92행(_check_run 고정 튜플), 175-178행(review_packets), 226-227행(_packet)
- 인용: `pinned = (record["plan"]["plan_id"], record["plan"]["sha256"], record["topic_specs"][topic])` compared with the manifest's `generation` fields; `planned, _ = plan.load_plan(record["plan"]["plan_id"])`; `units = validation.evidence_units(item, bundles[item["bundle_id"]])`
- 적용: 유일한 확인이 manifest와 freeze.json을 비교하며, 묶음 근거에 쓰는 plan 내용은 해시를 버린 채 읽는다는 것을 보여 줍니다.
- 반대 근거: `_checked_runs`는 review_packets 안에서 주제마다 돌므로, 다른 plan으로 만든 실행은 여전히 거부됩니다. 빈틈은 올바른 실행 뒤에 plan 파일을 고치는 경우뿐입니다.
- 검증: 고친 줄은 해시를 남기고, `folder.mkdir()` 전에 record['plan']['sha256']과 다르면 오류를 냅니다. 새 테스트는 HEAD에서 실패하고 수정 뒤에 통과합니다.

### S4 — golden_pipeline의 기존 plan 해시 막이

- URL: golden_pipeline/experiment.py
- 확인일: 2026-10-18
- 위치: experiment.py:79-86(pro_packets); report.py:43-45(compare); plan.py:146-148(asked_document); validation.py:255-257
- 인용: pro_packets: `planned, sha = plan.load_plan(experiment_id)` ... `frozen = {"계획": record["plan"]["sha256"], ...}` ... `raise ValueError(f"실험 {experiment_id} 를 고정한 뒤 바뀌었습니다: {changed}")`. report.compare: `planned, current_sha = plan.load_plan(plan_id)` / `if current_sha != plan_sha: raise ValueError(...)`. experiment.estimate:214 also discards the hash, but it runs before any run exists.
- 적용: 저장소는 plan 내용이 결과에 들어가는 곳마다 이미 이 방식을 씁니다. 실행 뒤에 plan을 쓰는 곳 중 review_packets만 예외이므로, 수정은 이 방식을 따라 합니다.
- 반대 근거: experiment.estimate도 해시를 버립니다. 실행 전 비용 추정이라 맞지 않을 고정 실행이 없으므로, 이 버그와 같은 종류가 아닙니다.
- 검증: 수정의 모양과 오류 문구가 pro_packets와 맞습니다. 수정 뒤 `load_plan(`과 `, _ =`을 grep하면 막이 없는 곳은 estimate와 improvement.py:342(비교용 목록)뿐입니다.

### S5 — tests/golden/test_cli.py 1회차 테스트

- URL: tests/golden/test_cli.py
- 확인일: 2026-10-18
- 위치: write_freeze 도우미와 test_compare_refuses_runs_outside_the_frozen_plan_or_train_assignment(180-205행 부근)
- 인용: `write_freeze(plan_sha="0" * 64)` / `with pytest.raises(ValueError, match="고정한 계획"): golden("compare", "x1")`
- 적용: 테스트는 plan 파일이 아니라 freeze 쪽을 바꾸고 compare만 돌리므로, review_packets가 바뀐 plan을 읽는 것을 잡을 수 없습니다.
- 반대 근거: 테스트는 자신이 막는 것(다른 plan으로 만든 실행)에 대해서는 여전히 유효합니다. 틀린 것이 아니라 덜 다룬 것입니다.
- 검증: 새 테스트는 실행 뒤에 outputs/plans/p3.json을 고치고 review-packets를 부릅니다. HEAD에서 실패하고 수정 뒤에 통과해야 하며, 그러면 2회차 경우를 다룬다는 것이 보입니다.

## 주장

- C1 (출처; S1): 확인은 확인한 자원이 쓰는 시점에도 확인할 때와 같을 때만 유효합니다.
- C2 (해석; S1, S2): 기록된 출처를 확인하는 것으로는 부족하며, 실제로 쓰는 산출물의 해시가 믿는 해시와 맞아야 합니다.
- C3 (출처; S3): 1회차 막이는 실행 manifest에 기록된 plan 해시와 freeze.json, 즉 두 기록만 비교하고, 나중에 읽는 plan 파일은 해시하지 않습니다.
- C4 (출처; S3): review_packets는 지금 plan 파일로 묶음 근거를 만들고 load_plan이 돌려준 해시를 버리므로, 실행 뒤의 편집을 알아채지 못합니다.
- C5 (출처; S4): golden_pipeline에서 실행 뒤에 plan 내용을 읽는 다른 곳은 이미 load_plan의 해시를 고정 해시와 비교하며, review_packets만 예외입니다.
- C6 (해석; S5): 1회차 테스트는 freeze 쪽에서, compare에 대해서만 불일치를 흉내 내므로 2회차 지적을 잡을 수 없었습니다.

## 핵심 원리

확인은 쓰는 시점의 상태에 있는 자원에 대해서만 의미가 있습니다. CWE-367은 확인과 사용 사이에 상태가 바뀔 수 있는 자원이 확인을 무효로 만든다고 말하고, 확인한 자원이 쓰는 시점에도 같도록 하라고 권합니다. SLSA 산출물 검증은 출처 기록을 확인하고, 그 출처 기록의 대상이 쓰려는 산출물의 해시와 맞는지도 확인합니다. 올바른 출처 기록만으로는 손에 든 산출물을 보증하지 못합니다.

## 적용

freeze.json은 신뢰 기준, 실행 manifest는 출처 기록 역할을 합니다. 1회차는 출처 기록을 신뢰 기준과 대조했지만, 실제로 쓰는 산출물, 곧 comparison.py:177에서 읽어 comparison.py:227에서 쓰는 plan 파일의 대상 해시 단계는 건너뛰었습니다. 확인과 사용 사이의 틈은 실행을 만든 때와 review-packets를 돌리는 때 사이이며, 며칠일 수 있습니다. `compare()`는 plan 내용을 파싱하지 않습니다. freeze.json 항목, report._collect/read_validated로 읽는 실행 파일, 반복 report.json을 씁니다. 그래서 새 막이는 review_packets에만 필요합니다. 다른 plan 읽기는 이미 이렇게 막습니다. experiment.pro_packets:79-86, report.compare:43-45, plan.asked_document:146-148, validation.py:255-257입니다.

## 가설

막이가 실제로 쓰는 바이트가 아니라 기록된 출처(manifest 대 freeze)를 확인합니다. comparison.py에서 plan 파일 내용을 파싱하는 코드는 `review_packets`뿐이며, 그 내용을 고정 해시에 묶지 않습니다. 수정: `planned, sha = plan.load_plan(record['plan']['plan_id'])`로 받고, `sha != record['plan']['sha256']`이면 ValueError를 냅니다. 거부할 때 아무것도 쓰지 않도록 `_checked_runs`/표본 뽑기 전, `folder.mkdir()` 전에 합니다. experiment.pro_packets(experiment.py:79-86)와 report.compare(report.py:43-45)를 그대로 따릅니다.

## 반대 근거

- CWE-367은 동시 경쟁에 관한 것입니다. 여기서의 변경은 사람이 나중에 고친 것이므로, 위협 모델이나 잠금 대책이 아니라 '쓰는 자원을 확인하라'는 원칙만 옮겨 옵니다.
- plan.load_plan은 파일을 두 번 읽습니다(`_read_json`, 그다음 같은 경로에 `_sha256`). 수정 뒤에도 이론상 두 읽기 사이에 바뀔 수 있습니다. 아주 좁은 틈이고 기존 호출 지점이 모두 같으며, 리뷰어가 제기하지 않았습니다.
- validation.py:255-257은 생성 뒤 plan이 바뀌었으면 이미 검증을 거부합니다. 그래서 받아들인 항목은 고정한 plan으로 검증됐고, 남은 위험은 review_packets가 나중에 읽는 것뿐입니다. 가설을 약하게 하기보다 뒷받침하지만, compare의 수치는 영향을 받지 않는다는 뜻입니다.

## 다른 방법

- `plan.load_plan`에 `expected_sha` 인자를 더해 모든 호출을 한곳에서 확인하기. 확인을 모으지만, 다섯 호출 지점이 이미 자기 문구로 직접 확인하므로 지적에 비해 넓은 리팩터링입니다. 첫 선택이 아닙니다.
- 묶음마다 근거 글을 실행이나 freeze.json에 복사하고 그 사본으로 검토 묶음을 만들기. plan 파일 의존을 없애지만 저장이 늘고 형식이 바뀝니다. golden_pipeline의 다른 곳은 바뀐 plan을 거부하고 새 실행을 만들라고 안내하며, 해시 거부가 이와 맞습니다.
- `_checked_runs`에서 확인을 불러 compare도 바뀐 plan을 거부하게 하기. compare는 plan 내용을 읽지 않으므로, 수치가 바뀌지 않는 상태를 거부하게 됩니다. 일관성을 위해 더할 수는 있지만 지적이 요구하지는 않습니다.

## 실험

tests/golden/test_cli.py에 기존 planned/api 테스트 준비물을 쓰는 테스트 하나를 더합니다. p3에서 B b1을 `--part train`으로 돌리고, 올바른 해시로 `write_freeze()`를 부른 뒤, 비교용 묶음의 단위 글이 바뀌도록 outputs/plans/p3.json을 다시 씁니다. `golden('review-packets', 'x1')`은 ValueError(고정한 plan 문구와 일치)를 내야 하고, outputs/experiments/x1/review는 없어야 합니다. 지금 코드에서는 같은 단계가 대신 고친 글을 인용한 packet.md를 써야 하며, 그러면 가설이 확인됩니다. 이 테스트만 돌린 뒤 검사를 한 번 돌립니다.

## 결과

관측했지만 검증하지 않은 초안입니다. 이 문서의 본문은 review-packets의 plan 해시(2회차 F1)를 조사하며, 분류된 2회차 F4 지적(후보 하나의 판정 안에서 하위 호출 결과를 잃음)이 아닙니다. 둘 다 돌렸습니다.

- plan 해시: 이 문서의 실험은 `tests/golden/test_cli.py::test_review_packets_refuse_a_plan_file_changed_after_the_freeze`입니다. 9272eca에서 실패했고(`DID NOT RAISE`, 검토 폴더가 고친 plan으로 쓰임), 수정 뒤에 통과합니다(F1 문서 참고).
- 제기된 F4: `tests/golden/test_cli.py::test_resuming_a_candidate_refused_mid_verdict_reuses_its_settled_calls`. 여기서 채권 후보의 첫 검증기 호출은 약속을 어기는 출력으로 끝나고, 재시도는 장부에 의해 거부됩니다(`BudgetExceeded`). 후보는 미판정으로 남고, 그다음 `resume`이 돕니다. 9272eca에서 resume은 끝난 첫 호출을 다시 보내, 3번이면 될 검증기 요청이 4번이 됐습니다(`assert 4 == 3`). 끝난 하위 호출 결과를 잃었다는 것이 확인됩니다.
- 수정(9272eca 다음 커밋): `validation._reply`가 호출마다 요청 SHA-256, 시도 번호, 출력을 검증 기록에 남깁니다. `resume_validation`이 이를 `settled`로 넘기므로, `_reply`는 다시 부르지 않고 끝난 출력을 다시 쓰며 비용도 두 번 세지 않습니다. 그 뒤 테스트는 정확히 요청 3번, 검증기 출력 오류로 후보 거부로 통과했습니다.
- 검증기, 채점, 문서 묶음, 다중 근거 하위 호출은 모두 `_reply`를 거치므로 다른 호출 지점은 없습니다. release는 `--experiment`를 거부하므로, release 선별은 빈 `settled`를 넘깁니다.

## 남은 한계

아무것도 돌리지 않았습니다. 이 단계에는 셸이 없습니다. review_packets의 다른 입력이 freeze에 묶여 있는지는 확인하지 않았습니다. 항목 자체를 위해 `_sample`이 읽는 candidates.jsonl/accepted.jsonl/rejected.jsonl과, `_costs`/`_reconcile`이 쓰는 반복 report.json의 비용 항목입니다. 나중에 같은 종류의 지적을 받을 수 있지만 F1과는 별개입니다. freeze.json 자체는 믿는 것으로 보며 보호하지 않습니다.
