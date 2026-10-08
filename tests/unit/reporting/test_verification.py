"""Scripted semantic dispositions exercise validation, not live entailment quality."""

import pytest
from pydantic import ValidationError

from novelty_harness.reporting.models import ReportProposalError
from novelty_harness.runtime.tracing.hashing import canonical_hash
from tests.unit.reporting.test_firewall import claim_case
from tests.unit.reporting.test_obligations import report_case as _report_case
from tests.unit.reporting.test_plan import compilation as _compilation

report_case = _report_case
compilation = _compilation


def verification_case(bundle, compilation, *, text="An admitted source describes a mechanism"):
    from novelty_harness.reporting.firewall import check_report_claims
    from novelty_harness.reporting.verification import build_claim_verification_context

    draft, extraction, plan = claim_case(bundle, compilation, text=text)
    context = build_claim_verification_context(draft, extraction, bundle, plan)
    return context, check_report_claims(draft, extraction, bundle, plan)


def scripted_batch(context, *, disposition="SUPPORTED", block_disposition="SUPPORTED", code=()):
    from novelty_harness.reporting.verification import (
        BlockCompleteness,
        ClaimVerification,
        ClaimVerificationBatch,
    )

    blocks = {b.block_id: b for b in context.draft.blocks}
    return ClaimVerificationBatch(
        scope=context.scope,
        compilation_id=context.compilation_id,
        question_id=context.question_id,
        context_digest=canonical_hash(context),
        draft_digest=canonical_hash(context.draft),
        extraction_digest=canonical_hash(context.extraction),
        dispositions=tuple(
            ClaimVerification(
                scope=context.scope,
                compilation_id=context.compilation_id,
                claim_id=claim.claim_id,
                text_digest=canonical_hash(
                    {
                        "block_text": blocks[claim.block_id].text,
                        "spans": [s.model_dump(mode="json") for s in claim.spans],
                    }
                ),
                basis_digest=canonical_hash(
                    [
                        link.model_dump(mode="json")
                        for link in context.extraction.basis_links
                        if link.claim_id == claim.claim_id
                    ]
                ),
                permission_digest=canonical_hash(
                    [e.model_dump(mode="json") for e in context.language_envelopes]
                ),
                disposition=disposition,
                unmet_qualification_refs=(),
                reason_codes=code,
                reason="Recorded independent support disposition for this actual text",
                basis_refs=tuple(
                    dict.fromkeys(
                        link.authority_ref
                        for link in context.extraction.basis_links
                        if link.claim_id == claim.claim_id
                    )
                ),
            )
            for claim in context.extraction.claims
        ),
        blocks=tuple(
            BlockCompleteness(
                scope=context.scope,
                compilation_id=context.compilation_id,
                block_id=block.block_id,
                text_digest=canonical_hash(block.text),
                claims_digest=canonical_hash(
                    [
                        c.model_dump(mode="json")
                        for c in context.extraction.claims
                        if c.block_id == block.block_id
                    ]
                ),
                disposition=block_disposition,
                missing_assertion_spans=(),
                unmet_obligation_ids=(),
                unmet_qualification_refs=(),
                reason_codes=code,
                reason="Recorded independent extraction and limitation completeness disposition",
            )
            for block in context.draft.blocks
        ),
    )


def test_supported_claim_cannot_drop_material_limitation(report_case, compilation):
    from novelty_harness.reporting.verification import (
        VerificationDisposition,
        validate_verification_batch,
    )

    context, firewall = verification_case(report_case.bundle, compilation)
    assert firewall.accepted
    limitation = next(
        o for o in context.coverage_obligations if o.requirement_kind == "ACTUAL_LIMITATION"
    )
    batch = scripted_batch(
        context,
        disposition="REJECTED",
        block_disposition="REJECTED",
        code=("MISSING_MATERIAL_LIMITATION",),
    )
    block = batch.blocks[0].model_copy(update={"unmet_obligation_ids": (limitation.obligation_id,)})
    batch = batch.model_copy(update={"blocks": (block,)})
    checked = validate_verification_batch(context, batch, firewall)
    assert checked.dispositions[0].disposition == "REJECTED"
    assert "MISSING_MATERIAL_LIMITATION" in checked.dispositions[0].reason_codes
    assert not checked.accepted
    # A supported individual claim cannot certify a paragraph whose limitation check failed.
    claim_supported = batch.model_copy(
        update={"dispositions": scripted_batch(context).dispositions}
    )
    assert not validate_verification_batch(context, claim_supported, firewall).accepted
    lying_block = block.model_copy(update={"disposition": VerificationDisposition.SUPPORTED})
    with pytest.raises(ReportProposalError):
        validate_verification_batch(
            context, batch.model_copy(update={"blocks": (lying_block,)}), firewall
        )
    with pytest.raises(ReportProposalError):
        validate_verification_batch(context, batch.model_copy(update={"blocks": ()}), firewall)
    faithful, faithful_firewall = verification_case(
        report_case.bundle,
        compilation,
        text=context.draft.blocks[0].text
        + "; limitation: "
        + context.language_envelopes[0].required_limitations[0],
    )
    assert validate_verification_batch(
        faithful, scripted_batch(faithful), faithful_firewall
    ).accepted


