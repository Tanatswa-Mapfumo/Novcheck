"""Text accounting is mechanical and never certifies material completeness."""

import pytest
from pydantic import ValidationError

from novelty_harness.reporting.drafts import DraftBlock, SectionDraft
from novelty_harness.reporting.models import AuthorityRef, ReportProposalError
from novelty_harness.runtime.tracing.hashing import canonical_hash
from tests.fixtures.phase8 import report_scope
from tests.unit.reporting.test_drafts import context_for
from tests.unit.reporting.test_obligations import report_case as _report_case
from tests.unit.reporting.test_plan import compilation as _compilation

report_case = _report_case
compilation = _compilation


def public_draft():
    return SectionDraft(
        scope=report_scope(),
        compilation_id="p8run_shapes",
        question_id=2,
        blocks=(
            DraftBlock(block_id="heading", kind="HEADING", text="Stored component facts"),
            DraftBlock(
                block_id="cell-x",
                kind="TABLE_CELL",
                text="Source A describes X",
                table_id="t",
                row=0,
                column=0,
            ),
            DraftBlock(
                block_id="cell-y",
                kind="TABLE_CELL",
                text="Source B describes Y",
                table_id="t",
                row=0,
                column=1,
            ),
            DraftBlock(
                block_id="causal", kind="PARAGRAPH", text="X is established; R remains a candidate."
            ),
            DraftBlock(block_id="list", kind="LIST_ITEM", text="Café 🔬 uses a controller"),
            DraftBlock(block_id="caption", kind="CAPTION", text="Admitted source mappings"),
            DraftBlock(
                block_id="absence", kind="PARAGRAPH", text="The remaining unexplored configuration"
            ),
        ),
    )


def extraction_for(draft):
    from novelty_harness.reporting.claims import (
        BlockClaimAccount,
        ClaimBasisLink,
        ClaimExtractionProposal,
        ReportClaim,
        TextSpan,
    )

    reference = AuthorityRef(
        scope=draft.scope, kind="PASSAGE", native_id="pas_shapes", digest="a" * 64
    )
    claims, accounts, links = [], [], []
    for block in draft.blocks:
        spans = (
            ((0, 16), (18, len(block.text)))
            if block.block_id == "causal"
            else ((0, len(block.text)),)
        )
        ids = []
        for index, (start, end) in enumerate(spans):
            label = f"{block.block_id}-{index}"
            ids.append(label)
            claims.append(
                ReportClaim(
                    scope=draft.scope,
                    compilation_id=draft.compilation_id,
                    claim_id=label,
                    block_id=block.block_id,
                    block_text_digest=canonical_hash(block.text),
                    spans=(TextSpan(start=start, end=end),),
                    normalized_assertion=block.text[start:end],
                    category="SOURCE_FACT",
                    use="ASSERTION",
                    target_scopes=(),
                    basis_candidates=(reference,),
                    citation_candidates=(reference,),
                    required_qualification_refs=(),
                )
            )
            links.append(
                ClaimBasisLink(
                    scope=draft.scope,
                    compilation_id=draft.compilation_id,
                    claim_id=label,
                    authority_ref=reference,
                    proposition=block.text[start:end],
                    use="ASSERTION",
                )
            )
        accounts.append(
            BlockClaimAccount(
                block_id=block.block_id,
                block_text_digest=canonical_hash(block.text),
                claim_ids=tuple(ids),
            )
        )
    return ClaimExtractionProposal(
        scope=draft.scope,
        compilation_id=draft.compilation_id,
        question_id=draft.question_id,
        draft_digest=canonical_hash(draft),
        claims=tuple(claims),
        basis_links=tuple(links),
        block_accounts=tuple(accounts),
    )


def test_extraction_accounts_actual_text_including_heading_and_table():
    from novelty_harness.reporting.claims import validate_claim_extraction

    draft = public_draft()
    proposal = extraction_for(draft)
    checked = validate_claim_extraction(draft, proposal)
    assert {a.block_id for a in checked.block_accounts} == {b.block_id for b in draft.blocks}
    assert len(checked.claims) == 8
    texts = {b.block_id: b.text for b in draft.blocks}
    assert all(
        texts[c.block_id][s.start : s.end] == c.normalized_assertion
        for c in checked.claims
        for s in c.spans
    )
    assert all(c.claim_id.startswith("p8claim_") for c in checked.claims)
    assert {link.claim_id for link in checked.basis_links} == {c.claim_id for c in checked.claims}
    assert {
        c.claim_id
        for a in checked.block_accounts
        for c in checked.claims
        if c.claim_id in a.claim_ids
    } == {c.claim_id for c in checked.claims}
    changed = draft.model_copy(
        update={
            "blocks": (
                draft.blocks[0].model_copy(update={"text": "Changed heading"}),
                *draft.blocks[1:],
            )
        }
    )
    with pytest.raises(ReportProposalError):
        validate_claim_extraction(changed, proposal)


