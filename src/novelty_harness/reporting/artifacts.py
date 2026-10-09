"""Attempt identities and a closed typed vocabulary for immutable report artifacts."""

from enum import StrEnum
from typing import Annotated, Literal, cast

from pydantic import Field, JsonValue, model_validator

from novelty_harness.domain.base import UTCDateTime
from novelty_harness.reporting.claims import ClaimExtractionProposal
from novelty_harness.reporting.drafts import SectionDraft, SectionDraftFragment
from novelty_harness.reporting.execution import (
    ReportCompilationConfiguration,
    ReportExecutionRecord,
    ReportMethodRegistration,
    ReportRoleConfiguration,
    configuration_key_content,
)
from novelty_harness.reporting.fallback import FallbackRecord
from novelty_harness.reporting.firewall import FirewallResult
from novelty_harness.reporting.models import (
    Digest,
    NonBlank,
    QuestionId,
    ReportOptions,
    ReportScope,
    ReportScoped,
)
from novelty_harness.reporting.plan import ReportPlan, ReportPlanProposal
from novelty_harness.reporting.repair import RepairCluster
from novelty_harness.reporting.serialization import canonical_json_digest
from novelty_harness.reporting.verification import (
    ClaimVerificationBatch,
    CompositionCheck,
    CompositionContext,
)
from novelty_harness.runtime.tracing.hashing import canonical_hash


class ReportAttemptState(StrEnum):
    STARTED = "STARTED"
    PLANNED = "PLANNED"
    DRAFTED = "DRAFTED"
    VERIFIED = "VERIFIED"
    ACCEPTED = "ACCEPTED"
    FAILED = "FAILED"


class ReportCompilationRecord(ReportScoped):
    contract_kind: Literal["phase8-report-compilation-record-v1"] = (
        "phase8-report-compilation-record-v1"
    )
    compilation_key: NonBlank
    attempt_token: NonBlank
    options: ReportOptions
    configuration: ReportCompilationConfiguration
    bundle_digest: Digest
    started_at: UTCDateTime

    @model_validator(mode="after")
    def bound_configuration(self) -> "ReportCompilationRecord":
        if any(
            (role.scope, role.compilation_id) != (self.scope, self.compilation_id)
            for role in self.configuration.roles
        ):
            raise ValueError("attempt configuration scope differs")
        if self.compilation_key != compilation_key(
            self.scope, self.bundle_digest, self.options, self.configuration
        ):
            raise ValueError("attempt compilation key differs")
        if self.compilation_id != compilation_id(self.compilation_key, self.attempt_token):
            raise ValueError("attempt compilation identity differs")
        return self


class ReportStatusEvent(ReportScoped):
    contract_kind: Literal["phase8-report-status-event-v1"] = "phase8-report-status-event-v1"
    event_id: NonBlank
    predecessor_id: NonBlank | None = None
    expected_state: ReportAttemptState | None = None
    next_state: ReportAttemptState
    reason: NonBlank
    observed_at: UTCDateTime

    @model_validator(mode="after")
    def legal_step(self) -> "ReportStatusEvent":
        states = (
            ReportAttemptState.STARTED,
            ReportAttemptState.PLANNED,
            ReportAttemptState.DRAFTED,
            ReportAttemptState.VERIFIED,
            ReportAttemptState.ACCEPTED,
        )
        if self.expected_state is None:
            if self.next_state != ReportAttemptState.STARTED or self.predecessor_id is not None:
                raise ValueError("initial status must start without a predecessor")
        elif self.expected_state in {ReportAttemptState.ACCEPTED, ReportAttemptState.FAILED}:
            raise ValueError("terminal report attempt cannot advance")
        elif self.predecessor_id is None:
            raise ValueError("status transition requires predecessor")
        elif self.next_state != ReportAttemptState.FAILED and (
            self.next_state != states[states.index(self.expected_state) + 1]
        ):
            raise ValueError("report status cannot skip a stage")
        return self


