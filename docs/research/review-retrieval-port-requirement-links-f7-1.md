# 리뷰 조사 · F7, 1회차

PR #70 리뷰 9회차의 수정 전에 2026-10-19에 쓴 조사 초안입니다. 검증된 사실이나 공용 규칙이 아니며, 리뷰는 이 문서를 수정과 함께 읽습니다.

## 문제

F7(P1, be56259의 9회차): rag/retrieval/retrieval.py:80은 나뉜 표의 청크를, 그 표가 _TABLE_LINK_MAX = 6개 이하의 청크일 때만 서로 연결합니다. 일곱 개 이상의 청크로 나뉜 표는 표 연결을 전혀 받지 못하므로, 검색이 한 조각을 찾아도 머리글, 관련 행, 이어지는 부분을 담은 조각이 함께 담기지 않습니다. 이는 PR의 표 연결 약속(retrieval.py:65의 docstring: 'if a table was split into several chunks, the other chunks of the same table are its linked chunks')을 깹니다. 깨진 규칙: 나뉜 표의 모든 청크는 정해진 예산 안에서 같은 표의 관련 부분을 데려올 수 있어야 합니다. tests/test_retrieval.py:308은 바로 이 결함을 단정합니다. 일곱 청크 표의 연결이 모두 비어 있다고 봅니다.

발생: 최후 확인(backstop), 9회차.

- [P1] [P1] rag/retrieval/retrieval.py:80 — 일곱 개 이상 청크로 나뉜 표는 연결 확장을 모두 잃습니다

## 실패한 수정

- F7에는 아직 시도한 수정이 없습니다. 리뷰에는 'Correction then: none yet'이라고 되어 있고, 저장소에 F7 조사 문서도 없습니다. 실패한 것은 원래 설계입니다. _TABLE_LINK_MAX = 6은 요구사항 목록표 같은 긴 표(retrieval.py:25의 주석)가 관련 없는 행으로 문맥을 채우지 않게 하려고 더했습니다. 찾은 청크마다 거는 상한 _LINK_TOKENS = 600(retrieval.py:26, 228-238의 _with_links에서 적용)이 이제 혼자서 그 확장을 제한하므로, 개수 상한은 토큰 상한이 이미 하지 않는 제한을 더하지 않습니다. 긴 표를 전부 아니면 전무로 잘라 낼 뿐입니다. 토큰 상한이 개수 상한 뒤에 들어왔는지는 확인하지 못했습니다(shell도 git log도 없음).

## 출처

### S1 — rag/retrieval/retrieval.py (브랜치 retrieval-port/requirement-links, be56259)

- URL: rag/retrieval/retrieval.py
- 확인일: 2026-10-19
- 위치: 25-26, 60-83, 228-238행
- 인용: _TABLE_LINK_MAX = 6  # 한 표가 이 개수 이하 청크로 나뉘었을 때만 같은 표 청크를 함께 담는다 (요구사항 목록표처럼 긴 표는 제외) / _LINK_TOKENS = 600 ... / if group[0] == "requirement" or len(members) <= _TABLE_LINK_MAX: ... return code_chunks, [sorted(linked - {i}) for i, linked in enumerate(links)] / for j in self.links[i]: cost = ...; if spent + cost <= _LINK_TOKENS: spent += cost; yield j, score
- 적용: 결함이 있는 행, 문서 순서의 연결 목록, 그리고 개수 상한을 없앤 뒤 긴 표가 무엇을 붙일지 정할 탐욕적 토큰 상한입니다.
- 반대 근거: 주석이 개수 상한의 목적(긴 요구사항 목록표 빼기)을 밝히며, 수정은 여전히 이에 답해야 합니다.
- 검증: 수정 뒤에는 크기와 상관없이 표에 연결이 있고, _with_links가 600토큰 안에서 첫 조각과 가장 가까운 조각을 붙입니다.

### S2 — tests/test_retrieval.py와 tests/test_v11_package.py

