from datetime import date

import httpx

from novelty_harness.research.adaptive.controller import AdaptiveController
from novelty_harness.research.adaptive.escalation import multilingual_hook
from novelty_harness.research.adaptive.stopping import assess_stop
from novelty_harness.research.expansion.chronology import assess_temporal, capture_chronology
from novelty_harness.research.fusion.clustering import cluster_candidates, rekey_lists
from novelty_harness.research.fusion.rrf import reciprocal_rank_fusion
from novelty_harness.runtime.config.models import BudgetLimits
from tests.benchmarks.test_known_item_retrieval import benchmark_case
from tests.fixtures.known_items import CASES, recording
from tests.fixtures.phase4 import registry, wire
from tests.integration.test_phase4_retrieval_pipeline import run
from tests.unit.research.adaptive.test_controller import action, branch
from tests.unit.research.adaptive.test_stopping import policy, signals, stable
from tests.unit.research.fusion.test_clustering import record
from tests.unit.research.retrieval.test_models import candidate
from tests.unit.research.test_coverage_floor import prepared


async def test_01_missing_exact_terms_recovers_semantically():
    m, _ = await benchmark_case(CASES[1])
    assert m.recall_at_k == 1 and {p.strategy.value for p in m.recovery_paths} == {"SEMANTIC"}


async def test_02_semantic_miss_recovered_by_lexical_historical_terms():
    requests = []

    def respond(request):
        requests.append(request)
        if request.url.host == "api.openalex.org" and "thermostatic" in str(
            request.url.params.get("search", "")
        ):
            return wire(request)
        return (
            recording(CASES[1])(request)
            if request.url.host != "api.openalex.org"
            else httpx.Response(200, json={"results": [], "meta": {"next_cursor": None}})
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result, _, _ = await run(client)
    assert any(b.strategy.value == "HISTORICAL_TERM" and b.candidates for b in result.batches)
    assert not any(b.strategy.value == "SEMANTIC" and b.candidates for b in result.batches)


def test_03_many_paraphrases_do_not_manufacture_independent_mechanisms():
    result = assess_stop(
        stable(),
        signals(
            successful_strategies=["LEXICAL", "RELATIONAL", "HISTORICAL_TERM", "ADJACENT_DOMAIN"]
        ),
        policy(),
    )
    assert result.reason.value == "CONTINUE" and result.signals["mechanism_diversity"] is False


def test_04_empty_one_path_with_close_other_path_keeps_escalating():
    state = type(branch()).model_validate(
        {**branch().model_dump(), "relevant_candidate_count": 1, "new_candidate_yield": [0, 1]}
    )
    assert (
        AdaptiveController()
        .next_action(state, [action("CITATION_BACKWARD", kind="EXPAND")])
        .action_type
        == "EXPAND"
    )


async def test_05_later_work_predecessor_recovered_and_dated_independently():
    m, result = await benchmark_case(CASES[3])
    assert "CITATION_BACKWARD" in {p.strategy.value for p in m.recovery_paths}
    assert any(c.publication_date == date(1990, 1, 1) for c in result.chronology.values())
    assert any(c.publication_date == date(2020, 1, 1) for c in result.chronology.values())


def test_06_post_cutoff_context_is_not_historical_negation():
    chronology = capture_chronology(candidate(raw_metadata={"publication_date": "2026-01-01"}))
    assert assess_temporal(chronology, as_of=date(2000, 1, 1)).predates_cutoff is False


def test_07_duplicate_provider_observations_collapse_candidate_not_paths():
    a = candidate()
    b = a.model_copy(update={"query_id": "qry_another"})
    clusters = cluster_candidates([a, b])
    assert len(clusters) == 1 and len(clusters[0].discoveries) == 2


def test_08_similar_titles_distinct_works_remain_separate():
    assert len(cluster_candidates([record("openalex", "W1"), record("crossref", "work2")])) == 2


def test_09_score_scale_metamorphism_leaves_fused_order_and_score_unchanged():
    lists = {"a": [record("openalex", "W1", local_rank=1), record("openalex", "W2", local_rank=2)]}
    altered = {
        name: [c.model_copy(update={"provider_score": c.local_rank * 1000000.0}) for c in rows]
        for name, rows in lists.items()
    }
    a = reciprocal_rank_fusion(lists)
    b = reciprocal_rank_fusion(altered)
    assert [(f.candidate_key, f.rrf_score) for f in a] == [
        (f.candidate_key, f.rrf_score) for f in b
    ]


async def test_10_citation_explosion_obeys_hard_wire_budget():
    requests = []

    def respond(request):
        requests.append(request)
        data = wire(request).json()
        if request.url.path.startswith("/works/W"):
            data["referenced_works"] = [
                "https://openalex.org/W" + str(i) for i in range(1000, 3000)
            ]
        return httpx.Response(200, json=data)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result, runtime, _ = await run(client, limits=BudgetLimits(max_provider_calls=85))
    assert len(requests) == len(runtime.attempts) == result.budget_usage.provider_calls <= 85
    assert any(s.reason.value == "BUDGET_STOPPED" for s in result.stop_assessments)


def test_11_blocked_provider_prevents_false_saturation():
    assert (
        assess_stop(stable(access_failures=["Provider blocked"]), signals(), policy()).reason.value
        == "ACCESS_BLOCKED"
    )


def test_12_budget_exhaustion_never_serializes_as_saturation():
    result = assess_stop(stable(budget_stopped=True), signals(), policy())
    assert result.reason.value == "BUDGET_STOPPED" and "SATURATED" not in result.model_dump_json()


def test_13_sparse_branch_gets_more_falsification_effort():
    result = AdaptiveController().next_action(branch(), [action("LEXICAL", kind="PAGE"), action()])
    assert result.strategy.value == "SEMANTIC"


def test_14_growing_citation_neighborhood_prevents_saturation():
    assert (
        assess_stop(stable(), signals(citation_yield=[1, 2]), policy()).reason.value == "CONTINUE"
    )


def test_15_multiple_discovery_routes_survive_cluster_and_fusion():
    a = candidate()
    b = candidate(strategy="CITATION_BACKWARD", query_id=None, seed_source=a.source)
    lists = {"text": [a], "backward": [b]}
    result = reciprocal_rank_fusion(rekey_lists(lists, cluster_candidates([a, b])))
    assert len(result) == 1 and {c.strategy.value for c in result[0].discoveries} == {
        "LEXICAL",
        "CITATION_BACKWARD",
    }


async def test_16_empty_field_is_explicit_escalation_not_novelty():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(recording({"case_id": "empty"}))
    ) as client:
        result, _, sink = await run(client)
    assert not result.fused_candidates
    assert any(b.strategy.value == "SEMANTIC" for b in result.batches)
    assert not any(s.reason.value == "SATURATED" for s in result.stop_assessments)
    assert any(e.reason_code == "RESEARCH_ACTION" for e in sink.events)


