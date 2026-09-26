from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from novelty_harness.ports.models import RerankResult


@runtime_checkable
class Reranker(Protocol):
    @property
    def name(self) -> str: ...
    async def rank(self, query_representation: str, candidates: Sequence[str]) -> RerankResult:
        """Return unique input strings as candidate IDs with unique one-based ranks.

        Ranks must be within the input count. Partial and empty results are allowed;
        result order need not match input order.
        """
        ...
