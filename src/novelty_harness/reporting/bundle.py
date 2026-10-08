"""Temporary typed projection of an exact validated upstream closure."""

from datetime import date
from typing import Annotated, Literal, cast

from pydantic import BaseModel, Field, JsonValue, model_validator

from novelty_harness.adjudication.context import Phase7InputManifest
from novelty_harness.adjudication.counterfactual import CounterfactualLocalization
from novelty_harness.adjudication.frozen import (
    FrozenAdjudication,
    LanguagePermissionClass,
    OverallFinding,
    TargetFinding,
)
from novelty_harness.adjudication.gates import (
    GateAFinding,
    GateBFinding,
    GateCFinding,
    GateDFinding,
)
from novelty_harness.adjudication.judge import (
    CounterbalanceComparison,
    CounterbalanceRun,
    JudgeResolution,
)
from novelty_harness.adjudication.models import Phase7Artifact, TargetRef
from novelty_harness.adjudication.needs import (
    InputClarificationNeed,
    ResearchGapDisposition,
    ResearchGapRequest,
)
from novelty_harness.adjudication.qualifications import DomainQualification, RobustnessQualification
from novelty_harness.adjudication.roles import DefenseCase, ProsecutionCase, RebuttalCase
from novelty_harness.domain.enums import VerdictState
from novelty_harness.domain.idea import CanonicalIdeaRepresentation
from novelty_harness.domain.mcu import MCUGraph
from novelty_harness.evidence.graph.assessment_view import (
    AuthorizedGraphRelation,
    CitedPassageView,
    CommittedComparisonView,
    Phase6AssessmentView,
)
from novelty_harness.evidence.mapping.dimensions import MCUComparisonProfile
from novelty_harness.evidence.normalization.models import SourceRecord, SourceVersionRecord
from novelty_harness.mcu.overrides import MCUVersion
from novelty_harness.reporting.models import (
    AuthorityKind,
    AuthorityRef,
    Digest,
    NonBlank,
    ReportContract,
    ReportDependency,
    ReportScope,
    validate_authority_refs,
)
from novelty_harness.reporting.obligations import CoverageObligation
from novelty_harness.reporting.value import ValueProjection
from novelty_harness.runtime.tracing.hashing import canonical_hash

GateProjection = Annotated[
    GateAFinding | GateBFinding | GateCFinding | GateDFinding, Field(discriminator="contract_kind")
]
QualificationProjection = Annotated[
    RobustnessQualification | DomainQualification, Field(discriminator="contract_kind")
]
RoleProjection = Annotated[ProsecutionCase | DefenseCase, Field(discriminator="contract_kind")]


class LanguageEnvelope(ReportContract):
    contract_kind: Literal["phase8-language-envelope-v1"] = "phase8-language-envelope-v1"
    scope: ReportScope
    target: TargetRef
    claim_scope: NonBlank
    verdict: VerdictState
    permitted_classes: tuple[LanguagePermissionClass, ...]
    required_limitations: tuple[str, ...]
    authority_refs: tuple[AuthorityRef, ...]


class SourceMetadataObservation(ReportContract):
    contract_kind: Literal["phase8-source-metadata-observation-v1"] = (
        "phase8-source-metadata-observation-v1"
    )
    scope: ReportScope
    source: SourceRecord
    version: SourceVersionRecord | None
    source_ref: AuthorityRef
    version_ref: AuthorityRef | None
    comparison_refs: tuple[AuthorityRef, ...]
    missing_fields: tuple[str, ...] = ()
    conflicting_observation_refs: tuple[AuthorityRef, ...] = ()


class AdjudicationReportingClosure(ReportContract):
    contract_kind: Literal["phase8-adjudication-reporting-closure-v1"] = (
        "phase8-adjudication-reporting-closure-v1"
    )
    scope: ReportScope
    phase6_view: Phase6AssessmentView
    role_cases: tuple[RoleProjection, ...]
    rebuttals: tuple[RebuttalCase, ...]
    judge_runs: tuple[CounterbalanceRun, ...]
    judge_comparisons: tuple[CounterbalanceComparison, ...]
    judge_resolutions: tuple[JudgeResolution, ...]
    research_dispositions: tuple[ResearchGapDisposition, ...]
    upstream_artifacts: tuple[Phase7Artifact, ...]
    superseded_context_refs: tuple[AuthorityRef, ...] = ()


