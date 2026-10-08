"""Writer inputs retain admitted meaning; draft annotations confer no support."""

import pytest
from pydantic import ValidationError

from novelty_harness.reporting.models import ReportLens, ReportOptions, ReportProposalError
from tests.unit.reporting.test_obligations import report_case as _report_case
from tests.unit.reporting.test_plan import compilation as _compilation

report_case = _report_case
compilation = _compilation


def context_for(bundle, compilation, question_id=2):
    from novelty_harness.reporting.drafts import build_section_context
    from novelty_harness.reporting.plan import build_coverage_plan

    return build_section_context(
        bundle,
        build_coverage_plan(bundle, compilation),
        question_id=question_id,
        compilation=compilation,
    )


def draft_for(context, blocks=None):
    from novelty_harness.reporting.drafts import DraftBlock, SectionDraft

    return SectionDraft(
        scope=context.scope,
        compilation_id=context.compilation_id,
        question_id=context.question_id,
        blocks=blocks
        or (DraftBlock(block_id="paragraph", kind="PARAGRAPH", text="Retained facts"),),
    )


def test_writer_context_retains_complete_residual_and_global_scope(report_case, compilation):
    from novelty_harness.reporting.drafts import build_section_context
    from novelty_harness.reporting.plan import build_coverage_plan

    bundle = report_case.bundle
    plan = build_coverage_plan(bundle, compilation)
    for question_id in range(1, 10):
        context = build_section_context(
            bundle,
            plan,
            question_id=question_id,
            compilation=compilation,
        )
        assert context.scope == bundle.scope
        assert context.plan_id == plan.plan_id
        assert context.question_plan == plan.questions[question_id - 1]
        assert context.language_envelopes == bundle.language_envelopes
        assert context.target_findings == bundle.target_findings
        assert context.overall_finding == bundle.overall_finding
        assert context.authority.comparisons == bundle.eligible_comparisons
        assert context.authority.graph == bundle.graph_or_version
        assert context.authority.target_profiles == bundle.target_profiles
        assert context.authority.source_metadata == bundle.source_metadata
        assert context.authority.cited_passages == bundle.cited_passages
        assert context.authority.authorized_relations == bundle.authorized_relations
        assert context.authority.counterfactuals == bundle.counterfactuals
        for actual, original in zip(
            context.authority.comparisons, bundle.eligible_comparisons, strict=True
        ):
            assert actual.comparison.classification == original.comparison.classification
            assert (
                actual.comparison.comparison.chain.verification
                == original.comparison.comparison.chain.verification
            )
            assert (
                actual.comparison.comparison.chain.edge.chronology
                == original.comparison.comparison.chain.edge.chronology
            )
            assert (
                actual.comparison.comparison.chain.mapping
                == original.comparison.comparison.chain.mapping
            )
        selected = set(context.selected_basis_refs)
        assert set(context.question_plan.required_limitation_refs) <= selected
        assert all(set(o.authority_refs) <= selected for o in context.coverage_obligations)
        assert not hasattr(context, "repository")
        assert not hasattr(context, "search")


def test_context_limit_requires_fallback_instead_of_decisive_omission(report_case, compilation):
    limits = compilation.options.limits.model_copy(update={"max_context_chars": 1})
    bounded = compilation.model_copy(
        update={"options": compilation.options.model_copy(update={"limits": limits})}
    )
    context = context_for(report_case.bundle, bounded)
    assert context.requires_fallback
    assert context.display_chars > context.limits.max_context_chars
    assert set(context.omission_manifest.authority_refs) == set(context.selected_basis_refs)
    assert set(context.omission_manifest.obligation_ids) == {
        o.obligation_id for o in context.coverage_obligations
    }
    assert context.authority.comparisons == report_case.bundle.eligible_comparisons
    from novelty_harness.reporting.drafts import validate_section_draft

    with pytest.raises(ReportProposalError):
        validate_section_draft(draft_for(context), context)


