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
