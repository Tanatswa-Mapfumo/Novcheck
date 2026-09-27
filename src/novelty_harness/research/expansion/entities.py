from datetime import date

from novelty_harness.ports.retrieval import NativeRetrievalProvider
from novelty_harness.research.expansion.citations import (
    ExpansionRequest,
    ExpansionResult,
    expand_candidates,
)
from novelty_harness.research.retrieval.models import RetrievalStrategy


async def expand_entities(
    request: ExpansionRequest,
    *,
    provider: NativeRetrievalProvider | None,
    as_of: date,
    max_actions: int,
    approved_depth: int = 1,
) -> ExpansionResult:
    if request.kinds != frozenset({RetrievalStrategy.ENTITY_LINEAGE}):
        raise ValueError("Entity traversal must be an explicit ENTITY_LINEAGE request")
    return await expand_candidates(
        request,
        provider=provider,
        as_of=as_of,
        max_actions=max_actions,
        approved_depth=approved_depth,
    )