def test_lenses_change_presentation_only(report_case, compilation):
    from novelty_harness.reporting.drafts import lens_instruction

    contexts = []
    for lens in ReportLens:
        changed = compilation.model_copy(update={"options": ReportOptions(lens=lens)})
        context = context_for(report_case.bundle, changed, 7)
        assert context.lens == lens
        assert context.lens_instruction == lens_instruction(lens)
        assert context.lens_version == "p8-lens-v1"
        contexts.append(context)
    assert len({c.lens_instruction for c in contexts}) == 6
    assert all(c.authority == contexts[0].authority for c in contexts)
    assert all(c.target_findings == contexts[0].target_findings for c in contexts)
    assert all(c.language_envelopes == contexts[0].language_envelopes for c in contexts)
    assert all(c.coverage_obligations == contexts[0].coverage_obligations for c in contexts)


def test_heading_table_and_citation_tokens_are_structured(report_case, compilation):
    from novelty_harness.reporting.drafts import (
        CitationToken,
        DraftBlock,
        InlineStyle,
        validate_section_draft,
    )

    context = context_for(report_case.bundle, compilation)
    # Increase only display capacity for this contract-only test, not evidence permissions.
    context = context.model_copy(update={"requires_fallback": False})
    ref = context.eligible_citation_refs[0]
    blocks = (
        DraftBlock(block_id="heading", kind="HEADING", text="Stored comparison"),
        DraftBlock(
            block_id="cell",
            kind="TABLE_CELL",
            text="Earlier description",
            inline_styles=(InlineStyle(start=0, end=7, style="EMPHASIS"),),
            citation_tokens=(CitationToken(offset=19, authority_ref=ref),),
            basis_candidate_refs=(ref,),
            table_id="table",
            row=0,
            column=0,
        ),
    )
    result = validate_section_draft(draft_for(context, blocks), context)
    assert result.blocks == blocks
    assert not hasattr(result, "supported")
    assert not hasattr(result, "verified")
    for extra in (
        {"url": "https://invented.invalid"},
        {"gate_override": "PASS"},
        {"trusted": True},
    ):
        with pytest.raises(ValidationError):
            type(result).model_validate({**result.model_dump(mode="json"), **extra})
    with pytest.raises(ValidationError):
        DraftBlock.model_validate({"block_id": "html", "kind": "HTML", "text": "<b>x</b>"})


@pytest.mark.parametrize(
    "text",
    [
        "<script>run()</script>",
        "[claim](https://invented.invalid)",
        "javascript:run()",
        "data:text/html,x",
        "ftp://invented.invalid/file",
    ],
)
def test_draft_rejects_raw_markup_and_free_urls(report_case, compilation, text):
    from novelty_harness.reporting.drafts import DraftBlock, validate_section_draft

    context = context_for(report_case.bundle, compilation).model_copy(
        update={"requires_fallback": False}
    )
    with pytest.raises(ReportProposalError):
        validate_section_draft(
            draft_for(context, (DraftBlock(block_id="unsafe", kind="PARAGRAPH", text=text),)),
            context,
        )


def test_draft_rejects_duplicate_foreign_and_stale_tokens(report_case, compilation):
    from novelty_harness.reporting.drafts import (
        CitationToken,
        DraftBlock,
        InlineStyle,
        validate_section_draft,
    )

    context = context_for(report_case.bundle, compilation).model_copy(
        update={"requires_fallback": False}
    )
    block = DraftBlock(block_id="x", kind="PARAGRAPH", text="facts")
    for blocks in (
        (block, block),
        (
            block.model_copy(
                update={"inline_styles": (InlineStyle(start=0, end=9, style="STRONG"),)}
            ),
        ),
        (
            block.model_copy(
                update={
                    "citation_tokens": (
                        CitationToken(offset=6, authority_ref=context.eligible_citation_refs[0]),
                    )
                }
            ),
        ),
        (block.model_copy(update={"obligation_ids": ("foreign",)}),),
    ):
        with pytest.raises(ReportProposalError):
            validate_section_draft(draft_for(context, blocks), context)
    with pytest.raises(ReportProposalError):
        validate_section_draft(draft_for(context).model_copy(update={"question_id": 3}), context)


def test_uncertain_chronology_display_not_earlier_precedent(report_case, compilation):
    context = context_for(report_case.bundle, compilation)
    for comparison in context.authority.comparisons:
        edge = comparison.comparison.comparison.chain.edge
        assert (
            edge.chronology
            == next(
                c
                for c in report_case.bundle.eligible_comparisons
                if c.commit_id == comparison.commit_id
            ).comparison.comparison.chain.edge.chronology
        )
        if edge.chronology.state == "UNCERTAIN":
            assert edge.decisive is False
    assert all(
        m.missing_fields == original.missing_fields
        for m, original in zip(
            context.authority.source_metadata, report_case.bundle.source_metadata, strict=True
        )
    )


