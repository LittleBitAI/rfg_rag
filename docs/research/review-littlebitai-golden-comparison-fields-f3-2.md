# 리뷰 조사 · F3, 2회차

PR #76 리뷰 5회차의 수정 전에 2026-10-20에 쓴 조사 초안입니다. 검증된 사실이나 공용 규칙이 아니며, 리뷰는 이 문서를 수정과 함께 읽습니다.

## 문제

F3는 고정한 plan과, 나중에 그 plan을 위해 읽는 근거 사이의 연결이 깨진 문제입니다. 지금 묶음 선언과 어댑터 재생은 더 새로운 스냅숏에 대해 서로 맞을 수 있는데, experiment._unanswerable_batches는 여전히 옛 plan을 씁니다. 추정기는 지금 묶음 파일을 planned['pinned_sha256']과 비교하지 않으므로, 고정한 실험이 서로 다른 원본 바이트에서 문서 묶음과 추정 검증 비용을 얻을 수 있습니다. [C1, C2, C3, C10]

발생: 반복, 4·5회차.

- [P1] [P1] golden_pipeline/experiment.py:301 — 답할 수 없음 비용 추정이 더 새로운 묶음에서 근거를 읽을 수 있습니다 / 묶음 선언과 어댑터 기록을 일관되게 바꾼 뒤 / 고정한 plan 해시를 한 번도 확인하지 않기 때문입니다

## 실패한 수정

- 3회차 지적은, 저장된 단위와 판정이 그 원본 바이트에서 나왔는지 확인하지 않고 바꿀 수 있는 근거 실행 해시를 복사하는 것을 설명했습니다. 그 뒤 어댑터 재생이 낡은 기록 경로를 막았지만, 처음에는 묶음 선언 확인을 빠뜨렸습니다. 이 시간 순서는 따로 살핀 과거 체크아웃이 아니라 받은 리뷰 기록과 1회차 조사에서 왔습니다. [C6]
- 4회차 정정은 재생 전에 pin(package)을 더하고, plan 받아들이기에서 근거 실행 고정값 전체를 선언이 확인된 묶음과 비교하게 했습니다. 그 보호는 지금 코드에 있으며 앞선 받아들이기 결함을 다룹니다. 지금 묶음이 일관된다는 것은 세우지만, 그것이 이미 고정한 plan이 고른 묶음이라는 것은 세우지 않습니다. [C1, C2, C6]
- 1회차 조사는 document_units를 없음 추정까지 따라갔지만, 묶음 선언이 낡은 채 맞춰 바꾼 어댑터를 시험하자고 제안했습니다. 그 경우는 pin 안에서 실패하므로, 일관되게 바꾼 묶음과 옛 plan 사이의 빠진 관계를 한 번도 시험하지 않습니다. 그래서 보고된 통과 확인은 더 넓은 고정 plan 규칙을 세우지 못했습니다. [C5, C6]
- 두 추정 회귀 테스트 분기는 모두 evidence_run과 bundles만 담은 부분 사전을 만듭니다. 테스트 준비물이 만든 실제 plan의 pinned_sha256을 넘기지 않습니다. 한 경우는 어댑터 기록을 낡은 채 두고, 다른 경우는 묶음 선언을 낡은 채 둡니다. 어느 쪽도 선언과 어댑터 기록을 일관되게 바꾸면서 옛 plan을 유지하지 않습니다. [C5]

## 출처

### S1 — plan 받아들이기, 고정 해시, 문서 읽기

