from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from novelty_harness.application.understanding import UnderstandingUpdate
from novelty_harness.domain.assessment import AssessmentRequest
from novelty_harness.domain.base import ContractModel, utc_now
from novelty_harness.domain.idea import (
    ArtifactProvenance,
    CanonicalIdeaRepresentation,
    SufficiencyAssessment,
)
from novelty_harness.domain.ids import AssessmentId
from novelty_harness.domain.mcu import MCU, MCUGraph
from novelty_harness.intake.models import NormalizationResult
from novelty_harness.intake.normalization import FaithfulIdeaNormalizer
from novelty_harness.intake.sufficiency import StructuralSufficiencyAnalyzer, lower_resolution
from novelty_harness.mcu.alignment import align_decompositions
from novelty_harness.mcu.decomposition import (
    IndependenceFocusedDecomposer,
    RelationshipFocusedDecomposer,
)
from novelty_harness.mcu.models import MCUDecomposition
from novelty_harness.mcu.overrides import MCUVersion, create_mcu_version
from novelty_harness.mcu.reconciliation import ReconciliationResult, reconcile_decompositions
from novelty_harness.runtime.artifacts.writer import RunArtifactWriter
from novelty_harness.runtime.semantic.structured import SemanticRunner
from novelty_harness.runtime.tracing.hashing import canonical_hash


@dataclass(frozen=True, slots=True)
class UnderstandingResult:
    cir: CanonicalIdeaRepresentation
    sufficiency: SufficiencyAssessment
    decomposition_a: MCUDecomposition
    decomposition_b: MCUDecomposition
    reconciliation: ReconciliationResult
    active_mcu_version: MCUVersion


def cap_understanding_sufficiency(
    assessment: SufficiencyAssessment,
    reconciliation: ReconciliationResult,
) -> SufficiencyAssessment:
    state = lower_resolution(assessment.state, reconciliation.assessment_ceiling)
    if state == assessment.state:
        return assessment
    return SufficiencyAssessment.model_validate(
        {
            **assessment.model_dump(),
            "state": state,
            "consequences": (
                *assessment.consequences,
                "MCU_DECOMPOSITION_INSTABILITY: " + ", ".join(reconciliation.affected_mcu_ids),
            ),
            "missing_information": (
                *assessment.missing_information,
                *reconciliation.unresolved_disagreements,
            ),
        }
    )


