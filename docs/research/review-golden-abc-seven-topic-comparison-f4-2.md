# 리뷰 조사 · F4, 2회차

집계 결과와 측정 조건은 Git에 보관하고, 실제 질문·정답·근거·OCR 텍스트와 레코드별 내보내기는 Git에서 제외된 로컬 `artifacts/`에 보관합니다.

복원 출처: 정리 전 `artifacts/review-round2/originals/` 또는 `d7d1682^`. 아래 수치와 검증 기록은 당시 실행에서 관측한 과거 기록이며, 이번 작업에서 다시 측정한 결과가 아닙니다.

PR #65 리뷰 3회차의 수정 전에 2026-10-18에 쓴 조사 초안입니다. 검증된 사실이나 공용 규칙이 아니며, 리뷰는 이 문서를 수정과 함께 읽습니다.

## 문제

지켜야 할 규칙: 장부가 거부(BudgetExceeded)하기 전에 끝난 유료 호출은 모두 정확히 보존합니다. 이어할 때, 호출을 한 후보는 그 호출 자신의 출력을 돌려받습니다. 두 번 사지 않고, 다른 호출의 출력을 대신 쓰지 않습니다. 5ec5266에서 resume_validation(golden_pipeline/validation.py:90-91)은 `settled`를 (request_sha256, attempt)만을 키로 하는 사전으로 만듭니다. 이미 판정이 끝난 후보를 포함해, 모든 검증 기록과 모든 후보의 호출을 읽습니다. `_reply`(validation.py:955-957)는 그 내용 해시로 출력을 찾습니다. 메시지가 같은 서로 다른 논리적 호출 두 개는 키 하나를 함께 쓰고, 사전 컴프리헨션은 마지막에 온 것을 남깁니다. 예: 질문, 근거 이름표와 글은 같고 참조만 다른 두 후보, 또는 multi_hop 후보가 두 번 보낼 수 있는 똑같은 채점 요청입니다. 그러면 미판정 후보가 형제 후보의 출력을 다시 써서, 재시도 여부와 판정이 바뀔 수 있습니다.

발생: 반복, 2·3회차.

- [P1] [P1] golden_pipeline/validation.py:90 — 동일 요청의 정산 결과가 하나로 합쳐져 재개 시 다른 후보의 응답을 재사용함

## 실패한 수정

- 1회차(89f54e6): generation.parallel(generation.py:449-460)은 항목마다 BudgetExceeded를 잡고 그 항목만 None을 돌려주므로, 끝난 형제 판정은 남습니다. 버티지 못한 이유는 _verdict 하나가 여러 호출을 차례로 하기 때문입니다(검증기 재시도, 문서 묶음, multi_hop 단일 단위 확인, 채점). 중간에 거부되면 그 후보의 앞서 끝난 출력은 여전히 버려졌고, `calls`에는 토큰 행만 남았습니다. 이것이 2회차 지적이었습니다.
- 2회차(60b911a/5ec5266): _reply가 호출 기록마다 request_sha256, attempt, text를 쓰고, resume_validation이 이를 `settled`로 모으며, _reply는 다시 부르지 않고 맞는 것을 다시 씁니다. 버티지 못한 이유는 키가 어느 호출이었는지가 아니라 요청 내용이기 때문입니다. candidate_id를 기록하지 않고, 미판정이 아닌(이미 판정된) 후보의 호출도 내주며, 겹치는 키는 하나로 합쳐집니다. 이 수정의 테스트(tests/golden/test_cli.py:221)에는 중단된 후보가 하나뿐이고 겹치는 요청이 없으므로, 충돌이 일어날 수 없습니다.
- 조사 과정: F4로 분류된 1회차 문서(docs/research/review-golden-abc-seven-topic-comparison-f4-1.md)는 실제로 F1 plan 해시 지적을 조사했고, 그 문서의 결과 절도 그렇게 말합니다. F4 재사용 키는 조사 없이 설계됐고, 내용 해시가 호출을 식별하는지 아무도 묻지 않았습니다.

