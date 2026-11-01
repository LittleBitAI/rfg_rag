---
scope: project
severity: landmine
repeat: rule
triggers: ['(?i)langfuse', '랑퓨즈', '(?i)conftest', '(?i)trace_id', '추적', '(?i)\.env\b', '(?i)load_dotenv']
slots: []
sources: ['https://github.com/LittleBitAI/rfg_rag/pull/42', 'commit 13a1574', 'tests/conftest.py#L12', 'rag/config.py#L17']
links: []
---

# Every code path and every test runs without Langfuse keys; tests blank them, never delete them

Rule. Team members have no Langfuse keys, so no code path may require them:
tracing turns off unless both keys are set (`rag/config.py:19-20`) and scores
go only to rows with a `trace_id`. In tests, keep the autouse fixture in
`tests/conftest.py` that sets `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`
to empty strings and `LANGFUSE_TRACING_ENABLED=false`. Never make a test
delete those variables with `delenv`, and never let a test build a Langfuse
client from the real `.env`.

Why. `load_config` calls `load_dotenv`, which refilled the real keys from
`.env` after a test deleted them. A Langfuse client built with the real keys
then stayed in the process, and `test_rewrite`'s `trace_id` checks failed on
every machine whose `.env` held Langfuse keys (commit 13a1574, PR #42).
`load_dotenv` does not overwrite an existing variable, so empty strings hold.

What goes wrong. The gate passes for teammates and fails for the owner, or
tests send traces to Langfuse Cloud from a developer machine.
