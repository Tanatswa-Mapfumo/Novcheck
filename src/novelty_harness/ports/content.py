from typing import Protocol, runtime_checkable

from novelty_harness.ports.models import Passage, SourceContent, SourceRef


@runtime_checkable
class ContentResolver(Protocol):
    @property
    def name(self) -> str: ...
    async def resolve(self, source_ref: SourceRef) -> SourceContent: ...
    async def resolve_passage(self, source_ref: SourceRef, locator: str) -> Passage: ...