## 출처

### S1 — Event History walkthrough with the Python SDK (Temporal 문서)

- URL: https://docs.temporal.io/encyclopedia/event-history/event-history-python
- 확인일: 2026-10-18
- 위치: Replay / non-determinism 절
- 인용: The Worker must "produce a set of Commands which is compared against the sequence of Commands in the Event History." A Command proceeds when it is "the right type of Command and it occurs at the right position in the expected sequence, so Replay proceeds." On mismatch: "That is not the Command it expected at this position in the sequence", and the execution "cannot be replayed". Condition: a Workflow Definition is deterministic if it "produces the same Commands in the same sequence given the same input"; calls to external systems belong in Activities, which may be non-deterministic, and their results come from the history on replay.
- 적용: 후보마다의 _verdict는 워크플로, _reply API 호출은 Activity 역할을 합니다. 기록된 출력은 요청 내용으로 전체에서 찾지 말고, 그 후보의 호출에 순서대로 맞춰야 합니다.
- 반대 근거: Temporal은 실행마다 기록 하나를 남기고 위치로 맞춥니다. golden_pipeline에는 지금 후보별 기록이 없어 candidate_id를 더해야 합니다. Temporal은 명령 종류도 맞추지만, 이 제안은 한 후보 안에서 요청 해시를 맞춥니다.
- 검증: 수정 뒤 이어하기는 미판정 후보마다 자기 기록 출력만 호출 순서대로 줍니다. 새 테스트는 Y가 X의 출력이 아니라 자기 attempt-0 출력을 받는 것을 보여 줍니다.

### S2 — Idempotent requests (Stripe API 문서)

- URL: https://docs.stripe.com/api/idempotent_requests.md
- 확인일: 2026-10-18
- 위치: 키 만들기와 인자 비교에 대한 문단
- 인용: "A client generates an idempotency key, which is a unique key that the server uses to recognize subsequent retries of the same request. How you create unique keys is up to you, but we suggest using V4 UUIDs, or another random string with enough entropy to avoid collisions." "For API v1, Stripe saves the status code and body of the first request made with a given idempotency key after endpoint execution begins. Retries with the same key return the saved response, including 500 errors." "The idempotency layer compares incoming parameters to those of the original request and errors if they're not the same to prevent accidental misuse." Limits: results are saved only after endpoint execution begins; keys may be pruned after 24 hours, after which reuse creates a new request.
- 적용: 저장된 결과를 돌려주는 키는 작업 하나(여기서는 후보의 호출 하나)를 가리켜야 합니다. 요청 인자, 여기서는 request_sha256은 막이로만 쓰고 정체로 쓰지 않습니다.
- 반대 근거: Stripe는 네트워크 실패를 사이에 둔 HTTP 요청 하나의 클라이언트 재시도를 다루며, 여러 호출로 된 계산을 재생하는 것이 아닙니다. '키는 작업 하나를 가리키고 인자는 막이'라는 원칙만 옮겨 옵니다.
- 검증: 수정 뒤 조회에 candidate_id가 들어가고, 요청 해시는 그 후보 자신의 호출 안에서만 고릅니다.

### S3 — golden_pipeline/validation.py (resume_validation, _judge_run, _reply)

- URL: golden_pipeline/validation.py
- 확인일: 2026-10-18
- 위치: 87-92행, 114-116행, 129-130행, 947-974행
- 인용: `settled = {(call["request_sha256"], call["attempt"]): call["text"] for path in storage.validation_records(run_dir) for call in storage._read_json(path)["calls"] if "text" in call}`; `ask = _asker(client, config, ..., calls, settled)` built once for all candidates; `_reply`: `request = hashlib.sha256(json.dumps(messages, ...)).hexdigest()` ... `text = settled.get((request, attempt))`; call records hold question, labels, model, tokens, request_sha256, attempt, text, and no candidate_id.
- 적용: 내용 기준 키, 후보 거르기 없음(판정이 끝난 후보의 호출도 내줌), 겹치는 키의 덮어쓰기를 보여 줍니다. 3회차 지적의 정확한 위치입니다.
- 반대 근거: `pending`(87행)은 이미 계산돼 거르는 데 쓸 수 있지만, 호출에 거를 candidate_id가 없습니다.
- 검증: 수정 뒤 호출에 candidate_id가 있고, settled는 미판정 id에 대해서만 FIFO 목록으로 만들며, ask/judge는 후보마다 만듭니다.

