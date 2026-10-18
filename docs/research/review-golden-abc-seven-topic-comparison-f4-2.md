# Review research — F4, cycle 2

Draft research before the fix of review round 3 of PR #65, written 2026-10-18. It is not a verified fact or a shared rule: the review reads it with the fix.

## Problem

Invariant: every paid call that settled before a ledger refusal (BudgetExceeded) is kept exactly. On resume, the candidate that made a call gets back that call's own output; nothing is bought twice and no other call's output is used in its place. At 5ec5266, resume_validation (golden_pipeline/validation.py:90-91) builds `settled` as a dict keyed only by (request_sha256, attempt). It reads calls from every validation record and every candidate, including candidates already decided. `_reply` (validation.py:955-957) looks outputs up by that content hash. Two different logical calls with the same messages share one key, and the dict comprehension keeps whichever came last. Example: two candidates with the same question and the same evidence labels and text but different refs, or the identical judge request a multi_hop candidate can send twice. A pending candidate can then replay a sibling's output, which changes whether it retries and how it is judged.

Trigger: repeat, rounds 2, 3.

- [P1] [P1] golden_pipeline/validation.py:90 — 동일 요청의 정산 결과가 하나로 합쳐져 재개 시 다른 후보의 응답을 재사용함

## Failed fixes

- Round 1 (89f54e6): generation.parallel (generation.py:449-460) catches BudgetExceeded per item and returns None for that item only, so settled sibling verdicts survive. It did not hold because one _verdict makes several sequential calls (validator retry, document batches, multi_hop single-unit checks, judge). A refusal partway through still threw away that candidate's earlier settled outputs; only their token rows stayed in `calls`. That was the round-2 finding.
- Round 2 (60b911a/5ec5266): _reply writes request_sha256, attempt and text into each call record; resume_validation gathers them into `settled` and _reply reuses a match instead of calling again. It did not hold because the key is the content of the request, not which call it was. No candidate_id is recorded, calls from non-pending (already decided) candidates are offered, and duplicate keys collapse into one entry. The fix's test (tests/golden/test_cli.py:221) has a single interrupted candidate and no duplicate requests, so a collision can never happen in it.
- Research process: the cycle-1 page listed under F4 (docs/research/review-golden-abc-seven-topic-comparison-f4-1.md) actually researched the F1 plan-hash finding; its own Result section says so. The F4 replay key was designed without research, and nobody asked whether a content hash identifies a call.

## Sources

### S1 — Event History walkthrough with the Python SDK (Temporal docs)

- URL: https://docs.temporal.io/encyclopedia/event-history/event-history-python
- Retrieved: 2026-10-18
- Locator: Replay / non-determinism sections
- Fragment: The Worker must "produce a set of Commands which is compared against the sequence of Commands in the Event History." A Command proceeds when it is "the right type of Command and it occurs at the right position in the expected sequence, so Replay proceeds." On mismatch: "That is not the Command it expected at this position in the sequence", and the execution "cannot be replayed". Condition: a Workflow Definition is deterministic if it "produces the same Commands in the same sequence given the same input"; calls to external systems belong in Activities, which may be non-deterministic, and their results come from the history on replay.
- Applicability: Each candidate's _verdict plays the role of a workflow and each _reply API call the role of an Activity. Recorded outputs should be matched to that candidate's calls by order, not looked up globally by request content.
- Counterevidence: Temporal records one history per execution and matches by position. golden_pipeline has no per-candidate history today and would need candidate_id added. Temporal also matches command types; this proposal matches request hashes within one candidate.
- Validation: After the fix, resume gives each pending candidate only its own recorded outputs in call order. The new test shows Y gets its own attempt-0 output, not X's.

### S2 — Idempotent requests (Stripe API reference)

