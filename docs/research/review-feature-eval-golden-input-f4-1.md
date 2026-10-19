# Review research — F4, cycle 1

집계 결과와 측정 조건은 Git에 보관하고, 원시 질문·정답·근거·OCR 전사와 레코드별 내보내기는 무시된 로컬 `artifacts/`에 보관한다.

편집 주의: 실제 자료에서 복사한 질문·답·근거 문구는 제거했다. 아래 합성 예제는 이번 문서 수정을 위해 독립적으로 작성했으며 실제 릴리스의 대체 기록이 아니다. 기존 집계 수치·실험 조건·한계는 당시 기록을 유지한다.

복원 출처: 정리 전 `artifacts/review-round2/originals/` 또는 `d7d1682^`. 아래 수치와 검증 기록은 당시 실행의 역사적 관측이며 이번 작업에서 재측정한 결과가 아니다.

Draft research before the fix of review round 3 of PR #48, written 2026-10-15. It is not a verified fact or a shared rule: the review reads it with the fix.

## Problem

F4(반복, 2·3라운드)는 다중 근거 질문이 요구하는 일부 사실을 추출기가 누락하여 불완전한 답에 만점을 주던 문제다. 당시 393행은 한 필수 항목과 네 개의 세부 항목을 요구했으나 추출 결과에는 한 항목만 남았다. 실제 질문·답·근거 문장은 게시하지 않고 아래 S6의 합성 예제로 구조를 설명한다.

Trigger: repeat, rounds 2, 3.

- [P1] [P1] rag/validation/validation.py:53 — Whole-cell matching still discards requested multi-hop facts

## Failed fixes

- Round 1 fix (d763d41): 근거 문장 전체 대신 답에 포함된 표 칸을 핵심 사실로 고르고 첫 칸을 모두 필드명으로 제외했다. 그러나 첫 칸에 답의 식별자가 있는 경우도 있어 필요한 값이 사라졌다. 원래 식별자 문자열은 게시하지 않는다.
- Round 2 fix (617bc3b): 첫 칸이 3개 이상 문서에서 반복될 때만 필드명으로 처리하고 맨 수는 `N|N<unit>`로 표현했다. 333·335·336행은 고쳤으나 통째 칸 일치가 남았다. 393행의 한 칸은 제목 2개와 세부 항목 7개를 담았고 답이 인용한 4개 항목을 각각 추출하지 못했다.
- In both rounds the guarding test (tests/test_eval_items.py:48-50) only checked precision: each surviving fact is found in the row's context. It pinned the exact rows the reviewer had named (270, 333, 335, 336, 362) and never checked that the facts cover the answer's content. So each fix passed the gate while a different row still lost requested facts.

## Sources

### S1 — Initial Nugget Evaluation Results for the TREC 2024 RAG Track with the AutoNuggetizer Framework

- URL: https://arxiv.org/html/2411.09607v1
- Retrieved: 2026-10-15
- Locator: nugget definition and scoring sections
- Fragment: Quoting Voorhees (2003): 'An information nugget was defined as a fact for which the assessor could make a binary decision'; 'nuggets manifest as short natural language phrases or sentences'; 'We aim to generate nuggets that are neither too broad nor too specific.' Scores are averages over nuggets: full support 1, partial 0.5, else 0. Caveats: automatic filtering 'usually trims a few okay nuggets and, less frequently, some vital nuggets'; hallucinations are not considered; results rest on 21 topics, and topic-level agreement with manual scores is weaker than run-level.
- Applicability: Key facts in rag/validation play the role of vital nuggets: each must be judgeable as present or absent on its own, at a grain no coarser than the facts the answer states.
- Counterevidence: Nugget assignment there is done by an LLM that judges meaning, with partial credit. The repo's matcher is literal and binary, so verbatim quotation matters more here than in the source.
- Validation: 당시 회귀는 요청한 5개 사실 중 단일 사실만 있는 답이 1.0이 아닌 0.2를 받는지 점검했다. 실제 답 문자열 대신 S6의 합성 항목으로 이 비율을 설명한다.

### S2 — FActScore: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text Generation (Min et al., EMNLP 2023)