class ReportInputBundle(ReportContract):
    contract_kind: Literal["phase8-report-input-bundle-v1"] = "phase8-report-input-bundle-v1"
    scope: ReportScope
    as_of: date
    bundle_version: Literal["p8-bundle-v1"] = "p8-bundle-v1"
    bundle_digest: Digest
    frozen_adjudication: FrozenAdjudication
    input_manifest_ref: AuthorityRef
    cir: CanonicalIdeaRepresentation
    graph_or_version: MCUGraph | MCUVersion
    target_profiles: tuple[MCUComparisonProfile, ...]
    target_findings: tuple[TargetFinding, ...]
    overall_finding: OverallFinding
    gate_findings: tuple[GateProjection, ...]
    qualifications: tuple[QualificationProjection, ...]
    eligible_comparisons: tuple[CommittedComparisonView, ...]
    authorized_relations: tuple[AuthorizedGraphRelation, ...]
    cited_passages: tuple[CitedPassageView, ...]
    source_metadata: tuple[SourceMetadataObservation, ...]
    research_state: Phase7InputManifest
    input_needs: tuple[InputClarificationNeed, ...]
    research_gaps: tuple[ResearchGapRequest, ...]
    judge_resolutions_and_limitations: AdjudicationReportingClosure
    counterfactuals: tuple[CounterfactualLocalization, ...]
    value_projection: tuple[ValueProjection, ...] = ()
    language_envelopes: tuple[LanguageEnvelope, ...] = ()
    coverage_obligations: tuple[CoverageObligation, ...] = ()
    dependency_manifest: tuple[ReportDependency, ...]
    audit_refs: tuple[str, ...]

    @model_validator(mode="after")
    def exact_projections(self) -> "ReportInputBundle":
        frozen = self.frozen_adjudication
        if (
            frozen.assessment_id,
            frozen.adjudication_id,
            frozen.assessment_context_id,
            frozen.phase6_snapshot_id,
        ) != (
            self.scope.assessment_id,
            self.scope.adjudication_id,
            self.scope.assessment_context_id,
            self.scope.phase6_snapshot_id,
        ):
            raise ValueError("bundle frozen scope differs")
        if (
            self.target_findings != frozen.target_findings
            or self.overall_finding != frozen.overall_finding
        ):
            raise ValueError("bundle findings differ from frozen adjudication")
        if {(p.target_kind, p.target_id) for p in self.target_profiles} != {
            (t.kind, t.id) for t in frozen.expected_targets
        }:
            raise ValueError("bundle target universe differs")
        if (
            self.cir != self.research_state.cir
            or self.graph_or_version != self.research_state.mcu_graph
            or self.as_of != frozen.as_of
        ):
            raise ValueError("bundle input projection differs")
        refs = tuple(
            d.authority_ref for d in self.dependency_manifest if d.authority_ref is not None
        )
        validate_authority_refs(refs, self.scope)
        if len(refs) != len(self.dependency_manifest):
            raise ValueError("bundle dependencies must be upstream")
        return self


def report_bundle_digest(bundle: ReportInputBundle) -> str:
    return canonical_hash(bundle.model_dump(mode="json", exclude={"bundle_digest"}))


