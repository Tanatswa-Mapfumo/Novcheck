from novelty_harness.application import ports
from novelty_harness.domain.enums import SufficiencyState, SupportVerificationState
from novelty_harness.ports.content import ContentResolver
from novelty_harness.ports.search import SearchProvider
from tests.fixtures.phase1 import make_fixture


def test_fixture_components_conform_to_all_application_and_provider_protocols():
    scenario = make_fixture()
    for field, protocol in [
        ("normalizer", ports.IdeaNormalizer),
        ("sufficiency_analyzer", ports.SufficiencyAnalyzer),
        ("decomposer", ports.MCUDecomposer),
        ("reconciler", ports.MCUReconciler),
        ("planner", ports.SearchPlanner),
        ("plan_reviewer", ports.SearchPlanReviewer),
        ("mapper", ports.EvidenceMapper),
        ("verifier", ports.EvidenceVerifier),
        ("adjudicator", ports.AdjudicationEngine),
    ]:
        component = getattr(scenario.components, field)
        assert isinstance(component, protocol)
        assert type(component).__name__.startswith("Fixture")
    assert isinstance(scenario.search_provider, SearchProvider)
    assert isinstance(scenario.content_resolver, ContentResolver)


async def test_fixture_outputs_are_repeated_deterministically_without_network():
    scenario = make_fixture()
    other = make_fixture()
    assert scenario.request == other.request
    assert scenario.clock() == other.clock()
    components = scenario.components
    for _ in range(2):
        idea = await components.normalizer.normalize(scenario.request)
        assert idea == scenario.idea
        assert idea.original_input == scenario.request.input_text
        sufficiency = await components.sufficiency_analyzer.analyze(idea)
        assert sufficiency.state == SufficiencyState.ASSESSABLE
        mcus = await components.decomposer.decompose(idea)
        assert len(mcus) >= 2
        graph = await components.reconciler.reconcile(idea, mcus)
        assert graph == scenario.graph
        plan = await components.planner.plan(idea, graph)
        review = await components.plan_reviewer.review(plan)
        assert review.approved
        page = await scenario.search_provider.search(scenario.search_query)
        assert len(page.results) == 1
        content = await scenario.content_resolver.resolve(page.results[0].source)
        passage = await scenario.content_resolver.resolve_passage(
            content.source, "resolved_content"
        )
        assert passage.text == content.text
        edges = await components.mapper.map(mcus, scenario.sources, scenario.passages)
        verified = await components.verifier.verify(
            edges[0], mcus, scenario.sources, scenario.passages
        )
        assert verified.support_verification == SupportVerificationState.SUPPORTED
        frozen = await components.adjudicator.adjudicate(
            assessment_id="asm_run",
            as_of=scenario.request.as_of,
            idea=idea,
            sufficiency=sufficiency,
            mcus=mcus,
            edges=(verified,),
        )
        assert frozen.assessment_id == "asm_run"
        assert frozen.provenance.kind == "fixture"
        assert frozen == scenario.adjudication.model_copy(update={"assessment_id": "asm_run"})


async def test_fixture_normalizer_rejects_unconfigured_requests():
    import pytest

    scenario = make_fixture()
    request = scenario.request.model_copy(update={"input_text": "Unconfigured input"})
    with pytest.raises(ValueError, match="configured fixture"):
        await scenario.components.normalizer.normalize(request)