### S4 — golden_pipeline/generation.py 모듈 설명과 parallel()

- URL: golden_pipeline/generation.py
- 확인일: 2026-10-18
- 위치: 4-5행; 449-460행
- 인용: "LLM 출력은 같은 입력에도 달라질 수 있어 결정성을 주장하지 않는다." parallel: "실험 장부가 어느 호출을 거절하면 그 자리만 None 이다. 함께 보낸 다른 호출은 이미 정산됐으므로 그 결과를 버리지 않는다."
- 적용: 똑같은 요청 두 개는 서로 다른 유료 결과 두 개이므로, 요청이 같다고 결과가 같다고 볼 수 없습니다. parallel은 후보마다 _verdict를 자기 작업자에서 돌리므로, 후보별 큐는 스레드 하나만 꺼냅니다.
- 반대 근거: 정체에 관해서는 없습니다. 공용 `calls` 목록의 스레드 안전성은 CPython의 원자적 list.append에 기대며, 코드가 이미 그렇게 기대고 있습니다.
- 검증: 새 테스트는 똑같은 요청에 두 후보가 서로 다른 출력을 받게 하고, 각자 자기 것을 받는지 확인합니다.

### S5 — tests/golden/test_cli.py 2회차 F4 테스트

- URL: tests/golden/test_cli.py
- 확인일: 2026-10-18
- 위치: test_resuming_a_candidate_refused_mid_verdict_reuses_its_settled_calls, 221-244행
- 인용: Only the bond ('보증금') candidate is intercepted; `sent` counts its requests; call 2 raises BudgetExceeded; `assert len(sent) == 3`.
- 적용: 요청이 서로 다른 중단 후보 하나만 시험하므로 내용 키가 충돌하지 않습니다. 3회차 결함을 잡을 수 없습니다.
- 반대 근거: 2회차 동작(후보 자신의 끝난 호출을 다시 사지 않음)은 올바르게 막으므로 남겨야 합니다.
- 검증: 새 충돌 테스트는 HEAD에서 실패하고 수정 뒤에 통과하며, 이 테스트는 계속 통과합니다.

### S6 — F4로 분류된 1회차 조사 문서

- URL: docs/research/review-golden-abc-seven-topic-comparison-f4-1.md
- 확인일: 2026-10-18
- 위치: 문제, 가설, 결과 절
- 인용: 결과: "이 문서의 본문은 review-packets의 plan 해시(2회차 F1)를 조사하며, 분류된 2회차 F4 지적(후보 하나의 판정 안에서 하위 호출 결과를 잃음)이 아닙니다."
- 적용: 2회차 F4 수정의 재사용 키가 설계 검토를 받지 못한 이유를 설명합니다.
- 반대 근거: 그 문서의 결과 절은 F4 수정과 테스트를 설명했지만, 키의 정체는 살피지 않았습니다.
- 검증: 이번 회차 문서는 F4를 바로 다룹니다.

## 주장