- URL: https://arxiv.org/abs/2305.14251
- Retrieved: 2026-10-15
- Locator: Abstract
- Fragment: Generations 'often contain a mixture of supported and unsupported pieces of information, making binary judgments of quality inadequate'; FActScore 'breaks a generation into a series of atomic facts' and computes the percentage supported by a reliable knowledge source. The decomposition is done by an LLM and the paper's setting is biographies checked against Wikipedia.
- Applicability: A table cell that holds a bulleted list is a 'mixture' unit: the answer contains some of its items and not others, so judging the whole cell at once (keep or drop) fails the same way a binary judgment of a whole passage does.
- Counterevidence: FActScore measures precision of generated text, not recall of reference facts, and uses LLM decomposition, not rule-based splitting. It supports the granularity principle, not the specific line-split rule.
- Validation: The fix is confirmed if splitting cells into items gives facts that each match one bullet in row 393's context (_key_fact_ratio(facts, context) == 1) and the answer (== 1), while a partial answer scores below 1.

### S3 — rag/validation/validation.py at 7a71cdf

- URL: rag/validation/validation.py
- Retrieved: 2026-10-15
- Locator: _cells lines 21-24; _multi_hop_key_facts lines 47-56
- Fragment: _cells splits each evidence unit on ' | ' and _squash collapses all whitespace including newlines. _multi_hop_key_facts builds values = {cell ...} - field_names, then keeps v only if 'len(v) > 1 and v in answer and v not in question', and drops any value contained in another found value.
- Applicability: This is where the cell is fixed as the fact unit, and where newlines that mark bullet items are lost before any split could use them.
- Counterevidence: The whole-cell rule is correct for single-value cells (IDs, names, numbers), which most rows have, and the F1/F2/F3/F5 fixes rely on it. The split must reduce to the same result for single-line cells.
- Validation: The pinned rows 270, 333, 335, 336 and 362 in tests/test_eval_items.py still pass after the split, and row 393 gains the four bullet facts.

### S4 — rag/evaluation/evaluation.py key-fact matcher

- URL: rag/evaluation/evaluation.py
- Retrieved: 2026-10-15
- Locator: _fact_matches lines 154-161; _key_fact_ratio lines 164-168
- Fragment: _key_fact_ratio returns the share of facts for which any '|' alternative matches as a contiguous pattern in the canonicalised text (whitespace and commas removed, numbers and dates tokenised), unless the match is negated.
- Applicability: Each key fact must be one contiguous span in one text, so facts must be no larger than what a single evidence unit or answer states contiguously.
- Counterevidence: Removing whitespace makes matching somewhat lenient, so slightly different spacing between context and answer bullets still matches. This argues that line splitting is enough for verbatim-quoted bullets.
- Validation: _key_fact_ratio(facts[393], row['context']) == 1 and _key_fact_ratio(facts[393], row['answer']) == 1 after the change.

### S5 — tests/test_eval_items.py at 7a71cdf

- URL: tests/test_eval_items.py
- Retrieved: 2026-10-15
- Locator: test_bundled_dev_key_facts_score_the_requested_answer, lines 40-58
- Fragment: for multi_hop rows with facts: assert _key_fact_ratio(facts[n], row['context']) == 1; then pinned asserts for rows 270, 333, 335, 336, 362 only.
- Applicability: This shows why each fix passed the gate: the test checks precision of surviving facts and pins reviewer-named rows, but never checks that the facts cover the answer.
- Counterevidence: Pinned asserts did catch regressions on the named rows. The gap is only the missing coverage dimension.
- Validation: Adding the row-393 assertion makes the test fail on 7a71cdf and pass after the fix. A coverage audit run once before the fix lists the other under-covered rows.

### S6 — 로컬 dev 추출 구조 (원문·문항 ID 비공개)