def test_terminology_difference_does_not_change_frozen_equivalence(report_case, compilation):
    from novelty_harness.reporting.drafts import build_section_context
    from novelty_harness.reporting.plan import build_coverage_plan, validate_report_plan
    from tests.unit.reporting.test_plan import proposal_from, replace_question

    plan = build_coverage_plan(report_case.bundle, compilation)
    proposal = replace_question(
        proposal_from(plan),
        2,
        analytical_thesis="Explain alternative terminology in the admitted descriptions",
    )
    changed = validate_report_plan(proposal, report_case.bundle, compilation.options)
    context = build_section_context(
        report_case.bundle, changed, question_id=2, compilation=compilation
    )
    assert context.authority.comparisons == report_case.bundle.eligible_comparisons
    assert context.target_findings == report_case.frozen.target_findings


def test_patent_lens_cannot_stitch_sources(report_case, compilation):
    from novelty_harness.reporting.drafts import lens_instruction

    instruction = lens_instruction(ReportLens.PATENT_SCREENING)
    assert "single reference" in instruction
    assert "legal opinion" in instruction
    changed = compilation.model_copy(
        update={"options": ReportOptions(lens=ReportLens.PATENT_SCREENING)}
    )
    context = context_for(report_case.bundle, changed)
    assert context.authority.comparisons == report_case.bundle.eligible_comparisons
    assert context.authority.authorized_relations == report_case.bundle.authorized_relations


def test_repair_context_owns_only_local_blocks(report_case, compilation):
    from novelty_harness.reporting.drafts import DraftBlock, SectionDraftFragment
    from novelty_harness.reporting.repair import LocalRepairContext, RepairCluster

    context = context_for(report_case.bundle, compilation)
    block = DraftBlock(block_id="local", kind="PARAGRAPH", text="Local explanation")
    cluster = RepairCluster(
        scope=context.scope,
        compilation_id=context.compilation_id,
        cluster_id="cluster",
        origin_id="origin",
        question_id=2,
        original_block_ids=("local",),
        original_spans=(),
        claim_ids=(),
        obligation_ids=(),
        reason_codes=("UNSUPPORTED",),
    )
    repair = LocalRepairContext(
        scope=context.scope,
        compilation_id=context.compilation_id,
        section_context=context,
        cluster=cluster,
        original_blocks=(block,),
        neighboring_blocks=(),
        relevant_basis_refs=context.selected_basis_refs,
        required_qualification_refs=(),
    )
    assert repair.cluster.original_block_ids == ("local",)
    assert not hasattr(repair, "repository")
    fragment = SectionDraftFragment(
        scope=context.scope,
        compilation_id=context.compilation_id,
        question_id=2,
        cluster_origin_id="origin",
        replaced_block_ids=("local",),
        blocks=(block,),
    )
    with pytest.raises(ValidationError):
        SectionDraftFragment.model_validate(
            {**fragment.model_dump(mode="json"), "edit_neighbors": True}
        )


def test_selected_passage_brings_complete_committed_comparison(report_case, compilation):
    from novelty_harness.reporting.drafts import build_section_context
    from novelty_harness.reporting.models import AuthorityKind
    from novelty_harness.reporting.plan import build_coverage_plan, validate_report_plan
    from tests.unit.reporting.test_plan import proposal_from, replace_question

    plan = build_coverage_plan(report_case.bundle, compilation)
    passage_ref = next(
        r for r in plan.questions[0].evidence_refs if r.kind == AuthorityKind.PASSAGE
    )
    proposal = replace_question(
        proposal_from(plan),
        1,
        evidence_refs=(passage_ref,),
        subsections=tuple(
            s.model_copy(update={"evidence_refs": (passage_ref,)})
            for s in plan.questions[0].subsections
        ),
    )
    selected = validate_report_plan(proposal, report_case.bundle, compilation.options)
    context = build_section_context(
        report_case.bundle, selected, question_id=1, compilation=compilation
    )
    assert any(
        p.passage.passage_id == passage_ref.native_id
        for c in context.authority.comparisons
        for p in c.cited_passages
    )
    assert any(r.kind == AuthorityKind.COMPARISON for r in context.selected_basis_refs)


