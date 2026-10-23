# 리뷰 조사 · F3, 1회차

PR #76 리뷰 4회차의 수정 전에 2026-10-20에 쓴 조사 초안입니다. 검증된 사실이나 공용 규칙이 아니며, 리뷰는 이 문서를 수정과 함께 읽습니다.

## 문제

F3는 묶음 선언, 묶음 바이트, 어댑터 기록, plan에 고정된 해시 사이의 연결을 깹니다. 이들은 하나의 일관된 묶음을 나타내야 합니다. 지금 make_plan은 옛 청크를 선언한 그대로의 묶음 manifest를, 바뀐 청크와 그에 맞게 바꾼 어댑터 기록과 함께 받아들여, 그 일관되지 않은 조합을 고정할 수 있습니다. 뒤의 해시 확인은 받아들여진 불일치를 찾아내지 않고 그대로 유지합니다. [C1, C2, C3]

발생: 반복, 3·4회차.

- [P1] [P1] golden_pipeline/evidence.py:70 — adapter 재생이 패키지 매니페스트의 파일 선언을 검증하지 않아 승인되지 않은 역할 원문을 계획에 고정합니다

## 실패한 수정

- 받은 3회차 기준에서 make_plan은 지금 묶음 파일을, 바꿀 수 있는 근거 실행 manifest가 주는 해시와 비교했습니다. 저장된 단위와 판정이 그 파일에서 나왔는지는 확인하지 않았습니다. 그래서 manifest를 다시 쓰면 옛 어댑터 본문과 참조가 새 원본 해시와 함께 갈 수 있었습니다. 역할 이름이 그대로면 역할이 같은지 보는 것으로는 바뀐 본문 값이나 요구사항 연결을 찾을 수 없었습니다. PR 전체 diff로 보면 eligible_units는 전에는 저장된 단위와 판정을 바로 읽었습니다. [C1, C2]
- 4회차 기준에서 보이는 정정은 _adapt를 뽑아내고, 저장된 두 기록 순서 전체를 새 어댑터 출력과 비교하는 read_verified를 더했습니다. 낡은 기록 경로는 막습니다. 하지만 evidence.run은 _adapt 전에 pin을 부르는데, read_verified는 _adapt만 부릅니다. 뽑아낸 재생은 생성 쪽의 묶음 선언 전제를 빠뜨렸습니다. 이제 원본과 어댑터를 맞춰 고치면, 묶음 manifest가 여전히 옛 원본 해시를 선언하고 있어도 재생을 통과합니다. [C1, C4]
- 집중 테스트는 어댑터만 고친 경우와, 어댑터 기록은 낡은 채 원본을 고친 경우를 다뤘습니다. 뒤의 경우는 일부러 두 manifest를 모두 고쳤으므로, 선언 불일치가 아니라 재생 불일치를 시험했습니다. 기존 plan 뒤 변경 테스트는 올바른 plan이 이미 있는 상태에서 시작합니다. plan을 만들기 전에 원본과 어댑터는 맞지만 묶음 선언이 낡은 경우를 거부하는지 보여 주는 테스트는 없습니다. [C4, C5]

## 출처

### S1 — 근거 생성, 재생 읽기, 묶음 선언 확인

- URL: golden_pipeline/evidence.py
- 확인일: 2026-10-20
- 위치: run 34–52행; _adapt/read_verified/pin 56–84행; 역할 파싱 121–144행
- 인용: run executes `hashes = pin(package)` before `units, judgments, counts = _adapt(package)`. read_verified instead begins `units, judgments, _ = _adapt(package)` and compares the complete parsed units.jsonl and judgments.jsonl lists with those results. _adapt checks chunk/document counts against manifest counts. pin hashes PINNED and, for every name in PINNED[1:], rejects when `declared[name]["sha256"] != hashes[name]`. Role parsing checks shape, names in the body, duplicates and overlap; it does not verify the manifest's file declarations.
- 적용: 재생에서 빠진 생성 쪽의 정확한 전제와, 그것을 되살리는 기존 함수를 보여 줍니다.
- 반대 근거: 재생은 기록 전체의 불일치를 찾고, 처음 근거를 만들 때는 이미 선언을 확인합니다.
- 검증: 묶음 선언이 낡았으면, 맞춰 바꾼 어댑터 기록이라도 재생 결과를 내기 전에 실패해야 합니다.