class ReportArtifactKind(StrEnum):
    METHOD = "METHOD"
    CONFIGURATION = "CONFIGURATION"
    EXECUTION = "EXECUTION"
    STATUS = "STATUS"
    PLAN_PROPOSAL = "PLAN_PROPOSAL"
    PLAN = "PLAN"
    DRAFT = "DRAFT"
    REPAIR = "REPAIR"
    EXTRACTION = "EXTRACTION"
    FIREWALL = "FIREWALL"
    VERIFICATION = "VERIFICATION"
    COMPOSITION = "COMPOSITION"
    FALLBACK = "FALLBACK"


ReportArtifactDocument = Annotated[
    ReportMethodRegistration
    | ReportRoleConfiguration
    | ReportExecutionRecord
    | ReportStatusEvent
    | ReportPlanProposal
    | ReportPlan
    | SectionDraft
    | SectionDraftFragment
    | RepairCluster
    | ClaimExtractionProposal
    | FirewallResult
    | ClaimVerificationBatch
    | CompositionCheck
    | CompositionContext
    | FallbackRecord,
    Field(discriminator="contract_kind"),
]
_DOCUMENT_KINDS = {
    ReportMethodRegistration: ReportArtifactKind.METHOD,
    ReportRoleConfiguration: ReportArtifactKind.CONFIGURATION,
    ReportExecutionRecord: ReportArtifactKind.EXECUTION,
    ReportStatusEvent: ReportArtifactKind.STATUS,
    ReportPlanProposal: ReportArtifactKind.PLAN_PROPOSAL,
    ReportPlan: ReportArtifactKind.PLAN,
    SectionDraft: ReportArtifactKind.DRAFT,
    SectionDraftFragment: ReportArtifactKind.REPAIR,
    RepairCluster: ReportArtifactKind.REPAIR,
    ClaimExtractionProposal: ReportArtifactKind.EXTRACTION,
    FirewallResult: ReportArtifactKind.FIREWALL,
    ClaimVerificationBatch: ReportArtifactKind.VERIFICATION,
    CompositionCheck: ReportArtifactKind.COMPOSITION,
    CompositionContext: ReportArtifactKind.COMPOSITION,
    FallbackRecord: ReportArtifactKind.FALLBACK,
}


class ReportArtifact(ReportScoped):
    contract_kind: Literal["phase8-report-artifact-v1"] = "phase8-report-artifact-v1"
    artifact_id: NonBlank
    kind: ReportArtifactKind
    question_id: QuestionId | None = None
    cluster_origin_id: NonBlank | None = None
    method_version: NonBlank
    execution_ref: NonBlank | None = None
    document: ReportArtifactDocument

    @model_validator(mode="after")
    def document_binding(self) -> "ReportArtifact":
        if self.kind != _DOCUMENT_KINDS[type(self.document)]:
            raise ValueError("artifact kind differs from typed document")
        if (self.document.scope, self.document.compilation_id) != (self.scope, self.compilation_id):
            raise ValueError("artifact document scope differs")
        if isinstance(
            self.document,
            (ReportMethodRegistration, ReportRoleConfiguration, ReportExecutionRecord),
        ):
            if self.method_version != self.document.method_version:
                raise ValueError("artifact method differs from document")
        question_id = (
            self.document.question_id
            if isinstance(
                self.document,
                (
                    SectionDraft,
                    SectionDraftFragment,
                    RepairCluster,
                    ClaimExtractionProposal,
                    FirewallResult,
                    ClaimVerificationBatch,
                    FallbackRecord,
                ),
            )
            else None
        )
        origin_id = (
            self.document.cluster_origin_id
            if isinstance(self.document, SectionDraftFragment)
            else self.document.origin_id
            if isinstance(self.document, RepairCluster)
            else None
        )
        if (self.question_id, self.cluster_origin_id) != (question_id, origin_id):
            raise ValueError("artifact section or repair ownership differs from document")
        if self.execution_ref is not None and self.kind not in {
            ReportArtifactKind.PLAN_PROPOSAL,
            ReportArtifactKind.DRAFT,
            ReportArtifactKind.REPAIR,
            ReportArtifactKind.EXTRACTION,
            ReportArtifactKind.VERIFICATION,
            ReportArtifactKind.COMPOSITION,
        }:
            raise ValueError("registration, execution or status cannot claim proposal execution")
        return self


