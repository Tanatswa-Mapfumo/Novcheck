from datetime import date
from typing import Protocol, runtime_checkable

from novelty_harness.domain.ids import MCUId
from novelty_harness.ports.models import SourceRef
from novelty_harness.research.models import SearchIntent
from novelty_harness.research.retrieval.models import (
    RetrievalBatch,
    RetrievalCapabilities,
    RetrievalStrategy,
)


@runtime_checkable
class NativeRetrievalProvider(Protocol):
    @property
    def name(self) -> str: ...
    async def retrieval_capabilities(self) -> RetrievalCapabilities: ...
    async def retrieve(
        self,
        *,
        intent: SearchIntent,
        strategy: RetrievalStrategy,
        as_of: date,
        cursor: str | None = None,
        rank_offset: int = 0,
    ) -> RetrievalBatch: ...
    async def expand(
        self,
        *,
        source: SourceRef,
        strategy: RetrievalStrategy,
        as_of: date,
        mcu_id: MCUId | None = None,
        cursor: str | None = None,
        rank_offset: int = 0,
    ) -> RetrievalBatch: ...
