# 리뷰 조사 · F8, 2회차

집계 결과와 측정 조건은 Git에 보관하고, 실제 질문·정답·근거·OCR 텍스트와 레코드별 내보내기는 Git에서 제외된 로컬 `artifacts/`에 보관합니다.

복원 출처: 정리 전 `artifacts/review-round2/originals/` 또는 `d7d1682^`. 아래 수치와 검증 기록은 당시 실행에서 관측한 과거 기록이며, 이번 작업에서 다시 측정한 결과가 아닙니다.

PR #65 리뷰 9회차의 수정 전에 2026-10-18에 쓴 조사 초안입니다. 검증된 사실이나 공용 규칙이 아니며, 리뷰는 이 문서를 수정과 함께 읽습니다.

## 문제

experiment.freeze()는 두 산출물(experiments/{id}/freeze.json과 plans/{id}.json)을 모두 남기거나 하나도 남기지 않아야 합니다. generation._plan_for는 freeze.json을 확인하지 않고 id로 plan을 읽으므로, plan이 freeze 기록 없이 있으면 절대 안 됩니다. 실패한 고정은 다시 시도할 수도 있어야 합니다. 9회차 재현이 이를 깹니다. _publish()의 os.link()(experiment.py:87)가 성공한 뒤, finally 안의 temp.unlink()(experiment.py:89)가 오류를 냅니다. plan에서 이 일이 일어나면 freeze()는 이 예외를 링크 실패로 보고 freeze.json을 지우며, 링크된 plan을 남깁니다. 그러면 재시도가 plan 충돌로 실패합니다. freeze.json에서 일어나면 freeze.json이 plan 없이 남습니다.

발생: 반복, 8·9회차.

- [P1] [P1] golden_pipeline/experiment.py:89 — 성공한 공개가 실패로 보고될 수 있습니다 / 임시 링크 정리가 오류를 낼 때 / F8의 갈라진, 다시 시도할 수 없는 상태가 돌아옵니다

## 실패한 수정

- 1회차(05c5196)는 모든 읽기(근거 manifest, 프롬프트 스냅숏)를 쓰기보다 앞으로 옮기고, _publish()(임시 형제 파일 + os.link + finally 안의 unlink)로 freeze.json을 먼저, plan을 마지막에 공개했으며, plan 공개가 오류를 내면 freeze.json을 지웠습니다. 순서는 맞았습니다. 되돌리기 조건이 틀렸습니다. '_publish에서 예외가 나왔다'로 무엇을 되돌릴지 정하지만, _publish에는 확정 지점 뒤에 실패할 수 있는 단계(os.link 뒤의 temp.unlink)가 있습니다. 그래서 예외가 났다고 대상이 만들어지지 않았다는 뜻은 아닙니다. 그 테스트는 공개 전 실패(manifest 없음)와 링크 전 충돌(이미 있는 plan id)을 다뤘으므로, 어느 쪽도 링크 뒤의 실패를 시험하지 않았습니다.

## 출처

### S1 — golden_pipeline/experiment.py freeze()와 _publish()

- URL: golden_pipeline/experiment.py
- 확인일: 2026-10-18
- 위치: 70-89행
- 인용: _publish(root / "freeze.json", ...)
    try:
        _publish(plan_path, plan_bytes)
    except BaseException:
        (root / "freeze.json").unlink()
        raise
...
    temp.write_bytes(data)
    try:
        os.link(temp, path)
    finally:
        temp.unlink()
- 적용: 같은 호출 안에서 확정 지점(os.link) 뒤에 실패할 수 있는 정리가 오고, 바깥 처리기는 어떤 예외든 '공개되지 않음'으로 읽습니다.
- 반대 근거: 실제로 unlink가 절대 실패하지 않는다면, 갈라진 상태는 오류 주입으로만 닿을 수 있습니다. 그래도 리뷰어는 이를 P1로 봅니다.
- 검증: 수정 뒤에는 plan 쓰기가 끝난 뒤 오류를 낼 수 있는 문장이 없고, 되돌리기는 `created`에 있는 경로만 지웁니다.

### S2 — Python Language Reference: The try statement(finally 절)

