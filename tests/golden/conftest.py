"""테스트 출력을 실제 golden_pipeline/outputs 와 분리하고, 유효한 항목 견본과 가짜 근거 어댑터 run 을 만든다."""
import copy
import json
import shutil

import pytest

from golden_pipeline import generation, storage

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
    return root


DOC_1 = "1" * 64
DOC_2 = "2" * 64
# (unit_id, 문서, 요소 본문 또는 표 행, 판정). 표 행은 요소 e-table 의 칸들이다.
UNITS = [
    ("u1", DOC_1, "사업 예산은 130,000,000원(부가세 포함)이며 계약 기간은 12개월이다.", "eligible"),
    ("u2", DOC_1, "다만, 하자 보수 기간은 계약 종료 후 1년 이내로 한다.", "eligible"),
    ("u3", DOC_1, ["구분", "A안", "B안"], "eligible"),
    ("u4", DOC_1, ["예산", "1억원", "2억원"], "eligible"),
    ("u5", DOC_1, ["기간", "6개월", "12개월"], "eligible"),
    ("u6", DOC_2, "제안서는 11월 3일까지 제출한다. 단, 우편 접수는 받지 않는다.", "eligible"),
    ("u7", DOC_2, "평가 위원은 7명으로 구성한다.", "held"),
    ("u8", DOC_2, "입찰 보증금은 입찰 금액의 5% 이상으로 한다.", "eligible"),
]


def _unit(unit_id, doc, body, row):
    if isinstance(body, list):
        element_id, location = "e-table", {"kind": "table", "grid": "logical_restored", "row": row, "cell": None}
    else:
        element_id, location = f"e-{unit_id}", {"kind": "char", "start": 0, "end": len(body)}
    return {
        "unit_id": unit_id, "doc_sha": doc, "chunk_id": f"c-{unit_id}", "element_id": element_id,
        "record_id": f"r-{unit_id}", "location": location, "page": None, "requirement_ids": [],
        "image_sha": None, "ocr_scope": None, "raw_start": 0, "raw_end": 1, "source_units": [],
        "ids_linked": True, "meaning_verified": True,
    }


def _write_jsonl(path, rows):
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


@pytest.fixture
def evidence_run(outputs, tmp_path):
    """근거 어댑터 run 'ev1' 과 그 run 이 고정한 가짜 v11 패키지를 만들고 패키지 경로를 돌려준다.

    주제 명세와 프롬프트는 실제 파일을 복사해 실제 명세로 묶음을 고르고 검사한다.
    """
    shutil.copytree(storage.PACKAGE / "configs", outputs / "configs", dirs_exist_ok=True)
    shutil.copytree(storage.PACKAGE / "prompts", outputs / "prompts", dirs_exist_ok=True)
    package = tmp_path / "v11"
    package.mkdir()
    rows = [body for _, _, body, _ in UNITS if isinstance(body, list)]
    cells = [{"row": r, "col": c, "text": text} for r, row in enumerate(rows) for c, text in enumerate(row)]
    elements = [{"element_id": "e-table", "search_text": "표", "table": {"cells": cells},
                 "location": {"span_text_field": "search_text"}}]
    elements += [{"element_id": f"e-{unit_id}", "search_text": body, "table": None,
                  "location": {"span_text_field": "search_text"}}
                 for unit_id, _, body, _ in UNITS if isinstance(body, str)]
    _write_jsonl(package / "final_elements.jsonl", elements)
    _write_jsonl(package / "final_records.jsonl", [
        {"doc_id": DOC_1, "source_paths": ["원본 데이터/files/가기관_가사업 구축.hwp"]},
        {"doc_id": DOC_2, "source_paths": ["원본 데이터/files/나기관_나사업 운영.hwp"]},
    ])
    (package / "manifest.json").write_text('{"package": "fake v11"}', encoding="utf-8")

    run_dir = outputs / "outputs" / "evidence" / "ev1"
    run_dir.mkdir(parents=True)
    table_rows = iter(range(len(rows)))
    _write_jsonl(run_dir / "units.jsonl", [
        _unit(unit_id, doc, body, next(table_rows) if isinstance(body, list) else None)
        for unit_id, doc, body, _ in UNITS
    ])
    _write_jsonl(run_dir / "judgments.jsonl", [
        {"unit_id": unit_id, "judgment": judgment, "reasons": []} for unit_id, _, _, judgment in UNITS
    ])
    pinned = {name: storage._sha256(package / name) for name in ("manifest.json", "final_elements.jsonl")}
    (run_dir / "manifest.json").write_text(json.dumps({"pinned_sha256": pinned}), encoding="utf-8")
    return package
