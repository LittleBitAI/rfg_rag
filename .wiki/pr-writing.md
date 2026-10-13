---
scope: project
severity: contract
repeat: rule
triggers: ['(?i)\bpr(?=$|[\W가-힣])', '(?i)pull request', '풀 리퀘스트', '풀리퀘스트']
sources: ['https://github.com/LittleBitAI/rfg_rag/pull/11']
links: []
---

# Pull requests explain the reason, the change, and the proof

Rule. Write every PR description so a teammate can understand why the change
is needed, what behavior changes, and how it was verified without reading the
chat. Use the sections `요약`, `변경 이유`, `변경 내용`, and `검증`; include
concrete before-and-after examples, the purpose of each changed file, actual
check results, and material verification limits. Keep the description current
when the scope changes. A feature list and a passing test count alone are not
enough.

## Why this rule exists

The first description of PR #11 listed parser features and said that 97 tests
passed. The person had to ask again for a detailed, readable explanation of
the reason, the changes, and the verification. A teammate needs to understand
how the old matching behavior distorted evaluation scores and what the tests
actually establish. Recording the checks without that explanation leaves the
reviewer to reconstruct the task from code or chat.

## What each section must explain

| Section | Required content |
| --- | --- |
| `요약` | The concrete problem and resulting behavior, in a short paragraph. |
| `변경 이유` | The old behavior, its cause, its effect on users or scores, and why the chosen approach fits. Record meaningful decisions and rejected alternatives when they explain the change. |
| `변경 내용` | Observable before-and-after examples and the purpose of each changed file. Explain implementation details only where they help assess correctness. |
| `검증` | The commands actually run, their results, and the behavior each test group guards. Explain integration evidence separately from parser evidence. |
| `범위와 한계`, when relevant | The supported forms, intentionally excluded work, checks not performed, and warnings or risks that affect interpretation of the evidence. |
| `테스트 정리`, when relevant | What redundant or obsolete tests were removed or folded, why, and which current behavior remains guarded. |

Use Korean for the published PR prose, following this repository's language
rules. Keep code, paths, commands, and metric names literal. Use tables for
examples and comparisons, paragraphs for the reason, and headings for real
sections. Avoid repeated bold labels and unexplained jargon. The detail should
make the change easier to understand rather than lengthen a generic template.

## Before publishing or updating

1. Read the final diff and the actual check output. Replace abandoned plans
   with the implemented behavior; do not claim evidence that was not run.
2. Write the reason and at least one concrete behavior example for a behavior
   change. For documentation changes, explain who follows the rule and why.
3. Explain what the checks prove and what they leave unmeasured. A unit test
   result cannot establish a real dataset's score improvement.
4. Update the existing branch PR with `gh`, using a UTF-8 without BOM body
   file passed through `--body-file` to preserve Markdown and real newlines.
5. Fetch the saved PR body and check that the reason, changes, verification,
   examples, and limits survived publication.

This page is a repository rule for coding agents. Keep it in the root of
`.wiki/`, where the project's wiki loader discovers rule pages, and commit
changes to it with the task that established or revised the rule.
