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


def map_evidence_response(context: Sequence[ContextBlock]) -> Mapping[str, JsonValue]:
    """Scripted mapper: match every proposition commitment to the first passage."""

    proposition = context_json(context, "proposition")
    passages = context_json(context, "passages")
    assert isinstance(proposition, dict) and isinstance(passages, list)
    if not passages:
        return {"prompt_version": "evidence-mapper-v1", "dimensions": [], "unresolved": []}
    first_passage = passages[0]["passage_id"]
    grouped: dict[str, dict[str, object]] = {}
    for commitment in proposition["commitments"]:
        dimension = commitment["dimension"]
        entry = grouped.setdefault(
            dimension, {"dimension": dimension, "matching": [], "missing": [], "conflicting": []}
        )
        statement: dict[str, object] = {
            "statement": commitment["text"],
            "passage_ids": [first_passage],
        }
        if commitment.get("relationship"):
            statement["relationship"] = commitment["relationship"]
        entry["matching"].append(statement)
    return {
        "prompt_version": "evidence-mapper-v1",
        "dimensions": list(grouped.values()),
        "unresolved": [],
    }


def verify_support_response(context: Sequence[ContextBlock]) -> Mapping[str, JsonValue]:
    """Scripted verifier: mark every commitment supported by the first passage."""

    payload = context_json(context, "verification_input")
    assert isinstance(payload, dict)
    first_passage = payload["passages"][0]["passage_id"]
    return {
        "prompt_version": "support-verifier-v1",
        "judgments": [
            {
                "commitment_id": commitment["commitment_id"],
                "state": "SUPPORTED",
                "rationale": "scripted fixture support",
                "passage_ids": [first_passage],
            }
            for commitment in payload["commitments"]
        ],
        "context_needed": [],
    }


def scripted_phase6_llm(name: str = "scripted-phase6") -> StubLLMProvider:
    return StubLLMProvider(
        {
            "map_evidence": map_evidence_response,
            "verify_support": verify_support_response,
        },
        name=name,
    )
