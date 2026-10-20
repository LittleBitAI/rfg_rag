"""테스트 출력을 실제 golden_pipeline/outputs 와 분리하고, 유효한 항목 견본과 가짜 근거 어댑터 run 을 만든다."""
import copy
import json
import shutil
import unicodedata

import pytest

from golden_pipeline import adoption, evidence, generation, plan, storage

DOC_SHA = "a" * 64
IMAGE_SHA = "b" * 64

ITEM = {
    "candidate_id": "numeric-A-r1-0001",
    "parent_candidate_id": None,
    "run_id": "r1",
    "method": "A",
    "primary_topic": "numeric",
    "secondary_tags": ["table"],
    "question": "사업 예산은 얼마인가?",
    "answer": "1억 3천만원(부가세 포함)",
    "evidence": [
        {
            "doc_sha": DOC_SHA,
            "chunk_id": "c-12",
            "element_id": "e-34",
            "record_id": "r-56",
            "location": {"kind": "char", "start": 10, "end": 42},
            "page": None,
            "requirement_ids": ["SFR-001"],
            "image_sha": None,
            "ocr_scope": None,
        },
        {
            "doc_sha": DOC_SHA,
            "chunk_id": "c-13",
            "element_id": "e-35",
            "record_id": "r-57",
            "location": {"kind": "table", "grid": "logical_restored", "row": 2, "cell": 1},
            "page": 7,
            "requirement_ids": [],
            "image_sha": IMAGE_SHA,
            "ocr_scope": "full_visible_text",
        },
    ],
    "bundle_id": "b-0001",
    "context": "[E1]\n사업 예산은 1억 3천만원(부가세 포함)이다",
    "structure": {"value": "1억 3천만", "unit": "원"},
    "generator_version": "gen-0.1",
    "validator_version": None,
    "prompt_version": "prompt-0.1",
    "difficulty": None,
    "state": "candidate",
    "state_history": [],
}


@pytest.fixture(autouse=True)
def one_worker(monkeypatch):
    """가짜 생성기 · 검증기는 받은 차례대로 답한다. 호출 차례가 정해지도록 테스트에서는 한 번에 하나씩 보낸다."""
    monkeypatch.setattr(generation, "WORKERS", 1)


