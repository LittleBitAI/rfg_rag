# 리뷰 조사 · F5, 1회차

집계 결과와 측정 조건은 Git에 보관하고, 실제 질문·정답·근거·OCR 텍스트와 레코드별 내보내기는 Git에서 제외된 로컬 `artifacts/`에 보관합니다.

복원 출처: 정리 전 `artifacts/review-round2/originals/` 또는 `d7d1682^`. 아래 수치와 검증 기록은 당시 실행에서 관측한 과거 기록이며, 이번 작업에서 다시 측정한 결과가 아닙니다.

PR #65 리뷰 7회차의 수정 전에 2026-10-18에 쓴 조사 초안입니다. 검증된 사실이나 공용 규칙이 아니며, 리뷰는 이 문서를 수정과 함께 읽습니다.

## 문제

복구 조사 문서는 자신이 분류된 지적을 분석해야 합니다. 다음 수정과 리뷰가 기대는 근거이기 때문입니다. PR #65에서 두 번, 문서가 한 문제로 분류됐는데 다른 문제를 분석했습니다. 2회차에서 review-golden-abc-seven-topic-comparison-f4-1.md는 F4로 분류됐지만 F1 plan 해시를 분석했고, 3회차가 이를 F5로 제기했습니다. 6회차에서 review-golden-abc-seven-topic-comparison-f6-1.md는 F6(이어하기 한도에 세는 역할 없는 끝난 호출)로 분류됐지만 F2(judgments.csv 파싱)를 분석했고, 7회차가 이를 F5로 제기했습니다. 두 번 모두, 반복된 지적은 수정 전에 쓴 근본 원인 조사 없이 남았습니다.

발생: 최후 확인(backstop), 7회차.

- [P1] [P1] docs/research/review-golden-abc-seven-topic-comparison-f6-1.md:7 — F6 조사가 F2를 분석합니다 / 반복된 이어하기 한도 실패에 필요한 재분석을 낼 때 / 수정에 올바른 근본 원인 근거가 없습니다

## 실패한 수정

- 3회차 정정(8326cee): f4-1.md(5행)에 'F4 조사가 아닙니다' 안내를 더하고, F4를 바로 조사한 새 f4-2.md에 기댔습니다. 잘못된 결과물은 고쳤지만 그것을 만든 원인은 고치지 않았습니다. wiki-agent tool/main/recovery.py의 서버 형식 재시도 경로를 건드리지 않았으므로, 6회차에서 같은 실패가 났습니다.
- 6회차 정정(f0ddd69): 수정을 이미 한 뒤에 'F6 as raised' 문단(f6-1.md 144행)을 덧붙였습니다. 3회차 방식을 되풀이한 것입니다. 수정 전에 쓴 F6 조사를 내지 않고 결과를 나중에 기록했습니다. 재시도 경로도 건드리지 않았습니다.

## 출처

### S1 — Using the Messages API — Multiple conversational turns (Anthropic 문서)

- URL: https://platform.claude.com/docs/en/build-with-claude/working-with-messages
- 확인일: 2026-10-18
- 위치: 'Multiple conversational turns' 절
- 인용: The Messages API is stateless, which means that you always send the full conversational history to the API. You can use this pattern to build up a conversation over time. Earlier conversational turns don't necessarily need to actually originate from Claude. You can use synthetic assistant messages.
- 적용: 재시도용 새 조사 세션은 앞선 대화 없이 시작합니다. 재시도 프롬프트는 지적과 거부된 답을 직접 담아야 하며, 앞선 문맥으로 보낼 수 있습니다.
- 반대 근거: 날것의 API를 설명합니다. CLI는 저장된 세션을 이어갈 수 있지만, recovery.py는 세션을 이어가지 않습니다.
- 검증: 수정 뒤 두 번째 프롬프트는 asked() 글과 첫 답을 담으며, 테스트가 이를 확인합니다.

### S2 — anthropics/claude-code 이슈 #43696(세션 이어가기가 문맥을 되살리지 못함)