def test_empty_extraction_does_not_self_certify_safe_draft():
    from novelty_harness.reporting.claims import (
        BlockClaimAccount,
        ClaimExtractionProposal,
        validate_claim_extraction,
    )

    draft = public_draft()
    proposal = ClaimExtractionProposal(
        scope=draft.scope,
        compilation_id=draft.compilation_id,
        question_id=draft.question_id,
        draft_digest=canonical_hash(draft),
        claims=(),
        basis_links=(),
        block_accounts=tuple(
            BlockClaimAccount(
                block_id=b.block_id,
                block_text_digest=canonical_hash(b.text),
                claim_ids=(),
                non_material_reason="Extractor proposes connective text",
            )
            for b in draft.blocks
        ),
    )
    checked = validate_claim_extraction(draft, proposal)
    assert checked.claims == ()
    assert not hasattr(checked, "complete")
    assert not hasattr(checked, "accepted")
    assert not hasattr(checked, "supported")
    with pytest.raises(ValidationError):
        ClaimExtractionProposal.model_validate(
            {**proposal.model_dump(mode="json"), "complete": True}
        )


def test_extractor_hints_do_not_certify_material_completeness():
    from novelty_harness.reporting.claims import validate_claim_extraction

    checked = validate_claim_extraction(public_draft(), extraction_for(public_draft()))
    assert checked.basis_links
    assert not hasattr(checked.basis_links[0], "supported")
    assert not hasattr(checked.claims[0], "entails")
    with pytest.raises(ValidationError):
        type(checked.claims[0]).model_validate(
            {**checked.claims[0].model_dump(mode="json"), "confidence": 0.99}
        )


@pytest.mark.parametrize(
    "attack",
    ["unicode_bounds", "duplicate", "account_missing", "account_duplicate", "swapped_cells"],
)
def test_unicode_spans_and_duplicate_claims_fail_closed(attack):
    from novelty_harness.reporting.claims import TextSpan, validate_claim_extraction

    draft = public_draft()
    proposal = extraction_for(draft)
    if attack == "unicode_bounds":
        claim = next(c for c in proposal.claims if c.block_id == "list")
        altered = claim.model_copy(
            update={"spans": (TextSpan(start=0, end=len(draft.blocks[4].text.encode("utf-8"))),)}
        )
        proposal = proposal.model_copy(
            update={"claims": tuple(altered if c == claim else c for c in proposal.claims)}
        )
    elif attack == "duplicate":
        proposal = proposal.model_copy(update={"claims": (*proposal.claims, proposal.claims[0])})
    elif attack == "account_missing":
        proposal = proposal.model_copy(update={"block_accounts": proposal.block_accounts[1:]})
    elif attack == "account_duplicate":
        proposal = proposal.model_copy(
            update={"block_accounts": (*proposal.block_accounts, proposal.block_accounts[0])}
        )
    else:
        cells = draft.blocks[1:3]
        draft = draft.model_copy(
            update={
                "blocks": (
                    draft.blocks[0],
                    cells[0].model_copy(update={"text": cells[1].text}),
                    cells[1].model_copy(update={"text": cells[0].text}),
                    *draft.blocks[3:],
                )
            }
        )
    with pytest.raises(ReportProposalError):
        validate_claim_extraction(draft, proposal)


def test_stale_block_digest_after_repair_rejected():
    from novelty_harness.reporting.claims import validate_claim_extraction

    draft = public_draft()
    proposal = extraction_for(draft)
    changed = draft.model_copy(
        update={
            "blocks": (
                draft.blocks[0].model_copy(update={"text": "Repaired heading"}),
                *draft.blocks[1:],
            )
        }
    )
    # Updating the outer digest cannot rescue stale independent block accounting.
    with pytest.raises(ReportProposalError):
        validate_claim_extraction(
            changed, proposal.model_copy(update={"draft_digest": canonical_hash(changed)})
        )


