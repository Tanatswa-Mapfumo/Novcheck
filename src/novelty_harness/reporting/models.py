"""Immutable report identities and presentation options; shapes are not authority."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, StringConstraints, model_validator

from novelty_harness.adjudication.models import TargetRef
from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.ids import AssessmentId
from novelty_harness.runtime.tracing.hashing import canonical_hash

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Digest = Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
QuestionId = Literal[1, 2, 3, 4, 5, 6, 7, 8, 9]


class ReportContract(ContractModel):
    model_config = ConfigDict(frozen=True)


class ReportProposalError(ValueError):
    """Untrusted reporting proposal failed a contract check."""


class ReportScope(ReportContract):
    contract_kind: Literal["phase8-report-scope-v1"] = "phase8-report-scope-v1"
    assessment_id: AssessmentId
    adjudication_id: NonBlank
    assessment_context_id: NonBlank
    phase6_snapshot_id: NonBlank


class ReportScoped(ReportContract):
    scope: ReportScope
    compilation_id: NonBlank


class AuthorityKind(StrEnum):
    FROZEN = "FROZEN"
    CONTEXT = "CONTEXT"
    INPUT_MANIFEST = "INPUT_MANIFEST"
    CIR = "CIR"
    GRAPH = "GRAPH"
    TARGET = "TARGET"
    TARGET_FINDING = "TARGET_FINDING"
    OVERALL_FINDING = "OVERALL_FINDING"
    GATE = "GATE"
    QUALIFICATION = "QUALIFICATION"
    COUNTERFACTUAL = "COUNTERFACTUAL"
    ROLE = "ROLE"
    REBUTTAL = "REBUTTAL"
    JUDGE_RUN = "JUDGE_RUN"
    JUDGE_COMPARISON = "JUDGE_COMPARISON"
    JUDGE_RESOLUTION = "JUDGE_RESOLUTION"
    INPUT_NEED = "INPUT_NEED"
    RESEARCH_GAP = "RESEARCH_GAP"
    SUPERSESSION = "SUPERSESSION"
    RESEARCH_STATE = "RESEARCH_STATE"
    COVERAGE = "COVERAGE"
    CANDIDATE = "CANDIDATE"
    COMPARISON = "COMPARISON"
    COMMIT = "COMMIT"
    GRAPH_RELATION = "GRAPH_RELATION"
    PASSAGE = "PASSAGE"
    SOURCE = "SOURCE"
    SOURCE_VERSION = "SOURCE_VERSION"
    LINEAGE = "LINEAGE"
    VALUE_BASIS = "VALUE_BASIS"


class AuthorityRef(ReportContract):
    contract_kind: Literal["phase8-authority-ref-v1"] = "phase8-authority-ref-v1"
    kind: AuthorityKind
    native_id: NonBlank
    digest: Digest
    scope: ReportScope
    target: TargetRef | None = None
    path: tuple[NonBlank | Annotated[int, Field(ge=0, strict=True)], ...] = ()

    @model_validator(mode="after")
    def target_identity(self) -> "AuthorityRef":
        if self.kind == AuthorityKind.TARGET and (
            self.target is None or self.target.id != self.native_id
        ):
            raise ValueError("target reference must retain its native target identity")
        return self


def authority_dependency_id(ref: AuthorityRef) -> str:
    """Field identity distinguishes multiple admitted observations of one record."""
    return "p8dep_" + canonical_hash(
        ref.model_dump(mode="json", include={"kind", "native_id", "path", "scope"})
    )


def validate_authority_refs(refs: tuple[AuthorityRef, ...], scope: ReportScope) -> None:
    identities: set[str] = set()
    for proposed in refs:
        ref = AuthorityRef.model_validate(proposed.model_dump(mode="json"))
        if ref.scope != scope:
            raise ValueError("authority reference scope differs")
        identity = authority_dependency_id(ref)
        if identity in identities:
            raise ValueError("duplicate native authority reference")
        identities.add(identity)


class ReportDependency(ReportContract):
    contract_kind: Literal["phase8-report-dependency-v1"] = "phase8-report-dependency-v1"
    dependency_kind: Literal["UPSTREAM", "REPORT_ARTIFACT"]
    dependency_id: NonBlank
    expected_digest: Digest
    authority_ref: AuthorityRef | None = None
    report_artifact_id: NonBlank | None = None

    @model_validator(mode="after")
    def exactly_one_arm(self) -> "ReportDependency":
        if self.dependency_kind == "UPSTREAM":
            if self.authority_ref is None or self.report_artifact_id is not None:
                raise ValueError("upstream dependency requires only its authority reference")
            if self.dependency_id != authority_dependency_id(self.authority_ref):
                raise ValueError("upstream dependency identity differs from native field")
            if self.expected_digest != self.authority_ref.digest:
                raise ValueError("upstream dependency digest differs")
        elif self.report_artifact_id is None or self.authority_ref is not None:
            raise ValueError("local dependency requires only its report artifact reference")
        elif self.dependency_id != self.report_artifact_id:
            raise ValueError("local dependency identity differs from artifact")
        return self


class ReportLens(StrEnum):
    RESEARCH = "RESEARCH"
    PRODUCT = "PRODUCT"
    ENGINEERING = "ENGINEERING"
    SOFTWARE = "SOFTWARE"
    PROCESS = "PROCESS"
    PATENT_SCREENING = "PATENT_SCREENING"


class ReportSemanticRole(StrEnum):
    PLANNER = "PLANNER"
    WRITER = "WRITER"
    EXTRACTOR = "EXTRACTOR"
    VERIFIER = "VERIFIER"
    COMPOSITION = "COMPOSITION"
    REPAIR = "REPAIR"


class ReportGenerationLimits(ReportContract):
    contract_kind: Literal["phase8-report-generation-limits-v1"] = (
        "phase8-report-generation-limits-v1"
    )
    max_calls: int = Field(default=96, ge=0)
    max_tokens: int = Field(default=100000, ge=0)
    max_cost_usd: float | None = Field(default=None, ge=0)
    max_context_chars: int = Field(default=80000, ge=0)
    max_question_chars: int = Field(default=24000, ge=0)
    max_blocks_per_question: int = Field(default=32, ge=0)
    max_subsections_per_question: int = Field(default=8, ge=0)
    max_hierarchy_depth: int = Field(default=2, ge=0)
    max_repairs_total: int = Field(default=9, ge=0)


class ReportOptions(ReportContract):
    contract_kind: Literal["phase8-report-options-v1"] = "phase8-report-options-v1"
    lens: ReportLens = ReportLens.RESEARCH
    detail: Literal["SHORT", "STANDARD", "DETAILED"] = "STANDARD"
    compact_summary: bool = False
    limits: ReportGenerationLimits = Field(default_factory=ReportGenerationLimits)
    render_policy_version: NonBlank = "p8-render-v1"


class ReportClaimCategory(StrEnum):
    INPUT_DESCRIPTION = "INPUT_DESCRIPTION"
    SOURCE_FACT = "SOURCE_FACT"
    EQUIVALENCE_DESCRIPTION = "EQUIVALENCE_DESCRIPTION"
    NOVELTY_INTERPRETATION = "NOVELTY_INTERPRETATION"
    NEGATIVE_CLAIM = "NEGATIVE_CLAIM"
    POTENTIAL_NOVELTY_CLAIM = "POTENTIAL_NOVELTY_CLAIM"
    VALUE_CLAIM = "VALUE_CLAIM"
    COVERAGE_CLAIM = "COVERAGE_CLAIM"
    UNCERTAINTY_CLAIM = "UNCERTAINTY_CLAIM"
    VALIDATION_RECOMMENDATION = "VALIDATION_RECOMMENDATION"