- URL: tests/test_retrieval.py
- 확인일: 2026-10-19
- 위치: test_retrieval.py:308-314; test_v11_package.py:60-69
- 인용: tables = [["t1"], ["t1"], *[["long"]] * 7] ... assert all(index.links[i] == [] for i in range(2, 9)) / table = [... for body in ["| 구분 | 값 |", "| 응답 | 3초 |"]] ... assert links == [[1], [0], [3], [2]]
- 적용: 앞의 테스트는 결함을 굳혀 두므로 다시 써야 합니다. v11 테스트 데이터는 머리글 행 없는 이어지는 청크를 보여 줍니다.
- 반대 근거: v11 테스트 데이터는 합성이며, 실제 v11의 이어지는 청크는 머리글을 되풀이할 수 있습니다.
- 검증: 다시 쓴 테스트가 지금 코드에서 실패하고 수정 뒤 통과하며, v11 테스트는 계속 통과합니다.

### S3 — rag/preprocessing/chunking.py와 config.yaml

- URL: rag/preprocessing/chunking.py
- 확인일: 2026-10-19
- 위치: chunking.py:61-77 (_split_table), 199-200; config.yaml:40-42, 58
- 인용: """표를 size 글자 안쪽으로 행 단위 분할, 조각마다 헤더(캡션 줄 + 헤더 2줄)를 반복""" / chunk_size: 700 / table_size_factor: 2.0 # 표 청크는 chunk_size × 이 배수까지 허용 / token_budget: 2500
- 적용: 01이 직접 만든 표 청크는 머리글을 되풀이하지만, v11 청크는 table_refs를 그대로 넘깁니다. 표 청크가 1400자까지 되므로, 600토큰 상한에는 연결 청크가 몇 개만 들어갑니다.
- 반대 근거: 01이 나눈 표는 이미 청크마다 머리글이 있으므로, 첫 조각을 먼저 두는 것은 v11 청크에서만 의미가 있습니다.
- 검증: 순서를 고르기 전에, 지금 쓰는 청크 파일에서 표 청크의 토큰 크기를 잽니다.

### S4 — 표 청크 나누기·구조 인식 청크 나누기 안내(웹 검색 결과)

- URL: https://blogs.oracle.com/developers/rag-chunking-and-parsing-for-tables-pdfs-transcripts-and-media
- 확인일: 2026-10-19
- 위치: 'RAG table split across chunks retrieve sibling chunks header row' 검색 결과 요약
- 인용: A table split across a page break can get chunked into two pieces that make no sense independently, or lose its header row entirely. ... Tables are split mid-row or mid-column, making the data incomprehensible and breaking the semantic relationships between table headers and values. ... Structure-aware chunking should preserve: document title, section and parent headings, list context, table headers... Attach parent context to small chunks. ... risk of duplicate or redundant context if not deduped carefully.
- 적용: 긴 표를 잘라 내지 말고, 찾은 표 조각을 그 머리글과 이웃 행에 다시 이어 주자는 쪽을 뒷받침합니다.
- 반대 근거: 실무자 블로그이지 평가가 아닙니다. 부모·형제 확장이 겹치는 문맥을 더한다고도 경고하므로, 600토큰 상한과 _is_dup 중복 제거가 이를 억눌러야 합니다. 인용은 여러 페이지(Oracle 개발자 블로그, twig.so, customgpt.ai)에 대한 검색 엔진 요약에서 왔고, 페이지 자체는 가져오지 않았습니다.
- 검증: dev 검색 전용 재실행으로, 근거 포함률이 오르는 효과가 잃는 예산보다 큰지 봅니다.

### S5 — LlamaIndex API 참조: PrevNextNodePostprocessor

