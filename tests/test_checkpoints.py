"""파싱 · 임베딩 · 답변 · 심판 점수가 끊긴 뒤 다시 실행하면 이어서 하고, 입력이 바뀌면 다시 하는지 확인한다."""
import math
from unittest.mock import MagicMock

import faiss
import numpy as np
import pytest
from ragas.metrics import Faithfulness

from rag.config import load_config, read_checkpoint
from rag.evaluation import evaluation
from rag.generation import generation
from rag.preprocessing import parsing
from rag.retrieval import indexing
from test_usage import _answer_row

_OCR_CFG = {"model": "m", "max_tokens": 1, "reasoning_effort": "low", "usd_per_1m_tokens": [1, 1, 1]}


def _files(tmp_path, *names):
    paths = [tmp_path / name for name in names]
    for path in paths:
        path.write_bytes(path.name.encode())
    return [str(path) for path in paths]


def _fake_parse(parsed, fail_on=None, error=RuntimeError):
    def parse_file(path, pcfg, parser, saved_rows=None):
        if path == fail_on:
            raise error("컴퓨터가 꺼짐")
        parsed.append(path)
        return {"source": path, "records": [{"page": 1, "kind": "text", "text": "본문"}]}
    return parse_file


@pytest.mark.parametrize("error", [RuntimeError, KeyboardInterrupt])  # 문서 오류 · 노트북 중지(커널 중단)
def test_parse_documents_resumes_after_interruption(monkeypatch, tmp_path, error):
    first, second = _files(tmp_path, "첫째.pdf", "둘째.pdf")
    cache = tmp_path / "parsed"
    parsed = []

    monkeypatch.setattr(parsing, "_parse_file", _fake_parse(parsed, fail_on=second, error=error))
    if error is KeyboardInterrupt:
        with pytest.raises(KeyboardInterrupt):
            parsing.parse_documents([first, second], {}, False, _OCR_CFG, cache_dir=cache)
    else:
        assert len(parsing.parse_documents([first, second], {}, False, _OCR_CFG, cache_dir=cache)) == 1
    monkeypatch.setattr(parsing, "_parse_file", _fake_parse(parsed))
    docs = parsing.parse_documents([first, second], {}, False, _OCR_CFG, cache_dir=cache)

    assert parsed == [first, second]  # 첫째는 한 번만 파싱, 둘째만 이어서 파싱
    assert [d["source"] for d in docs] == [first, second]


@pytest.mark.parametrize("changed", [{"pcfg": {"hanja_mode": "none"}}, {"ocr": True},
                                     {"ocr_cfg": {**_OCR_CFG, "model": "other"}, "ocr": True}, {"content": b"new"}])
def test_parse_documents_ignores_saved_result_when_file_or_settings_change(monkeypatch, tmp_path, changed):
    path, = _files(tmp_path, "문서.pdf")
    parsed = []
    monkeypatch.setattr(parsing, "_parse_file", _fake_parse(parsed))
    monkeypatch.setattr(parsing, "_ocr_parser", MagicMock())
    args = {"pcfg": {}, "ocr": False, "ocr_cfg": _OCR_CFG}

    parsing.parse_documents([path], args["pcfg"], args["ocr"], args["ocr_cfg"], cache_dir=tmp_path / "parsed")
    if "content" in changed:
        (tmp_path / "문서.pdf").write_bytes(changed.pop("content"))
    args |= changed
    parsing.parse_documents([path], args["pcfg"], args["ocr"], args["ocr_cfg"], cache_dir=tmp_path / "parsed")

    assert parsed == [path, path]


def _fake_embedder(monkeypatch, calls, stop_at=None):
    """청크 글 길이로 만든 가짜 임베딩. stop_at 번째 묶음에서 노트북이 중지된 것처럼 멈춘다"""
    def encode(texts, progress=False):
        calls.append(list(texts))
        if len(calls) == stop_at:
            raise KeyboardInterrupt
        return np.array([[len(t), 1.0] for t in texts], dtype=np.float32)

    embedder = MagicMock()
    embedder.encode.side_effect = encode
    embedder.token_counts.side_effect = lambda texts: [1] * len(texts)
    monkeypatch.setattr(indexing, "Embedder", MagicMock(return_value=embedder))
    monkeypatch.setattr(indexing, "_PART_SIZE", 2)


_INDEX_CFG = {"embedding": {"model": "kure", "max_seq_length": 2048, "batch_size": 4}}


def _chunks(texts):
    return [{"chunk_id": str(i), "doc_id": "d", "text": t, "body": t} for i, t in enumerate(texts)]


def test_build_index_resumes_embedding_from_checkpoint(monkeypatch, tmp_path):
    chunks = _chunks([f"청크 본문 {'가' * i}" for i in range(5)])  # 묶음 3개: 2 · 2 · 1
    calls = []
    _fake_embedder(monkeypatch, calls, stop_at=2)
    with pytest.raises(KeyboardInterrupt):
        indexing.build_index(chunks, _INDEX_CFG, tmp_path / "index", tmp_path / "ckpt")

    calls.clear()
    _fake_embedder(monkeypatch, calls)
    summary = indexing.build_index(chunks, _INDEX_CFG, tmp_path / "index", tmp_path / "ckpt")

    assert calls == [[c["text"] for c in chunks[2:4]], [chunks[4]["text"]]]  # 첫 묶음은 저장된 결과를 읽음
    index = faiss.read_index(str(tmp_path / "index" / "faiss.index"))
    assert index.ntotal == summary["청크"] == 5
    assert index.reconstruct_n(0, 5)[:, 0].tolist() == [len(c["text"]) for c in chunks]


