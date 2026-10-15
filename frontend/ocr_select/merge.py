"""팀원이 각자 내보낸 묶음 결과(ocr_labels_batchN.jsonl)를 artifacts/ocr_labels/merged_labels.jsonl 하나로 합친다.

묶음 번호와 묶음마다 매긴 수 · 전체 수는 이 컴퓨터의 images.jsonl 로 다시 센다 — 먼저 같은 data/rfp.zip 으로 extract 해 둔다.
저장소 최상위에서 실행: .venv\\Scripts\\python -m frontend.ocr_select.merge ocr_labels_batch1.jsonl ... ocr_labels_batch5.jsonl
"""
from __future__ import annotations

import sys
from datetime import datetime
from collections import Counter
from pathlib import Path

from frontend.ocr_select.extract import OUT
from frontend.ocr_select.server import cards, latest_labels, result_rows
from rag.config import read_jsonl, write_jsonl


def merge(rows: list[dict], images: list[dict]) -> tuple[list[dict], list[dict], int]:
    """(합친 결과, 전체 카드, images.jsonl 에 없는 위치 수). 두 사람이 같은 위치를 매겼으면 나중 라벨이 이긴다.
    labelled_at 은 매긴 컴퓨터의 시간대로 적히므로 문자열이 아니라 시각으로 비교한다."""
    labels = latest_labels(sorted(rows, key=lambda r: datetime.fromisoformat(r["labelled_at"])))
    all_cards = cards(images, labels, {})
    unknown = len(set(labels) - {c["key"] for c in all_cards})
    return result_rows(all_cards, labels), all_cards, unknown


def main(paths: list[str]):
    rows = [r for p in paths for r in read_jsonl(Path(p))]
    merged, all_cards, unknown = merge(rows, read_jsonl(OUT / "images.jsonl"))
    write_jsonl(merged, OUT / "merged_labels.jsonl")
    total, done = Counter(c["batch"] for c in all_cards), Counter(r["batch"] for r in merged)
    for batch in sorted(total):
        print(f"묶음 {batch}: 라벨 {done[batch]} / {total[batch]} (빠진 위치 {total[batch] - done[batch]})")
    if unknown:
        print(f"⚠️ 이 컴퓨터의 images.jsonl 에 없는 위치 {unknown}곳은 뺐습니다. 같은 data/rfp.zip 으로 extract 했는지 확인하세요.")
    print(f"합친 결과 {len(merged)}곳 → {OUT / 'merged_labels.jsonl'}")


if __name__ == "__main__":
    main(sys.argv[1:])
