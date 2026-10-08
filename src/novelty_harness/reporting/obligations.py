"""Mandatory reporting coverage shapes; derivation is separate from authority."""

from typing import TYPE_CHECKING, Literal, cast

from pydantic import JsonValue

from novelty_harness.adjudication.models import TargetRef
from novelty_harness.reporting.models import (
    AuthorityRef,
    NonBlank,
    QuestionId,
    ReportContract,
    ReportScope,
    ReportScoped,
)

ObligationKind = Literal[
    "TARGET_REPRESENTATION",
    "DECISIVE_PRECEDENT",
    "SCOPED_NEGATIVE",
    "SURVIVING_CANDIDATE",
    "ACCEPTED_CHALLENGE",
    "LANGUAGE_CEILING",
    "ACTUAL_LIMITATION",
    "MISSING_ASSESSED_VALUE",
    "COVERAGE_STATE",
]


class CoverageObligation(ReportContract):
    contract_kind: Literal["phase8-coverage-obligation-v1"] = "phase8-coverage-obligation-v1"
    scope: ReportScope
    obligation_id: NonBlank
    question_ids: tuple[QuestionId, ...]
    target: TargetRef | None = None
    authority_refs: tuple[AuthorityRef, ...]
    requirement_kind: ObligationKind
    materiality_origin: AuthorityRef


class ObligationSatisfaction(ReportScoped):
    contract_kind: Literal["phase8-obligation-satisfaction-v1"] = (
        "phase8-obligation-satisfaction-v1"
    )
    obligation_id: NonBlank
    question_id: QuestionId
    block_ids: tuple[NonBlank, ...]
    claim_ids: tuple[NonBlank, ...]
    basis_refs: tuple[AuthorityRef, ...]
    verification_refs: tuple[NonBlank, ...]
    fallback_transformation_ref: NonBlank | None = None


def derive_coverage_obligations(bundle: "ReportInputBundle") -> tuple[CoverageObligation, ...]:
    """Mandatory authority is independent of any planner or display configuration."""
    from novelty_harness.adjudication.roles import ProsecutionCase
    from novelty_harness.domain.enums import VerdictState
    from novelty_harness.reporting.bundle import field_ref, native_ref
    from novelty_harness.reporting.models import AuthorityKind
    from novelty_harness.reporting.uncertainty import project_uncertainty
    from novelty_harness.reporting.value import project_value
    from novelty_harness.runtime.tracing.hashing import canonical_hash

    obligations: list[CoverageObligation] = []

    def add(
        kind: ObligationKind,
        refs: tuple[AuthorityRef, ...],
        questions: tuple[QuestionId, ...],
        *,
        target: TargetRef | None = None,
    ) -> None:
        identity = {
            "scope": bundle.scope.model_dump(mode="json"),
            "kind": kind,
            "refs": [r.model_dump(mode="json") for r in refs],
            "questions": list(questions),
        }
        obligations.append(
            CoverageObligation(
                scope=bundle.scope,
                obligation_id="p8ob_" + canonical_hash(cast(JsonValue, identity)),
                requirement_kind=kind,
                authority_refs=refs,
                materiality_origin=refs[0],
                target=target if target is not None else refs[0].target,
                question_ids=questions,
            )
        )

    for finding in bundle.target_findings:
        ref = native_ref(bundle, AuthorityKind.TARGET_FINDING, target_id=finding.target_id)
        add("TARGET_REPRESENTATION", (ref,), (1, 3, 4, 8, 9))
        add("LANGUAGE_CEILING", (ref,), (8, 9))
        if finding.verdict == VerdictState.NOT_NOVEL_AT_CLAIMED_LEVEL:
            add("SCOPED_NEGATIVE", (ref,), (3, 8, 9))
        elif finding.verdict in {
            VerdictState.POTENTIALLY_NOVEL,
            VerdictState.STRONG_EVIDENCE_OF_NOVELTY,
        }:
            add("SURVIVING_CANDIDATE", (ref,), (4, 8, 9))
        for identifier in dict.fromkeys(
            (
                *finding.decisive_phase6_ids,
                *finding.supporting_phase6_ids,
                *finding.challenged_phase6_ids,
            )
        ):
            matched = tuple(
                d.authority_ref
                for d in bundle.dependency_manifest
                if d.authority_ref is not None
                and d.authority_ref.native_id == identifier
                and d.authority_ref.kind
                in {AuthorityKind.COMPARISON, AuthorityKind.GRAPH_RELATION, AuthorityKind.PASSAGE}
                and (
                    d.authority_ref.target is None or d.authority_ref.target.id == finding.target_id
                )
            )
            if not matched:
                raise ValueError("frozen evidence reference lacks its exact bundle basis")
            add("DECISIVE_PRECEDENT", (ref, *matched), (2, 3, 5, 9), target=ref.target)
    for gate in bundle.gate_findings:
        ref = native_ref(bundle, AuthorityKind.GATE, native_id=gate.gate_id)
        add("LANGUAGE_CEILING", (ref,), (3, 4, 8, 9))
    for resolution in bundle.judge_resolutions_and_limitations.judge_resolutions:
        ref = native_ref(bundle, AuthorityKind.JUDGE_RESOLUTION, native_id=resolution.resolution_id)
        add("LANGUAGE_CEILING", (ref,), (3, 4, 5, 8, 9))
        if resolution.resolved_semantics is not None:
            for identifier in resolution.resolved_semantics.accepted_challenge_ids:
                for role in bundle.judge_resolutions_and_limitations.role_cases:
                    if isinstance(role, ProsecutionCase):
                        for index, argument in enumerate(role.challenges):
                            if argument.argument_id == identifier:
                                basis = field_ref(
                                    native_ref(bundle, AuthorityKind.ROLE, native_id=role.case_id),
                                    argument,
                                    "challenges",
                                    index,
                                )
                                add("ACCEPTED_CHALLENGE", (ref, basis), (5, 9))
    for item in project_uncertainty(bundle):
        add(
            "COVERAGE_STATE"
            if item.upstream_kind
            in {
                "COVERAGE",
                "COVERAGE_CELL",
                "BUDGET_USAGE",
                "QUERY_HISTORY",
                "PROVIDERS_ATTEMPTED",
                "STOP_REASON",
            }
            else "ACTUAL_LIMITATION",
            item.authority_refs,
            item.question_ids,
            target=item.target,
        )
    for projection in project_value(bundle):
        if projection.kind == "NO_VALUE_ASSESSMENT":
            add("MISSING_ASSESSED_VALUE", projection.basis_refs, (6, 7, 9))
    return tuple(sorted(obligations, key=lambda o: o.obligation_id))


