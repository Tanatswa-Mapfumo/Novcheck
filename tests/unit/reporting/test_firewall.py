"""Deterministic joins reject authority escapes without pretending to prove entailment."""

import pytest
from pydantic import ValidationError

from novelty_harness.reporting.models import AuthorityKind
from novelty_harness.runtime.tracing.hashing import canonical_hash
from tests.unit.reporting.test_obligations import report_case as _report_case
from tests.unit.reporting.test_plan import compilation as _compilation

report_case = _report_case
compilation = _compilation


def claim_case(
    bundle,
    compilation,
    *,
    question_id=2,
    category="SOURCE_FACT",
    text="The admitted source describes a mechanism",
    use="ASSERTION",
    target=None,
    basis=None,
):
    from novelty_harness.reporting.claims import (
        BlockClaimAccount,
        ClaimBasisLink,
        ClaimExtractionProposal,
        ClaimTarget,
        ReportClaim,
        TextSpan,
    )
    from novelty_harness.reporting.drafts import DraftBlock, SectionDraft
    from novelty_harness.reporting.plan import build_coverage_plan

    plan = build_coverage_plan(bundle, compilation)
    if basis is None:
        basis = next(
            d.authority_ref
            for d in bundle.dependency_manifest
            if d.authority_ref.kind == AuthorityKind.PASSAGE
        )
    if target is None:
        target = next(e for e in bundle.language_envelopes if e.target == basis.target)
    draft = SectionDraft(
        scope=bundle.scope,
        compilation_id=compilation.compilation_id,
        question_id=question_id,
        blocks=(
            DraftBlock(
                block_id="public",
                kind="PARAGRAPH",
                text=text,
                basis_candidate_refs=(basis,),
                obligation_ids=plan.questions[question_id - 1].obligation_ids,
            ),
        ),
    )
    claim = ReportClaim(
        scope=bundle.scope,
        compilation_id=compilation.compilation_id,
        claim_id="local",
        block_id="public",
        block_text_digest=canonical_hash(draft.blocks[0].text),
        spans=(TextSpan(start=0, end=len(draft.blocks[0].text)),),
        normalized_assertion=text,
        category=category,
        use=use,
        target_scopes=(ClaimTarget(target=target.target, claim_scope=target.claim_scope),),
        basis_candidates=(basis,),
        citation_candidates=(basis,),
        required_qualification_refs=(),
    )
    extraction = ClaimExtractionProposal(
        scope=bundle.scope,
        compilation_id=compilation.compilation_id,
        question_id=question_id,
        draft_digest=canonical_hash(draft),
        claims=(claim,),
        basis_links=(
            ClaimBasisLink(
                scope=bundle.scope,
                compilation_id=compilation.compilation_id,
                claim_id="local",
                authority_ref=basis,
                proposition=text,
                use=use,
            ),
        ),
        block_accounts=(
            BlockClaimAccount(
                block_id="public",
                block_text_digest=canonical_hash(draft.blocks[0].text),
                claim_ids=("local",),
            ),
        ),
    )
    return draft, extraction, plan


def test_real_citation_wrong_proposition_or_target_fails_firewall(report_case, compilation):
    from novelty_harness.reporting.firewall import check_report_claims

    bundle = report_case.bundle
    draft, extraction, plan = claim_case(bundle, compilation)
    other = next(
        e
        for e in bundle.language_envelopes
        if e.target != extraction.claims[0].target_scopes[0].target
    )
    from novelty_harness.reporting.claims import ClaimTarget

    rebound = extraction.model_copy(
        update={
            "claims": (
                extraction.claims[0].model_copy(
                    update={
                        "target_scopes": (
                            ClaimTarget(target=other.target, claim_scope=other.claim_scope),
                        )
                    }
                ),
            )
        }
    )
    result = check_report_claims(draft, rebound, bundle, plan)
    assert result.accepted is False
    assert "BASIS_SCOPE_MISMATCH" in result.reason_codes
    assert result.violations[0].block_id == "public"
    assert bundle.target_findings == report_case.frozen.target_findings
    # Real membership alone cannot establish this arbitrary assertion's entailment.
    valid = check_report_claims(draft, extraction, bundle, plan)
    assert valid.accepted
    assert not hasattr(valid, "semantically_supported")


