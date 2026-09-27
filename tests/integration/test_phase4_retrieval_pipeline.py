import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from novelty_harness.ports.models import SourceRef
from novelty_harness.research.adaptive.pipeline import BudgetExhausted, run_adaptive_research
from novelty_harness.research.coverage import CoveragePolicy
from novelty_harness.runtime.artifacts.writer import RunArtifactWriter
from novelty_harness.runtime.budgets.controller import BudgetController
from novelty_harness.runtime.config.models import BudgetLimits
from novelty_harness.runtime.tracing.sinks import InMemoryTraceSink
from tests.fixtures.phase1 import make_fixture
from tests.fixtures.phase4 import assessment, registry, stop_policy, wire
from tests.unit.research.test_coverage_floor import prepared


async def run(client, *, limits=None, writer=None, **kwargs):
    providers, runtime = registry(client, **kwargs)
    sink = InMemoryTraceSink()
    result = await run_adaptive_research(
        assessment=assessment(),
        mcus=make_fixture().graph.mcus,
        reviewed_plan=await prepared(),
        provider_registry=providers,
        coverage_policy=CoveragePolicy.standard(),
        budget_controller=BudgetController(),
        budget_limits=limits or BudgetLimits(max_deep_search_rounds=80),
        stopping_policy=stop_policy(),
        trace_sink=sink,
        artifact_writer=writer,
        clock=runtime.clock,
    )
    return result, runtime, sink


async def test_pipeline_real_native_paths_fusion_chronology_coverage_and_artifacts(tmp_path):
    async with httpx.AsyncClient(transport=httpx.MockTransport(wire)) as client:
        result, runtime, sink = await run(client, writer=RunArtifactWriter(tmp_path))
    strategies = {b.strategy.value for b in result.batches}
    assert {
        "LEXICAL",
        "SEMANTIC",
        "RELATIONAL",
        "HISTORICAL_TERM",
        "ADJACENT_DOMAIN",
        "CITATION_BACKWARD",
        "CITATION_FORWARD",
        "RELATED_WORK",
        "ENTITY_LINEAGE",
    } <= strategies
    assert result.fused_candidates and result.expansion_events
    assert len(runtime.attempts) == result.budget_usage.provider_calls
    assert any(t.predates_cutoff is True for t in result.temporal_assessments.values())
    patent = [c for c in result.coverage_matrix if c.screening.evidence_family.value == "PATENT"]
    assert all(
        c.stop.reason.value == "ACCESS_BLOCKED" and c.depth.value == "ACCESS_BLOCKED"
        for c in patent
    )
    names = {p.name for p in (tmp_path / "asm_research" / "phase4").iterdir()}
    assert {
        "retrieval_batches.jsonl",
        "fused_candidates.jsonl",
        "expansion_events.jsonl",
        "chronology.json",
        "branch_states.jsonl",
        "stop_assessments.jsonl",
        "coverage_matrix.json",
        "request_events.jsonl",
        "research_result.json",
    } <= names
    assert any(e.reason_code == "RESEARCH_STOP" for e in sink.events)
    assert any(e.reason_code == "CANDIDATE_FUSION" for e in sink.events)
    assert any(e.reason_code == "CANDIDATE_CHRONOLOGY" for e in sink.events)
    stored = json.loads((tmp_path / "asm_research" / "phase4" / "research_result.json").read_text())
    assert stored["contract_kind"] == "adaptive-research-v1"


async def test_physical_retries_are_budgeted_and_partial_expansion_cannot_overshoot():
    count = 0

    def fail(request):
        nonlocal count
        count += 1
        return httpx.Response(503, json={})

    async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as client:
        result, runtime, _ = await run(client, limits=BudgetLimits(max_provider_calls=2), retries=3)
    assert count == len(runtime.attempts) == result.budget_usage.provider_calls == 2
    assert any(s.reason.value == "BUDGET_STOPPED" for s in result.stop_assessments)
    assert not any(s.reason.value == "SATURATED" for s in result.stop_assessments)
    assert result.request_events and result.request_events[0].attempts


async def test_pacing_elapsed_limit_checked_before_wire_attempt():
    now = datetime(2026, 9, 27, tzinfo=UTC)

    async def sleep(seconds):
        nonlocal now
        now += timedelta(seconds=seconds)

    async with httpx.AsyncClient(transport=httpx.MockTransport(wire)) as client:
        result, runtime, _ = await run(
            client, limits=BudgetLimits(max_elapsed_seconds=0.01), clock=lambda: now, sleeper=sleep
        )
    assert len(runtime.attempts) < 72
    assert any(s.reason.value == "BUDGET_STOPPED" for s in result.stop_assessments)


async def test_changed_plan_is_rejected_before_any_network_or_artifact():
    plan = await prepared()
    plan.intents[0].filters["language"] = "zz"
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: pytest.fail("must not request"))
    ) as client:
        providers, _ = registry(client)
        with pytest.raises(ValueError):
            await run_adaptive_research(
                assessment=assessment(),
                mcus=make_fixture().graph.mcus,
                reviewed_plan=plan,
                provider_registry=providers,
                coverage_policy=CoveragePolicy.standard(),
                budget_controller=BudgetController(),
                budget_limits=BudgetLimits(),
                stopping_policy=stop_policy(),
                trace_sink=InMemoryTraceSink(),
            )


async def test_partial_seed_lookup_records_budget_stopped_hydration_request():
    count = 0

    def guard():
        nonlocal count
        if count == 1:
            raise BudgetExhausted("Budget prevents hydration")
        count += 1

    async with httpx.AsyncClient(transport=httpx.MockTransport(wire)) as client:
        providers, runtime = registry(client)
        provider = providers.get("openalex").provider
        provider.set_request_guard(guard)
        with pytest.raises(BudgetExhausted):
            await provider.expand(
                source=SourceRef(provider_name="openalex", provider_source_id="W123"),
                strategy="CITATION_BACKWARD",
                as_of=assessment().request.as_of,
                mcu_id="mcu_control",
            )
    assert len(runtime.attempts) == 1
    events = provider.retrieval_request_events()
    assert len(events) == 2 and events[0].call.status.value == "SUCCESS"
    assert events[1].failure_code == "BUDGET_STOPPED"


async def test_document_limit_is_compiled_as_actual_page_size_and_stops_followups():
    requests = []

    def respond(request):
        requests.append(request)
        return wire(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result, _, _ = await run(client, limits=BudgetLimits(max_retrieved_documents=1))
    assert len(requests) == 1 and requests[0].url.params["per_page"] == "1"
    assert result.request_events[0].compiled_query.params["per_page"] == 1
    assert result.budget_usage.retrieved_documents == 1
    assert any(s.reason.value == "BUDGET_STOPPED" for s in result.stop_assessments)
