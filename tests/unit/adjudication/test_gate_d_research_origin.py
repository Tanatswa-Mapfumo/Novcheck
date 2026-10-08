"""External research cannot establish the meaning of a claimed contribution."""

import asyncio
from dataclasses import replace

import pytest

from novelty_harness.adjudication.needs import ResearchGapRequest, validate_research_gap_request
from novelty_harness.application.phase7 import run_phase7
from novelty_harness.domain.enums import VerdictState
from novelty_harness.evidence.graph.sqlalchemy_repository import SqlAlchemyEvidenceGraphRepository
from tests.integration.test_phase6_evidence_pipeline import graph_database
from tests.integration.test_phase7_slice import _real_ports
from tests.unit.adjudication.test_roles import build_packet, scope


def disguised_gap(packet, target_id="mcu_control"):
    comparison = packet.comparisons[0].comparison.comparison
    return ResearchGapRequest(
        **scope(packet, target_id),
        request_id="p7gap_disguised_input",
        requesting_stage="FIRST_PASS",
        material_gate="D",
        gap_type="ACCESS",
        missing_prior_art_reference=str(comparison.source_version_id),
        reason="The user's mechanism is unspecified",
        research_hypothesis="Search implementations to infer the user's control mechanism",
        stop_condition="Recover the missing meaning from prior art",
    )


@pytest.fixture(scope="module")
def packet(tmp_path_factory):
    return build_packet(tmp_path_factory.mktemp("gate_d_origin"))


def test_gate_d_research_requires_typed_external_fact_basis(packet):
    with pytest.raises(ValueError, match="external.*basis"):
        validate_research_gap_request(disguised_gap(packet), packet)


def test_gate_d_research_requires_gate_a_comparable_target(packet):
    with pytest.raises(ValueError, match="Gate A|comparable"):
        validate_research_gap_request(disguised_gap(packet, "mcu_status"), packet)


def test_gate_d_research_cannot_infer_missing_user_mechanism(tmp_path):
    packet = build_packet(tmp_path)
    repository = SqlAlchemyEvidenceGraphRepository(graph_database(tmp_path))
    ports = _real_ports(packet)
    inner = ports.prosecutor
    gap = disguised_gap(packet)

    class Role:
        async def propose(self, given):
            case = await inner.propose(given)
            if case.target_id == gap.target_id:
                return case.model_copy(
                    update={"research_gaps": (gap,), "research_gap_ids": (gap.request_id,)}
                )
            return case

    class Research:
        calls = 0

        async def execute(self, request, context):
            self.calls += 1
            from novelty_harness.adjudication.needs import ResearchEscalationOutcome
            from novelty_harness.runtime.budgets.controller import BudgetUsage

            return ResearchEscalationOutcome(
                request_id=request.request_id,
                assessment_id=context.assessment_id,
                assessment_context_id=context.context_id,
                phase6_snapshot_id=context.snapshot_id,
                updated_snapshot_id=context.snapshot_id,
                updated_manifest=context.manifest,
                budget_usage=context.manifest.budget_usage,
                cost=BudgetUsage(),
                stop_reason=context.manifest.stop_reason,
            )

    research = Research()
    try:
        frozen = asyncio.run(
            run_phase7(
                packet.assessment_id,
                context_id=packet.assessment_context_id,
                repository=repository,
                ports=replace(ports, prosecutor=Role(), research_escalation=research),
            )
        )
        assert research.calls == 0
        assert frozen.input_need_ids
        assert (
            next(t for t in frozen.target_findings if t.target_id == gap.target_id).verdict
            == VerdictState.UNASSESSABLE
        )
        assert (
            repository.load_frozen_adjudication(
                packet.assessment_id, adjudication_id=frozen.adjudication_id
            )
            == frozen
        )
    finally:
        repository.close()


def test_disguised_input_gap_routes_to_input_clarification(packet):
    from novelty_harness.adjudication.needs import clarify_unproved_gate_d
    from tests.unit.adjudication.test_roles import valid_case

    gap = disguised_gap(packet)
    case = valid_case(packet).model_copy(
        update={"research_gaps": (gap,), "research_gap_ids": (gap.request_id,)}
    )
    clarified = clarify_unproved_gate_d(case, packet)
    assert not clarified.research_gaps
    assert clarified.input_needs[0].material_gate == "A"
    assert clarified.input_needs[0].reason == gap.reason


@pytest.mark.parametrize(
    "meaning", ["relationship direction", "control flow", "combination topology"]
)
def test_missing_structure_cannot_be_disguised_by_access_wording(packet, meaning):
    from novelty_harness.adjudication.needs import classify_gap_origin

    gap = disguised_gap(packet).model_copy(
        update={
            "reason": "Resolve closest historical " + meaning,
            "research_hypothesis": "Retrieve accessible prior art",
        }
    )
    assert classify_gap_origin(gap, packet) == "INPUT_MEANING_GAP"


