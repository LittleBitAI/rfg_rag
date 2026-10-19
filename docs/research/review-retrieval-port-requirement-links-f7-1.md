# Review research — F7, cycle 1

Draft research before the fix of review round 9 of PR #70, written 2026-10-19. It is not a verified fact or a shared rule: the review reads it with the fix.

## Problem

F7 (P1, round 9 at be56259): rag/retrieval/retrieval.py:80 links the chunks of a split table only when the table has at most _TABLE_LINK_MAX = 6 chunks. A table split into seven or more chunks gets no table links at all, so when search finds one part, the part holding the header, the related row or the continuation is never packed with it. That breaks the PR's table-linking contract (docstring at retrieval.py:65: 'if a table was split into several chunks, the other chunks of the same table are its linked chunks'). The rule broken: every chunk of a split table may bring in related parts of the same table, within a bounded budget. tests/test_retrieval.py:308 asserts the defect: a seven-chunk table whose links are all empty.

Trigger: backstop, rounds 9.

- [P1] [P1] rag/retrieval/retrieval.py:80 — tables split into seven or more chunks lose all link expansion

## Failed fixes

- No fix has been tried for F7: the review says 'Correction then: none yet', and the repository has no F7 research page. What failed is the original design. _TABLE_LINK_MAX = 6 was added to keep long tables, such as requirement-list tables (comment at retrieval.py:25), from flooding the context with unrelated rows. The per-found-chunk cap _LINK_TOKENS = 600 (retrieval.py:26, applied in _with_links at 228-238) now bounds that expansion by itself, so the count cap does no bounding the token cap does not already do. It only cuts long tables off all-or-nothing. Whether the token cap came after the count cap could not be checked: no shell, no git log.

## Sources

### S1 — rag/retrieval/retrieval.py (branch retrieval-port/requirement-links at be56259)

- URL: rag/retrieval/retrieval.py
- Retrieved: 2026-10-19
- Locator: lines 25-26, 60-83, 228-238
- Fragment: _TABLE_LINK_MAX = 6  # 한 표가 이 개수 이하 청크로 나뉘었을 때만 같은 표 청크를 함께 담는다 (요구사항 목록표처럼 긴 표는 제외) / _LINK_TOKENS = 600 ... / if group[0] == "requirement" or len(members) <= _TABLE_LINK_MAX: ... return code_chunks, [sorted(linked - {i}) for i, linked in enumerate(links)] / for j in self.links[i]: cost = ...; if spent + cost <= _LINK_TOKENS: spent += cost; yield j, score
- Applicability: The defect line, the document-order link list, and the greedy token cap that would decide what a long table attaches once the count cap is gone.
- Counterevidence: The comment states the count cap's purpose (keeping long requirement-list tables out), which the fix must still answer.
- Validation: After the fix, links exist for tables of any size, and _with_links attaches the head and nearest members within 600 tokens.

### S2 — tests/test_retrieval.py and tests/test_v11_package.py

- URL: tests/test_retrieval.py
- Retrieved: 2026-10-19
- Locator: test_retrieval.py:308-314; test_v11_package.py:60-69
- Fragment: tables = [["t1"], ["t1"], *[["long"]] * 7] ... assert all(index.links[i] == [] for i in range(2, 9)) / table = [... for body in ["| 구분 | 값 |", "| 응답 | 3초 |"]] ... assert links == [[1], [0], [3], [2]]
- Applicability: The first test enshrines the defect and must be rewritten. The v11 fixture shows continuation chunks without a header row.
- Counterevidence: The v11 fixture is synthetic; real v11 continuation chunks may repeat headers.
- Validation: The rewritten test fails on the current code and passes after the fix; the v11 test still passes.

### S3 — rag/preprocessing/chunking.py and config.yaml

- URL: rag/preprocessing/chunking.py
- Retrieved: 2026-10-19
- Locator: chunking.py:61-77 (_split_table), 199-200; config.yaml:40-42, 58
- Fragment: """표를 size 글자 안쪽으로 행 단위 분할, 조각마다 헤더(캡션 줄 + 헤더 2줄)를 반복""" / chunk_size: 700 / table_size_factor: 2.0 # 표 청크는 chunk_size × 이 배수까지 허용 / token_budget: 2500
- Applicability: 01's own table chunks repeat the header, but v11 chunks pass table_refs through unchanged. Table chunks of up to 1400 characters mean the 600-token cap admits only a few linked chunks.
- Counterevidence: For 01-chunked tables the header is already in every chunk, so putting the head first matters only for v11 chunks.
- Validation: Measure the token sizes of table chunks in the active chunk file before choosing the ordering.

### S4 — Chunking for tables / structure-aware chunking guides (web search results)