- URL: https://developers.llamaindex.ai/python/framework-api-reference/postprocessor/prev_next/
- 확인일: 2026-10-19
- 위치: class PrevNextNodePostprocessor: docstring, num_nodes, mode, _postprocess_nodes
- 인용: Previous/Next Node post-processor. Allows users to fetch additional nodes from the document store, based on the relationships of the nodes. num_nodes: The number of nodes to return (default: 1). mode: The mode of the post-processor. Can be "previous", "next", or "both. ... 'both' 모드에서는 방향마다 num_nodes를 요청하고, 결과는 prev/next 관계에 따라 후보 앞이나 뒤에 끼워 넣습니다. (문서에는 beta로 표시되어 있고, 도우미 구현은 페이지에 없습니다.)
- 적용: 찾은 청크마다 가장 가까운 이웃으로 제한해 넓히고 문서 위치 순으로 내보내는 선례입니다. 제안한 거리 우선 고르기와 문서 순서 출력에 맞습니다.
- 반대 근거: 토큰이 아니라 노드 개수로 제한하며, 머리글 우선 규칙이 없습니다. num_nodes가 방향마다 적용되는지는 페이지로 확인하지 못했습니다.
- 검증: 단위 테스트로, 찾은 표 가운데 청크가 상한 안에서 이웃을 받는지 보입니다.

## 주장

- C1 (출처; S1, S2): 한 table_ref 아래 청크가 6개보다 많으면 _link_index는 모든 구성원에게 빈 연결 목록을 주며, tests/test_retrieval.py:308의 테스트가 정확히 그것을 단정합니다.
- C2 (해석; S1): _LINK_TOKENS = 600이 이미 찾은 청크마다 더하는 연결 토큰을 제한하므로, 개수 상한은 전부 아니면 전무인 잘라 내기만 더합니다.
- C3 (해석; S1): 개수 상한만 지우면 600토큰 상한이 문서 순서로 채워져, 찾은 청크의 이웃 행이 아니라 긴 표의 첫 행들이 붙습니다.
- C4 (출처; S2, S3): v11 테스트 데이터에서 이어지는 청크는 머리글을 되풀이하지 않고, 01의 _split_table은 조각마다 되풀이합니다.
- C5 (해석; S3): 표 청크가 1400자까지 될 수 있으므로, 연결이 600토큰 상한을 채우는 순서가 어떤 부분이 붙을지 정합니다.
- C6 (출처; S4, S5): 실무에서는 나뉜 조각과 함께 표 머리글과 이웃 문맥을 지키고, 찾은 노드마다 확장을 제한하라고 권하며, 겹치는 문맥을 경고합니다.
- C7 (해석; S1, S5): 토큰 상한 안에서 첫 조각을 먼저, 그다음 거리 순으로 연결을 고르고 문서 순서로 내보내면, 요구사항 묶음 동작을 바꾸지 않고 어떤 크기의 표든 표 연결 약속을 지킵니다.

## 핵심 원리

이웃 확장 검색은 저장된 이전/다음 관계를 따라 찾은 노드에 붙은 노드를 가져오며, 방향마다 노드 개수로 제한합니다(LlamaIndex PrevNextNodePostprocessor: num_nodes, mode previous/next/both). 청크 나누기 안내는 표를 중간에서 나누면 조각 혼자로는 알아볼 수 없거나 머리글 행을 잃는다고 경고하고, 조각마다 머리글이나 부모 문맥을 함께 두라고 권합니다. 둘을 합치면, 확장은 찾은 청크마다 제한하고 가장 가까운 구조 문맥(머리글, 그다음 이웃)에 닿아야 합니다. 구조 전체의 크기 때문에 꺼지면 안 됩니다.

## 적용

rag/retrieval/retrieval.py:60-83(_link_index가 table_refs로 표 묶음을 만들고 구성원이 6개보다 많은 묶음을 버림)과 228-238(_with_links가 _LINK_TOKENS 안에서 links[i]를 index 순서로 훑음)입니다. v11 묶음 로더(rag/preprocessing/chunking.py:199-200)는 table_refs를 그대로 넘깁니다. tests/test_v11_package.py:60의 테스트 데이터는 v11의 이어지는 청크('| 응답 | 3초 |')가 머리글을 되풀이하지 않아, 머리글이 첫 청크에만 있다는 것을 보여 줍니다. 01의 분할기(_split_table, chunking.py:61-77)는 조각마다 머리글을 되풀이하므로, 그 청크에서 빠진 것은 머리글이 아니라 이어지는 행입니다. 표 청크는 chunk_size × table_size_factor = 1400자까지 되므로(config.yaml:40-42), 600토큰에는 연결된 표 청크가 한두 개만 들어갈 수 있습니다. 그래서 상한을 채우는 순서가 무엇이 붙을지 정합니다.