def test_firewall_rejects_structured_verdict_gate_and_value_override(report_case, compilation):
    from novelty_harness.reporting.firewall import check_report_claims

    draft, extraction, plan = claim_case(
        report_case.bundle,
        compilation,
        question_id=6,
        category="VALUE_CLAIM",
        text="This is a measured advantage",
    )
    result = check_report_claims(draft, extraction, report_case.bundle, plan)
    assert not result.accepted
    assert "NO_ASSESSED_VALUE_BASIS" in result.reason_codes
    for key in (
        "verdict_override",
        "gate_mutation",
        "qualification_grant",
        "value_maturity",
        "novelty_score",
    ):
        with pytest.raises(ValidationError):
            type(extraction.claims[0]).model_validate(
                {**extraction.claims[0].model_dump(mode="json"), key: "invented"}
            )


def test_firewall_rejects_source_stitch_and_universal_absence_intents(report_case, compilation):
    from novelty_harness.reporting.firewall import check_report_claims

    for text, reason in (
        (
            "Sources stitched together establish one direct combination precedent",
            "SOURCE_STITCHING",
        ),
        ("No prior art exists anywhere", "UNIVERSAL_ABSENCE"),
    ):
        draft, extraction, plan = claim_case(report_case.bundle, compilation, text=text)
        result = check_report_claims(draft, extraction, report_case.bundle, plan)
        assert not result.accepted
        assert reason in result.reason_codes


@pytest.mark.parametrize("attack", ["url", "metadata"])
def test_firewall_rejects_free_url_and_metadata_only_passage_basis(
    report_case, compilation, attack
):
    from novelty_harness.reporting.firewall import check_report_claims

    if attack == "url":
        draft, extraction, plan = claim_case(
            report_case.bundle, compilation, text="Evidence at javascript:invented()"
        )
        reason = "UNSAFE_PUBLIC_TEXT"
    else:
        basis = next(
            d.authority_ref
            for d in report_case.bundle.dependency_manifest
            if d.authority_ref.kind == AuthorityKind.SOURCE
        )
        target = next(
            e for e in report_case.bundle.language_envelopes if e.target.id == "mcu_control"
        )
        draft, extraction, plan = claim_case(
            report_case.bundle, compilation, basis=basis, target=target
        )
        reason = "CITATION_NOT_COMMITTED_PASSAGE"
    result = check_report_claims(draft, extraction, report_case.bundle, plan)
    assert not result.accepted
    assert reason in result.reason_codes


def test_overall_classes_do_not_authorize_foreign_target(report_case, compilation):
    from novelty_harness.domain.enums import VerdictState
    from novelty_harness.reporting.firewall import check_report_claims

    target = next(
        e for e in report_case.bundle.language_envelopes if e.verdict == VerdictState.UNASSESSABLE
    )
    draft, extraction, plan = claim_case(
        report_case.bundle,
        compilation,
        question_id=4,
        category="POTENTIAL_NOVELTY_CLAIM",
        target=target,
    )
    result = check_report_claims(draft, extraction, report_case.bundle, plan)
    assert not result.accepted
    assert "TARGET_PERMISSION_EXCEEDED" in result.reason_codes


