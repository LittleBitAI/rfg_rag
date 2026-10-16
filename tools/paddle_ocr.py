"""별도 PaddleOCR 환경에서 이미지별 인식 시간과 전사를 기록한다."""
import json
import re
import sys
import time
from html.parser import HTMLParser
from pathlib import Path


class _TableText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "tr":
            self.parts.append("\n")
        elif tag in ("td", "th"):
            self.parts.append(" | ")


def plain_tables(text):
    for table in re.findall(r"<table\b.*?</table>", text, flags=re.IGNORECASE | re.DOTALL):
        parser = _TableText()
        parser.feed(table)
        rows = (line.rstrip(" |") for line in "".join(parser.parts).splitlines())
        text = text.replace(table, "\n".join(rows).strip())
    return text


def main(manifest: str, image_dir: str, output: str):
    import paddle
    from paddleocr import PaddleOCRVL

    pipeline = PaddleOCRVL(pipeline_version="v1.5", device="gpu:0", use_layout_detection=False)
    path = Path(output)
    done = {json.loads(line)["image_sha256"] for line in path.read_text(encoding="utf-8").splitlines()} if path.exists() else set()
    images = [json.loads(line) for line in Path(manifest).read_text(encoding="utf-8").splitlines()]
    path.parent.mkdir(parents=True, exist_ok=True)
    for image in images:
        sha = image["image_sha256"]
        if sha in done:
            continue
        paddle.device.cuda.empty_cache()
        started = time.perf_counter()
        results = list(pipeline.predict(str(Path(image_dir) / image["file"])))
        text = "\n\n".join(block.content for result in results for block in result["parsing_res_list"])
        seconds = time.perf_counter() - started
        row = {"engine": "PaddleOCR-VL-1.5", "image_sha256": sha, "text": plain_tables(text),
               "seconds": seconds, "cost_usd": None}
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(sha, row["seconds"], flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
