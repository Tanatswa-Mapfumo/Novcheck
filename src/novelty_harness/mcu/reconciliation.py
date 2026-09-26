from typing import Literal

from pydantic import ConfigDict

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.enums import SufficiencyState
from novelty_harness.domain.idea import CanonicalIdeaRepresentation, NonBlankText
from novelty_harness.domain.ids import MCUId
from novelty_harness.domain.mcu import MCU, MCUCombination
from novelty_harness.mcu.alignment import DecompositionAlignment
from novelty_harness.mcu.critic import (
    CandidateResolution,
    StructuralTestResult,
    criticize_structure,
)
from novelty_harness.mcu.models import MCUDecomposition
from novelty_harness.mcu.prompts import CRITIC_VERSION
from novelty_harness.runtime.semantic.structured import SemanticRunner


class ReconciliationResult(ContractModel):
    model_config = ConfigDict(frozen=True)
    mcus: tuple[MCU, ...]
    combinations: tuple[MCUCombination, ...]
    alignment: DecompositionAlignment
    structural_tests: tuple[StructuralTestResult, ...]
    unresolved_disagreements: tuple[NonBlankText, ...]
    decomposition_stability: Literal["STABLE", "MINOR_DISAGREEMENT", "MATERIAL_DISAGREEMENT"]
    assessment_ceiling: SufficiencyState
    affected_mcu_ids: tuple[MCUId, ...] = ()
    resolutions: tuple[CandidateResolution, ...] = ()
    prompt_version: NonBlankText = CRITIC_VERSION


async def reconcile_decompositions(
    idea: CanonicalIdeaRepresentation,
    left: MCUDecomposition,
    right: MCUDecomposition,
    alignment: DecompositionAlignment,
    *,
    runner: SemanticRunner,
) -> ReconciliationResult:
    proposal = await criticize_structure(idea, left, right, alignment, runner=runner)
    unresolved = list(proposal.unresolved_disagreements)
    affected: set[str] = set()
    outputs = {c.mcu.mcu_id for c in proposal.candidates}
    resolutions = {(r.strategy, r.input_mcu_id): r.output_mcu_ids for r in proposal.resolutions}
    non_equivalent = [p for p in alignment.pairs if p.relation != "EQUIVALENT"]
    for pair in non_equivalent:
        # Explicit structural repairs may resolve granularity, never opposing directed meanings.
        if pair.relation in ("DISTINCT", "UNRESOLVED"):
            unresolved.append(
                f"{pair.left_mcu_id}/{pair.right_mcu_id}: {pair.relation}; "
                + "; ".join(pair.relationship_differences)
            )
            affected.update(resolutions[(left.strategy, pair.left_mcu_id)])
            affected.update(resolutions[(right.strategy, pair.right_mcu_id)])
    for test in proposal.structural_tests:
        if test.passed is not True:
            unresolved.append(f"{test.test_name}: {test.explanation}")
            affected.update(test.mcu_ids or outputs)
    for unknown in (*left.global_unknowns, *right.global_unknowns):
        unresolved.append(unknown)
        affected.update(outputs)
    for c in (*left.candidates, *right.candidates):
        if c.unresolved_questions:
            unresolved.extend(c.unresolved_questions)
            affected.update(outputs)
    if unresolved:
        affected.update(outputs if not affected else ())
    stability: Literal["STABLE", "MINOR_DISAGREEMENT", "MATERIAL_DISAGREEMENT"] = (
        "MATERIAL_DISAGREEMENT"
        if unresolved
        else "MINOR_DISAGREEMENT"
        if non_equivalent or alignment.unmatched_left or alignment.unmatched_right
        else "STABLE"
    )
    return ReconciliationResult(
        mcus=tuple(c.mcu for c in proposal.candidates),
        combinations=tuple(c.combination for c in proposal.combinations),
        alignment=alignment,
        structural_tests=proposal.structural_tests,
        unresolved_disagreements=tuple(dict.fromkeys(unresolved)),
        decomposition_stability=stability,
        assessment_ceiling=SufficiencyState.EXPLORATORY
        if unresolved
        else SufficiencyState.HIGH_RESOLUTION,
        affected_mcu_ids=tuple(sorted(affected)),
        resolutions=proposal.resolutions,
    )
