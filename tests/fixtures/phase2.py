"""Recorded semantic responses; no understanding implementation lives here."""

from collections.abc import Sequence
from copy import deepcopy

from pydantic import JsonValue

from novelty_harness.ports.models import ContextBlock, LLMCallConfig, StructuredResult
from tests.fixtures.phase1 import FIXED_TIME
from tests.fixtures.providers import MockLLMProvider


def attack_responses(
    text,
    *,
    candidates=(),
    mechanism=False,
    contribution=True,
    advantages=(),
    ambiguity=(),
    withheld=False,
    combinations=(),
):
    norm = normalization_draft(
        problem=text,
        mechanism=text if mechanism and not withheld else None,
        advantage_statements=list(advantages),
        ambiguities=list(ambiguity),
        explicit_unknowns=["Core mechanism withheld"] if withheld else [],
        source_attributions=[{"field_path": "problem", "supporting_excerpt": text}]
        + (
            [{"field_path": "mechanism", "supporting_excerpt": text}]
            if mechanism and not withheld
            else []
        )
        + [
            {"field_path": f"advantage_statements.{i}", "supporting_excerpt": value}
            for i, value in enumerate(advantages)
        ],
    )
    signals = {
        "problem_defined": True,
        "contribution_identifiable": contribution,
        "mechanism_described": mechanism,
        "relationship_structure_described": mechanism,
        "comparison_scope_identifiable": mechanism,
        "critical_unknowns": [],
        "withheld_mechanism": withheld,
        "contradictory_specification": bool(ambiguity),
    }
    suff = {
        "proposed_state": "HIGH_RESOLUTION",
        "assessable_dimensions": ["problem_landscape", "mechanism"],
        "unassessable_dimensions": [],
        "missing_information": [],
        "consequences": [],
        "signals": signals,
        "prompt_version": "sufficiency-v1",
        "source_attributions": [
            {"field_path": key, "supporting_excerpt": text}
            for key, value in signals.items()
            if value is True
        ],
    }
    ids = tuple(c["mcu"]["mcu_id"] for c in candidates)
    critic = reconciliation_proposal(
        list(candidates), left_ids=ids, right_ids=ids, combinations=list(combinations)
    )
    for test in critic["structural_tests"]:
        test["source_support"] = [text]
        if not candidates:
            test.update(passed=None, severity="MATERIAL")
    return {
        "normalize_idea": norm,
        "assess_sufficiency": suff,
        "decompose_a": decomposition(
            "INDEPENDENCE_FOCUSED",
            deepcopy(list(candidates)),
            combinations=deepcopy(list(combinations)),
        ),
        "decompose_b": decomposition(
            "RELATIONSHIP_FOCUSED",
            deepcopy(list(candidates)),
            combinations=deepcopy(list(combinations)),
        ),
        "align_mcus": {"prompt_version": "alignment-v1", "mappings": []},
        "criticize_mcus": critic,
    }


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


def understanding_responses():
    control = "A temperature sensor controls a relay"
    status = "a separate status indicator reduces operator checks."
    a = candidate(statement=control)
    b = candidate("mcu_status", status)
    b["mcu"]["features"] = [
        {"feature_id": "F1", "concept": "indicator"},
        {"feature_id": "F2", "concept": "checks"},
    ]
    b["mcu"]["relationships"] = [{"subject": "F1", "relation": "REDUCES", "object": "F2"}]
    norm = normalization_draft(
        problem=status,
        mechanism=control,
        advantage_statements=[status],
        source_attributions=[
            {"field_path": "problem", "supporting_excerpt": status},
            {"field_path": "mechanism", "supporting_excerpt": control},
            {"field_path": "advantage_statements.0", "supporting_excerpt": status},
        ],
    )
    suff = {
        "proposed_state": "HIGH_RESOLUTION",
        "assessable_dimensions": ["mechanism"],
        "unassessable_dimensions": ["demonstrated_value"],
        "missing_information": [],
        "consequences": [],
        "prompt_version": "sufficiency-v1",
        "signals": {
            "problem_defined": True,
            "contribution_identifiable": True,
            "mechanism_described": True,
            "relationship_structure_described": True,
            "comparison_scope_identifiable": True,
            "critical_unknowns": [],
        },
        "source_attributions": [
            {"field_path": name, "supporting_excerpt": control}
            for name in (
                "problem_defined",
                "contribution_identifiable",
                "mechanism_described",
                "relationship_structure_described",
                "comparison_scope_identifiable",
            )
        ],
    }
    critic = reconciliation_proposal(
        [a, b], left_ids=("mcu_control", "mcu_status"), right_ids=("mcu_control", "mcu_status")
    )
    for test in critic["structural_tests"]:
        test["source_support"] = [control, status]
    return {
        "normalize_idea": norm,
        "assess_sufficiency": suff,
        "decompose_a": decomposition("INDEPENDENCE_FOCUSED", [a, b]),
        "decompose_b": decomposition("RELATIONSHIP_FOCUSED", [a, b]),
        "criticize_mcus": critic,
    }


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
                "output_mcu_ids": [mcu_id] if mcu_id in ids else ids,
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