### S2 — plan 받아들이기, 해시 복사, 공용 근거 읽기

- URL: golden_pipeline/plan.py
- 확인일: 2026-10-20
- 위치: make_plan 31–71행; eligible_units/document_units 87–111행; _check_package 161–165행; 이 함수들에 대한 PR 전체 diff
- 인용: make_plan reads `pinned_sha256` from the evidence-run manifest, calls `_check_package(package, pinned)`, then eligible_units. It stores `package_manifest_sha256` and the same `pinned_sha256` in the plan. _check_package compares each supplied hash with its current file; it does not read package file declarations. Both eligible_units and document_units call read_verified. The PR diff replaces direct reads of saved adapter records with those calls.
- 적용: 하나씩은 맞는 해시들이 어떻게 일관되다고 여겨지는 plan이 되는지 설명하고, 공용 읽기 수정이 보호하는 직접 사용처를 짚습니다.
- 반대 근거: 근거 고정값을 바꾸지 않고 묶음만 바꾸면 이미 _check_package에서 실패합니다.
- 검증: 단독 plan 파일 쓰기 전에 manifest와 청크가 섞인 스냅숏을 거부하고, 새로 만든 일관된 근거 실행은 받아들입니다.

### S3 — 뒤쪽 plan 기준과 원본 역할 확인

- URL: golden_pipeline/validation.py
- 확인일: 2026-10-20
- 위치: _documents 201–212행; _comparison_role_reason/_pinned_roles/_planned_package 662–698행
- 인용: _pinned_roles verifies the generation plan SHA, checks CHUNKS against the plan's per-file hash, then reads role_annotations using that hash. Its comment states: `Rename may update agency names; only the source chunks affect role judgments.` _comparison_role_reason compares cited plan roles with source roles. _documents checks the planned hashes for PINNED[1:] before reading document units.
- 적용: 뒤쪽 사용처는 plan이 받아들인 원본 정체를 유지하며, plan을 만들기 전에 받아들인 틀린 정체도 그대로 유지합니다.
- 반대 근거: 이 확인들은 뒤의 원본 변경과 plan 역할 덮어쓰기를 막습니다.
- 검증: 받아들이기를 고친 뒤에도 기존의 plan 뒤 변경 실패와 기관 이름 갱신 성공을 유지합니다.

### S4 — 어댑터와 비교 출처에 대한 집중 회귀 테스트

- URL: tests/golden/test_comparison_fields.py
- 확인일: 2026-10-20
- 위치: 86–125행, 153–190행, 227–243행, 259–291행
- 인용: The post-plan mutation test changes body, requirement_ids or roles and optionally repins the evidence and package manifests. The adapter-output test changes saved units or judgments alone. The stale-reader test changes body or requirement_ids, updates the package declaration and evidence pins using evidence.pin, but leaves adapter records stale; it expects a units.jsonl mismatch. Its plan branch also checks that a fresh evidence run succeeds. The name-refresh test updates the agency CSV and its package declaration while preserving chunk bytes.
- 적용: 빠진 plan 전 조합, 곧 바뀐 원본에 맞춘 어댑터 출력과 바뀌지 않은 묶음 선언을 보여 줍니다.
- 반대 근거: 테스트 모음은 이미 실제 변조 경로 여럿과 올바른 재생성을 다룹니다.
- 검증: 이 테스트들 옆에 맞춰 바꾼 경우를 더하고, 각자의 서로 다른 실패 기대는 유지합니다.

### S5 — 생성 쪽 선언과 기록 전체 확인 테스트

