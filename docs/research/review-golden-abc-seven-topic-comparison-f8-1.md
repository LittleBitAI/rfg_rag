# 리뷰 조사 · F8, 1회차

집계 결과와 측정 조건은 Git에 보관하고, 실제 질문·정답·근거·OCR 텍스트와 레코드별 내보내기는 Git에서 제외된 로컬 `artifacts/`에 보관합니다.

복원 출처: 정리 전 `artifacts/review-round2/originals/` 또는 `d7d1682^`. 아래 수치와 검증 기록은 당시 실행에서 관측한 과거 기록이며, 이번 작업에서 다시 측정한 결과가 아닙니다.

PR #65 리뷰 8회차의 수정 전에 2026-10-18에 쓴 조사 초안입니다. 검증된 사실이나 공용 규칙이 아니며, 리뷰는 이 문서를 수정과 함께 읽습니다.

## 문제

experiment.freeze()는 근거 manifest를 읽기(54행), 프롬프트 스냅숏 찍기(61행), experiments/{id}/freeze.json을 단독 생성하기(67행) 전에 plans/{id}.json을 공개합니다(experiment.py:51-53). plan을 쓴 뒤 어느 단계든 실패하면, plan은 freeze 기록 없이 공개된 채 남습니다. generation._plan_for(generation.py:495)와 validation.py:217은 id로 어떤 plan이든 읽으므로, 주인 없는 plan을 고정 출처 없이 쓸 수 있습니다. 다시 시도하면 plan_path.open('x')에서 FileExistsError가 나므로, 그 실험은 더는 고정할 수 없습니다. 어긴 규칙: 실험 id로 공개된 plan은 완전한 freeze 기록이 있을 때만 있어야 하고, 실패한 고정은 아무것도 남기지 않아 다시 시도할 수 있어야 합니다.

발생: 최후 확인(backstop), 8회차.

- [P1] [P1] golden_pipeline/experiment.py:52 — 고정 공개가 원자적이지 않습니다 / 뒤의 의존 파일 읽기나 manifest 쓰기가 실패하면 / 실험을 다시 시도할 수 없게 되고 고정 출처 없이 돌릴 수 있게 됩니다

## 실패한 수정

- F8에 대해서는 아직 시도한 수정이 없습니다(정정: 아직 없음). 앞선 회차를 통과한 것은 유일한 실패 테스트인 test_freeze_refuses_a_topic_with_an_empty_part_and_writes_no_plan(tests/golden/test_experiment.py:53)이 어떤 쓰기보다 앞선 분할 확인 단계에서 실패하기 때문입니다. plan을 쓴 뒤의 실패를 다루는 테스트가 없어, 쓰고 나서 읽는 순서가 한 번도 시험되지 않았습니다.

## 출처

### S1 — golden_pipeline/experiment.py freeze()

- URL: golden_pipeline/experiment.py
- 확인일: 2026-10-18
- 위치: 51-69행
- 인용: plan_path = storage._child(storage.OUTPUTS / "plans", f"{experiment_id}.json")
    with plan_path.open("x", encoding="utf-8") as f: ...
    evidence_manifest = storage._read_json(storage.OUTPUTS / "evidence" / pool["evidence_run"] / "manifest.json") ... "prompts": storage.snapshot(storage.PROMPTS) ... with (root / "freeze.json").open("x", encoding="utf-8") as f:
- 적용: plan을 실패할 수 있는 읽기와 단계보다 먼저, 되돌리기 없이 씁니다.
- 반대 근거: 없음
- 검증: 수정 뒤에는 마지막 읽기 전에 아무것도 쓰지 않고, plan 연결이 실패할 수 있는 마지막 문장입니다.

### S2 — generation._plan_for와 plan.load_plan

- URL: golden_pipeline/generation.py
- 확인일: 2026-10-18
- 위치: generation.py:495-500; plan.py:74-77; validation.py:217
- 인용: def _plan_for(plan_id, topic):
    plan, plan_sha = plans.load_plan(plan_id) ... load_plan: path = storage._child(storage.OUTPUTS / "plans", f"{plan_id}.json"); return storage._read_json(path), storage._sha256(path)
