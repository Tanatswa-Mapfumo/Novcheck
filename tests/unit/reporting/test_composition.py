"""Composition contracts cannot supply authoritative findings or rewrites."""

import pytest
from pydantic import ValidationError

from tests.fixtures.phase8 import report_scope
from tests.unit.reporting.test_obligations import report_case as _report_case


def test_composition_check_binds_scope_text_and_explicit_localization():
    from novelty_harness.reporting.verification import CompositionCheck

    payload = dict(
        scope=report_scope(),
        compilation_id="p8run_shapes",
        narrative_digest="a" * 64,
        claims_digest="b" * 64,
        permission_digest="c" * 64,
        disposition="REJECTED",
        implicated_block_ids=("heading",),
        implicated_question_ids=(3,),
        indeterminate_scope=False,
        reason_codes=("WHOLE_SCOPE_DRIFT",),
        reason="Heading overstates whole-project scope",
    )
    check = CompositionCheck(**payload)
    assert not check.accepted
    assert check.implicated_question_ids == (3,)
    with pytest.raises(ValidationError):
        CompositionCheck(**(payload | {"rewrite": "A replacement report"}))
    with pytest.raises(ValidationError):
        CompositionCheck(**(payload | {"verdict": "NOT_NOVEL_AT_CLAIMED_LEVEL"}))
    with pytest.raises(ValidationError):
        CompositionCheck(**(payload | {"implicated_block_ids": (), "implicated_question_ids": ()}))
    assert CompositionCheck(
        **(
            payload
            | {
                "implicated_block_ids": (),
                "implicated_question_ids": (),
                "indeterminate_scope": True,
            }
        )
    ).indeterminate_scope


report_case = _report_case


class UnitArtifactSink:
    """Routing-only sink: cannot create or load accepted report authority."""

    def __init__(self, artifacts):
        self.artifacts = list(artifacts)

    def load_report_artifacts(self, compilation_id):
        return tuple(a for a in self.artifacts if a.compilation_id == compilation_id)

    def record_report_artifact(self, compilation_id, artifact):
        assert artifact.compilation_id == compilation_id
        if not any(a.artifact_id == artifact.artifact_id for a in self.artifacts):
            self.artifacts.append(artifact)
        return artifact.artifact_id


class CompositionPort:
    def __init__(
        self, *, questions=(3,), unknown=False, supported=False, reason="WHOLE_SCOPE_DRIFT"
    ):
        self.questions = questions
        self.unknown = unknown
        self.supported = supported
        self.reason = reason
        self.calls = []

    @property
    def configuration(self):
        from novelty_harness.reporting.execution import ReportPortConfiguration

        return ReportPortConfiguration(
            mode="PORT_PROTOCOL",
            implementation=type(self).__module__ + "." + type(self).__qualname__,
        )

    async def verify(self, context):
        raise AssertionError("composition cannot open another local verification loop")

    async def check_composition(self, context):
        from novelty_harness.reporting.verification import CompositionCheck

        self.calls.append(context)
        return CompositionCheck(
            scope=context.scope,
            compilation_id=context.compilation_id,
            narrative_digest=context.narrative_digest,
            claims_digest=context.claims_digest,
            permission_digest=context.permission_digest,
            disposition="SUPPORTED" if self.supported else "REJECTED",
            implicated_block_ids=(),
            implicated_question_ids=() if self.supported or self.unknown else self.questions,
            indeterminate_scope=self.unknown,
            reason_codes=() if self.supported else (self.reason,),
            reason="Recorded composition meaning case; no rewrite or new adjudication",
        )


