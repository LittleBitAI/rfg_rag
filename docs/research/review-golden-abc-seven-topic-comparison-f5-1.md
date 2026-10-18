# Review research — F5, cycle 1

Draft research before the fix of review round 7 of PR #65, written 2026-10-18. It is not a verified fact or a shared rule: the review reads it with the fix.

## Problem

A recovery research page must analyse the finding it is filed under. It is the evidence the next fix and the review rely on. Twice in PR #65 a page was filed under one issue but analysed another. In round 2, review-golden-abc-seven-topic-comparison-f4-1.md was filed under F4 but analysed the F1 plan hash; round 3 raised it as F5. In round 6, review-golden-abc-seven-topic-comparison-f6-1.md was filed under F6 (the roleless settled calls counted against the resume cap) but analysed F2 (judgments.csv parsing); round 7 raised it as F5. Each time, the repeated finding was left without root-cause research written before its fix.

Trigger: backstop, rounds 7.

- [P1] [P1] docs/research/review-golden-abc-seven-topic-comparison-f6-1.md:7 — the F6 research analyzes F2 / when supplying the required re-analysis for the repeated resume-limit failure / the repair lacks valid root-cause evidence

## Failed fixes

- Round 3 correction (8326cee): added a 'Not F4 research' banner to f4-1.md (line 5) and relied on the new f4-2.md, which researched F4 directly. That repaired the bad output but not what produced it. The server's format-retry path in wiki-agent tool/main/recovery.py was not touched, so round 6 produced the same failure.
- Round 6 correction (f0ddd69): appended an 'F6 as raised' paragraph (f6-1.md line 144) after the fix was already made. That repeats the round-3 pattern: it records the result afterwards instead of supplying F6 research written before the fix. It also did not touch the retry path.

## Sources

### S1 — Using the Messages API — Multiple conversational turns (Anthropic docs)

- URL: https://platform.claude.com/docs/en/build-with-claude/working-with-messages
- Retrieved: 2026-10-18
- Locator: section 'Multiple conversational turns'
- Fragment: The Messages API is stateless, which means that you always send the full conversational history to the API. You can use this pattern to build up a conversation over time. Earlier conversational turns don't necessarily need to actually originate from Claude. You can use synthetic assistant messages.
- Applicability: A new research session for the retry starts with no earlier turns. The retry prompt must carry the finding and the rejected answer itself, which can be sent as earlier context.
- Counterevidence: It describes the raw API. The CLI can resume a stored session, but recovery.py never resumes one.
- Validation: After the fix, the second prompt contains the asked() text and the first answer, and the test asserts this.

### S2 — anthropics/claude-code issue #43696 (session resume not restoring context)

- URL: https://github.com/anthropics/claude-code/issues/43696
- Retrieved: 2026-10-18
- Locator: web search result summary; issue page not fetched
- Fragment: Per the search summary: a report from early April 2026 that the prior conversation context is not restored and the session starts fresh as if it were a new conversation; reporter on Windows 11 with git-bash; no workaround listed; whether it was resolved is not shown.
- Applicability: Argues against fixing the retry by reusing or resuming the session alone. Putting the context in the prompt does not depend on resume working.
- Counterevidence: Only a single report, read from a summary, and possibly fixed since.
- Validation: The chosen fix does not rely on resume, so this issue cannot affect it.

### S3 — Review research — F6, cycle 1

- URL: docs/research/review-golden-abc-seven-topic-comparison-f6-1.md
- Retrieved: 2026-10-18
- Locator: lines 7, 125, 140, 144, 148
- Fragment: line 125: 'I could not read the round-6 finding text in the repo. If the reviewer flagged something other than these three shapes (for example key.json), this hypothesis misses it.' line 140: 'This page analyses F2 (_human reading judgments.csv), not the round-6 F6 finding' line 148: 'The round-6 finding text was not available to me, so I derived these shapes by reading the code rather than from the reviewer's words.'
- Applicability: The page itself shows its writing turn never saw the F6 finding, although the original F6 prompt quoted it in full. The turn that wrote it had a different prompt from the first one.
- Counterevidence: The page does not say why the finding was unavailable. That comes from the transcript and recovery.py, outside this repo.
- Validation: After the retry fix, a forced format retry still produces a page about the issue it is filed under.

### S4 — Review research — F4, cycle 1

- URL: docs/research/review-golden-abc-seven-topic-comparison-f4-1.md
- Retrieved: 2026-10-18
- Locator: line 5 (banner), line 112 (Result)
- Fragment: line 5: 'Not F4 research (review round 3, F5). This page is filed under F4, but every section below analyses the review-packets plan hash: round-2 F1 ... Do not cite this page as grounds for any F4 fix.' line 112: 'This page's text researches the review-packets plan hash (round-2 F1), not the round-2 F4 finding it is listed under'
- Applicability: The first instance: the same switch to another issue, and the round-3 repair was only this banner on the page.
- Counterevidence: The banner shows the page was flagged correctly. The failure lies in what it left unchanged, not in what it did.
- Validation: With the retry fix, no new banner of this kind should be needed.

