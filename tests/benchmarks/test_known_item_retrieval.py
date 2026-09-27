import httpx
import pytest

from novelty_harness.evaluation.known_item import measure_known_item
from novelty_harness.research.adaptive.pipeline import run_adaptive_research
from novelty_harness.research.coverage import CoveragePolicy
from novelty_harness.runtime.artifacts.writer import RunArtifactWriter
from novelty_harness.runtime.budgets.controller import BudgetController
from novelty_harness.runtime.config.models import BudgetLimits
from novelty_harness.runtime.tracing.sinks import InMemoryTraceSink
from tests.fixtures.known_items import CASES, recording, reviewed_case
from tests.fixtures.phase1 import make_fixture
from tests.fixtures.phase4 import assessment, registry, stop_policy


async def benchmark_case(case):
    record = assessment()
    record = record.model_copy(
        update={"request": record.request.model_copy(update={"input_text": case["input"]})}
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(recording(case))) as client:
        providers, _ = registry(client)
        result = await run_adaptive_research(
            assessment=record,
            mcus=make_fixture().graph.mcus,
            reviewed_plan=await reviewed_case(case),
            provider_registry=providers,
            coverage_policy=CoveragePolicy.standard(),
            budget_controller=BudgetController(),
            budget_limits=BudgetLimits(max_deep_search_rounds=60),
            stopping_policy=stop_policy(),
            trace_sink=InMemoryTraceSink(),
        )
    ranked = [
        f
        for f in result.fused_candidates
        if f.discoveries[0].mcu_id == "mcu_control"
        and f.discoveries[0].evidence_family.value == "SCHOLARLY"
    ]
    metrics = measure_known_item(
        case_id=case["case_id"],
        attack_type=case["attack_type"],
        ranked=ranked,
        expected_sources={(case["expected_provider"], case["expected_source"])},
        allowed_providers=frozenset(case["allowed_providers"]),
        k=case["k"],
    )
    return metrics, result


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["case_id"])
async def test_engine_recovers_disguised_known_items_with_observed_paths(case, tmp_path):
    metrics, result = await benchmark_case(case)
    assert metrics.recall_at_k == 1 and metrics.reciprocal_rank > 0
    assert case["expected_strategy"] in {p.strategy.value for p in metrics.recovery_paths}
    assert all(p.provider_name in case["allowed_providers"] for p in metrics.recovery_paths)
    assert result.request_events
    RunArtifactWriter(tmp_path).write_json("asm_benchmark", case["case_id"] + ".json", metrics)


def test_missed_item_reports_zero_and_invalid_k_rejected():
    metrics = measure_known_item(
        case_id="missing",
        attack_type="CANONICAL",
        ranked=[],
        expected_sources={("openalex", "W1")},
        allowed_providers=frozenset({"openalex"}),
        k=10,
    )
    assert metrics.recall_at_k == 0 and metrics.reciprocal_rank == 0 and not metrics.recovery_paths
    with pytest.raises(ValueError):
        measure_known_item(
            case_id="missing",
            attack_type="CANONICAL",
            ranked=[],
            expected_sources={("openalex", "W1")},
            allowed_providers=frozenset({"openalex"}),
            k=0,
        )
