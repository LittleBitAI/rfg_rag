import pytest

from golden_pipeline.schema import EVIDENCE_FIELDS, SchemaError, validate_item


def test_fixture_item_is_valid(make_item):
    validate_item(make_item())


@pytest.mark.parametrize("primary_topic", ["", "numbers", None, "Numeric"])
def test_unknown_primary_topic_is_rejected(make_item, primary_topic):
    with pytest.raises(SchemaError, match="primary_topic"):
        validate_item(make_item(primary_topic=primary_topic))


def test_missing_primary_topic_is_rejected(make_item):
    item = make_item()
    del item["primary_topic"]
    with pytest.raises(SchemaError, match="primary_topic"):
        validate_item(item)


def test_primary_topic_repeated_in_secondary_tags_is_rejected(make_item):
    with pytest.raises(SchemaError, match="secondary_tags"):
        validate_item(make_item(secondary_tags=["table", "numeric"]))


@pytest.mark.parametrize("field", [
    "candidate_id", "parent_candidate_id", "run_id", "method",
    "generator_version", "validator_version", "prompt_version", "state", "state_history",
])
def test_missing_item_provenance_field_is_rejected(make_item, field):
    item = make_item()
    del item[field]
    with pytest.raises(SchemaError, match=field):
        validate_item(item)


@pytest.mark.parametrize("field", EVIDENCE_FIELDS)
def test_missing_evidence_provenance_field_is_rejected(make_item, field):
    item = make_item()
    del item["evidence"][1][field]
    with pytest.raises(SchemaError, match=field):
        validate_item(item)


def test_item_without_evidence_is_rejected(make_item):
    with pytest.raises(SchemaError, match="evidence"):
        validate_item(make_item(evidence=[]))


@pytest.mark.parametrize("location, valid", [
    ({"kind": "table", "grid": "original_verified", "row": 0, "cell": None}, True),
    ({"kind": "table", "grid": "markdown", "row": 0, "cell": 0}, False),
    ({"kind": "table", "row": 0, "cell": 0}, False),
    ({"kind": "char", "start": 5, "end": 5}, False),
    ({"kind": "page"}, False),
])
def test_location_is_char_span_or_table_cell_with_grid_kind(make_item, location, valid):
    item = make_item()
    item["evidence"][0]["location"] = location
    if valid:
        validate_item(item)
    else:
        with pytest.raises(SchemaError, match="location"):
            validate_item(item)


@pytest.mark.parametrize("image_sha, ocr_scope", [
    ("b" * 64, None),
    ("b" * 64, "easyocr"),
    (None, "human_verified"),
    ("not-a-sha", "unverified"),
])
def test_image_needs_sha_and_known_ocr_scope_together(make_item, image_sha, ocr_scope):
    item = make_item()
    item["evidence"][1].update(image_sha=image_sha, ocr_scope=ocr_scope)
    with pytest.raises(SchemaError):
        validate_item(item)
