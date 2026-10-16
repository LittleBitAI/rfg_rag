"""OCR 설정 전달과 02에서 조절한 검색 설정의 04 전달을 확인한다."""
import ast
import json
from copy import deepcopy
from unittest.mock import MagicMock

import pytest
import yaml

from rag.config import ROOT, read_jsonl, write_jsonl
from rag.preprocessing import chunking, parsing
from rag.usage import UsageCallback


def test_notebooks_have_no_saved_execution_results():
    for path in sorted(ROOT.glob("*.ipynb")):
        notebook = json.loads(path.read_text(encoding="utf-8"))
        for cell in notebook["cells"]:
            assert cell.get("execution_count") is None, path.name
            assert not cell.get("outputs"), path.name


def test_ocr_parser_uses_selected_model_and_effort(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    cfg = {"model": "gpt-5-mini", "max_tokens": 1234, "reasoning_effort": "high"}

    parser = parsing._ocr_parser(cfg, UsageCallback("ocr", [0.25, 0.025, 2.0], "high"))

    assert parser.model.model_name == cfg["model"]
    assert parser.model.max_tokens == 1234
    assert parser.model.reasoning_effort == "high"


@pytest.mark.parametrize("ocr", [False, True])
def test_parse_documents_initializes_ocr_only_when_enabled(monkeypatch, tmp_path, ocr):
    cfg = {"model": "gpt-5-mini", "max_tokens": 1234, "reasoning_effort": "high",
           "usd_per_1m_tokens": [0.25, 0.025, 2.0]}
    parser = object()
    make_parser = MagicMock(return_value=parser)
    parse_file = MagicMock(return_value={"source": "test.pdf", "records": []})
    monkeypatch.setattr(parsing, "_ocr_parser", make_parser)
    monkeypatch.setattr(parsing, "_parse_file", parse_file)

    pdf = tmp_path / "test.pdf"
    pdf.write_bytes(b"pdf")

    docs = parsing.parse_documents([str(pdf)], {}, ocr=ocr, ocr_cfg=cfg, cache_dir=tmp_path / "parsed")

    parse_file.assert_called_once_with(str(pdf), {}, parser if ocr else None)
    assert docs == [parse_file.return_value]
    if ocr:
        assert make_parser.call_count == 1
        assert make_parser.call_args.args[0] == cfg
        assert make_parser.call_args.args[1].subject == "test.pdf"
    else:
        make_parser.assert_not_called()


def _run_cell(filename: str, prefix: str, namespace: dict, **overrides):
    notebook = json.loads((ROOT / filename).read_text(encoding="utf-8"))
    source = next("".join(cell["source"]) for cell in notebook["cells"]
                  if cell["cell_type"] == "code" and "".join(cell["source"]).startswith(prefix))
    tree = ast.parse(source)
    tree.body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))]
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in overrides:
                node.value = ast.parse(repr(overrides[name]), mode="eval").body
    exec(compile(ast.fix_missing_locations(tree), filename, "exec"), namespace)


def test_retrieval_notebook_overrides_reach_generation(tmp_path):
    defaults = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    namespace = {"cfg": deepcopy(defaults), "ARTIFACTS": tmp_path, "write_jsonl": write_jsonl}
    _run_cell("02_retrieval.ipynb", "REWRITE_MODEL =", namespace,
              REWRITE_MODEL="selected-rewrite-model", REWRITE_REASONING_EFFORT="high",
              REWRITE_MAX_TOKENS=1234, REWRITE_PRICES=[1.0, 0.1, 4.0], DENSE_WEIGHT=0.25, RERANK=False)
    namespace.update(load_config=lambda: deepcopy(defaults), read_jsonl=read_jsonl)
    _run_cell("04_generation.ipynb", "import pandas", namespace)
    _run_cell("04_generation.ipynb", "LLM_MODEL =", namespace,
              LLM_MODEL="selected-answer-model", LLM_REASONING_EFFORT="medium", LLM_MAX_TOKENS=2345,
              LLM_PRICES=[2.0, 0.2, 8.0])
    index = object()
    namespace.update(HybridIndex=MagicMock(return_value=index), answer_questions=MagicMock(return_value=[]),
                     pd=MagicMock())
    write_jsonl([{"id": "q1", "question": "질문"}], tmp_path / "eval_set.jsonl")

    _run_cell("04_generation.ipynb", "eval_set =", namespace)

    used_cfg = namespace["HybridIndex"].call_args.args[1]
    assert used_cfg["retrieval"]["dense_weight"] == 0.25
    assert used_cfg["rerank"] == {**defaults["rerank"], "enabled": False}
    assert used_cfg["rewrite"] == {**defaults["rewrite"], "model": "selected-rewrite-model",
                                   "reasoning_effort": "high", "max_tokens": 1234,
                                   "usd_per_1m_tokens": [1.0, 0.1, 4.0]}
    namespace["answer_questions"].assert_called_once_with(
        [{"id": "q1", "question": "질문"}], index,
        {**defaults["llm"], "model": "selected-answer-model", "reasoning_effort": "medium", "max_tokens": 2345,
         "usd_per_1m_tokens": [2.0, 0.2, 8.0]},
        used_cfg["rewrite"], checkpoint_dir=tmp_path / "checkpoints" / "answers")