if TYPE_CHECKING:
    from novelty_harness.reporting.bundle import ReportInputBundle
    from novelty_harness.reporting.verification import VerifiedSection


def check_report_coverage(
    sections: tuple["VerifiedSection", ...], bundle: "ReportInputBundle"
) -> tuple[ObligationSatisfaction, ...]:
    """Join every mandatory visible home; membership never proves textual entailment."""
    from novelty_harness.reporting.claims import validate_claim_extraction
    from novelty_harness.reporting.fallback import validate_fallback_content
    from novelty_harness.reporting.models import ReportProposalError
    from novelty_harness.reporting.verification import section_extraction

    if tuple(s.draft.question_id for s in sections) != tuple(range(1, 10)):
        raise ReportProposalError("coverage requires complete ordered Q1–Q9")
    run = sections[0].compilation_id
    obligations = {o.obligation_id: o for o in bundle.coverage_obligations}
    eligible = tuple(
        d.authority_ref for d in bundle.dependency_manifest if d.authority_ref is not None
    )
    result: list[ObligationSatisfaction] = []
    for section in sections:
        if (
            section.scope,
            section.compilation_id,
            section.draft.scope,
            section.draft.compilation_id,
        ) != (bundle.scope, run, bundle.scope, run):
            raise ReportProposalError("coverage section scope differs")
        extraction = validate_claim_extraction(section.draft, section_extraction(section))
        blocks = {b.block_id: b for b in section.draft.blocks}
        claims = {c.claim_id: c for c in extraction.claims}
        if set(section.block_origins) != set(blocks):
            raise ReportProposalError("every public block requires an origin")
        if set(section.block_origins.values()) == {"DETERMINISTIC_FALLBACK"}:
            validate_fallback_content(section, bundle)
        homes = section.obligation_satisfaction
        expected = {
            o.obligation_id
            for o in obligations.values()
            if section.draft.question_id in o.question_ids
        }
        if len(homes) != len(expected) or {h.obligation_id for h in homes} != expected:
            raise ReportProposalError(
                "mandatory local home is missing or duplicated; Q9 is not a substitute"
            )
        for home in homes:
            obligation = obligations[home.obligation_id]
            if (home.scope, home.compilation_id, home.question_id) != (
                bundle.scope,
                run,
                section.draft.question_id,
            ):
                raise ReportProposalError("coverage home scope differs")
            if (
                not home.block_ids
                or not home.claim_ids
                or len(set(home.block_ids)) != len(home.block_ids)
                or len(set(home.claim_ids)) != len(home.claim_ids)
                or not set(home.block_ids) <= blocks.keys()
                or not set(home.claim_ids) <= claims.keys()
            ):
                raise ReportProposalError("coverage requires actual public blocks and claims")
            if home.basis_refs != obligation.authority_refs or any(
                r not in eligible for r in home.basis_refs
            ):
                raise ReportProposalError("coverage obligation basis differs")
            if any(home.obligation_id not in blocks[b].obligation_ids for b in home.block_ids):
                raise ReportProposalError("coverage has no visible tagged block")
            if any(claims[c].block_id not in home.block_ids for c in home.claim_ids):
                raise ReportProposalError("coverage claim belongs to another block")
            linked = tuple(
                link.authority_ref
                for link in section.basis_links
                if link.claim_id in home.claim_ids
            )
            origins = {section.block_origins[b] for b in home.block_ids}
            if origins != {"DETERMINISTIC_FALLBACK"}:
                if not linked or any(r not in eligible for r in linked):
                    raise ReportProposalError("coverage requires actual admitted claim basis links")
                # Materiality origins can be finding/judge records while Q1 describes
                # the corresponding input target. Exact reference, native parent or
                # target joins are necessary; semantic completeness remains independent.
                if not any(
                    r in home.basis_refs
                    or any(
                        (r.kind, r.native_id) == (basis.kind, basis.native_id)
                        or (r.target is not None and r.target == basis.target)
                        for basis in home.basis_refs
                    )
                    for r in linked
                ):
                    raise ReportProposalError(
                        "coverage material claims lack their native obligation join"
                    )
            if origins == {"DETERMINISTIC_FALLBACK"}:
                if home.fallback_transformation_ref is None or home.verification_refs:
                    raise ReportProposalError(
                        "fallback home lacks its deterministic transformation"
                    )
            elif (
                home.fallback_transformation_ref is not None
                or not home.verification_refs
                or any(r not in section.verification_refs for r in home.verification_refs)
            ):
                raise ReportProposalError("generative home lacks independent verification links")
            result.append(home)
    return tuple(result)