## 가설

원인은, 확장을 찾은 청크마다 제한해야 하는데 개수 문턱이 표 전체의 연결을 꺼 버리는 것입니다. 문턱만 지워도 약속을 지키지 못합니다. _link_index는 연결을 문서 순서(sorted(linked - {i}))로 돌려주고, _with_links는 그 순서로 600토큰 상한을 탐욕적으로 채웁니다. 긴 표 깊숙한 청크라면 상한이 표의 첫 행들로 차서, 이어지는 부분인 이웃 행 i-1과 i+1에 거의 닿지 못합니다. 버틸 수정은 이렇습니다. (1) _TABLE_LINK_MAX와 80행의 길이 확인을 지웁니다. (2) 600토큰 상한 안에서 우선순위로 연결 청크를 고릅니다. 표의 첫 청크(v11의 이어지는 청크에 없는 머리글과 캡션)를 먼저, 그다음 나머지를 거리 |j-i| 순으로 고릅니다. (3) 고른 청크를 문서 순서로 내보내, LLM이 보는 문맥의 순서를 지킵니다. 요구사항 묶음은 청크가 2~3개라 거리 순서가 문서 순서와 같으므로, 지금 동작과 테스트는 그대로입니다.

## 반대 근거

- 개수 상한은 요구사항 목록표를 막으려고 일부러 더한 것입니다. 이것이 없으면 긴 목록표에서 찾을 때마다, 2500토큰 예산(config.yaml:58) 가운데 같은 표의, 관련 없을 수도 있는 행이 600토큰까지 더해질 수 있습니다. 그러면 다른 문서의 근거가 밀려나 근거 포함률(Evidence Coverage, B)이 떨어질 수 있습니다. 다만 순위(A) 지표는 담기 전 후보를 쓰므로 바뀌지 않습니다.
- 표 청크 하나가 600토큰보다 크면 순서와 상관없이 연결 청크가 하나도 들어가지 않으며, 그 표에는 수정이 아무것도 바꾸지 않습니다.
- 01의 분할기에서 나온 청크(머리글 되풀이)에서는, 첫 청크를 먼저 두면 찾은 조각에 이미 있는 머리글에 상한을 씁니다. 거기서는 거리 순서만 쓰는 편이 낫습니다.

## 다른 방법

- 리뷰가 암시하듯('the existing 600-token cap already bounds expansion') _TABLE_LINK_MAX만 지우고 문서 순서를 유지하기. 가장 작은 diff지만, 긴 표 깊숙한 곳에서는 이웃이 아니라 첫 행들을 붙이므로 이어지는 부분은 계속 빠집니다. 잰 표 청크가 충분히 작아 600토큰이 대개 i±1에 닿을 때만 씁니다.
- _TABLE_LINK_MAX 올리기. 절벽을 없애지 않고 옮길 뿐이며, 리뷰의 지적은 다음으로 큰 표에 그대로 적용됩니다.
- 긴 표에는 고정 창(첫 조각 + i±1), 짧은 표에는 전체 연결. 토큰 상한 아래 우선순위 하나로 둘 다 덮을 수 있는데 규칙이 둘이 됩니다.
- 전처리에서 표마다 머리글을 메타데이터로 저장해 이어지는 청크 앞에 붙이기. 다른 파이프라인의 전처리 변경과 v11 묶음 변경이 필요해, 이 PR의 검색 범위를 벗어납니다.

## 실험

