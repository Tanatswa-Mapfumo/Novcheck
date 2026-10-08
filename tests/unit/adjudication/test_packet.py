import pytest

from novelty_harness.adjudication.context import Phase7InputManifest
from novelty_harness.adjudication.packet import (
    build_adjudication_case,
    select_role_display,
    validate_decisive_basis,
)
from novelty_harness.evidence.graph.sqlalchemy_repository import SqlAlchemyEvidenceGraphRepository
from tests.fixtures.phase1 import make_fixture
from tests.integration.test_phase6_evidence_pipeline import graph_database, run_phase6_for_ledger


@pytest.mark.asyncio
async def test_packet_preserves_full_phase6_and_research_state(tmp_path) -> None:
    result, _, _, _, _ = await run_phase6_for_ledger(tmp_path)
    assert result.snapshot_id is not None
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    try:
        view = repository.load_phase6_assessment("asm_research", snapshot_id=result.snapshot_id)
        fixture = make_fixture()
        manifest = Phase7InputManifest(
            assessment_id="asm_research",
            phase6_snapshot_id=view.snapshot_id,
            as_of=view.as_of,
            cir=fixture.idea,
            sufficiency=fixture.sufficiency,
            mcu_graph=fixture.graph,
            unknown_upstream_artifacts=("phase3", "phase4"),
            query_history=("qry_historical",),
            providers_attempted=("recorded-provider",),
            stop_reason="BUDGET_STOPPED",
        )
        context = repository.seal_phase7_context(
            "asm_research", snapshot_id=view.snapshot_id, manifest=manifest
        )
        packet = build_adjudication_case(context, view)

        assert packet.case_id.startswith("p7case_")
        assert packet.phase6_view == view
        assert packet.manifest == manifest
        assert packet.comparisons == view.committed_comparisons
        assert packet.authorized_relations == view.authorized_graph_relations
        assert packet.candidate_outcomes == view.candidate_outcomes
        assert packet.target_profiles == view.targets
        assert packet.coverage == view.coverage
        assert packet.query_history == ("qry_historical",)
        assert packet.providers_attempted == ("recorded-provider",)
        assert packet.stop_reason == "BUDGET_STOPPED"
        assert packet.cited_passages
        assert all(comparison.cited_passages for comparison in packet.comparisons)
    finally:
        repository.close()


@pytest.mark.asyncio
async def test_display_omission_is_not_decisive_basis(tmp_path) -> None:
    result, _, _, _, _ = await run_phase6_for_ledger(tmp_path)
    assert result.snapshot_id is not None
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    try:
        view = repository.load_phase6_assessment("asm_research", snapshot_id=result.snapshot_id)
        fixture = make_fixture()
        context = repository.seal_phase7_context(
            "asm_research",
            snapshot_id=view.snapshot_id,
            manifest=Phase7InputManifest(
                assessment_id="asm_research",
                phase6_snapshot_id=view.snapshot_id,
                as_of=view.as_of,
                cir=fixture.idea,
                sufficiency=fixture.sufficiency,
                mcu_graph=fixture.graph,
                unknown_upstream_artifacts=("phase3", "phase4"),
            ),
        )
        packet = build_adjudication_case(context, view)
        target_id = view.committed_comparisons[0].comparison.comparison.chain.edge.mcu_id
        display = select_role_display(packet, target_id=target_id, max_chars=1)
        assert display.omitted_passage_ids
        assert display.omitted_material_ids
        with pytest.raises(ValueError, match="omitted"):
            validate_decisive_basis(display, passage_ids=(display.omitted_passage_ids[0],))
        with pytest.raises(ValueError, match="omitted"):
            validate_decisive_basis(display, material_ids=(display.omitted_material_ids[0],))
        complete = select_role_display(packet, target_id=target_id, max_chars=1_000_000)
        assert complete.displayed_passage_ids
        validate_decisive_basis(complete, passage_ids=(complete.displayed_passage_ids[0],))
    finally:
        repository.close()


@pytest.mark.asyncio
async def test_packet_rejects_missing_combination_member(tmp_path) -> None:
    result, _, _, _, _ = await run_phase6_for_ledger(tmp_path)
    assert result.snapshot_id is not None
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    try:
        view = repository.load_phase6_assessment("asm_research", snapshot_id=result.snapshot_id)
        fixture = make_fixture()
        combination = fixture.graph.combinations[0].model_copy(
            update={"member_ids": ("mcu_control", "mcu_missing")}
        )
        graph = fixture.graph.model_copy(update={"combinations": (combination,)})
        manifest = Phase7InputManifest(
            assessment_id="asm_research",
            phase6_snapshot_id=view.snapshot_id,
            as_of=view.as_of,
            cir=fixture.idea,
            sufficiency=fixture.sufficiency,
            mcu_graph=graph,
            unknown_upstream_artifacts=("phase3", "phase4"),
        )
        with pytest.raises(ValueError, match="Combination members are missing"):
            repository.seal_phase7_context(
                "asm_research", snapshot_id=view.snapshot_id, manifest=manifest
            )
    finally:
        repository.close()
