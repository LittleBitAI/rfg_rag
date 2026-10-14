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
    "candidate_id", "parent_candidate_id", "run_id", "method", "bundle_id", "context", "structure",
    "generator_version", "validator_version", "prompt_version", "difficulty", "state", "state_history",
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


@pytest.mark.parametrize("field, value", [("bundle_id", ""), ("context", " "), ("structure", ["value"])])
def test_bundle_and_context_must_be_text_and_structure_an_object(make_item, field, value):
    with pytest.raises(SchemaError, match=field):
        validate_item(make_item(**{field: value}))


def test_item_without_evidence_is_rejected(make_item):
    with pytest.raises(SchemaError, match="evidence"):
        validate_item(make_item(evidence=[]))


@pytest.mark.parametrize("location, valid", [
    ({"kind": "table", "grid": "original_verified", "row": 0, "cell": None}, True),
    ({"kind": "table", "grid": "original_reference", "row": 0, "cell": 2}, True),
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
    (None, "full_visible_text"),
    ("not-a-sha", "partial_region"),
])
def test_image_needs_sha_and_known_ocr_scope_together(make_item, image_sha, ocr_scope):
    item = make_item()
    item["evidence"][1].update(image_sha=image_sha, ocr_scope=ocr_scope)
    with pytest.raises(SchemaError):
        validate_item(item)


def step(start, to, reason="이유"):
    return {"from": start, "to": to, "reason": reason, "at": "2026-10-14T00:00:00+00:00"}


@pytest.mark.parametrize("state, history", [
    ("released", []),
    ("released", [step("candidate", "released")]),
    ("auto_validated", [step("candidate", "held")]),
    ("released", [step("candidate", "rejected"), step("rejected", "released")]),
    ("released", [step("auto_validated", "released")]),
    ("rejected", [step("candidate", "rejected", reason="")]),
    ("held", [{"from": "candidate", "to": "held"}]),
])
def test_state_must_be_reached_by_permitted_transitions_with_reasons(make_item, state, history):
    # state 만 released 로 고치고 state_history 를 비워 두면 검증·사람 검토 없이 출시되던 결함,
    # 거절 이유 없는 거절 항목이 failure_memory 에 들어가던 결함을 막는다.
    with pytest.raises(SchemaError, match="state_history"):
        validate_item(make_item(state=state, state_history=history, validator_version="val-0.1", difficulty="easy"))


def test_item_past_candidate_needs_validator_version_and_difficulty(make_item):
    history = [step("candidate", "auto_validated"), step("auto_validated", "released")]
    validate_item(make_item(state="released", state_history=history, validator_version="val-0.1", difficulty="hard"))
    with pytest.raises(SchemaError, match="validator_version"):
        validate_item(make_item(state="released", state_history=history, validator_version=None))
    for difficulty in (None, "보통"):
        with pytest.raises(SchemaError, match="difficulty"):
            validate_item(make_item(
                state="released", state_history=history, validator_version="val-0.1", difficulty=difficulty,
            ))
    with pytest.raises(SchemaError, match="difficulty"):
        validate_item(make_item(difficulty="easy"))


@pytest.mark.parametrize("at", [None, object(), "어제", "2026-10-14T00:00:00", "2026-10-14T09:00:00+09:00"])
def test_transition_time_must_be_iso_utc(make_item, at):
    # at 이 None 이면 그대로 저장되고, JSON 으로 못 쓰는 값이면 run 폴더만 만든 채 TypeError 로 끝나
    # 같은 run_id 로 다시 돌릴 수 없던 결함을 막는다.
    history = [{**step("candidate", "held"), "at": at}]
    with pytest.raises(SchemaError, match="state_history.at"):
        validate_item(make_item(state="held", state_history=history, validator_version="val-0.1", difficulty="easy"))


@pytest.mark.parametrize("where", ["item", "evidence", "location", "state_history"])
def test_undeclared_field_is_rejected_at_every_level(make_item, where):
    # 선언되지 않은 필드는 출시 때 run 기록과의 비교를 빠져나가 golden.jsonl 에 그대로 들어가던 결함을 막는다.
    item = make_item(
        state="held", state_history=[step("candidate", "held")], validator_version="val-0.1", difficulty="easy",
    )
    target = {
        "item": item,
        "evidence": item["evidence"][0],
        "location": item["evidence"][0]["location"],
        "state_history": item["state_history"][0],
    }[where]
    target["replacement_answer"] = "바꿔 끼운 답"
    with pytest.raises(SchemaError, match="선언되지 않은 필드"):
        validate_item(item)