- URL: golden_pipeline/plan.py
- 확인일: 2026-10-20
- 위치: make_plan 31–60행; document_units 98–110행; _verified_evidence_pins와 _check_package 160–173행
- 인용: make_plan: "pinned = _verified_evidence_pins(run_dir, package)"; "\"pinned_sha256\": pinned". _verified_evidence_pins: "pinned = evidence.pin(package)\n    recorded = storage._read_json(run_dir / \"manifest.json\")[\"pinned_sha256\"]\n    if recorded != pinned:". document_units: "def document_units(run_dir, docs):"; "units, _ = evidence.read_verified(run_dir, evidence.PACKAGE)". _check_package: "for name, sha in pinned.items():\n        if storage._sha256(package / name) != sha:\n            raise evidence.PackageMismatch(f\"{name} SHA-256 이 근거 어댑터 run 에 고정된 값과 다릅니다\")".
- 적용: plan 받아들이기는 확인된 해시를 고정하지만, 지금 문서 읽기는 기대하는 plan 정체를 받지 않는다는 것을 보여 줍니다.
- 반대 근거: plan 받아들이기는 이미 근거 고정값 전체를 비교하고, _check_package는 이미 필요한 파일별 비교를 구현합니다.
- 검증: 옛 실제 plan은 일관되게 바꾼 원본 파일을 거부해야 하고, 새로 받아들인 plan은 받아들여야 합니다.

### S2 — 지금 묶음 선언 확인과 어댑터 재생

- URL: golden_pipeline/evidence.py
- 확인일: 2026-10-20
- 위치: PINNED 20행; read_verified 68–75행; pin 78–85행
- 인용: "PINNED = (\"manifest.json\", CHUNKS, DOCS, AGENCIES)". read_verified: "pin(package)\n    units, judgments, _ = _adapt(package)\n    for name, expected in ((\"units.jsonl\", units), (\"judgments.jsonl\", judgments)):\n        if list(_iter_jsonl(run_dir / name)) != expected:"; "return units, judgments". pin: "hashes = {name: storage._sha256(package / name) for name in PINNED}\n    declared = storage._read_json(package / \"manifest.json\")[\"files\"]\n    for name in PINNED[1:]:\n        if declared[name][\"sha256\"] != hashes[name]:"; "return hashes".
- 적용: 두 확인 모두 지금 묶음을 검증할 뿐, 고정한 plan을 받거나 그 해시와 비교하지 않습니다.
- 반대 근거: 이 확인들은 낡은 선언, 빠지거나 바뀐 기록, 순서가 바뀐 기록, 맞지 않는 판정을 올바르게 거부합니다.
- 검증: plan 기반 거부를 기대하기 전에, 일관되게 바꾼 것이 이 확인들을 따로 통과한다는 것을 보입니다.

### S3 — 추정은 plan 해시 막이 없이 지금 문서 단위를 읽음

- URL: golden_pipeline/experiment.py
- 확인일: 2026-10-20
- 위치: estimate 243–271행; _unanswerable_batches 297–302행
- 인용: "planned, _ = plan.load_plan(experiment_id)\n    batches = _unanswerable_batches(planned)". "if topic == \"unanswerable\":\n            per_output[\"high\"] = max(per_output[\"high\"], sum(batches) / len(batches))". _unanswerable_batches: "bundles = [bundle for bundle in planned[\"bundles\"] if bundle[\"topic\"] == \"unanswerable\"]\n    run_dir = storage.OUTPUTS / \"evidence\" / planned[\"evidence_run\"]\n    found = plan.document_units(run_dir, {bundle[\"doc_sha\"] for bundle in bundles})\n    return [len(validation.document_batches(found[bundle[\"doc_sha\"]])) for bundle in bundles]".
- 적용: 전체 plan이 바꿀 수 있는 경로와 ID로 줄어드는 정확한 지점과, 묶음 수에서 높은 비용 추정으로 가는 조건부 경로를 짚습니다.
- 반대 근거: 과거 검증 호출 비율이 max를 차지할 수 있으므로, 묶음이 바뀌어도 최종 비용이 바뀌지 않을 수 있습니다.
- 검증: 바뀌지 않은 옛 plan으로 도우미 함수와 공개 estimate를 모두 시험하고, 묶음 경계를 바꾸는 교체는 해시 거부와 따로 보입니다.

### S4 — 기존의 plan 기반 검증과 글에 달린 묶음 나누기