- 적용: 생성과 검증은 id로 어떤 plan이든 읽고 freeze.json을 찾지 않으므로, 주인 없는 plan을 쓸 수 있습니다. load_plan은 파일 바이트를 해시하므로, 기록하는 해시는 메모리의 문자열이 아니라 파일에서 나와야 합니다.
- 반대 근거: freeze.json을 읽는 곳(pro_packets, comparison.py:26,176)도 plan이 필요하므로, plan 없는 freeze.json은 쓸 수 없습니다.
- 검증: 테스트가 record['plan']['sha256'] == storage._sha256(plan 파일)을 확인합니다.

### S3 — Python os 모듈 문서: os.rename, os.replace

- URL: https://docs.python.org/3/library/os.html
- 확인일: 2026-10-18
- 위치: os.rename / os.replace 항목
- 인용: os.rename: "On Windows, if dst exists a FileExistsError is always raised. The operation may fail if src and dst are on different filesystems." "On Unix, ... If both are files, dst will be replaced silently if the user has permission. ... If successful, the renaming will be an atomic operation (this is a POSIX requirement)." os.replace: "If dst exists and is a file, it will be replaced silently if the user has permission. The operation may fail if src and dst are on different filesystems."
- 적용: Windows와 Linux VM 모두에서 덮어쓰지 않고 plan을 공개하는 데 rename과 replace는 맞지 않습니다.
- 반대 근거: Windows에서 rename은 실제로 덮어쓰기를 거부하므로, Windows만 쓰는 코드라면 쓸 수 있습니다. 이 저장소는 Linux에서도 돕니다(CLAUDE.md 6절).
- 검증: rename을 쓰면 Linux에서 충돌 테스트가 바꿔치기를 보여 줍니다.

### S4 — POSIX link() (The Open Group Base Specifications)

- URL: https://pubs.opengroup.org/onlinepubs/9799919799/functions/link.html
- 확인일: 2026-10-18
- 위치: DESCRIPTION; ERRORS [EEXIST]
- 인용: "The link() function shall atomically create a new hard link for the existing file" ... "If link() fails, no link shall be created and the link count of the file shall remain unchanged." [EEXIST] "The path2 argument resolves to an existing directory entry or refers to a symbolic link."
- 적용: Linux에서 os.link는 plan을 한 단계로 공개하고, 기존 plan을 덮어쓰지 않고 실패합니다.
- 반대 근거: 이 문서가 link가 절대 바꿔치지 않는다고 그대로 말하지는 않습니다. EEXIST 조건과 '실패하면 링크를 만들지 않는다'는 문장에서 나오는 결론입니다.
- 검증: 이미 있는 plan 테스트가 FileExistsError를 내고 기존 바이트를 그대로 둡니다.

### S5 — CreateHardLinkW function (Microsoft Learn)

- URL: https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-createhardlinkw
- 확인일: 2026-10-18
- 위치: 요약; Remarks
- 인용: "This function is only supported on the NTFS file system, and only for files, not directories." "all hard links to a file must be on the same volume." Technology table: "Resilient File System (ReFS) | No"; "SMB 3.0 does not support creation of hard links on shares with continuous availability capability."
- 적용: Windows의 os.link는 NTFS와 같은 볼륨이 필요하므로, 임시 폴더를 OUTPUTS 아래에 둡니다.
- 반대 근거: 이 문서는 lpFileName이 있을 때 나는 오류를 말하지 않습니다. Windows에서 FileExistsError가 나는 것은 Python의 오류 대응에서 예상할 뿐 여기서 인용하지는 않습니다.
- 검증: 충돌 테스트를 Windows 검사에서 돌리면 os.link가 FileExistsError를 내는 것이 확인됩니다.

### S6 — atomicwrites README

- URL: https://slackbuilds.org/repository/14.2/python/atomicwrites/
- 확인일: 2026-10-18
- 위치: README, 덮어쓰기 동작
- 인용: It uses a temporary file in the same directory as the given path. ... On POSIX, it will use rename if files should be overwritten, otherwise a combination of link and unlink. ... there's a timewindow where the file might be available under two entries in the filesystem; permissions of the target file may change this way.
- 적용: 덮어쓰지 않는 공개에 임시 파일과 link를 쓰는 것은 자리 잡은 방식입니다. 이름이 두 개인 틈은 여기서는 해가 없습니다. 임시 이름은 아무도 읽지 않는 TemporaryDirectory 안에 있기 때문입니다.
- 반대 근거: 이 프로젝트는 관리 중단으로 표시돼 있습니다. 여기서는 의존성이 아니라 방식의 근거로만 씁니다.
- 검증: 임시 폴더를 읽는 곳이 없습니다(grep으로 outputs/plans나 OUTPUTS 최상위를 훑는 glob이 없음을 확인).