async def test_17_mature_field_deepens_pagination_without_exhaustiveness_claim():
    pages = []

    def respond(request):
        data = wire(request).json()
        if (
            request.url.host == "api.openalex.org"
            and request.url.path == "/works"
            and "search" in request.url.params
        ):
            cursor = request.url.params.get("cursor", "*")
            pages.append(cursor)
            data["meta"]["next_cursor"] = "next" if cursor == "*" else None
            if cursor == "next":
                data["results"][0].update(
                    id="https://openalex.org/W888", doi="https://doi.org/10.1234/page2"
                )
        return httpx.Response(200, json=data)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result, _, _ = await run(client)
    assert "next" in pages and any(c.cursor == "next" for b in result.batches for c in b.candidates)
    assert "verified relevant evidence" in " ".join(result.limitations)


def test_18_unavailable_multilingual_hook_is_not_silent_coverage():
    assert multilingual_hook(branch(), supported=False).action_type == "MULTILINGUAL_UNAVAILABLE"


async def test_partial_crossref_wire_dates_never_become_invented_january_first():
    def respond(request):
        data = wire(request).json()
        data["message"]["items"][0]["published"]["date-parts"] = [[1999]]
        return httpx.Response(200, json=data)

    plan = await prepared()
    intent = next(q for q in plan.intents if q.evidence_family.value == "SCHOLARLY")
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        providers, _ = registry(client)
        provider = providers.get("crossref").provider
        batch = await provider.retrieve(intent=intent, strategy="LEXICAL", as_of=plan.as_of)
    chronology = capture_chronology(batch.candidates[0])
    assert chronology.publication_date is None
    assert assess_temporal(chronology, as_of=date(2020, 1, 1)).predates_cutoff is None