- URL: golden_pipeline/validation.py
- 확인일: 2026-10-20
- 위치: _documents 201–212행; _pinned_roles와 _planned_package 680–698행; document_batches 800–822행; DOCUMENT_BATCH_CHARS 47행
- 인용: _documents: "if topic not in DOCUMENT_TOPICS:\n        return {}"; "_planned_package(planned, evidence.PINNED[1:])" precedes "found = plan.document_units(run_dir, set(asked.values()))". _planned_package: "if \"pinned_sha256\" not in planned:"; "pinned = {name: planned[\"pinned_sha256\"][name] for name in files}\n    plan._check_package(evidence.PACKAGE, pinned)\n    return pinned". _pinned_roles: "# Rename may update agency names; only the source chunks affect role judgments."; "pinned = _planned_package(planned, [evidence.CHUNKS])". Batching: "DOCUMENT_BATCH_CHARS = 60_000"; "if fresh and size + len(unit[\"text\"]) > DOCUMENT_BATCH_CHARS:".
- 적용: 추정이 다시 쓸 수 있는 기존 막이를 주고, 본문 길이와 단위 묶기가 추정 호출 수에 영향을 주는 이유를 보여 줍니다.
- 반대 근거: 문서 전체 경로는 이미 이 보호가 있고, 역할만 쓰는 곳은 일부러 더 작은 파일 집합을 확인합니다.
- 검증: 추정은 문서 전체 검증과 같은 파일별 정책으로 교체 스냅숏을 거부해야 하고, 역할만 쓰는 이름 갱신은 계속 올바라야 합니다.

### S5 — 추정 회귀 조합에 실제 옛 plan이 빠짐

- URL: tests/golden/test_comparison_fields.py
- 확인일: 2026-10-20
- 위치: field_run 58–70행; 낡은 어댑터 테스트 259–291행; 맞춘 교체 테스트 294–336행; 이름 갱신 테스트 86–125행
- 인용: "plan.make_plan(\"p-fields\", \"ev-roles\", {\"comparison\": 1}, 2000, package=evidence_run)". Both estimation branches use: "\"estimate\": lambda: experiment._unanswerable_batches({\"evidence_run\": \"ev-roles\", \"bundles\": [\n            {\"topic\": \"unanswerable\", \"doc_sha\": DOC_1}]}),". First case: "manifest[\"pinned_sha256\"] = evidence.pin(evidence_run)" and "with pytest.raises(evidence.PackageMismatch, match=\"units.jsonl\"):". Second case: "assert (evidence_run / \"manifest.json\").read_bytes() == package_manifest" and "with pytest.raises(evidence.PackageMismatch, match=r\"corpus/chunks.jsonl SHA-256.*manifest.json\"):".
- 적용: 테스트 준비물은 고정값이 있는 plan을 만들지만, 추정 테스트는 이를 넘기지 않습니다. 그 실패는 과거 스냅숏 정체가 아니라 재생이나 선언 거부를 보여 줍니다.
- 반대 근거: 이 테스트들은 서로 다른 올바른 실패 방식을 다루며, 앞선 plan 해시 막이를 도입한 뒤에도 직접 읽기를 통해 그 범위를 유지해야 합니다.
- 검증: 선언과 저장된 어댑터 기록이 모두 교체 묶음과 맞는 상태에서, 완전한 실제 옛 plan을 추정에 넘깁니다.

### S6 — 문서로 정한 원본 권한과 manifest 갱신 한계

- URL: golden_pipeline/README.md
- 확인일: 2026-10-20
- 위치: 440–490행
- 인용: "The pipeline checks this contract but does not certify the source owner's semantic annotations." "Updating `data/data_list.csv` and its package-manifest declaration therefore allows rename to use current organization names while keeping source chunks fixed." "Whole-document validation uses the same per-file anchor for the chunks, document list and agency CSV it already required to remain fixed." "The whole-package manifest hash remains in the plan as provenance, but role checks do not require the current manifest to match it."
- 적용: 수정을 기존 파일별 정책으로 제한하고, 바이트 정체와 주석의 뜻이 맞는지를 구별합니다.
- 반대 근거: 문서는 의도한 동작을 말하며, 구현 동작을 세우려면 소스와 회귀 대조군이 필요합니다.
- 검증: 기존 이름 갱신 테스트를 유지하고, 옛 plan에 대해 바뀐 원본 청크를 거부합니다.