- URL: https://docs.stripe.com/api/idempotent_requests.md
- Retrieved: 2026-10-18
- Locator: paragraphs on key generation and parameter comparison
- Fragment: "A client generates an idempotency key, which is a unique key that the server uses to recognize subsequent retries of the same request. How you create unique keys is up to you, but we suggest using V4 UUIDs, or another random string with enough entropy to avoid collisions." "For API v1, Stripe saves the status code and body of the first request made with a given idempotency key after endpoint execution begins. Retries with the same key return the saved response, including 500 errors." "The idempotency layer compares incoming parameters to those of the original request and errors if they're not the same to prevent accidental misuse." Limits: results are saved only after endpoint execution begins; keys may be pruned after 24 hours, after which reuse creates a new request.
- Applicability: The key that brings back a saved result has to name one operation (here: a candidate's call). Request parameters, here the request_sha256, serve only as a guard, never as the identity.
- Counterevidence: Stripe deals with client retries of one HTTP request across network failures, not with replaying a multi-call computation. Only the principle that a key names one operation and parameters are a guard carries over.
- Validation: After the fix, the lookup includes candidate_id, and the request hash only selects within that candidate's own calls.

### S3 — golden_pipeline/validation.py (resume_validation, _judge_run, _reply)

- URL: golden_pipeline/validation.py
- Retrieved: 2026-10-18
- Locator: lines 87-92, 114-116, 129-130, 947-974
- Fragment: `settled = {(call["request_sha256"], call["attempt"]): call["text"] for path in storage.validation_records(run_dir) for call in storage._read_json(path)["calls"] if "text" in call}`; `ask = _asker(client, config, ..., calls, settled)` built once for all candidates; `_reply`: `request = hashlib.sha256(json.dumps(messages, ...)).hexdigest()` ... `text = settled.get((request, attempt))`; call records hold question, labels, model, tokens, request_sha256, attempt, text, and no candidate_id.
- Applicability: Shows the content-addressed key, the lack of a candidate filter (calls from decided candidates are offered too) and the overwrite on duplicate keys: the exact site of the round-3 finding.
- Counterevidence: `pending` (line 87) is already computed and could filter, but the calls carry no candidate_id to filter on.
- Validation: After the fix, calls carry candidate_id, settled is built only for pending ids as FIFO lists, and ask/judge are built per candidate.

### S4 — golden_pipeline/generation.py module docstring and parallel()

- URL: golden_pipeline/generation.py
- Retrieved: 2026-10-18
- Locator: lines 4-5; 449-460
- Fragment: "LLM 출력은 같은 입력에도 달라질 수 있어 결정성을 주장하지 않는다." (LLM output can differ for the same input, so determinism is not claimed.) parallel: "실험 장부가 어느 호출을 거절하면 그 자리만 None 이다. 함께 보낸 다른 호출은 이미 정산됐으므로 그 결과를 버리지 않는다." (When the ledger refuses a call, only that slot is None; the other calls sent with it are already settled, so their results are not thrown away.)
- Applicability: Two identical requests are two distinct paid results, so request equality cannot stand in for result identity. parallel runs each candidate's _verdict on its own worker, so a per-candidate queue is popped by one thread only.
- Counterevidence: None for the identity point. Thread safety of the shared `calls` list relies on CPython's atomic list.append, which the code already relies on.
- Validation: The new test gives the two candidates different outputs for the identical request and checks each gets its own.

### S5 — tests/golden/test_cli.py round-2 F4 test

- URL: tests/golden/test_cli.py
- Retrieved: 2026-10-18
- Locator: test_resuming_a_candidate_refused_mid_verdict_reuses_its_settled_calls, lines 221-244
- Fragment: Only the bond ('보증금') candidate is intercepted; `sent` counts its requests; call 2 raises BudgetExceeded; `assert len(sent) == 3`.
- Applicability: Exercises one interrupted candidate with unique requests, so the content key never collides. It cannot detect the round-3 defect.
- Counterevidence: It correctly guards the round-2 behaviour (no re-buying the candidate's own settled call) and should stay.
- Validation: The new collision test fails on HEAD and passes after the fix; this test keeps passing.

### S6 — Cycle-1 research page listed under F4

- URL: docs/research/review-golden-abc-seven-topic-comparison-f4-1.md
- Retrieved: 2026-10-18
- Locator: Problem, Hypothesis, Result sections
- Fragment: Result: "This page's text researches the review-packets plan hash (round-2 F1), not the round-2 F4 finding it is listed under (sub-call results lost inside one candidate's verdict)."
- Applicability: Explains why the round-2 F4 fix got no design review of its replay key.
- Counterevidence: The page's Result section did describe the F4 fix and its test; it just did not examine the key's identity.
- Validation: This cycle's page targets F4 directly.

## Claims

- C1 (source; S1): Recorded results of external calls can be replayed safely only when each is matched to the call that produced it by its position in a deterministic execution; a mismatch at a position means the history cannot be replayed.
- C2 (source; S2, S4): The key that returns a saved result must name one operation; parameter equality is only a guard against misuse, and identical inputs to an LLM can yield different paid results.
- C3 (source; S3): At 5ec5266 the resume replay key is (request_sha256, attempt) gathered from all candidates of all records, with no candidate id, so duplicate keys collapse to the last one written.
- C4 (interpretation; S1, S4, S3): Because one candidate's _verdict runs sequentially on one worker and its call sequence depends only on prior replies and pinned inputs, popping a per-(candidate, request, attempt) FIFO queue reproduces each call's own output exactly.
- C5 (interpretation; S3): Calls belonging to candidates already decided in earlier records should not be offered on resume; filtering by last['pending'] requires candidate_id on each call.
- C6 (source; S5): The round-2 test has a single interrupted candidate with unique requests and so could not detect a key collision.
- C7 (source; S6): The round-2 F4 fix was designed without research on its replay key, because the cycle-1 F4 page researched the F1 plan-hash finding instead.

## Core theory

Replaying recorded results of side-effecting calls is safe only when each result is matched to the call that produced it: the call's position in one deterministic execution, or a key that names one operation. Temporal checks each command on replay by its type and its position in the recorded sequence; a command at the wrong position cannot be replayed. Stripe has the client generate a unique key per operation (UUID), saves the first result under that key, and compares parameters only to catch misuse. Matching parameters do not make two requests the same operation.

## Applicability

A candidate's _verdict (validation.py:512-528, 610-671) is a sequential execution whose branches depend only on replies already received. The static checks that depend on `survivors` run before any call, and plan/prompt/model/price are pinned by the plan check and by the criteria check in resume_validation:76-81. So the n-th call of one candidate is reproducible, and replaying by (candidate, request, attempt) in order gives each call its own settled output. The places to change are _reply (validation.py:947-974: add candidate_id, pop from the per-candidate queue), _asker/_judger (927-944: take the candidate id and its queue), _judge_run (115-116, 129-130: build ask/judge per item inside the lambda) and resume_validation (90-91: filter by last['pending'], build lists instead of a dict overwrite). validate() and release still pass an empty `settled`.

## Hypothesis

The replay cache is keyed by what was sent (request hash + attempt) instead of which call sent it (candidate + its order within the candidate's verdict). Different calls that happen to send the same request overwrite each other, and calls from candidates that are already decided are still offered. Fix: (1) _reply records `candidate_id` in each call; (2) ask/judge are built per candidate inside the parallel lambda, so _reply knows its candidate; (3) resume_validation builds, for candidates in last['pending'] only, a FIFO list of outputs per (candidate_id, request_sha256, attempt), in record order and in call order within each record; (4) _reply pops the front entry for its key and calls the API only when the list is empty. One candidate's calls run on one thread in sequence, so popping in order hands each identical request back its own output. Replayed outputs are still not re-appended to `calls`, so a third record lines up with the queues and costs are not counted twice.

## Counterevidence

- If the LLM always returned the same output for the same request, the collision would only re-use an equivalent result. But generation.py:4 says outputs can differ for the same input, and the sibling's output is a different paid call, so the invariant still fails.
- The sibling's output is a real settled response to the identical request, so it could be argued to be a valid sample. It still makes the pending candidate's verdict depend on a sibling and on thread completion order, and the pending candidate's own settled output is lost.
- Whether the within-candidate duplicate (two identical judge requests in one multi_hop candidate) happens on real data is untested. The cross-candidate case raised in round 3 is enough on its own to motivate the fix.

## Alternatives

- Key by (candidate_id, request_sha256, attempt) with a plain dict: fixes the cross-candidate collision with the smallest diff, but leaves identical requests within one candidate overwriting each other. FIFO lists cost one more line and cover both cases.
- Key by (candidate_id, ordinal), where the ordinal counts calls within the candidate, with request_sha256 kept as a guard (the Temporal model): equally exact, but needs a counter shared by ask and judge and carried across records. More moving parts than FIFO popping for the same guarantee here.
- Drop replay and charge the re-run: breaks the F4 invariant (settled calls are bought again, and near the ceiling a re-run may not fit). Rejected.
- Store each pending candidate's partial verdict state instead of raw call outputs: needs a resumable form for every branch of _verdict. Larger change than replaying calls. Not first.

## Experiment

Add one test next to tests/golden/test_cli.py:221, reusing the planned/api fixtures. Make two numeric candidates in one B run with the same question and the same evidence labels and text but different refs, so their validator requests have the same SHA-256. Set generation.WORKERS = 1 and order them so the candidate that will end up pending (Y) comes before the sibling (X); then Y's call record is written first and X's overwrites it on HEAD. Fake client: Y attempt 0 -> 'JSON 아님'; Y attempt 1 -> raise BudgetExceeded; X attempt 0 -> a valid verdict that rejects X. Run audit, then resume. On HEAD, expect resume to replay X's valid output for Y at attempt 0 and send no new request (Y's result then follows X's verdict). After the fix, Y replays its own 'JSON 아님', sends exactly one new attempt-1 request, and ends rejected with '검증기 출력 오류' if that output also breaks the contract. Assert the count of sent requests and Y's final reason. Also assert that the second validation record's calls carry candidate_id. Run only this test plus test_cli.py:221, then the gate once.

## Result

Observed, not verified (draft). The experiment ran as `tests/golden/test_cli.py::test_resume_replays_a_pending_candidate_its_own_output_not_a_siblings_for_the_same_request`.

Setup:
- Unlike the proposal, it uses no hand-made duplicate candidates. Fixture plan p3's validation and held-out bundles copy the budget bundle's labels and text, so a B run without `--part` gives three budget candidates whose validator requests have the same SHA-256.
- With `generation.WORKERS = 8`, the first thread to send that request becomes the pending candidate Y: attempt 0 returns 'JSON 아님', attempt 1 raises `BudgetExceeded`.
- The two siblings X wait on a barrier until Y has retried, so their valid E1 verdicts (which reject X) are recorded after Y's attempt 0.
- A first try with `threading.get_ident()` alone was flaky. Pool threads are reused, and after Y raised its thread picked up a sibling. The barrier keeps Y's thread busy until both siblings have arrived.

Results:
- On a97eb96 plus the test, `resume` sent 0 requests (`assert 0 == 1`): Y replayed a sibling's valid output instead of its own 'JSON 아님'. That confirms the hypothesis.
- The fix, in the commit after a97eb96 titled "golden: replay settled validation outputs per candidate on resume", implements the proposal as written. `_reply` records `candidate_id`. ask/judge are built per candidate inside `_judge_run`'s parallel function. `_settled_calls` builds FIFO deques per (candidate_id, request_sha256, attempt) for `last['pending']` only, and `_reply` pops them in order.
- After the fix: Y replays its own 'JSON 아님', sends exactly one new attempt-1 request, and ends rejected with '검증기 출력 오류'. The calls in validation-2.json carry `candidate_id`, and only Y's.
- `test_resuming_a_candidate_refused_mid_verdict_reuses_its_settled_calls` passed after the fix too, but the test-cleanup pass then removed it. Unlike S5's suggestion to keep it, the new test asserts the same observation more strongly: had resume re-bought the candidate's own settled attempt 0, it would have sent 2 requests instead of 1.
- The full gate was not run, because the task rules forbid whole-directory pytest during review repairs. The affected golden test files were run instead; their counts are in the commit message.

## Unresolved limits

Nothing was run in this turn (no shell); the HEAD failure is predicted from reading the code. Validation records already written by 5ec5266 have no candidate_id. The proposal deliberately adds no compatibility path for them (CLAUDE.md 1.1), so a pending run from that commit would re-buy its calls on resume; whether any such run exists under outputs/ was not checked. The order-based replay assumes _verdict's call sequence depends only on earlier replies plus pinned inputs; a future change that makes the call order depend on something not pinned (for example, survivors checked after a call) would break this. The generation side (round-1 site) was not re-checked, because generation records refused bundles per bundle and has no replay cache.
