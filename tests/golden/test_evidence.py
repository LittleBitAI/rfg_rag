"""v12 근거 어댑터: 작은 가짜 패키지로 고정·개수·연결·판정을 확인한다."""
import copy
import hashlib
import json

import pytest

from golden_pipeline import evidence

DOC = "a" * 64
IMAGE = "c" * 64
PASSED = "자동 검사 완료·원본 완전성 미확인"


def _source(element_id, review_status=PASSED, exception_kinds=(), sha=DOC):
    metadata = {"sha256": sha, "review_status": review_status, "exception_kinds": list(exception_kinds)}
    return {"element_id": element_id, "location": {"record_id": f"r-{element_id}", "supplier_metadata": metadata}}


def _chunk(chunk_id, spans, body, image=None, page=None, requirement_ids=()):
    sources = [_source(element_id) for element_id in dict.fromkeys(span["element_id"] for span in spans)]
    return {"chunk_id": chunk_id, "doc_id": DOC, "source_sha256": DOC, "spans": spans, "body": body,
            "source_locations": sources, "image_source": image, "page": page, "requirement_ids": list(requirement_ids)}


BASE = [
    _chunk("c-text", [{"element_id": "e-text", "start": 3, "end": 12}], "사업 예산은 1억원이다", page=4),
    # 앞 글 뒤에 표가 이어진 청크. 위치는 첫 표 span 이다.
    _chunk("c-table", [{"element_id": "e-lead", "start": 0, "end": 4}, {"element_id": "e-table", "rows": [2, 3]}],
           "가. 예산\n예산 | 1억\n기간 | 6개월", requirement_ids=["SFR-001"]),
    _chunk("c-image", [{"element_id": "e-image", "start": 0, "end": 5}], "접수\n심사",
           image={"asset_sha256": IMAGE, "scope": "FULL_VISIBLE_TEXT"}),
]


def write_package(root, chunks, counts=None):
    """패키지 파일을 쓰고, 실제 개수와 파일 SHA 로 manifest.json 을 만든다."""
    (root / "corpus").mkdir(parents=True)
    (root / "data").mkdir()
    (root / evidence.CHUNKS).write_text("".join(json.dumps(c, ensure_ascii=False) + "\n" for c in chunks), encoding="utf-8")
    (root / evidence.DOCS).write_text(json.dumps({"doc_id": DOC, "source": "기관_사업.hwp"}) + "\n", encoding="utf-8")
    (root / evidence.AGENCIES).write_text("파일명,발주기관\n기관_사업.hwp,기관\n", encoding="utf-8")
    manifest = {
        "counts": {"v12_search_chunks": len(chunks), "v12_documents": 1, **(counts or {})},
        "files": {name: {"sha256": hashlib.sha256((root / name).read_bytes()).hexdigest()}
                  for name in evidence.PINNED[1:]},
    }
    (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return root


@pytest.fixture
def package(tmp_path):
    """고쳐 쓸 청크 목록을 받아 가짜 v12 패키지를 만든다."""
    def make(chunks=None, counts=None):
        return write_package(tmp_path / "v12", chunks or copy.deepcopy(BASE), counts)
    return make


def run(package_dir):
    out = evidence.run("r1", package=package_dir)
    units = [json.loads(line) for line in (out / "units.jsonl").read_text(encoding="utf-8").splitlines()]
    judgments = [json.loads(line) for line in (out / "judgments.jsonl").read_text(encoding="utf-8").splitlines()]
    return out, {unit["chunk_id"]: unit for unit in units}, {j["unit_id"]: j for j in judgments}


def test_run_pins_counts_and_writes_one_unit_per_chunk_with_separate_judgments(outputs, package):
    out, units, judgments = run(package())

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["pinned_sha256"]) == set(evidence.PINNED)
    assert manifest["counts"] == {"v12_search_chunks": 3, "v12_documents": 1}
    assert list(judgments) == [unit["unit_id"] for unit in units.values()]
    text = units["c-text"]
    assert (text["unit_id"], text["doc_sha"], text["record_id"], text["page"]) == ("chunk:c-text", DOC, "r-e-text", 4)
    assert text["location"] == {"kind": "char", "start": 3, "end": 12} and text["text"] == "사업 예산은 1억원이다"
    # 앞 글이 붙은 표 청크도 표 단위이고, 위치는 첫 표 span 의 요소와 첫 행이다. 본문은 청크 전체다.
    table = units["c-table"]
    assert table["location"] == {"kind": "table", "grid": "logical_restored", "row": 2, "cell": None}
    assert (table["element_id"], table["requirement_ids"]) == ("e-table", ["SFR-001"])
    assert table["text"] == "가. 예산\n예산 | 1억\n기간 | 6개월"
    assert {j["judgment"] for j in judgments.values()} == {"eligible"}


def test_run_stops_when_files_differ_from_manifest_declaration(outputs, package):
    root = package()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    manifest["files"][evidence.CHUNKS]["sha256"] = "0" * 64
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(evidence.PackageMismatch, match="chunks.jsonl"):
        evidence.run("r1", package=root)
    assert not (outputs / "outputs" / "evidence" / "r1").exists()


def test_counts_read_from_files_must_equal_manifest(outputs, package):
    with pytest.raises(evidence.PackageMismatch, match="v12_search_chunks"):
        evidence.run("r1", package=package(counts={"v12_search_chunks": 999}))


def test_a_chunk_the_package_marked_for_exception_review_is_held_although_ids_link(outputs, package):
    chunks = copy.deepcopy(BASE)
    chunks[0]["source_locations"] = [_source("e-text", "예외 검토 필요", ["띄어 쓴 단어 후보", "독음 미확정 한자"])]

    _, units, judgments = run(package(chunks))

    assert units["c-text"]["ids_linked"] is True and units["c-text"]["meaning_verified"] is False
    assert judgments["chunk:c-text"] == {"unit_id": "chunk:c-text", "judgment": "held",
                                         "reasons": ["원본 대조 예외: 독음 미확정 한자, 띄어 쓴 단어 후보"]}


def test_a_chunk_whose_source_names_another_document_is_held(outputs, package):
    chunks = copy.deepcopy(BASE)
    chunks[0]["source_locations"] = [_source("e-text", sha="d" * 64)]

    _, units, judgments = run(package(chunks))

    assert units["c-text"]["ids_linked"] is False
    assert judgments["chunk:c-text"]["reasons"] == ["청크 원본 위치의 문서 SHA 가 doc_id 와 다릅니다"]


@pytest.mark.parametrize("image, scope, judgment", [
    ({"asset_sha256": IMAGE, "scope": "PARTIAL_REGIONS"}, "partial_region", "eligible"),
    # 패키지의 이미지 하나는 scope 키 자체가 없다.
    ({"asset_sha256": IMAGE}, "hold", "held"),
])
def test_image_evidence_carries_sha_and_scope_and_is_held_without_one(outputs, package, image, scope, judgment):
    chunks = copy.deepcopy(BASE)
    chunks[2]["image_source"] = image

    _, units, judgments = run(package(chunks))

    assert (units["c-image"]["image_sha"], units["c-image"]["ocr_scope"]) == (IMAGE, scope)
    assert judgments["chunk:c-image"]["judgment"] == judgment


def test_linked_unit_without_verified_meaning_is_never_eligible():
    unit = {"unit_id": "u", "ids_linked": True, "meaning_verified": False}
    assert evidence.judge(unit, [])["judgment"] == "held"