- URL: https://github.com/anthropics/claude-code/issues/43696
- 확인일: 2026-10-18
- 위치: 웹 검색 결과 요약, 이슈 페이지는 가져오지 않음
- 인용: Per the search summary: a report from early April 2026 that the prior conversation context is not restored and the session starts fresh as if it were a new conversation; reporter on Windows 11 with git-bash; no workaround listed; whether it was resolved is not shown.
- 적용: 세션을 다시 쓰거나 이어가는 것만으로 재시도를 고치는 데 반대하는 근거입니다. 문맥을 프롬프트에 넣는 것은 이어가기가 되는지에 달려 있지 않습니다.
- 반대 근거: 요약에서 읽은 보고 하나뿐이며, 그 뒤 고쳐졌을 수 있습니다.
- 검증: 고른 수정은 이어가기에 기대지 않으므로 이 이슈의 영향을 받지 않습니다.

### S3 — 리뷰 조사 · F6, 1회차

- URL: docs/research/review-golden-abc-seven-topic-comparison-f6-1.md
- 확인일: 2026-10-18
- 위치: 7, 125, 140, 144, 148행
- 인용: line 125: 'I could not read the round-6 finding text in the repo. If the reviewer flagged something other than these three shapes (for example key.json), this hypothesis misses it.' line 140: 'This page analyses F2 (_human reading judgments.csv), not the round-6 F6 finding' line 148: 'The round-6 finding text was not available to me, so I derived these shapes by reading the code rather than from the reviewer's words.' (번역 전 원문 기준 인용)
- 적용: 원래 F6 프롬프트가 지적을 그대로 인용했는데도, 이 문서를 쓴 단계는 F6 지적을 보지 못했다는 것을 문서 스스로 보여 줍니다. 이 문서를 쓴 단계는 첫 단계와 프롬프트가 달랐습니다.
- 반대 근거: 문서는 지적을 왜 볼 수 없었는지 말하지 않습니다. 그 이유는 이 저장소 밖의 대화 기록과 recovery.py에서 나옵니다.
- 검증: 재시도 수정 뒤에는, 형식 재시도를 강제해도 분류된 문제에 대한 문서가 나옵니다.

### S4 — 리뷰 조사 · F4, 1회차

- URL: docs/research/review-golden-abc-seven-topic-comparison-f4-1.md
- 확인일: 2026-10-18
- 위치: 5행(안내), 112행(결과)
- 인용: line 5: 'Not F4 research (review round 3, F5). This page is filed under F4, but every section below analyses the review-packets plan hash: round-2 F1 ... Do not cite this page as grounds for any F4 fix.' line 112: 'This page's text researches the review-packets plan hash (round-2 F1), not the round-2 F4 finding it is listed under' (번역 전 원문 기준 인용)
- 적용: 첫 사례입니다. 같은 식으로 다른 문제로 넘어갔고, 3회차 수정은 문서에 이 안내를 단 것뿐이었습니다.
- 반대 근거: 안내는 문서가 올바르게 표시됐음을 보여 줍니다. 실패는 한 일이 아니라 바꾸지 않은 것에 있습니다.
- 검증: 재시도 수정이 있으면 이런 안내가 새로 필요하지 않아야 합니다.

### S5 — 리뷰 조사 · F4, 2회차

- URL: docs/research/review-golden-abc-seven-topic-comparison-f4-2.md
- 확인일: 2026-10-18
- 위치: 17행(실패한 수정, 조사 과정)
- 인용: Research process: the cycle-1 page listed under F4 (docs/research/review-golden-abc-seven-topic-comparison-f4-1.md) actually researched the F1 plan-hash finding; its own Result section says so. The F4 replay key was designed without research, and nobody asked whether a content hash identifies a call. (번역 전 원문 기준 인용)
- 적용: 잘못된 분류를 그 문서 하나의 실수로 본 3회차의 시각을 기록합니다. 서버 재시도까지 따라가지 않았고, 그래서 다시 일어났습니다.
- 반대 근거: 이 문서는 첫 시도에 올바르게 쓴 조사이며, 재시도만 잘못 분류한다는 가설과 맞습니다.
- 검증: 바꿀 필요 없습니다. F4 참고 문서로 남습니다.

### S6 — 저장소 reflog