- C1 (출처; S1): 외부 호출의 기록 결과는 결정적인 실행 안에서의 위치로 그 결과를 만든 호출에 맞출 때만 안전하게 재생할 수 있습니다. 위치가 맞지 않으면 기록을 재생할 수 없습니다.
- C2 (출처; S2, S4): 저장된 결과를 돌려주는 키는 작업 하나를 가리켜야 합니다. 인자가 같은지는 잘못 쓰는 것을 막는 막이일 뿐이며, LLM에 같은 입력을 줘도 다른 유료 결과가 나올 수 있습니다.
- C3 (출처; S3): 5ec5266에서 이어하기 재사용 키는 모든 기록의 모든 후보에서 모은 (request_sha256, attempt)이며 후보 id가 없으므로, 겹치는 키는 마지막에 쓴 것 하나로 합쳐집니다.
- C4 (해석; S1, S4, S3): 후보 하나의 _verdict는 작업자 하나에서 차례로 돌고 호출 순서가 앞선 답과 고정한 입력에만 달려 있으므로, (후보, 요청, 시도)별 FIFO 큐에서 꺼내면 각 호출 자신의 출력이 정확히 재현됩니다.
- C5 (해석; S3): 앞선 기록에서 이미 판정이 끝난 후보의 호출은 이어할 때 내주면 안 됩니다. last['pending']으로 거르려면 호출마다 candidate_id가 있어야 합니다.
- C6 (출처; S5): 2회차 테스트에는 요청이 서로 다른 중단 후보 하나뿐이라 키 충돌을 잡을 수 없었습니다.
- C7 (출처; S6): 2회차 F4 수정은 재사용 키에 대한 조사 없이 설계됐습니다. 1회차 F4 문서가 대신 F1 plan 해시 지적을 조사했기 때문입니다.

## 핵심 원리

부작용이 있는 호출의 기록 결과를 재생하는 것은 결과마다 그것을 만든 호출에 맞출 때만 안전합니다. 결정적인 실행 하나 안에서의 위치나, 작업 하나를 가리키는 키로 맞춥니다. Temporal은 재생할 때 명령마다 종류와 기록된 순서 안의 위치를 확인하며, 위치가 틀린 명령은 재생할 수 없습니다. Stripe는 클라이언트가 작업마다 고유 키(UUID)를 만들게 하고, 그 키 아래 첫 결과를 저장하며, 인자는 잘못 쓰는 것을 잡는 데만 비교합니다. 인자가 같다고 두 요청이 같은 작업이 되지는 않습니다.

## 적용

후보 하나의 _verdict(validation.py:512-528, 610-671)는 분기가 이미 받은 답에만 달린 순차 실행입니다. `survivors`에 달린 정적 확인은 어떤 호출보다 먼저 돌고, plan/프롬프트/모델/가격은 plan 확인과 resume_validation:76-81의 기준 확인으로 고정됩니다. 그래서 후보 하나의 n번째 호출은 재현할 수 있고, (후보, 요청, 시도)로 순서대로 재생하면 호출마다 자기 끝난 출력을 받습니다. 바꿀 곳은 _reply(validation.py:947-974: candidate_id를 더하고 후보별 큐에서 꺼냄), _asker/_judger(927-944: 후보 id와 그 큐를 받음), _judge_run(115-116, 129-130: 람다 안에서 항목마다 ask/judge를 만듦), resume_validation(90-91: last['pending']으로 거르고, 사전 덮어쓰기 대신 목록을 만듦)입니다. validate()와 release는 여전히 빈 `settled`를 넘깁니다.

## 가설

재사용 캐시가 어느 호출이 보냈는지(후보 + 그 후보 판정 안의 순서)가 아니라 무엇을 보냈는지(요청 해시 + 시도)를 키로 씁니다. 우연히 같은 요청을 보낸 서로 다른 호출은 서로 덮어쓰고, 이미 판정이 끝난 후보의 호출도 여전히 내줍니다. 수정: (1) _reply가 호출마다 `candidate_id`를 기록합니다. (2) ask/judge를 parallel 람다 안에서 후보마다 만들어, _reply가 자기 후보를 압니다. (3) resume_validation은 last['pending']의 후보에 대해서만, (candidate_id, request_sha256, attempt)마다 기록 순서와 기록 안의 호출 순서대로 FIFO 출력 목록을 만듭니다. (4) _reply는 자기 키의 맨 앞 항목을 꺼내고, 목록이 비었을 때만 API를 부릅니다. 후보 하나의 호출은 스레드 하나에서 차례로 돌므로, 순서대로 꺼내면 똑같은 요청마다 자기 출력을 돌려줍니다. 재생한 출력은 여전히 `calls`에 다시 더하지 않으므로, 세 번째 기록도 큐와 맞고 비용을 두 번 세지 않습니다.

