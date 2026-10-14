"""분포 계획: eligible 단위로만 근거 묶음을 만들고, 계획을 해시로 고정하며, 판정과 다른 패키지면 멈춘다."""
import pytest

from golden_pipeline import evidence, storage
from golden_pipeline.plan import _groups, load_plan, make_plan, topic_spec

DOC_1, DOC_2 = "1" * 64, "2" * 64
COUNTS = {"numeric": 1, "table": 1, "condition": 1, "comparison": 1}


def unit_ids(plan, topic=None):
    return [u["unit_id"] for b in plan["bundles"] if topic in (None, b["topic"]) for u in b["units"]]


def test_bundles_use_only_eligible_units_once_and_carry_their_context(evidence_run):
    path = make_plan("p1", "ev1", COUNTS, 2000, package=evidence_run)
    plan, sha = load_plan("p1")

    assert sha == storage._sha256(path)
    assert "u7" not in unit_ids(plan)  # held 단위 (숫자가 있어 numeric 패턴에는 맞는다)
    assert len(unit_ids(plan)) == len(set(unit_ids(plan)))
    assert unit_ids(plan, "numeric") == ["u1", "u2"]
    assert unit_ids(plan, "table") == ["u3", "u4", "u5"]
    assert unit_ids(plan, "condition") == ["u6", "u8"]
    assert plan["planned"] == {"numeric": 1, "table": 1, "condition": 1, "comparison": 0}
    assert plan["coverage"] == {"numeric": {DOC_1: 1}, "table": {DOC_1: 1}, "condition": {DOC_2: 1}}
    assert plan["v11_manifest_sha256"] == storage._sha256(evidence_run / "manifest.json")
    assert plan["topic_specs"]["numeric"] == storage._sha256(storage.CONFIGS / "topics" / "numeric.json")

    table = next(b for b in plan["bundles"] if b["topic"] == "table")
    assert table["context"] == "[E1]\n구분 | A안 | B안\n\n[E2]\n예산 | 1억원 | 2억원\n\n[E3]\n기간 | 6개월 | 12개월"
    assert table["units"][1]["ref"]["location"] == {"kind": "table", "grid": "logical_restored", "row": 1, "cell": None}


def test_plan_is_never_overwritten(evidence_run):
    path = make_plan("p1", "ev1", COUNTS, 2000, package=evidence_run)
    before = path.read_bytes()

    with pytest.raises(FileExistsError):
        make_plan("p1", "ev1", {"numeric": 2}, 2000, package=evidence_run)
    assert path.read_bytes() == before


def test_documents_are_taken_in_turn_and_long_contexts_are_left_out(evidence_run):
    make_plan("p1", "ev1", {"numeric": 2}, 2000, package=evidence_run)
    plan = load_plan("p1")[0]
    assert plan["coverage"] == {"numeric": {DOC_1: 1, DOC_2: 1}}
    assert unit_ids(plan) == ["u1", "u2", "u6", "u8"]  # DOC_2 의 held 단위 u7 을 건너뛴다

    make_plan("p2", "ev1", {"numeric": 2}, 60, package=evidence_run)
    plan = load_plan("p2")[0]
    assert all(len(b["context"]) <= 60 for b in plan["bundles"])
    assert unit_ids(plan) == ["u3", "u4", "u5"]  # 표 행 u4 · u5 에 머리글 행 u3 이 붙는다


def table_row(row, text):
    location = {"kind": "table", "grid": "logical_restored", "row": row, "cell": None}
    return {"unit_id": f"r{row}", "ref": {"doc_sha": DOC_1, "element_id": "e-table", "location": location}, "text": text}


@pytest.mark.parametrize("header_eligible", [True, False])
def test_table_rows_are_bundled_with_their_header_row_or_left_out(header_eligible):
    rows = [table_row(0, "구분 | A안 | B안")] + [table_row(n, f"항목{n} | {n}억원 | {n + 1}억원") for n in range(1, 6)]
    units = rows if header_eligible else rows[1:]

    bundles = _groups("table", topic_spec("table")[0], units, set(), 2000)[DOC_1]

    if header_eligible:
        assert [[u["unit_id"] for u in b["units"]] for b in bundles] == [["r0", "r1", "r2"], ["r0", "r3", "r4", "r5"]]
        assert bundles[1]["context"].startswith("[E1]\n구분 | A안 | B안")
    else:
        assert bundles == []


def test_package_that_differs_from_the_judged_one_stops_the_plan(evidence_run):
    elements = evidence_run / "final_elements.jsonl"
    elements.write_text(elements.read_text(encoding="utf-8").replace("130,000,000", "150,000,000"), encoding="utf-8")

    with pytest.raises(evidence.PackageMismatch, match="final_elements.jsonl"):
        make_plan("p1", "ev1", COUNTS, 2000, package=evidence_run)


@pytest.mark.parametrize("counts", [{"numerics": 1}, {"numeric": 0}, {"numeric": "1"}])
def test_counts_must_name_topics_with_positive_integers(evidence_run, counts):
    with pytest.raises(ValueError, match="counts"):
        make_plan("p1", "ev1", counts, 2000, package=evidence_run)

