"""Canonical report proposals retain exact frozen state and actual local proof."""

from datetime import UTC, datetime

import pytest

from novelty_harness.domain.enums import VerdictState
from novelty_harness.reporting.models import ReportOptions, ReportProposalError
from tests.unit.reporting.test_obligations import report_case as _report_case

report_case = _report_case


@pytest.fixture(scope="module")
def ir_case(report_case):
    from novelty_harness.reporting.artifacts import ReportArtifactKind, make_report_artifact
    from novelty_harness.reporting.citations import build_citation_registry
    from novelty_harness.reporting.execution import ReportCompilationConfiguration
    from novelty_harness.reporting.fallback import FallbackRecord, render_fallback_section
    from novelty_harness.reporting.plan import build_coverage_plan

    c = report_case.repository.begin_report_compilation(
        report_case.bundle.scope.assessment_id,
        adjudication_id=report_case.frozen.adjudication_id,
        options=ReportOptions(compact_summary=True),
        configuration=ReportCompilationConfiguration(),
        attempt_token="canonical-ir",
    )
    plan = build_coverage_plan(report_case.bundle, c)
    documents = [(ReportArtifactKind.PLAN, plan, "p8-plan-firewall-v1")]
    sections = tuple(
        render_fallback_section(report_case.bundle, c, question_id=q) for q in range(1, 10)
    )
    documents.extend(
        (
            ReportArtifactKind.FALLBACK,
            FallbackRecord(
                scope=c.scope,
                compilation_id=c.compilation_id,
                question_id=s.draft.question_id,
                bundle_digest=report_case.bundle.bundle_digest,
                section=s,
            ),
            "p8-fallback-v1",
        )
        for s in sections
    )
    for kind, document, version in documents:
        artifact = make_report_artifact(c, kind, document, method_version=version)
        report_case.repository.record_report_artifact(c.compilation_id, artifact)
    artifacts = report_case.repository.load_report_artifacts(c.compilation_id)
    return c, sections, build_citation_registry(sections, report_case.bundle), artifacts


def build_ir(case, data):
    from novelty_harness.reporting.ir import build_report_ir

    compilation, sections, citations, artifacts = data
    return build_report_ir(case.bundle, compilation, sections, citations, artifacts)


def compiled_shape(ir, data):
    from novelty_harness.reporting.ir import CompiledAssessmentReport, report_id

    compilation, _, _, _ = data
    report = CompiledAssessmentReport(
        scope=ir.scope,
        compilation_id=compilation.compilation_id,
        report_id="pending",
        ir=ir,
        dependencies=(*ir.source_dependency_manifest, *ir.report_artifact_dependencies),
        approved_versions=compilation.configuration.deterministic_versions,
        configuration_refs=ir.generation_provenance.configuration_refs,
        execution_refs=ir.generation_provenance.execution_refs,
        accepted_at=datetime(2026, 10, 6, tzinfo=UTC),
    )
    return report.model_copy(update={"report_id": report_id(report)})


def test_ir_preserves_mixed_targets_and_summary_limitations(report_case, ir_case):
    from novelty_harness.reporting.ir import derive_compact_summary, validate_report_ir

    ir = build_ir(report_case, ir_case)
    compilation, sections, _, artifacts = ir_case
    validate_report_ir(ir, report_case.bundle, compilation, artifacts)
    assert tuple(s.question_id for s in ir.sections) == tuple(range(1, 10))
    assert ir.target_findings == report_case.bundle.target_findings
    assert ir.overall_finding == report_case.bundle.overall_finding
    assert ir.source_dependency_manifest == report_case.bundle.dependency_manifest
    assert {d.report_artifact_id for d in ir.report_artifact_dependencies} == {
        a.artifact_id for a in artifacts
    }
    assert ir.material_claims and ir.claim_basis_links
    assert ir.citation_registry.citations and ir.coverage_satisfaction
    assert ir.uncertainty_summary and ir.validation_requirements
    assert any(v.kind == "NO_VALUE_ASSESSMENT" for v in ir.value_availability)
    summary = derive_compact_summary(ir)
    assert ir.compact_summary == summary
    assert {t.target.id for t in summary.targets} == {f.target_id for f in ir.target_findings}
    for envelope in report_case.bundle.language_envelopes:
        target = next(t for t in summary.targets if t.target == envelope.target)
        assert target.verdict == envelope.verdict
        assert target.permitted_classes == envelope.permitted_classes
        assert target.limitations == envelope.required_limitations
    for section in ir.sections:
        for block in section.blocks:
            assert block.origin == "DETERMINISTIC_FALLBACK"
            assert block.source_artifact_refs and not block.verification_refs
    assert not ir.verification_refs
    assert len(sections) == 9