def test_right_title_wrong_version_fails(report_case, compilation):
    from novelty_harness.reporting.firewall import check_report_claims

    draft, extraction, plan = claim_case(report_case.bundle, compilation)
    real = extraction.claims[0].basis_candidates[0]
    rebound = real.model_copy(update={"digest": "b" * 64})
    changed = extraction.model_copy(
        update={
            "claims": (
                extraction.claims[0].model_copy(
                    update={"basis_candidates": (rebound,), "citation_candidates": (rebound,)}
                ),
            ),
            "basis_links": (
                extraction.basis_links[0].model_copy(update={"authority_ref": rebound}),
            ),
        }
    )
    result = check_report_claims(draft, changed, report_case.bundle, plan)
    assert not result.accepted
    assert "BASIS_DIGEST_MISMATCH" in result.reason_codes
    assert real.native_id == rebound.native_id


def test_supported_score_cannot_override_rejection(report_case, compilation):
    from novelty_harness.reporting.firewall import check_report_claims

    draft, extraction, plan = claim_case(
        report_case.bundle, compilation, text="No prior art exists anywhere"
    )
    result = check_report_claims(draft, extraction, report_case.bundle, plan)
    with pytest.raises(ValidationError):
        type(result).model_validate({**result.model_dump(mode="json"), "supported_score": 1.0})
    with pytest.raises(ValidationError):
        type(result).model_validate({**result.model_dump(mode="json"), "accepted": True})


def test_missing_obligation_annotations_are_not_silently_accepted(report_case, compilation):
    from novelty_harness.reporting.firewall import check_report_claims

    draft, extraction, plan = claim_case(report_case.bundle, compilation)
    draft = draft.model_copy(
        update={"blocks": (draft.blocks[0].model_copy(update={"obligation_ids": ()}),)}
    )
    extraction = extraction.model_copy(update={"draft_digest": canonical_hash(draft)})
    result = check_report_claims(draft, extraction, report_case.bundle, plan)
    assert not result.accepted
    assert "MISSING_OBLIGATION_LINK" in result.reason_codes


def test_foreign_reference_scope_and_stale_text_fail_closed(report_case, compilation):
    from novelty_harness.reporting.firewall import check_report_claims

    draft, extraction, plan = claim_case(report_case.bundle, compilation)
    changed = extraction.model_copy(update={"draft_digest": "b" * 64})
    result = check_report_claims(draft, changed, report_case.bundle, plan)
    assert not result.accepted
    assert "INVALID_EXTRACTION" in result.reason_codes
    result = check_report_claims(
        draft, extraction, report_case.bundle, plan.model_copy(update={"bundle_digest": "b" * 64})
    )
    assert not result.accepted
    assert "PLAN_SCOPE_MISMATCH" in result.reason_codes


@pytest.mark.parametrize(
    "attack,reason", [("basis", "MISSING_CLAIM_BASIS"), ("link", "MISSING_BASIS_LINK")]
)
def test_material_claim_needs_explicit_basis_mapping(report_case, compilation, attack, reason):
    from novelty_harness.reporting.firewall import check_report_claims

    draft, extraction, plan = claim_case(report_case.bundle, compilation)
    changes = {"basis_links": ()}
    if attack == "basis":
        changes["claims"] = (
            extraction.claims[0].model_copy(
                update={"basis_candidates": (), "citation_candidates": ()}
            ),
        )
    extraction = extraction.model_copy(update=changes)
    result = check_report_claims(draft, extraction, report_case.bundle, plan)
    assert not result.accepted
    assert reason in result.reason_codes


def test_normalized_hint_cannot_hide_known_unsafe_public_text(report_case, compilation):
    from novelty_harness.reporting.firewall import check_report_claims

    draft, extraction, plan = claim_case(
        report_case.bundle, compilation, text="No prior art exists anywhere"
    )
    extraction = extraction.model_copy(
        update={
            "claims": (
                extraction.claims[0].model_copy(
                    update={"normalized_assertion": "A scoped source description"}
                ),
            )
        }
    )
    result = check_report_claims(draft, extraction, report_case.bundle, plan)
    assert not result.accepted
    assert "UNIVERSAL_ABSENCE" in result.reason_codes


