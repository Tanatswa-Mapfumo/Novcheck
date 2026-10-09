"""Exact JSON projection hashing; allocation controls confer no native authority."""

import gc
import tracemalloc

import pytest

from novelty_harness.runtime.tracing.hashing import canonical_hash


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {"z": [None, True, False, 0, -7, 1.25, -0.0], "a": 'é雪😀\\n"\\'},
        {"nested": [{"b": "value", "a": []}], "empty": {}},
        {"large_integer": 2**100, "small_float": 1e-100, "large_float": 1e100},
    ],
)
def test_json_digest_matches_existing_canonical_identity(payload):
    from novelty_harness.reporting.serialization import canonical_json_digest

    assert canonical_json_digest(payload) == canonical_hash(payload)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_json_digest_rejects_nonfinite_values(value):
    from novelty_harness.reporting.serialization import canonical_json_digest

    with pytest.raises(ValueError):
        canonical_json_digest({"value": value})


def test_json_digest_does_not_retain_complete_wire_and_utf8_copy(record_property):
    from novelty_harness.reporting.serialization import canonical_json_digest

    # Repeated propositions are required on the v1 wire. The digest need not
    # retain a second complete rendering of those propositions in memory.
    payload = {"propositions": ["évidence " + "x" * 65536] * 128}
    peaks = []
    results = []
    for digest in (canonical_hash, canonical_json_digest):
        gc.collect()
        tracemalloc.start()
        try:
            results.append(digest(payload))
            peaks.append(tracemalloc.get_traced_memory()[1])
        finally:
            tracemalloc.stop()
    record_property("original_peak_bytes", peaks[0])
    record_property("streamed_peak_bytes", peaks[1])
    assert results[0] == results[1]
    assert peaks[1] < peaks[0] * 0.25, peaks


def _status_artifacts():
    from novelty_harness.reporting.artifacts import (
        ReportArtifactKind,
        ReportStatusEvent,
        make_report_artifact,
        report_status_event_id,
    )
    from tests.fixtures.phase8 import OBSERVED
    from tests.unit.reporting.test_contracts import _compilation

    compilation = _compilation()
    artifacts = []
    for index in range(3):
        event = ReportStatusEvent(
            scope=compilation.scope,
            compilation_id=compilation.compilation_id,
            event_id="pending",
            next_state="STARTED",
            reason=f"synthetic {index}: " + "x" * 1048576,
            observed_at=OBSERVED,
        )
        event = event.model_copy(update={"event_id": report_status_event_id(event)})
        artifacts.append(
            make_report_artifact(
                compilation, ReportArtifactKind.STATUS, event, method_version="p8-bundle-v1"
            )
        )
    return compilation, tuple(artifacts)


def test_ir_artifact_boundary_preserves_exact_snapshot_and_identity():
    from novelty_harness.reporting.artifacts import ReportArtifact, report_artifact_id
    from novelty_harness.reporting.ir import _validated_ir_artifacts

    compilation, artifacts = _status_artifacts()
    expected = tuple(
        ReportArtifact.model_validate_json(a.model_dump_json(), strict=True) for a in artifacts
    )
    actual = _validated_ir_artifacts(artifacts, compilation)
    assert actual == expected
    assert [a.model_dump_json() for a in actual] == [a.model_dump_json() for a in expected]
    assert all(a.artifact_id == report_artifact_id(a) for a in actual)
    assert all(a is not raw for a, raw in zip(actual, artifacts, strict=True))


@pytest.mark.parametrize("change", ["identity", "scope", "kind", "duplicate", "document_scope"])
def test_ir_artifact_boundary_rejects_mutated_caller_models(change):
    from novelty_harness.reporting.ir import _validated_ir_artifacts
    from novelty_harness.reporting.models import ReportProposalError

    compilation, artifacts = _status_artifacts()
    artifact = artifacts[0]
    if change == "identity":
        artifact = artifact.model_copy(update={"artifact_id": "p8artifact_wrong"})
    elif change == "scope":
        artifact = artifact.model_copy(
            update={"scope": artifact.scope.model_copy(update={"assessment_id": "asm_foreign"})}
        )
    elif change == "kind":
        artifact = artifact.model_copy(update={"kind": "FALLBACK"})
    elif change == "document_scope":
        artifact = artifact.model_copy(
            update={
                "document": artifact.document.model_copy(update={"compilation_id": "p8run_foreign"})
            }
        )
    proposed = (artifact, artifact) if change == "duplicate" else (artifact,)
    with pytest.raises((ValueError, ReportProposalError)):
        _validated_ir_artifacts(proposed, compilation)