- URL: .git/logs/HEAD
- 확인일: 2026-10-18
- 위치: 370-372행과 381-382행
- 인용: 370: 'docs: research F1 before fixing it again (cycle 1)' (291ed08); 371: 'docs: research F4 before fixing it again (cycle 1)' (9272eca), about 270 s later; 372: 'golden: tie review packets to the frozen plan and reuse settled validation calls on resume'; 381: 'docs: research F6 before fixing it again (cycle 1)' (9458840); 382: 'golden: count settled validator calls by rebuilt request, parse judgment files once before use' (f0ddd69).
- 적용: F4 재시도가 돌 때 가장 최근 조사 커밋은 F1 문서였으며, 재시도가 F1을 베낀 것과 맞습니다. F6 수정 커밋은 F6 조사 커밋 뒤에 오며, 수정 전에 쓴 분석의 시점을 정해 줍니다.
- 반대 근거: 커밋 시점만으로는 모델이 무엇을 봤는지 알 수 없습니다.
- 검증: 되살리는 대화 기록 43행 분석은 f0ddd69가 커밋되기 전 시점을 가리킵니다.

## 주장

- C1 (출처; S1): 모델 요청은 앞선 대화를 기억하지 못합니다. 요청마다 필요한 문맥을 담아야 합니다.
- C2 (해석; S3, S4, S6): 잘못 분류된 두 문서는 모두 분류된 지적을 갖지 않은 단계가 썼습니다. 각각 브랜치에서 가장 최근의 다른 지적을 분석했습니다.
- C3 (해석; S3, S4, S5): 3회차와 6회차 정정은 서버 재시도가 아니라 조사 문서만 바꿨으므로, 잘못된 분류가 다시 일어날 수 있었습니다.
- C4 (해석; S1): 원래 asked() 글과 거부된 답, 오류로 재시도 프롬프트를 만들면, 세션 재사용에 기대지 않고 원인을 없앱니다.
- C5 (해석; S2): 세션 이어가기가 문맥을 되살리지 못한 보고가 있으므로, 세션을 다시 쓰거나 이어가는 것만으로는 약한 수정입니다.
- C6 (해석; S6, S3): 수정 전에 쓴 F6 조사는 거부된 첫 답에 있으며, 수정 커밋 f0ddd69 전에 쓰였습니다. 출처를 밝히고 f6-1.md에 되살릴 수 있습니다.

## 핵심 원리

서버 쪽 상태가 없는 모델 요청은 앞선 대화를 기억하지 못하므로, 요청마다 필요한 문맥을 모두 담아야 합니다. Anthropic의 Messages API 문서: 'The Messages API is stateless, which means that you always send the full conversational history to the API.' --resume 없는 새 CLI 세션도 같습니다. 받은 프롬프트만 가지고 시작합니다.

## 적용

recovery.research()는 프롬프트가 asked() 글 전체인 첫 시도에는 이를 올바르게 적용하지만, 두 번째 시도에는 적용하지 않습니다. 재시도는 새 ChatSession(wiki-agent tool/main/recovery.py:356, :346의 반복 안)과 파싱 오류만 담은 프롬프트(:413)를 받습니다. planning.consume은 일부러 CLI 세션 id를 기록에서 빼므로, 이어갈 방법이 없습니다. 그 결과가 이 저장소에 드러납니다. f6-1.md 125행은 '저장소에서 6회차 지적 글을 읽을 수 없었다'고 하고, 148행은 '6회차 지적 글을 볼 수 없었다'고 합니다. 원래 F6 프롬프트는 두 회차의 지적을 모두 그대로 인용했는데도 그렇습니다. f4-1.md 본문은 1분 앞서 291ed08로 커밋된 F1 분석을 되풀이합니다(.git/logs/HEAD 370-371행). 원인이 wiki-agent 서버에 있으므로, 이 저장소에서 하는 수정(안내, 결과 메모)으로는 원인에 닿을 수 없습니다.

## 가설