def test_specified_target_and_unassessed_source_permit_gate_d_research(packet):
    from novelty_harness.adjudication.context import SealedAssessmentContext
    from novelty_harness.adjudication.gates import evaluate_gate_d, gate_d_research_gap
    from novelty_harness.adjudication.models import TargetRef
    from novelty_harness.adjudication.needs import GapEscalationPolicy, ResearchEscalationBudget
    from novelty_harness.runtime.budgets.controller import BudgetUsage
    from novelty_harness.runtime.config.models import BudgetLimits
    from tests.unit.adjudication.test_gates import _packet_with_comparisons

    local = _packet_with_comparisons(packet, kept_relations=frozenset())
    target = TargetRef(kind="MCU", id="mcu_control")
    gap = gate_d_research_gap(local, target, evaluate_gate_d(local, target, None, None))
    assert gap is not None
    assert validate_research_gap_request(gap, local) == gap
    context = SealedAssessmentContext(
        context_id=local.assessment_context_id,
        assessment_id=local.assessment_id,
        snapshot_id=local.phase6_snapshot_id,
        phase6_view_digest=local.phase6_view_digest,
        manifest_id=local.manifest_id,
        manifest_digest=local.manifest_digest,
        manifest=local.manifest,
    )
    budget = ResearchEscalationBudget(
        limits=BudgetLimits(max_provider_calls=1), usage=BudgetUsage(), max_requests=1
    )
    assert GapEscalationPolicy().decide(gap, context, budget, packet=local).status == "ACCEPT"
    forged = gap.model_copy(
        update={
            "missing_prior_art_reference": gap.external_fact_basis.source_version_id
            or "src_foreign",
            "external_fact_basis": gap.external_fact_basis.model_copy(
                update={"source_id": "src_foreign"}
            ),
        }
    )
    with pytest.raises(ValueError, match="unassessed"):
        validate_research_gap_request(forged, local)
    missing = gap.model_copy(update={"target_id": "mcu_status"})
    with pytest.raises(ValueError, match="Gate A"):
        validate_research_gap_request(missing, local)


def test_persisted_misrouted_gate_d_gap_cannot_freeze_negative(tmp_path):
    from sqlalchemy.orm import Session

    from novelty_harness.adjudication.frozen import phase7_frozen_id
    from novelty_harness.application.phase7_roles import make_phase7_artifact
    from novelty_harness.evidence.graph.phase7_models import Phase7ArtifactRow
    from novelty_harness.runtime.tracing.hashing import canonical_json
    from tests.unit.evidence.graph.test_phase7_store import _freeze_fixture

    packet, repository, run, proposed = _freeze_fixture(tmp_path)
    gap = disguised_gap(packet)
    artifact = make_phase7_artifact(run.run_id, "RESEARCH_GAP", gap)
    try:
        # Bypass dispatch with a canonical, correctly scoped artifact.
        with Session(repository.engine) as session, session.begin():
            session.add(
                Phase7ArtifactRow(
                    artifact_id=artifact.artifact_id,
                    run_id=run.run_id,
                    context_id=run.assessment_context_id,
                    assessment_id=run.assessment_id,
                    snapshot_id=run.phase6_snapshot_id,
                    kind=artifact.kind,
                    target_id=artifact.target_id,
                    document_json=canonical_json(artifact),
                )
            )
        proposed = proposed.model_copy(
            update={
                "dependency_ids": tuple(sorted((*proposed.dependency_ids, artifact.artifact_id))),
                "research_gap_ids": (gap.request_id,),
            }
        )
        proposed = proposed.model_copy(update={"adjudication_id": phase7_frozen_id(proposed)})
        with pytest.raises(ValueError, match="external.*basis"):
            repository.freeze_phase7_adjudication(run.run_id, proposed)
    finally:
        repository.close()


def test_verified_external_contradiction_can_request_gate_d_research(tmp_path):
    from novelty_harness.adjudication.needs import GateDExternalEvidenceBasis
    from novelty_harness.runtime.tracing.hashing import canonical_hash
    from tests.unit.adjudication.test_gates import _matrix_packet

    local = _matrix_packet(tmp_path, "CONTRADICTS")
    item = local.comparisons[0].comparison
    assert item.classification.contradictions
    profile = local.target_profiles[0]
    comparison_id = str(item.classification.classification_id)
    reference = item.comparison.source_version_id
    basis = GateDExternalEvidenceBasis(
        **scope(local, profile.target_id),
        target_profile_digest=canonical_hash(profile),
        contribution=profile.statement,
        source_id=str(item.comparison.source_id),
        source_version_id=reference,
        comparison_ids=(comparison_id,),
        missing_external_fact_type="SOURCE_CONTRADICTION",
        contradiction=item.classification.contradictions[0],
    )
    gap = ResearchGapRequest(
        **scope(local, profile.target_id),
        request_id="p7gap_contradiction",
        requesting_stage="ADJUDICATION",
        gap_type="CONTRADICTORY_EVIDENCE",
        material_gate="D",
        reason="Resolve the conflicting source implementation",
        research_hypothesis="Another source passage may resolve the verified contradiction",
        linked_comparison_ids=(comparison_id,),
        missing_prior_art_reference=reference,
        external_fact_basis=basis,
        stop_condition="Resolve the source contradiction or retain it as unresolved",
    )
    assert validate_research_gap_request(gap, local) == gap
    invented = gap.model_copy(
        update={
            "external_fact_basis": basis.model_copy(
                update={"contradiction": "invented source conflict"}
            )
        }
    )
    with pytest.raises(ValueError, match="contradiction"):
        validate_research_gap_request(invented, local)