def project_source_metadata(
    view: Phase6AssessmentView, scope: ReportScope
) -> tuple[SourceMetadataObservation, ...]:
    """Retain each committed observation, including conflicts; never pick the latest."""
    profiles = {p.target_id: p for p in view.targets}
    observations: list[SourceMetadataObservation] = []
    for comparison in view.committed_comparisons:
        chain = comparison.comparison.comparison.chain
        profile = profiles[chain.edge.mcu_id]
        target = TargetRef(kind=profile.target_kind, id=profile.target_id)
        cls_id = comparison.comparison.classification.classification_id
        comparison_ref = AuthorityRef(
            kind=AuthorityKind.COMPARISON,
            native_id=cls_id,
            digest=canonical_hash(comparison),
            scope=scope,
            target=target,
        )
        path = ("comparisons", comparison.commit_id, cls_id)
        source_ref = AuthorityRef(
            kind=AuthorityKind.SOURCE,
            native_id=chain.source.source_id,
            digest=canonical_hash(chain.source),
            scope=scope,
            target=target,
            path=(*path, "source"),
        )
        version_ref = (
            AuthorityRef(
                kind=AuthorityKind.SOURCE_VERSION,
                native_id=chain.version.version_id,
                digest=canonical_hash(chain.version),
                scope=scope,
                target=target,
                path=(*path, "version"),
            )
            if chain.version
            else None
        )
        missing = tuple(
            field
            for field, value in (
                ("canonical_url", chain.source.canonical_url),
                ("authors_or_owners", chain.source.authors_or_owners),
                ("publication_date", chain.source.dates.publication_date),
            )
            if not value
        )
        observations.append(
            SourceMetadataObservation(
                scope=scope,
                source=chain.source,
                version=chain.version,
                source_ref=source_ref,
                version_ref=version_ref,
                comparison_refs=(comparison_ref,),
                missing_fields=missing,
            )
        )
    return tuple(
        o.model_copy(
            update={
                "conflicting_observation_refs": tuple(
                    other.source_ref
                    for other in observations
                    if other.source.source_id == o.source.source_id
                    and other.source_ref.digest != o.source_ref.digest
                )
            }
        )
        for o in observations
    )


def native_ref(
    bundle: ReportInputBundle,
    kind: AuthorityKind,
    *,
    native_id: str | None = None,
    target_id: str | None = None,
) -> AuthorityRef:
    """Select one exact admitted native record, rather than a generic ID join."""
    matches = tuple(
        d.authority_ref
        for d in bundle.dependency_manifest
        if d.authority_ref is not None
        and d.authority_ref.kind == kind
        and (native_id is None or d.authority_ref.native_id == native_id)
        and (
            target_id is None
            or (d.authority_ref.target is not None and d.authority_ref.target.id == target_id)
        )
        and (
            d.authority_ref.path == ()
            or (kind == AuthorityKind.TARGET_FINDING and len(d.authority_ref.path) == 2)
            or (
                kind == AuthorityKind.OVERALL_FINDING
                and d.authority_ref.path == ("overall_finding",)
            )
        )
    )
    if len(matches) != 1:
        raise ValueError("report native reference is absent or ambiguous")
    return matches[0]


def field_ref(parent: AuthorityRef, value: object, *path: str | int) -> AuthorityRef:
    """An exact recorded field has its own digest and retains its parent's scope."""
    return parent.model_copy(
        update={
            "path": (*parent.path, *path),
            "digest": canonical_hash(cast(JsonValue | BaseModel, value)),
        }
    )


def derive_language_envelopes(bundle: ReportInputBundle) -> tuple[LanguageEnvelope, ...]:
    """Copy target permission; the overall class union grants no target permission."""
    from novelty_harness.reporting.uncertainty import project_uncertainty

    items = project_uncertainty(bundle)
    envelopes: list[LanguageEnvelope] = []
    for finding in bundle.target_findings:
        ref = native_ref(bundle, AuthorityKind.TARGET_FINDING, target_id=finding.target_id)
        relevant = tuple(
            i
            for i in items
            if not i.historical and (i.target is None or i.target.id == finding.target_id)
        )
        refs = (ref, *(r for i in relevant for r in i.authority_refs))
        envelopes.append(
            LanguageEnvelope(
                scope=bundle.scope,
                target=TargetRef(kind=finding.target_kind, id=finding.target_id),
                claim_scope=finding.claim_scope,
                verdict=finding.verdict,
                permitted_classes=finding.language_permission,
                required_limitations=tuple(
                    dict.fromkeys((*finding.limiting_factors, *(i.reason for i in relevant)))
                ),
                authority_refs=tuple(dict.fromkeys(refs)),
            )
        )
    return tuple(envelopes)


def basis_json(value: object) -> str:
    """Canonical display of known typed upstream fields, not an evidence inference."""
    from novelty_harness.runtime.tracing.hashing import canonical_json

    return canonical_json(cast(JsonValue | BaseModel, value))