- URL: tests/golden/test_evidence.py
- 확인일: 2026-10-20
- 위치: 90–102행과 169–191행
- 인용: test_run_stops_when_files_differ_from_manifest_declaration changes the declared CHUNKS hash, expects evidence.run to raise PackageMismatch, and asserts no evidence-run directory exists. test_verified_reader_checks_complete_records_including_held_units mutates saved records through missing, duplicate, reversed or promoted cases and expects read_verified to reject.
- 적용: 선언 규칙은 생성에서는 이미 강제되고 시험되지만, 맞춰 바꾼 기록의 재생에서는 그렇지 않습니다.
- 반대 근거: 이 테스트들은 보고된 맞춘 편집 상황을 돌리지 않습니다.
- 검증: 다른 점은 맞는 기록으로, 재생 진입점에서도 같은 선언 거부를 요구합니다.

### S6 — 문서로 정한 원본 역할 권한과 manifest 갱신 약속

- URL: golden_pipeline/README.md
- 확인일: 2026-10-20
- 위치: 440–486행
- 인용: `Requirement comparisons use explicit roles authored by the trusted source-package owner.` The contract states that the pipeline does not certify the owner's semantic annotations. It describes adapter replay before copying per-file hashes into the plan, permits agency CSV and package-declaration updates while source chunks remain fixed, and says the whole-package manifest hash remains provenance rather than a required current-manifest match for role checks. Using annotations from an old package requires a new owner-prepared package and new evidence, plan and generation runs.
- 적용: 권한 경계를 정하고, 의도한 뒤쪽 이름 갱신을 유지하도록 수정을 제한합니다.
- 반대 근거: 문서의 연결은 지금 구현이 세우는 것보다 강합니다. 문서는 의도이지 증명이 아닙니다.
- 검증: 낡은 선언은 받아들이기를 막고, 일관된 새 묶음과 허용된 이름 갱신은 계속 돼야 합니다.

### S7 — The Update Framework Specification — 확인된 메타데이터 사슬

- URL: https://theupdateframework.github.io/specification/latest/
- 확인일: 2026-10-20
- 위치: 5.6절 2단계와 5.7절 1–3단계; 웹 검색으로 찾아 열어 봄
- 인용: "The hashes of the new targets metadata file MUST match the hashes, if any, listed in the trusted snapshot metadata."
- 적용: 여러 부분으로 된 스냅숏을 받아들이기 전에 선언과 파일의 관계를 확인하라는 근거가 됩니다.
- 반대 근거: TUF는 인증된 메타데이터를 씁니다. 이 저장소의 로컬 manifest에는 그런 서명 확인이 없습니다. 이 출처는 여기서 묶음 주인의 정체를 세우지 않습니다.
- 검증: 파생 기록이 맞더라도 그 원본 바이트가 선언한 묶음 manifest와 다르면 거부합니다.

## 주장

- C1 (출처; S1): 생성 쪽은 변환 전에 pin으로 묶음 선언을 확인하지만, read_verified는 그 선언 확인 없이 변환과 기록 전체 비교를 합니다.
- C2 (해석; S2): make_plan은 지금 파일을 근거가 준 해시와 확인하고 그 해시를 plan에 복사하므로, 이 확인만으로는 묶음 선언과 맞는다는 것이 서지 않습니다.
- C3 (해석; S2, S3): plan 기반 뒤쪽 확인은 받아들인 스냅숏을 유지하지만, plan을 만들 때 받아들인 일관되지 않은 스냅숏을 고치지는 못합니다.
- C4 (해석; S1, S4): 재생은 낡은 어댑터 기록을 고치지만, 선언을 확인하지 않으면 원본과 어댑터를 맞춰 바꾼 것은 받아들입니다.
- C5 (해석; S4, S5): 살펴본 테스트는 원본/어댑터의 따로 된 불일치와 plan 뒤 변경을 다루지만, 묶음 선언이 낡은 채 plan 전에 맞춰 바꾼 경우는 빠뜨립니다.
- C6 (해석; S1, S2, S3, S5, S6): 맞는 수정은 plan 받아들이기 전에 선언 확인, 근거 고정값 일치, 전체 재생을 함께 하고, 선언 확인을 직접 근거 읽기와 함께 쓰는 것입니다.
- C7 (해석; S7): TUF는 앞서 믿은 부모를 거쳐 메타데이터를 확인하고, 대상 해시를 그것을 선언한 메타데이터와 대조합니다. 확인되지 않은 문맥의 해시가 맞는 것만으로는 부족합니다.
- C8 (해석; S1, S3, S4, S6): 의도한 약속은 주인이 쓴 역할의 뜻을 믿고, 고정 원본 청크를 바꾸지 않는 기관 이름 갱신을 허용합니다. 선언이 일관된다고 주석이 맞거나 과거 작성자가 증명되지는 않습니다.

