from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from novelty_harness.ports.models import RerankResult


@runtime_checkable
class Reranker(Protocol):
    @property
    def name(self) -> str: ...
    async def rank(self, query_representation: str, candidates: Sequence[str]) -> RerankResult: ...