### S7 — 1회차 가설, 실험, 보고된 결과

- URL: docs/research/review-littlebitai-golden-comparison-fields-f3-1.md
- 확인일: 2026-10-20
- 위치: 실패한 수정; 가설; 실험; 결과; 한계(번역 전 원문 기준 15–17, 112, 131, 135–143, 147행)
- 인용: "받아들이려면 실제로 서로 독립인 관계 셋이 필요합니다. 묶음 manifest 선언이 지금 파일 해시와 같아야 하고, 근거 실행 고정값이 그 확인된 묶음 해시 집합과 같아야 하며, 저장된 단위와 판정이 그 묶음의 변환 결과와 같아야 합니다." "근거 실행의 CHUNKS 해시만 고치고, 묶음 manifest 바이트와 선언한 청크 해시는 그대로 둡니다." "공용 읽기를 부르는 코드는 `eligible_units`와 `document_units` 둘이며, 뒤의 것은 문서 전체 검증과 없음 추정이라는 두 사용처에 더 닿습니다." "처음 조사는 과거 체크아웃을 살피지 않았으므로, 받은 보고를 넘는 과거 귀속은 확인하지 않았습니다."
- 적용: 1회차가 추정 호출자를 따라갔는데도, 받아들이기에 초점을 둔 가설과 실험이 뒤의 사용처-plan 관계를 세우지 못한 이유를 보여 줍니다.
- 반대 근거: 그 문서는 과거 귀속을 분명히 제한하고, 의미 있는 선언/재생 확인을 보고합니다. 그 확인은 앞선 결함을 다룹니다.
- 검증: 실제 옛 plan을 유지한 채, 일관된 교체 묶음과 맞는 어댑터 출력으로 실험을 넓힙니다.

### S8 — The Update Framework Specification 1.0.37

- URL: https://theupdateframework.github.io/specification/latest/
- 확인일: 2026-10-20
- 위치: 5.6절 2단계, 890–891행; 3단계의 서명 요구. 실제 웹 검색으로 찾아 열어 봄.
- 인용: "The hashes of the new targets metadata file MUST match the hashes, if any, listed in the trusted snapshot metadata."
- 적용: 후보를 따로 믿는 부모와 대조하라는 근거가 됩니다. 그 관계를 plan에 고정된 로컬 파일에 적용하는 것은 해석입니다.
- 반대 근거: 해시 조건은 해시가 있을 때로 분명히 한정됩니다. TUF는 서명도 확인하고 업데이트 전환을 지원합니다. 이 저장소에는 그런 인증된 메타데이터 사슬이 없고, 고정한 plan은 일부러 옛 스냅숏을 고릅니다.
- 검증: 옛 plan을 기대하는 부모로 두고, 필요한 파일 해시가 그것과 다른 일관된 지금 묶음을 거부합니다.

## 주장

