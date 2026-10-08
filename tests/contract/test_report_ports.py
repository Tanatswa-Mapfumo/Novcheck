"""Shared stateless role operations over recorded provider responses."""

import pytest

from tests.unit.reporting.test_execution import model_case
from tests.unit.reporting.test_obligations import report_case as _report_case

report_case = _report_case


async def test_report_model_adapter_implements_all_six_stateless_operations(report_case):
    from novelty_harness.ports.reporting import ReportPorts
    from novelty_harness.reporting.claims import build_claim_extraction_context
    from novelty_harness.reporting.drafts import SectionDraftFragment
    from novelty_harness.reporting.plan import ReportPlanProposal, build_planner_context
    from novelty_harness.reporting.verification import (
        CompositionCheck,
        CompositionContext,
        build_claim_verification_context,
    )
    from novelty_harness.runtime.tracing.hashing import canonical_hash
    from tests.unit.reporting.test_verification import scripted_batch

    adapter, _, provider, compilation, section, extraction_context, plan = model_case(report_case)
    ports = ReportPorts(planner=adapter, writer=adapter, extractor=adapter, verifier=adapter)
    assert ports.writer is adapter
    provider.payloads["ReportPlanProposal"] = ReportPlanProposal(
        scope=plan.scope,
        compilation_id=plan.compilation_id,
        bundle_digest=plan.bundle_digest,
        questions=plan.questions,
    ).model_dump(mode="json")
    planner = build_planner_context(report_case.bundle, compilation)
    proposal = await adapter.plan(planner, compilation.options)
    draft = await adapter.write(section)
    extraction = await adapter.extract(build_claim_extraction_context(draft, section))
    verification_context = build_claim_verification_context(
        draft, extraction, report_case.bundle, plan
    )
    provider.payloads["ClaimVerificationBatch"] = scripted_batch(verification_context).model_dump(
        mode="json"
    )
    batch = await adapter.verify(verification_context)
    local = repair_context_for(section, draft, extraction)
    cluster = local.cluster
    fragment = SectionDraftFragment(
        scope=plan.scope,
        compilation_id=plan.compilation_id,
        question_id=2,
        cluster_origin_id="origin",
        replaced_block_ids=(draft.blocks[0].block_id,),
        blocks=draft.blocks,
    )
    provider.payloads["SectionDraftFragment"] = fragment.model_dump(mode="json")
    repaired = await adapter.repair(local)
    composition = CompositionContext(
        scope=plan.scope,
        compilation_id=plan.compilation_id,
        bundle_digest=plan.bundle_digest,
        drafts=(draft,),
        extractions=(extraction,),
        language_envelopes=section.language_envelopes,
        target_findings=section.target_findings,
        overall_finding=section.overall_finding,
        coverage_obligations=section.coverage_obligations,
        narrative_digest=canonical_hash(draft),
        claims_digest=canonical_hash(extraction.claims),
        permission_digest=canonical_hash(section.language_envelopes),
    )
    provider.payloads["CompositionCheck"] = CompositionCheck(
        scope=plan.scope,
        compilation_id=plan.compilation_id,
        narrative_digest=composition.narrative_digest,
        claims_digest=composition.claims_digest,
        permission_digest=composition.permission_digest,
        disposition="SUPPORTED",
        implicated_block_ids=(),
        implicated_question_ids=(),
        indeterminate_scope=False,
        reason_codes=(),
        reason="Recorded compatible composition",
    ).model_dump(mode="json")
    checked = await adapter.check_composition(composition)
    assert proposal.questions == plan.questions
    assert batch.accepted and checked.accepted
    assert repaired.cluster_origin_id == cluster.origin_id
    assert len(provider.calls) == 6
    assert len({e.role for e in adapter.executions}) == 6
    assert all(c[3].metadata["task_name"] == c[0] for c in provider.calls)
    assert all(
        c[2][0].trusted_instruction and all(not b.trusted_instruction for b in c[2][1:])
        for c in provider.calls
    )
    with pytest.raises(AttributeError):
        ports.writer = None


async def test_repair_schema_failure_has_no_recovery(report_case):
    from novelty_harness.application.phase8_model_adapter import ReportModelOutputError
    from novelty_harness.reporting.claims import ClaimExtractionProposal

    adapter, _, provider, _, section, extraction_context, _ = model_case(report_case)
    extraction = ClaimExtractionProposal.model_validate(
        provider.payloads["ClaimExtractionProposal"]
    )
    local = repair_context_for(section, extraction_context.draft, extraction)
    provider.payloads["SectionDraftFragment"] = {"invalid": True}
    with pytest.raises(ReportModelOutputError) as error:
        await adapter.repair(local)
    assert len(provider.calls) == 1
    assert len(error.value.executions) == 1
    assert not error.value.executions[0].recovery


def repair_context_for(section, draft, extraction):
    from novelty_harness.reporting.repair import LocalRepairContext, RepairCluster, RepairSpan

    cluster = RepairCluster(
        scope=section.scope,
        compilation_id=section.compilation_id,
        cluster_id="cluster",
        origin_id="origin",
        question_id=2,
        original_block_ids=(draft.blocks[0].block_id,),
        original_spans=(
            RepairSpan(block_id=draft.blocks[0].block_id, start=0, end=len(draft.blocks[0].text)),
        ),
        claim_ids=(extraction.claims[0].claim_id,),
        obligation_ids=draft.blocks[0].obligation_ids,
        reason_codes=("RECORDED_LOCAL_DEFECT",),
    )
    local = LocalRepairContext(
        scope=section.scope,
        compilation_id=section.compilation_id,
        section_context=section,
        cluster=cluster,
        original_blocks=draft.blocks,
        neighboring_blocks=(),
        relevant_basis_refs=section.selected_basis_refs,
        required_qualification_refs=(),
    )
    return local