## 핵심 원리

TUF는 메타데이터 일관성과 파일 확인을 나눕니다. 확인은 이미 확인된 부모를 따라가고, 대상 바이트는 그것을 선언한 메타데이터와 맞아야 합니다. 메타데이터 해시 요구는 해시가 있을 때의 조건입니다. 여기에 적용하면, 파생 기록끼리 맞는다는 것으로 그 입력을 허가하는 묶음 선언 확인을 대신할 수 없습니다. 일관성에 대한 비유이며, TUF를 구현하자는 제안이 아닙니다. [C7, C6]

## 적용

빠진 선언 확인은 evidence.read_verified 안 _adapt 앞에 둡니다. 그러면 eligible_units와 document_units가 evidence.run과 같은 묶음 유효성 전제를 받습니다. make_plan 받아들이기에서는 evidence.pin(package)으로 해시를 얻어, 전체 PINNED 집합을 근거 실행 고정값과 비교하고, 재생 확인은 유지하며, 확인된 집합을 plan에 저장합니다. 뒤쪽 확인은 생성 plan을 기준으로 둡니다. 문서로 정한 기관 이름 갱신은 원본 청크를 바꾸지 않고 지금 묶음 manifest를 바꿀 수 있으므로, 뒤의 모든 역할 확인에서 옛 manifest 전체 해시를 요구하면 의도한 동작을 거꾸로 만듭니다. [C1, C2, C3, C6, C8]

## 가설

근본 원인은 확인 경계가 불완전하다는 것입니다. 재생이 같다는 것을 묶음이 올바르다는 충분한 근거로 봤습니다. 받아들이려면 실제로 서로 독립인 관계 셋이 필요합니다. 묶음 manifest 선언이 지금 파일 해시와 같아야 하고, 근거 실행 고정값이 그 확인된 묶음 해시 집합과 같아야 하며, 저장된 단위와 판정이 그 묶음의 변환 결과와 같아야 합니다. 원래 경로에는 세 번째 관계가 없었고, 재생 정정에는 여전히 첫 번째가 없습니다. 공용 확인 읽기에서 재생 전에 pin을 다시 쓰고, 기록 전체 비교를 유지하며, make_plan이 근거 실행 고정값과 맞은 뒤에만 확인된 전체 해시 집합을 고정하게 합니다. [C1, C2, C6]

## 반대 근거

- 재생은 이미 기록 전체, 순서, 보류 단위, 자격, 이유를 확인합니다. 낡거나 따로 고친 어댑터 출력에 대한 의미 있는 보호입니다. 가설은 기록 비교 자체의 부족이 아니라 빠진 전제에 관한 것입니다. [C1, C4]
- 처음 근거를 만들 때는 이미 묶음 선언과 다른 파일을 거부합니다. 일관되지 않은 상태가 되려면 근거를 만든 뒤, 다음 읽기나 plan 전에 고쳐야 합니다. [C1, C5]
- 뒤쪽 plan과 청크 해시 확인은 올바른 plan을 고정한 뒤의 원본 변경을 올바르게 거부합니다. 올바른 스냅숏과 plan을 만들 때 받아들인 일관되지 않은 스냅숏은 구별하지 못합니다. [C3, C5]
- 저장소는 원본 주인의 역할 주석을 분명히 믿고, 그 뜻이 맞다고 보증하지 않습니다. 선언이 일관된 묶음에도 틀린 역할이 있을 수 있으며, 이 수정은 받은 묶음 약속 이상의 뜻 권한을 세우지 못합니다. [C8]

