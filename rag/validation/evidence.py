"""골든 근거 본문을 복원하고 현재 문서·청크에 정확 일치로 연결한다."""
from __future__ import annotations

import hashlib
import io
import random
import re
import unicodedata
import zipfile
from collections import defaultdict
from pathlib import Path

import pandas as pd

from ..config import read_jsonl
from ..preprocessing.parsing import SUPPORTED, _safe_name, _zip_name


# 짧은 수·코드·항목 이름만으로 청크를 확정하지 않는다. test 결과와 무관하게 고정한다.
MIN_EVIDENCE_LENGTH = 20
OUTCOMES = ("labelled", "doc_unmapped", "not_found", "ambiguous", "too_short")
BLOCK = re.compile(r"^\[(E\d+)[^\]\n]*\]\s*\n", re.M)


def normalize_evidence(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).replace("|", " ").split())


def _archive_files(archive, raw_dir: Path):
    with zipfile.ZipFile(archive) as zipped:
        for info in zipped.infolist():
            name = _zip_name(info)
            source = _safe_name(re.sub(r'[<>:"|?*\x00-\x1f]', "_", name.replace("\\", "/").split("/")[-1]).strip())
            if info.is_dir() or "__MACOSX" in name or source.startswith("._"):
                continue
            if source.lower().endswith(".zip"):
                yield from _archive_files(io.BytesIO(zipped.read(info)), raw_dir / Path(source).stem)
            elif source.lower().endswith(SUPPORTED):
                yield raw_dir / source, hashlib.sha256(zipped.read(info)).hexdigest()


def _input_files(input_path: Path, raw_dir: Path):
    paths = sorted(input_path.rglob("*")) if input_path.is_dir() else [input_path]
    for path in paths:
        if not path.is_file():
            continue
        if path.suffix.lower() == ".zip":
            destination = raw_dir / path.stem if input_path.is_dir() else raw_dir
            yield from _archive_files(path, destination)
        elif path.suffix.lower() in SUPPORTED:
            yield path, hashlib.sha256(path.read_bytes()).hexdigest()


def _raw_documents(sources: dict, raw_dir: Path, input_path: Path) -> dict:
    candidates = defaultdict(set)
    for path, expected_sha in _input_files(input_path, raw_dir):
        source = unicodedata.normalize("NFC", path.name)
        if source in sources and path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha:
            candidates[source].add(expected_sha)
    return {next(iter(shas)): {"source": source, "doc_id": sources[source]}
            for source, shas in candidates.items() if len(shas) == 1}


def link_documents(chunks: list[dict], raw_dir: Path, input_path: Path, elements: dict) -> dict[str, dict]:
    sources = {unicodedata.normalize("NFC", c["source"]): c["doc_id"] for c in chunks}
    documents = {}
    for element in elements.values():
        metadata = element["location"]["supplier_metadata"]
        source = unicodedata.normalize("NFC", Path(metadata["source_paths"][0]).name)
        # v11 로더의 doc_id는 패키지가 기록한 원본 SHA다. 같은 이름만으로 다른 출력에 적용하지 않는다.
        if sources.get(source) == metadata["doc_id"] == metadata["sha256"]:
            documents[metadata["sha256"]] = {"source": source, "doc_id": metadata["doc_id"]}
    if all(doc_id in documents for doc_id in sources.values()):
        return documents
    unlinked = {source: doc_id for source, doc_id in sources.items() if doc_id not in documents}
    return {**documents, **_raw_documents(unlinked, raw_dir, input_path)}


def _evidence_text(ref: dict, elements: dict) -> str:
    element = elements[ref["element_id"]]
    location = ref["location"]
    if location["kind"] == "char":
        text = element[element["location"]["span_text_field"]]
        return text[location["start"]:location["end"]]
    cells = sorted(element["table"]["cells"], key=lambda c: (c["row"], c["col"]))
    return " | ".join(c["text"] for c in cells if c["row"] == location["row"])


def _context_labels(text: str, context: str) -> list[str]:
    parts = BLOCK.split(context)
    labels = [parts[i] for i in range(1, len(parts), 2) if parts[i + 1].strip() == text.strip()]
    if not labels:
        raise ValueError("골든 근거 본문이 context의 [E] 블록과 일치하지 않습니다")
    return labels


def _chunk_label(text: str, doc_id: str | None, by_doc: dict) -> dict:
    if doc_id is None:
        return {"chunk_id": None, "reason": "doc_unmapped"}
    normalized = normalize_evidence(text)
    if len(normalized) < MIN_EVIDENCE_LENGTH:
        return {"chunk_id": None, "reason": "too_short"}
    matches = {chunk_id for chunk_id, body in by_doc[doc_id] if normalized in body}
    if len(matches) == 1:
        return {"chunk_id": next(iter(matches)), "reason": None}
    return {"chunk_id": None, "reason": "ambiguous" if matches else "not_found"}


