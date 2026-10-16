"""실제 파일 SHA와 골든 좌표를 쓰되 API·색인 없이 라벨 연결을 검증한다."""
import hashlib
import io
import json
import unicodedata
import zipfile

import fitz
import pandas as pd
import pytest
import yaml

from rag.config import ROOT, read_jsonl, write_jsonl
from rag.preprocessing.chunking import chunk_documents, load_v11_package, save_chunks
from rag.preprocessing.parsing import collect_inputs, parse_documents
from rag.validation.evidence import (
    correspondence_report,
    document_report,
    label_evidence,
    labelled_sample,
    mapping_report,
)
from rag.validation.validation import check_eval_items, load_eval_items


TEXT = "사업 기간은 계약 체결일로부터 정확히 180일입니다."


@pytest.fixture
def mapping_input(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "문서.hwp").write_bytes(b"raw document bytes")
    sha = hashlib.sha256(b"raw document bytes").hexdigest()
    element = {"element_id": "el", "search_text": TEXT, "table": None,
               "location": {"span_text_field": "search_text",
                            "supplier_metadata": {"source_paths": ["문서.hwp"], "doc_id": sha, "sha256": sha}}}
    write_jsonl([element], tmp_path / "final_elements.jsonl")
    ref = {"doc_sha": sha, "chunk_id": "old", "element_id": "el",
           "location": {"kind": "char", "start": 0, "end": len(TEXT)}}
    golden = {"candidate_id": "q", "question": "기간은?", "answer": "180일", "primary_topic": "numeric",
              "structure": {"value": "180", "unit": "일"}, "evidence": [ref], "context": "[E1]\n" + TEXT}
    write_jsonl([golden], tmp_path / "dev.jsonl")
    [item] = load_eval_items([str(tmp_path / "dev.jsonl")])
    chunk = {"chunk_id": "live", "doc_id": "doc", "source": "문서.hwp", "body": TEXT}
    return item, chunk, raw, tmp_path


@pytest.mark.parametrize("case, expected", [
    ("unique", None), ("duplicate", "ambiguous"), ("other_document", "not_found"),
    ("unmapped", "doc_unmapped"), ("short", "too_short"),
])
def test_document_scoped_exact_label(mapping_input, case, expected):
    item, chunk, raw, package = mapping_input
    chunks = [chunk]
    if case == "duplicate":
        chunks.append({**chunk, "chunk_id": "second"})
    if case == "other_document":
        chunks = [{**chunk, "body": "다른 본문"}, {**chunk, "doc_id": "other", "chunk_id": "other-chunk"}]
        # 원본 파일명은 한 문서에만 연결된다.
        chunks[1]["source"] = "다른.hwp"
    if case == "unmapped":
        item["golden_evidence"][0]["doc_sha"] = "0" * 64
    if case == "short":
        item["golden_evidence"][0]["location"]["end"] = 3
        item["golden_context"] = "[E1]\n" + TEXT[:3]

    [labelled] = label_evidence([item], chunks, raw, package, raw)
    [evidence] = labelled["evidence"]

    assert evidence["reason"] == expected
    assert evidence["chunk_id"] == ("live" if expected is None else None)
    assert evidence["golden_chunk_id"] == "old"
    assert labelled["doc_ids"] == ([] if case == "unmapped" else ["doc"])


