import pytest

from rag.preprocessing.ocr_benchmark import edit_similarity, key_metrics, winners


def test_handmade_edit_and_key_metrics_include_invented_number():
    assert edit_similarity("금액 12", "금액 13") == pytest.approx(0.8)
    assert edit_similarity("A", "AAAA") == -2.0
    assert key_metrics("금액 12 SFR-001", ["금액", "12", "SFR-001"], "금액 12 SFR-999") == {
        "key_recall": 2 / 3, "key_precision": 2 / 3}
    assert key_metrics("금액 12", ["금액", "12"], "") == {"key_recall": 0, "key_precision": 0}


def test_local_winner_requires_recall_margin_and_no_lower_precision():
    rows = []
    for kind, recall, precision in [("table", .85, .95), ("text", .84, .95), ("diagram", .9, .94)]:
        rows.extend([
            {"image_type": kind, "engine": "PaddleOCR-VL-1.5", "key_recall": recall,
             "key_precision": precision, "cost_usd": None},
            {"image_type": kind, "engine": "gpt-6-luna", "key_recall": .90,
             "key_precision": .95, "cost_usd": .001},
            {"image_type": kind, "engine": "gemini-3.5-flash-lite", "key_recall": .89,
             "key_precision": .96, "cost_usd": .002},
        ])
    assert winners(rows) == {"table": "PaddleOCR-VL-1.5", "text": "gpt-6-luna", "diagram": "gpt-6-luna"}


@pytest.mark.parametrize("model", ["gpt-6-luna", "gemini-3.5-flash-lite"])
def test_api_ocr_uses_common_instruction_and_records_each_paid_call(tmp_path, monkeypatch, model):
    import csv
    from types import SimpleNamespace
    from unittest.mock import Mock

    from PIL import Image
    from rag.preprocessing import ocr_benchmark

    monkeypatch.setenv("GEMINI_API_KEY", "offline-test")
    tokens = {"prompt_tokens": 100, "completion_tokens": 20}
    response = SimpleNamespace(usage=SimpleNamespace(model_dump=lambda: tokens),
                               choices=[SimpleNamespace(message=SimpleNamespace(content="금액 12"),
                                                        finish_reason="stop")])
    create = Mock(return_value=response)
    factory = Mock(return_value=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    monkeypatch.setattr(ocr_benchmark, "OpenAI", factory)
    image = tmp_path / "input.png"
    Image.new("RGB", (2, 2)).save(image)
    result = ocr_benchmark.api_ocr(image, model, "image-sha", "benchmark")
    assert create.call_args.kwargs["messages"][0]["content"][0]["text"] == ocr_benchmark.INSTRUCTION
    assert factory.call_args.kwargs["max_retries"] == 0
    if model.startswith("gemini"):
        assert factory.call_args.kwargs["base_url"] == "https://generativelanguage.googleapis.com/v1beta/openai/"
    with (tmp_path / "api_usage.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 1
    assert (rows[0]["stage"], rows[0]["evaluation"], rows[0]["subject"], rows[0]["model"]) == (
        "ocr", "benchmark", "image-sha", model)
    assert float(rows[0]["cost_usd"]) == result["cost_usd"] > 0