## 다른 방법

- 바꿀 수 있는 근거 manifest에 units.jsonl과 judgments.jsonl 해시만 더하기. 맞춰 바꾸는 쪽이 그 해시도 바꿀 수 있고, 묶음 선언은 여전히 확인되지 않습니다. 대신 재생을 유지합니다. [C1, C6]
- 원본 역할이 같은지나 기록 수만 확인하기. 맞춰 바꾼 역할과 바뀌지 않은 수는 묶음 파일 선언이 틀린 채로 두 확인을 모두 통과합니다. [C1, C3]
- pin을 make_plan에만 두기. 보고된 plan 진입점은 막지만, 직접 eligible_units와 document_units 읽기에는 생성 쪽 선언 확인이 없습니다. 공용 읽기가 더 강한 기존 경계입니다. [C1, C2]
- 모든 검증, 공개, 이름 바꾸기 역할 확인에서 과거 묶음 manifest 해시를 요구하기. 문서로 정한 기관 이름 갱신을 방해합니다. plan을 받아들일 때 선언 일관성을 세우고, 그 뒤에는 기존 파일별 기준을 유지합니다. [C3, C8]
- 서명된 manifest, 바꿀 수 없는 저장소, 인증된 과거 실행 정체 도입하기. 로컬 산출물을 모두 일관되게 바꾸는 더 강한 위협 모델을 다룹니다. 보고된 낡은 선언 경우는 먼저 기존 pin과 재생 장치로 다룰 수 있습니다. [C6, C7]

## 실험

API 호출 없이 합성 테스트 데이터만 씁니다. 올바른 묶음과 근거 실행을 만든 뒤, 기록 수는 바꾸지 않고 청크 본문이나 올바른 역할 배정을 바꿉니다. 저장된 어댑터 파일 둘을 바뀐 청크에서 나온 정확한 기록으로 바꿉니다. 근거 실행의 CHUNKS 해시만 고치고, 묶음 manifest 바이트와 선언한 청크 해시는 그대로 둡니다. 재생 불일치로 거부를 설명할 수 없도록, 어댑터 기록이 바뀐 원본과 정말 맞는지 확인합니다. 지금 코드에서는 make_plan이 이 혼합을 받아들일 것으로 코드를 읽어 예측합니다. 수정 뒤에는 plan을 쓰기 전에 묶음 청크 선언을 짚는 PackageMismatch를 내야 합니다. 같은 테스트 데이터를 read_verified, eligible_units, document_units, 없음 추정 경로로도 돌려, 출력 스냅숏이 바뀌지 않는지 확인합니다. 기존의 어댑터만 고친 경우와 낡은 어댑터 경우의 실패는 유지합니다. 긍정 대조군으로, 바뀌지 않은 묶음은 계속 읽을 수 있어야 하고, 일관되게 고친 묶음과 새 근거 실행은 새 본문, 참조, 역할을 담은 plan을 만들어야 합니다. plan 뒤 원본 변경과 기관 이름 갱신에 대한 기존 검증/공개/이름 바꾸기 테스트는 유지합니다. 제안한 확인이며 실행하지 않았습니다. [C4, C5, C6, C8]

## 결과

기준 `5f7625b`에 대해 관측했으며, 이 문서를 담은 수정 커밋의 이름은 `golden: verify declarations before replay and plan admission`입니다. 여전히 조사 초안이며, 따로 검증된 규칙이 아닙니다.

`test_matching_adapter_replacements_cannot_bypass_package_declarations`는 본문 값이나 올바른 역할을 바꾸고, 어댑터 파일 둘을 정확한 `_adapt` 출력으로 바꾸며, 근거 실행 청크 해시만 고치고, 묶음 선언 바이트가 그대로라는 것을 보입니다. 코드 수정 전에는 조합 열 가지(원본 변경 두 가지 × 직접 재생, plan 만들기, 자격 단위 읽기, 문서 단위 읽기, 없음 추정)가 모두 `PackageMismatch`를 내지 못했습니다. `test_plan_requires_the_complete_verified_evidence_pin_set`도 선언된 파일 고정값 세 개를 하나씩 뺐을 때 받아들이는 것을 재현했습니다. 명령 `.venv\Scripts\python -m pytest -q tests/golden/test_comparison_fields.py -k 'matching_adapter_replacements or complete_verified_evidence_pin_set' --tb=short --junitxml=artifacts/comparison-fields-review4-reproduction.xml`은 `13 failed, 85 deselected in 46.10s`로 끝났습니다.

