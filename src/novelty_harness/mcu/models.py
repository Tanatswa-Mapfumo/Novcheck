from typing import Literal

from pydantic import ConfigDict, Field

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.idea import NonBlankText
from novelty_harness.domain.mcu import MCU, MCUCombination


class MCUCandidate(ContractModel):
    model_config = ConfigDict(frozen=True)
    mcu: MCU
    source_support: tuple[NonBlankText, ...] = Field(min_length=1)
    rationale: NonBlankText
    unresolved_questions: tuple[NonBlankText, ...] = ()


class CombinationCandidate(ContractModel):
    model_config = ConfigDict(frozen=True)
    combination: MCUCombination
    source_support: tuple[NonBlankText, ...] = Field(min_length=1)


class MCUDecomposition(ContractModel):
    model_config = ConfigDict(frozen=True)
    strategy: Literal["INDEPENDENCE_FOCUSED", "RELATIONSHIP_FOCUSED"]
    prompt_version: NonBlankText
    candidates: tuple[MCUCandidate, ...]
    global_unknowns: tuple[NonBlankText, ...] = ()
    combinations: tuple[CombinationCandidate, ...] = ()
