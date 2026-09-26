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


def reconciliation_proposal(
    candidates=None, left_ids=("mcu_control",), right_ids=("mcu_control",), **updates
):
    candidates = candidates if candidates is not None else [candidate()]
    ids = [c["mcu"]["mcu_id"] for c in candidates]
    return {
        "prompt_version": "structural-critic-v1",
        "candidates": candidates,
        "combinations": [],
        "unresolved_disagreements": [],
        "resolutions": [
            {
                "strategy": strategy,
                "input_mcu_id": mcu_id,
                "output_mcu_ids": ids,
                "reason": "Retain supported contribution",
            }
            for strategy, mcus in (
                ("INDEPENDENCE_FOCUSED", left_ids),
                ("RELATIONSHIP_FOCUSED", right_ids),
            )
            for mcu_id in mcus
        ],
        "structural_tests": [
            {
                "test_name": name,
                "mcu_ids": ids,
                "passed": True,
                "severity": "INFO",
                "explanation": "Supported meaningful structure",
                "source_support": ["Sensor controls relay."],
            }
            for name in (
                "REMOVAL",
                "INDEPENDENCE",
                "RELATIONSHIP_PRESERVATION",
                "MERGE",
                "PARAPHRASE_STABILITY",
                "SPECIFICITY",
            )
        ],
        **updates,
    }
