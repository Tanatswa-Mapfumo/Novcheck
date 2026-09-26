from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from pydantic import JsonValue

from novelty_harness.ports.models import ContextBlock, LLMCallConfig, StructuredResult


@runtime_checkable
class LLMProvider(Protocol):
    @property
    def name(self) -> str: ...
    async def generate_structured(
        self,
        *,
        task: str,
        schema: dict[str, JsonValue],
        context: Sequence[ContextBlock],
        config: LLMCallConfig,
    ) -> StructuredResult: ...