@pytest.fixture
def measure_bundles(monkeypatch):
    """loop 는 계획의 validation · held-out 몫으로 정책을 잰다. 계획에 예산 묶음을 본뜬 묶음을 몫마다 하나씩 더한다.

    본뜬 묶음은 단위 id 만 달라 묶음 id 가 다르고 근거 · 본문은 같다. 나머지 묶음은 모두 train 몫이다.
    """
    def add(plan_id):
        path = storage.OUTPUTS / "plans" / f"{plan_id}.json"
        planned = json.loads(path.read_text(encoding="utf-8"))
        budget = next(bundle for bundle in planned["bundles"] if "130,000,000원" in bundle["context"])
        parts = {}
        for part in ("validation", "held_out"):
            units = [{**{key: value for key, value in unit.items() if key != "label"}, "unit_id": f"{unit['unit_id']}-{part}"}
                     for unit in budget["units"]]
            bundle = plan._bundle(budget["topic"], units, budget["doc"])
            planned["bundles"].append(bundle)
            parts[bundle["bundle_id"]] = part
        path.write_text(json.dumps(planned, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        monkeypatch.setattr(adoption, "split", lambda bundle_id: parts.get(bundle_id, "train"))
        return parts
    return add


@pytest.fixture
def make_item():
    def make(**overrides):
        item = copy.deepcopy(ITEM)
        item.update(overrides)
        return item
    return make


@pytest.fixture
def outputs(monkeypatch, tmp_path):
    root = tmp_path / "golden_pipeline"
    for name in ("outputs", "configs", "prompts"):
        (root / name).mkdir(parents=True)
    monkeypatch.setattr(storage, "OUTPUTS", root / "outputs")
    monkeypatch.setattr(storage, "CONFIGS", root / "configs")
    monkeypatch.setattr(storage, "PROMPTS", root / "prompts")
    # cli --experiment 가 모듈 값을 바꾸므로 테스트마다 되돌린다.
    monkeypatch.setattr(storage, "EXPERIMENT", None)
    return root


DOC_1 = "1" * 64
DOC_2 = "2" * 64
# (unit_id, 문서, 청크 본문 또는 표 행, 판정). 표 행은 요소 e-table 의 칸들이다.
UNITS = [
    ("u1", DOC_1, "사업 예산은 130,000,000원(부가세 포함)이며 계약 기간은 12개월이다.", "eligible"),
    ("u2", DOC_1, "다만, 하자 보수 기간은 계약 종료 후 1년 이내로 한다.", "eligible"),
    ("u3", DOC_1, ["구분", "A안", "B안"], "eligible"),
    ("u4", DOC_1, ["예산", "1억원", "2억원"], "eligible"),
    ("u5", DOC_1, ["기간", "6개월", "12개월"], "eligible"),
    ("u6", DOC_2, "제안서는 11월 3일까지 제출한다. 단, 우편 접수는 받지 않는다.", "eligible"),
    ("u7", DOC_2, "평가 위원은 7명으로 구성한다.", "held"),
    ("u8", DOC_2, "입찰 보증금은 입찰 금액의 5% 이상으로 한다.", "eligible"),
    # 원본 대조 예외로 보류된 청크. 문서에 없음을 보는 주제는 이 청크의 글까지 읽는다.
    ("u9", DOC_2, "하자 보수 기간: 2년", "held"),
]


def _chunk(unit_id, doc, body, row, judgment):
    """Build synthetic source records; let the real adapter determine units and judgments."""
    text = " | ".join(body) if isinstance(body, list) else body
    element_id = "e-table" if row is not None else f"e-{unit_id}"
    span = {"rows": [row, row]} if row is not None else {"start": 0, "end": len(text)}
    metadata = {"sha256": doc, "review_status": evidence.EXCEPTION if judgment == "held" else "자동 검사 완료",
                "exception_kinds": ["synthetic exception"] if judgment == "held" else []}
    return {"chunk_id": f"c-{unit_id}", "doc_id": doc, "source_sha256": doc, "body": text,
            "spans": [{"element_id": element_id, **span}], "requirement_ids": [], "image_source": None, "page": None,
            "source_locations": [{"element_id": element_id, "location": {"record_id": f"r-{unit_id}", "supplier_metadata": metadata}}]}


def _write_jsonl(path, rows):
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


@pytest.fixture
def evidence_run(outputs, tmp_path, monkeypatch):
    """Run the real adapter on a synthetic v12 package and isolate configs, prompts and outputs."""
    shutil.copytree(storage.PACKAGE / "configs", outputs / "configs", dirs_exist_ok=True)
    shutil.copytree(storage.PACKAGE / "prompts", outputs / "prompts", dirs_exist_ok=True)
    package = tmp_path / "v12"
    (package / "corpus").mkdir(parents=True)
    (package / "data").mkdir()
    monkeypatch.setattr(evidence, "PACKAGE", package)
    table_rows = iter(range(3))
    _write_jsonl(package / evidence.CHUNKS, [
        _chunk(unit_id, doc, body, next(table_rows) if isinstance(body, list) else None, judgment)
        for unit_id, doc, body, judgment in UNITS
    ])
    _write_jsonl(package / evidence.DOCS, [
        {"doc_id": DOC_1, "source": "사단법인가기관_가사업 구축.hwp"},
        # 실제 원본처럼 한 파일 이름은 NFD 로 둔다.
        {"doc_id": DOC_2, "source": unicodedata.normalize("NFD", "나기관_[재공고]나사업 운영.hwp")},
    ])
    (package / evidence.AGENCIES).write_text(
        "파일명,발주기관\n사단법인가기관_가사업 구축.hwp,가기관\n나기관_[재공고]나사업 운영.hwp,나기관\n", encoding="utf-8")
    (package / "manifest.json").write_text(json.dumps({"package": "fake v12",
        "counts": {"v12_search_chunks": len(UNITS), "v12_documents": 2}, "files": {
        name: {"sha256": storage._sha256(package / name)} for name in evidence.PINNED[1:]
    }}), encoding="utf-8")
    evidence.run("ev1", package=package)
    return package