### S5 — Review research — F4, cycle 2

- URL: docs/research/review-golden-abc-seven-topic-comparison-f4-2.md
- Retrieved: 2026-10-18
- Locator: line 17 (Failed fixes, research process)
- Fragment: Research process: the cycle-1 page listed under F4 (docs/research/review-golden-abc-seven-topic-comparison-f4-1.md) actually researched the F1 plan-hash finding; its own Result section says so. The F4 replay key was designed without research, and nobody asked whether a content hash identifies a call.
- Applicability: Records the round-3 view of the misfiling as a lapse for that one page. It does not trace it to the server's retry, which is why it recurred.
- Counterevidence: This page is a correct first-try research turn, consistent with the hypothesis that only retries misfile.
- Validation: No change needed. It stays the F4 reference.

### S6 — Repository reflog

- URL: .git/logs/HEAD
- Retrieved: 2026-10-18
- Locator: lines 370-372 and 381-382
- Fragment: 370: 'docs: research F1 before fixing it again (cycle 1)' (291ed08); 371: 'docs: research F4 before fixing it again (cycle 1)' (9272eca), about 270 s later; 372: 'golden: tie review packets to the frozen plan and reuse settled validation calls on resume'; 381: 'docs: research F6 before fixing it again (cycle 1)' (9458840); 382: 'golden: count settled validator calls by rebuilt request, parse judgment files once before use' (f0ddd69).
- Applicability: The F1 page was the newest research commit when the F4 retry ran, which matches the retry copying F1. The F6 fix commit comes after the F6 research commit, which sets the timing for the analysis written before the fix.
- Counterevidence: Commit timing alone does not show what the model saw.
- Validation: Restoring the transcript line 43 analysis cites a time before f0ddd69 is committed.

## Claims

- C1 (source; S1): A model request has no memory of earlier turns. Each request must carry the context it needs.
- C2 (interpretation; S3, S4, S6): Both misfiled pages were written by a turn that did not have the finding it was filed under. Each analysed the most recent other finding on the branch.
- C3 (interpretation; S3, S4, S5): The round-3 and round-6 corrections changed only the research pages, not the server's retry, so the misfiling could recur.
- C4 (interpretation; S1): Building the retry prompt from the original asked() text plus the rejected answer and error removes the cause without depending on session reuse.
- C5 (interpretation; S2): Reusing or resuming the session alone is a weaker fix, because restoring a resumed session has had reported failures.
- C6 (interpretation; S6, S3): F6 research written before the fix exists, in the rejected first answer, and was written before fix commit f0ddd69. It can be restored to f6-1.md with stated provenance.

## Core theory

A model request without server-side state has no memory of earlier turns, so every request must carry the full context it needs. Anthropic's Messages API docs: 'The Messages API is stateless, which means that you always send the full conversational history to the API.' A new CLI session without --resume is the same: it starts with only the prompt it is given.

## Applicability

recovery.research() applies this correctly to the first attempt, whose prompt is the full asked() text, but not to the second. The retry gets a new ChatSession (wiki-agent tool/main/recovery.py:356, inside the loop at :346) and a prompt holding only the parse error (:413). planning.consume deliberately leaves the CLI session id out of the record, so nothing resumes it. The effect shows in this repository. f6-1.md line 125 says 'I could not read the round-6 finding text in the repo', and line 148 says 'The round-6 finding text was not available to me', even though the original F6 prompt quoted both rounds of the finding in full. f4-1.md's body reproduces the F1 analysis committed a minute earlier at 291ed08 (.git/logs/HEAD lines 370-371). Repairs made in this repository (banners, Result notes) cannot reach the cause, because the cause is in the wiki-agent server.

## Hypothesis

The format retry in wiki-agent tool/main/recovery.py research() runs in a new session and sends no finding. The loop at line 346 builds a new ChatSession on every attempt (line 356). After read() rejects the first answer, the retry prompt (line 413) is only 'Your answer could not be read: <error> ... Answer again'. The new session has no history, so it never sees the finding. It picks the most recent recurring finding it can find in the repository, and read() checks only the format, so that page is written under the active issue key. Evidence from the task transcript (wiki-agent raw/work/rfg_rag/golden-abc-seven-topic-comparison.jsonl): F4 round 2 — the first answer (line 21, cell b976...) analysed F4 and was rejected because sources.validation was empty (line 22); the retry (line 23, cell b5d3...) analysed F1. F6 round 6 — the first answer (line 43, cell e8e0...) analysed F6 and was rejected because S5 was a hub-wiki path outside the repo (line 44); the retry (line 45, cell ae2c...) analysed F2 and says it could not find the round-6 finding. Every research turn that passed on the first try matched its issue: F1 round 2 (line 19), F4 cycle 2 (line 29) and F2 cycle 1 (line 37). Fix: build the retry prompt from the original asked() text, the rejected answer and the error, for example text = f'{asked(spec, key, s)}\n\nYour answer below could not be read: {exc}. Return the same research with only that corrected, ending with exactly the recovery-research block.\n\n{final}'. Then the retry has the finding and its own first answer, whether or not the session is reused.

