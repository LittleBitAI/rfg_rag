"""골든 항목 스키마. 새 패키지를 requirements.txt 에 넣지 않으려고 표준 라이브러리로만 검증한다."""
import re
from datetime import datetime, timedelta

from golden_pipeline.state import TRANSITIONS

TOPICS = ("numeric", "table", "condition", "comparison", "multi_hop")
METHODS = ("A", "B", "C")
STATES = ("candidate", "auto_validated", "held", "rejected", "released")
# 표 위치가 원본 격자를 확인한 것인지, 검증되지 않은 원본 격자 참고 파일의 것인지,
# 마크다운 논리 행으로 복원한 것인지 구분한다. 세 종류는 서로 섞지 않는다.
GRIDS = ("logical_restored", "original_verified", "original_reference")
# 이미지 OCR 이 검증한 범위: 보이는 글자 전체, 선언한 일부 영역, 검증 범위 없음(보류).
OCR_SCOPES = ("full_visible_text", "partial_region", "hold")

ITEM_FIELDS = (
    "candidate_id", "parent_candidate_id", "run_id", "method",
    "primary_topic", "secondary_tags", "question", "answer", "evidence",
    "bundle_id", "context", "structure",
    "generator_version", "validator_version", "prompt_version",
    "state", "state_history",
)
EVIDENCE_FIELDS = (
    "doc_sha", "chunk_id", "element_id", "record_id", "location",
    "page", "requirement_ids", "image_sha", "ocr_scope",
)
LOCATION_FIELDS = {"char": ("kind", "start", "end"), "table": ("kind", "grid", "row", "cell")}
SHA256 = re.compile(r"[0-9a-f]{64}")


class SchemaError(ValueError):
    pass


def validate_item(item):
    """항목이 스키마를 어기면 SchemaError 를 낸다."""
    _require_fields(item, ITEM_FIELDS, "item")
    for name in ("candidate_id", "run_id", "question", "answer", "bundle_id", "context",
                 "generator_version", "prompt_version"):
        _require_text(item[name], name)
    if not isinstance(item["structure"], dict):
        raise SchemaError("structure 는 객체여야 합니다")
    for name in ("parent_candidate_id", "validator_version"):
        if item[name] is not None:
            _require_text(item[name], name)
    _require_choice(item["method"], METHODS, "method")
    _require_choice(item["state"], STATES, "state")
    _validate_topics(item["primary_topic"], item["secondary_tags"])
    _validate_history(item["state"], item["state_history"])
    if item["state"] != "candidate" and item["validator_version"] is None:
        raise SchemaError("candidate 를 지난 항목은 validator_version 이 있어야 합니다")
    if not isinstance(item["evidence"], list) or not item["evidence"]:
        raise SchemaError("evidence 는 비어 있지 않은 리스트여야 합니다")
    for ref in item["evidence"]:
        _validate_evidence(ref)


def _validate_history(state, history):
    """state 만 고쳐 검증·사람 검토를 건너뛰지 못하게,
    state_history 가 candidate 에서 허용된 전이만 거쳐 지금 state 에 닿는지 본다.
    """
    if not isinstance(history, list):
        raise SchemaError("state_history 는 리스트여야 합니다")
    current = "candidate"
    for step in history:
        _require_fields(step, ("from", "to", "reason", "at"), "state_history")
        if step["from"] != current or step["to"] not in TRANSITIONS[current]:
            raise SchemaError(f"state_history 에 허용되지 않는 전이가 있습니다: {step['from']} -> {step['to']}")
        _require_text(step["reason"], "state_history.reason")
        _require_utc_time(step["at"], "state_history.at")
        current = step["to"]
    if current != state:
        raise SchemaError(f"state_history 는 {current} 에서 끝나는데 state 는 {state} 입니다")


