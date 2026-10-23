# 리뷰 조사 · F7, 2회차

PR #70 리뷰 10회차의 수정 전에 2026-10-19에 쓴 조사 초안입니다. 검증된 사실이나 공용 규칙이 아니며, 리뷰는 이 문서를 수정과 함께 읽습니다.

## 문제

F7(PR #70): 길게 나뉜 표에서 찾은 청크는 정해진 예산 안에서 같은 표의 관련 부분(머리글 청크와 가장 가까운 이어지는 행)을 문맥에 데려올 수 있어야 합니다. 수정 전에는 청크가 6개보다 많은 표가 연결을 전혀 받지 못했습니다(_TABLE_LINK_MAX). 6510eea의 수정은 그 잘라 내기를 없애고, _LINK_TOKENS = 600 안에서 연결을 (첫 청크가 아님, 거리, 위치) 순으로 정렬합니다. 이 불변 조건은 고른 청크가 실제로 담긴 문맥에 들어가고, 실제 표 청크가 상한 안에 들어갈 때만 지켜집니다. 실제 데이터에서는 둘 다 보이지 않았습니다.

발생: 반복, 9·10회차.

- [P1] [P1] rag/retrieval/retrieval.py:244 — 거부된 연결이 담기 전에 연결 예산을 써 버려, 쓸 수 있는 연결 근거가 고려되지 않습니다

## 실패한 수정

- 6510eea('retrieval: link long split tables by head and distance')는 _TABLE_LINK_MAX를 지우고, _link_priority(첫 조각 먼저, 그다음 거리)를 더했으며, _with_links가 그 순서로 600토큰 상한을 채우고 고른 것을 문서 순서로 내보내게 했습니다. 청크마다 300토큰인 합성 9청크 테스트(['c5','c0','c4'])는 통과했습니다. 버티지 못한 이유는 셋입니다. (1) 연결은 _with_links에서 고르는데, 이 생성기는 _pack의 확인(이미 고름(i == j), 거의 같은 중복(_is_dup), 2500토큰 예산)보다 먼저 돕니다. 이미 문맥에 있거나 중복으로 빠지는 첫 조각도 600토큰 상한 일부를 쓰므로, 그 때문에 밀려난 이웃은 끝내 오지 않습니다. 또 _pack이 찾은 청크 자체를 건너뛸 때도 연결은 내보내집니다. (2) 1회차가 직접 센 결과로, v12 묶음의 긴 표 21청크는 중앙값 670토큰(p90 790)이었으므로, 대부분의 경우 어떤 순서로도 600 안에 연결이 들어가지 않습니다. 실제 데이터에서 긴 표는 여전히 연결을 잃으며, 이것이 F7 증상입니다. (3) 그 셈은 o200k 토크나이저를 썼지만, 상한과 예산은 Embedder.token_counts(KURE-v1, XLM-R SentencePiece 토크나이저)로 잽니다. 그래서 크기 증거조차 단위가 틀렸습니다.

## 출처

### S1 — 6510eea의 rag/retrieval/retrieval.py

- URL: rag/retrieval/retrieval.py
- 확인일: 2026-10-19
- 위치: 25, 81-90, 235-266행
- 인용: _LINK_TOKENS = 600 ... for j in self.links[i]: cost = self.embedder.token_counts([self.chunks[j]["body"]])[0]; if spent + cost <= _LINK_TOKENS: spent += cost; chosen.append(j) / for j in sorted(chosen): yield j, score ... (in _pack) if any(i == j or (... _is_dup(words, seen)) for j, _, seen in picked): continue ... if picked and used + cost > budget: continue
- 적용: 연결 상한이 _pack의 이미 고름·중복·예산 확인보다 앞서 _with_links에서 쓰이고, 찾은 청크가 나중에 건너뛰어져도 연결은 내보내진다는 것을 보여 줍니다.
- 반대 근거: 앞서 찾은 것 가운데 같은 표의 청크를 담은 것이 없고 거의 같은 중복도 없다면, 담기 전에 골라도 결과는 같습니다.
- 검증: 수정 뒤에는 찾은 청크를 받아들인 다음 _pack 안에서 연결을 고르고, 건너뛴 연결은 셈하지 않습니다.

### S2 — tests/test_retrieval.py

- URL: tests/test_retrieval.py
- 확인일: 2026-10-19
- 위치: 308-312, 322-325행
- 인용: index = make_index([f"표 {i}" for i in range(9)], [300] * 9, tables=[["t1"]] * 9) / assert [hit["chunk_id"] for hit in index._pack([(5, 0.9)])] == ["c5", "c0", "c4"]
- 적용: 하나뿐인 긴 표 테스트는 찾은 것 하나와 300토큰 청크를 쓰므로, 이미 담긴 첫 조각도 상한보다 큰 청크도 확인하지 않습니다.
- 반대 근거: 순서 자체를 확인하는 데는 합성 크기로 충분합니다.
- 검증: 이미 담긴 첫 조각과 건너뛴 찾은 청크를 다루는 새 테스트가 6510eea에서 실패하고 수정 뒤 통과합니다.

### S3 — 리뷰 조사 · F7, 1회차(결과 절)

- URL: docs/research/review-retrieval-port-requirement-links-f7-1.md
- 확인일: 2026-10-19
- 위치: ## 결과
- 인용: 6개 초과 3개(각 7청크, 표 청크 21개, requirement_key 있는 것 없음). 그 21청크의 o200k 토큰 중앙값은 670(p90 790)이라, 대부분은 순서와 상관없이 600토큰 연결 상한에 들어가지 못합니다. ... 돌리지 않은 것: 파이프라인 수준의 dev `rerun_retrieval`과 05 Retrieval 비교입니다.
- 적용: 실제 v12 묶음에서 잰 값입니다. 긴 표 청크 대부분이 상한보다 크지만, 임베딩 토크나이저가 아니라 o200k로 쟀습니다.
- 반대 근거: 앞 회차에서 개수만 센 것이며, 단위가 코드와 달라 실제 KURE 크기는 더 작거나 클 수 있습니다.
- 검증: 같은 21청크를 Embedder.token_counts로 다시 잽니다.

### S4 — LlamaIndex core: postprocessor/node.py (PrevNextNodePostprocessor)

- URL: https://raw.githubusercontent.com/run-llama/llama_index/main/llama-index-core/llama_index/core/postprocessor/node.py
- 확인일: 2026-10-19
- 위치: PrevNextNodePostprocessor._postprocess_nodes; get_forward_nodes / get_backward_nodes
- 인용: all_nodes: Dict[str, NodeWithScore] = {} ... all_nodes[node.node.node_id] = node ... all_nodes.update(...) — 이웃은 node id로 합쳐지므로 이미 있는 노드는 한 번만 남습니다(점수는 점수 없는 이웃 사본으로 덮일 수 있음). 결과는 prev/next 관계에 따라 노드 앞뒤에 놓여 문서 순서가 됩니다. 이웃 수는 토큰이 아니라 num_nodes로 제한됩니다. (가져오기 도구가 소스 파일에서 요약한 내용)
- 적용: 이웃을 세기 전에 정체로 합치고 문서 순서로 내보내는 선례입니다. _with_links는 _pack의 정체 확인보다 먼저 돌기 때문에 이 동작이 없습니다.
- 반대 근거: LlamaIndex에는 토큰 예산이 없으므로, 중복 제거 뒤에 상한을 셈하는 것은 확장이지 LlamaIndex가 문서로 정한 것이 아닙니다. 점수 덮어쓰기 버릇을 보면 그 합치기를 그대로 베낄 모범은 아닙니다.
- 검증: 고친 _pack에서 이미 고른 연결은 더하지도 셈하지도 않습니다.

### S5 — KURE v1 onnx int8 (Hugging Face 모델 카드)

- URL: https://huggingface.co/LaraAI-Labs/KURE-v1-onnx-int8
- 확인일: 2026-10-19
- 위치: 모델 설명; 사양 절
- 인용: nlpai-lab/KURE-v1 (BGE-M3 한국어 파인튜닝)의 ONNX INT8 변환본 ... XLM-R SentencePiece (sentencepiece.bpe.model 동봉 — xlm-roberta-large/BGE-M3 와 동일, sha256 cfc8146a…). 카드에 최대 시퀀스 길이는 적혀 있지 않습니다.
- 적용: 상한과 예산은 KURE-v1의 토크나이저(Embedder.token_counts)로 세며, 이는 1회차가 쓴 o200k가 아니라 XLM-R SentencePiece입니다.
- 반대 근거: nlpai-lab 자신의 카드가 아니라 제3자 변환 카드이며, 한국어 토큰 수는 주지 않습니다.
- 검증: 긴 표 청크 크기를 Embedder.token_counts로 다시 잽니다.

### S6 — config.yaml

- URL: config.yaml
- 확인일: 2026-10-19
- 위치: 40-42, 47, 58행
- 인용: chunk_size: 700 # 글자 단위 / table_size_factor: 2.0 # 표 청크는 chunk_size × 이 배수까지 허용(행 단위 분할, 헤더 반복) / model: nlpai-lab/KURE-v1 / token_budget: 2500 # 검색 결과 본문 토큰 예산 (임베딩 토크나이저 기준)
- 적용: 표 청크는 1400자까지 될 수 있고, 예산 단위는 임베딩 토크나이저입니다.
- 반대 근거: v12 묶음은 앞 단계에서 청크를 나누므로, 이 한도는 01의 분할기를 설명할 뿐 v12 청크를 꼭 설명하지는 않습니다.
- 검증: 잰 크기를 같은 단위로 상한과 비교합니다.

## 주장

- C1 (출처; S1): _with_links는 _pack의 이미 고름·거의 같은 중복·예산 확인보다 먼저 600토큰 연결 상한을 쓰고, 찾은 청크가 나중에 건너뛰어져도 연결을 내보냅니다.
- C2 (해석; S1, S2): 수정은 300토큰 합성 청크에서 찾은 것 하나로만 확인했으므로, 이미 담긴 청크나 상한보다 큰 청크에서 상한이 낭비되는 것을 드러낼 수 없습니다.
- C3 (출처; S3): v12 묶음에서 긴 표 청크의 o200k 토큰 중앙값은 670으로 600 상한보다 크므로, 긴 표를 찾아도 대부분 연결이 붙지 않습니다.
- C4 (해석; S3, S5, S6): 상한은 KURE-v1의 XLM-R SentencePiece 토크나이저로 재는데 크기 증거는 o200k를 썼으므로, 수정의 크기 가정은 상한의 단위로 확인되지 않았습니다.
- C5 (해석; S4): 정착된 이웃 확장은 이웃을 노드 정체로 합치고 문서 순서로 돌려줍니다. 실제로 더한 연결에만 상한을 셈하는 것은 거기서 따라 나옵니다.

## 핵심 원리

정착된 검색기의 이웃 확장은 가져온 이웃을 노드 정체를 키로 결과 집합에 합치므로, 이미 있는 이웃은 다시 더하거나 세지 않고, 합친 집합을 문서 순서로 돌려줍니다(LlamaIndex PrevNextNodePostprocessor: node_id를 키로 한 all_nodes, update()로 합치기, 사슬 순서 출력). 예산 확인은 실제로 남는 것을, 예산을 정의한 단위로 잴 때만 의미가 있습니다. 여기 임베더는 XLM-R SentencePiece 토크나이저를 쓰는 BGE-M3 파인튜닝 KURE-v1이며, 1회차 측정에 쓴 o200k 토크나이저가 아닙니다.

## 적용

rag/retrieval/retrieval.py:235-248(_with_links가 중복 제거 전에 _LINK_TOKENS를 채움)과 250-266(_pack은 그 뒤에야 i == j 확인, _is_dup, token_budget을 돌림)입니다. rag/retrieval/retrieval.py:25가 _LINK_TOKENS = 600을 정하고, config.yaml:58은 token_budget을 임베딩 토크나이저(KURE-v1, config.yaml:47)로 센다고 적습니다. docs/research/review-retrieval-port-requirement-links-f7-1.md(결과)에 적힌 v12 수치는 실제 긴 표 청크가 상한보다 크다는 것을 보여 줍니다. tests/test_retrieval.py:308-312는 300토큰 합성 경우만 확인하므로, 두 실패 어느 쪽도 잡지 못합니다.

## 가설

결함은 연결의 순서가 아니라, 연결 고르기를 어디서 어떤 단위로 재느냐에 있습니다. 600토큰 상한은 _pack이 실제로 문맥에 무엇을 넣을지 정하기 전의 후보 목록에 적용되고, 수정은 실제 표 청크가 아니라 테스트 데이터 크기로, 그것도 상한과 다른 단위로 확인했습니다. 버틸 수정은 이렇습니다. (a) 연결 고르기를 _pack 안으로 옮깁니다. 찾은 청크를 실제로 고른 뒤에만 links[i]를 _link_priority 순서로 훑고, 이미 고른 청크나 거의 같은 중복은 상한에 셈하지 않고 건너뛰며, 실제로 더한 청크만 셈합니다. (b) 긴 표 청크를 Embedder.token_counts로 재고, 상한보다 크면 나뉜 표가 최소한 가장 가까운 부분을 어떻게 얻을지 분명히 정합니다. 방법은 둘입니다. _pack이 이미 첫 청크를 예산을 넘어도 남기듯, 2500 예산에 아직 들어가는 가장 높은 우선순위 연결을 늘 받아들이거나, 잰 최대 표 청크로 _LINK_TOKENS 크기를 정합니다. (b)가 없으면 순서가 어떻든 v12 데이터에서 불변 조건이 지켜질 수 없습니다.

## 반대 근거

- 10회차 리뷰 글은 여기서 볼 수 없었습니다. 거부 이유는 코드와 1회차 수치에서 짐작한 것이므로, 리뷰는 문맥 넘침이나 파이프라인 측정 누락 같은 다른 이유로 거부했을 수 있습니다.
- v12에서 청크가 6개보다 많은 표는 3개(21청크)뿐이라, 수정이 무엇을 하든 dev 검색 지표에 대한 효과는 너무 작아 잴 수 없을지도 모릅니다.
- 그 청크들의 KURE 토큰 수가 600보다 작다면(XLM-R은 한국어를 o200k와 다르게 나눌 수 있음), 원인 (2)는 사라지고 중복 제거 전 상한 셈만 원인으로 남습니다.
- 상한을 넘는 연결을 받아들이면 _TABLE_LINK_MAX의 원래 걱정, 곧 긴 요구사항 목록표가 다른 문서의 근거에서 예산을 빼앗는 문제가 다시 열립니다.

## 다른 방법

- 6510eea를 두고 테스트만 현실적인 크기로 다시 쓰기. 결함을 보여 주지만 아무것도 고치지 않습니다.
- _LINK_TOKENS를 더 큰 고정값으로 올리기. 잰 청크 크기에 묶지 않고 절벽을 옮길 뿐이며, 고르기는 여전히 중복 제거 전에 일어납니다.
- _TABLE_LINK_MAX 되살리기. 바로 F7이 거부한 것입니다.
- 전처리에서 이어지는 청크 앞에 표 머리글 붙이기. 다른 파이프라인과 v11/v12 묶음에 속하며, 이 PR의 검색 범위 밖입니다.

## 실험

(1) 단위 테스트: 앞 순위로 찾은 것이 이미 c0을 담은 9청크 표에서, 청크마다 300토큰으로 c5를 찾습니다. 지금 코드는 c0을 상한에 셈하므로, _pack이 이미 고른 것으로 건너뛰고 c5 뒤에는 c4만 더해집니다(c4, c6 또는 둘 다 빠졌을 수 있음). 고르기를 _pack 안으로 옮기면 c4와 c6이 모두 들어옵니다(c0은 셈 없이 건너뜀). 찾은 청크를 _pack이 건너뛰는 경우를 더하고, 그 연결이 담기지 않는다고 단정합니다. (2) API 호출 없이: v12 corpus/chunks.jsonl을 읽고, 청크가 6개보다 많은 (doc_id, table_ref) 묶음을 골라 본문의 Embedder.token_counts를 계산한 뒤, 지금 코드와 제안한 규칙에서 연결을 하나도 받지 못하는 경우를 셉니다. 개수만 보고합니다. (3) 이 브랜치용으로 다시 만든 index로 dev에서만(test는 절대 아님) rerun_retrieval을 돌리고, 05 Retrieval만 하여 단일·다중 근거 포함률(Evidence Coverage)을 비교합니다.

## 결과

관측했지만 검증하지 않았으며, 여전히 초안입니다. 리뷰어의 경우를 4090646에서 재현했습니다. 9청크 표, c5를 찾음, `_pack`이 c5와 거의 같은 중복으로 버리는 600토큰 c0, 100토큰 c4입니다. `_pack([(5, 0.9)])`는 `['c5']`를 돌려줬습니다. `_pack`이 c0을 버리기 전에 c0이 연결 상한을 다 썼기 때문입니다.

실험 (2)는 개수만, KURE-v1 토크나이저(`_LINK_TOKENS`와 예산의 단위)로 오프라인에서 했습니다. 청크가 6개보다 많은 v12 표 3개의 21청크는 KURE 토큰 중앙값이 576(최대 701, 600 초과 6개)입니다. 600 상한에서 첫 조각 먼저, 그다음 거리 순서로 하면, 찾을 수 있는 21경우 가운데 연결을 하나도 받지 못하는 경우는 0이므로, 반대 근거에서 내다본 대로 원인 (2)는 사라집니다. 상한 정책 변경, 곧 방법 (b)는 필요 없었습니다. 비교하면, 2~6청크 표의 청크 1,562개 가운데 322개가 600토큰을 넘습니다(중앙값 461).

수정은 가설의 (a)를 따릅니다. `_with_links`를 지웠습니다. `_pack`은 찾은 청크를 새 `_admit`로 더하며, 이미 고른 청크, 같은 문서의 거의 같은 중복, 남은 자리를 넘는 청크는 거부합니다. 찾은 청크를 실제로 고른 뒤에만 `links[i]`를 `_link_priority` 순서로 훑습니다. 연결마다 min(남은 예산, `_LINK_TOKENS` − 이 찾은 것의 연결이 이미 쓴 양)과 비교해 받아들이므로, 상한은 실제로 더한 연결에만 셈합니다. 찾은 것 하나에 더한 연결은 문서 순서로 놓습니다.

테스트(`tests/test_retrieval.py`):
- `test_links_already_packed_or_dropped_as_duplicates_do_not_use_the_link_cap`: 청크마다 300토큰으로 c0을 찾은 뒤 c5를 찾으면 `['c0', 'c1', 'c2', 'c5', 'c4', 'c6']`이 나오고(예전 코드: c6 없음), 리뷰어의 중복 첫 조각 경우는 `['c5', 'c4', 'c6']`이 나옵니다(예전 코드: `['c5']`).
- `test_links_of_a_found_chunk_dropped_as_a_duplicate_are_not_packed`는 `['c0']`을 냅니다(예전 코드: `['c0', 'c2']`).

`tests/test_retrieval.py`, `tests/test_retrieval_benchmark.py`, `tests/test_v11_package.py`가 통과하고(76 passed), ruff도 깨끗합니다. 커밋은 이 문서를 담은 것("retrieval: charge the link cap only for links actually packed")입니다. 돌리지 않은 것: 실험 (3), 곧 dev `rerun_retrieval`과 05 Retrieval 비교입니다. 이 브랜치의 검색 글로 다시 만든 index가 필요하기 때문입니다.

## 남은 한계

10회차 지적 글은 읽지 못했습니다. 긴 표 청크의 KURE 토큰 크기는 재지 않았고, 수치는 o200k뿐입니다. 어떤 상한 정책(엄격한 상한, 가장 가까운 연결은 늘 받아들임, 잰 상한)이 받아들일 만한지는 검색 담당자가 정할 제품 결정입니다. LlamaIndex 소스는 node id로 중복을 없애는 것을 보여 줄 뿐 토큰 예산은 없으므로, 연결을 중복 제거 뒤에 셈해야 한다는 주장은 이 문서의 해석입니다.
