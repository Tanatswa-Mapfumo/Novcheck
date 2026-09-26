from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from novelty_harness.ports.models import EmbeddingResult


@runtime_checkable
class EmbeddingProvider(Protocol):
    @property
    def name(self) -> str: ...
    async def embed(self, texts: Sequence[str]) -> EmbeddingResult: ...