def _validate_topics(primary, secondary):
    _require_choice(primary, TOPICS, "primary_topic")
    if not isinstance(secondary, list):
        raise SchemaError("secondary_tags 는 리스트여야 합니다")
    for tag in secondary:
        _require_choice(tag, TOPICS, "secondary_tags")
    if primary in secondary:
        raise SchemaError("primary_topic 이 secondary_tags 에 다시 들어 있습니다")


def _validate_evidence(ref):
    _require_fields(ref, EVIDENCE_FIELDS, "evidence")
    _require_sha(ref["doc_sha"], "doc_sha")
    for name in ("chunk_id", "element_id", "record_id"):
        _require_text(ref[name], name)
    # v11 청크는 대부분 page 가 없으므로 None 을 허용한다.
    if ref["page"] is not None and not (_is_index(ref["page"]) and ref["page"] >= 1):
        raise SchemaError("page 는 None 이거나 1 이상의 정수여야 합니다")
    if not isinstance(ref["requirement_ids"], list):
        raise SchemaError("requirement_ids 는 리스트여야 합니다")
    for requirement_id in ref["requirement_ids"]:
        _require_text(requirement_id, "requirement_ids")
    _validate_image(ref["image_sha"], ref["ocr_scope"])
    _validate_location(ref["location"])


def _validate_image(image_sha, ocr_scope):
    if image_sha is None:
        if ocr_scope is not None:
            raise SchemaError("image_sha 없이 ocr_scope 만 있습니다")
        return
    _require_sha(image_sha, "image_sha")
    _require_choice(ocr_scope, OCR_SCOPES, "ocr_scope")


def _validate_location(location):
    if not isinstance(location, dict) or location.get("kind") not in LOCATION_FIELDS:
        raise SchemaError(f"location 은 kind 가 {tuple(LOCATION_FIELDS)} 중 하나인 객체여야 합니다")
    _require_fields(location, LOCATION_FIELDS[location["kind"]], "location")
    if location["kind"] == "char":
        start, end = location["start"], location["end"]
        if not (_is_index(start) and _is_index(end) and start < end):
            raise SchemaError("location(char) 은 0 <= start < end 인 정수여야 합니다")
    else:
        _require_choice(location["grid"], GRIDS, "location.grid")
        cell = location["cell"]
        if not _is_index(location["row"]) or not (cell is None or _is_index(cell)):
            raise SchemaError("location(table) 은 0 이상의 row 와 None 또는 0 이상의 cell 이 필요합니다")


def _require_fields(record, fields, label):
    """필드가 정확히 fields 여야 한다.

    선언되지 않은 필드를 허용하면 출시 때 run 기록과의 비교를 빠져나가고, JSON 으로 못 쓰는 값이 저장까지 간다.
    """
    if not isinstance(record, dict):
        raise SchemaError(f"{label} 는 객체여야 합니다")
    missing = [name for name in fields if name not in record]
    if missing:
        raise SchemaError(f"{label} 에 필드가 없습니다: {missing}")
    extra = sorted(name for name in record if name not in fields)
    if extra:
        raise SchemaError(f"{label} 에 선언되지 않은 필드가 있습니다: {extra}")


def _require_utc_time(value, name):
    """transition 이 남기는 ISO-8601 UTC 시각인지 본다."""
    try:
        moment = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        raise SchemaError(f"{name} 는 ISO-8601 시각 문자열이어야 합니다: {value!r}") from None
    if moment.utcoffset() != timedelta(0):
        raise SchemaError(f"{name} 는 UTC 시각이어야 합니다: {value!r}")


def _require_text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise SchemaError(f"{name} 는 비어 있지 않은 문자열이어야 합니다")


def _require_sha(value, name):
    if not isinstance(value, str) or not SHA256.fullmatch(value):
        raise SchemaError(f"{name} 는 소문자 SHA-256 16진수여야 합니다")


def _require_choice(value, choices, name):
    if value not in choices:
        raise SchemaError(f"{name} 는 {choices} 중 하나여야 합니다: {value!r}")


def _is_index(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0
