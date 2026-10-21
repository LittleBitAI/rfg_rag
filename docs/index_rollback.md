# 색인 되돌리기

색인을 새 토크나이저로 다시 만든 뒤 코드를 예전으로 되돌릴 때는, 코드만 되돌리면 안 됩니다. 코드, 실행 환경, 색인 전체를 함께 되돌려야 합니다.
예전 코드는 새 색인 파일을 읽지 못하고, 새 파일에서 토큰만 꺼내 써도 문서와 질문을 자르는 방식이 서로 어긋나기 때문입니다.

아래 절차는 색인을 읽는 프로그램을 모두 멈춘 상태에서, 되돌릴 버전의 코드로 색인을 따로 만들어 확인한 뒤 폴더 이름을 한 번 바꿔 교체합니다.
기존 `build_index`만 쓰며, 예비로 읽는 방법이나 새 설정, 자동 변환은 없습니다.

## 준비와 순서

1. 질문 서버를 끄고 02 · 04 · 05 노트북 커널을 닫습니다. 교체가 끝날 때까지 켜지 않습니다. 버전을 바꾸기 전에 이 문서를 열어 둡니다.
2. 되돌릴 코드 버전, 실행 환경, 설정과 그에 맞는 `chunks.jsonl` · `docs.jsonl` · 기관 CSV를 적어 두고, 작업하는 동안 바꾸지 않습니다.
   회귀 시험의 기준은 토크나이저를 바꾸기 전의 `dev` 커밋 `2f746f38dba1d5fdbdfc924fbce3eac3297081b7`입니다.
   읽는 프로그램을 켜지 않은 채로 그 버전과 맞는 실행 환경을 고릅니다. 임베딩 모델은 미리 내려받아 두어야 합니다.
   내 PC에서만 도는 작업이므로 질문 다듬기, 답변, 채점 셀은 실행하지 않습니다.
3. 그 버전의 새 Python 프로세스에서, 지금 쓰는 색인 폴더 전체를 옆으로 치웁니다. 아래 두 폴더 이름은 아직 없어야 하며, 예전에 치워 둔 폴더를 덮어쓰면 안 됩니다.

   ```python
   from rag.config import ARTIFACTS

   root = ARTIFACTS.resolve()
   active = root / "index"
   previous = root / "index.before-downgrade"
   staging = root / "downgrade-staging"
   assert all(path.resolve().parent == root for path in (active, previous, staging))
   assert not previous.exists() and not staging.exists()
   active.rename(previous)
   ```

   이제 `index` 폴더가 없으므로, 실수로 읽는 프로그램을 켜도 섞인 색인으로 답하지 않고 불러오기에서 실패합니다.
   치워 둔 폴더는 그에 맞는 새 코드 · 환경 · 입력과만 함께 쓸 수 있습니다.

## 따로 만들어 확인하기

4. 되돌린 코드와 환경에서, 따로 떨어진 폴더에 색인 전체를 만듭니다.

   ```python
   from shutil import copy2
   from rag.config import ARTIFACTS, load_config, read_jsonl
   from rag.retrieval.indexing import build_index

   staging = ARTIFACTS / "downgrade-staging"
   staging.mkdir()
   for name in ("chunks.jsonl", "docs.jsonl"):
       copy2(ARTIFACTS / name, staging / name)
   build_index(read_jsonl(staging / "chunks.jsonl"), load_config(), staging / "index")
   ```

   만들다가 실패하면 `index` 폴더는 없는 채로, 읽는 프로그램도 멈춘 채로 둡니다. 다시 하려면 새 임시 폴더를 쓰거나, 실패한 임시 폴더를 확인한 뒤 그것만 지웁니다. 실패한 폴더의 내용을 옮겨 쓰지 않습니다.
   회귀 시험은 일부러 만들기를 실패시키고, 그때도 예전 코드가 켜지지 않는 것을 확인합니다.