def test_compact_summary_cannot_strengthen_or_drop_decisive_limit(report_case, ir_case):
    from novelty_harness.reporting.ir import validate_report_ir

    ir = build_ir(report_case, ir_case)
    summary = ir.compact_summary
    assert summary is not None
    assert any(t.limitations for t in summary.targets)
    changed = summary.model_copy(
        update={"targets": tuple(t.model_copy(update={"limitations": ()}) for t in summary.targets)}
    )
    with pytest.raises(ReportProposalError):
        validate_report_ir(
            ir.model_copy(update={"compact_summary": changed}),
            report_case.bundle,
            ir_case[0],
            ir_case[3],
        )


def test_different_actual_prose_changes_report_id(report_case, ir_case):
    from novelty_harness.reporting.ir import report_id

    report = compiled_shape(build_ir(report_case, ir_case), ir_case)
    section = report.ir.sections[0]
    block = section.blocks[0]
    changed_block = block.model_copy(
        update={
            "draft_block": block.draft_block.model_copy(
                update={"text": "Another realized paragraph"}
            )
        }
    )
    changed_section = section.model_copy(update={"blocks": (changed_block, *section.blocks[1:])})
    changed = report.model_copy(
        update={
            "ir": report.ir.model_copy(
                update={"sections": (changed_section, *report.ir.sections[1:])}
            )
        }
    )
    # Pure identity distinction does not confer acceptance on the changed prose.
    assert report_id(changed) != report.report_id


def test_report_identity_ignores_only_observations(report_case, ir_case):
    from novelty_harness.reporting.ir import report_id

    report = compiled_shape(build_ir(report_case, ir_case), ir_case)
    changed = report.model_copy(update={"accepted_at": datetime(2040, 1, 1, tzinfo=UTC)})
    assert report_id(changed) == report.report_id
    assert (
        report_id(report.model_copy(update={"approved_versions": ("different-version",)}))
        != report.report_id
    )
    assert (
        report_id(report.model_copy(update={"execution_refs": ("actual-other-response",)}))
        != report.report_id
    )


def test_generative_acceptance_needs_exact_verification_refs(report_case, ir_case):
    from novelty_harness.reporting.citations import build_citation_registry
    from novelty_harness.reporting.ir import build_report_ir

    compilation, sections, _, artifacts = ir_case
    section = sections[0]
    changed = section.model_copy(
        update={
            "block_origins": {b.block_id: "GENERATIVE_ACCEPTED" for b in section.draft.blocks},
            "verification_refs": ("forged-verification",),
            "source_artifact_refs": ("forged-draft",),
            "obligation_satisfaction": tuple(
                h.model_copy(
                    update={
                        "fallback_transformation_ref": None,
                        "verification_refs": ("forged-verification",),
                    }
                )
                for h in section.obligation_satisfaction
            ),
        }
    )
    proposed = (changed, *sections[1:])
    with pytest.raises(ReportProposalError):
        build_report_ir(
            report_case.bundle,
            compilation,
            proposed,
            build_citation_registry(proposed, report_case.bundle),
            artifacts,
        )


@pytest.mark.parametrize(
    "field", ["target_findings", "value_availability", "source_dependency_manifest"]
)
def test_caller_ir_cannot_upgrade_value_or_target_class(report_case, ir_case, field):
    from novelty_harness.reporting.ir import validate_report_ir

    ir = build_ir(report_case, ir_case)
    if field == "target_findings":
        findings = ir.target_findings
        value = (
            findings[0].model_copy(update={"verdict": VerdictState.STRONG_EVIDENCE_OF_NOVELTY}),
            *findings[1:],
        )
    else:
        value = ()
    with pytest.raises(ReportProposalError):
        validate_report_ir(
            ir.model_copy(update={field: value}), report_case.bundle, ir_case[0], ir_case[3]
        )