단위 수준: tests/test_retrieval.py:308을 청크 9개 이상인 표로 바꾸되, 상한에 연결이 2개만 들어가도록 비용을 둡니다(예: 청크마다 300). 청크 5를 찾게 하고, 담기는 순서로 [c5, 그다음 문서 순서로 c0과 c4(또는 c6)]를 기대합니다. 지금 코드는 [c5]를 내고, 지우기만 한 수정은 c0과 c1을 냅니다. 기존의 짧은 표, 문서 간, 토큰 상한 테스트와 test_v11_package의 links == [[1],[0],[3],[2]]가 계속 통과하게 합니다. 파이프라인 수준(API 호출 없음): 수정 전후로 dev(test 아님)에서 rerun_retrieval을 돌리고, 05의 Retrieval 평가만 합니다. 단일·다중 근거 포함률(Evidence Coverage)과 2500 예산 가운데 연결 청크가 차지하는 비율을 비교하고, 청크가 6개보다 많은 표의 수를 보고합니다.

## 결과

관측했지만 검증하지 않았으며, 여전히 초안입니다. v12 팀 묶음(`corpus/chunks.jsonl`, 개수만 셈)에서 (doc_id, table_ref)로 묶은 표 14,024개는 청크 하나짜리 13,410개, 2~6개짜리 611개, 6개 초과 3개(각 7청크, 표 청크 21개, requirement_key 있는 것 없음)로 나뉩니다. 그 21청크의 o200k 토큰 중앙값은 670(p90 790)이라, 대부분은 순서와 상관없이 600토큰 연결 상한에 들어가지 못합니다. 여러 청크로 된 표에서, 이어지는 청크 969개 가운데 733개는 표의 첫 청크와 같은 첫 줄로 시작하고 236개는 그렇지 않으므로, 첫 조각을 먼저 두는 것은 이어지는 청크의 약 4분의 1에 의미가 있습니다. 수정은 가설을 따릅니다. `_TABLE_LINK_MAX`와 길이 확인을 지웠습니다. 새 `_link_priority`가 청크마다 연결을 (묶음의 첫 청크가 아님, 거리, 위치) 순으로 정렬합니다. `_with_links`는 그 순서로 `_LINK_TOKENS` 안에서 고르고, 고른 청크를 문서 순서로 내보냅니다. `tests/test_retrieval.py::test_long_table_chunk_packs_the_table_head_and_its_nearest_row_in_document_order`가 빈 연결을 단정하던 테스트를 대신합니다. 청크마다 300토큰인 9청크 표에서 c5를 찾습니다. 예전 코드는 `['c5']`를, 수정 뒤에는 `['c5', 'c0', 'c4']`를 냅니다. `tests/test_retrieval.py`, `tests/test_retrieval_benchmark.py`, `tests/test_v11_package.py`가 통과하고(74 passed; v11 연결은 `[[1], [0], [3], [2]]` 그대로), ruff도 깨끗합니다. 커밋은 이 문서를 담은 것("retrieval: link long split tables by head and distance")입니다. 돌리지 않은 것: 파이프라인 수준의 dev `rerun_retrieval`과 05 Retrieval 비교입니다. 이 브랜치의 검색 글(`texts.sha256`)로 만든 index가 필요하고, 바뀌는 표가 3개뿐이라 잴 만한 포함률 차이를 보일 수 없었습니다.

## 남은 한계

여기서 재지 않은 것: v12 묶음(18,989청크)에서 청크가 6개보다 많은 표가 몇 개인지, 표 청크가 임베딩 토큰으로 얼마나 큰지, 긴 표를 찾았을 때 머리글이 없는 경우가 얼마나 잦은지. shell과 git이 없어서, 개수 상한과 토큰 상한이 언제 왜 들어왔는지 확인하지 못했습니다. LlamaIndex는 이웃 확장을 개수로 설명할 뿐, 토큰 예산이나 머리글 우선은 다루지 않습니다. 첫 조각 우선 순서는 이 문서의 해석이지, 인용한 규칙이 아닙니다.
