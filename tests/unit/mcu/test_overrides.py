import pytest

from novelty_harness.domain.mcu import MCU
from novelty_harness.mcu.overrides import MCUOverrideOperation, apply_override, create_mcu_version
from tests.fixtures.phase1 import FIXED_TIME
from tests.fixtures.phase2 import candidate


def mcu(mcu_id="mcu_control"):
    return MCU.model_validate(candidate(mcu_id)["mcu"])


def initial():
    return create_mcu_version(
        mcus=(mcu(),),
        combinations=(),
        source_reconciliation_hash="reconciliation-hash",
        created_at=FIXED_TIME,
        created_by="engine",
    )


def operation(kind, payload, **updates):
    return MCUOverrideOperation(
        operation_id="override_1",
        kind=kind,
        payload=payload,
        reason="User corrects interpretation",
        actor="user",
        occurred_at=FIXED_TIME,
        **updates,
    )


@pytest.mark.parametrize(
    "kind",
    [
        "ADD_MCU",
        "EDIT_MCU",
        "REMOVE_MCU",
        "MERGE_MCUS",
        "SPLIT_MCU",
        "ADD_RELATIONSHIP",
        "REMOVE_RELATIONSHIP",
        "EDIT_COMBINATION",
    ],
)
def test_every_override_creates_new_auditable_version_and_keeps_parent(kind):
    parent = initial()
    if kind == "ADD_MCU":
        payload = {"mcu": mcu("mcu_extra").model_dump(mode="json")}
    elif kind == "EDIT_MCU":
        payload = {
            "mcu": mcu()
            .model_copy(update={"label": "User corrected label"})
            .model_dump(mode="json")
        }
    elif kind == "REMOVE_MCU":
        payload = {"mcu_id": "mcu_control"}
    elif kind == "SPLIT_MCU":
        payload = {
            "mcu_id": "mcu_control",
            "mcus": [
                mcu("mcu_left").model_dump(mode="json"),
                mcu("mcu_right").model_dump(mode="json"),
            ],
            "combination_updates": [],
        }
    elif kind == "MERGE_MCUS":
        parent = create_mcu_version(
            mcus=(mcu(), mcu("mcu_extra")),
            combinations=(),
            source_reconciliation_hash="reconciliation-hash",
            created_at=FIXED_TIME,
            created_by="engine",
        )
        payload = {
            "mcu_ids": ["mcu_control", "mcu_extra"],
            "mcu": mcu("mcu_merged").model_dump(mode="json"),
            "combination_updates": [],
        }
    elif kind == "ADD_RELATIONSHIP":
        payload = {
            "mcu_id": "mcu_control",
            "relationship": {"subject": "F2", "relation": "FEEDBACK", "object": "F1"},
        }
    elif kind == "REMOVE_RELATIONSHIP":
        payload = {
            "mcu_id": "mcu_control",
            "relationship": {"subject": "F1", "relation": "CONTROLS", "object": "F2"},
        }
    else:
        parent = create_mcu_version(
            mcus=(mcu(), mcu("mcu_extra")),
            combinations=(),
            source_reconciliation_hash="reconciliation-hash",
            created_at=FIXED_TIME,
            created_by="engine",
        )
        payload = {
            "combination": {
                "combination_id": "C1",
                "label": "User combination",
                "statement": "Linked contribution",
                "member_ids": ["mcu_control", "mcu_extra"],
                "provenance": {"kind": "implemented", "component": "user", "detail": "Override"},
            }
        }
    before = parent.model_dump_json()
    changed = apply_override(parent, operation(kind, payload))
    assert parent.model_dump_json() == before
    assert changed.parent_version_id == parent.version_id
    assert changed.version_id != parent.version_id
    assert changed.overrides[-1].actor == "user"
    assert changed.overrides[-1].reason == "User corrects interpretation"
    assert changed.overrides[-1].payload == payload
    if kind in ("MERGE_MCUS", "SPLIT_MCU"):
        assert changed.overrides[-1].previous_mcus
    # Rollback is selection of the immutable parent, not history mutation.
    assert initial().version_id == initial().version_id


@pytest.mark.parametrize(
    "kind,payload",
    [
        ("ADD_MCU", {"mcu": candidate()["mcu"]}),
        ("REMOVE_MCU", {"mcu_id": "mcu_missing"}),
        (
            "ADD_RELATIONSHIP",
            {
                "mcu_id": "mcu_control",
                "relationship": {"subject": "F1", "relation": "CONTROLS", "object": "missing"},
            },
        ),
        ("EDIT_MCU", {"mcu": candidate("mcu_missing")["mcu"]}),
        ("REMOVE_MCU", {"mcu_id": "mcu_control", "extra": "reject"}),
    ],
)
def test_invalid_edits_reject_without_changing_parent(kind, payload):
    parent = initial()
    before = parent.model_dump_json()
    with pytest.raises(ValueError):
        apply_override(parent, operation(kind, payload))
    assert parent.model_dump_json() == before


def test_operation_and_audit_payload_cannot_mutate_frozen_history():
    op = operation("ADD_MCU", {"mcu": mcu("mcu_extra").model_dump(mode="json")})
    changed = apply_override(initial(), op)
    before = changed.model_dump_json()
    op.payload["mcu"] = "changed afterwards"
    payload = changed.overrides[0].payload
    payload["mcu"] = "changed via accessor"
    assert changed.model_dump_json() == before
    with pytest.raises(ValueError):
        changed.mcus[0].label = "mutated"


def test_duplicate_operation_id_and_naive_timestamp_rejected():
    op = operation("EDIT_MCU", {"mcu": mcu().model_dump(mode="json")})
    changed = apply_override(initial(), op)
    with pytest.raises(ValueError):
        apply_override(changed, op)
    with pytest.raises(ValueError):
        MCUOverrideOperation.model_validate(
            {**op.model_dump(), "occurred_at": FIXED_TIME.replace(tzinfo=None)}
        )