def compilation_key(
    scope: ReportScope,
    bundle_digest: str,
    options: ReportOptions,
    configuration: ReportCompilationConfiguration,
) -> str:
    payload: dict[str, JsonValue] = {
        "scope": scope.model_dump(mode="json"),
        "bundle_digest": bundle_digest,
        "options": options.model_dump(mode="json"),
        "configuration": configuration_key_content(configuration),
    }
    return "p8key_" + canonical_hash(payload)


def compilation_id(key: str, attempt_token: str) -> str:
    if not key.strip() or not attempt_token.strip():
        raise ValueError("compilation key and attempt token must be nonblank")
    return "p8run_" + canonical_hash({"key": key, "attempt_token": attempt_token})


def report_artifact_id(artifact: ReportArtifact) -> str:
    artifact = ReportArtifact.model_validate(artifact.model_dump(mode="json"))
    return report_artifact_snapshot_id(artifact)


def report_artifact_snapshot_id(artifact: ReportArtifact) -> str:
    """Hash a private reparsed snapshot; callers must validate before entering.

    Public identity calculation and the IR boundary each reparse untrusted
    callers. Revalidating the same isolated snapshot again only creates another
    full document and normalized string collection.
    """
    payload = artifact.model_dump(mode="json", exclude={"artifact_id"})
    document = cast(dict[str, JsonValue], payload["document"])
    if isinstance(artifact.document, ReportExecutionRecord):
        document.pop("observations")
    elif isinstance(artifact.document, ReportStatusEvent):
        document.pop("event_id")
        document.pop("observed_at")
    payload["document"] = document
    return "p8artifact_" + canonical_json_digest(payload)


def report_status_event_id(event: ReportStatusEvent) -> str:
    event = ReportStatusEvent.model_validate(event.model_dump(mode="json"))
    return "p8event_" + canonical_hash(
        event.model_dump(mode="json", exclude={"event_id", "observed_at"})
    )


def make_report_artifact(
    compilation: ReportCompilationRecord,
    kind: ReportArtifactKind,
    document: ReportArtifactDocument,
    *,
    method_version: str,
    execution_ref: str | None = None,
) -> ReportArtifact:
    compilation = ReportCompilationRecord.model_validate(compilation.model_dump(mode="json"))
    artifact = ReportArtifact(
        scope=compilation.scope,
        compilation_id=compilation.compilation_id,
        artifact_id="pending",
        kind=kind,
        method_version=method_version,
        execution_ref=execution_ref,
        document=document,
        question_id=document.question_id
        if isinstance(
            document,
            (
                SectionDraft,
                SectionDraftFragment,
                RepairCluster,
                ClaimExtractionProposal,
                FirewallResult,
                ClaimVerificationBatch,
                FallbackRecord,
            ),
        )
        else None,
        cluster_origin_id=(
            document.cluster_origin_id
            if isinstance(document, SectionDraftFragment)
            else document.origin_id
            if isinstance(document, RepairCluster)
            else None
        ),
    )
    return artifact.model_copy(update={"artifact_id": report_artifact_id(artifact)})


def report_artifact_semantic_content(artifact: ReportArtifact) -> dict[str, JsonValue]:
    """Exact replay ignores only observations and preserves the stored original."""
    content = artifact.model_dump(mode="json")
    # Closed native documents use the already dumped projection. Preserve the
    # original standalone serializer for unsupported caller subclasses; this
    # helper is not a validation or authority boundary.
    document = (
        cast(dict[str, JsonValue], content["document"])
        if type(artifact.document) in _DOCUMENT_KINDS
        else artifact.document.model_dump(mode="json")
    )
    if isinstance(artifact.document, ReportExecutionRecord):
        document.pop("observations")
    elif isinstance(artifact.document, ReportStatusEvent):
        document.pop("observed_at")
    content["document"] = document
    return content


# Backward-compatible internal alias for the already validated snapshot helper.
_report_artifact_id_from_snapshot = report_artifact_snapshot_id