def test_table_text_normalization_and_context_correspondence(mapping_input):
    item, chunk, raw, package = mapping_input
    text = "사업 기간 | 계약 체결 후\n180일 동안 모든 업무 수행"
    element = {"element_id": "table", "table": {"cells": [
        {"row": 1, "col": 1, "text": "계약 체결 후\n180일 동안 모든 업무 수행"},
        {"row": 0, "col": 0, "text": "인용하지 않은 머리글"},
        {"row": 1, "col": 0, "text": "사업 기간"},
    ]}, "location": {"supplier_metadata": {"source_paths": ["문서.hwp"],
                                          "doc_id": item["golden_evidence"][0]["doc_sha"],
                                          "sha256": item["golden_evidence"][0]["doc_sha"]}}}
    write_jsonl([element], package / "final_elements.jsonl")
    item["golden_evidence"][0].update(element_id="table", location={"kind": "table", "row": 1, "cell": None})
    item["golden_context"] = "[E1 · 머리글 행]\n다른 글\n\n[E2]\n" + text + "\n\n[E3]\n" + text
    chunk["body"] = unicodedata.normalize("NFD", "서문 사업 기간    계약 체결 후\t180일 동안 모든 업무 수행 맺음")
    chunk["source"] = unicodedata.normalize("NFD", chunk["source"])

    [labelled] = label_evidence([item], [chunk], raw, package, raw)
    [ref] = labelled["evidence"]

    assert ref["text"] == text
    assert ref["context_labels"] == ["E2", "E3"]
    assert ref["chunk_id"] == "live"
    assert correspondence_report([item], [labelled], [chunk]) == {
        "questions": 1, "evidence_entries": 1, "context_blocks": 3, "entries_with_context_text": 1,
        "entries_with_repeated_context_text": 1, "original_chunk_ids_live": 0, "minimum_normalized_length": 20}


def test_context_mismatch_stops_instead_of_using_another_block(mapping_input):
    item, chunk, raw, package = mapping_input
    item["golden_context"] = "[E1]\n무관한 글"
    with pytest.raises(ValueError, match="context"):
        label_evidence([item], [chunk], raw, package, raw)


def test_labels_survive_validation_and_yaml_has_no_golden_evidence(mapping_input):
    item, chunk, raw, package = mapping_input
    path = package / "questions.yaml"
    path.write_text("- {id: manual, question: 수동 질문, reference: 답, must_include: [답]}\n", encoding="utf-8")
    yaml_items = load_eval_items([str(path)])
    labelled = label_evidence([item, *yaml_items], [chunk], raw, package, raw)

    kept, _ = check_eval_items(labelled)

    assert kept[0]["evidence"][0]["chunk_id"] == "live"
    assert kept[0]["doc_ids"] == ["doc"]
    assert kept[1]["evidence_source"] == "none"
    assert kept[1]["evidence"] == kept[1]["doc_ids"] == []
    assert "golden_context" not in kept[0] and "golden_evidence" not in kept[0]


def test_reports_count_entries_and_question_completeness_separately(mapping_input):
    item, chunk, raw, package = mapping_input
    [labelled] = label_evidence([item], [chunk], raw, package, raw)
    ref = labelled["evidence"][0]
    items = [
        {**labelled, "primary_topic": "multi_hop", "evidence": [ref, ref]},
        {**labelled, "primary_topic": "multi_hop", "evidence": [ref, {**ref, "chunk_id": None, "reason": "ambiguous"}]},
        {**labelled, "primary_topic": "comparison", "evidence": [{**ref, "chunk_id": None, "reason": "too_short"}]},
    ]
    report = mapping_report({"dev": items, "test": [items[2]]}).set_index(["split", "primary_topic"])

    assert report.loc[("dev", "ALL"), ["evidence_entries", "labelled", "ambiguous", "too_short"]].tolist() == [5, 3, 1, 1]
    assert report.loc[("dev", "ALL"), ["fully_labelled", "partly_labelled", "not_labelled"]].tolist() == [1, 1, 1]
    assert report.loc[("dev", "multi_hop"), "chunk_rate"] == 0.75
    assert report.loc[("test", "comparison"), "not_labelled"] == 1
    assert document_report({"dev": items})["doc_id"].tolist() == ["doc"]


def test_sample_is_fixed_seed_30_pairs_with_full_chunk_body(mapping_input):
    item, chunk, raw, package = mapping_input
    chunk["body"] = "청크 앞부분\n" + TEXT + "\n청크 뒷부분"
    [labelled] = label_evidence([item], [chunk], raw, package, raw)
    items = [{**labelled, "id": str(i)} for i in range(40)]
    sample = labelled_sample(items, [chunk])

    assert len(sample) == sample["question_id"].nunique() == 30
    assert sample.equals(labelled_sample(list(reversed(items)), [chunk]))
    assert sample["golden_evidence_text"].tolist() == [TEXT] * 30
    assert sample["matched_chunk_text"].tolist() == [chunk["body"]] * 30