def test_synthesis_does_not_establish_combination(report_case, compilation):
    from novelty_harness.reporting.verification import validate_verification_batch

    compatible, good_firewall = verification_case(
        report_case.bundle,
        compilation,
        text=(
            "X and Y are individually described in admitted sources; "
            "R remains a candidate in its accepted scope."
        ),
    )
    assert validate_verification_batch(
        compatible, scripted_batch(compatible), good_firewall
    ).accepted
    stitched, bad_firewall = verification_case(
        report_case.bundle,
        compilation,
        text="The X and Y sources establish the complete X+Y configuration.",
    )
    # Same real basis membership passes mechanical checks; independent meaning rejects stitching.
    assert bad_firewall.accepted
    rejected = scripted_batch(
        stitched,
        disposition="REJECTED",
        block_disposition="REJECTED",
        code=("INCOMPATIBLE_SYNTHESIS",),
    )
    assert not validate_verification_batch(stitched, rejected, bad_firewall).accepted
    with pytest.raises(ReportProposalError):
        validate_verification_batch(stitched, scripted_batch(compatible), bad_firewall)


def test_hidden_heading_table_presupposition_rejects_incomplete_extraction(
    report_case, compilation
):
    from novelty_harness.reporting.claims import validate_claim_extraction
    from novelty_harness.reporting.drafts import DraftBlock, SectionDraft
    from novelty_harness.reporting.firewall import check_report_claims
    from novelty_harness.reporting.plan import build_coverage_plan
    from novelty_harness.reporting.verification import (
        build_claim_verification_context,
        validate_verification_batch,
    )
    from tests.unit.reporting.test_claims import extraction_for

    plan = build_coverage_plan(report_case.bundle, compilation)
    draft = SectionDraft(
        scope=compilation.scope,
        compilation_id=compilation.compilation_id,
        question_id=2,
        blocks=(
            DraftBlock(block_id="h", kind="HEADING", text="An unprecedented configuration"),
            DraftBlock(
                block_id="t",
                kind="TABLE_CELL",
                text="No earlier implementation",
                table_id="table",
                row=0,
                column=0,
            ),
            DraftBlock(
                block_id="p",
                kind="PARAGRAPH",
                text="The unexplored mechanism remains",
                obligation_ids=plan.questions[1].obligation_ids,
            ),
        ),
    )
    proposal = extraction_for(draft)
    empty = proposal.model_copy(
        update={
            "claims": (),
            "basis_links": (),
            "block_accounts": tuple(
                a.model_copy(update={"claim_ids": (), "non_material_reason": "decorative"})
                for a in proposal.block_accounts
            ),
        }
    )
    assert validate_claim_extraction(draft, empty) == empty
    firewall = check_report_claims(draft, empty, report_case.bundle, plan)
    assert firewall.accepted
    context = build_claim_verification_context(draft, empty, report_case.bundle, plan)
    batch = scripted_batch(
        context, block_disposition="REJECTED", code=("MISSING_MATERIAL_ASSERTION",)
    )
    assert len(batch.blocks) == 3
    assert not validate_verification_batch(context, batch, firewall).accepted


@pytest.mark.parametrize(
    "field",
    ["gate_override", "verdict", "qualification_grant", "confidence", "trusted", "execution_ref"],
)
def test_verifier_cannot_supply_gate_verdict_or_qualification(report_case, compilation, field):
    from novelty_harness.reporting.verification import ClaimVerificationBatch

    context, _ = verification_case(report_case.bundle, compilation)
    payload = scripted_batch(context).model_dump(mode="json")
    payload[field] = True
    with pytest.raises(ValidationError):
        ClaimVerificationBatch.model_validate(payload)


def test_unresolved_is_not_acceptance(report_case, compilation):
    from novelty_harness.reporting.verification import validate_verification_batch

    context, firewall = verification_case(report_case.bundle, compilation)
    batch = scripted_batch(context, disposition="UNRESOLVED", code=("AMBIGUOUS_ASSERTION",))
    assert not validate_verification_batch(context, batch, firewall).accepted


