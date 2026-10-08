"""Provider-neutral Phase 7 persistence and authority protocol."""

from typing import Protocol

from novelty_harness.adjudication.context import Phase7InputManifest, SealedAssessmentContext
from novelty_harness.adjudication.frozen import FrozenAdjudication
from novelty_harness.adjudication.models import (
    Phase7Artifact,
    Phase7RunRecord,
    Phase7RunState,
    Phase7RunTransition,
    TargetRef,
)
from novelty_harness.adjudication.needs import ResearchContinuation, ResearchEscalationOutcome
from novelty_harness.adjudication.qualifications import DomainQualification, RobustnessQualification
from novelty_harness.domain.ids import AssessmentId
from novelty_harness.evidence.graph.assessment_view import Phase6AssessmentView


class Phase7AuthorityError(ValueError):
    """A Phase 7 artifact cannot be treated as authoritative."""


class Phase7AdjudicationRepository(Protocol):
    def freeze_phase7_adjudication(self, run_id: str, proposed: FrozenAdjudication) -> str: ...

    def load_frozen_adjudication(
        self, assessment_id: AssessmentId, *, adjudication_id: str
    ) -> FrozenAdjudication: ...

    def load_phase6_assessment(
        self, assessment_id: AssessmentId, *, snapshot_id: str
    ) -> Phase6AssessmentView: ...

    def seal_phase7_context(
        self,
        assessment_id: AssessmentId,
        *,
        snapshot_id: str,
        manifest: Phase7InputManifest,
        parent_context_id: str | None = None,
    ) -> SealedAssessmentContext: ...

    def load_phase7_context(
        self, assessment_id: AssessmentId, *, context_id: str
    ) -> SealedAssessmentContext: ...

    def load_phase7_superseded_contexts(
        self, assessment_id: AssessmentId, *, context_id: str
    ) -> tuple[str, ...]: ...

    def begin_phase7_run(
        self, context_id: str, *, attempt_token: str | None = None
    ) -> Phase7RunRecord: ...

    def load_phase7_run(self, run_id: str) -> Phase7RunRecord: ...

    def load_phase7_artifacts(self, run_id: str) -> tuple[Phase7Artifact, ...]: ...

    def record_phase7_artifact(self, run_id: str, artifact: Phase7Artifact) -> str: ...

    def transition_phase7_run(
        self,
        run_id: str,
        *,
        expected_state: Phase7RunState,
        next_state: Phase7RunState,
    ) -> Phase7RunTransition: ...

    def complete_phase7_research(
        self, run_id: str, outcome: ResearchEscalationOutcome
    ) -> ResearchContinuation: ...

    def load_phase7_qualifications(
        self, context_id: str, target: TargetRef
    ) -> tuple[RobustnessQualification, DomainQualification]: ...
