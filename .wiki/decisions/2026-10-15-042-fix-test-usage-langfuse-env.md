---
scope: project
severity: preference
triggers: []
domain: ''
title: "tests: Run all tests without Langfuse key"
pr: 42
merged: 2026-10-15
branch: "fix/test-usage-langfuse-env"
---

# tests: Run all tests without Langfuse key

What. \`tests/conftest.py\`: The autouse fixture leaves \`LANGFUSE_PUBLIC_KEY\` and \`LANGFUSE_SECRET_KEY\` empty in all tests. \`load_dotenv\` does not overwrite existing environment variables, so the key is not restored. - \`tests/test_usage.py\`: Removed the loop that cleared the key in RAGAS evaluation tests. The fixture handles it instead, and that loop actually \`. …

Why. If you run the entire gate on a PC with a Langfuse key in \`.env\`, 3 \`test_answer_flow_preserves_original_question_without_langfuse_keys\` of \`tests/test_rewrite.py\` fail. The \`trace_id is None\` check breaks. When tests in \`test_usage.py\` call \`load_config()\`, \`load_dotenv\` puts the actual Langfuse key of \`.env\` into the environment variable. This remains true even after clearing the key in the test. The Langfuse client created in that state remains in the process. Therefore, subsequent tests receive an actual trace id. …

Source. PR #42 · `fix/test-usage-langfuse-env`