def test_verifier_supported_cannot_override_firewall(report_case, compilation):
    from novelty_harness.reporting.verification import validate_verification_batch

    context, firewall = verification_case(
        report_case.bundle, compilation, text="No prior art exists anywhere"
    )
    assert not firewall.accepted
    with pytest.raises(ReportProposalError):
        validate_verification_batch(context, scripted_batch(context), firewall)


@pytest.mark.parametrize(
    "text,code",
    [
        (
            "The strong partial match demonstrates exact direct equivalence",
            "CLASSIFICATION_UPGRADE",
        ),
        (
            "No related result was returned, therefore this has never been implemented",
            "UNIVERSAL_ABSENCE",
        ),
        ("The scoped component match proves the entire project unoriginal", "WHOLE_SCOPE_DRIFT"),
        ("The accepted candidate is an established original invention", "PERMISSION_EXCEEDED"),
        ("Gate D establishes demonstrated performance advantage", "VALUE_UPGRADE"),
    ],
)
def test_semantic_paraphrases_do_not_escape_scope(report_case, compilation, text, code):
    from novelty_harness.reporting.verification import validate_verification_batch

    context, firewall = verification_case(report_case.bundle, compilation, text=text)
    assert firewall.accepted  # lexical checks cannot prove these arbitrary paraphrases
    batch = scripted_batch(
        context, disposition="REJECTED", block_disposition="REJECTED", code=(code,)
    )
    assert not validate_verification_batch(context, batch, firewall).accepted


@pytest.mark.parametrize("tag", ["DISALLOWED_WORDING_EXAMPLE", "RECOMMENDATION"])
def test_example_or_recommendation_tag_cannot_hide_assertion(report_case, compilation, tag):
    from novelty_harness.reporting.claims import ClaimUse
    from novelty_harness.reporting.verification import (
        build_claim_verification_context,
        validate_verification_batch,
    )

    context, firewall = verification_case(report_case.bundle, compilation)
    claim = context.extraction.claims[0].model_copy(update={"use": ClaimUse(tag)})
    proposal = context.extraction.model_copy(update={"claims": (claim,)})
    # Rebuild canonical claim addresses after the discourse change.
    from novelty_harness.reporting.claims import ClaimExtractionProposal

    proposal = ClaimExtractionProposal.model_validate(proposal.model_dump(mode="json"))
    from novelty_harness.reporting.plan import build_coverage_plan

    plan = build_coverage_plan(report_case.bundle, compilation)
    context = build_claim_verification_context(context.draft, proposal, report_case.bundle, plan)
    from novelty_harness.reporting.firewall import check_report_claims

    firewall = check_report_claims(context.draft, proposal, report_case.bundle, plan)
    if not firewall.accepted:
        with pytest.raises(ReportProposalError):
            validate_verification_batch(context, scripted_batch(context), firewall)
    else:
        assert not validate_verification_batch(
            context,
            scripted_batch(
                context, disposition="REJECTED", code=("DISCOURSE_DOES_NOT_REMOVE_ASSERTION",)
            ),
            firewall,
        ).accepted


def test_shared_model_has_no_writer_certification_context(report_case, compilation):
    context, _ = verification_case(report_case.bundle, compilation)
    assert context.draft.blocks[0].text
    assert context.authority.comparisons == report_case.bundle.eligible_comparisons
    assert (
        context.authority.judge_resolutions
        == report_case.bundle.judge_resolutions_and_limitations.judge_resolutions
    )
    assert context.as_of == report_case.bundle.as_of
    assert context.language_envelopes == report_case.bundle.language_envelopes
    assert not set(type(context).model_fields) & {
        "writer_reasoning",
        "writer_certification",
        "repository",
        "execution_ref",
        "accepted",
    }
    assert "execution_envelope" not in context.authority.model_dump(mode="json")


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_claim",
        "duplicate_claim",
        "duplicate_block",
        "text",
        "basis",
        "permission",
        "block_text",
        "context",
        "scope",
    ],
)
def test_verification_rejects_incomplete_duplicate_or_stale_checks(
    report_case, compilation, mutation
):
    from novelty_harness.reporting.verification import validate_verification_batch

    context, firewall = verification_case(report_case.bundle, compilation)
    batch = scripted_batch(context)
    if mutation == "missing_claim":
        batch = batch.model_copy(update={"dispositions": ()})
    elif mutation == "duplicate_claim":
        batch = batch.model_copy(update={"dispositions": batch.dispositions * 2})
    elif mutation == "duplicate_block":
        batch = batch.model_copy(update={"blocks": batch.blocks * 2})
    elif mutation == "block_text":
        batch = batch.model_copy(
            update={"blocks": (batch.blocks[0].model_copy(update={"text_digest": "b" * 64}),)}
        )
    elif mutation in {"text", "basis", "permission"}:
        batch = batch.model_copy(
            update={
                "dispositions": (
                    batch.dispositions[0].model_copy(update={mutation + "_digest": "b" * 64}),
                )
            }
        )
    elif mutation == "context":
        batch = batch.model_copy(update={"context_digest": "b" * 64})
    else:
        batch = batch.model_copy(
            update={"scope": batch.scope.model_copy(update={"adjudication_id": "other"})}
        )
    with pytest.raises(ReportProposalError):
        validate_verification_batch(context, batch, firewall)