def test_firewall_artifact_recomputes_exact_committed_inputs(report_case, compilation):
    from novelty_harness.reporting.artifacts import ReportArtifactKind, make_report_artifact
    from novelty_harness.reporting.firewall import check_report_claims
    from novelty_harness.reporting.repository import ReportAuthorityError

    draft, extraction, plan = claim_case(report_case.bundle, compilation)
    result = check_report_claims(draft, extraction, report_case.bundle, plan)
    for kind, document, method in (
        (ReportArtifactKind.PLAN, plan, "p8-plan-firewall-v1"),
        (ReportArtifactKind.DRAFT, draft, "p8-write-v1"),
        (ReportArtifactKind.EXTRACTION, extraction, "p8-extract-v1"),
        (ReportArtifactKind.FIREWALL, result, "p8-semantic-firewall-v1"),
    ):
        artifact = make_report_artifact(compilation, kind, document, method_version=method)
        assert (
            report_case.repository.record_report_artifact(compilation.compilation_id, artifact)
            == artifact.artifact_id
        )
    assert artifact.question_id == 2
    changed = result.model_copy(update={"permission_digest": "b" * 64})
    bad = make_report_artifact(
        compilation, ReportArtifactKind.FIREWALL, changed, method_version="p8-semantic-firewall-v1"
    )
    with pytest.raises(ReportAuthorityError):
        report_case.repository.record_report_artifact(compilation.compilation_id, bad)
    assert artifact in report_case.repository.load_report_artifacts(compilation.compilation_id)


@pytest.mark.parametrize(
    ("question_id", "category", "text"),
    [
        (3, "SOURCE_FACT", "The established component uses the admitted mechanism."),
        (
            3,
            "NOVELTY_INTERPRETATION",
            "The accepted target state retains its attached limitations.",
        ),
        (4, "EQUIVALENCE_DESCRIPTION", "The admitted comparison retains its residual differences."),
        (4, "SOURCE_FACT", "The admitted source describes the compared component."),
        (
            6,
            "NOVELTY_INTERPRETATION",
            "The accepted contribution state establishes no measured advantage.",
        ),
        (
            9,
            "NOVELTY_INTERPRETATION",
            "The accepted target state accompanies its remaining limitations.",
        ),
        (
            9,
            "EQUIVALENCE_DESCRIPTION",
            "The comparison residual remains relevant to the stated uncertainty.",
        ),
        (9, "SOURCE_FACT", "The cited source record retains its chronology limitation."),
    ],
)
def test_question_retains_explanatory_basis_without_new_permission(
    report_case, compilation, question_id, category, text
):
    from novelty_harness.reporting.firewall import check_report_claims

    draft, extraction, plan = claim_case(
        report_case.bundle, compilation, question_id=question_id, category=category, text=text
    )
    result = check_report_claims(draft, extraction, report_case.bundle, plan)
    assert result.accepted
    assert not hasattr(result, "semantically_supported")
    # Passing the structural routing gate cannot establish arbitrary entailment.
    assert report_case.bundle.target_findings == report_case.frozen.target_findings


def test_explicit_overbroad_example_has_no_asserted_target(report_case, compilation):
    from novelty_harness.reporting.claims import ClaimExtractionProposal
    from novelty_harness.reporting.firewall import check_report_claims

    draft, extraction, plan = claim_case(
        report_case.bundle,
        compilation,
        question_id=8,
        category="NEGATIVE_CLAIM",
        text="Unsupported example to avoid: No prior art exists anywhere.",
        use="DISALLOWED_WORDING_EXAMPLE",
    )
    payload = extraction.model_dump(mode="json")
    payload["claims"][0]["target_scopes"] = []
    extraction = ClaimExtractionProposal.model_validate(payload)
    result = check_report_claims(draft, extraction, report_case.bundle, plan)
    assert result.accepted
    assert not hasattr(result, "semantically_supported")
