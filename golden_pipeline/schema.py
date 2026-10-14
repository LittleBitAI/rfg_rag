"""골든 항목 스키마. 새 패키지를 requirements.txt 에 넣지 않으려고 표준 라이브러리로만 검증한다."""
import re

TOPICS = ("numeric", "table", "condition", "comparison", "multi_hop")
METHODS = ("A", "B", "C")
STATES = ("candidate", "auto_validated", "held", "rejected", "released")
# 표 위치가 원본 격자를 확인한 것인지, 마크다운 논리 행으로 복원한 것인지 구분한다.
GRIDS = ("logical_restored", "original_verified")
OCR_SCOPES = ("human_verified", "unverified")

ITEM_FIELDS = (
    "candidate_id", "parent_candidate_id", "run_id", "method",
    "primary_topic", "secondary_tags", "question", "answer", "evidence",
    "generator_version", "validator_version", "prompt_version",
    "state", "state_history",
)
EVIDENCE_FIELDS = (
    "doc_sha", "chunk_id", "element_id", "record_id", "location",
    "page", "requirement_ids", "image_sha", "ocr_scope",
)
SHA256 = re.compile(r"[0-9a-f]{64}")


class SchemaError(ValueError):
    pass


def validate_item(item):
    """항목이 스키마를 어기면 SchemaError 를 낸다."""
    _require_fields(item, ITEM_FIELDS, "item")
    for name in ("candidate_id", "run_id", "question", "answer", "generator_version", "prompt_version"):
        _require_text(item[name], name)
    for name in ("parent_candidate_id", "validator_version"):
        if item[name] is not None:
            _require_text(item[name], name)
    _require_choice(item["method"], METHODS, "method")
    _require_choice(item["state"], STATES, "state")
    _validate_topics(item["primary_topic"], item["secondary_tags"])
    if not isinstance(item["state_history"], list):
        raise SchemaError("state_history 는 리스트여야 합니다")
    if not isinstance(item["evidence"], list) or not item["evidence"]:
        raise SchemaError("evidence 는 비어 있지 않은 리스트여야 합니다")
    for ref in item["evidence"]:
        _validate_evidence(ref)


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
    if not isinstance(location, dict):
        raise SchemaError("location 은 객체여야 합니다")
    kind = location.get("kind")
    if kind == "char":
        start, end = location.get("start"), location.get("end")
        if not (_is_index(start) and _is_index(end) and start < end):
            raise SchemaError("location(char) 은 0 <= start < end 인 정수여야 합니다")
    elif kind == "table":
        _require_choice(location.get("grid"), GRIDS, "location.grid")
        cell = location.get("cell")
        if not _is_index(location.get("row")) or not (cell is None or _is_index(cell)):
            raise SchemaError("location(table) 은 0 이상의 row 와 None 또는 0 이상의 cell 이 필요합니다")
    else:
        raise SchemaError(f"알 수 없는 location.kind: {kind!r}")


def _require_fields(record, fields, label):
    if not isinstance(record, dict):
        raise SchemaError(f"{label} 는 객체여야 합니다")
    missing = [name for name in fields if name not in record]
    if missing:
        raise SchemaError(f"{label} 에 필드가 없습니다: {missing}")


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