- URL: https://docs.python.org/3/reference/compound_stmts.html
- 확인일: 2026-10-18
- 위치: 8.4 The try statement, finally 절
- 인용: If an exception occurs in any of the clauses and is not handled, the exception is temporarily saved. The finally clause is executed. If there is a saved exception it is re-raised at the end of the finally clause. If the finally clause raises another exception, the saved exception is set as the context of the new exception. If the finally clause executes a return, break or continue statement, the saved exception is discarded.
- 적용: os.link가 성공하면 저장된 예외가 없으므로, finally 안 temp.unlink의 예외만 전해집니다. 호출하는 쪽에서는 성공한 링크와 실패한 링크가 똑같아 보입니다.
- 반대 근거: 둘 다 실패하면 예외 연결이 문맥을 남기지만, 성공한 경우에는 도움이 되지 않습니다.
- 검증: 리뷰어의 오류 주입(링크 뒤 임시 파일 unlink가 오류를 냄)이 HEAD에서 갈라진 상태를 재현합니다.

### S3 — atomicwrites 소스(_move_atomic, AtomicWriter)

- URL: https://python-atomicwrites.readthedocs.io/en/latest/_modules/atomicwrites.html
- 확인일: 2026-10-18
- 위치: _move_atomic POSIX 분기; move_atomic 설명; AtomicWriter._open
- 인용: def _move_atomic(src, dst):
        os.link(src, dst)
        os.unlink(src)  ... "Move src to dst. There might a timewindow where both filesystem entries exist." "If dst already exists, FileExistsError will be raised." "Both paths must reside on the same filesystem for the operation to be atomic." rollback failures are suppressed: try: self.rollback(f) except Exception: pass
- 적용: 1회차가 '링크 뒤 unlink'의 본보기로 인용한 라이브러리도 링크 뒤에 아무 막이 없이 unlink하므로, 링크 뒤 정리 실패가 확정 단계에서 전해집니다. 약점은 이 코드만이 아니라 방식 자체에 있습니다. 예외를 삼키는 것은 되돌리기에서만이고, 확정 뒤에서는 아닙니다.
- 반대 근거: atomicwrites는 파일 하나를 공개하므로, 링크 뒤 예외가 산출물 두 개를 가르지 않습니다. 이 프로젝트는 관리가 중단됐습니다.
- 검증: 소유 기반 설계에는 확정 뒤 단계가 없으므로 이 약점이 해당하지 않습니다.

### S4 — Python 내장 open(): 'x' 모드

- URL: https://docs.python.org/3/library/functions.html
- 확인일: 2026-10-18
- 위치: open() 모드 표, 'x'
- 인용: 'x' open for exclusive creation, failing if the file already exists
- 적용: open('xb')가 성공하면 이 호출이 그 경로를 만들었다는 증거이므로, 되돌리기가 지워도 됩니다. 이미 있는 plan id에서 open이 실패하면 그 plan은 건드리지 않습니다.
- 반대 근거: 이 문서는 원자성을 직접 보장하지 않으며, 그 보장은 바탕의 O_EXCL(S5)에서 옵니다. NFSv2에서는 O_EXCL을 믿을 수 없습니다.
- 검증: 기존 테스트 test_a_freeze_onto_an_existing_plan_id_keeps_that_plan_and_writes_no_record가 통과합니다. FileExistsError, 기존 바이트 그대로, freeze.json 없음입니다.

### S5 — open() O_CREAT|O_EXCL 동작(Open Group 글 인용)

- URL: https://zenn.dev/tn_a/articles/system-call-open
- 확인일: 2026-10-18
- 위치: Open Group open() 페이지를 인용한 O_EXCL 설명
- 인용: If O_CREAT and O_EXCL are set, open() shall fail if the file exists. The check for the existence of the file and the creation of the file if it does not exist shall be atomic with respect to other threads executing open() naming the same filename in the same directory with O_EXCL and O_CREAT set.
- 적용: 소유 판단 뒤에 있는 보장입니다. 경로를 만들 수 있는 호출은 하나뿐이고, 그 호출은 자기가 만들었다는 것을 압니다.
- 반대 근거: POSIX를 인용한 2차 자료입니다. 원자성은 다른 O_EXCL 열기에 대해서만 보장되며, NFSv2는 O_EXCL을 지원하지 않습니다(SEI CERT).
- 검증: S4와 같습니다.

