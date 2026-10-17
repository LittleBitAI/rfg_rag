# Review research — F4, cycle 1

Draft research before the fix of review round 3 of PR #63, written 2026-10-17. It is not a verified fact or a shared rule: the review reads it with the fix.

## Problem

F4 concerns the boundary between whole-project quantity filtering and ordinary hybrid retrieval. An unscoped numeric condition should select the project filter when its target is projects, including `예산 1억원 이상인 전체 사업`; requirement and vendor-qualification comparisons must retain hybrid retrieval. The round-2 implementation admitted non-project questions. Its correction now rejects a valid project question because a modifier precedes `사업`. These are opposite failures of the same intent boundary. [C1, C2, C3, C4]

Trigger: repeat, rounds 2, 3.

- [P1] [P1] rag/retrieval/quantity_filter.py:130 — 명사 수식어가 붙은 전체 사업 질의가 하이브리드 검색으로 폴백함 / `예산 1억원 이상인 전체 사업` 같은 질의 / 수량 조건이 적용되지 않음

## Failed fixes

- Before the round-2 correction, routing treated a successfully parsed numeric condition as sufficient evidence for whole-project intent. The validation report records an unscoped response-time requirement entering `_filter` without hybrid ranking. Numeric parsing established the comparison, but not its target. [C2]
- The round-2 correction introduced `project_condition()`. It examines the condition remainder, selects the first NNG/NNP other than `인` or `규모`, and requires that token to equal `사업`. This protects the reported requirement and qualification questions but substitutes first-noun identity for target recognition. Under the round-3 reported tokenization, `전체` blocks recognition of the following project noun. [C3, C4]
- Verification covered five non-project questions as original and rewritten inputs, plus positive project forms where `사업` is the first admitted noun. The report also records unchanged results for four existing project searches. Those checks support the repaired cases but do not exercise insertion of a noun modifier before the project target. No round-3 correction is present in the inspected function. [C3, C5]

## Sources

### S1 — Quantity condition parsing and project-target gate

- URL: rag/retrieval/quantity_filter.py
- Retrieved: 2026-10-17
- Locator: Lines 42–46, 105–132 and 151–167
- Fragment: def project_condition(question):
    condition = parse_condition(question)
    if condition is None:
        return None
    target = next((t.form for t in tokens(condition.remainder)
                   if t.tag in ("NNG", "NNP") and t.form not in ("인", "규모")), None)
    return condition if target == "사업" else None

Default excerpt selection:
words = subject_phrase(remainder).split()
if "개요" in words or not set(words) - {"사업", "인", "규모"}:
    return "사업 개요와 목적, 추진배경 및 주요 사업내용"
return remainder

Selection remains conditional:
eligible = [{**r, "similarity": float(similarities[r["phrase"]])} for r in rows
            if _usable(r) and similarities[r["phrase"]] >= cutoff]
- Applicability: Contains the first-noun decision, the separate default-content decision and downstream similarity eligibility.
- Counterevidence: The existing gate deliberately protects non-project targets. Numeric parsing can independently return None, and accepted project routing still permits value exclusions.
- Validation: Trace the actual remainder and tokens; verify modifier insertion preserves the parsed condition and selected project set while non-project targets remain rejected.

### S2 — Hybrid search dispatch and filter result construction

- URL: rag/retrieval/retrieval.py
- Retrieved: 2026-10-17
- Locator: Lines 81–125
- Fragment: return self.search_with_candidates(question, query=query)[0]

query = query or question
route = self.router.route(query)
condition = project_condition(query) if not route and not re.match(r"^.*?」 사업에서 ", query) else None
if condition:
    return self._filter(condition)

Fallback ranks, snapshots and packs candidates:
groups = [self._rank(query, codes, doc_ids) for doc_ids in (list(route.values()) or [None])]

Filter output:
summary = f"[수량 필터] 조건 일치 {len(matched)}개 문서; 값 미표기·매칭 불가로 제외 {excluded}개 문서."
return FilterHits(hits, summary, matched, chosen), self._candidate_snapshot([ranked], ranked)
- Applicability: Shows where rejection switches retrieval algorithms, the effective-query rule, routing guards and the shared public entry point.
- Counterevidence: Agency routing or the document-prefix guard intentionally prevents whole-collection filtering. `_filter()` also uses ranking for per-document excerpts, so an experiment must distinguish excerpt ranking from ordinary collection-wide fallback.
- Validation: Observe dispatch or ranking scope, then assert filter metadata and complete matched IDs rather than merely asserting that ranking was never called.

### S3 — Existing positive, negative and scoped routing regressions

- URL: tests/test_quantity_filter.py
- Retrieved: 2026-10-17
- Locator: Lines 107–134, 190–200, 235–244 and 439–455
- Fragment: Positive examples include:
("예산 1억원 이상인 사업들의 개요", ["b", "c", "a"])
("예산 1억~2억 사업", ["a"])
("예산이 가장 큰 사업", ["b", "c"])
("예산 9억원 이상 사업", [])