- C1 (출처; S1): 지금 plan 받아들이기는 선언이 확인된 묶음 해시를 얻고, 근거 실행 고정값 전체를 비교하며, 그 확인된 집합을 plan에 저장합니다.
- C2 (출처; S2): read_verified는 지금 묶음 선언과 어댑터 재생 전체를 확인하지만, 기대하는 plan 해시는 받지 않습니다.
- C3 (해석; S1, S2, S3): 호출자가 읽기 전에 plan 정체를 버리므로, 일관되게 바꾼 묶음과 어댑터는 원본 해시가 바뀌지 않은 옛 plan과 달라도 추정이 닿는 확인을 통과할 수 있습니다.
- C4 (출처; S4): 문서 전체 검증은 이미 document_units 전에 필요한 파일을 고정한 plan과 확인합니다. 비교 역할 확인은 생성 plan 출처를 확인한 뒤 일부러 원본 청크만 확인합니다.
- C5 (해석; S5): 기존 추정 회귀 분기는 plan 고정값을 빼고, 낡은 어댑터나 낡은 선언 거부를 따로 일으킵니다. 옛 plan에 대한 일관된 교체 거부는 세우지 않습니다.
- C6 (해석; S7, S1, S2, S5): 1회차와 받은 리뷰 시간 순서는 재생과 선언 확인에 대한 잇단 수정을 설명하지만, 1회차 실험은 과거 plan 기준을 시험하지 않았습니다. 과거 결과는 보고된 근거이지, 이번 세션에서 돌린 확인이 아닙니다.
- C7 (출처; S8): TUF는 새 targets 메타데이터 해시가 있으면 믿는 snapshot 메타데이터와 맞기를 요구하며, 이 규칙은 서명도 확인하는 절차의 일부입니다.
- C8 (해석; S1, S2, S3, S4, S5, S7, S8): 남은 수정은 지금 묶음을 읽기 전에 호출자가 고른 plan 기준을 유지하는 것입니다. 문서 전체 검증의 기존 파일별 막이를 없음 추정에 다시 쓰면, 선언과 재생 확인을 유지하면서 보고된 순차 교체 경로를 막습니다.
- C9 (출처; S6, S4, S5): 저장소는 원본 청크가 그대로인 한 비교 이름 바꾸기를 위한 기관 이름과 manifest 갱신을 허용하고, manifest 전체 해시를 역할 확인의 출처 기록으로 다루며, 원본 주인의 주석 뜻을 보증하지 않습니다.
- C10 (해석; S3, S4): 교체 글은 문서 묶음 나누기와 높은 검증 호출 추정을 바꿀 수 있지만, 수치에 영향을 주려면 묶음 경계를 넘고 max가 쓰는 과거 검증 호출 비율을 넘어야 합니다.

## 핵심 원리

TUF는 참조된 메타데이터를 이미 믿는 부모가 준 해시와 대조하며, 해시 확인은 해시가 있을 때 적용된다고 분명히 한정합니다. 그 절차는 서명 확인도 요구합니다. 여기서 쓰는 원리는, 후보 산출물 집합 안에서 서로 맞는다고 해서 따로 고른 부모와의 관계 확인을 대신할 수 없다는 것입니다. 이 원리를 고정한 plan에 적용하는 것은 해석입니다. 이 저장소에 필요한 것은 TUF의 소프트웨어 업데이트 정책이나 서명 기반이 아니라, 고른 과거 스냅숏과 같은지입니다. [C7, C8]

## 적용

_unanswerable_batches가 plan.document_units를 부르기 전에, validation._documents가 이미 쓰는 plan 기반 파일별 확인 validation._planned_package(planned, evidence.PINNED[1:])를 적용합니다. 그다음 document_units의 선언 확인과 어댑터 재생 전체를 유지합니다. experiment 모듈은 이미 validation을 가져오며, 같은 파일 집합을 쓰려면 evidence.PINNED가 필요합니다. 기존 장치를 쓰는 작은 수정입니다. document_units는 지금 묶음 읽기용으로 남겨 두고, 기존 두 인자를 고정 plan의 증거로 소리 없이 다루지 않습니다. 코드에서 부르는 곳 둘을 모두 찾았습니다. validation._documents는 이미 plan 해시를 확인하고, experiment._unanswerable_batches에는 확인이 필요합니다. 파일별 기준과 과거 manifest 전체 해시의 의도한 구별은 유지하며, 비교 이름 바꾸기 경로의 기관 이름 갱신도 포함합니다. 추정 회귀 테스트 데이터가 실제 plan 고정값을 담고 앞선 해시 실패를 고려하도록 고치고, 선언과 재생 실패를 따로 시험하는 직접 읽기 테스트는 유지합니다. [C1, C2, C3, C4, C5, C8, C9]

