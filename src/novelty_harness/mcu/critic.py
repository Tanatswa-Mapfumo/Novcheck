from typing import Literal

from pydantic import ConfigDict

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.idea import CanonicalIdeaRepresentation, NonBlankText
from novelty_harness.domain.ids import MCUId
from novelty_harness.mcu.alignment import DecompositionAlignment, signature
from novelty_harness.mcu.decomposition import validate_decomposition
from novelty_harness.mcu.models import CombinationCandidate, MCUCandidate, MCUDecomposition
from novelty_harness.mcu.prompts import CRITIC_INSTRUCTION, CRITIC_VERSION
from novelty_harness.ports.models import ContextBlock
from novelty_harness.runtime.semantic.structured import SemanticRunner, SemanticTaskSpec

STRUCTURAL_TESTS = (
    "REMOVAL",
    "INDEPENDENCE",
    "RELATIONSHIP_PRESERVATION",
    "MERGE",
    "PARAPHRASE_STABILITY",
    "SPECIFICITY",
)


class StructuralTestResult(ContractModel):
    model_config = ConfigDict(frozen=True)
    test_name: Literal[
        "REMOVAL",
        "INDEPENDENCE",
        "RELATIONSHIP_PRESERVATION",
        "MERGE",
        "PARAPHRASE_STABILITY",
        "SPECIFICITY",
    ]
    mcu_ids: tuple[MCUId, ...]
    passed: bool | None
    severity: Literal["INFO", "WARNING", "MATERIAL"]
    explanation: NonBlankText
    source_support: tuple[NonBlankText, ...] = ()


class CandidateResolution(ContractModel):
    model_config = ConfigDict(frozen=True)
    strategy: Literal["INDEPENDENCE_FOCUSED", "RELATIONSHIP_FOCUSED"]
    input_mcu_id: MCUId
    output_mcu_ids: tuple[MCUId, ...]
    reason: NonBlankText
    disposition: Literal["REPRESENTED", "CONTEXT_ONLY"] = "REPRESENTED"


class ReconciliationProposal(ContractModel):
    model_config = ConfigDict(frozen=True)
    prompt_version: NonBlankText
    candidates: tuple[MCUCandidate, ...]
    combinations: tuple[CombinationCandidate, ...]
    resolutions: tuple[CandidateResolution, ...]
    structural_tests: tuple[StructuralTestResult, ...]
    unresolved_disagreements: tuple[NonBlankText, ...]


def validate_criticism(
    proposal: ReconciliationProposal,
    idea: CanonicalIdeaRepresentation,
    left: MCUDecomposition,
    right: MCUDecomposition,
) -> None:
    if proposal.prompt_version != CRITIC_VERSION:
        raise ValueError("critic prompt version mismatch")
    validated = MCUDecomposition(
        strategy="INDEPENDENCE_FOCUSED",
        prompt_version=CRITIC_VERSION,
        candidates=proposal.candidates,
        combinations=proposal.combinations,
    )
    validate_decomposition(validated, idea.original_input)
    tests = proposal.structural_tests
    if len(tests) != len(STRUCTURAL_TESTS) or {t.test_name for t in tests} != set(STRUCTURAL_TESTS):
        raise ValueError("all six structural tests required exactly once")
    outputs = {c.mcu.mcu_id: c for c in proposal.candidates}
    for test in tests:
        if not set(test.mcu_ids) <= set(outputs) or len(set(test.mcu_ids)) != len(test.mcu_ids):
            raise ValueError("invalid structural test MCU reference")
        if test.passed is not None and (
            not test.source_support
            or any(s not in idea.original_input for s in test.source_support)
        ):
            raise ValueError("meaning-level structural judgment requires input support")
    inputs = {(d.strategy, c.mcu.mcu_id): c for d in (left, right) for c in d.candidates}
    resolutions = {(r.strategy, r.input_mcu_id): r for r in proposal.resolutions}
    if len(resolutions) != len(proposal.resolutions) or set(resolutions) != set(inputs):
        raise ValueError("every input candidate requires one explicit resolution")
    referenced: set[str] = set()
    for key, resolution in resolutions.items():
        original = inputs[key]
        targets = resolution.output_mcu_ids
        if not set(targets) <= set(outputs) or len(set(targets)) != len(targets):
            raise ValueError("invalid resolution output reference")
        if resolution.disposition == "CONTEXT_ONLY":
            if targets or original.mcu.relationships or original.mcu.mechanism:
                raise ValueError("cannot discard mechanism/relationships as context")
            continue
        if not targets:
            raise ValueError("contribution cannot disappear during reconciliation")
        referenced.update(targets)
        represented_links = frozenset(
            link for target in targets for link in signature(outputs[target].mcu)
        )
        if not signature(original.mcu) <= represented_links:
            raise ValueError("reconciliation loses contribution-bearing relationship")
        for feature in original.mcu.features:
            if not any(
                feature.concept.casefold() == f.concept.casefold()
                for target in targets
                for f in outputs[target].mcu.features
            ):
                raise ValueError("reconciliation loses supported feature")
    if referenced != set(outputs):
        raise ValueError("unbound reconciled contribution")
    # Combinations are separately retained; any incompatible representation stays unresolved.
    for original in (*left.combinations, *right.combinations):
        mappings = {
            r.input_mcu_id: r.output_mcu_ids
            for r in proposal.resolutions
            if r.strategy == (left.strategy if original in left.combinations else right.strategy)
        }
        members = {
            target for member in original.combination.member_ids for target in mappings[member]
        }
        if not any(
            set(c.combination.member_ids) == members
            and c.combination.statement == original.combination.statement
            for c in proposal.combinations
        ):
            raise ValueError("meaningful combination lost during reconciliation")


async def criticize_structure(
    idea: CanonicalIdeaRepresentation,
    left: MCUDecomposition,
    right: MCUDecomposition,
    alignment: DecompositionAlignment,
    *,
    runner: SemanticRunner,
) -> ReconciliationProposal:
    proposal = await runner.run(
        SemanticTaskSpec("criticize_mcus", CRITIC_VERSION, ReconciliationProposal),
        CRITIC_INSTRUCTION + f"\nprompt_version: {CRITIC_VERSION}",
        [
            ContextBlock(label="canonical_idea", text=idea.model_dump_json()),
            ContextBlock(label="decomposition_a", text=left.model_dump_json()),
            ContextBlock(label="decomposition_b", text=right.model_dump_json()),
            ContextBlock(label="alignment", text=alignment.model_dump_json()),
        ],
    )
    validate_criticism(proposal, idea, left, right)
    return proposal