### S7 — OpenStack Swift: Make object creation more atomic in Linux

- URL: https://opendev.org/openstack/swift/commit/773edb4a5dd22b22f5fcab57820bcbdd4176dfcd
- 확인일: 2026-10-18
- 위치: 커밋 메시지
- 인용: Unlike os.rename(), linkat() cannot overwrite destination path if it already exists.
- 적용: 덮어쓰지 않는 공개에 rename 대신 link를 쓰는 실제 운영 시스템입니다.
- 반대 근거: Swift는 Linux에서 O_TMPFILE을 쓰는데 Windows에는 없습니다. 이 수정은 대신 이름 있는 임시 파일을 씁니다.
- 검증: S4와 같습니다.

### S8 — tests/golden/test_experiment.py 기존 고정 실패 테스트

- URL: tests/golden/test_experiment.py
- 확인일: 2026-10-18
- 위치: 53-59행
- 인용: def test_freeze_refuses_a_topic_with_an_empty_part_and_writes_no_plan ... with pytest.raises(ValueError, match="numeric 묶음이 모자랍니다"): experiment.freeze("x1", "pool") ... assert not (outputs / "outputs/plans/x1.json").exists()
- 적용: 어떤 쓰기보다 앞선 실패만 다루므로, 쓴 뒤의 실패를 잡지 못했습니다.
- 반대 근거: 없음
- 검증: 새 테스트가 쓴 뒤의 실패와 공개 충돌을 다룹니다.

### S9 — OUTPUTS 아래의 cli._config_file 임시 폴더

- URL: golden_pipeline/cli.py
- 확인일: 2026-10-18
- 위치: 147-155행
- 인용: with tempfile.TemporaryDirectory(dir=storage.guard(storage.OUTPUTS)) as folder: path = Path(folder) / "config.json"
- 적용: plan의 임시 파일에 다시 쓸 수 있는 기존 방식입니다. outputs/plans와 같은 볼륨이고, 출력 막이 안에 있으며, 저절로 정리됩니다.
- 반대 근거: 없음
- 검증: 고정 뒤 OUTPUTS 아래에 남은 임시 파일이 없습니다.

## 주장

- C1 (출처; S1, S2): freeze()는 실패할 수 있는 단계보다 먼저 plan을 공개하고, 생성/검증은 freeze.json 없이 공개된 plan을 무엇이든 씁니다. 그래서 plan을 쓴 뒤 실패하면 쓸 수 있지만 뒷받침 없는 plan이 남고, 실험을 다시 시도할 수 없습니다.
- C2 (출처; S3, S4, S6, S7): Linux와 Windows 모두에서 덮어쓰지 않고 공개하려면 임시 파일에서 하드 링크를 거는 것이 맞는 단계입니다. os.rename은 Unix에서 덮어쓰고, os.replace는 어디서나 덮어씁니다.
- C3 (해석; S4, S5): os.link는 대상이 있으면 아무것도 만들지 않고 실패하므로, 기존 pool plan과 plan id가 겹치면 덮어쓰지 않고 거부한 뒤 되돌립니다.
- C4 (해석; S2): Windows 텍스트 모드 쓰기는 줄바꿈을 바꾸고 load_plan은 파일 바이트를 해시하므로, 기록하는 plan SHA-256은 메모리의 문자열이 아니라 쓴 파일에서 계산해야 합니다.
- C5 (해석; S5, S9): 임시 파일을 OUTPUTS 아래 TemporaryDirectory에 두면 하드 링크의 같은 볼륨·NTFS 조건을 만족하고, 저장소의 기존 방식을 다시 씁니다.
- C6 (해석; S8): 유일한 고정 실패 테스트가 어떤 쓰기보다 앞서 실패하므로, 이 지적이 앞선 회차를 통과했습니다.

## 핵심 원리

읽는 사람이 일부만 쓰였거나 뒷받침 없는 상태를 보지 않게 파일을 공개하려면, 임시 이름으로 준비하고 원자적인 디렉터리 작업 하나로 드러냅니다. 대상을 덮어쓰면 안 될 때는 rename() 대신 link()를 씁니다. POSIX link()는 'shall atomically create a new hard link'이고, path2가 있으면 EEXIST로 실패하며, 실패하면 링크를 만들지 않습니다. Python의 os.rename은 Unix에서 소리 없이 덮어쓰지만 Windows에서는 언제나 FileExistsError를 내고, os.replace는 둘 다에서 덮어쓰므로, 어느 것도 이식 가능한 '덮어쓰지 않는 공개'를 주지 못합니다. 파일 두 개를 한 번에 원자적으로 확정할 수는 없으므로, 한 파일을 확정 지점으로 삼아 그것이 기대는 모든 것 뒤에 마지막으로 써야 합니다.