class UnderstandingComponents:
    """One request-scoped understanding session behind the four existing async ports."""

    def __init__(self, runner: SemanticRunner, *, clock: Callable[[], datetime] = utc_now) -> None:
        self.runner = runner
        self.clock = clock
        self.normalization: NormalizationResult | None = None
        self.sufficiency: SufficiencyAssessment | None = None
        self.decomposition_a: MCUDecomposition | None = None
        self.decomposition_b: MCUDecomposition | None = None
        self.reconciliation: ReconciliationResult | None = None
        self.result: UnderstandingResult | None = None
        self._pending: list[tuple[str, ContractModel]] = []
        self._audit_cursor = len(runner.audits)
        self._final_published = False

    def _require_idea(self, idea: CanonicalIdeaRepresentation) -> None:
        if self.normalization is None or canonical_hash(idea) != canonical_hash(
            self.normalization.cir
        ):
            raise ValueError("understanding component belongs to another CIR/request")

    async def normalize(self, request: AssessmentRequest) -> CanonicalIdeaRepresentation:
        if self.normalization is not None:
            raise ValueError("create a new understanding session for each request")
        self.normalization = await FaithfulIdeaNormalizer(self.runner).normalize_result(request)
        self._pending.append(("normalization.json", self.normalization))
        return self.normalization.cir

    async def analyze(self, idea: CanonicalIdeaRepresentation) -> SufficiencyAssessment:
        self._require_idea(idea)
        if self.sufficiency is not None:
            raise ValueError("sufficiency already analyzed")
        analyzer = StructuralSufficiencyAnalyzer(self.runner)
        reasoning = await analyzer.analyze_reasoning(idea)
        from novelty_harness.intake.sufficiency import apply_sufficiency_ceiling

        self.sufficiency = apply_sufficiency_ceiling(reasoning, idea)
        self._pending.extend(
            (
                ("sufficiency_reasoning.json", reasoning),
                ("sufficiency_initial.json", self.sufficiency),
            )
        )
        return self.sufficiency

    async def decompose(self, idea: CanonicalIdeaRepresentation) -> tuple[MCU, ...]:
        self._require_idea(idea)
        if self.sufficiency is None or self.decomposition_a is not None:
            raise ValueError("decomposition requires initial sufficiency and a fresh session")
        # Each strategy receives only a defensive CIR copy, never the other result.
        self.decomposition_a = await IndependenceFocusedDecomposer(self.runner).decompose_result(
            idea.model_copy(deep=True)
        )
        self._pending.append(("mcu_candidates_A.json", self.decomposition_a))
        self.decomposition_b = await RelationshipFocusedDecomposer(self.runner).decompose_result(
            idea.model_copy(deep=True)
        )
        self._pending.append(("mcu_candidates_B.json", self.decomposition_b))
        return tuple(c.mcu for c in self.decomposition_a.candidates)

    async def reconcile(
        self, idea: CanonicalIdeaRepresentation, candidates: Sequence[MCU]
    ) -> MCUGraph:
        self._require_idea(idea)
        left, right = self.decomposition_a, self.decomposition_b
        if left is None or right is None or self.sufficiency is None or self.result is not None:
            raise ValueError("reconciliation requires both independent decompositions")
        if tuple(candidates) != tuple(c.mcu for c in left.candidates):
            raise ValueError("reconciliation candidate snapshot mismatch")
        aligned = await align_decompositions(left, right, runner=self.runner)
        self._pending.append(("mcu_alignment.json", aligned))
        reconciled = await reconcile_decompositions(idea, left, right, aligned, runner=self.runner)
        self.reconciliation = reconciled
        version = create_mcu_version(
            mcus=reconciled.mcus,
            combinations=reconciled.combinations,
            source_reconciliation_hash=canonical_hash(reconciled),
            created_at=self.clock(),
            created_by="understanding-engine",
        )
        graph = MCUGraph(
            idea_id=idea.idea_id,
            mcus=version.mcus,
            combinations=version.combinations,
            unresolved_disagreements=reconciled.unresolved_disagreements,
            provenance=ArtifactProvenance(
                kind="implemented",
                component="UnderstandingComponents",
                detail=f"Two independent decompositions; critic {reconciled.prompt_version}; "
                f"ceiling {reconciled.assessment_ceiling.value}.",
            ),
        )
        final_idea = CanonicalIdeaRepresentation.model_validate(
            {
                **idea.model_dump(),
                "mcu_ids": tuple(m.mcu_id for m in graph.mcus),
                "combination_ids": tuple(c.combination_id for c in graph.combinations),
            }
        )
        self.result = UnderstandingResult(
            final_idea,
            cap_understanding_sufficiency(self.sufficiency, reconciled),
            left,
            right,
            reconciled,
            version,
        )
        self._pending.extend(
            (
                ("mcu_reconciliation.json", reconciled),
                ("mcu_version.json", version),
                ("canonical_idea_initial.json", idea),
            )
        )
        return graph

    def drain_understanding_update(self) -> UnderstandingUpdate:
        calls = self.runner.audits[self._audit_cursor :]
        self._audit_cursor += len(calls)
        final = self.result if not self._final_published else None
        update = UnderstandingUpdate(
            tuple(self._pending),
            calls,
            final.cir if final else None,
            final.reconciliation.assessment_ceiling if final else None,
        )
        self._pending.clear()
        self._final_published = self._final_published or final is not None
        return update


async def understand_idea(
    request: AssessmentRequest,
    *,
    runner: SemanticRunner,
    writer: RunArtifactWriter | None = None,
    assessment_id: AssessmentId | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> UnderstandingResult:
    if (writer is None) != (assessment_id is None):
        raise ValueError("writer and assessment_id must be supplied together")
    components = UnderstandingComponents(runner, clock=clock)
    start_audit = len(runner.audits)
    try:
        idea = await components.normalize(request)
        await components.analyze(idea)
        candidates = await components.decompose(idea)
        graph = await components.reconcile(idea, candidates)
        result = components.result
        if result is None:
            raise RuntimeError("understanding result was not frozen")
        if writer is not None and assessment_id is not None:
            for name, artifact in components.drain_understanding_update().artifacts:
                writer.write_json(assessment_id, name, artifact)
            writer.write_json(assessment_id, "canonical_idea.json", result.cir)
            writer.write_json(assessment_id, "sufficiency.json", result.sufficiency)
            writer.write_json(assessment_id, "mcu_graph.json", graph)
        return result
    finally:
        if writer is not None and assessment_id is not None:
            writer.write_jsonl(assessment_id, "semantic_calls.jsonl", runner.audits[start_audit:])