- URL: https://blogs.oracle.com/developers/rag-chunking-and-parsing-for-tables-pdfs-transcripts-and-media
- Retrieved: 2026-10-19
- Locator: search result summaries for 'RAG table split across chunks retrieve sibling chunks header row'
- Fragment: A table split across a page break can get chunked into two pieces that make no sense independently, or lose its header row entirely. ... Tables are split mid-row or mid-column, making the data incomprehensible and breaking the semantic relationships between table headers and values. ... Structure-aware chunking should preserve: document title, section and parent headings, list context, table headers... Attach parent context to small chunks. ... risk of duplicate or redundant context if not deduped carefully.
- Applicability: Supports linking a found table piece back to its header and neighbouring rows rather than cutting long tables off.
- Counterevidence: These are practitioner blogs, not evaluations. They also warn that parent/sibling expansion adds redundant context, which the 600-token cap and _is_dup deduplication must hold down. Quotes come from the search engine's summaries of several pages (Oracle developers blog, twig.so, customgpt.ai); the pages themselves were not fetched.
- Validation: The dev retrieval-only rerun shows whether coverage gains outweigh lost budget.

### S5 — LlamaIndex API reference — PrevNextNodePostprocessor

- URL: https://developers.llamaindex.ai/python/framework-api-reference/postprocessor/prev_next/
- Retrieved: 2026-10-19
- Locator: class PrevNextNodePostprocessor: docstring, num_nodes, mode, _postprocess_nodes
- Fragment: Previous/Next Node post-processor. Allows users to fetch additional nodes from the document store, based on the relationships of the nodes. num_nodes: The number of nodes to return (default: 1). mode: The mode of the post-processor. Can be "previous", "next", or "both. ... In 'both' mode each direction is requested with num_nodes; results are inserted before or after the candidate by prev/next relationship. (Labelled beta in the docs; helper implementations not shown on the page.)
- Applicability: Prior art for bounded expansion to the nearest neighbours of each retrieved chunk, emitted in document position. That matches the proposed distance-first selection and document-order output.
- Counterevidence: It bounds by node count, not tokens, and has no header-first rule. Whether num_nodes applies per direction could not be confirmed from the page.
- Validation: The unit test shows a found mid-table chunk getting its neighbour(s) under the cap.

## Claims

- C1 (source; S1, S2): With more than 6 chunks under one table_ref, _link_index gives every member an empty link list, and the test at tests/test_retrieval.py:308 asserts exactly that.
- C2 (interpretation; S1): _LINK_TOKENS = 600 already bounds the linked tokens added per found chunk, so the count cap adds only an all-or-nothing cut-off.
- C3 (interpretation; S1): Removing the count cap alone would fill the 600-token cap in document order, attaching a long table's first rows instead of the found chunk's neighbouring rows.
- C4 (source; S2, S3): In the v11 fixture continuation chunks do not repeat the header, while 01's own _split_table repeats it in every piece.
- C5 (interpretation; S3): Table chunks can reach 1400 characters, so the order in which links fill the 600-token cap decides which parts get attached.
- C6 (source; S4, S5): Practice recommends keeping table headers and neighbouring context with split pieces, and bounding expansion per retrieved node, while warning about redundant context.
- C7 (interpretation; S1, S5): Choosing links head-first then by distance under the token cap, and emitting them in document order, satisfies the table-linking contract for tables of any size without changing requirement-group behaviour.

## Core theory

Neighbour-expansion retrieval fetches the nodes adjacent to a retrieved node through stored previous/next relationships, bounded by a node count per direction (LlamaIndex PrevNextNodePostprocessor: num_nodes, mode previous/next/both). Chunking guides warn that a table split mid-table yields pieces that are unintelligible alone or have lost their header row, and recommend keeping the header or parent context with each piece. Together: expansion should be bounded per retrieved chunk and should reach the closest structural context (the header, then the neighbours). It should not be switched off by the size of the whole structure.

## Applicability

rag/retrieval/retrieval.py:60-83 (_link_index builds table groups from table_refs and drops groups with more than 6 members) and 228-238 (_with_links walks links[i] in index order under _LINK_TOKENS). The v11 package loader (rag/preprocessing/chunking.py:199-200) passes table_refs through. The tests/test_v11_package.py:60 fixture shows that a v11 continuation chunk ('| 응답 | 3초 |') does not repeat the header, so the header lives only in the first chunk. 01's own splitter (_split_table, chunking.py:61-77) repeats the header in every piece, so for those chunks the gap is continuation rows, not the header. Table chunks are up to chunk_size × table_size_factor = 1400 characters (config.yaml:40-42), so 600 tokens may hold only one or two linked table chunks. That is why the order the cap is filled in decides what gets attached.

## Hypothesis