@pytest.mark.parametrize("package", [None, "data/Golden_Dev396_v12_Team_Package/corpus"])
def test_preprocessing_notebook_selects_input(tmp_path, package):
    docs, chunks = [{"doc_id": "d1"}], [{"chunk_id": "c1"}]
    defaults = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    namespace = {"cfg": defaults, "ROOT": tmp_path, "ARTIFACTS": tmp_path / "artifacts",
                 "collect_inputs": MagicMock(return_value=["test.pdf"]),
                 "parse_documents": MagicMock(return_value=docs),
                 "chunk_documents": MagicMock(return_value=chunks),
                 "load_package": MagicMock(return_value=(docs, chunks)),
                 "save_chunks": MagicMock(), "parsing_summary": MagicMock(),
                 "chunk_summary": MagicMock(), "display": MagicMock()}
    _run_cell("01_preprocessing.ipynb", "PREPROCESSED =", namespace, PREPROCESSED=package)
    notebook = json.loads((ROOT / "01_preprocessing.ipynb").read_text(encoding="utf-8"))
    for cell in notebook["cells"]:
        source = "".join(cell["source"])
        if cell["cell_type"] == "code" and source.startswith("if PREPROCESSED is None:"):
            exec(source, namespace)

    namespace["save_chunks"].assert_called_once_with(docs, chunks, tmp_path / "artifacts")
    if package is None:
        namespace["collect_inputs"].assert_called_once()
        namespace["parse_documents"].assert_called_once_with(
            ["test.pdf"], defaults["parsing"], ocr=False, ocr_cfg=defaults["ocr"],
            cache_dir=tmp_path / "artifacts" / "parsed")
        namespace["chunk_documents"].assert_called_once_with(docs, defaults["chunking"],
                                                             cache_dir=tmp_path / "artifacts" / "chunked")
        namespace["load_package"].assert_not_called()
    else:
        namespace["load_package"].assert_called_once_with(tmp_path / package)
        for name in ["collect_inputs", "parse_documents", "chunk_documents", "parsing_summary"]:
            namespace[name].assert_not_called()


def _files(tmp_path, *names):
    paths = [tmp_path / name for name in names]
    for path in paths:
        path.write_bytes(path.name.encode())
    return [str(path) for path in paths]


def _fake_parse(parsed, fail_on=None, error=RuntimeError):
    def parse_file(path, pcfg, parser):
        if path == fail_on:
            raise error("컴퓨터가 꺼짐")
        parsed.append(path)
        return {"source": path, "records": [{"page": 1, "kind": "text", "text": "본문"}]}
    return parse_file


@pytest.mark.parametrize("error", [RuntimeError, KeyboardInterrupt])  # 문서 오류 · 노트북 중지(커널 중단)
def test_parse_documents_resumes_after_interruption(monkeypatch, tmp_path, error):
    first, second = _files(tmp_path, "첫째.pdf", "둘째.pdf")
    ocr_cfg = {"model": "m", "max_tokens": 1, "reasoning_effort": "low", "usd_per_1m_tokens": [1, 1, 1]}
    cache = tmp_path / "parsed"
    parsed = []

    monkeypatch.setattr(parsing, "_parse_file", _fake_parse(parsed, fail_on=second, error=error))
    if error is KeyboardInterrupt:
        with pytest.raises(KeyboardInterrupt):
            parsing.parse_documents([first, second], {}, False, ocr_cfg, cache)
    else:
        assert len(parsing.parse_documents([first, second], {}, False, ocr_cfg, cache)) == 1   # 둘째에서 끊김
    monkeypatch.setattr(parsing, "_parse_file", _fake_parse(parsed))
    docs = parsing.parse_documents([first, second], {}, False, ocr_cfg, cache)

    assert parsed == [first, second]  # 첫째는 한 번만 파싱, 둘째만 이어서 파싱
    assert [d["source"] for d in docs] == [first, second]