@pytest.mark.parametrize("count", [0, 2])
def test_small_sample_displays_all_available_pairs(mapping_input, count):
    item, chunk, raw, package = mapping_input
    [labelled] = label_evidence([item], [chunk], raw, package, raw)
    items = [{**labelled, "id": str(i)} for i in range(count)]
    sample = labelled_sample(items, [chunk])
    assert len(sample) == count
    assert sample.columns.tolist() == [
        "question_id", "doc_id", "chunk_id", "golden_evidence_text", "matched_chunk_text"]


@pytest.mark.parametrize("field", ["sha256", "doc_id", "source_paths"])
def test_v11_identity_requires_sha_id_and_source_agreement(mapping_input, field):
    item, chunk, raw, package = mapping_input
    chunk["doc_id"] = item["golden_evidence"][0]["doc_sha"]
    [element] = read_jsonl(package / "final_elements.jsonl")
    element["location"]["supplier_metadata"][field] = ["다른.hwp"] if field == "source_paths" else "wrong"
    write_jsonl([element], package / "final_elements.jsonl")
    [labelled] = label_evidence([item], [chunk], package / "absent", package, package / "absent.zip")
    assert labelled["doc_ids"] == []
    assert labelled["evidence"][0]["reason"] == "doc_unmapped"


def _pdf_input(tmp_path, route, data):
    source = tmp_path / "source"
    source.mkdir()
    path = source / "사업.pdf"
    if route in ("directory", "file"):
        path.write_bytes(data)
        return source if route == "directory" else path
    archive = source / "input.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("사업.pdf", data)
    if route == "directory_zip":
        return source
    if route == "nested_zip":
        outer = tmp_path / "outer.zip"
        with zipfile.ZipFile(outer, "w") as zipped:
            zipped.write(archive, "input.zip")
        return outer
    return archive


def _source_golden(package, text, sha):
    metadata = {"source_paths": ["사업.pdf"], "doc_id": sha, "sha256": sha}
    element = {"element_id": "el", "search_text": text,
               "location": {"span_text_field": "search_text", "page": 1, "supplier_metadata": metadata}}
    write_jsonl([element], package / "final_elements.jsonl")
    golden = {"candidate_id": "q", "question": "기간은?", "answer": "180일", "primary_topic": "numeric",
              "structure": {"value": "180", "unit": "일"}, "context": "[E1]\n" + text,
              "evidence": [{"doc_sha": sha, "chunk_id": "v11-chunk", "element_id": "el",
                            "location": {"kind": "char", "start": 0, "end": len(text)}}]}
    write_jsonl([golden], package / "dev.jsonl")
    return load_eval_items([str(package / "dev.jsonl")])


@pytest.mark.parametrize("route", ["v11", "directory", "file", "zip", "nested_zip", "directory_zip"])
def test_supported_ingestion_to_evidence_labels_without_previous_artifacts(tmp_path, route):
    text = "The project must be completed within exactly 180 days after signing."
    with fitz.open() as pdf:
        pdf.new_page().insert_text((72, 72), text)
        data = pdf.tobytes()
    sha = hashlib.sha256(data).hexdigest()
    package = tmp_path / "package"
    package.mkdir()
    items = _source_golden(package, text, sha)
    out = tmp_path / "artifacts"
    input_path = tmp_path / "absent.zip"
    if route == "v11":
        write_jsonl([{"doc_id": sha, "sha256": sha, "source_paths": ["사업.pdf"], "search_text": text}],
                    package / "final_records.jsonl")
        write_jsonl([{"chunk_id": "v11-chunk", "body": text, "payload": text, "chunk_type": "prose",
                      "section_path": [], "spans": [{"element_id": "el"}]}], package / "final_chunks.jsonl")
        docs, chunks = load_v11_package(package)
    else:
        input_path = _pdf_input(tmp_path, route, data)
        files = collect_inputs(input_path, out / "raw")
        cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
        cfg["parsing"]["skip_first_pages"] = 0
        docs = parse_documents(files, cfg["parsing"], ocr=False, ocr_cfg={}, cache_dir=out / "parsed")
        chunks = chunk_documents(docs, cfg["chunking"], out / "chunked")
    save_chunks(docs, chunks, out)
    if route in ("v11", "directory", "file"):
        assert not (out / "raw").exists()
    labelled_items = label_evidence(items, read_jsonl(out / "chunks.jsonl"), out / "raw", package, input_path)
    [labelled], _ = check_eval_items(labelled_items)
    assert labelled["doc_ids"] == [chunks[0]["doc_id"]]
    assert labelled["evidence"][0]["chunk_id"] == chunks[0]["chunk_id"]
    assert len(labelled_sample(labelled_items, chunks)) == 1
    assert mapping_report({"dev": labelled_items})["doc_unmapped"].sum() == 0