## 가설

남은 원인은 호출자가 기대하는 스냅숏 정체를 버리는 확인 경계입니다. _unanswerable_batches는 전체 planned 객체를 받지만, document_units에는 바꿀 수 있는 근거 실행 경로와 문서 ID만 넘깁니다. 그 읽기는 옛 plan 해시를 받지 못한 채 지금 묶음의 일관성만 확인합니다. 문서 전체 검증은 _planned_package로 이 빠진 확인을 따로 하지만, 추정은 하지 않습니다. 앞선 수정은 지금 묶음 확인을 강화했지만, 사용처와 plan의 관계를 완성하지 않았습니다. [C3, C4, C5, C8]

## 반대 근거

- 지금 make_plan은 이미 불완전하거나 맞지 않는 근거 고정값 집합을 거부하고, read_verified는 이미 낡은 선언과 기록 전체 불일치를 거부합니다. 앞선 수정은 그 관계에 대해서는 효과가 있으며, 남은 결함은 올바른 plan이 생긴 뒤의 사용에 관한 것입니다. [C1, C2]
- 문서 전체 검증은 document_units 전에 plan의 청크, 문서 목록, 기관 CSV를 확인합니다. 비교 역할 확인은 생성 plan SHA와 plan에 고정된 청크를 따로 확인합니다. 그래서 살펴본 경로로는 모든 뒤쪽 사용처에 plan 기준이 없다고 말할 수 없습니다. [C4]
- 길이가 같은 본문 교체는 묶음 수를 바꾸지 않을 수 있습니다. 다른 스냅숏을 받아들이는 것 자체가 출처 실패를 보여 주지만, 비용 영향을 보이려면 묶음 나누기를 바꾸고 그 차이를 가리는 과거 호출 비율 최대값을 피해야 합니다. [C10]
- 과거 묶음 manifest 전체를 모든 곳에서 요구하면, 문서로 정하고 시험한 기관 이름 갱신 동작과 어긋납니다. 제안하는 수정은 사용처별 파일 확인을 유지해야 합니다. [C9]

## 다른 방법

- 지금 묶음 해시를 지금 근거 실행 manifest와만 비교하기. 맞춘 교체는 그 manifest도 바꿀 수 있으므로, 기대하는 정체는 고정한 plan에서 와야 합니다. [C1, C3, C8]
- 선언이나 재생 확인을 하나 더 더하기. 일관된 교체 묶음은 둘 다 이미 통과하므로, 되풀이해도 옛 plan과 같은지는 세울 수 없습니다. [C2, C3]
- make_plan이나 experiment.freeze에서만 확인하기. 나중의 묶음 교체는 그 확인 뒤에 일어납니다. 추정은 바꿀 수 있는 원본 파일을 읽기 전에 자기 확인이 필요합니다. [C1, C3, C8]
- 과거 package_manifest_sha256을 모든 곳에서 확인하기. 기존 약속은 원본 청크가 그대로인 한 기관 이름 갱신을 위한 manifest 변경을 일부러 허용합니다. 대신 정해진 파일별 정책을 다시 씁니다. [C4, C9]
- document_units가 plan을 요구하게 바꾸고 두 호출자를 plan에 묶인 공용 읽기 하나로 옮기기. 규칙을 빠뜨리기 어렵게 만들 수 있지만, 빠진 유일한 호출자에 기존 막이를 더하는 것보다 넓은 인터페이스 변경입니다. 이 방법을 고르면 plan 고정값을 선택 사항이 아니라 필수로 하고, 지금 묶음 확인 테스트는 따로 유지합니다. [C3, C4, C5, C8]
- 서명된 manifest, 바꿀 수 없는 근거 저장소, 보관한 묶음 스냅숏 더하기. 더 강한 교체와 가용성 문제를 다룰 수 있지만, 보고된 순차 변경은 이미 plan에 저장된 고정 해시로 찾을 수 있습니다. [C1, C7, C8]

