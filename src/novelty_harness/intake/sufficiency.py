from pydantic import ConfigDict

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.enums import SufficiencyState
from novelty_harness.domain.idea import (
    ArtifactProvenance,
    CanonicalIdeaRepresentation,
    NonBlankText,
    SufficiencyAssessment,
)
from novelty_harness.intake.models import InputSpanAttribution
from novelty_harness.intake.prompts import SUFFICIENCY_INSTRUCTION, SUFFICIENCY_VERSION
from novelty_harness.ports.models import ContextBlock
from novelty_harness.runtime.semantic.structured import SemanticRunner, SemanticTaskSpec

RESOLUTION_ORDER = (
    SufficiencyState.INSUFFICIENT,
    SufficiencyState.EXPLORATORY,
    SufficiencyState.ASSESSABLE,
    SufficiencyState.HIGH_RESOLUTION,
)


def lower_resolution(left: SufficiencyState, right: SufficiencyState) -> SufficiencyState:
    return min((left, right), key=RESOLUTION_ORDER.index)


class SufficiencySignals(ContractModel):
    model_config = ConfigDict(frozen=True)
    problem_defined: bool
    contribution_identifiable: bool
    mechanism_described: bool
    relationship_structure_described: bool
    comparison_scope_identifiable: bool
    critical_unknowns: tuple[NonBlankText, ...] = ()
    withheld_mechanism: bool = False
    contradictory_specification: bool = False


class SufficiencyReasoning(ContractModel):
    model_config = ConfigDict(frozen=True)
    proposed_state: SufficiencyState
    assessable_dimensions: tuple[NonBlankText, ...]
    unassessable_dimensions: tuple[NonBlankText, ...]
    missing_information: tuple[NonBlankText, ...]
    consequences: tuple[NonBlankText, ...]
    signals: SufficiencySignals
    prompt_version: NonBlankText
    source_attributions: tuple[InputSpanAttribution, ...] = ()


def apply_sufficiency_ceiling(
    reasoning: SufficiencyReasoning,
    cir: CanonicalIdeaRepresentation,
) -> SufficiencyAssessment:
    attrs = {a.field_path: a.supporting_excerpt for a in reasoning.source_attributions}
    if len(attrs) != len(reasoning.source_attributions):
        raise ValueError("duplicate sufficiency attribution")
    signals = reasoning.signals

    def grounded(name: str, value: bool) -> bool:
        support = attrs.get(name)
        return value and support is not None and support in cir.original_input

    contribution = grounded("contribution_identifiable", signals.contribution_identifiable)
    mechanism = (
        grounded("mechanism_described", signals.mechanism_described)
        and not signals.withheld_mechanism
    )
    scope = grounded("comparison_scope_identifiable", signals.comparison_scope_identifiable)
    relationship = grounded(
        "relationship_structure_described", signals.relationship_structure_described
    )
    problem = grounded("problem_defined", signals.problem_defined)
    ceiling = SufficiencyState.HIGH_RESOLUTION
    missing = list(reasoning.missing_information)
    unassessable = list(reasoning.unassessable_dimensions)
    consequences = list(reasoning.consequences)
    if not contribution:
        ceiling = SufficiencyState.INSUFFICIENT
        missing.append("Identifiable contribution")
    elif not mechanism or not scope or signals.contradictory_specification:
        ceiling = SufficiencyState.EXPLORATORY
    elif not relationship or not problem or signals.critical_unknowns or cir.unknowns:
        ceiling = SufficiencyState.ASSESSABLE
    if not mechanism:
        unassessable.append("mechanism")
        missing.append(
            "Core mechanism withheld" if signals.withheld_mechanism else "Core mechanism"
        )
    if not relationship:
        unassessable.append("relationship_structure")
        missing.append("Contribution-bearing relationships")
    if not scope:
        unassessable.append("comparison_scope")
        missing.append("Comparison scope")
    missing.extend(signals.critical_unknowns)
    if signals.contradictory_specification:
        missing.append("Resolve contradictory specification")
    state = lower_resolution(reasoning.proposed_state, ceiling)
    if state != SufficiencyState.HIGH_RESOLUTION:
        consequences.append("Specification limits resolution; missing detail is not novelty.")
    assessable = tuple(d for d in reasoning.assessable_dimensions if d not in unassessable)
    return SufficiencyAssessment(
        idea_id=cir.idea_id,
        state=state,
        assessable_dimensions=assessable,
        unassessable_dimensions=tuple(dict.fromkeys(unassessable)),
        missing_information=tuple(dict.fromkeys(missing)),
        consequences=tuple(dict.fromkeys(consequences)),
        provenance=ArtifactProvenance(
            kind="implemented",
            component="StructuralSufficiencyAnalyzer",
            detail=f"Structural ceiling; prompt {SUFFICIENCY_VERSION}; no length thresholds.",
        ),
    )


class StructuralSufficiencyAnalyzer:
    def __init__(self, runner: SemanticRunner) -> None:
        self.runner = runner

    async def analyze_reasoning(self, idea: CanonicalIdeaRepresentation) -> SufficiencyReasoning:
        result = await self.runner.run(
            SemanticTaskSpec("assess_sufficiency", SUFFICIENCY_VERSION, SufficiencyReasoning),
            SUFFICIENCY_INSTRUCTION + f"\nprompt_version: {SUFFICIENCY_VERSION}",
            [ContextBlock(label="canonical_idea", text=idea.model_dump_json())],
        )
        if result.prompt_version != SUFFICIENCY_VERSION:
            raise ValueError("sufficiency prompt version mismatch")
        return result

    async def analyze(self, idea: CanonicalIdeaRepresentation) -> SufficiencyAssessment:
        return apply_sufficiency_ceiling(await self.analyze_reasoning(idea), idea)