## 적용

golden_pipeline/experiment.py freeze()에서: storage._read_json(...근거 manifest...)과 storage.snapshot(storage.PROMPTS)를 모든 쓰기 위로 옮깁니다. cli._config_file 방식(cli.py:147-155)을 다시 써서 `frozen`을 tempfile.TemporaryDirectory(dir=storage.guard(storage.OUTPUTS)) 안의 파일로 직렬화합니다. 그러면 임시 파일이 하드 링크에 필요한 outputs/plans와 같은 볼륨에 있고, 폴더가 임시 이름을 정리합니다. record['plan']['sha256']에는 그 파일을 storage._sha256으로 해시한 값을 씁니다. Windows 텍스트 모드 쓰기는 '\n'을 '\r\n'으로 바꾸므로, 메모리 문자열을 해시하면 load_plan의 파일 해시와 맞지 않습니다. freeze.json을 open('x')로 쓰고, 그다음 try/except 안에서 os.link(temp, plan_path)를 하며, 실패하면 freeze.json을 지우고 오류를 다시 냅니다. plan_path는 pool plan과 이름 공간을 함께 쓰는 outputs/plans에 있으므로, id 충돌은 link의 FileExistsError로 잡히고 되돌리기가 돕니다. freeze.json을 읽는 곳(experiment.pro_packets, comparison.py:26, 176)도 plan을 읽으므로, plan 없이 남은 freeze.json은 쓰이지 않습니다.

## 가설

원인은 순서입니다. 쓰는 쪽이 볼 수 있는 산출물(plan)을 먼저 쓰고, 아직 실패할 수 있는 단계(manifest 읽기, 프롬프트 스냅숏, freeze.json 만들기)를 그 뒤에 되돌리기 없이 돌립니다. 수정은 모든 읽기를 쓰기보다 먼저 하고, 덮어쓰지 않는 단계 하나로 plan을 마지막에 공개하는 것입니다. plan 바이트를 OUTPUTS 아래 임시 파일에 쓰고, 그 파일의 SHA-256을 freeze.json에 기록하고, open('x')로 freeze.json을 만든 뒤 os.link(temp, plan_path)를 합니다. 링크가 실패하면 freeze.json을 지우고 오류를 다시 냅니다. 그러면 plan 파일이 있다는 것은 freeze 기록이 있다는 뜻이 되고, _plan_for에는 새 확인이 필요 없습니다.

## 반대 근거

- Windows의 하드 링크는 NTFS 전용이고(ReFS 아님) 같은 볼륨이 필요합니다. 로컬 Windows PC(NTFS)와 Linux VM(아마 ext4)의 저장소는 괜찮겠지만, 가정이지 확인한 것은 아닙니다.
- freeze.json을 만든 뒤 링크 전에 프로세스가 (예외가 아니라) 강제로 죽으면 되돌리기가 돌지 않습니다. freeze.json이 plan 없이 남아, 누가 손으로 지울 때까지 open('x')에서 재시도를 막습니다. 쓸 수는 없지만, 그 경우 실험을 다시 시도할 수 없습니다.
- 저장소 규칙 1.1은 근거 없는 예외 처리를 금지합니다. 되돌리기가 정당한 것은 리뷰어의 재현(manifest 없음)과 plan id 충돌이 실제로 일어날 수 있는 실패이기 때문입니다.

## 다른 방법