def test_build_index_recomputes_changed_chunks_and_drops_old_checkpoints(monkeypatch, tmp_path):
    chunks = _chunks([f"청크 {i}" for i in range(4)])
    calls = []
    _fake_embedder(monkeypatch, calls)
    indexing.build_index(chunks, _INDEX_CFG, tmp_path / "index", tmp_path / "ckpt")

    calls.clear()
    chunks[3] = {**chunks[3], "text": "바뀐 청크", "body": "바뀐 청크"}
    indexing.build_index(chunks, _INDEX_CFG, tmp_path / "index", tmp_path / "ckpt")

    assert calls == [["청크 2", "바뀐 청크"]]
    assert len(list((tmp_path / "ckpt").glob("*.npy"))) == 2


def _item(i: int) -> dict:
    return {"id": f"q{i}", "question": f"질문 {i}", "reference": "정답", "key_facts": ["정답"], "reset_context": False,
            "answerable": True, "primary_topic": None, "evidence": []}


def _fake_answer(item, index, llm_cfg, rewrite_cfg, history):
    return {**item, "answer": "답변 " + item["id"], "latency_s": 0.1}


def test_interrupted_answers_resume_from_next_question_with_saved_history(monkeypatch, tmp_path):
    index = MagicMock(fingerprint="색인")
    items = [_item(i) for i in range(5)]
    interrupted = MagicMock(side_effect=[_fake_answer(items[0], *[None] * 4), _fake_answer(items[1], *[None] * 4),
                                         KeyboardInterrupt])
    monkeypatch.setattr(generation, "answer_question", interrupted)
    with pytest.raises(KeyboardInterrupt):
        generation.answer_questions(items, index, {}, {}, checkpoint_dir=tmp_path)
    checkpoint, = tmp_path.glob("*.jsonl")
    with open(checkpoint, "a", encoding="utf-8") as f:
        f.write('{"id": "q2", "ans')  # 저장 도중 꺼져 반쯤 쓰인 줄
    resumed = MagicMock(side_effect=_fake_answer)
    monkeypatch.setattr(generation, "answer_question", resumed)

    rows = generation.answer_questions(items, index, {}, {}, checkpoint_dir=tmp_path)

    assert [c.args[0]["id"] for c in resumed.call_args_list] == ["q2", "q3", "q4"]
    assert resumed.call_args_list[0].kwargs["history"] == [{"question": "질문 0", "answer": "답변 q0"},
                                                           {"question": "질문 1", "answer": "답변 q1"}]
    assert [r["answer"] for r in rows] == [f"답변 q{i}" for i in range(5)]


def test_answer_checkpoint_is_not_reused_after_question_or_setting_change(monkeypatch, tmp_path):
    index = MagicMock(fingerprint="색인")
    items = [_item(i) for i in range(3)]
    answer = MagicMock(side_effect=_fake_answer)
    monkeypatch.setattr(generation, "answer_question", answer)
    generation.answer_questions(items, index, {}, {}, checkpoint_dir=tmp_path)
    answer.reset_mock()

    items[1] = {**items[1], "question": "바뀐 질문"}
    generation.answer_questions(items, index, {}, {}, checkpoint_dir=tmp_path)
    assert [c.args[0]["id"] for c in answer.call_args_list] == ["q1", "q2"]

    answer.reset_mock()
    generation.answer_questions(items, index, {"model": "다른 모델"}, {}, checkpoint_dir=tmp_path)
    assert answer.call_count == 3


def test_interrupted_judge_scores_resume_and_nan_is_judged_again(monkeypatch, tmp_path):
    monkeypatch.setattr(evaluation, "_JUDGE_BATCH", 2)
    monkeypatch.setattr(evaluation, "_judge", MagicMock())
    rows = [{**_answer_row(), "id": f"q{i}", "question": f"질문 {i}"} for i in range(5)]
    judged = []

    def fake_evaluate(data, **kwargs):
        questions = [sample.user_input for sample in data.samples]
        judged.append(questions)
        if judged == [["질문 0", "질문 1"], ["질문 2", "질문 3"]]:
            raise KeyboardInterrupt
        return MagicMock(scores=[{"faithfulness": math.nan if q == "질문 0" else 1.0} for q in questions])

    monkeypatch.setattr(evaluation, "evaluate", fake_evaluate)
    checkpoint = tmp_path / "grounding.jsonl"
    cfg = load_config()
    with pytest.raises(KeyboardInterrupt):
        evaluation._ragas(rows, [Faithfulness()], cfg, "grounding", checkpoint)
    judged.clear()

    scores = evaluation._ragas(rows, [Faithfulness()], cfg, "grounding", checkpoint)

    assert judged == [["질문 0", "질문 2"], ["질문 3", "질문 4"]]  # 저장된 질문 1 은 건너뛰고 NaN 인 질문 0 은 다시
    assert [s["faithfulness"] for s in scores[1:]] == [1.0] * 4


@pytest.mark.parametrize("tail", [b'{"answer": "', '{"answer": "가'.encode()[:-1]], ids=["json", "utf8"])
def test_checkpoint_drops_line_cut_mid_write(tmp_path, tail):
    path = tmp_path / "answers.jsonl"
    path.write_bytes('{"answer": "가"}\n'.encode() + tail)
    assert read_checkpoint(path) == [{"answer": "가"}]
