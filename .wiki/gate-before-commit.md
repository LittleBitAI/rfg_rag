---
scope: project
severity: contract
repeat: rule
triggers: ['커밋', '(?i)\bcommit', '게이트', '(?i)\bgate\b', '(?i)pytest', '(?i)\bruff\b', '(?i)AGENTS\.md', '(?i)CLAUDE\.md', '복잡도']
slots: []
sources: ['CLAUDE.md#L179', '.wiki/adapter.toml#L4', 'pyproject.toml#L1']
links: []
---

# Before every commit: ruff clean, the pytest gate passes, CLAUDE.md and AGENTS.md identical

Rule. Before each commit run three checks from the repository root and fix
what they report. `ruff check .` must report nothing; a function over C901 8
or PLR0915 50 is split or simplified, never silenced with `noqa` or a raised
limit. The gate `.venv\Scripts\python -m pytest -q tests` (Linux:
`.venv/bin/python -m pytest -q tests`) must pass, using the Python 3.10 `.venv`
from `README.md`. `git diff --no-index CLAUDE.md AGENTS.md` must print
nothing: edit one, copy it over the other. While working, run only the
affected test files; the full gate is the pre-commit check.

Why. `CLAUDE.md` section 6 makes these the commit conditions, and section 1.3
exists because the previous repository became too complex to work in. The
gate is the server's repository gate too (`.wiki/adapter.toml` `gate_cmd`).
Run it as `python -m pytest` from the root: tests import `rag`, `tools` and
sibling test modules through the root on `sys.path`.

What goes wrong. A commit that skips ruff lets complexity grow back; a
diverged `AGENTS.md` gives Codex different rules from Claude; a gate run with
another interpreter misses the pinned packages and fails `tests/test_smoke.py`.
