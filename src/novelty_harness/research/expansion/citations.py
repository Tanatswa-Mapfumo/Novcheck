from datetime import date
from typing import Literal

from pydantic import ConfigDict, Field

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.ids import MCUId
from novelty_harness.ports.models import SourceRef
from novelty_harness.ports.retrieval import NativeRetrievalProvider
from novelty_harness.providers.errors import ProviderError
from novelty_harness.research.retrieval.models import (
    RetrievalBatch,
    RetrievalCandidate,
    RetrievalStrategy,
)


class ExpansionRequest(ContractModel):
    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["expansion-request-v1"] = "expansion-request-v1"
    source: SourceRef
    mcu_id: MCUId | None
    kinds: frozenset[RetrievalStrategy]
    depth: int = Field(default=1, ge=1)


class ExpansionResult(ContractModel):
    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["expansion-result-v1"] = "expansion-result-v1"
    candidates: tuple[RetrievalCandidate, ...] = ()
    attempted_kinds: frozenset[RetrievalStrategy] = frozenset()
    unavailable_kinds: frozenset[RetrievalStrategy] = frozenset()
    deferred_kinds: frozenset[RetrievalStrategy] = frozenset()
    failures: tuple[str, ...] = ()
    batches: tuple[RetrievalBatch, ...] = ()


EXPANSION_KINDS = frozenset(
    {
        RetrievalStrategy.CITATION_BACKWARD,
        RetrievalStrategy.CITATION_FORWARD,
        RetrievalStrategy.RELATED_WORK,
        RetrievalStrategy.ENTITY_LINEAGE,
    }
)


async def expand_candidates(
    request: ExpansionRequest,
    *,
    provider: NativeRetrievalProvider | None,
    as_of: date,
    max_actions: int,
    approved_depth: int = 1,
) -> ExpansionResult:
    request = ExpansionRequest.model_validate(request.model_dump())
    if request.depth > approved_depth:
        raise ValueError("Deeper expansion requires explicit controller approval")
    if type(max_actions) is not int or max_actions < 0:
        raise ValueError("Expansion action budget must be a nonnegative integer")
    if not request.kinds <= EXPANSION_KINDS:
        raise ValueError("Only expansion strategies are accepted")
    if provider is None or provider.name != request.source.provider_name:
        return ExpansionResult(unavailable_kinds=request.kinds)
    caps = await provider.retrieval_capabilities()
    unavailable = request.kinds - caps.strategies
    attempted: set[RetrievalStrategy] = set()
    deferred: set[RetrievalStrategy] = set()
    batches: list[RetrievalBatch] = []
    failures: list[str] = []
    for kind in sorted(request.kinds - unavailable):
        if len(attempted) >= max_actions:
            deferred.add(kind)
            continue
        attempted.add(kind)
        try:
            batch = await provider.expand(
                source=request.source, strategy=kind, as_of=as_of, mcu_id=request.mcu_id
            )
            batch = RetrievalBatch.model_validate(batch.model_dump())
            if (
                batch.provider_name != provider.name
                or batch.strategy != kind
                or any(
                    c.seed_source != request.source or c.mcu_id != request.mcu_id
                    for c in batch.candidates
                )
            ):
                failures.append(f"{provider.name}:{kind.value}:PARSE_FAILURE")
                continue
            batches.append(batch)
        except ProviderError as error:
            failures.append(f"{provider.name}:{kind.value}:{error.failure.category.value}")
        except ValueError:
            failures.append(f"{provider.name}:{kind.value}:PARSE_FAILURE")
    return ExpansionResult(
        candidates=tuple(c for b in batches for c in b.candidates),
        attempted_kinds=frozenset(attempted),
        unavailable_kinds=unavailable,
        deferred_kinds=frozenset(deferred),
        failures=tuple(failures),
        batches=tuple(batches),
    )
