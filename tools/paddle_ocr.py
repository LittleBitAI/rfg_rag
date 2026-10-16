"""Measure per-image latency in the isolated PaddleOCR environment."""
import json
import sys
import time
from pathlib import Path


def main(manifest: str, image_dir: str, output: str):
    from paddleocr import PaddleOCRVL

    pipeline = PaddleOCRVL(pipeline_version="v1.5", device="gpu:0")
    path = Path(output)
    done = {json.loads(line)["image_sha256"] for line in path.read_text(encoding="utf-8").splitlines()} if path.exists() else set()
    images = [json.loads(line) for line in Path(manifest).read_text(encoding="utf-8").splitlines()]
    path.parent.mkdir(parents=True, exist_ok=True)
    for image in images:
        sha = image["image_sha256"]
        if sha in done:
            continue
        started = time.perf_counter()
        results = list(pipeline.predict(str(Path(image_dir) / image["file"])))
        text = "\n\n".join(result.markdown["markdown_texts"] for result in results)
        row = {"engine": "PaddleOCR-VL-1.5", "image_sha256": sha, "text": text,
               "seconds": time.perf_counter() - started, "cost_usd": None}
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(sha, row["seconds"], flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