## 실험

제안한 확인일 뿐이며, 이번 조사 세션에서는 아무것도 돌리지 않았습니다. 따로 만든 합성 테스트 데이터를 쓰고 API는 쓰지 않습니다. 먼저 선언이 올바른 묶음, 실제 근거 실행, make_plan으로 만든 실제 답할 수 없음 plan을 만들고, 완전한 옛 plan과 그 파일 바이트를 남깁니다. 없음 검증은 고른 묶음 근거만이 아니라 모든 단위를 읽으므로, 대상 문서에 단위를 둘 이상, 가능하면 보류 단위도 넣습니다. 기준 묶음 수를 기록합니다. 단위 수는 같게 두고 대상 문서 글을 바꿔 document_batches 크기 경계를 넘게 하되, 올바른 원본 연결과 역할 주석은 유지합니다. 묶음 선언을 일관되게 고치고, 저장된 어댑터 파일 둘을 새 _adapt 출력으로 정확히 바꾸며, 강한 대조군으로 근거 실행 고정값도 고칩니다. evidence.pin과 evidence.read_verified가 교체를 받아들이고, 그 CHUNKS 해시가 바뀌지 않은 옛 plan과 다르다는 것을 보입니다. 지금 코드에서는 _unanswerable_batches(old_plan)가 교체에서 나온 수를 돌려줄 것으로 코드를 읽어 예측합니다. 수정 뒤에는 문서 묶음 나누기나 과거 기록 읽기 전에, 바뀐 고정 파일을 짚는 PackageMismatch를 내야 하고 출력 스냅숏은 그대로여야 합니다. 저장된 옛 plan으로 공개 estimate도 돌립니다. 표시용 _history를 쓰면 실제 사용량을 지어내지 않고도 과거 계산 전에 거부된다는 것을 보일 수 있습니다. 긍정 대조군: 바뀌지 않은 plan/묶음은 여전히 기준 수를 내고, 새 근거 실행과 새 plan은 일관된 교체를 받아들여 새 수를 냅니다. 공개 비용 비교에는, estimate의 max가 묶음 변화를 가리지 않도록 검증 호출 비율이 충분히 낮은, 합성임이 분명한 과거 기록을 줍니다. 낡은 선언과 낡은 어댑터 기록에 대한 별도의 직접 읽기 테스트를 유지하고, 빠진 plan 고정값은 기존 거부 동작으로 시험하며, 기관 이름 갱신 대조군을 유지합니다. [C1, C2, C3, C4, C5, C8, C9, C10]

## 결과

기준 `d75399a`에 대해 관측했으며, 이 문서를 담은 수정 커밋의 이름은 `golden: pin absence cost estimates to the frozen plan`입니다. 조사 초안 속 합성 실험 관측이며, 따로 검증된 규칙이 아닙니다.

`test_estimation_rejects_coherent_replacement_of_a_frozen_plans_source`는 실제 근거 실행과 답할 수 없음 plan을 만든 뒤 옛 plan 바이트를 남깁니다. 대상 문서에는 보류 근거를 포함해 단위가 네 개 있습니다. 교체는 기록 수를 유지하고, 묶음 선언과 근거 고정값을 일관되게 고치며, 어댑터 파일 둘을 정확한 새 변환으로 바꿉니다. `evidence.pin`과 `evidence.read_verified`는 모두 교체를 받아들이며, 그 청크 해시는 옛 plan과 다릅니다. 수정 전에는 도우미 함수와 공개 estimate가 모두 이를 받아들였습니다. 묶음은 1개에서 4개로, 높은 검증 호출은 40에서 160으로, 합성 답할 수 없음 높은 추정은 USD 0.0104에서 USD 0.0272로 바뀌었습니다. 낮은 합성 과거 비율 때문에 과거 최대값이 그 변화를 가리지 않습니다. `.venv\Scripts\python -m pytest -q tests/golden/test_experiment.py -k 'estimation_rejects_coherent or estimation_accepts_a_fresh' --tb=short --junitxml=artifacts/comparison-fields-review5-reproduction.xml`은 `2 failed, 1 passed, 24 deselected in 50.65s`로 끝났습니다. 옛 plan 경우 둘은 `PackageMismatch`를 내지 못했고, 새 plan 대조군은 통과했습니다.