재생 전에 `pin`을 더하고 plan 받아들이기에서 확인된 전체 해시 집합을 비교한 뒤, 같은 선택자에 `-x --junitxml=artifacts/comparison-fields-review4-experiment-final.xml`을 붙이면 `13 passed, 85 deselected in 30.89s`로 끝났습니다. 선언 불일치는 이제 출력 쓰기 전에 `corpus/chunks.jsonl`과 `manifest.json`을 짚습니다. plan 경우는 묶음 선언도 일관되게 고치고, 새 근거 실행을 만들며, 새 plan이 확인된 해시, 지금 본문, 요구사항 연결, 원본에서 나온 정규화 역할을 담는지 확인합니다.

더 넓은 범위 명령 `.venv\Scripts\python -m pytest -q tests/golden/test_evidence.py tests/golden/test_plan.py tests/golden/test_comparison_fields.py --tb=short -x --junitxml=artifacts/comparison-fields-review4-provenance-final.xml`은 처음에 `1 failed, 125 passed in 229.49s`로 끝났습니다. 새 실행 대조군이 정규화하지 않은 원본 역할 철자를 잘못 기대했습니다. 기대 역할을 원본에서 나온 어댑터 역할로 바로잡았고, 그 뒤 위의 13개 경우 실행이 통과했습니다. 그 넓은 실행 뒤로 코드는 바꾸지 않았습니다. 통과한 125개 확인에는 바뀌지 않은 묶음 읽기, 기록 전체와 보류 기록 확인, 낡은 어댑터, 어댑터만 고친 경우, plan 뒤 원본 변경, 검증·공개·이름 바꾸기를 거치는 기관 이름 갱신이 들어 있습니다.

`.venv\Scripts\python -m pytest -q tests/golden/test_validation.py tests/golden/test_improvement.py -k 'inconsistent_source_or_adapter or attribute or absence or false_premise or held_unit or criteria_changed or (previous_versions and validation-14)' --tb=short -x --junitxml=artifacts/comparison-fields-review4-validation-final.xml`은 `31 passed, 141 deselected in 125.72s (0:02:05)`로 끝났습니다. 문서 전체 검증과, 새 `validation-15` 경계를 넘는 B/C/A 이어하기 거부가 들어 있습니다. 공용 읽기를 부르는 코드는 `eligible_units`와 `document_units` 둘이며, 뒤의 것은 문서 전체 검증과 없음 추정이라는 두 사용처에 더 닿습니다. 테스트 정리에서 각자의 회귀 확인을 유지했고, 지울 낡은 테스트, skip, xfail은 없었습니다. `ruff check .`은 통과했습니다. 저장소 전체 검사는 서버가 돌리며 아직 기다리는 중입니다.

## 남은 한계

소스 검토, 받은 회차 보고, 결과 절의 합성 관측에 바탕을 둔 초안입니다. 실제 데이터셋 기록은 보지 않았고 API 호출도 하지 않았습니다. 처음 조사는 과거 체크아웃을 살피지 않았으므로, 받은 보고를 넘는 과거 귀속은 확인하지 않았습니다. pin은 로컬 manifest와의 일관성을 확인할 뿐, 그 manifest를 누가 썼는지 인증하지 않으며, 묶음 파일, manifest, 어댑터 기록을 모두 일관되게 바꾸면 실행의 과거 정체를 증명하지 못합니다. 파일을 따로 읽으므로 동시 쓰기에서 원자적 스냅숏도 세우지 못하며, 이 상황은 조사하지 않았습니다. [C1, C2, C6, C8]