def test_validated_string_sharing_bounds_retained_copies(record_property):
    from typing import Annotated

    from pydantic import BaseModel, ConfigDict, StringConstraints

    from novelty_harness.reporting.serialization import _share_validated_strings

    class Payload(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)
        text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
        notes: dict[str, list[str]]

    originals = [Payload(text="x" * 1048576, notes={"labels": ["original"]}) for _ in range(3)]
    gc.collect()
    tracemalloc.start()
    try:
        snapshots = [
            _share_validated_strings(
                Payload.model_validate_json(value.model_dump_json(), strict=True), value
            )
            for value in originals
        ]
        retained, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    record_property("string_snapshot_retained_bytes", retained)
    record_property("string_snapshot_peak_bytes", peak)
    assert retained < sum(len(value.text) for value in originals) * 0.25, retained
    assert snapshots == originals
    originals[0].notes["labels"].append("caller mutation")
    assert snapshots[0].notes == {"labels": ["original"]}


def test_validated_string_sharing_never_changes_normalization_or_private_containers():
    from typing import Annotated

    from pydantic import BaseModel, ConfigDict, StringConstraints

    from novelty_harness.reporting.serialization import _share_validated_strings

    class Payload(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)
        text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
        notes: dict[str, list[str]]

    original = Payload(text="normalized", notes={"labels": ["source"]}).model_copy(
        update={"text": "  normalized  "}
    )
    validated = Payload.model_validate_json(original.model_dump_json(), strict=True)
    shared = _share_validated_strings(validated, original)
    assert shared.model_dump_json() == validated.model_dump_json()
    assert shared.text == "normalized"
    original.notes["labels"][0] = "changed"
    assert shared.notes == {"labels": ["source"]}


def test_validated_string_sharing_does_not_consult_caller_string_subclasses():
    from pydantic import BaseModel, ConfigDict

    from novelty_harness.reporting.serialization import _share_validated_strings

    class Payload(BaseModel):
        model_config = ConfigDict(extra="forbid", frozen=True)
        text: str
        notes: dict[str, str]

    class CallerString(str):
        def __eq__(self, other):
            raise AssertionError("caller equality cannot authorize or alter a snapshot")

        __hash__ = str.__hash__

    original = Payload(text="plain", notes={"label": "plain"}).model_copy(
        update={"text": CallerString("plain"), "notes": {CallerString("label"): "plain"}}
    )
    validated = Payload.model_validate_json(original.model_dump_json(), strict=True)
    shared = _share_validated_strings(validated, original)
    assert shared.model_dump_json() == validated.model_dump_json()
    assert type(shared.text) is str
    original.notes.clear()
    assert shared.notes == {"label": "plain"}


def test_validated_string_pool_has_operation_local_lifetime():
    from novelty_harness.reporting.serialization import _share_validated_strings

    original = "independent" * 1000
    first = original.encode().decode()
    second = original.encode().decode()
    assert first is not second
    first_shared = _share_validated_strings(first, first)
    second_shared = _share_validated_strings(second, second)
    assert first_shared is first
    assert second_shared is second


def test_artifact_semantic_projection_preserves_standalone_subclass_wire():
    from novelty_harness.reporting.artifacts import (
        ReportStatusEvent,
        report_artifact_semantic_content,
    )

    class ExtraStatus(ReportStatusEvent):
        extra_prose: str = "standalone caller projection retains this field"

    _, artifacts = _status_artifacts()
    extra = ExtraStatus.model_validate(artifacts[0].document.model_dump())
    proposed = artifacts[0].model_copy(update={"document": extra})
    expected = proposed.model_dump(mode="json")
    expected["document"] = extra.model_dump(mode="json", exclude={"observed_at"})
    assert report_artifact_semantic_content(proposed) == expected