The cause is a count threshold that switches linking off for a whole table, when expansion should be bounded per found chunk. Deleting the threshold alone would not satisfy the contract either. _link_index returns links in document order (sorted(linked - {i})), and _with_links fills the 600-token cap greedily in that order. For a chunk deep in a long table, the cap would fill with the table's first rows and almost never reach the neighbouring rows i-1 and i+1, the continuation. The fix that would hold: (1) delete _TABLE_LINK_MAX and the length check at line 80; (2) choose linked chunks by priority under the 600-token cap: the table's first chunk (header and caption, which v11 continuation chunks lack) first, then the others by distance |j-i|; (3) yield the chosen chunks in document order, so the context the LLM sees keeps its order. Requirement groups have 2-3 chunks, where distance order equals document order, so their current behaviour and tests stay the same.

## Counterevidence

- The count cap was added on purpose against requirement-list tables. Without it, every hit in a long list table can add up to 600 tokens of rows from the same table, which may be unrelated, out of a 2500-token budget (config.yaml:58). That can push out other documents' evidence and lower Evidence Coverage (B), though Ranking (A) metrics do not change because they use candidates before packing.
- If a table chunk costs more than 600 tokens, no linked chunk fits whatever the order, and the fix changes nothing for that table.
- For chunks from 01's own splitter (header repeated), putting the first chunk first spends cap on a header the hit already has. Distance order alone would be better there.

## Alternatives

- Delete _TABLE_LINK_MAX only and keep document order, as the review implies ('the existing 600-token cap already bounds expansion'). This is the smallest diff, but deep in a long table it attaches the first rows instead of the neighbours, so the continuation stays missing. Use it only if measured table chunks are small enough that 600 tokens usually reaches i±1.
- Raise _TABLE_LINK_MAX. This moves the cliff instead of removing it, and the review's point would still apply to the next larger table.
- A fixed window (head + i±1) for long tables and full linking for short ones. That is two rules where one priority order under the token cap covers both.
- Store each table's header as metadata and prepend it to continuation chunks in preprocessing. That needs a preprocessing change in another pipeline and a v11 package change, outside this PR's retrieval scope.

## Experiment

Unit level: replace tests/test_retrieval.py:308 with a table of 9 or more chunks, all cost 1 except a cap that fits only 2 links (for example cost 300 each). Find chunk 5 and expect the packed order [c5, then c0 and c4 (or c6) in document order]. The current code gives [c5]; a delete-only fix gives c0 and c1. Keep the existing short-table, cross-document and token-cap tests passing, plus test_v11_package links == [[1],[0],[3],[2]]. Pipeline level, no API calls: run rerun_retrieval on dev (not test) before and after, then 05's Retrieval evaluation only. Compare Evidence Coverage single and multi and the share of the 2500 budget taken by linked chunks, and report tables with more than 6 chunks by count.

## Result

Observed, not verified: this is still a draft. In the v12 team package (`corpus/chunks.jsonl`, counts only), 14,024 table groups keyed by (doc_id, table_ref) split into 13,410 single-chunk tables, 611 of 2-6 chunks and 3 of more than 6 (7 chunks each, 21 table chunks, none with a requirement_key). Those 21 chunks have a median of 670 o200k tokens (p90 790), so most of them cannot fit under the 600-token link cap whatever the order. In multi-chunk tables, 733 of 969 continuation chunks start with the same first line as the table's first chunk, and 236 do not, so putting the head first matters for about a quarter of continuations. The fix follows the hypothesis. `_TABLE_LINK_MAX` and the length check are deleted. A new `_link_priority` orders each chunk's links by (not the group's first chunk, distance, position). `_with_links` picks under `_LINK_TOKENS` in that order and yields the picked chunks in document order. `tests/test_retrieval.py::test_long_table_chunk_packs_the_table_head_and_its_nearest_row_in_document_order` replaces the test that asserted empty links: a 9-chunk table at 300 tokens per chunk, hit at c5. On the old code it gave `['c5']`; with the fix it gives `['c5', 'c0', 'c4']`. `tests/test_retrieval.py`, `tests/test_retrieval_benchmark.py` and `tests/test_v11_package.py` pass (74 passed; the v11 links stay `[[1], [0], [3], [2]]`), and ruff is clean. The commit is the one that carries this page ("retrieval: link long split tables by head and distance"). Not run: the pipeline-level dev `rerun_retrieval` and 05 Retrieval comparison. It needs an index built from this branch's search texts (`texts.sha256`), and only 3 tables change, so it could not show a measurable coverage difference.

## Unresolved limits

Not measured here: how many tables in the v12 package (18,989 chunks) have more than 6 chunks, how big table chunks are in embedding tokens, or how often a long-table hit lacks its header. No shell or git, so it is unconfirmed when and why the count cap and the token cap were added. LlamaIndex documents neighbour expansion by count, not by token budget or header priority; the head-first ordering is this page's reading, not a cited rule.