def test_disallowed_example_tag_not_an_authority_grant():
    from novelty_harness.reporting.claims import ClaimUse, validate_claim_extraction

    draft = public_draft()
    proposal = extraction_for(draft)
    changed = proposal.model_copy(
        update={
            "claims": tuple(
                c.model_copy(update={"use": ClaimUse.DISALLOWED_WORDING_EXAMPLE})
                for c in proposal.claims
            )
        }
    )
    checked = validate_claim_extraction(draft, changed)
    assert all(c.use == "DISALLOWED_WORDING_EXAMPLE" for c in checked.claims)
    assert not hasattr(checked, "accepted")


def test_extraction_context_has_actual_public_text_and_no_writer_certification(
    report_case, compilation
):
    from novelty_harness.reporting.claims import build_claim_extraction_context
    from tests.unit.reporting.test_drafts import draft_for

    section = context_for(report_case.bundle, compilation)
    draft = draft_for(section)
    context = build_claim_extraction_context(draft, section)
    assert context.draft == draft
    assert context.draft_digest == canonical_hash(draft)
    assert context.authority == section.authority
    assert context.language_envelopes == section.language_envelopes
    assert not hasattr(context, "writer_reasoning")
    assert not hasattr(context, "supported")
    assert not hasattr(context, "repository")


def test_claim_ids_are_canonical_and_local_labels_rejoin_exactly():
    from novelty_harness.reporting.claims import validate_claim_extraction

    draft = public_draft()
    checked = validate_claim_extraction(draft, extraction_for(draft))
    data = checked.model_dump(mode="json")
    labels = {c["claim_id"]: f"label-{index}" for index, c in enumerate(data["claims"])}
    for claim in data["claims"]:
        claim["claim_id"] = labels[claim["claim_id"]]
    for link in data["basis_links"]:
        link["claim_id"] = labels[link["claim_id"]]
    for account in data["block_accounts"]:
        account["claim_ids"] = [labels[c] for c in account["claim_ids"]]
    renamed = type(checked).model_validate(data)
    assert validate_claim_extraction(draft, renamed) == checked


def test_extraction_cannot_attach_foreign_basis_link_or_scope():
    from novelty_harness.reporting.claims import validate_claim_extraction

    draft = public_draft()
    proposal = extraction_for(draft)
    foreign = proposal.basis_links[0].model_copy(update={"claim_id": "nonexistent"})
    with pytest.raises(ReportProposalError):
        validate_claim_extraction(
            draft, proposal.model_copy(update={"basis_links": (foreign, *proposal.basis_links[1:])})
        )
    with pytest.raises(ReportProposalError):
        validate_claim_extraction(draft, proposal.model_copy(update={"compilation_id": "foreign"}))


def test_extraction_artifact_binds_actual_committed_draft(report_case, compilation):
    from novelty_harness.reporting.artifacts import ReportArtifactKind, make_report_artifact
    from novelty_harness.reporting.plan import build_coverage_plan
    from novelty_harness.reporting.repository import ReportAuthorityError
    from tests.unit.reporting.test_drafts import draft_for

    context = context_for(report_case.bundle, compilation)
    draft = draft_for(context)
    proposal = extraction_for(draft)
    plan = build_coverage_plan(report_case.bundle, compilation)
    for kind, document, method in (
        (ReportArtifactKind.PLAN, plan, "p8-plan-firewall-v1"),
        (ReportArtifactKind.DRAFT, draft, "p8-write-v1"),
        (ReportArtifactKind.EXTRACTION, proposal, "p8-extract-v1"),
    ):
        artifact = make_report_artifact(compilation, kind, document, method_version=method)
        assert (
            report_case.repository.record_report_artifact(compilation.compilation_id, artifact)
            == artifact.artifact_id
        )
    assert artifact.question_id == draft.question_id
    assert artifact in report_case.repository.load_report_artifacts(compilation.compilation_id)
    changed = proposal.model_copy(update={"draft_digest": "b" * 64})
    bad = make_report_artifact(
        compilation, ReportArtifactKind.EXTRACTION, changed, method_version="p8-extract-v1"
    )
    with pytest.raises(ReportAuthorityError):
        report_case.repository.record_report_artifact(compilation.compilation_id, bad)