wiki-agent tool/main/recovery.py research()의 형식 재시도는 새 세션에서 돌고 지적을 보내지 않습니다. 346행의 반복은 시도마다 새 ChatSession을 만듭니다(356행). read()가 첫 답을 거부하면, 재시도 프롬프트(413행)는 'Your answer could not be read: <error> ... Answer again'뿐입니다. 새 세션에는 대화 기록이 없으므로 지적을 보지 못합니다. 저장소에서 찾을 수 있는 가장 최근의 반복 지적을 고르고, read()는 형식만 확인하므로 그 문서가 지금 문제 키로 쓰입니다. 작업 대화 기록(wiki-agent raw/work/rfg_rag/golden-abc-seven-topic-comparison.jsonl)의 근거: F4 2회차 — 첫 답(21행, 셀 b976...)은 F4를 분석했고 sources.validation이 비어 거부됐습니다(22행). 재시도(23행, 셀 b5d3...)는 F1을 분석했습니다. F6 6회차 — 첫 답(43행, 셀 e8e0...)은 F6를 분석했고 S5가 저장소 밖의 허브 위키 경로라 거부됐습니다(44행). 재시도(45행, 셀 ae2c...)는 F2를 분석했고 6회차 지적을 찾을 수 없다고 말합니다. 첫 시도에 통과한 조사 단계는 모두 자기 문제와 맞았습니다. F1 2회차(19행), F4 2회차(29행), F2 1회차(37행)입니다. 수정: 원래 asked() 글, 거부된 답, 오류로 재시도 프롬프트를 만듭니다. 예를 들어 text = f'{asked(spec, key, s)}\n\nYour answer below could not be read: {exc}. Return the same research with only that corrected, ending with exactly the recovery-research block.\n\n{final}'. 그러면 세션을 다시 쓰든 말든 재시도가 지적과 자기 첫 답을 갖습니다.

## 반대 근거

- 재시도는 두 번만 일어났고 둘 다 잘못 분류됐습니다(2번 중 2번). 첫 시도에 통과한 조사 단계 세 번은 모두 자기 문제와 맞았습니다. 양상은 일관되지만 표본이 작습니다.
- 새 세션의 SessionStart 훅은 모든 조사 문서와 최근 결정을 나열합니다. 모델이 어떤 틀린 지적을 골랐는지(이 브랜치의 가장 최근 문서)는 설명할 수 있지만, 왜 맞는 지적이 없었는지는 설명하지 못합니다.
- 지적을 되돌려줘도 원리상 모델이 벗어날 수는 있습니다. read()는 여전히 답이 그 문제에 관한 것인지 확인하지 않습니다. 재시도 수정 뒤에도 벗어남이 이어지면 주제 확인이 필요합니다.
- F4 재시도(23행)는 'HEAD(291ed08)에서 코드를 다시 확인했다'고 말합니다. 지적을 보지 못해 가장 최근 조사 커밋으로 돌아간 모델과 맞습니다. 그래도 모델 동작에 대한 추론이며, 호스트가 기록한 것은 아닙니다.

## 다른 방법