def test_verification_artifact_binds_exact_committed_inputs(report_case, compilation):
    from novelty_harness.reporting.artifacts import ReportArtifactKind, make_report_artifact
    from novelty_harness.reporting.firewall import check_report_claims
    from novelty_harness.reporting.plan import build_coverage_plan
    from novelty_harness.reporting.repository import ReportAuthorityError

    context, _ = verification_case(report_case.bundle, compilation)
    plan = build_coverage_plan(report_case.bundle, compilation)
    firewall = check_report_claims(context.draft, context.extraction, report_case.bundle, plan)
    batch = scripted_batch(context)
    for kind, document, method in (
        (ReportArtifactKind.PLAN, plan, "p8-plan-firewall-v1"),
        (ReportArtifactKind.DRAFT, context.draft, "p8-write-v1"),
        (ReportArtifactKind.EXTRACTION, context.extraction, "p8-extract-v1"),
        (ReportArtifactKind.FIREWALL, firewall, "p8-semantic-firewall-v1"),
        (ReportArtifactKind.VERIFICATION, batch, "p8-verify-v1"),
    ):
        artifact = make_report_artifact(compilation, kind, document, method_version=method)
        assert (
            report_case.repository.record_report_artifact(compilation.compilation_id, artifact)
            == artifact.artifact_id
        )
    assert artifact.question_id == 2
    changed = batch.model_copy(update={"context_digest": "b" * 64})
    bad = make_report_artifact(
        compilation, ReportArtifactKind.VERIFICATION, changed, method_version="p8-verify-v1"
    )
    with pytest.raises(ReportAuthorityError):
        report_case.repository.record_report_artifact(compilation.compilation_id, bad)
    assert artifact in report_case.repository.load_report_artifacts(compilation.compilation_id)


@pytest.mark.parametrize(
    "mutation",
    [
        "unmet_qualification",
        "missing_assertion",
        "foreign_obligation",
        "outside_span",
        "foreign_basis",
        "nested_scope",
    ],
)
def test_support_cannot_hide_unmet_or_foreign_checks(report_case, compilation, mutation):
    from novelty_harness.reporting.claims import TextSpan
    from novelty_harness.reporting.verification import validate_verification_batch

    context, firewall = verification_case(report_case.bundle, compilation)
    batch = scripted_batch(context)
    if mutation == "unmet_qualification":
        claim = batch.dispositions[0].model_copy(
            update={"unmet_qualification_refs": (context.eligible_basis_refs[0],)}
        )
        batch = batch.model_copy(update={"dispositions": (claim,)})
    elif mutation in {"missing_assertion", "outside_span"}:
        span = TextSpan(
            start=0,
            end=1 if mutation == "missing_assertion" else len(context.draft.blocks[0].text) + 1,
        )
        block = batch.blocks[0].model_copy(update={"missing_assertion_spans": (span,)})
        batch = batch.model_copy(update={"blocks": (block,)})
    elif mutation == "foreign_obligation":
        block = batch.blocks[0].model_copy(update={"unmet_obligation_ids": ("p8ob_foreign",)})
        batch = batch.model_copy(update={"blocks": (block,)})
    elif mutation == "foreign_basis":
        ref = batch.dispositions[0].basis_refs[0].model_copy(update={"digest": "b" * 64})
        claim = batch.dispositions[0].model_copy(update={"basis_refs": (ref,)})
        batch = batch.model_copy(update={"dispositions": (claim,)})
    else:
        claim = batch.dispositions[0].model_copy(update={"compilation_id": "p8run_foreign"})
        batch = batch.model_copy(update={"dispositions": (claim,)})
    with pytest.raises(ReportProposalError):
        validate_verification_batch(context, batch, firewall)


def test_verification_requires_exact_firewall_authority_digest(report_case, compilation):
    from novelty_harness.reporting.verification import validate_verification_batch

    context, firewall = verification_case(report_case.bundle, compilation)
    stale = firewall.model_copy(update={"authority_digest": "b" * 64})
    with pytest.raises(ReportProposalError):
        validate_verification_batch(context, scripted_batch(context), stale)