## Counterevidence

- Only two retries have occurred, and both misfiled (2 of 2). Three research turns that passed on the first try all matched their issue. The pattern is consistent but the sample is small.
- The new session's SessionStart hook lists every research page and recent decision. That may explain which wrong finding the model picked (the most recent page on this branch), but not why it lacked the right one.
- With the finding restored, a model could still drift in principle. read() still does not check that the answer is about the issue. If drift continued after the retry fix, a subject check would be needed.
- The F4 retry (line 23) says it 're-checked the code at HEAD (291ed08)'. That fits a model that cannot see the finding and falls back to the newest research commit. It is still an inference about the model's behaviour, not something the host recorded.

## Alternatives

- Reuse the same ChatSession for the retry (create it before the loop). This keeps context and prompt cache, but the per-attempt timer, run and close must be restructured. Resuming a CLI session has had reported failures to restore context (claude-code issue #43696), so passing the context explicitly is more robust. A reasonable second choice.
- Add a server check that the answer names the finding's file or line (for example validation.py:110). This is a heuristic that can wrongly reject valid research. It may be added later as a guard, not as the fix.
- Loosen the source-format checks so retries happen less often. That lowers how often it happens but leaves the fault in place. Rejected.
- Keep repairing pages in rfg_rag (banners, Result notes), as rounds 3 and 6 did. It has already failed once. Necessary for the current artifact, but not sufficient.
- In this repo, besides the server fix: mark f6-1.md as misfiled, like f4-1.md line 5, and record the F6 analysis written before the fix. That analysis is the first F6 answer at transcript line 43, timestamp 1792283995, before fix commit f0ddd69 at 1792284592. It was rejected only for the non-repo S5 path, and its hypothesis (count prepaid by rebuilding validator requests and matching their SHA-256 to the replay map) is what f0ddd69 implemented. That gives the reviewer F6 research written before the fix, with stated provenance. Also add the negative case it proposed: a roleless record whose only saved attempt-0 call is a judge call must not lower the count.

## Experiment

In wiki-agent tool/test_recovery.py, patch recovery.ChatSession with a Host that records each prompt. Its first reply ends with a recovery-research block whose S2 url is a path outside the repository, so read() rejects it; its second reply is valid. Run prepared() for one F1 repeat trigger. Assert that the second recorded prompt contains 'Review research for issue `F1`' and the finding head from the trigger round. On current code the second prompt is only the error text, so the test fails. After the retry text is built from asked() plus the rejected answer, it passes. A check against past runs is already done: transcript lines 20-23 and 42-45 show the issue switching exactly at the retry, with different cell ids.

## Result

Ran the experiment as a scratch test outside both repositories (`test_the_format_retry_prompt_carries_the_finding`). It imports wiki-agent `tool/test_recovery.py` read-only (wiki-agent at `f7b4bdf`, its worktree left clean), with `recovery.ChatSession` patched to its `Host`. The first reply's S1 url was `C:/outside/the/repo.md`, and the second reply was valid; `prepared()` ran for one F1 repeat trigger. Observed: two sessions with different ids. Prompt 1 began "Review research for issue `F1` (repeat, rounds [1, 2]), cycle 1 of 2" and quoted the finding. Prompt 2 was only "Your answer could not be read: 출처 `S1` 는 URL 도 저장소의 파일도 아니다: C:/outside/the/repo.md / Answer again, ending with exactly the `recovery-research` block." The assertion that the second prompt carries the issue and the finding failed, as predicted. The page was still accepted (phase `fixing`), so nothing checks that the retry's subject matches the issue. The transcript agrees: line 44 is the F6 retry prompt holding only the error, and line 45 is a new cell. The hypothesis holds on current code.

The cause and its fix are in wiki-agent `tool/main/recovery.py` (lines 356 and 413), outside this task's repository, and were not changed here. In this repository: `review-golden-abc-seven-topic-comparison-f6-1.md` now carries a misfiled banner, as `f4-1.md` does. Its F6 research written before the fix is restored from transcript line 43 (ts 1792283995, before `9458840` and `f0ddd69`), with provenance. Two follow-ups from that research are done: the negative judge-call test `tests/golden/test_validation.py::test_a_settled_judge_call_does_not_count_as_a_paid_validator_call`, and shared `validation._single_units` so the counted and sent requests cannot drift. Results are in the commit that carries this page. Until recovery.py builds the retry from `asked()` plus the rejected answer, a format retry can misfile again.

## Unresolved limits

The cause and the proposed fix are in wiki-agent (tool/main/recovery.py), which is outside this task's repository. The fix turn for rfg_rag cannot change it without the person's permission, and the server's research checks only accept URLs and this repository's files as sources. So recovery.py and the transcript are cited in the text, not as sources. Nothing was run (no shell). The two retry cases are confirmed from the transcript, but no test reproduces them yet. Whether a reviewer will accept the restored F6 first answer as research written before the fix, given that it appears in a page edited after the fix, is a judgement for the review.
