"""Immutable, typed records for completed Phase 6 assessment snapshots."""

from datetime import date
from typing import Literal, Self, cast

from pydantic import ConfigDict, Field, JsonValue, model_validator

from novelty_harness.domain.base import ContractModel, UTCDateTime
from novelty_harness.domain.ids import (
    AssessmentId,
    ClassificationId,
    EvidenceEdgeId,
    MCUId,
    SourceId,
    SourceVersionId,
)
from novelty_harness.evidence.mapping.dimensions import MCUComparisonProfile
from novelty_harness.evidence.precedent.gates import MultiSourceAssessment
from novelty_harness.evidence.precedent.models import PatentScreeningResult
from novelty_harness.evidence.verification.models import ContextExpansion
from novelty_harness.runtime.tracing.hashing import canonical_hash


class Phase6CoverageExclusion(ContractModel):
    """A source or source version omitted by a documented local bound."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["phase6-coverage-exclusion-v1"] = "phase6-coverage-exclusion-v1"

    source_id: SourceId
    source_version_id: SourceVersionId | None = None
    reason: Literal["SOURCE_BOUND", "VERSION_BOUND", "UNVERSIONED", "MISSING_VERSION_RECORD"]


class Phase6CoverageLedger(ContractModel):
    """Bounded local selection facts; it makes no claim about global coverage."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["phase6-coverage-ledger-v1"] = "phase6-coverage-ledger-v1"

    selected_source_ids: tuple[SourceId, ...] = ()
    excluded_sources: tuple[Phase6CoverageExclusion, ...] = ()
    selected_version_ids: tuple[SourceVersionId, ...] = ()
    excluded_versions: tuple[Phase6CoverageExclusion, ...] = ()
    limitations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def selections_are_unique(self) -> Self:
        if len(set(self.selected_source_ids)) != len(self.selected_source_ids):
            raise ValueError("Selected source IDs must be unique")
        if len(set(self.selected_version_ids)) != len(self.selected_version_ids):
            raise ValueError("Selected version IDs must be unique")
        return self


class Phase6AssessmentSnapshotRecord(ContractModel):
    """Frozen identity and referenced record set for one completed run."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["phase6-assessment-snapshot-v1"] = "phase6-assessment-snapshot-v1"

    snapshot_id: str
    assessment_id: AssessmentId
    as_of: date
    method_version: str
    max_sources_per_mcu: int = Field(ge=0)
    max_versions_per_source: int = Field(ge=0)
    max_expansions: int = Field(ge=0)
    window_chars: int = Field(ge=0)
    target_record_ids: tuple[str, ...]
    candidate_record_ids: tuple[str, ...]
    derived_record_ids: tuple[str, ...]
    lineage_cluster_ids: tuple[str, ...]
    commit_ids: tuple[str, ...]
    coverage: Phase6CoverageLedger
    audit_refs: tuple[str, ...]
    completed_at: UTCDateTime

    @model_validator(mode="after")
    def reference_ids_are_unique(self) -> Self:
        groups = (
            self.target_record_ids,
            self.candidate_record_ids,
            self.derived_record_ids,
            self.lineage_cluster_ids,
            self.commit_ids,
            self.audit_refs,
        )
        if any(len(set(values)) != len(values) for values in groups):
            raise ValueError("Snapshot reference IDs must be unique within each collection")
        return self


class Phase6TargetLedgerRecord(ContractModel):
    """One full MCU or combination comparison profile in a snapshot."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["phase6-target-ledger-v1"] = "phase6-target-ledger-v1"

    snapshot_id: str
    assessment_id: AssessmentId
    profile: MCUComparisonProfile


