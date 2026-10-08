"""Origin-bound local repair vocabulary; dispatch is introduced at Task 14."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import Field, model_validator

from novelty_harness.reporting.claims import ClaimExtractionProposal, TextSpan
from novelty_harness.reporting.drafts import (
    DraftBlock,
    SectionContext,
    SectionDraft,
    SectionDraftFragment,
    validate_section_draft,
)
from novelty_harness.reporting.firewall import FirewallResult
from novelty_harness.reporting.models import (
    AuthorityRef,
    NonBlank,
    QuestionId,
    ReportContract,
    ReportProposalError,
    ReportScoped,
)
from novelty_harness.runtime.tracing.hashing import canonical_hash

if TYPE_CHECKING:
    from novelty_harness.reporting.artifacts import ReportArtifact
    from novelty_harness.reporting.verification import ClaimVerificationBatch


class RepairSpan(ReportContract):
    contract_kind: Literal["phase8-repair-span-v1"] = "phase8-repair-span-v1"
    block_id: NonBlank
    start: int = Field(ge=0, strict=True)
    end: int = Field(ge=1, strict=True)

    @model_validator(mode="after")
    def nonempty(self) -> RepairSpan:
        if self.end <= self.start:
            raise ValueError("repair interval must be nonempty")
        return self


class RepairCluster(ReportScoped):
    contract_kind: Literal["phase8-repair-cluster-v1"] = "phase8-repair-cluster-v1"
    cluster_id: NonBlank
    origin_id: NonBlank
    question_id: QuestionId
    original_block_ids: tuple[NonBlank, ...] = Field(min_length=1)
    original_spans: tuple[RepairSpan, ...]
    claim_ids: tuple[NonBlank, ...]
    obligation_ids: tuple[NonBlank, ...]
    reason_codes: tuple[NonBlank, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def local_intervals(self) -> RepairCluster:
        for group in (
            self.original_block_ids,
            self.claim_ids,
            self.obligation_ids,
            self.reason_codes,
        ):
            if len(set(group)) != len(group):
                raise ValueError("repair cluster identities must be unique")
        if any(s.block_id not in self.original_block_ids for s in self.original_spans):
            raise ValueError("repair interval belongs to an unowned block")
        return self


class LocalRepairContext(ReportScoped):
    contract_kind: Literal["phase8-local-repair-context-v1"] = "phase8-local-repair-context-v1"
    section_context: SectionContext
    cluster: RepairCluster
    original_blocks: tuple[DraftBlock, ...]
    neighboring_blocks: tuple[DraftBlock, ...]
    relevant_basis_refs: tuple[AuthorityRef, ...]
    required_qualification_refs: tuple[AuthorityRef, ...]

    @model_validator(mode="after")
    def local_ownership(self) -> LocalRepairContext:
        if any(
            (m.scope, m.compilation_id) != (self.scope, self.compilation_id)
            for m in (self.section_context, self.cluster)
        ):
            raise ValueError("repair context scope differs")
        if self.cluster.question_id != self.section_context.question_id:
            raise ValueError("repair question differs")
        if tuple(
            b.block_id for b in self.original_blocks
        ) != self.cluster.original_block_ids or set(self.cluster.original_block_ids) & {
            b.block_id for b in self.neighboring_blocks
        }:
            raise ValueError("repair ownership differs or neighbors overlap")
        original_text = {b.block_id: b.text for b in self.original_blocks}
        if any(
            span.end > len(original_text[span.block_id]) for span in self.cluster.original_spans
        ):
            raise ValueError("repair interval extends outside original public text")
        if not set((*self.relevant_basis_refs, *self.required_qualification_refs)) <= set(
            self.section_context.selected_basis_refs
        ):
            raise ValueError("repair basis expands section authority")
        return self


class ReportViolation(ReportScoped):
    contract_kind: Literal["phase8-report-violation-v1"] = "phase8-report-violation-v1"
    question_id: QuestionId
    block_id: NonBlank
    spans: tuple[TextSpan, ...] = ()
    claim_ids: tuple[NonBlank, ...] = ()
    obligation_ids: tuple[NonBlank, ...] = ()
    reason_codes: tuple[NonBlank, ...] = Field(min_length=1)


def repair_origin_id(draft: SectionDraft, spans: tuple[RepairSpan, ...]) -> str:
    return "p8origin_" + canonical_hash(
        {"draft": canonical_hash(draft), "spans": [s.model_dump(mode="json") for s in spans]}
    )


def repair_cluster_id(cluster: RepairCluster) -> str:
    return "p8repair_" + canonical_hash(cluster.model_dump(mode="json", exclude={"cluster_id"}))


def select_repair_clusters(
    draft: SectionDraft, violations: tuple[ReportViolation, ...]
) -> tuple[RepairCluster, ...]:
    """Whole-block replacement ownership merges before any repair is consumed."""
    blocks = {b.block_id: b for b in draft.blocks}
    grouped: dict[str, list[ReportViolation]] = {}
    for violation in violations:
        violation = ReportViolation.model_validate(violation.model_dump(mode="json"))
        if (violation.scope, violation.compilation_id, violation.question_id) != (
            draft.scope,
            draft.compilation_id,
            draft.question_id,
        ) or violation.block_id not in blocks:
            raise ReportProposalError("repair violation belongs to another draft")
        grouped.setdefault(violation.block_id, []).append(violation)
    clusters: list[RepairCluster] = []
    for block_id in blocks:
        if block_id not in grouped:
            continue
        failures = grouped[block_id]
        intervals = sorted(
            (span.start, span.end)
            for v in failures
            for span in (v.spans or (TextSpan(start=0, end=len(blocks[block_id].text)),))
        )
        merged: list[tuple[int, int]] = []
        for start, end in intervals:
            if end > len(blocks[block_id].text):
                raise ReportProposalError("repair failure span exceeds original text")
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        spans = tuple(RepairSpan(block_id=block_id, start=start, end=end) for start, end in merged)
        cluster = RepairCluster(
            scope=draft.scope,
            compilation_id=draft.compilation_id,
            cluster_id="pending",
            origin_id=repair_origin_id(draft, spans),
            question_id=draft.question_id,
            original_block_ids=(block_id,),
            original_spans=spans,
            claim_ids=tuple(dict.fromkeys(c for v in failures for c in v.claim_ids)),
            obligation_ids=tuple(
                dict.fromkeys(
                    (
                        *blocks[block_id].obligation_ids,
                        *(o for v in failures for o in v.obligation_ids),
                    )
                )
            ),
            reason_codes=tuple(sorted({r for v in failures for r in v.reason_codes})),
        )
        clusters.append(cluster.model_copy(update={"cluster_id": repair_cluster_id(cluster)}))
    return tuple(clusters)


def validate_repair_fragment(
    fragment: SectionDraftFragment, cluster: RepairCluster, context: LocalRepairContext
) -> SectionDraftFragment:
    try:
        fragment = SectionDraftFragment.model_validate(fragment.model_dump(mode="json"))
        if (
            fragment.scope,
            fragment.compilation_id,
            fragment.question_id,
            fragment.cluster_origin_id,
            fragment.replaced_block_ids,
        ) != (
            context.scope,
            context.compilation_id,
            cluster.question_id,
            cluster.origin_id,
            cluster.original_block_ids,
        ) or context.cluster != cluster:
            raise ReportProposalError("repair fragment escapes its immutable origin")
        ids = {b.block_id for b in fragment.blocks}
        if len(ids) != len(fragment.blocks) or ids & {
            b.block_id for b in context.neighboring_blocks
        }:
            raise ReportProposalError("repair edits a neighbor or duplicates replacement blocks")
        if not set(cluster.obligation_ids) <= {
            o for b in fragment.blocks for o in b.obligation_ids
        }:
            raise ReportProposalError("repair drops original mandatory obligations")
        if any(
            r not in context.relevant_basis_refs
            for b in fragment.blocks
            for r in (*b.basis_candidate_refs, *(c.authority_ref for c in b.citation_tokens))
        ):
            raise ReportProposalError("repair expands its original basis")
        validate_section_draft(
            SectionDraft(
                scope=fragment.scope,
                compilation_id=fragment.compilation_id,
                question_id=fragment.question_id,
                blocks=fragment.blocks,
            ),
            context.section_context,
        )
    except ValueError as error:
        raise ReportProposalError("repair fragment fails strict local validation") from error
    return fragment


def apply_repair_fragment(
    draft: SectionDraft, fragment: SectionDraftFragment, cluster: RepairCluster
) -> SectionDraft:
    """Apply only the already validated original block ownership; keep neighbors exact."""
    if (draft.scope, draft.compilation_id, draft.question_id) != (
        fragment.scope,
        fragment.compilation_id,
        fragment.question_id,
    ) or (
        fragment.cluster_origin_id != cluster.origin_id
        or fragment.replaced_block_ids != cluster.original_block_ids
    ):
        raise ReportProposalError("repair derivation scope or ownership differs")
    if not set(cluster.original_block_ids) <= {b.block_id for b in draft.blocks}:
        raise ReportProposalError("repair derivation cannot find its original blocks")
    blocks: list[DraftBlock] = []
    inserted = False
    for block in draft.blocks:
        if block.block_id in cluster.original_block_ids:
            if not inserted:
                blocks.extend(fragment.blocks)
                inserted = True
        else:
            blocks.append(block)
    if len({b.block_id for b in blocks}) != len(blocks):
        raise ReportProposalError("repair replacement collides with a public block")
    return draft.model_copy(update={"blocks": tuple(blocks)})


def repair_available(cluster: RepairCluster, artifacts: tuple[ReportArtifact, ...]) -> bool:
    """A committed cluster consumes its one attempt before a response exists."""
    return not any(
        (a.scope, a.compilation_id) == (cluster.scope, cluster.compilation_id)
        and a.cluster_origin_id == cluster.origin_id
        for a in artifacts
    )


def report_violations(
    draft: SectionDraft,
    extraction: ClaimExtractionProposal,
    firewall: FirewallResult,
    batch: ClaimVerificationBatch | None,
) -> tuple[ReportViolation, ...]:
    failures: list[ReportViolation] = []
    claims = {c.claim_id: c for c in extraction.claims}

    def add(
        block_id: str,
        reasons: tuple[str, ...],
        claim_ids: tuple[str, ...] = (),
        obligations: tuple[str, ...] = (),
    ) -> None:
        failures.append(
            ReportViolation(
                scope=draft.scope,
                compilation_id=draft.compilation_id,
                question_id=draft.question_id,
                block_id=block_id,
                spans=tuple(s for cid in claim_ids for s in claims[cid].spans),
                claim_ids=claim_ids,
                obligation_ids=obligations,
                reason_codes=reasons or ("UNRESOLVED_MATERIAL_CONTENT",),
            )
        )

    for violation in firewall.violations:
        ids = (violation.claim_id,) if violation.claim_id in claims else ()
        if violation.block_id:
            add(violation.block_id, (violation.reason_code,), ids)
        else:
            for block in draft.blocks:
                add(block.block_id, (violation.reason_code,))
    if batch:
        for check in batch.dispositions:
            if check.disposition != "SUPPORTED" or check.unmet_qualification_refs:
                add(claims[check.claim_id].block_id, check.reason_codes, (check.claim_id,))
        for check in batch.blocks:
            if (
                check.disposition != "SUPPORTED"
                or check.unmet_obligation_ids
                or check.missing_assertion_spans
            ):
                add(check.block_id, check.reason_codes, obligations=check.unmet_obligation_ids)
    return tuple(failures)
