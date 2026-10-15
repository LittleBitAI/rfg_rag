"""분포 계획: eligible 단위로만 근거 묶음을 만들고, 계획을 해시로 고정하며, 판정과 다른 패키지면 멈춘다."""
import pytest

from golden_pipeline import evidence, storage
from golden_pipeline.plan import _groups, _is_toc, load_plan, make_plan, topic_spec

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
    # 질문 앞에 붙일 문서 이름: 정리된 발주 기관(data_list.csv)과 파일 이름의 사업 이름 ([재공고] 같은 표시는 뺀다).
    assert table["doc"] == {"agency": "가기관", "title": "가사업 구축"}
    condition = next(b for b in plan["bundles"] if b["topic"] == "condition")
    assert condition["doc"] == {"agency": "나기관", "title": "나사업 운영"}
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


def test_units_of_a_skipped_plan_are_left_out_and_the_skip_is_recorded(evidence_run):
    # 묶음은 늘 같은 순서로 골라, 빼지 않으면 재생성 계획이 앞 계획의 묶음을 그대로 다시 뽑는다.
    first = make_plan("p1", "ev1", {"numeric": 1}, 2000, package=evidence_run)
    make_plan("p2", "ev1", {"numeric": 1}, 2000, package=evidence_run, skip_plans=["p1"])
    before, after = load_plan("p1")[0], load_plan("p2")[0]

    assert unit_ids(after) and not set(unit_ids(after)) & set(unit_ids(before))
    assert after["skipped_plans"] == {"p1": storage._sha256(first)}


def table_row(row, text):
    location = {"kind": "table", "grid": "logical_restored", "row": row, "cell": None}
    return {"unit_id": f"r{row}", "ref": {"doc_sha": DOC_1, "element_id": "e-table", "location": location}, "text": text}


def six_rows():
    return [table_row(0, "구분 | A안 | B안")] + [table_row(n, f"항목{n} | {n}억원 | {n + 1}억원") for n in range(1, 6)]


NAMES = {DOC_1: {"agency": "가기관", "title": "가사업 구축"}}


def test_header_row_owned_by_an_earlier_topic_is_not_inserted_again():
    rows = six_rows()
    [numeric, *_] = _groups("numeric", topic_spec("numeric")[0], rows, set(), 2000, NAMES)[DOC_1]
    used = {u["unit_id"] for u in numeric["units"]}
    assert used == {"r0", "r1", "r2"}

    # 남은 r3 · r4 · r5 는 머리글 r0 을 numeric 이 가져 열 이름 없이 남으므로 묶음이 되지 않는다.
    assert _groups("table", topic_spec("table")[0], rows, used, 2000, NAMES)[DOC_1] == []


def char_unit(unit_id, chunk_id):
    location = {"kind": "char", "start": 0, "end": 1}
    return {"unit_id": unit_id, "ref": {"doc_sha": DOC_1, "chunk_id": chunk_id, "element_id": f"e-{unit_id}",
                                        "location": location}, "text": f"본문 {unit_id}"}


def test_multi_hop_bundles_cross_a_chunk_boundary():
    # 한 청크 안의 단위만 받은 묶음은 청크 둘을 잇는 질문이 나올 수 없어, 늘 거절되면서 생성 · 검증 호출만 쓴다.
    units = [char_unit(f"a{n}", "chunk-a") for n in (1, 2, 3, 4)] + [char_unit(f"b{n}", "chunk-b") for n in (1, 2)]

    [bundle] = _groups("multi_hop", topic_spec("multi_hop")[0], units, set(), 2000, NAMES)[DOC_1]

    assert [u["unit_id"] for u in bundle["units"]] == ["a3", "a4", "b1"]


@pytest.mark.parametrize("header_eligible", [True, False])
def test_table_rows_are_bundled_with_their_header_row_or_left_out(header_eligible):
    rows = six_rows()
    units = rows if header_eligible else rows[1:]

    bundles = _groups("table", topic_spec("table")[0], units, set(), 2000, NAMES)[DOC_1]

    if header_eligible:
        assert [[u["unit_id"] for u in b["units"]] for b in bundles] == [["r0", "r1", "r2"], ["r0", "r3", "r4", "r5"]]
        assert bundles[1]["context"].startswith("[E1]\n구분 | A안 | B안")
    else:
        assert bundles == []


@pytest.mark.parametrize("text, toc", [
    ("Ⅰ. 제안 요청내용 01\n 1. 용역개요 02 \n 2. 기본방향 03", True),
    ("사업 예산은 130,000,000원이며\n계약 기간은 12개월이다.", False),
    ("구분 | A안 | 12", False),
])
def test_table_of_contents_text_is_recognised(text, toc):
    # 목차로 만든 질문(어느 항목이 몇 쪽인가)은 RFP 내용을 묻지 않아 근거 묶음에서 뺀다.
    assert _is_toc(text) is toc


def test_package_that_differs_from_the_judged_one_stops_the_plan(evidence_run):
    elements = evidence_run / "final_elements.jsonl"
    elements.write_text(elements.read_text(encoding="utf-8").replace("130,000,000", "150,000,000"), encoding="utf-8")

    with pytest.raises(evidence.PackageMismatch, match="final_elements.jsonl"):
        make_plan("p1", "ev1", COUNTS, 2000, package=evidence_run)


@pytest.mark.parametrize("counts", [{"numerics": 1}, {"numeric": 0}, {"numeric": "1"}])
def test_counts_must_name_topics_with_positive_integers(evidence_run, counts):
    with pytest.raises(ValueError, match="counts"):
        make_plan("p1", "ev1", counts, 2000, package=evidence_run)

