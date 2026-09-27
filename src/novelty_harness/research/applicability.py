from collections.abc import Sequence
from typing import Literal

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.enums import EvidenceFamily
from novelty_harness.domain.idea import CanonicalIdeaRepresentation, NonBlankText
from novelty_harness.domain.mcu import MCU
from novelty_harness.ports.models import ContextBlock
from novelty_harness.research.models import EvidenceFamilyAssessment, FamilyApplicability
from novelty_harness.research.prompts import APPLICABILITY, APPLICABILITY_VERSION
from novelty_harness.runtime.semantic.structured import SemanticRunner, SemanticTaskSpec


class FamilyProposal(EvidenceFamilyAssessment):
    exclusion_basis: (
        Literal["SEMANTIC_INCOMPATIBILITY", "PROVIDER_AVAILABILITY", "USER_ASSERTION"] | None
    ) = None
    exclusion_support: tuple[NonBlankText, ...] = ()


class ApplicabilityProposal(ContractModel):
    prompt_version: Literal["family-applicability-v1"]
    assessments: tuple[FamilyProposal, ...]


class EvidenceFamilyApplicabilityAssessor:
    def __init__(self, runner: SemanticRunner) -> None:
        self.runner = runner

    async def assess(
        self, *, idea: CanonicalIdeaRepresentation, mcus: Sequence[MCU]
    ) -> list[EvidenceFamilyAssessment]:
        proposal = await self.runner.run(
            SemanticTaskSpec("assess_families", APPLICABILITY_VERSION, ApplicabilityProposal),
            APPLICABILITY,
            [
                ContextBlock(label="idea", text=idea.model_dump_json()),
                ContextBlock(
                    label="mcus", text="[" + ",".join(m.model_dump_json() for m in mcus) + "]"
                ),
            ],
        )
        expected = {(m.mcu_id, family) for m in mcus for family in EvidenceFamily}
        actual = [(a.mcu_id, a.evidence_family) for a in proposal.assessments]
        if len(actual) != len(set(actual)) or set(actual) != expected:
            raise ValueError("applicability must assess all families exactly once per known MCU")
        by_id = {m.mcu_id: m for m in mcus}
        result: list[EvidenceFamilyAssessment] = []
        for row in proposal.assessments:
            data = row.model_dump(exclude={"exclusion_basis", "exclusion_support"})
            mcu = by_id[row.mcu_id]
            if row.applicability == FamilyApplicability.NOT_APPLICABLE:
                supported = (
                    row.exclusion_basis == "SEMANTIC_INCOMPATIBILITY"
                    and bool(row.exclusion_support)
                    and all(quote in idea.original_input for quote in row.exclusion_support)
                    and bool(mcu.features or mcu.relationships or mcu.mechanism)
                )
                if not supported:
                    data.update(
                        applicability=FamilyApplicability.UNRESOLVED,
                        exclusion_reason=None,
                        limitations=(
                            *row.limitations,
                            "Exclusion lacks grounded semantic support; "
                            "applicability remains unresolved",
                        ),
                    )
            result.append(EvidenceFamilyAssessment.model_validate(data))
        return result