@pytest.mark.parametrize("changed", [{"pcfg": {"hanja_mode": "none"}}, {"ocr": True},
                                     {"ocr_cfg": {"model": "other", "max_tokens": 1, "reasoning_effort": "low",
                                                  "usd_per_1m_tokens": [1, 1, 1]}, "ocr": True}])
def test_parse_documents_ignores_saved_result_when_settings_change(monkeypatch, tmp_path, changed):
    path, = _files(tmp_path, "문서.pdf")
    ocr_cfg = {"model": "m", "max_tokens": 1, "reasoning_effort": "low", "usd_per_1m_tokens": [1, 1, 1]}
    cache = tmp_path / "parsed"
    parsed = []
    monkeypatch.setattr(parsing, "_parse_file", _fake_parse(parsed))
    monkeypatch.setattr(parsing, "_ocr_parser", MagicMock())
    args = {"pcfg": {}, "ocr": False, "ocr_cfg": ocr_cfg}

    parsing.parse_documents([path], args["pcfg"], args["ocr"], args["ocr_cfg"], cache)
    args |= changed
    parsing.parse_documents([path], args["pcfg"], args["ocr"], args["ocr_cfg"], cache)

    assert parsed == [path, path]


def _doc(doc_id, text="본문 문장입니다. " * 80):
    return {"doc_id": doc_id, "source": f"{doc_id}.pdf", "title": doc_id, "doc_type": "pdf",
            "records": [{"page": 1, "kind": "text", "text": text}]}


_REAL_CHUNK_DOC = chunking._chunk_doc


def _spy_chunk_doc(monkeypatch, calls, stop_at=None):
    """실제 청킹을 그대로 하되 문서 이름을 기록하고, stop_at 문서에서 노트북이 꺼진 것처럼 멈춘다"""
    def chunk_doc(doc, *args):
        if doc["doc_id"] == stop_at:
            raise KeyboardInterrupt
        calls.append(doc["doc_id"])
        return _REAL_CHUNK_DOC(doc, *args)
    monkeypatch.setattr(chunking, "_chunk_doc", chunk_doc)


def test_chunk_documents_resumes_after_interruption(monkeypatch, tmp_path):
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))["chunking"]
    docs = [_doc("첫째"), _doc("둘째")]
    expected = chunking.chunk_documents(docs, cfg, tmp_path / "fresh")
    calls = []

    _spy_chunk_doc(monkeypatch, calls, stop_at="둘째")
    with pytest.raises(KeyboardInterrupt):
        chunking.chunk_documents(docs, cfg, tmp_path / "chunked")
    _spy_chunk_doc(monkeypatch, calls)
    chunks = chunking.chunk_documents(docs, cfg, tmp_path / "chunked")

    assert calls == ["첫째", "둘째"]  # 첫째는 한 번만 분할, 둘째만 이어서 분할
    assert chunks == expected


@pytest.mark.parametrize("change", ["chunk_size", "doc"])
def test_chunk_documents_rechunks_when_settings_or_parsed_doc_change(monkeypatch, tmp_path, change):
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))["chunking"]
    doc = _doc("문서")
    calls = []
    _spy_chunk_doc(monkeypatch, calls)

    chunking.chunk_documents([doc], cfg, tmp_path)
    chunking.chunk_documents([doc], cfg, tmp_path)   # 그대로면 저장된 결과
    if change == "chunk_size":
        cfg = {**cfg, "chunk_size": 300}
    else:
        doc = _doc("문서", text="다시 파싱한 본문입니다. " * 80)
    chunking.chunk_documents([doc], cfg, tmp_path)

    assert calls == ["문서", "문서"]


def test_save_chunks_keeps_previous_files_when_interrupted_while_writing(monkeypatch, tmp_path):
    chunking.save_chunks([{"doc_id": "d0"}], [{"chunk_id": "c0"}], tmp_path)

    def write_half_then_stop(rows, path):
        path.write_text('{"chunk_id": "c1"', encoding="utf-8")
        raise KeyboardInterrupt
    monkeypatch.setattr(chunking, "write_jsonl", write_half_then_stop)
    with pytest.raises(KeyboardInterrupt):
        chunking.save_chunks([{"doc_id": "d1"}], [{"chunk_id": "c1"}], tmp_path)

    assert read_jsonl(tmp_path / "chunks.jsonl") == [{"chunk_id": "c0"}]
    assert read_jsonl(tmp_path / "docs.jsonl") == [{"doc_id": "d0"}]


def test_evaluation_notebook_judge_setting_reaches_config():
    defaults = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    namespace = {"cfg": deepcopy(defaults)}

    _run_cell("05_evaluation.ipynb", "JUDGE =", namespace, JUDGE="ragas")

    assert namespace["cfg"]["evaluation"] == {**defaults["evaluation"], "judge": "ragas"}