class Phase6CandidateLedgerRecord(ContractModel):
    """One selected, excluded, failed, or committed candidate outcome."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["phase6-candidate-ledger-v1"] = "phase6-candidate-ledger-v1"

    snapshot_id: str
    assessment_id: AssessmentId
    target_id: MCUId
    source_id: SourceId
    source_version_id: SourceVersionId | None = None
    source_content_hash: str | None = None
    version_content_hash: str | None = None
    evidence_families: tuple[str, ...] = ()
    decision: Literal[
        "ASSESSED",
        "EXCLUDED_SOURCE_BOUND",
        "EXCLUDED_VERSION_BOUND",
        "FAILED_MAPPING",
        "FAILED_PASSAGE_SELECTION",
        "FAILED_VERIFICATION",
        "UNASSESSABLE",
        "AUTHORITY_REJECTED",
    ]
    reason: str | None = None
    failure_stage: str | None = None
    projection_intent: Literal["GRAPH_BACKED", "SEMANTIC_ONLY"] | None = None
    commit_id: str | None = None
    verified_edge_id: EvidenceEdgeId | None = None
    classification_id: ClassificationId | None = None
    expansions: tuple[ContextExpansion, ...] = ()
    limitations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def outcome_shape_is_consistent(self) -> Self:
        if self.decision == "ASSESSED":
            if self.projection_intent is None:
                raise ValueError("Assessed candidates require projection intent")
            if (
                self.commit_id is None
                or self.verified_edge_id is None
                or self.classification_id is None
            ):
                raise ValueError("Assessed candidates require committed comparison identities")
        elif (
            self.commit_id is not None
            or self.verified_edge_id is not None
            or self.classification_id is not None
        ):
            raise ValueError("Unassessed candidates cannot claim committed comparison identities")
        if self.decision != "ASSESSED" and self.projection_intent is not None:
            raise ValueError("Only assessed candidates have a projection intent")
        return self


class Phase6DerivedLedgerRecord(ContractModel):
    """Input-bound multi-source or patent screening output."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["phase6-derived-ledger-v1"] = "phase6-derived-ledger-v1"

    snapshot_id: str
    assessment_id: AssessmentId
    target_id: MCUId
    kind: Literal["MULTI_SOURCE", "PATENT"]
    input_commit_ids: tuple[str, ...]
    input_edge_ids: tuple[EvidenceEdgeId, ...]
    input_classification_ids: tuple[ClassificationId, ...]
    lineage_root_ids: tuple[SourceId, ...]
    as_of: date
    method_version: str
    result: MultiSourceAssessment | PatentScreeningResult

    @model_validator(mode="after")
    def result_matches_kind(self) -> Self:
        if self.kind == "MULTI_SOURCE" and not isinstance(self.result, MultiSourceAssessment):
            raise ValueError("MULTI_SOURCE records require a multi-source result")
        if self.kind == "PATENT" and not isinstance(self.result, PatentScreeningResult):
            raise ValueError("PATENT records require a patent screening result")
        if len(self.input_commit_ids) != len(self.input_edge_ids) or len(
            self.input_edge_ids
        ) != len(self.input_classification_ids):
            raise ValueError("Derived input identities must be paired")
        return self


def phase6_target_record_id(record: Phase6TargetLedgerRecord) -> str:
    """Return the stable row identity for a target profile within a snapshot."""

    payload = record.model_dump(mode="json", exclude={"snapshot_id"})
    return "p6target_" + canonical_hash(
        cast(
            JsonValue,
            {
                "snapshot_id": record.snapshot_id,
                "kind": "TARGET",
                "identity": record.profile.target_id,
                "payload": payload,
            },
        )
    )


def phase6_candidate_record_id(record: Phase6CandidateLedgerRecord) -> str:
    """Return the stable row identity for a candidate outcome within a snapshot."""

    payload = record.model_dump(mode="json", exclude={"snapshot_id"})
    return "p6candidate_" + canonical_hash(
        cast(
            JsonValue,
            {
                "snapshot_id": record.snapshot_id,
                "kind": "CANDIDATE",
                "identity": (record.target_id, record.source_id, record.source_version_id),
                "payload": payload,
            },
        )
    )


def phase6_derived_record_id(record: Phase6DerivedLedgerRecord) -> str:
    """Return the stable row identity for a derived result within a snapshot."""

    payload = record.model_dump(mode="json", exclude={"snapshot_id"})
    return "p6derived_" + canonical_hash(
        cast(
            JsonValue,
            {
                "snapshot_id": record.snapshot_id,
                "kind": "DERIVED",
                "identity": (record.target_id, record.kind),
                "payload": payload,
            },
        )
    )


def phase6_assessment_snapshot_id(
    snapshot: Phase6AssessmentSnapshotRecord,
    *,
    targets: tuple[Phase6TargetLedgerRecord, ...],
    candidates: tuple[Phase6CandidateLedgerRecord, ...],
    derived: tuple[Phase6DerivedLedgerRecord, ...],
) -> str:
    """Compute deterministic snapshot identity, excluding clocks and row IDs."""

    target_facts = sorted(
        (target.model_dump(mode="json", exclude={"snapshot_id"}) for target in targets),
        key=lambda value: str(value["profile"]["target_id"]),
    )
    candidate_facts = sorted(
        (record.model_dump(mode="json", exclude={"snapshot_id"}) for record in candidates),
        key=lambda value: canonical_hash(cast(JsonValue, value)),
    )
    derived_facts = sorted(
        (record.model_dump(mode="json", exclude={"snapshot_id"}) for record in derived),
        key=lambda value: canonical_hash(cast(JsonValue, value)),
    )
    return "p6snap_" + canonical_hash(
        cast(
            JsonValue,
            {
                "assessment_id": snapshot.assessment_id,
                "as_of": snapshot.as_of,
                "method_version": snapshot.method_version,
                "limits": {
                    "max_sources_per_mcu": snapshot.max_sources_per_mcu,
                    "max_versions_per_source": snapshot.max_versions_per_source,
                    "max_expansions": snapshot.max_expansions,
                    "window_chars": snapshot.window_chars,
                },
                "targets": target_facts,
                "candidates": candidate_facts,
                "derived": derived_facts,
                "lineage_cluster_ids": sorted(snapshot.lineage_cluster_ids),
                "commit_ids": sorted(snapshot.commit_ids),
                "coverage": snapshot.coverage,
            },
        )
    )