def test_whole_negative_requires_actual_frozen_whole_scope(report_case, ir_case):
    from novelty_harness.reporting.ir import validate_report_ir

    ir = build_ir(report_case, ir_case)
    changed = ir.overall_finding.model_copy(
        update={"verdict": VerdictState.NOT_NOVEL_AT_CLAIMED_LEVEL}
    )
    assert changed != ir.overall_finding
    with pytest.raises(ReportProposalError):
        validate_report_ir(
            ir.model_copy(update={"overall_finding": changed}),
            report_case.bundle,
            ir_case[0],
            ir_case[3],
        )


def test_unassessable_and_mixed_summary_never_flattens(report_case, ir_case):
    from novelty_harness.reporting.ir import derive_compact_summary

    ir = build_ir(report_case, ir_case)
    summary = derive_compact_summary(ir)
    assert summary.overall_finding == ir.overall_finding
    assert any(t.verdict == "UNASSESSABLE" for t in summary.targets)
    assert {t.verdict for t in summary.targets} == {f.verdict for f in ir.target_findings}
    assert summary.value_availability == ir.value_availability
    assert summary.uncertainty == ir.uncertainty_summary


def test_same_config_distinct_realizations_do_not_collide(report_case, ir_case):
    test_different_actual_prose_changes_report_id(report_case, ir_case)


def test_ir_missing_fallback_artifact_is_not_repaired_by_label(report_case, ir_case):
    from novelty_harness.reporting.ir import validate_report_ir

    ir = build_ir(report_case, ir_case)
    artifacts = tuple(a for a in ir_case[3] if a.question_id != 3)
    with pytest.raises(ReportProposalError):
        validate_report_ir(ir, report_case.bundle, ir_case[0], artifacts)


def test_section_projection_does_not_self_certify_nonmaterial_block(ir_case):
    from novelty_harness.reporting.claims import validate_claim_extraction
    from novelty_harness.reporting.verification import section_extraction

    section = ir_case[1][0]
    heading = section.draft.blocks[0]
    claims = tuple(c for c in section.claims if c.block_id != heading.block_id)
    retained = {c.claim_id for c in claims}
    # A projection of absent proposed claims supplies only a neutral hint.
    shaped = section.model_copy(
        update={
            "claims": claims,
            "basis_links": tuple(link for link in section.basis_links if link.claim_id in retained),
        }
    )
    proposal = section_extraction(shaped)
    validate_claim_extraction(shaped.draft, proposal)
    account = next(a for a in proposal.block_accounts if a.block_id == heading.block_id)
    assert account.claim_ids == () and account.non_material_reason
    assert not hasattr(proposal, "complete")


def test_report_identity_separates_retrieval_observation_from_publication_fact(
    report_case, ir_case
):
    from datetime import date

    from novelty_harness.reporting.ir import report_id

    report = compiled_shape(build_ir(report_case, ir_case), ir_case)
    registry = report.ir.citation_registry
    citation = registry.citations[0]
    observed = citation.model_copy(update={"retrieved_at": datetime(2040, 1, 1, tzinfo=UTC)})
    observation_report = report.model_copy(
        update={
            "ir": report.ir.model_copy(
                update={
                    "citation_registry": registry.model_copy(
                        update={"citations": (observed, *registry.citations[1:])}
                    )
                }
            )
        }
    )
    assert report_id(observation_report) == report.report_id
    assert citation.source_metadata.version is not None
    published = citation.source_metadata.version.model_copy(
        update={"published_date": date(2040, 1, 1)}
    )
    factual = citation.model_copy(
        update={
            "source_metadata": citation.source_metadata.model_copy(update={"version": published})
        }
    )
    factual_report = report.model_copy(
        update={
            "ir": report.ir.model_copy(
                update={
                    "citation_registry": registry.model_copy(
                        update={"citations": (factual, *registry.citations[1:])}
                    )
                }
            )
        }
    )
    assert report_id(factual_report) != report.report_id