- 임시 파일+링크 없이 순서만 바꾸기(읽기를 모두 먼저, 그다음 freeze.json, 그다음 open('x')로 plan): 더 작지만, plan을 쓰다가 실패하면 잘린 plan이 남고 실험을 다시 시도할 수 없습니다. 하드 링크를 쓸 수 없다고 밝혀지면 받아들일 만한 대안입니다.
- os.rename(temp, plan_path): Windows에서는 덮어쓰기를 거부하지만(FileExistsError) Linux에서는 소리 없이 바꿔치므로, 팀 VM에서 기존 pool plan을 덮어씁니다. 택하지 않았습니다.
- os.replace: 모든 플랫폼에서 덮어씁니다. plan은 절대 덮어쓰면 안 되므로(README.md:291) 택하지 않았습니다.
- _plan_for가 실험 plan에 freeze.json을 요구하게 하기: 실험 plan과 pool plan을 구별할 방법('stratified_from' 키)이 필요하고, 읽을 때마다 분기가 늘며, 재시도 막힘은 그대로 남습니다. 공개 순서를 고치는 쪽을 택했습니다.
- plan을 experiments/{id}/로 옮겨 폴더 하나를 확정 지점으로 삼기: plan.load_plan과 모든 사용처가 바뀝니다. 지적에 비해 변경이 큽니다.

## 실험

tests/golden/test_experiment.py에 더합니다. (1) write_pool로 pool을 만들고 outputs/evidence/ev/manifest.json을 지운 뒤, freeze('x1','pool')가 FileNotFoundError를 내고 outputs/plans/x1.json과 outputs/experiments/x1/freeze.json이 모두 없는지 확인합니다. manifest를 되돌리고, freeze가 성공하며 record['plan']['sha256'] == storage._sha256(plan 파일)인지 확인합니다. (2) 알려진 바이트로 outputs/plans/x1.json을 미리 만들고, freeze가 FileExistsError를 내며 freeze.json이 없고 기존 plan 바이트가 그대로인지 확인합니다. 수정 전에는 (1)이 재시도에서 FileExistsError로 실패하고, (2)는 freeze.json을 남깁니다. Windows에서 검사를 한 번 돌립니다. tmp_path의 NTFS에서 os.link가 Windows 링크 경로를 다룹니다.

## 결과

실험을 `tests/golden/test_experiment.py::test_a_freeze_that_fails_after_planning_leaves_nothing_and_can_be_retried`(1)와 `::test_a_freeze_onto_an_existing_plan_id_keeps_that_plan_and_writes_no_record`(2)로 돌렸습니다. 수정 전(HEAD `12597db`)에 (1)은 실패했습니다. FileNotFoundError 뒤에 `outputs/plans/x1.json`이 있었고 `freeze.json`은 없었습니다. 임시 테스트(뒤에 지움)로 manifest를 되돌리고 다시 시도하니 `FileExistsError [Errno 17] File exists: …\outputs\plans\x1.json`이 났습니다. (2)는 예측과 달리 수정 전에도 통과했습니다. 옛 순서에서는 plan의 `open("x")`가 먼저 와서 freeze.json을 쓰기 전에 오류를 냈습니다. 새 순서의 되돌리기를 막아 주므로 남겼습니다. 수정은 가설을 따릅니다. `freeze()`는 어떤 쓰기보다 먼저 plan 바이트를 만들고 근거 manifest와 프롬프트 스냅숏을 읽습니다. plan SHA-256은 바이너리로 쓰는 그 바이트에서 얻으므로, 파일과 기록이 같은 바이트를 해시합니다. freeze.json, 그다음 plan을 각각 `experiment._publish`(임시 형제 파일, 그다음 덮어쓰지 않는 `os.link`)로 공개합니다. plan을 링크할 수 없으면 freeze.json을 지우고 오류를 다시 냅니다. 수정 뒤 Windows에서 (1)과 (2)가 통과했고(NTFS tmp_path이므로 하드 링크 경로가 돎), `test_experiment.py`와 `test_cli.py`의 나머지도 통과했습니다(46 passed). 다른 곳에도 같은 규칙을 적용했습니다. `pro_packets`는 단독 쓰기 사이에 주제 명세를 읽고 틀을 채웠고, `review_packets`는 `mkdir()`과 `key.json` 뒤에 `packet.md`를 만들었습니다. 둘 다 이제 첫 쓰기 전에 모든 읽기와 렌더링을 끝냅니다. 결과는 이 문서를 담은 커밋에 있으며, 전체 검사는 서버가 돌리고 아직 기다리는 중입니다.

## 남은 한계

확인하지 않음: 팀 VM의 outputs 디렉터리 파일 시스템이 하드 링크를 지원하는지. freeze.json을 만든 뒤 링크 전에 강제 종료되면 여전히 손으로 지워야 합니다. 같은 id로 freeze()를 동시에 두 번 부르는 경우는 생각하지 않았습니다. 혼자 쓰는 CLI이기 때문입니다.
