from collections.abc import Sequence, Set
from typing import Literal

from pydantic import ConfigDict, Field, FiniteFloat

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.idea import NonBlankText
from novelty_harness.ports.models import SourceRef
from novelty_harness.research.fusion.rrf import FusedCandidate
from novelty_harness.research.retrieval.models import RetrievalStrategy


class RecoveryPath(ContractModel):
    model_config = ConfigDict(frozen=True)
    provider_name: NonBlankText
    strategy: RetrievalStrategy
    query_id: str | None
    seed_source: SourceRef | None
    local_rank: int = Field(ge=1)


class KnownItemMetrics(ContractModel):
    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["known-item-metrics-v1"] = "known-item-metrics-v1"
    case_id: NonBlankText
    attack_type: NonBlankText
    k: int = Field(ge=1)
    recall_at_k: FiniteFloat = Field(ge=0, le=1)
    reciprocal_rank: FiniteFloat = Field(ge=0, le=1)
    recovery_paths: tuple[RecoveryPath, ...]
    providers: frozenset[str]
    strategies: frozenset[RetrievalStrategy]


def measure_known_item(
    *,
    case_id: str,
    attack_type: str,
    ranked: Sequence[FusedCandidate],
    expected_sources: Set[tuple[str, str]],
    allowed_providers: frozenset[str],
    k: int,
) -> KnownItemMetrics:
    if type(k) is not int or k < 1 or not expected_sources:
        raise ValueError("Positive target K and designated source identities are required")
    first: int | None = None
    paths: list[RecoveryPath] = []
    for rank, fused in enumerate(ranked, 1):
        found = [
            c
            for c in fused.discoveries
            if c.provider_name in allowed_providers
            and (c.provider_name, c.source.provider_source_id) in expected_sources
        ]
        if not found:
            continue
        if first is None:
            first = rank
        paths.extend(
            RecoveryPath(
                provider_name=c.provider_name,
                strategy=c.strategy,
                query_id=c.query_id,
                seed_source=c.seed_source,
                local_rank=c.local_rank,
            )
            for c in found
        )
    return KnownItemMetrics(
        case_id=case_id,
        attack_type=attack_type,
        k=k,
        recall_at_k=1 if first is not None and first <= k else 0,
        reciprocal_rank=1 / first if first is not None else 0,
        recovery_paths=tuple(paths),
        providers=frozenset(p.provider_name for p in paths),
        strategies=frozenset(p.strategy for p in paths),
    )