### S6 — golden_pipeline/plan.py pool plan 쓰기

- URL: golden_pipeline/plan.py
- 확인일: 2026-10-18
- 위치: 69행
- 인용: with path.open("x", encoding="utf-8") as f:
- 적용: 저장소는 이미 임시 파일 없이 단독 생성으로 plan을 바로 공개하므로, 수정은 기존 방식을 다시 씁니다(기록된 SHA-256이 디스크의 바이트와 맞도록 바이너리 'xb'로 씀).
- 반대 근거: pool plan 쓰기는 산출물 하나만 쓰므로 되돌리기가 없습니다.
- 검증: 재시도 테스트에서 freeze.json의 plan SHA-256이 storage._sha256(plan 파일)과 같습니다.

## 주장

- C1 (출처; S1): freeze()의 되돌리기는 _publish(plan_path)가 오류를 낼 때마다 freeze.json을 지우지만, _publish는 os.link가 이미 plan을 만든 뒤에도 오류를 낼 수 있으므로, 되돌리기가 있는 plan의 기록을 지울 수 있습니다.
- C2 (출처; S1, S2): 성공한 단계 뒤 finally 절에서 난 예외는 유일한 예외로 전해지므로, 호출하는 쪽은 링크가 성공했다는 것을 알 수 없습니다.
- C3 (해석; S3): atomicwrites의 '링크 뒤 unlink'도 확정 뒤의 같은 unlink를 막지 않으므로, 1회차 방식이 이 실패를 함께 들여왔습니다.
- C4 (해석; S4, S5, S6): 단독 생성은 소유 신호를 줍니다. open('xb')가 돌아오면 이 호출이 경로를 만든 것이므로 되돌리기가 정확히 그 경로를 지울 수 있고, 이미 있던 plan은 절대 건드리지 않습니다.
- C5 (해석; S1, S6): freeze.json, 그다음 plan을 open('xb')로 만들고, 각각을 `created`에 기록하며, 어떤 예외에서든 정확히 그것들을 지우면, 마지막 확정 뒤에 실패할 수 있는 단계가 없고 임시 파일, 하드 링크, _publish()가 사라집니다.

## 핵심 원리

'확정 후 정리' 순서는 확정이 일어난 뒤에 실패를 보고하면 안 되며, 되돌리기는 그 작업이 만들었다고 아는 것만 되돌려야 합니다. Python의 try 문은 finally 끝에서 저장된 예외를 다시 내지만, 'if the finally clause raises another exception, the saved exception is set as the context of the new exception'. 그래서 성공한 단계 뒤에 도는 finally에서 난 예외는 그 단계의 실패와 똑같아 보입니다. 단독 생성('x': 'open for exclusive creation, failing if the file already exists', POSIX O_CREAT|O_EXCL은 파일이 있으면 실패하고, 확인과 생성이 다른 O_EXCL 열기에 대해 원자적)은 분명한 소유 신호를 줍니다. open이 돌아오면 이 호출이 파일을 만들었고, 지워도 됩니다.

## 적용

golden_pipeline/experiment.py:70-89입니다. _publish 안의 확정 지점은 87행의 os.link이고, 그 뒤의 실패할 수 있는 단계는 89행의 temp.unlink입니다. 71-75행의 바깥 처리기는 _publish(plan_path)의 어떤 예외든 'plan이 만들어지지 않음'으로 보고 freeze.json을 지웁니다. 70행에서 같은 일이 일어나면 freeze.json이 plan 없이 남습니다. 70-89행을 `created` 목록과 open('xb') 쓰기 두 개로 된 try 블록 하나로 다시 쓰면 두 경로가 모두 사라집니다. outputs/plans를 나열하는 곳은 없으므로(golden_pipeline을 grep하면 plan.py:31,76과 experiment.py:65뿐이고 모두 id로 읽음), 임시 파일에 기대는 것은 없습니다. freeze.json을 읽는 곳(pro_packets, comparison.py)은 plan도 읽고 SHA-256을 비교하므로, plan이 없으면 멈춥니다.