Non-project parameters:
"응답시간 3초 이하인 요구사항을 알려줘", "사업 응답시간 3초 이하인 요구사항을 알려줘",
"응답시간 1초~3초 사이 요구사항", "응답시간이 가장 짧은 요구사항",
"예산 1억원 이상인 업체의 자격을 알려줘"

@pytest.mark.parametrize("rewritten", [False, True])
index._filter = MagicMock(side_effect=AssertionError("Non-project question entered filter"))
index._rank.assert_called_once_with(question, set(), None)
assert hits == [index.chunks[0]] and not hasattr(hits, "summary")
- Applicability: Establishes meaningful existing regressions and the missing modifier-before-target dimension.
- Counterevidence: The tests cover more than thresholds, including ranges, extremes, empty matches, rewritten negatives and scoped routing. The gap is specific, not an absence of regression testing.
- Validation: Extend the existing parameterized behaviors with modifier-preserving positives and corresponding non-project targets.

### S4 — Recorded round-2 routing repair and validation

- URL: docs/quantity_filter_validation.md
- Retrieved: 2026-10-17
- Locator: Review round 2, lines 5, 9 and 15–17
- Fragment: The unscoped response-time requirement used `_filter` without calling hybrid ranking.

Project filtering now requires a project target in the parsed condition's remainder, ignoring connecting `인` and `규모`. A business word only in the field prefix is insufficient. Ten route regressions exercise five non-project comparisons as original and rewritten questions: requirement thresholds, ranges, extremes, a project-prefixed requirement and vendor qualification.

Four actual project searches retained 61/30/44/1 projects, 10/45/10/10 exclusions, all chosen values and complete source markers. Five actual non-project searches used hybrid retrieval and returned 14/17/15/23/15 hits.

The active index and server were not switched to the isolated artifacts.
- Applicability: Records the earlier executed symptom, intended repair and scope of reported validation.
- Counterevidence: This is a tracked report of earlier checks, not an independently rerun experiment. Its referenced artifact logs were unavailable to this source-only pass.
- Validation: Report the exact new modifier reproduction separately from prior successful searches and historical execution counts.

### S5 — Documented whole-project quantity-search contract

- URL: README.md
- Retrieved: 2026-10-17
- Locator: Lines 42–48 and 63–65
- Fragment: Quantity conditions targeting projects (`사업`), without an agency or document-name prefix, filter the whole collection using indexed per-document values. Thresholds, ranges and max/min are supported, retaining ties.

Numeric comparisons targeting requirements or vendor qualifications use the existing hybrid search; mentioning a project in the field name alone does not select the project filter. Routing uses the stored rewrite, or the original question when it is empty.

색인·라우팅·필터에 LLM이나 API 호출을 추가하지 않습니다.

Values without an accepted matching field can still be omitted, and conflicting values within one document are not semantically reconciled.
- Applicability: Defines both sides of the routing boundary and limits the completeness promise to accepted indexed values.
- Counterevidence: It does not specify a complete grammar for modifiers or guarantee extraction and semantic reconciliation for every document.
- Validation: Preserve project filtering, non-project hybrid behavior, effective-query routing and existing exclusions without adding paid intent classification.

### S6 — Kiwi Python API — token information and POS tags

- URL: https://github.com/bab2min/kiwipiepy
- Retrieved: 2026-10-17
- Locator: README token-information example and 품사 태그 table; fetched lines 355–365 and 1318–1333
- Fragment: tokens[0].tag # 형태소의 품사 정보

세종 품사 태그를 기초로 하되, 일부 품사 태그를 추가/수정하여 사용하고 있습니다.

NNG | 일반 명사
NNP | 고유 명사
- Applicability: Documents the meaning of the exact token fields and noun tags used by the gate. Found through an actual web search and fetched from the maintainer's repository.
- Counterevidence: The documentation does not supply the exact analysis of `인 전체 사업` or guarantee identical analyses across installed models and versions.
- Validation: Capture the actual installed analyzer's token forms, tags and offsets instead of mocking the assumed modifier analysis.

### S7 — Universal Dependencies — Nominals

- URL: https://universaldependencies.org/u/overview/nominal-syntax.html
- Retrieved: 2026-10-17
- Locator: Modifier Dependents, first definition
- Fragment: “An `nmod` is a nominal phrase modifying the head of another nominal phrase, with or without a special case marker.”
- Applicability: Provides the general distinction between a nominal modifier and the head it modifies. Found through an actual web search and fetched from the project's documentation.
- Counterevidence: This is a general annotation model, not a Korean routing algorithm or proof of the reported Kiwi analysis. It does not establish that arbitrary modifiers can be discarded.
- Validation: Use target/modifier minimal pairs to test the proposed local recognition rule; adding a dependency parser is not required by this source.

