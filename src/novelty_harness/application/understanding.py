from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.enums import SufficiencyState
from novelty_harness.domain.idea import CanonicalIdeaRepresentation
from novelty_harness.runtime.semantic.structured import SemanticCallAudit


@dataclass(frozen=True, slots=True)
class UnderstandingUpdate:
    artifacts: tuple[tuple[str, ContractModel], ...] = ()
    calls: tuple[SemanticCallAudit, ...] = ()
    finalized_idea: CanonicalIdeaRepresentation | None = None
    assessment_ceiling: SufficiencyState | None = None


@runtime_checkable
class UnderstandingArtifactSource(Protocol):
    def drain_understanding_update(self) -> UnderstandingUpdate: ...