5. 같은 버전과 환경으로 새 Python 프로세스를 하나 더 열고, 옮기기 전에 임시 색인을 확인합니다.

   ```python
   from rag.config import ARTIFACTS, load_config
   from rag.retrieval.retrieval import HybridIndex

   cfg = load_config()
   index = HybridIndex(ARTIFACTS / "downgrade-staging", cfg)
   query = "개인정보처리시스템"
   assert index.bm25.corpus_size == len(index.chunks)
   assert len(index.bm25.get_scores(index.tokenizer(query))) == len(index.chunks)
   index.rcfg["fusion"] = "minmax"  # dense_weight 0 = BM25만은 minmax 에서만 뜻이 있다
   for weight in (0, cfg["retrieval"]["dense_weight"]):
       index.rcfg["dense_weight"] = weight
       hits = index.search(query)
       assert hits
       print(weight, [row["chunk_id"] for row in hits])
   print("PASS: staged rollback search")
   ```

   문서에 실제로 있는 질문을 넣고, 출력된 조각 번호를 그 버전에서 미리 기록해 둔 결과와 비교합니다.
   회귀 시험은 만들기가 성공했는지만 보지 않고, 원래 토큰, BM25만 쓴 결과, 보통 검색 결과가 정확히 같은지 확인합니다.
   하나라도 실패하면 `index` 폴더는 없는 채로 두고 다음 단계로 가지 않습니다.

## 옮기고 다시 켜기

6. 새 프로세스에서 확인이 성공한 뒤에만, 같은 디스크 안에서 확인한 폴더를 제자리로 옮깁니다. 읽는 프로그램은 계속 멈춰 있어야 하고, `index` 폴더는 아직 없어야 합니다.

   ```python
   from rag.config import ARTIFACTS

   active = ARTIFACTS / "index"
   staged = ARTIFACTS / "downgrade-staging" / "index"
   assert not active.exists()
   staged.rename(active)
   ```

   서로 짝을 이루는 파일 다섯 개(`faiss.index`, `bm25_tokens.json`, `quantities.jsonl`, `quantity_phrases.json`, `quantity_vectors.npy`)가 함께 옮겨집니다.
   BM25 파일 하나만 바꾸거나 예전 토큰에 지문만 붙이면 안 됩니다. `index.before-downgrade`는 되돌리기가 확정될 때까지 남겨 둡니다.
   만들기, 확인, 옮기기 가운데 하나라도 실패했다면 예전 프로그램을 새 색인으로 켜지 않습니다.
7. 되돌린 버전의 프로그램이나 커널을 새로 켜고, 같은 검색을 한 번 더 해 봅니다.
   되돌리기를 그만두려면 다시 읽는 프로그램을 멈추고, 새 코드 · 환경과 그에 맞는 색인 전체를 함께 되돌려 놓습니다.

이 절차는 읽는 프로그램을 멈춘 상태에서 폴더 이름을 한 번 바꾸는 방식입니다. 켜져 있는 상태에서 코드를 바꾸거나, 중간에 꺼졌을 때 저절로 복구해 주지는 않습니다.
중간에 꺼졌다면, 읽는 프로그램을 켜기 전에 어떤 색인 폴더가 온전히 남아 있는지 보고 고른 버전과 맞는지 확인하세요.

## 회귀 시험

`.venv\Scripts\python -m pytest -q tests/test_index_migration.py tests/test_indexing.py`를 실행합니다.

이 시험은 git에 있는 예전 코드와 지금 코드를 각각 새 프로세스에서 실제로 돌립니다. 보통 clone에는 기준 커밋이 들어 있지만, 얕은 clone이면 그 기록을 먼저 받아야 합니다. 네트워크는 막고, 임베딩은 시험용 대체 모델을 씁니다.

확인하는 것은 아래와 같습니다.

- 예전 코드로 색인을 만들고 검색하기
- 새 코드가 예전 색인을 건드리지 않고 거부하기
- 새 코드로 다시 만들고 검색하기
- 예전 코드가 새 색인을 읽지 못하는 것
- 되돌리는 중에 실패하면 막히는 것
- 따로 만들기, 새 프로세스에서 확인하기, 폴더 통째로 옮기기
- 옮긴 뒤 예전 코드로 검색하기