def composition_case(case, port, token):
    """Native upstream authority; generative section shapes are not accepted reports."""
    from novelty_harness.reporting.execution import (
        ReportCompilationConfiguration,
        approved_role_configuration,
    )
    from novelty_harness.reporting.fallback import render_fallback_section
    from novelty_harness.reporting.models import (
        ReportGenerationLimits,
        ReportOptions,
        ReportSemanticRole,
    )

    c = case.repository.begin_report_compilation(
        case.bundle.scope.assessment_id,
        adjudication_id=case.frozen.adjudication_id,
        options=ReportOptions(
            limits=ReportGenerationLimits(
                max_context_chars=50_000_000,
                max_question_chars=2_000_000,
                max_blocks_per_question=1000,
                max_tokens=10000000000,
            )
        ),
        configuration=ReportCompilationConfiguration(
            roles=(
                approved_role_configuration(
                    case.bundle.scope, "pending", ReportSemanticRole.COMPOSITION, port.configuration
                ),
            )
        ),
        attempt_token=token,
    )
    sections = []
    for q in range(1, 10):
        known = render_fallback_section(case.bundle, c, question_id=q)
        # Known faithful text and native links stand in for local semantic results
        # in this unit routing test. The sink has no acceptance/load capability.
        sections.append(
            known.model_copy(
                update={
                    "block_origins": {
                        b.block_id: "GENERATIVE_ACCEPTED" for b in known.draft.blocks
                    },
                    "verification_refs": ("unit-local-verification",),
                    "source_artifact_refs": ("unit-local-source",),
                    "obligation_satisfaction": tuple(
                        s.model_copy(
                            update={
                                "verification_refs": ("unit-local-verification",),
                                "fallback_transformation_ref": None,
                            }
                        )
                        for s in known.obligation_satisfaction
                    ),
                }
            )
        )
    if token == "composition-whole":
        from novelty_harness.reporting.claims import TextSpan, report_claim_id
        from novelty_harness.runtime.tracing.hashing import canonical_hash

        section = sections[2]
        heading = section.draft.blocks[0]
        text = "Together, those precedents establish the full proposal."
        changed = heading.model_copy(update={"text": text})
        original = next(claim for claim in section.claims if claim.block_id == heading.block_id)
        claim = original.model_copy(
            update={
                "block_text_digest": canonical_hash(text),
                "spans": (TextSpan(start=0, end=len(text)),),
                "normalized_assertion": text,
            }
        )
        claim = claim.model_copy(update={"claim_id": report_claim_id(claim)})
        sections[2] = section.model_copy(
            update={
                "draft": section.draft.model_copy(
                    update={"blocks": (changed, *section.draft.blocks[1:])}
                ),
                "claims": tuple(claim if item == original else item for item in section.claims),
                "basis_links": tuple(
                    link.model_copy(update={"claim_id": claim.claim_id, "proposition": text})
                    if link.claim_id == original.claim_id
                    else link
                    for link in section.basis_links
                ),
            }
        )
    return (
        c,
        tuple(sections),
        UnitArtifactSink(case.repository.load_report_artifacts(c.compilation_id)),
    )


async def compose(case, port, token, *, absent=False):
    from novelty_harness.application.phase8_sections import assure_report_composition
    from novelty_harness.ports.reporting import ReportPorts

    c, sections, sink = composition_case(case, port, token)
    from novelty_harness.reporting.obligations import check_report_coverage

    check_report_coverage(sections, case.bundle)
    from novelty_harness.reporting.verification import build_composition_context
    from novelty_harness.runtime.tracing.hashing import canonical_json

    context = build_composition_context(sections, case.bundle, c)
    assert len(canonical_json(context)) <= c.options.limits.max_context_chars
    final = await assure_report_composition(
        c,
        sections,
        bundle=case.bundle,
        ports=ReportPorts(verifier=None if absent else port),
        repository=sink,
    )
    return c, sections, final, sink


async def test_cross_section_stronger_whole_implication_uses_fallback_not_rewrite(report_case):
    from novelty_harness.reporting.fallback import validate_fallback_section
    from novelty_harness.reporting.obligations import check_report_coverage

    port = CompositionPort()
    c, before, final, _ = await compose(report_case, port, "composition-whole")
    assert len(port.calls) == 1
    assert port.calls[0].drafts[2].blocks[0].text == (
        "Together, those precedents establish the full proposal."
    )
    assert set(final[2].block_origins.values()) == {"DETERMINISTIC_FALLBACK"}
    validate_fallback_section(final[2], report_case.bundle, c)
    assert final[:2] == before[:2] and final[3:] == before[3:]
    assert {s.obligation_id for s in check_report_coverage(final, report_case.bundle)} == {
        o.obligation_id for o in report_case.bundle.coverage_obligations
    }


async def test_composition_unknown_scope_replaces_full_report(report_case):
    port = CompositionPort(unknown=True)
    _, _, final, _ = await compose(report_case, port, "composition-unknown")
    assert len(port.calls) == 1
    assert all(set(s.block_origins.values()) == {"DETERMINISTIC_FALLBACK"} for s in final)


async def test_unavailable_composition_verifier_forces_complete_safe_fallback(report_case):
    port = CompositionPort()
    _, _, final, sink = await compose(report_case, port, "composition-absent", absent=True)
    assert not port.calls
    assert not any(a.kind == "EXECUTION" for a in sink.artifacts)
    assert tuple(s.draft.question_id for s in final) == tuple(range(1, 10))
    assert all(set(s.block_origins.values()) == {"DETERMINISTIC_FALLBACK"} for s in final)


