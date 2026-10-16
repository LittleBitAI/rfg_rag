import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock

from tools.paddle_ocr import main


def test_paddle_recognizes_whole_images_and_saves_text_without_layout_links(tmp_path, monkeypatch):
    predict = Mock(side_effect=[
        [{"parsing_res_list": [SimpleNamespace(content='<table><tr><th>금액</th><th>코드</th></tr>'
                                               '<tr><td colspan="2">42</td><td>SFR-001</td></tr></table>'),
                               SimpleNamespace(content="끝")]}],
        [{"parsing_res_list": [SimpleNamespace(content="")]}],
    ])
    factory = Mock(return_value=SimpleNamespace(predict=predict))
    empty_cache = Mock()
    monkeypatch.setitem(sys.modules, "paddle", SimpleNamespace(device=SimpleNamespace(
        cuda=SimpleNamespace(empty_cache=empty_cache))))
    monkeypatch.setitem(sys.modules, "paddleocr", SimpleNamespace(PaddleOCRVL=factory))
    manifest = tmp_path / "images.jsonl"
    images = [{"image_sha256": "one", "file": "one.png"}, {"image_sha256": "two", "file": "two.png"}]
    manifest.write_text("\n".join(json.dumps(row) for row in images), encoding="utf-8")
    output = tmp_path / "results.jsonl"
    main(str(manifest), str(tmp_path), str(output))
    factory.assert_called_once_with(pipeline_version="v1.5", device="gpu:0", use_layout_detection=False)
    rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert [row["text"] for row in rows] == ["금액 | 코드\n42 | SFR-001\n\n끝", ""]
    assert all(row["cost_usd"] is None and row["seconds"] >= 0 for row in rows)
    main(str(manifest), str(tmp_path), str(output))
    assert predict.call_count == 2
    assert empty_cache.call_count == 2
    assert len(output.read_text(encoding="utf-8").splitlines()) == 2