### S8 — Filter-context formatting and generation instructions

- URL: rag/generation/generation.py
- Retrieved: 2026-10-17
- Locator: Lines 26–32 and 38–46
- Fragment: "- [수량 필터] 컨텍스트는 질문의 부가 요청이 없어도 제공된 모든 사업을 각각 한 행으로 하는 "
"'사업 | 값(원문 표기) | 개요 | 출처 [번호]' Markdown 표로 빠짐없이 나열하세요. "
"검색기가 전체 문서의 확인 가능한 값에 질문의 조건을 이미 적용했으므로 제공된 사업은 모두 조건을 만족하며, "
"최대·최소 질문의 결과는 이미 비교를 마친 극값 사업입니다. 이 판정을 그대로 설명하세요. "

context = "\n\n".join(parts) or "(검색된 문서 청크가 없습니다.)"
return f"{hits.summary}\n\n{context}" if hasattr(hits, "summary") else context
- Applicability: Shows that the routing decision changes the context contract consumed by generation, including complete project tables and empty-result summaries.
- Counterevidence: These instructions do not prove generated answers comply. Routing and context checks can be performed without making a generation call.
- Validation: Assert filter-summary presence for accepted project queries, including empty matches, and its absence for non-project hybrid results.

### S9 — Actual morphological tokenizer used by quantity parsing

- URL: rag/retrieval/quantities.py
- Retrieved: 2026-10-17
- Locator: Lines 54–63
- Fragment: @lru_cache(maxsize=1)
def _kiwi():
    # 모델을 읽는 데 시간이 들어 한 번만 만든다.
    return Kiwi()


def tokens(text):
    """형태소 분석. 검증을 여러 스레드로 돌리므로 Kiwi 하나를 잠가 차례로 쓴다."""
    with _KIWI_LOCK:
        return _kiwi().tokenize(unicodedata.normalize("NFC", text))
- Applicability: Connects the gate to a real default Kiwi instance and NFC normalization rather than a syntactic target parser.
- Counterevidence: Source inspection establishes the call path but not the installed package/model version or exact runtime tokens.
- Validation: Use this wrapper in the initial reproduction and record the environment before changing the recognition rule.

## Claims

- C1 (source; S5): The documented contract separates unscoped project quantity filtering from requirement/vendor hybrid retrieval, preserves effective-query routing and excludes quantities without accepted matching fields.
- C2 (source; S4): The earlier validation report records a non-project requirement entering the filter, followed by a project-target gate and successful checks for the specific reported project and non-project searches.
- C3 (source; S1): The current project gate accepts only when the first NNG/NNP in the parsed remainder, excluding `인` and `규모`, equals `사업`.
- C4 (interpretation; S1, S2, S9): Given the review's reported `전체/NNG` analysis, the exact modifier query is predicted to return no project condition and enter hybrid retrieval. This is a static prediction requiring runtime confirmation.
- C5 (interpretation; S3, S4): The existing tests and recorded validation cover direct project targets and several non-project forms, but leave noun-modifier insertion before the project target untested.
- C6 (interpretation; S6, S7, S9): Kiwi documents morphological noun classes, while Universal Dependencies distinguishes nominal heads from nominal modifiers. Applying that distinction here explains why first eligible noun and requested target need not coincide.
- C7 (interpretation; S1, S2, S3, S5, S6, S7): A bounded recognition rule for the demonstrated scope modifier before `사업`, retaining rejection of other targets and existing scope guards, is preferable to unrestricted project-word membership, arbitrary noun skipping or a new parser dependency.
- C8 (source; S2, S8): Both public search entry points share dispatch on the effective query; filter results carry a summary that activates the generation prompt's complete-project-table contract.
- C9 (interpretation; S1): Default excerpt selection independently recognizes a limited word set that omits `전체`; fixing dispatch alone therefore does not establish equivalent default project excerpts.
- C10 (interpretation; S1, S2, S3, S5, S6, S8, S9): Actual-token tracing followed by paired positive/negative routing and result tests can distinguish a bounded repair from a return to overbroad routing, without paid API calls.

## Core theory

Morphological class and syntactic role are different information. Kiwi documents NNG and NNP as noun classes; those labels do not themselves identify the head of the requested entity phrase. Universal Dependencies separately models nominal heads and their modifiers, including nominal modifiers. Therefore a noun can modify another noun rather than be the target. These sources explain why first-noun selection is insufficient; they do not prescribe a Korean intent classifier or require adding a dependency parser. [C6]

## Applicability