## 가설

freeze()의 되돌리기는 이 호출이 실제로 어떤 산출물을 만들었는지가 아니라 예외가 어디서 났는지로 어떤 산출물이 있는지 추론합니다. _publish()에는 확정 지점(os.link) 뒤에 실패할 수 있는 정리 단계가 있으므로, '오류가 났다'가 '공개되지 않았다'를 뜻하지 않습니다. 수정은 마지막 확정 뒤에 단계를 두지 않고 소유로 되돌리는 것입니다. 각 파일을 단독 생성으로 바로 만듭니다(path.open('xb'), plan.py:69가 pool plan에 이미 쓰는 방식). freeze.json을 먼저, plan을 마지막에 만듭니다. open이 성공하자마자 경로를 `created` 목록에 더합니다. 어떤 예외에서든 `created`에 있는 경로만 정확히 지우고 오류를 다시 냅니다. 그러면 임시 파일, 하드 링크, _publish()가 사라지므로, 파일이 확정된 뒤에 실패할 것이 없습니다. plan id가 이미 있으면 plan 경로를 기록하기 전에 open('xb')가 오류를 내므로, freeze.json만 지워지고 기존 plan은 건드리지 않습니다.

## 반대 근거

- 임시 파일이 없으면, plan을 쓰는 중에 (예외가 아니라) 강제 종료될 때 완전한 freeze.json 옆에 잘린 plan이 남습니다. load_plan은 JSON을 파싱하므로, 잘린 객체는 소리 없이 쓰이지 않고 읽기에 실패합니다. 단 하나의 예외는 정확히 닫는 중괄호에서 끝나는 앞부분으로, SHA-256이 기록과 달라도 _plan_for가 받아들입니다. 1회차 설계에서도 두 링크 사이에 강제 종료되면 freeze.json이 남아 재시도를 막았으므로, 어느 설계도 강제 종료를 깔끔하게 견디지 못합니다.
- 되돌리기 안의 unlink 자체가 실패하면 상태가 다시 갈라집니다. 오류 처리 중의 두 번째 실패이며, 어느 설계도 이를 막지 않습니다. 규칙 1.1은 이를 위해 층을 더하는 데 반대합니다.
- 1회차는 쓰는 도중 실패하면 잘린 plan이 남아 재시도를 막는다는 이유로 'open(x)로 순서만 바꾸기'를 택하지 않았습니다. 그 이유는 plan을 되돌리지 않는다고 가정했습니다. 소유 기반 되돌리기에서는 이 호출이 만든 plan이 어떤 예외에서든 지워지므로, 그 반대 이유가 더는 해당하지 않습니다.

## 다른 방법

- _publish를 유지하고 링크 뒤 정리를 최선 노력으로 바꾸기(`with contextlib.suppress(OSError): temp.unlink()`를 링크 뒤와 실패 경로에 적용). 변경이 더 작고 리뷰어의 재현을 고치지만, outputs/plans/에 plan을 가리키는 숨은 하드 링크가 남고, 확인하지 않은 하드 링크 의존(NTFS, 같은 볼륨, 팀 VM 파일 시스템)도 남습니다. OSError만 삼키므로, 다른 형식을 내는 테스트에서는 여전히 상태가 갈라집니다. 두 번째 선택입니다.
- temp.unlink를 _publish 밖, freeze()에서 두 링크가 모두 성공한 뒤로 옮기기. 완전하고 일관된 공개 뒤에도 freeze()가 여전히 오류를 내고(지적의 '실패로 보고됨' 절반), 재시도는 자기 성공한 고정과 충돌합니다. 택하지 않았습니다.
- _plan_for가 실험 plan에 freeze.json을 요구하게 하기. 읽을 때마다 분기가 늘고 재시도 가능성을 되살리지 못합니다. 1회차처럼 택하지 않았습니다.

## 실험

