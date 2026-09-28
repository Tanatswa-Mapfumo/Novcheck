"""Deterministic Phase 6 fixtures. Production code never imports these."""

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime

from pydantic import JsonValue

from novelty_harness.domain.enums import TraceStatus
from novelty_harness.ports.models import (
    ContextBlock,
    LLMCallConfig,
    ProviderCallMetadata,
    StructuredResult,
)
from novelty_harness.runtime.tracing.hashing import canonical_hash, canonical_json

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)

StubResponse = Mapping[str, JsonValue] | Callable[[Sequence[ContextBlock]], Mapping[str, JsonValue]]


class StubLLMProvider:
    """Deterministic structured provider for mapper/verifier/classifier tests."""

    def __init__(
        self,
        responses: Mapping[str, StubResponse],
        *,
        name: str = "stub-llm",
    ) -> None:
        self._responses = dict(responses)
        self._name = name
        self.calls: list[tuple[str, tuple[ContextBlock, ...]]] = []

    @property
    def name(self) -> str:
        return self._name

    async def generate_structured(
        self,
        *,
        task: str,
        schema: dict[str, JsonValue],
        context: Sequence[ContextBlock],
        config: LLMCallConfig,
    ) -> StructuredResult:
        response = self._responses[task]
        data = response(context) if callable(response) else response
        self.calls.append((task, tuple(context)))
        return StructuredResult(
            data=dict(data),
            raw_text=None,
            call=ProviderCallMetadata(
                provider_name=self._name,
                provider_version="stub-1",
                started_at=NOW,
                finished_at=NOW,
                request_hash=canonical_hash(
                    {"task": task, "context": [item.model_dump(mode="json") for item in context]}
                ),
                status=TraceStatus.SUCCESS,
            ),
        )


def context_payload(context: Sequence[ContextBlock], label: str) -> JsonValue:
    for block in context:
        if block.label == label:
            return block.text
    raise KeyError(label)


def context_json(context: Sequence[ContextBlock], label: str) -> object:
    import json

    return json.loads(str(context_payload(context, label)))


def canonical_context_dump(context: Sequence[ContextBlock]) -> str:
    return canonical_json([item.model_dump(mode="json") for item in context])
