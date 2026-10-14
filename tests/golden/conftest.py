"""테스트 출력을 실제 golden_pipeline/outputs 와 분리하고, 유효한 항목 견본을 만든다."""
import copy

import pytest

from golden_pipeline import storage

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
            "ocr_scope": "human_verified",
        },
    ],
    "generator_version": "gen-0.1",
    "validator_version": None,
    "prompt_version": "prompt-0.1",
    "state": "candidate",
    "state_history": [],
}


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