- 재시도에 같은 ChatSession 다시 쓰기(반복 전에 만듦). 문맥과 프롬프트 캐시를 유지하지만, 시도별 타이머, 실행, 닫기 구조를 바꿔야 합니다. CLI 세션 이어가기가 문맥을 되살리지 못한 보고가 있으므로(claude-code 이슈 #43696), 문맥을 직접 넘기는 쪽이 더 튼튼합니다. 무난한 두 번째 선택입니다.
- 답이 지적의 파일이나 줄(예: validation.py:110)을 대는지 서버에서 확인하기. 올바른 조사를 잘못 거부할 수 있는 휴리스틱입니다. 수정이 아니라 나중에 막이로 더할 수 있습니다.
- 출처 형식 확인을 느슨하게 해 재시도를 줄이기. 일어나는 빈도는 줄지만 결함은 남습니다. 택하지 않았습니다.
- 3·6회차처럼 rfg_rag의 문서를 계속 고치기(안내, 결과 메모). 이미 한 번 실패했습니다. 지금 결과물에는 필요하지만 충분하지 않습니다.
- 서버 수정과 별개로 이 저장소에서: f4-1.md 5행처럼 f6-1.md를 잘못 분류된 문서로 표시하고, 수정 전에 쓴 F6 분석을 기록합니다. 그 분석은 대화 기록 43행의 첫 F6 답이며, 시각 1792283995로 수정 커밋 f0ddd69(1792284592)보다 앞섭니다. 저장소 밖 S5 경로 때문에만 거부됐고, 그 가설(검증기 요청을 다시 만들고 그 SHA-256을 재사용 맵과 맞춰 선결제 호출을 셈)이 바로 f0ddd69가 구현한 것입니다. 그러면 리뷰어는 출처를 밝힌, 수정 전에 쓴 F6 조사를 갖게 됩니다. 그 분석이 제안한 부정 경우도 더합니다. 저장된 attempt-0 호출이 채점 호출 하나뿐인 역할 없는 기록은 수를 낮추면 안 됩니다.

## 실험

wiki-agent tool/test_recovery.py에서 recovery.ChatSession을 프롬프트마다 기록하는 Host로 바꿉니다. 첫 답은 S2 url이 저장소 밖 경로인 recovery-research 블록으로 끝나 read()가 거부하고, 두 번째 답은 올바릅니다. F1 반복 발생 하나에 대해 prepared()를 돌립니다. 두 번째로 기록된 프롬프트에 'Review research for issue `F1`'과 발생 회차의 지적 머리글이 있는지 확인합니다. 지금 코드에서는 두 번째 프롬프트가 오류 글뿐이므로 테스트가 실패합니다. 재시도 글을 asked()와 거부된 답으로 만들면 통과합니다. 지난 실행에 대한 확인은 이미 했습니다. 대화 기록 20-23행과 42-45행에서 셀 id가 바뀌며 정확히 재시도 시점에 문제가 넘어갑니다.

## 결과

두 저장소 밖에서 임시 테스트(`test_the_format_retry_prompt_carries_the_finding`)로 실험을 돌렸습니다. wiki-agent `tool/test_recovery.py`를 읽기 전용으로 가져오고(wiki-agent는 `f7b4bdf`, 작업 트리는 깨끗하게 둠), `recovery.ChatSession`을 그 `Host`로 바꿨습니다. 첫 답의 S1 url은 `C:/outside/the/repo.md`였고 두 번째 답은 올발랐으며, F1 반복 발생 하나에 대해 `prepared()`를 돌렸습니다. 관측: id가 다른 세션 두 개. 프롬프트 1은 "Review research for issue `F1` (repeat, rounds [1, 2]), cycle 1 of 2"로 시작했고 지적을 인용했습니다. 프롬프트 2는 "Your answer could not be read: 출처 `S1` 는 URL 도 저장소의 파일도 아니다: C:/outside/the/repo.md / Answer again, ending with exactly the `recovery-research` block."뿐이었습니다. 두 번째 프롬프트가 문제와 지적을 담는지에 대한 확인은 예측대로 실패했습니다. 문서는 그래도 받아들여졌으므로(phase `fixing`), 재시도의 주제가 문제와 맞는지 확인하는 곳이 없습니다. 대화 기록도 맞습니다. 44행은 오류만 담은 F6 재시도 프롬프트이고, 45행은 새 셀입니다. 지금 코드에서 가설이 맞습니다.

원인과 수정은 이 작업 저장소 밖인 wiki-agent `tool/main/recovery.py`(356행과 413행)에 있으며, 여기서는 바꾸지 않았습니다. 이 저장소에서는 `review-golden-abc-seven-topic-comparison-f6-1.md`에 `f4-1.md`처럼 잘못 분류 안내를 달았습니다. 수정 전에 쓴 F6 조사는 대화 기록 43행(ts 1792283995, `9458840`과 `f0ddd69` 전)에서 출처와 함께 되살렸습니다. 그 조사에서 나온 후속 작업 두 개도 했습니다. 부정 채점 호출 테스트 `tests/golden/test_validation.py::test_a_settled_judge_call_does_not_count_as_a_paid_validator_call`과, 센 요청과 보낸 요청이 어긋나지 않도록 공용으로 쓰는 `validation._single_units`입니다. 결과는 이 문서를 담은 커밋에 있습니다. recovery.py가 `asked()`와 거부된 답으로 재시도를 만들기 전까지는, 형식 재시도가 다시 잘못 분류할 수 있습니다.

## 남은 한계

원인과 제안한 수정은 이 작업 저장소 밖인 wiki-agent(tool/main/recovery.py)에 있습니다. rfg_rag 수정 단계는 사람의 허락 없이 이를 바꿀 수 없고, 서버의 조사 확인은 URL과 이 저장소의 파일만 출처로 받습니다. 그래서 recovery.py와 대화 기록은 출처가 아니라 본문에서 인용했습니다. 아무것도 돌리지 않았습니다(셸 없음). 재시도 두 경우는 대화 기록으로 확인했지만, 아직 이를 재현하는 테스트는 없습니다. 수정 뒤에 고친 문서에 들어 있는, 되살린 F6 첫 답을 수정 전에 쓴 조사로 리뷰어가 받아들일지는 리뷰가 판단할 일입니다.