- URL: eval/golden/dev.jsonl
- Retrieved: 2026-10-15
- Locator: line 393, fields answer, context, structure
- Fragment: 실제 근거와 답의 인용은 제거했다. 독립 합성 예제: `결과물 | 별빛 관찰 카드`와 `할 일 | ◦ 종이별 접기\n ‑ 파란 리본 묶기\n ‑ 달 모양 도장 찍기\n ‑ 은색 봉투 접기\n ‑ 초록 실 감기`. 합성 답은 결과물과 네 개의 ‑ 항목을 나열하며 `structure = {}`다. 칸 전체가 아닌 요청한 항목 단위로 나눠야 한다는 구조만 재현한다.
- Applicability: This is the concrete case: four requested facts sit as line items in one cell, the answer quotes the items but not the whole cell, and there is no structure to fall back on.
- Counterevidence: One row is one shape. Other under-covered rows may paraphrase rather than quote, which line splitting does not fix.
- Validation: 당시 비교에서는 결과물 1개와 요청한 항목 4개가 모두 남아야 했다. 합성 예제의 다섯 사실 중 결과물만 일치하면 비율은 1/5 = 0.2다. 이 예제로 실제 릴리스 점수를 새로 측정했다고 주장하지 않는다.

## Claims

- C1 (source; S1): Nugget-based RAG evaluation scores answers by atomic facts that can each be judged present or absent, and aims at a grain neither too broad nor too specific.
- C2 (source; S2): Judging a unit that mixes several facts as one unit is inadequate; the unit should be broken into atomic facts first.
- C3 (source; S3): The current multi_hop extraction keeps a context cell only when the whole whitespace-collapsed cell is a substring of the answer, and newlines are removed before any split.
- C4 (source; S4): The evaluator matches each key fact, or one of its '|' alternatives, as one contiguous pattern in the target text.
- C5 (source; S5): The guarding test checks only that surviving facts are found in the context, plus specific reviewer-named rows; it never checks that facts cover the answer.
- C6 (interpretation; S1, S2, S3, S5, S6): The fixes failed because the fact unit stayed the table cell, coarser than the bullet-level facts golden answers state, and nothing measured coverage. Splitting cells into line items, plus a coverage audit, addresses the cause rather than one row.

## Core theory

Nugget-based RAG evaluation scores an answer by the atomic facts (nuggets) a good answer must contain. Each nugget is a fact an assessor can judge as present or absent, written as a short phrase, 'neither too broad nor too specific'. FActScore makes the same argument for long-form text: a passage mixes supported and unsupported pieces, so judging the whole unit at once is inadequate, and the text should be broken into atomic facts first. A fact unit coarser than the facts the answer states makes the judgment depend on the coarse unit, not on the content.

## Applicability

여기서 판정은 기존 연속 문자열 일치다(`rag/evaluation/evaluation.py:154-168`). 여러 항목이 든 칸을 하나로 취급하면 그 칸을 일부만 인용한 답의 사실을 잃는다. `_cells`·`_multi_hop_key_facts`에서 공백 정리 전에 줄·글머리표별로 나누되 기존 포함 관계·필드명·질문 제외 조건은 유지해야 한다. 당시 393행에 필요했던 것은 서로 독립된 5개 사실이며 실제 문구는 S6에 싣지 않는다.

## Hypothesis

The fact unit is fixed to a whole table cell, while golden answers state facts at a finer grain (lines and bullet items inside a cell). Extraction goes context-cell to answer with whole-cell substring containment, so any cell the answer only partly quotes is silently dropped. With no recall or coverage check, every fix that only changes which cells are kept leaves this loss in place.

## Counterevidence

- Line or bullet splitting only helps when the answer quotes items verbatim. Answers that paraphrase a bullet, or list items inside one comma-separated line, would still lose facts. Splitting on commas would break numbers like 2,150 and names.
- The rough regex count shows only about 9 of 71 multi_hop dev rows with bullet-marked contexts. Other under-covered rows may have a different shape (part of a prose sentence quoted), which line splitting does not fix.
- Smaller units mean more short items. A short line such as a heading fragment could match the answer by accident and become a fact the question never asked for. The question-exclusion and len>1 filters limit but do not remove this risk.

## Alternatives

- Answer to context: split the answer into segments (on 'N)', ',', '.', ':') and keep each segment found in one evidence unit. This handles answer-led enumerations, but segments carry connective text ('최종 산출물은 … 이다') that never matches, so it needs trimming or longest-common-substring logic. That is more code and more heuristics than line splitting; not first.
- LLM atomic-fact decomposition (FActScore / AutoNuggetizer style): best granularity, but it costs money on the shared OpenAI key (user rule: price it and ask first), is nondeterministic, and adds a paid step to an offline loader. Not first.
- Have golden_pipeline emit a per-hop structure for multi_hop rows (row 393 has structure {}), so key facts come from structured fields as for the other topics. This is the cleanest long-term fix, but it means regenerating the release (paid, a different module). It is a follow-up.
- Exclude rows whose facts cover too little of the answer (a new _problem reason, e.g. 'key facts do not cover the answer'). Cheap and honest, and the reviewer accepted not keeping such questions. Use it as the fallback for rows still under-covered after line splitting, not instead of it, because it shrinks the dev set.