async def test_ir_dependencies_retain_actual_failed_invocation(report_case):
    from novelty_harness.application.phase8_sections import invoke_report_operation
    from novelty_harness.reporting.artifacts import ReportArtifactKind, make_report_artifact
    from novelty_harness.reporting.citations import build_citation_registry
    from novelty_harness.reporting.drafts import SectionDraft, build_section_context
    from novelty_harness.reporting.execution import (
        ReportCompilationConfiguration,
        ReportExecutionRecord,
        ReportPortConfiguration,
        approved_role_configuration,
    )
    from novelty_harness.reporting.fallback import FallbackRecord, render_fallback_section
    from novelty_harness.reporting.ir import build_report_ir, validate_report_ir
    from novelty_harness.reporting.models import ReportGenerationLimits, ReportSemanticRole
    from novelty_harness.reporting.plan import build_coverage_plan

    class FailedPort:
        calls = 0

        @property
        def configuration(self):
            return ReportPortConfiguration(
                mode="PORT_PROTOCOL",
                implementation=type(self).__module__ + "." + type(self).__qualname__,
            )

        async def write(self, context):
            self.calls += 1
            raise RuntimeError("Recorded unavailable port")

    port = FailedPort()
    c = report_case.repository.begin_report_compilation(
        report_case.bundle.scope.assessment_id,
        adjudication_id=report_case.frozen.adjudication_id,
        options=ReportOptions(
            limits=ReportGenerationLimits(
                max_context_chars=50000000,
                max_question_chars=4000000,
                max_blocks_per_question=2000,
                max_tokens=10000000000,
            )
        ),
        configuration=ReportCompilationConfiguration(
            roles=(
                approved_role_configuration(
                    report_case.bundle.scope,
                    "pending",
                    ReportSemanticRole.WRITER,
                    port.configuration,
                ),
            )
        ),
        attempt_token="ir-actual-failed-call",
    )
    plan = build_coverage_plan(report_case.bundle, c)
    artifact = make_report_artifact(
        c, ReportArtifactKind.PLAN, plan, method_version="p8-plan-firewall-v1"
    )
    report_case.repository.record_report_artifact(c.compilation_id, artifact)
    context = build_section_context(report_case.bundle, plan, question_id=2, compilation=c)
    with pytest.raises(ReportProposalError):
        await invoke_report_operation(
            c,
            report_case.repository,
            port,
            ReportSemanticRole.WRITER,
            context,
            SectionDraft,
            lambda: port.write(context),
        )
    assert port.calls == 1
    sections = tuple(
        render_fallback_section(report_case.bundle, c, question_id=q) for q in range(1, 10)
    )
    for section in sections:
        record = FallbackRecord(
            scope=c.scope,
            compilation_id=c.compilation_id,
            question_id=section.draft.question_id,
            bundle_digest=report_case.bundle.bundle_digest,
            section=section,
        )
        artifact = make_report_artifact(
            c, ReportArtifactKind.FALLBACK, record, method_version="p8-fallback-v1"
        )
        report_case.repository.record_report_artifact(c.compilation_id, artifact)
    artifacts = report_case.repository.load_report_artifacts(c.compilation_id)
    failed = next(a for a in artifacts if isinstance(a.document, ReportExecutionRecord))
    assert failed.document.outcome == "PROVIDER_FAILURE"
    ir = build_report_ir(
        report_case.bundle,
        c,
        sections,
        build_citation_registry(sections, report_case.bundle),
        artifacts,
    )
    assert failed.artifact_id in ir.generation_provenance.execution_refs
    assert any(d.report_artifact_id == failed.artifact_id for d in ir.report_artifact_dependencies)
    changed = ir.model_copy(
        update={
            "report_artifact_dependencies": tuple(
                d
                for d in ir.report_artifact_dependencies
                if d.report_artifact_id != failed.artifact_id
            )
        }
    )
    with pytest.raises(ReportProposalError):
        validate_report_ir(changed, report_case.bundle, c, artifacts)