def test_missing_local_limitation_even_when_q9_has_it_rejected(report_case):
    from novelty_harness.reporting.models import ReportProposalError
    from novelty_harness.reporting.obligations import check_report_coverage

    _, sections, _ = composition_case(report_case, CompositionPort(), "composition-local-limit")
    limitation_ids = {
        o.obligation_id
        for o in report_case.bundle.coverage_obligations
        if o.requirement_kind == "ACTUAL_LIMITATION" and 9 in o.question_ids
    }
    section = next(
        s
        for s in sections
        if s.draft.question_id != 9
        and any(o.obligation_id in limitation_ids for o in s.obligation_satisfaction)
    )
    victim = next(
        o
        for o in section.obligation_satisfaction
        if next(
            b for b in report_case.bundle.coverage_obligations if b.obligation_id == o.obligation_id
        ).requirement_kind
        == "ACTUAL_LIMITATION"
    )
    changed = section.model_copy(
        update={
            "obligation_satisfaction": tuple(
                o for o in section.obligation_satisfaction if o != victim
            )
        }
    )
    replaced = tuple(changed if s == section else s for s in sections)
    with pytest.raises(ReportProposalError):
        check_report_coverage(replaced, report_case.bundle)
    assert any(o.obligation_id == victim.obligation_id for o in sections[8].obligation_satisfaction)


async def test_unassessable_target_not_lost_in_composition(report_case):
    port = CompositionPort(supported=True)
    _, before, final, _ = await compose(report_case, port, "composition-safe-mixed")
    assert final == before and len(port.calls) == 1
    assert port.calls[0].target_findings == report_case.bundle.target_findings
    assert any(f.verdict == "UNASSESSABLE" for f in port.calls[0].target_findings)


@pytest.mark.parametrize("reason", ["SUMMARY_HEADING_SCOPE_DRIFT", "VALUE_IMPLIES_NOVELTY"])
async def test_summary_like_heading_has_no_extra_permission(report_case, reason):
    port = CompositionPort(questions=(6, 8), reason=reason)
    _, _, final, _ = await compose(report_case, port, "composition-" + reason)
    assert len(port.calls) == 1
    assert all(
        set(final[q - 1].block_origins.values()) == {"DETERMINISTIC_FALLBACK"} for q in (6, 8)
    )


async def test_cross_question_value_implies_novelty_rejected(report_case):
    await test_summary_like_heading_has_no_extra_permission(report_case, "VALUE_IMPLIES_NOVELTY")


def test_composition_store_requires_committed_local_proof(report_case):
    from novelty_harness.reporting.artifacts import ReportArtifactKind, make_report_artifact
    from novelty_harness.reporting.repository import ReportAuthorityError
    from novelty_harness.reporting.verification import build_composition_context

    c, sections, _ = composition_case(report_case, CompositionPort(), "composition-no-proof")
    context = build_composition_context(sections, report_case.bundle, c)
    artifact = make_report_artifact(
        c, ReportArtifactKind.COMPOSITION, context, method_version="p8-compose-check-v1"
    )
    with pytest.raises(ReportAuthorityError, match="independently extracted"):
        report_case.repository.record_report_artifact(c.compilation_id, artifact)


async def test_composition_stored_input_and_execution_rejoin_exact_text(report_case):
    from novelty_harness.application.phase8_sections import (
        invoke_report_operation,
        record_section_artifact,
    )
    from novelty_harness.reporting.artifacts import ReportArtifactKind
    from novelty_harness.reporting.fallback import FallbackRecord, render_fallback_section
    from novelty_harness.reporting.models import ReportProposalError, ReportSemanticRole
    from novelty_harness.reporting.verification import (
        CompositionCheck,
        build_composition_context,
        validate_composition_check,
    )

    port = CompositionPort(supported=True)
    c, _, _ = composition_case(report_case, port, "composition-stored-proof")
    sections = tuple(
        render_fallback_section(report_case.bundle, c, question_id=q) for q in range(1, 10)
    )
    for section in sections:
        record_section_artifact(
            c,
            report_case.repository,
            ReportArtifactKind.FALLBACK,
            FallbackRecord(
                scope=c.scope,
                compilation_id=c.compilation_id,
                question_id=section.draft.question_id,
                bundle_digest=report_case.bundle.bundle_digest,
                section=section,
            ),
            "p8-fallback-v1",
        )
    context = build_composition_context(sections, report_case.bundle, c)
    record_section_artifact(
        c, report_case.repository, ReportArtifactKind.COMPOSITION, context, "p8-compose-check-v1"
    )
    check, execution_ref = await invoke_report_operation(
        c,
        report_case.repository,
        port,
        ReportSemanticRole.COMPOSITION,
        context,
        CompositionCheck,
        lambda: port.check_composition(context),
    )
    record_section_artifact(
        c,
        report_case.repository,
        ReportArtifactKind.COMPOSITION,
        check,
        "p8-compose-check-v1",
        execution_ref=execution_ref,
    )
    artifacts = report_case.repository.load_report_artifacts(c.compilation_id)
    assert any(a.document == context for a in artifacts)
    assert any(a.document == check and a.execution_ref == execution_ref for a in artifacts)
    with pytest.raises(ReportProposalError):
        validate_composition_check(context, check.model_copy(update={"narrative_digest": "f" * 64}))