## 반대 근거

- LLM이 같은 요청에 언제나 같은 출력을 낸다면, 충돌은 같은 결과를 다시 쓸 뿐입니다. 하지만 generation.py:4는 같은 입력에도 출력이 달라질 수 있다고 하고, 형제의 출력은 다른 유료 호출이므로 규칙은 여전히 깨집니다.
- 형제의 출력도 똑같은 요청에 대한 실제 끝난 응답이므로 올바른 표본이라고 주장할 수 있습니다. 그래도 미판정 후보의 판정이 형제와 스레드 완료 순서에 달리게 되고, 미판정 후보 자신의 끝난 출력은 잃습니다.
- 후보 안의 중복(multi_hop 후보 하나에서 똑같은 채점 요청 두 번)이 실제 데이터에서 일어나는지는 시험하지 않았습니다. 3회차가 제기한 후보 간 경우만으로도 수정할 이유가 충분합니다.

## 다른 방법

- 보통 사전으로 (candidate_id, request_sha256, attempt)를 키로 쓰기: 가장 작은 변경으로 후보 간 충돌을 고치지만, 한 후보 안의 똑같은 요청은 서로 덮어쓴 채 남습니다. FIFO 목록은 한 줄 더 들고 두 경우를 모두 다룹니다.
- (candidate_id, 순번)을 키로 쓰고 request_sha256은 막이로 남기기(Temporal 방식): 똑같이 정확하지만, ask와 judge가 함께 쓰고 기록을 넘어 이어지는 카운터가 필요합니다. 같은 보장에 대해 FIFO 꺼내기보다 움직이는 부분이 많습니다.
- 재생을 없애고 다시 돌리는 비용을 내기: F4 규칙을 깹니다(끝난 호출을 다시 사고, 한도 근처에서는 다시 돌리기가 들어가지 않을 수 있음). 택하지 않았습니다.
- 원래 호출 출력 대신 미판정 후보마다 판정 중간 상태를 저장하기: _verdict의 모든 분기에 이어할 수 있는 형태가 필요합니다. 호출 재생보다 큰 변경입니다. 첫 선택이 아닙니다.

## 실험

tests/golden/test_cli.py:221 옆에 planned/api 테스트 준비물을 다시 쓰는 테스트 하나를 더합니다. B 실행 하나에 질문, 근거 이름표와 글은 같고 참조만 다른 숫자 후보 두 개를 만들어, 검증기 요청의 SHA-256이 같게 합니다. generation.WORKERS = 1로 두고, 미판정으로 남을 후보(Y)가 형제(X)보다 앞에 오게 순서를 정합니다. 그러면 HEAD에서 Y의 호출 기록이 먼저 쓰이고 X의 기록이 이를 덮어씁니다. 가짜 클라이언트: Y attempt 0 -> 'JSON 아님', Y attempt 1 -> BudgetExceeded, X attempt 0 -> X를 거부하는 올바른 판정. audit을 돌린 뒤 resume을 돌립니다. HEAD에서는 resume이 Y의 attempt 0에 X의 올바른 출력을 재생하고 새 요청을 보내지 않을 것으로 예상합니다(그러면 Y의 결과가 X의 판정을 따름). 수정 뒤에는 Y가 자기 'JSON 아님'을 재생하고, 새 attempt-1 요청을 정확히 하나 보내며, 그 출력도 약속을 어기면 '검증기 출력 오류'로 거부돼야 합니다. 보낸 요청 수와 Y의 마지막 이유를 확인합니다. 두 번째 검증 기록의 호출에 candidate_id가 있는지도 확인합니다. 이 테스트와 test_cli.py:221만 돌린 뒤 검사를 한 번 돌립니다.

## 결과

관측했지만 검증하지 않은 초안입니다. 실험은 `tests/golden/test_cli.py::test_resume_replays_a_pending_candidate_its_own_output_not_a_siblings_for_the_same_request`로 돌렸습니다.

