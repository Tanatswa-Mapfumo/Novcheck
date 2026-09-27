from typing import Literal

from pydantic import ConfigDict, Field

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.enums import EvidenceFamily, ResearchDepth
from novelty_harness.domain.idea import NonBlankText
from novelty_harness.domain.ids import MCUId, QueryId
from novelty_harness.ports.models import SourceRef
from novelty_harness.research.retrieval.models import RetrievalStrategy


class BranchState(ContractModel):
    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["research-branch-v1"] = "research-branch-v1"
    mcu_id: MCUId
    evidence_family: EvidenceFamily
    depth: ResearchDepth
    strategies_attempted: frozenset[RetrievalStrategy] = frozenset()
    providers_attempted: frozenset[NonBlankText] = frozenset()
    rounds: int = Field(default=0, ge=0)
    relevant_candidate_count: int = Field(default=0, ge=0)
    new_candidate_yield: tuple[int, ...] = ()
    unresolved: bool = True
    access_failures: tuple[NonBlankText, ...] = ()
    budget_stopped: bool = False
    deferred_neighborhoods: tuple[NonBlankText, ...] = ()


class ResearchAction(ContractModel):
    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["research-action-v1"] = "research-action-v1"
    action_type: Literal[
        "RETRIEVE",
        "PAGE",
        "EXPAND",
        "BUDGET_STOPPED",
        "ACCESS_BLOCKED",
        "NO_ACTION",
        "MULTILINGUAL_UNAVAILABLE",
        "MULTILINGUAL_HOOK",
    ]
    mcu_id: MCUId
    evidence_family: EvidenceFamily
    strategy: RetrievalStrategy | None = None
    provider_name: NonBlankText | None = None
    rationale: NonBlankText
    query_id: QueryId | None = None
    seed_source: SourceRef | None = None
    cursor: str | None = None
    rank_offset: int = Field(default=0, ge=0)
    expansion_depth: int = Field(default=1, ge=1)