Repair the project-intent decision in `project_condition()`, preserving numeric parsing and the existing agency/document guards. The smallest supported repair is local recognition of the reported project phrase: permit `전체` as a scope modifier before the project target, alongside existing supported connecting forms, while still rejecting another target noun. Do not turn this into an unrestricted search for `사업` anywhere in the question or skip arbitrary nouns. Preserve the parsed subject, comparison, values and remainder; accepting a target must not silently erase a substantive selection constraint. A bounded rule is a proposed implementation choice whose sufficiency must be demonstrated by paired routing and result tests. [C7, C10]

## Hypothesis

The remaining cause is the assumption that the first eligible noun in the condition remainder must be the entity being selected. For `예산 1억원 이상인 전체 사업`, parsing leaves the remainder `인 전체 사업`. Given the review's observation that `전체` is NNG, `next(...)` selects it, `project_condition()` returns None, and `search_with_candidates()` takes hybrid ranking and packing. This is a static explanation consistent with the review, not an independently executed reproduction. [C3, C4]

## Counterevidence

- The current gate correctly distinguishes the existing direct-project fixtures from the five non-project regression fixtures. This argues for repairing its narrow recognition boundary rather than removing project-intent checking. [C5, C7]
- The validation report records four real project searches retaining their results and five non-project searches using hybrid retrieval. That supports the earlier correction for those inputs, although the referenced execution artifacts were not independently inspected or rerun here. [C2, C5]
- The exact local Kiwi output has not been executed in this session. If the deployed analyzer does not return `전체` as an eligible noun for the actual remainder, this particular failure trace needs revision. [C4, C6]
- General nominal-modifier theory does not establish that every modifier can be ignored. Some modifiers narrow the requested set, and admitting them without enforcing their meaning could introduce a different routing error. [C7]

## Alternatives

- Restore routing on every `parse_condition()` result: rejected because it recreates the demonstrated requirement-question regression. [C2, C7]
- Accept any occurrence of `사업` in the question or remainder: not first, because a project mention can occur in the numeric field prefix or after a non-project target. The original regression already includes a project-prefixed requirement question. [C5, C7]
- Skip every noun until `사업` appears: rejected for the same reason; it discards evidence that the condition targets requirements or vendors. [C7]
- Add a full dependency parser or an LLM intent classifier: disproportionate to the demonstrated phrase and inconsistent with the documented routing path's absence of added LLM/API calls. The linguistic sources motivate a distinction, not a new dependency. [C1, C6, C7]
- Change similarity cutoffs, quantity metadata or index construction: not first, because the reported branch decision occurs before `_filter()` and its value selection. Those changes cannot make a rejected project condition reach filtering. [C3, C4]
- Rely on rewriting to remove `전체`: not sufficient because both search entry points route the effective query directly, and the documented contract also permits the original query when no rewrite is supplied. [C1, C8]

## Experiment

First, in the implementation session, record the installed Kiwi version and the actual outputs of `parse_condition(question)`, tokens of its remainder, `project_condition(question)`, router result and selected retrieval branch for the exact reported query. The predicted pre-fix trace is remainder `인 전체 사업`, first eligible noun `전체`, no project condition, and hybrid retrieval. If that trace differs, revise the hypothesis before editing. Then extend the existing positive fixture with the base/modifier pair `예산 1억원 이상인 사업` and `예산 1억원 이상인 전체 사업`, using real tokenization and the controlled index. Require identical condition subject/unit/mode/values and the same complete matching document IDs, values, candidates and filter summary. Exercise threshold, range and extreme forms with the same modifier, original and explicit rewritten-query paths, and both public search entry points. Keep the existing non-project tests; add the paired targets `응답시간 3초 이하인 전체 요구사항을 알려줘` and `예산 1억원 이상인 전체 업체의 자격을 알려줘`, plus a requirement-target question with a later project mention, to reject unrestricted membership scanning. Preserve agency/document-prefix controls. Include a valid project condition with zero matching values: it must retain the filter result and summary rather than silently substitute hybrid results. Inspect formatted context and default excerpts, since route acceptance alone does not verify the whole downstream contract. All proposed checks can run locally without rewrite, generation or judge API calls. No checks were executed in this research session. [C8, C9, C10]

## Result

pending — the fix records what it observed here, with the tests and the commit.

## Unresolved limits

This is a draft based on current tracked source, the supplied round-2/round-3 findings, a tracked validation report and primary web documentation. Historical commits and artifact logs were not independently executed or reconstructed. The exact current tokenizer output remains an experimental prerequisite. The bounded proposal addresses the demonstrated `전체 사업` form and existing supported forms; it does not claim general Korean noun-phrase understanding or automatic support for arbitrary restrictive modifiers. Correct routing also does not guarantee that every corpus document has an eligible quantity: the documented unit, usability and field-similarity exclusions remain. `content_query()` separately has a literal default-request word set that omits `전체`, so excerpt equivalence should be checked after the route changes. No files were edited, tests run or paid calls made. [C1, C4, C9, C10]