준비:
- 제안과 달리 손으로 만든 중복 후보를 쓰지 않습니다. 테스트 plan p3의 판단용과 확인용 묶음이 예산 묶음의 이름표와 글을 복사하므로, `--part` 없는 B 실행은 검증기 요청의 SHA-256이 같은 예산 후보 세 개를 줍니다.
- `generation.WORKERS = 8`에서 그 요청을 처음 보내는 스레드가 미판정 후보 Y가 됩니다. attempt 0은 'JSON 아님'을 돌려주고, attempt 1은 `BudgetExceeded`를 냅니다.
- 형제 X 두 개는 Y가 재시도할 때까지 장벽(barrier)에서 기다리므로, X를 거부하는 올바른 E1 판정은 Y의 attempt 0 뒤에 기록됩니다.
- 처음에 `threading.get_ident()`만 쓴 시도는 결과가 들쭉날쭉했습니다. 풀의 스레드는 다시 쓰이고, Y가 오류를 낸 뒤 그 스레드가 형제를 집었습니다. 장벽은 두 형제가 도착할 때까지 Y의 스레드를 붙잡아 둡니다.

결과:
- a97eb96에 테스트를 더한 상태에서 `resume`은 요청을 0번 보냈습니다(`assert 0 == 1`). Y가 자기 'JSON 아님' 대신 형제의 올바른 출력을 재생했습니다. 가설이 확인됩니다.
- a97eb96 다음 커밋 "golden: replay settled validation outputs per candidate on resume"의 수정은 제안 그대로 구현합니다. `_reply`가 `candidate_id`를 기록하고, ask/judge는 `_judge_run`의 parallel 함수 안에서 후보마다 만들며, `_settled_calls`는 `last['pending']`에 대해서만 (candidate_id, request_sha256, attempt)별 FIFO deque를 만들고, `_reply`가 이를 순서대로 꺼냅니다.
- 수정 뒤: Y는 자기 'JSON 아님'을 재생하고, 새 attempt-1 요청을 정확히 하나 보내며, '검증기 출력 오류'로 거부됩니다. validation-2.json의 호출에는 `candidate_id`가 있고, Y의 것뿐입니다.
- `test_resuming_a_candidate_refused_mid_verdict_reuses_its_settled_calls`도 수정 뒤에 통과했지만, 테스트 정리 단계에서 지웠습니다. S5가 남기자고 한 것과 달리, 새 테스트가 같은 관측을 더 강하게 확인합니다. 이어하기가 후보 자신의 끝난 attempt 0을 다시 샀다면 요청을 1번이 아니라 2번 보냈을 것입니다.
- 리뷰 수정 중에는 작업 규칙상 디렉터리 전체 pytest가 금지돼 있어 전체 검사를 돌리지 않았습니다. 대신 영향받는 golden 테스트 파일을 돌렸고, 수는 커밋 메시지에 있습니다.

## 남은 한계

이 단계에서는 아무것도 돌리지 않았고(셸 없음), HEAD 실패는 코드를 읽어 예측했습니다. 5ec5266이 이미 쓴 검증 기록에는 candidate_id가 없습니다. 제안은 일부러 이에 대한 호환 경로를 더하지 않으므로(CLAUDE.md 1.1), 그 커밋에서 미판정으로 남은 실행은 이어할 때 호출을 다시 삽니다. outputs/ 아래에 그런 실행이 있는지는 확인하지 않았습니다. 순서 기반 재생은 _verdict의 호출 순서가 앞선 답과 고정한 입력에만 달려 있다고 가정합니다. 나중에 호출 순서가 고정되지 않은 무언가에 달리게 바뀌면(예: 호출 뒤에 survivors 확인) 이 가정이 깨집니다. 생성 쪽(1회차 위치)은 다시 확인하지 않았습니다. 생성은 거부된 묶음을 묶음별로 기록하고 재사용 캐시가 없기 때문입니다.
