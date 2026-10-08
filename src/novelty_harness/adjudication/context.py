"""One immutable research, input and Phase 6 assessment world-state."""

from datetime import date
from typing import Literal, Self

from pydantic import ConfigDict, model_validator

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.idea import CanonicalIdeaRepresentation, SufficiencyAssessment
from novelty_harness.domain.ids import AssessmentId
from novelty_harness.domain.mcu import MCUGraph
from novelty_harness.mcu.overrides import MCUVersion
from novelty_harness.research.adaptive.pipeline import ResearchResult
from novelty_harness.research.coverage import CoverageCell, CoveragePolicy
from novelty_harness.research.models import ResearchPlan
from novelty_harness.runtime.budgets.controller import DIMENSIONS, BudgetUsage
from novelty_harness.runtime.config.models import BudgetLimits
from novelty_harness.runtime.tracing.hashing import canonical_hash


class Phase7InputManifest(ContractModel):
    """Validated policy inputs; this document contains no verified prior-art facts."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["phase7-input-manifest-v1"] = "phase7-input-manifest-v1"
    assessment_id: AssessmentId
    phase6_snapshot_id: str
    as_of: date
    cir: CanonicalIdeaRepresentation
    sufficiency: SufficiencyAssessment
    mcu_graph: MCUGraph | MCUVersion
    research_plan: ResearchPlan | None = None
    research_result: ResearchResult | None = None
    coverage_policy: CoveragePolicy | None = None
    budget_limits: BudgetLimits | None = None
    budget_usage: BudgetUsage | None = None
    coverage_cells: tuple[CoverageCell, ...] = ()
    query_history: tuple[str, ...] = ()
    providers_attempted: tuple[str, ...] = ()
    access_failures: tuple[str, ...] = ()
    remaining_gaps: tuple[str, ...] = ()
    stop_reason: str | None = None
    unknown_upstream_artifacts: tuple[str, ...] = ()
    upstream_artifact_ids: dict[str, str] = {}
    upstream_artifact_digests: dict[str, str] = {}
    method_versions: dict[str, str] = {}

    @model_validator(mode="after")
    def validate_input_links(self) -> Self:
        if self.cir.idea_id != self.sufficiency.idea_id:
            raise ValueError("CIR and sufficiency refer to different ideas")
        if self.cir.context.temporal_cutoff != self.as_of:
            raise ValueError("CIR cutoff differs from assessment cutoff")
        if isinstance(self.mcu_graph, MCUGraph) and self.mcu_graph.idea_id != self.cir.idea_id:
            raise ValueError("MCU graph refers to a different idea")
        if self.research_plan is not None and (
            self.research_plan.assessment_id != self.assessment_id
            or self.research_plan.as_of != self.as_of
        ):
            raise ValueError("Research plan differs from assessment or cutoff")
        if self.research_result is not None:
            if self.budget_usage is None or any(
                getattr(self.budget_usage, dimension)
                < getattr(self.research_result.budget_usage, dimension)
                for dimension in DIMENSIONS
            ):
                raise ValueError("Cumulative budget usage is below the latest research pass")
        return self

    def content_digest(self) -> str:
        # JSON revalidation normalizes Pydantic numeric subtypes (for example
        # a default FiniteFloat represented as 0 before deserialization).
        return canonical_hash(type(self).model_validate(self.model_dump(mode="json")))


class SealedAssessmentContext(ContractModel):
    """Repository-issued identity over one exact view and input manifest."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["phase7-sealed-assessment-context-v1"] = (
        "phase7-sealed-assessment-context-v1"
    )
    context_id: str
    assessment_id: AssessmentId
    snapshot_id: str
    phase6_view_digest: str
    manifest_id: str
    manifest_digest: str
    manifest: Phase7InputManifest
    parent_context_id: str | None = None

    @model_validator(mode="after")
    def matching_manifest(self) -> Self:
        if (
            self.assessment_id != self.manifest.assessment_id
            or self.snapshot_id != self.manifest.phase6_snapshot_id
            or self.manifest_digest != self.manifest.content_digest()
        ):
            raise ValueError("Context and input manifest identities differ")
        return self


def is_true_noop(before: SealedAssessmentContext, after: SealedAssessmentContext) -> bool:
    """Pure equality check; callers must first reload both from repository authority."""

    return (
        before.assessment_id == after.assessment_id
        and before.snapshot_id == after.snapshot_id
        and before.phase6_view_digest == after.phase6_view_digest
        and before.manifest_digest == after.manifest_digest
        and before.manifest == after.manifest
    )