def _two_document_items(package, first, second):
    [item] = _source_golden(package, TEXT, hashlib.sha256(first).hexdigest())
    other = {**item, "id": "other", "golden_evidence": [
        {**item["golden_evidence"][0], "doc_sha": hashlib.sha256(second).hexdigest()}]}
    return [item, other]


@pytest.mark.parametrize("route", ["zip", "nested_zip", "directory_zip"])
def test_zip_labels_do_not_depend_on_previous_nested_extractions(tmp_path, route):
    previous, current = b"previous document bytes", b"different current document bytes"
    nested = io.BytesIO()
    with zipfile.ZipFile(nested, "w") as archive:
        archive.writestr("사업.pdf", previous)
    old_zip = tmp_path / "old-run.zip"
    with zipfile.ZipFile(old_zip, "w") as archive:
        archive.writestr("old.zip", nested.getvalue())
    raw = tmp_path / "artifacts/raw"
    collect_inputs(old_zip, raw)
    input_path = _pdf_input(tmp_path, route, current)
    collect_inputs(input_path, raw)
    package = tmp_path / "package"
    package.mkdir()
    items = _two_document_items(package, previous, current)
    chunks = [{"source": "사업.pdf", "doc_id": "current", "chunk_id": "live", "body": TEXT}]

    labelled = label_evidence(items, chunks, raw, package, input_path)

    assert labelled[0]["evidence"][0]["reason"] == "doc_unmapped"
    assert labelled[0]["evidence"][0]["chunk_id"] is None
    assert labelled[1]["evidence"][0]["chunk_id"] == "live"
    clean_raw = tmp_path / "clean/raw"
    collect_inputs(input_path, clean_raw)
    assert labelled == label_evidence(items, chunks, clean_raw, package, input_path)


def test_zip_rejects_cached_bytes_that_do_not_match_the_current_archive(tmp_path):
    previous, current = b"old!", b"new!"
    raw = tmp_path / "raw"
    for name, data in [("previous", previous), ("current", current)]:
        with zipfile.ZipFile(tmp_path / f"{name}.zip", "w") as archive:
            archive.writestr("사업.pdf", data)
        collect_inputs(tmp_path / f"{name}.zip", raw)
    # 01은 길이가 같은 기존 파일을 다시 풀지 않으므로 아카이브 본문과의 대조가 필요하다.
    assert (raw / "사업.pdf").read_bytes() == previous
    package = tmp_path / "package"
    package.mkdir()
    items = _two_document_items(package, previous, current)
    chunks = [{"source": "사업.pdf", "doc_id": "current", "chunk_id": "live", "body": TEXT}]

    labelled = label_evidence(items, chunks, raw, package, tmp_path / "current.zip")

    assert all(it["doc_ids"] == [] and it["evidence"][0]["chunk_id"] is None for it in labelled)
    assert all(it["evidence"][0]["reason"] == "doc_unmapped" for it in labelled)


def test_different_active_files_with_the_same_source_name_are_not_certified(tmp_path):
    source = tmp_path / "source"
    for name, data in [("a", b"first document"), ("b", b"second document")]:
        folder = source / name
        folder.mkdir(parents=True)
        (folder / "사업.pdf").write_bytes(data)
    package = tmp_path / "package"
    package.mkdir()
    items = _two_document_items(package, b"first document", b"second document")
    chunks = [{"source": "사업.pdf", "doc_id": "current", "chunk_id": "live", "body": TEXT}]

    labelled = label_evidence(items, chunks, tmp_path / "absent-raw", package, source)

    assert all(it["doc_ids"] == [] and it["evidence"][0]["reason"] == "doc_unmapped" for it in labelled)