정정은 `_unanswerable_batches`에서 문서를 읽기 전에 `validation._planned_package(planned, evidence.PINNED[1:])`를 부릅니다. 이제 옛 plan 경우는 묶음 나누기나 과거 기록 읽기 전에 바뀐 청크 파일 이름과 함께 거부되며, 출력 스냅숏과 plan 바이트는 그대로입니다. `test_estimation_accepts_a_fresh_plan_for_the_coherent_replacement`는 원본이 바뀌지 않은 기준 추정과, 교체에 대한 새 근거/plan 추정이 성공하는 것을 확인합니다. `test_estimation_requires_plan_pins_before_loading_history`는 두 진입점이 해시가 빠졌을 때 기존의 새 plan 안내를 유지하는지 확인합니다. `document_units`를 부르는 다른 코드는 `validation._documents` 하나이며, 이미 같은 파일별 막이를 적용합니다. 비교 역할 확인은 더 좁은 원본 청크 정책을 유지해 기관 이름 갱신을 지킵니다.

마지막 코드와 테스트 정리 뒤 `.venv\Scripts\python -m pytest -q tests/golden/test_experiment.py tests/golden/test_comparison_fields.py --tb=short -x --junitxml=artifacts/comparison-fields-review5-final.xml`은 `121 passed in 517.21s (0:08:37)`로 끝났습니다. 새 실제 plan 회귀 테스트와 대조군, 유지한 직접 읽기 선언/재생 경우, plan 뒤 변경 막이, 검증/공개/이름 바꾸기를 거치는 기관 이름 갱신이 들어 있습니다. 정리하면서, 고정값 없는 부분 사전을 쓰던 옛 `estimate` 매개변수 경우 네 개를 더 강한 실제 plan 도우미/공개 estimate 범위로 합쳤고, 직접 읽기 경우는 유지했습니다.

`.venv\Scripts\python -m pytest -q tests/golden/test_validation.py -k 'inconsistent_source_or_adapter or held_unit or absence_is_certified' --tb=short -x --junitxml=artifacts/comparison-fields-review5-document-controls.xml`은 `8 passed, 108 deselected in 470.22s (0:07:50)`로 끝났습니다. 두 프로세스 모두 마지막 보고가 느렸지만 정상 종료했고, 테스트 재시도나 프로세스 종료는 필요 없었습니다. `ruff check .`은 통과했습니다. 저장소 전체 검사는 서버가 돌리며 아직 기다리는 중입니다.

## 남은 한계

여전히 조사 초안이며, 처음의 소스 검토를 결과 절의 합성 관측이 보충합니다. 유료 호출은 하지 않았고 실제 데이터셋 기록은 보지 않았습니다. 수치는 합성 과거 기록과 줄인 테스트 묶음 한도를 나타내며, 실제 비용이나 성능이 아닙니다. 1회차가 인용한 과거 테스트 결과는, 위에서 명시적으로 유지해 돌린 대조군 말고는 그 문서의 보고된 관측으로 남습니다. 고정한 plan 해시를 기대하는 정체로 봅니다. plan 자체와 모든 외부 기준을 일관되게 바꾸는 것은 더 강한 위협 모델입니다. 로컬 선언은 묶음 주인을 인증하거나 뜻이 맞음을 세우지 않습니다. 해시와 파일을 따로 읽으므로 동시 쓰기 원자성도 이 조사 밖에 남습니다. [C6, C7, C8, C9, C10]