def test_draft_and_repair_artifacts_retain_section_ownership(report_case, compilation):
    from novelty_harness.reporting.artifacts import ReportArtifactKind, make_report_artifact
    from novelty_harness.reporting.drafts import SectionDraftFragment

    context = context_for(report_case.bundle, compilation)
    draft = draft_for(context)
    artifact = make_report_artifact(
        compilation, ReportArtifactKind.DRAFT, draft, method_version="p8-write-v1"
    )
    assert artifact.question_id == 2
    fragment = SectionDraftFragment(
        scope=context.scope,
        compilation_id=context.compilation_id,
        question_id=2,
        cluster_origin_id="original",
        replaced_block_ids=("paragraph",),
        blocks=draft.blocks,
    )
    repaired = make_report_artifact(
        compilation, ReportArtifactKind.REPAIR, fragment, method_version="p8-repair-v1"
    )
    assert repaired.question_id == 2
    assert repaired.cluster_origin_id == "original"


def test_draft_persistence_keeps_public_section_identity(report_case, compilation):
    from novelty_harness.reporting.artifacts import ReportArtifactKind, make_report_artifact
    from novelty_harness.reporting.execution import ReportCompilationConfiguration
    from novelty_harness.reporting.plan import build_coverage_plan
    from novelty_harness.reporting.repository import ReportAuthorityError

    attempt = report_case.repository.begin_report_compilation(
        report_case.bundle.scope.assessment_id,
        adjudication_id=report_case.frozen.adjudication_id,
        options=ReportOptions(),
        configuration=ReportCompilationConfiguration(),
        attempt_token="writer-storage",
    )
    plan = build_coverage_plan(report_case.bundle, attempt)
    report_case.repository.record_report_artifact(
        attempt.compilation_id,
        make_report_artifact(
            attempt, ReportArtifactKind.PLAN, plan, method_version="p8-plan-firewall-v1"
        ),
    )
    context = context_for(report_case.bundle, attempt)
    artifact = make_report_artifact(
        attempt, ReportArtifactKind.DRAFT, draft_for(context), method_version="p8-write-v1"
    )
    assert (
        report_case.repository.record_report_artifact(attempt.compilation_id, artifact)
        == artifact.artifact_id
    )
    assert artifact in report_case.repository.load_report_artifacts(attempt.compilation_id)
    with pytest.raises(ReportAuthorityError):
        report_case.repository.record_report_artifact(
            attempt.compilation_id, artifact.model_copy(update={"question_id": 3})
        )


def test_context_character_allowance_accounts_emitted_structure(report_case, compilation):
    from novelty_harness.runtime.tracing.hashing import canonical_json

    context = context_for(report_case.bundle, compilation)
    assert context.display_chars == len(canonical_json(context))


def test_repair_context_rejects_unowned_or_out_of_text_span(report_case, compilation):
    from novelty_harness.reporting.drafts import DraftBlock
    from novelty_harness.reporting.repair import LocalRepairContext, RepairCluster, RepairSpan

    context = context_for(report_case.bundle, compilation)
    cluster = RepairCluster(
        scope=context.scope,
        compilation_id=context.compilation_id,
        cluster_id="c",
        origin_id="o",
        question_id=2,
        original_block_ids=("local",),
        original_spans=(RepairSpan(block_id="local", start=0, end=99),),
        claim_ids=(),
        obligation_ids=(),
        reason_codes=("UNSUPPORTED",),
    )
    with pytest.raises(ValidationError):
        LocalRepairContext(
            scope=context.scope,
            compilation_id=context.compilation_id,
            section_context=context,
            cluster=cluster,
            original_blocks=(DraftBlock(block_id="local", kind="PARAGRAPH", text="short"),),
            neighboring_blocks=(),
            relevant_basis_refs=(),
            required_qualification_refs=(),
        )


def test_writer_context_retains_assessment_cutoff(report_case, compilation):
    context = context_for(report_case.bundle, compilation)
    assert context.as_of == report_case.frozen.as_of