링크 뒤 상황을 새 설계에 맞는 것으로 바꿉니다. tests/golden/test_experiment.py에서 pathlib.Path.open을 바꿔, outputs/plans/x1.json이면 진짜 open을 'xb'로 부르고 파일을 닫은 뒤 돌려주게 합니다. 이제 파일은 있고, 뒤따르는 f.write가 ValueError를 냅니다. freeze('x1','pool')가 오류를 내고 plans/x1.json과 experiments/x1/freeze.json이 모두 없는지 확인한 뒤, 패치를 풀고 재시도가 성공하며 record['plan']['sha256'] == storage._sha256(plan 파일)인지 확인합니다. 지금 HEAD 51ebc1b에서는 이 테스트가 실패해야 합니다. 거기서는 바꾼 open이 plans/x1.json을 건드리지 않으므로(plan은 os.link에서 옴), 리뷰어가 설명한 대로 임시 파일 unlink가 오류를 내게 하고, freeze.json이 사라지고 plan이 남기를 예상합니다. 1회차의 기존 테스트 두 개(manifest 없음, 이미 있는 plan id는 바이트를 유지하고 기록을 쓰지 않음)는 그대로 둡니다. 바꾸지 않고 통과해야 합니다. test_experiment.py를 한 번 돌린 뒤 검사를 돌립니다.

## 결과

HEAD `065063a`(코드는 `51ebc1b`와 같음)에서 임시 테스트(뒤에 지움)로 리뷰어의 상황을 재현했습니다. 임시 `.x1.json.*.tmp`에서만 오류를 내도록 `pathlib.Path.unlink`를 바꿨습니다. `freeze()`는 PermissionError를 냈고, plan은 있었고, freeze.json은 없었습니다. 재시도는 `plans/x1.json`에서 `FileExistsError [WinError 183]`을 냈습니다. 제안한 실험은 `tests/golden/test_experiment.py::test_a_freeze_that_fails_after_creating_the_plan_removes_what_it_created_and_can_be_retried`입니다. `Path.open`이 이미 닫힌 plan 파일을 돌려주도록 바꿉니다. HEAD의 `experiment.py`에 돌리면 예측대로 `DID NOT RAISE ValueError`로 실패했습니다. plan이 `os.link`에서 왔으므로 바꾼 open이 이를 건드리지 않았습니다. 수정은 가설을 따릅니다. `_publish`, 임시 파일, 하드 링크가 없어졌습니다. `experiment.create_all({path: bytes})`가 각 파일을 `open("xb")`로 만들고, open이 돌아오자마자 경로를 기록하며, 어떤 예외에서든 기록된 경로만 정확히 지우고 오류를 다시 냅니다. 한 가지는 바꿔야 했습니다. 경로는 `with` 안이 아니라 `with`에 들어가기 전에 기록합니다. 실험의 닫힌 파일 때문에 `with` 자체가 오류를 내서, 그대로라면 plan이 기록되지 않았을 것입니다. 수정 뒤 새 테스트가 통과하고, 1회차 테스트 두 개도 바꾸지 않고 통과합니다(manifest 없음, 이미 있는 plan id는 바이트를 유지하고 기록을 쓰지 않음). 다른 곳에도 같은 규칙을 적용했습니다. `pro_packets`(반복으로 쓰는 단독 파일 14개)와 `review_packets`(`mkdir` 뒤의 `key.json`, `packet.md`, `judgments.csv`)도 이제 `create_all`로 공개하므로, 쓰기가 실패해도 다시 돌리기를 막는 것이 남지 않습니다. `tests/golden/test_experiment.py`와 `test_cli.py`는 47 passed였으며, 이 문서를 담은 커밋에 있습니다. 전체 검사는 서버가 돌리고 아직 기다리는 중입니다.

## 남은 한계

이중 실패(되돌리기의 unlink가 실패)는 다루지 않습니다. plan을 쓰는 중에 강제 종료되면 freeze.json과 잘린 plan이 남고, 다시 시도하기 전에 손으로 지워야 합니다. 같은 id로 동시에 고정하는 경우는 생각하지 않았습니다(혼자 쓰는 CLI). 테스트가 HEAD에서 실패한다는 예측은 돌려 보지 않았습니다.
