"""OCR 설정 전달과 02에서 조절한 검색 설정의 04 전달을 확인한다."""
import ast
import json
from copy import deepcopy
from unittest.mock import MagicMock

import pytest
import yaml

from rag.config import ROOT, read_jsonl, write_jsonl
from rag.preprocessing import parsing


def test_ocr_parser_uses_selected_model_and_effort(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    cfg = {"model": "gpt-5-mini", "max_tokens": 1234, "reasoning_effort": "high"}

    parser = parsing._ocr_parser(cfg)

    assert parser.model.model_name == cfg["model"]
    assert parser.model.max_tokens == 1234
    assert parser.model.reasoning_effort == "high"


@pytest.mark.parametrize("ocr", [False, True])
def test_parse_documents_initializes_ocr_only_when_enabled(monkeypatch, ocr):
    cfg = {"model": "gpt-5-mini", "max_tokens": 1234, "reasoning_effort": "high"}
    parser = object()
    make_parser = MagicMock(return_value=parser)
    parse_file = MagicMock(return_value={"source": "test.pdf", "records": []})
    monkeypatch.setattr(parsing, "_ocr_parser", make_parser)
    monkeypatch.setattr(parsing, "_parse_file", parse_file)

    docs = parsing.parse_documents(["test.pdf"], {}, ocr=ocr, ocr_cfg=cfg)

    parse_file.assert_called_once_with("test.pdf", {}, parser if ocr else None)
    assert docs == [parse_file.return_value]
    if ocr:
        make_parser.assert_called_once_with(cfg)
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
                node.value = ast.Constant(overrides[name])
    exec(compile(ast.fix_missing_locations(tree), filename, "exec"), namespace)


def test_retrieval_notebook_overrides_reach_generation(tmp_path):
    defaults = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    namespace = {"cfg": deepcopy(defaults), "ARTIFACTS": tmp_path, "write_jsonl": write_jsonl}
    _run_cell("02_retrieval.ipynb", "REWRITE_MODEL =", namespace,
              REWRITE_MODEL="selected-rewrite-model", REWRITE_REASONING_EFFORT="high",
              REWRITE_MAX_TOKENS=1234, DENSE_WEIGHT=0.25)
    namespace.update(load_config=lambda: deepcopy(defaults), read_jsonl=read_jsonl)
    _run_cell("04_generation.ipynb", "import pandas", namespace)
    _run_cell("04_generation.ipynb", "LLM_MODEL =", namespace,
              LLM_MODEL="selected-answer-model", LLM_REASONING_EFFORT="medium", LLM_MAX_TOKENS=2345)
    index = object()
    namespace.update(HybridIndex=MagicMock(return_value=index), answer_questions=MagicMock(return_value=[]),
                     pd=MagicMock())
    write_jsonl([{"id": "q1", "question": "질문"}], tmp_path / "eval_set.jsonl")

    _run_cell("04_generation.ipynb", "eval_set =", namespace)

    used_cfg = namespace["HybridIndex"].call_args.args[1]
    assert used_cfg["retrieval"]["dense_weight"] == 0.25
    assert used_cfg["rewrite"] == {"model": "selected-rewrite-model", "reasoning_effort": "high", "max_tokens": 1234}
    namespace["answer_questions"].assert_called_once_with(
        [{"id": "q1", "question": "질문"}], index,
        {**defaults["llm"], "model": "selected-answer-model", "reasoning_effort": "medium", "max_tokens": 2345},
        used_cfg["rewrite"])
