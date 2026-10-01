"""Injection boundary for deterministic Phase 6 fixture adjudication."""

from collections.abc import Sequence
from datetime import date
from typing import Protocol, runtime_checkable

from novelty_harness.domain.adjudication import FrozenAdjudication
from novelty_harness.domain.idea import CanonicalIdeaRepresentation, SufficiencyAssessment
from novelty_harness.domain.ids import AssessmentId
from novelty_harness.domain.mcu import MCU
from novelty_harness.evidence.graph.assessment_view import Phase6AssessmentView


@runtime_checkable
class Phase6FixtureAdjudicator(Protocol):
    """Fixture-only adjudicator port; this is not a Phase 7 implementation."""

    async def adjudicate_phase6(
        self,
        *,
        assessment_id: AssessmentId,
        as_of: date,
        idea: CanonicalIdeaRepresentation,
        sufficiency: SufficiencyAssessment,
        mcus: Sequence[MCU],
        view: Phase6AssessmentView,
    ) -> FrozenAdjudication: ...
