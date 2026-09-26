"""Recorded semantic responses; no understanding implementation lives here."""

from collections.abc import Sequence

from pydantic import JsonValue

from novelty_harness.ports.models import ContextBlock, LLMCallConfig, StructuredResult
from tests.fixtures.phase1 import FIXED_TIME
from tests.fixtures.providers import MockLLMProvider


class RecordedLLM(MockLLMProvider):
    def __init__(self, responses: dict[str, dict[str, JsonValue]]) -> None:
        self.responses = responses
        self.requests = []
        super().__init__(name="recorded-understanding", result=self.result({}))

    def result(self, data):
        return StructuredResult.model_validate(
            {
                "data": data,
                "call": {
                    "provider_name": "recorded-understanding",
                    "provider_version": "recorded-v1",
                    "started_at": FIXED_TIME,
                    "finished_at": FIXED_TIME,
                    "request_hash": "recorded-provider-hash",
                    "status": "SUCCESS",
                },
            }
        )

    async def generate_structured(
        self,
        *,
        task: str,
        schema: dict[str, JsonValue],
        context: Sequence[ContextBlock],
        config: LLMCallConfig,
    ) -> StructuredResult:
        self.requests.append(
            (
                task,
                schema,
                tuple(c.model_copy(deep=True) for c in context),
                config.model_copy(deep=True),
            )
        )
        return self.result(self.responses[task])


def normalization_draft(**updates):
    return {
        "problem": None,
        "target_users_or_context": None,
        "domains": [],
        "application_setting": None,
        "mechanism": None,
        "relationship_statements": [],
        "extracted_claims": [],
        "advantage_statements": [],
        "constraints": [],
        "user_supplied_evidence": [],
        "explicit_unknowns": [],
        "ambiguities": [],
        "source_attributions": [],
        "prompt_version": "normalization-v1",
        **updates,
    }


def candidate(mcu_id="mcu_control", statement="Sensor controls relay.", **updates):
    return {
        "mcu": {
            "mcu_id": mcu_id,
            "label": "Sensor control",
            "statement": statement,
            "mechanism": statement,
            "features": [
                {"feature_id": "F1", "concept": "Sensor"},
                {"feature_id": "F2", "concept": "relay"},
            ],
            "relationships": [{"subject": "F1", "relation": "CONTROLS", "object": "F2"}],
            "provenance": {
                "kind": "implemented",
                "component": "decomposition",
                "detail": "Model proposed; requires validation",
            },
        },
        "source_support": [statement],
        "rationale": "Independently meaningful control",
        "unresolved_questions": [],
        **updates,
    }


def decomposition(strategy, candidates=None, **updates):
    return {
        "strategy": strategy,
        "prompt_version": "decomposition-a-v1"
        if strategy == "INDEPENDENCE_FOCUSED"
        else "decomposition-b-v1",
        "candidates": candidates if candidates is not None else [candidate()],
        "global_unknowns": [],
        "combinations": [],
        **updates,
    }