## Experiment

1) 당시 393행의 요청한 5개 사실을 모두 추출하고 단일 사실 답이 만점을 받지 않는지 확인하도록 제안했다. 7a71cdf 이전 실패와 이후 통과가 예측이었다. 2) 다중 근거 답에서 추출 사실·질문 공유 문구를 제외한 미충족 비율을 집계하고 절반 미만만 덮는 답을 감사하도록 했다. 3) 기존 정밀도와 270·333·335·336·362행 회귀를 유지하도록 했다. 실제 내용의 설명은 S6의 독립 합성 예제로 대체한다.

## Result

Observed, still a draft: these are measurements on eval/golden/dev.jsonl, not a verified rule. The fix is the commit right after 441c05b on feature/eval-golden-input; it changes rag/validation/validation.py, tests/test_eval_items.py and README.md.

- Reproduced at 7a71cdf: 필수 사실 5개 중 1개만 추출되어 그 한 사실만 포함한 답에 1.0을 주었다. 실제 답·추출 문자열은 제거했다.
- Experiment 1 (pinned test): 당시 테스트는 393행에서 필수 사실 5개를 보존하고 하나만 포함한 답의 점수가 0.2인지 확인했다. 7a71cdf에서는 실패하고 수정 후 게이트를 통과했다. 합성 예제는 당시 측정을 다시 실행한 입력이 아니다.
- 줄 분리만으로 393행을 고쳤지만 395행에서는 줄바꿈된 필드명 일부가 사실로 잘못 들어왔다. 여러 칸이 있는 행의 첫 칸은 나누지 않도록 수정했다. 실제 필드명 문자열은 제거했다.
- Experiment 2 (coverage audit). Before the fix, 5 kept rows had facts covering less than half of the answer: 379, 384, 386, 387, 393. 384 was a false alarm, because the audit counted field-name labels as uncovered. Two shapes remained:
  - Inline bullets on one line (379 ' o ', 330 '○ … - …'). Fixed by also splitting on bullet markers inside a line.
  - Paraphrased or partly quoted prose (326, 364, 376, 377, 386, 387, 394). No split recovers these, as the Counterevidence section predicted.
- For the second shape the Alternatives fallback was adopted: a multi_hop row is kept only when its facts cover at least 60% of the answer letters. Field names, 'X:' labels, words already in the question and particle-only words are not counted. On dev, rows missing requested content scored 0.07-0.54 and complete rows 0.60 or more. The cut is a judgement call with a narrow gap (0.54 vs 0.60), not a value from the sources.
- 같은 감사에서 348행의 한 자리 값 2개가 길이 필터와 1~4번 행 번호의 필드명 분류 때문에 빠진 것을 확인했다. 숫자는 유지하고 필드명에는 글자가 있어야 하도록 바꿨다. 원래 정답 값은 게시하지 않는다.
- Experiment 3 (regression): 유지한 다중 근거 사실은 자체 context에 모두 점수 1이었다. 270·333·335·336·362행 회귀도 유지했다. 자체 정답에 대한 예외는 370행으로, 식별자 끝 숫자를 9분으로 읽는 평가기 문제였다(`rag/evaluation/evaluation.py`, 이 수정 범위 밖). 원래 식별자·정답 문자열은 제거했다.
- Net effect: 374 of 396 dev questions are kept, against 377 at 7a71cdf. 22 multi_hop rows are excluded as having no key facts: 348 came back, and 364, 376, 386 and 387 left.

## Unresolved limits

No shell was available, so the extraction was not re-run after reading the code. The count of 9 bullet-context rows is a rough regex estimate, and the number of rows whose answers paraphrase cell content is unknown. The coverage threshold (about half) is a judgement call, not taken from the sources. The nugget literature uses LLM or human assessors that judge meaning; this repository's matcher is literal, so the granularity argument transfers but the sources' agreement numbers do not.