def test_known_external_chronology_gap_remains_research(packet):
    from novelty_harness.adjudication.needs import GateDExternalEvidenceBasis
    from novelty_harness.runtime.tracing.hashing import canonical_hash

    item = next(
        i.comparison
        for i in packet.comparisons
        if i.comparison.comparison.chain.edge.chronology.state == "UNCERTAIN"
    )
    profile = next(p for p in packet.target_profiles if p.target_id == item.classification.mcu_id)
    comparison_id = str(item.classification.classification_id)
    reference = item.comparison.source_version_id or item.comparison.source_id
    basis = GateDExternalEvidenceBasis(
        **scope(packet, profile.target_id),
        target_profile_digest=canonical_hash(profile),
        contribution=profile.statement,
        source_id=str(item.comparison.source_id),
        source_version_id=item.comparison.source_version_id,
        comparison_ids=(comparison_id,),
        missing_external_fact_type="SOURCE_CHRONOLOGY",
    )
    request = disguised_gap(packet, profile.target_id).model_copy(
        update={
            "gap_type": "CHRONOLOGY",
            "external_fact_basis": basis,
            "missing_prior_art_reference": reference,
            "linked_comparison_ids": (comparison_id,),
            "reason": "Closest source has unresolved chronology",
            "research_hypothesis": "Resolve the external publication date",
        }
    )
    assert validate_research_gap_request(request, packet) == request
    gate_c = request.model_copy(update={"material_gate": "C", "external_fact_basis": None})
    assert validate_research_gap_request(gate_c, packet) == gate_c


def test_research_continuation_revalidates_persisted_gate_d_origin(tmp_path):
    from sqlalchemy.orm import Session

    from novelty_harness.adjudication.models import Phase7RunState
    from novelty_harness.adjudication.needs import ResearchEscalationOutcome
    from novelty_harness.application.phase7_roles import make_phase7_artifact
    from novelty_harness.evidence.graph.phase7_models import Phase7ArtifactRow
    from novelty_harness.runtime.budgets.controller import BudgetUsage
    from novelty_harness.runtime.tracing.hashing import canonical_json
    from tests.unit.adjudication.test_roles import _committed_dispute_run

    packet, repository, run, _, _, _ = _committed_dispute_run(tmp_path)
    context = repository.load_phase7_context(
        packet.assessment_id, context_id=packet.assessment_context_id
    )
    gap = disguised_gap(packet)
    artifact = make_phase7_artifact(run.run_id, "RESEARCH_GAP", gap)
    try:
        with Session(repository.engine) as session, session.begin():
            session.add(
                Phase7ArtifactRow(
                    artifact_id=artifact.artifact_id,
                    run_id=run.run_id,
                    context_id=run.assessment_context_id,
                    assessment_id=run.assessment_id,
                    snapshot_id=run.phase6_snapshot_id,
                    kind=artifact.kind,
                    target_id=artifact.target_id,
                    document_json=canonical_json(artifact),
                )
            )
        repository.transition_phase7_run(
            run.run_id,
            expected_state=Phase7RunState.FIRST_PASSES_COMPLETE,
            next_state=Phase7RunState.ESCALATION_PENDING,
        )
        outcome = ResearchEscalationOutcome(
            request_id=gap.request_id,
            assessment_id=context.assessment_id,
            assessment_context_id=context.context_id,
            phase6_snapshot_id=context.snapshot_id,
            updated_snapshot_id=context.snapshot_id,
            updated_manifest=context.manifest,
            budget_usage=context.manifest.budget_usage,
            cost=BudgetUsage(),
            stop_reason=context.manifest.stop_reason,
        )
        with pytest.raises(ValueError, match="ACCEPT|external.*basis"):
            repository.complete_phase7_research(run.run_id, outcome)
        assert repository.load_phase7_run(run.run_id).state == Phase7RunState.ESCALATION_PENDING
    finally:
        repository.close()


def test_role_display_provides_bound_gate_d_research_basis(packet):
    import json

    from novelty_harness.application.phase7_model_adapter import _packet_block

    display = json.loads(_packet_block(packet).text)
    assert display["case_id"] == packet.case_id
    assert display["gate_d_external_fact_bases"]
    assert all(b["target_id"] == "mcu_control" for b in display["gate_d_external_fact_bases"])
    assert any(
        b["missing_external_fact_type"] == "SOURCE_CHRONOLOGY"
        for b in display["gate_d_external_fact_bases"]
    )
