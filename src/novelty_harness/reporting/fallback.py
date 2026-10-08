"""Pinned, complete deterministic transformations of authoritative report inputs."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, JsonValue

from novelty_harness.adjudication.roles import DefenseCase, ProsecutionCase
from novelty_harness.domain.reporting import CANONICAL_QUESTIONS
from novelty_harness.evidence.passages.models import PassageRecord
from novelty_harness.reporting.bundle import ReportInputBundle, native_ref
from novelty_harness.reporting.claims import (
    ClaimBasisLink,
    ClaimTarget,
    ClaimUse,
    ReportClaim,
    TextSpan,
    report_claim_id,
)
from novelty_harness.reporting.drafts import CitationToken, DraftBlock, SectionDraft
from novelty_harness.reporting.models import (
    AuthorityKind,
    AuthorityRef,
    Digest,
    QuestionId,
    ReportClaimCategory,
    ReportProposalError,
    ReportScoped,
)
from novelty_harness.reporting.obligations import ObligationSatisfaction
from novelty_harness.reporting.recommendations import minimum_validation_requirements
from novelty_harness.reporting.uncertainty import project_uncertainty
from novelty_harness.reporting.verification import VerifiedSection
from novelty_harness.reporting.wording import safe_claim_wording
from novelty_harness.runtime.tracing.hashing import canonical_hash

if TYPE_CHECKING:
    from novelty_harness.reporting.artifacts import ReportCompilationRecord

FALLBACK_VERSION = "p8-fallback-v1"


class FallbackRecord(ReportScoped):
    contract_kind: Literal["phase8-fallback-record-v1"] = "phase8-fallback-record-v1"
    question_id: QuestionId
    bundle_digest: Digest
    method_version: Literal["p8-fallback-v1"] = FALLBACK_VERSION
    section: VerifiedSection


def attributed_text(label: str, text: str) -> str:
    """Quote text as data; prevent markup, citation definitions and URI activation."""
    inert = text.translate(
        str.maketrans(
            {
                "<": "＜",
                ">": "＞",
                "[": "［",
                "]": "］",
                ":": "：",
                "#": "＃",
                "!": "！",
                "\n": r"\n",
                "\r": r"\r",
                "\t": r"\t",
            }
        )
    )
    return f'{label} (quoted record): "{inert}"'


def _record_text(label: str, document: BaseModel) -> str:
    """Display public recorded fields, never execution or observational provenance."""
    excluded = {
        "schema_version",
        "contract_kind",
        "provenance",
        "model_provenance",
        "observed_at",
        "frozen_at",
        "completed_at",
        "started_at",
        "prompt_version",
        "assessment_id",
        "assessment_context_id",
        "phase6_snapshot_id",
        "execution_ref",
        "instruction_hash",
        "request_hash",
        "raw_response_hash",
    }

    def public(value: JsonValue) -> JsonValue:
        if isinstance(value, dict):
            return {k: public(v) for k, v in value.items() if k not in excluded}
        if isinstance(value, list):
            return [public(v) for v in value]
        return value

    data = public(document.model_dump(mode="json"))
    return attributed_text(label, json.dumps(data, ensure_ascii=False, sort_keys=True))


def passage_text(passage: PassageRecord) -> str:
    """Display the admitted excerpt and locator without expanding into its parent."""
    retrieved_at = passage.attestation.parent.retrieved_at if passage.attestation else None
    data: dict[str, JsonValue] = {
        "passage_id": passage.passage_id,
        "source_id": passage.source_id,
        "source_version_id": passage.source_version_id,
        "text": passage.text,
        "locator": passage.locator.model_dump(mode="json"),
        "content_hash": passage.content_hash,
        "access_state": passage.access_state.value,
        "limitations": list(passage.limitations),
        "retrieved_at": retrieved_at.isoformat() if retrieved_at is not None else None,
    }
    return attributed_text(
        "Verifier-cited passage and locator", json.dumps(data, ensure_ascii=False, sort_keys=True)
    )


def render_fallback_section(
    bundle: ReportInputBundle,
    compilation: ReportCompilationRecord,
    *,
    question_id: QuestionId,
    obligation_ids: tuple[str, ...] | None = None,
) -> VerifiedSection:
    """Render a complete question; a partial request never drops its closure."""
    if compilation.scope != bundle.scope or compilation.bundle_digest != bundle.bundle_digest:
        raise ReportProposalError("fallback scope or upstream bundle differs")
    if question_id not in range(1, 10):
        raise ReportProposalError("fallback question differs")
    return _render_fallback_for_run(bundle, compilation.compilation_id, question_id, obligation_ids)


def _render_fallback_for_run(
    bundle: ReportInputBundle,
    run_id: str,
    question_id: QuestionId,
    obligation_ids: tuple[str, ...] | None = None,
) -> VerifiedSection:
    obligations = tuple(o for o in bundle.coverage_obligations if question_id in o.question_ids)
    if obligation_ids is not None and not set(obligation_ids) <= {
        o.obligation_id for o in obligations
    }:
        raise ReportProposalError("fallback selection contains a foreign obligation")
    blocks: list[DraftBlock] = []
    claims: list[ReportClaim] = []
    links: list[ClaimBasisLink] = []
    homes: dict[str, list[str]] = {o.obligation_id: [] for o in obligations}
    claim_homes: dict[str, list[str]] = {o.obligation_id: [] for o in obligations}
    catalog = tuple(d.authority_ref for d in bundle.dependency_manifest if d.authority_ref)

    def add(
        text: str,
        refs: tuple[AuthorityRef, ...],
        category: ReportClaimCategory,
        *,
        use: ClaimUse = ClaimUse.ASSERTION,
        obligation_links: tuple[str, ...] = (),
        heading: bool = False,
    ) -> None:
        if not refs or not set(refs) <= set(catalog):
            raise ReportProposalError("fallback basis lacks exact admitted authority")
        identifier = "p8block_" + canonical_hash(
            {
                "scope": bundle.scope.model_dump(mode="json"),
                "compilation": run_id,
                "question": question_id,
                "index": len(blocks),
                "text": text,
            }
        )
        citations = tuple(r for r in refs if r.kind == AuthorityKind.PASSAGE)
        block = DraftBlock(
            block_id=identifier,
            kind="HEADING" if heading else "PARAGRAPH",
            text=text,
            basis_candidate_refs=refs,
            obligation_ids=obligation_links,
            citation_tokens=tuple(
                CitationToken(offset=len(text), authority_ref=r) for r in citations
            ),
        )
        targets = tuple(
            ClaimTarget(target=e.target, claim_scope=e.claim_scope)
            for e in bundle.language_envelopes
            if any(r.target == e.target for r in refs)
        )
        claim = ReportClaim(
            scope=bundle.scope,
            compilation_id=run_id,
            claim_id="pending",
            block_id=identifier,
            block_text_digest=canonical_hash(text),
            spans=(TextSpan(start=0, end=len(text)),),
            normalized_assertion=text,
            category=category,
            use=use,
            target_scopes=targets,
            basis_candidates=refs,
            citation_candidates=citations,
        )
        claim = claim.model_copy(update={"claim_id": report_claim_id(claim)})
        blocks.append(block)
        claims.append(claim)
        links.extend(
            ClaimBasisLink(
                scope=bundle.scope,
                compilation_id=run_id,
                claim_id=claim.claim_id,
                authority_ref=ref,
                proposition=text,
                use=use,
            )
            for ref in refs
        )
        for oid in obligation_links:
            homes[oid].append(identifier)
            claim_homes[oid].append(claim.claim_id)

    frozen_ref = native_ref(bundle, AuthorityKind.FROZEN)
    add(
        CANONICAL_QUESTIONS[question_id - 1],
        (frozen_ref,),
        ReportClaimCategory.INPUT_DESCRIPTION,
        heading=True,
    )
    if question_id == 1:
        add(
            _record_text("Sealed input", bundle.cir),
            (native_ref(bundle, AuthorityKind.CIR),),
            ReportClaimCategory.INPUT_DESCRIPTION,
            use=ClaimUse.ATTRIBUTED_INPUT_CLAIM,
        )
        add(
            _record_text("Reconciled configuration", bundle.graph_or_version),
            (next(r for r in catalog if r.kind == AuthorityKind.GRAPH),),
            ReportClaimCategory.INPUT_DESCRIPTION,
            use=ClaimUse.ATTRIBUTED_INPUT_CLAIM,
        )
    if question_id == 1:
        for profile in bundle.target_profiles:
            ref = native_ref(bundle, AuthorityKind.TARGET, native_id=profile.target_id)
            oid = tuple(
                o.obligation_id
                for o in obligations
                if o.requirement_kind == "TARGET_REPRESENTATION"
                and o.target is not None
                and o.target.id == profile.target_id
            )
            add(
                _record_text("Assessed input target", profile),
                (ref,),
                ReportClaimCategory.INPUT_DESCRIPTION,
                obligation_links=oid,
                use=ClaimUse.ATTRIBUTED_INPUT_CLAIM,
            )
    if question_id in {3, 4, 8, 9}:
        for wording in safe_claim_wording(bundle):
            finding = next(f for f in bundle.target_findings if f.target_id == wording.target.id)
            oid = tuple(
                o.obligation_id
                for o in obligations
                if o.target == wording.target
                and o.requirement_kind
                in {
                    "TARGET_REPRESENTATION",
                    "SCOPED_NEGATIVE",
                    "SURVIVING_CANDIDATE",
                    "LANGUAGE_CEILING",
                }
            )
            text = (
                f"Accepted target {finding.target_id}: {finding.verdict.value}. "
                + attributed_text("Defensible wording", wording.wording_text)
                + " "
                + " ".join(
                    attributed_text("Attached limitation", limitation)
                    for limitation in wording.necessary_limitations
                )
            )
            add(
                text,
                tuple(dict.fromkeys((*wording.basis_refs, *wording.permission_refs))),
                ReportClaimCategory.NOVELTY_INTERPRETATION,
                obligation_links=oid,
            )
    if question_id in {2, 3, 4, 5, 9}:
        for comparison in bundle.eligible_comparisons:
            cls = comparison.comparison.classification
            ref = native_ref(bundle, AuthorityKind.COMPARISON, native_id=cls.classification_id)
            related = tuple(
                r
                for r in catalog
                if r.kind == AuthorityKind.PASSAGE
                and comparison.commit_id in r.path
                and cls.classification_id in r.path
            )
            relation_refs = tuple(
                r
                for r in catalog
                if r.kind == AuthorityKind.GRAPH_RELATION
                and r.native_id in comparison.graph_edge_ids
            )
            refs = (ref, *related, *relation_refs)
            verification = comparison.comparison.comparison
            text = (
                f"Recorded comparison {cls.classification_id}: {cls.relation.value}; "
                f"projection {comparison.projection_status}. "
                + _record_text("Classification and complete residual", cls)
                + " "
                + _record_text("Chronology", verification.chronology)
                + " "
                + _record_text(
                    "Verified support and unsupported remainder", verification.chain.verification
                )
                + " "
                + _record_text(
                    "Proposition and relationship topology", verification.chain.proposition
                )
            )
            oid = tuple(
                o.obligation_id
                for o in obligations
                if o.requirement_kind == "DECISIVE_PRECEDENT" and set(refs) & set(o.authority_refs)
            )
            add(text, refs, ReportClaimCategory.EQUIVALENCE_DESCRIPTION, obligation_links=oid)
            for cited in comparison.cited_passages:
                passage_refs = tuple(r for r in related if r.native_id == cited.passage.passage_id)
                add(
                    passage_text(cited.passage),
                    (ref, *passage_refs),
                    ReportClaimCategory.SOURCE_FACT,
                    use=ClaimUse.ATTRIBUTED_INPUT_CLAIM,
                )
        for metadata in bundle.source_metadata:
            refs = (metadata.source_ref, *((metadata.version_ref,) if metadata.version_ref else ()))
            text = (
                _record_text("Stored source metadata", metadata.source)
                + " "
                + (
                    _record_text("Stored version metadata", metadata.version)
                    if metadata.version
                    else "Versionless page; no version record is available."
                )
                + f" Cutoff: {bundle.as_of.isoformat()}; "
                + f"missing metadata: {metadata.missing_fields}. "
                + "Metadata does not establish proposition support or independent evidence."
            )
            add(text, refs, ReportClaimCategory.SOURCE_FACT, use=ClaimUse.ATTRIBUTED_INPUT_CLAIM)
    if question_id in {3, 4, 6, 8}:
        for gate in sorted(bundle.gate_findings, key=lambda g: (g.target_id, g.contract_kind)):
            if question_id == 6 and gate.contract_kind != "phase7-gate-d-finding-v1":
                continue
            add(
                _record_text("Accepted Gate state (not measured advantage)", gate),
                (native_ref(bundle, AuthorityKind.GATE, native_id=gate.gate_id),),
                ReportClaimCategory.NOVELTY_INTERPRETATION,
            )
        for counterfactual in sorted(bundle.counterfactuals, key=lambda c: c.target_id):
            add(
                _record_text(
                    "Counterfactual diagnostic; unresolved fields remain unresolved", counterfactual
                ),
                (
                    native_ref(
                        bundle,
                        AuthorityKind.COUNTERFACTUAL,
                        native_id=counterfactual.localization_id,
                    ),
                ),
                ReportClaimCategory.UNCERTAINTY_CLAIM,
            )
    if question_id == 5:
        closure = bundle.judge_resolutions_and_limitations
        accepted = {
            i
            for r in closure.judge_resolutions
            if r.resolved_semantics
            for i in r.resolved_semantics.accepted_challenge_ids
        }
        if not accepted:
            add(
                "No independently accepted challenge is recorded; verified comparisons and "
                "frozen limitations above retain their exact scope.",
                (frozen_ref,),
                ReportClaimCategory.NOVELTY_INTERPRETATION,
            )
        for case in sorted(closure.role_cases, key=lambda c: (c.target_id, c.contract_kind)):
            if isinstance(case, DefenseCase):
                ref = native_ref(bundle, AuthorityKind.ROLE, native_id=case.case_id)
                for point in case.points:
                    add(
                        f"Recorded defense disposition: {point.disposition}. "
                        + attributed_text("Recorded defense", point.thesis)
                        + " "
                        + _record_text("Defense position and attached limits", point),
                        (ref,),
                        ReportClaimCategory.NOVELTY_INTERPRETATION,
                    )
            if not isinstance(case, ProsecutionCase):
                continue
            ref = native_ref(bundle, AuthorityKind.ROLE, native_id=case.case_id)
            add(
                _record_text(
                    "Prosecution position; accepted challenge IDs "
                    + str(sorted(accepted))
                    + "; other arguments are not promoted to accepted",
                    case,
                ),
                (ref,),
                ReportClaimCategory.NOVELTY_INTERPRETATION,
            )
    if question_id == 6:
        for value in bundle.value_projection:
            oid = tuple(
                o.obligation_id
                for o in obligations
                if o.requirement_kind == "MISSING_ASSESSED_VALUE"
            )
            if value.kind == "NO_VALUE_ASSESSMENT":
                add(
                    "No authoritative value assessment is available. Gate D contribution "
                    "significance does not establish a measured advantage. M1 remains deferred.",
                    value.basis_refs,
                    ReportClaimCategory.VALUE_CLAIM,
                    obligation_links=oid,
                )
            else:
                add(
                    _record_text("Submitter's claimed advantage; no assessed maturity", value),
                    value.basis_refs,
                    ReportClaimCategory.VALUE_CLAIM,
                    use=ClaimUse.ATTRIBUTED_INPUT_CLAIM,
                )
    if question_id == 7:
        for requirement in sorted(
            minimum_validation_requirements(bundle),
            key=lambda r: (r.target_ids, r.purpose, r.proposed_method),
        ):
            add(
                _record_text(
                    "Prospective validation recommendation; no result is established", requirement
                ),
                requirement.basis_refs,
                ReportClaimCategory.VALIDATION_RECOMMENDATION,
                use=ClaimUse.RECOMMENDATION,
            )
    if question_id == 8:
        add(
            'Unsupported example to avoid: "No prior art exists anywhere." '
            "Reason: UNIVERSAL_ABSENCE. This wording is not permitted.",
            (frozen_ref,),
            ReportClaimCategory.NEGATIVE_CLAIM,
            use=ClaimUse.DISALLOWED_WORDING_EXAMPLE,
        )
    uncertainty = project_uncertainty(bundle)
    for item in sorted(
        uncertainty,
        key=lambda i: (
            i.upstream_kind,
            i.target.id if i.target else "",
            tuple(tuple(str(p) for p in r.path) for r in i.authority_refs),
            i.state,
            i.reason,
        ),
    ):
        matching = tuple(
            o.obligation_id
            for o in obligations
            if o.requirement_kind == "ACTUAL_LIMITATION"
            and set(item.authority_refs) <= set(o.authority_refs)
        )
        if question_id == 9 or matching:
            add(
                f"Uncertainty {item.uncertainty_id}: {item.upstream_kind}; state {item.state}; "
                f"historical={item.historical}. "
                + attributed_text("Recorded limitation", item.reason),
                item.authority_refs,
                ReportClaimCategory.UNCERTAINTY_CLAIM,
                obligation_links=matching,
            )
    if question_id == 9:
        view = bundle.judge_resolutions_and_limitations.phase6_view
        refs = (native_ref(bundle, AuthorityKind.COVERAGE),)
        add(
            _record_text("Actual coverage matrix; no saturation inference", view.coverage),
            refs,
            ReportClaimCategory.COVERAGE_CLAIM,
        )
        for candidate in view.candidate_outcomes:
            ref = next(
                r
                for r in catalog
                if r.kind == AuthorityKind.CANDIDATE and r.digest == canonical_hash(candidate)
            )
            add(
                _record_text("Candidate assessment state", candidate),
                (ref,),
                ReportClaimCategory.COVERAGE_CLAIM,
            )
    # Each remaining mandatory unit is expressed as its exact recorded kind and
    # full typed source projections. Never count an unseen ID as visible content.
    remaining: list[tuple[str, tuple[AuthorityRef, ...], str]] = []
    for obligation in obligations:
        if homes[obligation.obligation_id]:
            continue
        if obligation.requirement_kind == "COVERAGE_STATE":
            text = _record_text("Actual coverage state", bundle.research_state)
        elif obligation.requirement_kind == "ACCEPTED_CHALLENGE":
            role = next(
                c
                for c in bundle.judge_resolutions_and_limitations.role_cases
                if any(r.native_id == c.case_id for r in obligation.authority_refs)
            )
            argument_ref = next(
                r for r in obligation.authority_refs if r.kind == AuthorityKind.ROLE
            )
            argument = (
                role.challenges[int(argument_ref.path[-1])]
                if isinstance(role, ProsecutionCase)
                else None
            )
            if argument is None:
                raise ReportProposalError("accepted challenge lacks its exact argument")
            text = _record_text("Independently accepted challenge", argument)
        elif obligation.requirement_kind == "MISSING_ASSESSED_VALUE":
            text = "No authoritative value assessment is available. M1 remains deferred."
        elif obligation.requirement_kind == "LANGUAGE_CEILING":
            ref = obligation.materiality_origin
            if ref.kind == AuthorityKind.GATE:
                record = next(g for g in bundle.gate_findings if g.gate_id == ref.native_id)
                text = _record_text("Accepted target Gate and language constraint", record)
            elif ref.kind == AuthorityKind.JUDGE_RESOLUTION:
                resolution = next(
                    r
                    for r in bundle.judge_resolutions_and_limitations.judge_resolutions
                    if r.resolution_id == ref.native_id
                )
                text = _record_text("Accepted judge resolution and language constraint", resolution)
            else:
                raise ReportProposalError("fallback language constraint lacks known native record")
        else:
            raise ReportProposalError(
                "fallback has no complete transformation for mandatory unit: "
                + obligation.requirement_kind
            )
        remaining.append((text, obligation.authority_refs, obligation.obligation_id))

    def remaining_key(row: tuple[str, tuple[AuthorityRef, ...], str]) -> tuple[str, str, str]:
        text, refs, _ = row
        ref = refs[0]
        if ref.kind == AuthorityKind.GATE:
            gate = next(g for g in bundle.gate_findings if g.gate_id == ref.native_id)
            return (ref.kind.value, gate.target_id, gate.contract_kind)
        return (ref.kind.value, ref.target.id if ref.target else "", text)

    for text, refs, oid in sorted(remaining, key=remaining_key):
        add(text, refs, ReportClaimCategory.UNCERTAINTY_CLAIM, obligation_links=(oid,))
    draft = SectionDraft(
        scope=bundle.scope,
        compilation_id=run_id,
        question_id=question_id,
        blocks=tuple(blocks),
    )
    transformation = "p8fallback_" + canonical_hash(
        {
            "version": FALLBACK_VERSION,
            "bundle": bundle.bundle_digest,
            "draft": draft.model_dump(mode="json"),
        }
    )
    satisfaction = tuple(
        ObligationSatisfaction(
            scope=bundle.scope,
            compilation_id=run_id,
            obligation_id=o.obligation_id,
            question_id=question_id,
            block_ids=tuple(homes[o.obligation_id]),
            claim_ids=tuple(claim_homes[o.obligation_id]),
            basis_refs=o.authority_refs,
            verification_refs=(),
            fallback_transformation_ref=transformation,
        )
        for o in obligations
    )
    return VerifiedSection(
        scope=bundle.scope,
        compilation_id=run_id,
        draft=draft,
        claims=tuple(claims),
        basis_links=tuple(links),
        verification_refs=(),
        obligation_satisfaction=satisfaction,
        block_origins={b.block_id: "DETERMINISTIC_FALLBACK" for b in blocks},
        source_artifact_refs=(),
    )


def validate_fallback_section(
    section: VerifiedSection, bundle: ReportInputBundle, compilation: ReportCompilationRecord
) -> None:
    section = VerifiedSection.model_validate(section.model_dump(mode="json"))
    expected = render_fallback_section(bundle, compilation, question_id=section.draft.question_id)
    if section != expected:
        raise ReportProposalError("fallback differs from exact pinned transformation")


def validate_fallback_content(section: VerifiedSection, bundle: ReportInputBundle) -> None:
    """Known transformations can be checked without inventing compilation authority."""
    section = VerifiedSection.model_validate_json(section.model_dump_json(), strict=True)
    if section.scope != bundle.scope:
        raise ReportProposalError("fallback content belongs to another native scope")
    expected = _render_fallback_for_run(bundle, section.compilation_id, section.draft.question_id)
    if section != expected:
        raise ReportProposalError("fallback label does not authorize arbitrary public content")