def label_evidence(items: list[dict], chunks: list[dict], raw_dir: Path, package_dir: Path,
                   input_path: Path) -> list[dict]:
    """원본 SHA → source/doc_id, 근거 본문 → 같은 문서 안의 유일한 청크. 검색·API 호출 없음."""
    elements = {e["element_id"]: e for e in read_jsonl(package_dir / "final_elements.jsonl")}
    documents = link_documents(chunks, raw_dir, input_path, elements)
    by_doc = defaultdict(list)
    for chunk in chunks:
        by_doc[chunk["doc_id"]].append((chunk["chunk_id"], normalize_evidence(chunk["body"])))
    labelled = []
    for item in items:
        evidence = []
        for ref in item["golden_evidence"]:
            text = _evidence_text(ref, elements)
            document = documents.get(ref["doc_sha"], {})
            metadata = elements[ref["element_id"]]["location"]["supplier_metadata"]
            evidence.append({**ref, "golden_chunk_id": ref["chunk_id"], "text": text,
                             "context_labels": _context_labels(text, item["golden_context"]),
                             "golden_source": unicodedata.normalize("NFC", metadata["source_paths"][0]),
                             "doc_id": document.get("doc_id"), "source": document.get("source"),
                             **_chunk_label(text, document.get("doc_id"), by_doc)})
        labelled.append({**{k: v for k, v in item.items() if k not in ("golden_context", "golden_evidence")},
                         "doc_ids": sorted({e["doc_id"] for e in evidence if e["doc_id"]}),
                         "evidence": evidence})
    return labelled


def mapping_report(splits: dict[str, list[dict]]) -> pd.DataFrame:
    rows = []
    for split, items in splits.items():
        topics = sorted({item["primary_topic"] for item in items})
        for topic in ["ALL", *topics]:
            selected = items if topic == "ALL" else [it for it in items if it["primary_topic"] == topic]
            evidence = [e for it in selected for e in it["evidence"]]
            counts = {outcome: sum((e["reason"] or "labelled") == outcome for e in evidence)
                      for outcome in OUTCOMES}
            states = [sum(e["chunk_id"] is not None for e in it["evidence"]) for it in selected]
            rows.append({"split": split, "primary_topic": topic, "questions": len(selected),
                         "evidence_entries": len(evidence), **counts,
                         "fully_labelled": sum(n == len(it["evidence"]) and n > 0
                                               for n, it in zip(states, selected)),
                         "partly_labelled": sum(0 < n < len(it["evidence"]) for n, it in zip(states, selected)),
                         "not_labelled": states.count(0),
                         "chunk_rate": counts["labelled"] / len(evidence),
                         "document_rate": sum(e["doc_id"] is not None for e in evidence) / len(evidence)})
    return pd.DataFrame(rows)


def document_report(splits: dict[str, list[dict]]) -> pd.DataFrame:
    rows = {}
    for split, items in splits.items():
        for item in items:
            for ref in item["evidence"]:
                rows[split, ref["doc_sha"]] = {"split": split, "doc_sha": ref["doc_sha"],
                                               "source": ref["source"], "doc_id": ref["doc_id"],
                                               "golden_source": ref["golden_source"],
                                               "outcome": "matched" if ref["doc_id"] else "doc_unmapped"}
    return pd.DataFrame(rows.values()).sort_values(["split", "doc_sha"]).reset_index(drop=True)


def correspondence_report(items: list[dict], labelled: list[dict], chunks: list[dict]) -> dict:
    evidence = [e for item in labelled for e in item["evidence"]]
    live_ids = {c["chunk_id"] for c in chunks}
    return {"questions": len(items), "evidence_entries": len(evidence),
            "context_blocks": sum(len(BLOCK.findall(it["golden_context"])) for it in items),
            "entries_with_context_text": len(evidence),
            "entries_with_repeated_context_text": sum(len(e["context_labels"]) > 1 for e in evidence),
            "original_chunk_ids_live": sum(e["golden_chunk_id"] in live_ids for e in evidence),
            "minimum_normalized_length": MIN_EVIDENCE_LENGTH}


def labelled_sample(items: list[dict], chunks: list[dict]) -> pd.DataFrame:
    bodies = {c["chunk_id"]: c["body"] for c in chunks}
    pairs = [{"question_id": it["id"], "doc_id": e["doc_id"], "chunk_id": e["chunk_id"],
              "golden_evidence_text": e["text"], "matched_chunk_text": bodies[e["chunk_id"]]}
             for it in items for e in it["evidence"] if e["chunk_id"]]
    pairs.sort(key=lambda p: (p["question_id"], p["chunk_id"], p["golden_evidence_text"]))
    return pd.DataFrame(random.Random(42).sample(pairs, min(30, len(pairs))),
                        columns=["question_id", "doc_id", "chunk_id", "golden_evidence_text", "matched_chunk_text"])
