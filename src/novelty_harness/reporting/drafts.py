"""Complete typed writer context and untrusted structured public prose."""

import re
from datetime import date
from typing import TYPE_CHECKING, Literal

from pydantic import Field, model_validator

from novelty_harness.adjudication.counterfactual import CounterfactualLocalization
from novelty_harness.adjudication.frozen import OverallFinding, TargetFinding
from novelty_harness.adjudication.judge import (
    CounterbalanceComparison,
    CounterbalanceRun,
    JudgeResolution,
)
from novelty_harness.adjudication.needs import InputClarificationNeed, ResearchGapRequest
from novelty_harness.adjudication.roles import RebuttalCase
from novelty_harness.domain.idea import CanonicalIdeaRepresentation
from novelty_harness.domain.mcu import MCUGraph
from novelty_harness.evidence.graph.assessment_ledger import (
    Phase6CandidateLedgerRecord,
    Phase6CoverageLedger,
    Phase6DerivedLedgerRecord,
)
from novelty_harness.evidence.graph.assessment_view import (
    AuthorizedGraphRelation,
    CitedPassageView,
    CommittedComparisonView,
)
from novelty_harness.evidence.mapping.dimensions import MCUComparisonProfile
from novelty_harness.evidence.provenance.models import EvidenceLineageCluster
from novelty_harness.mcu.overrides import MCUVersion
from novelty_harness.reporting.bundle import (
    GateProjection,
    LanguageEnvelope,
    QualificationProjection,
    ReportInputBundle,
    RoleProjection,
    SourceMetadataObservation,
)
from novelty_harness.reporting.models import (
    AuthorityKind,
    AuthorityRef,
    Digest,
    NonBlank,
    QuestionId,
    ReportContract,
    ReportGenerationLimits,
    ReportLens,
    ReportProposalError,
    ReportScoped,
    validate_authority_refs,
)
from novelty_harness.reporting.obligations import CoverageObligation
from novelty_harness.reporting.plan import (
    QuestionPlan,
    ReportPlan,
    ReportPlanProposal,
    build_coverage_plan,
    validate_report_plan,
)
from novelty_harness.reporting.uncertainty import UncertaintyItem, project_uncertainty
from novelty_harness.reporting.value import ValueProjection
from novelty_harness.runtime.tracing.hashing import canonical_json


class InlineStyle(ReportContract):
    contract_kind: Literal["phase8-inline-style-v1"] = "phase8-inline-style-v1"
    start: int = Field(ge=0, strict=True)
    end: int = Field(ge=1, strict=True)
    style: Literal["EMPHASIS", "STRONG", "CODE"]

    @model_validator(mode="after")
    def nonempty(self) -> "InlineStyle":
        if self.end <= self.start:
            raise ValueError("inline style interval must be nonempty")
        return self


class CitationToken(ReportContract):
    contract_kind: Literal["phase8-citation-token-v1"] = "phase8-citation-token-v1"
    offset: int = Field(ge=0, strict=True)
    authority_ref: AuthorityRef


class DraftBlock(ReportContract):
    contract_kind: Literal["phase8-draft-block-v1"] = "phase8-draft-block-v1"
    block_id: NonBlank
    kind: Literal["HEADING", "PARAGRAPH", "LIST_ITEM", "TABLE_CELL", "CAPTION"]
    text: NonBlank
    inline_styles: tuple[InlineStyle, ...] = ()
    citation_tokens: tuple[CitationToken, ...] = ()
    basis_candidate_refs: tuple[AuthorityRef, ...] = ()
    obligation_ids: tuple[NonBlank, ...] = ()
    heading_level: Literal[1, 2] = 1
    table_id: NonBlank | None = None
    row: int | None = Field(default=None, ge=0, strict=True)
    column: int | None = Field(default=None, ge=0, strict=True)

    @model_validator(mode="after")
    def table_coordinates(self) -> "DraftBlock":
        coordinates = (self.table_id, self.row, self.column)
        if self.kind == "TABLE_CELL":
            if any(x is None for x in coordinates):
                raise ValueError("table cell requires exact table/row/column")
        elif any(x is not None for x in coordinates):
            raise ValueError("only a table cell can carry table coordinates")
        return self


class SectionDraft(ReportScoped):
    contract_kind: Literal["phase8-section-draft-v1"] = "phase8-section-draft-v1"
    question_id: QuestionId
    blocks: tuple[DraftBlock, ...] = Field(min_length=1)


class SectionDraftFragment(ReportScoped):
    contract_kind: Literal["phase8-section-draft-fragment-v1"] = "phase8-section-draft-fragment-v1"
    question_id: QuestionId
    cluster_origin_id: NonBlank
    replaced_block_ids: tuple[NonBlank, ...] = Field(min_length=1)
    blocks: tuple[DraftBlock, ...] = Field(min_length=1)


class SectionAuthority(ReportContract):
    """Public meaning closure without upstream provider instructions or execution payloads."""

    contract_kind: Literal["phase8-section-authority-v1"] = "phase8-section-authority-v1"
    cir: CanonicalIdeaRepresentation
    graph: MCUGraph | MCUVersion
    target_profiles: tuple[MCUComparisonProfile, ...]
    comparisons: tuple[CommittedComparisonView, ...]
    authorized_relations: tuple[AuthorizedGraphRelation, ...]
    cited_passages: tuple[CitedPassageView, ...]
    source_metadata: tuple[SourceMetadataObservation, ...]
    gate_findings: tuple[GateProjection, ...]
    qualifications: tuple[QualificationProjection, ...]
    role_cases: tuple[RoleProjection, ...]
    rebuttals: tuple[RebuttalCase, ...]
    judge_runs: tuple[CounterbalanceRun, ...]
    judge_comparisons: tuple[CounterbalanceComparison, ...]
    judge_resolutions: tuple[JudgeResolution, ...]
    counterfactuals: tuple[CounterfactualLocalization, ...]
    input_needs: tuple[InputClarificationNeed, ...]
    research_gaps: tuple[ResearchGapRequest, ...]
    value_projection: tuple[ValueProjection, ...]
    coverage: Phase6CoverageLedger
    candidate_outcomes: tuple[Phase6CandidateLedgerRecord, ...]
    multi_source_context: tuple[Phase6DerivedLedgerRecord, ...]
    patent_screenings: tuple[Phase6DerivedLedgerRecord, ...]
    lineage: tuple[EvidenceLineageCluster, ...]


class OmissionManifest(ReportContract):
    contract_kind: Literal["phase8-omission-manifest-v1"] = "phase8-omission-manifest-v1"
    authority_refs: tuple[AuthorityRef, ...] = ()
    obligation_ids: tuple[NonBlank, ...] = ()
    reason: Literal["DISPLAY_LIMIT"] | None = None


class SectionContext(ReportScoped):
    contract_kind: Literal["phase8-section-context-v1"] = "phase8-section-context-v1"
    bundle_digest: Digest
    plan_id: NonBlank
    as_of: date
    question_id: QuestionId
    question_plan: QuestionPlan
    authority: SectionAuthority
    target_findings: tuple[TargetFinding, ...]
    overall_finding: OverallFinding
    language_envelopes: tuple[LanguageEnvelope, ...]
    coverage_obligations: tuple[CoverageObligation, ...]
    uncertainty: tuple[UncertaintyItem, ...]
    selected_basis_refs: tuple[AuthorityRef, ...]
    eligible_citation_refs: tuple[AuthorityRef, ...]
    limits: ReportGenerationLimits
    lens: ReportLens
    lens_version: Literal["p8-lens-v1"] = "p8-lens-v1"
    lens_instruction: NonBlank
    detail: Literal["SHORT", "STANDARD", "DETAILED"]
    omission_manifest: OmissionManifest = Field(default_factory=OmissionManifest)
    display_chars: int = Field(ge=0)
    requires_fallback: bool


_LENSES = {
    ReportLens.RESEARCH: (
        "Organize explanation around admitted baselines and prospective ablations; "
        "separate candidate mechanisms from measured benefit."
    ),
    ReportLens.PRODUCT: (
        "Explain the attributed user workflow and admitted differentiation; propose validation "
        "of user outcomes without inventing market facts."
    ),
    ReportLens.ENGINEERING: (
        "Emphasize admitted system architecture, constraints and prospective measurements "
        "of latency, reliability and resource use."
    ),
    ReportLens.SOFTWARE: (
        "Emphasize admitted functionality, interfaces and control flow; propose usability "
        "and functional validation within the retained scope."
    ),
    ReportLens.PROCESS: (
        "Explain the admitted arrangement, roles, dependencies and sequence; propose "
        "validation of the contribution-bearing process relationships."
    ),
    ReportLens.PATENT_SCREENING: (
        "Explain exact admitted mappings and the single reference distinction: several sources "
        "do not establish one combination precedent. Retain chronology and configuration gaps. "
        "This presentation is not a legal opinion."
    ),
}


def lens_instruction(lens: ReportLens) -> str:
    return _LENSES[lens]


def build_section_context(
    bundle: ReportInputBundle,
    plan: ReportPlan,
    *,
    question_id: QuestionId,
    compilation: "ReportCompilationRecord",
) -> SectionContext:
    plan = ReportPlan.model_validate(plan.model_dump(mode="json"))
    if (plan.scope, plan.compilation_id, plan.bundle_digest) != (
        compilation.scope,
        compilation.compilation_id,
        bundle.bundle_digest,
    ) or bundle.scope != compilation.scope:
        raise ReportProposalError("writer plan/bundle/attempt scope differs")
    if plan.origin == "COVERAGE_FALLBACK":
        expected = build_coverage_plan(bundle, compilation)
    else:
        expected = validate_report_plan(
            ReportPlanProposal(
                scope=plan.scope,
                compilation_id=plan.compilation_id,
                bundle_digest=plan.bundle_digest,
                questions=plan.questions,
            ),
            bundle,
            compilation.options,
        )
    if plan != expected:
        raise ReportProposalError("writer context requires an exactly recomputed plan")
    question = next(q for q in plan.questions if q.question_id == question_id)
    selected = tuple(
        dict.fromkeys(
            (
                *question.evidence_refs,
                *question.adjudication_refs,
                *question.required_limitation_refs,
            )
        )
    )
    selected_evidence_ids = {
        r.native_id
        for r in selected
        if r.kind
        in {
            AuthorityKind.COMPARISON,
            AuthorityKind.COMMIT,
            AuthorityKind.PASSAGE,
            AuthorityKind.SOURCE,
            AuthorityKind.SOURCE_VERSION,
            AuthorityKind.GRAPH_RELATION,
        }
    }
    comparisons = tuple(
        c
        for c in bundle.eligible_comparisons
        if selected_evidence_ids
        & {
            c.comparison.classification.classification_id,
            c.commit_id,
            c.comparison.comparison.chain.source.source_id,
            c.comparison.comparison.chain.edge.source_version_id,
            *c.graph_edge_ids,
            *(p.passage.passage_id for p in c.cited_passages),
        }
    )
    closure_ids = {
        identifier
        for c in comparisons
        for identifier in (
            c.comparison.classification.classification_id,
            c.commit_id,
            c.comparison.comparison.chain.source.source_id,
            c.comparison.comparison.chain.edge.source_version_id,
            *c.graph_edge_ids,
            *(p.passage.passage_id for p in c.cited_passages),
        )
        if identifier is not None
    }
    selected = tuple(
        dict.fromkeys(
            (
                *selected,
                *(
                    d.authority_ref
                    for d in bundle.dependency_manifest
                    if d.authority_ref is not None and d.authority_ref.native_id in closure_ids
                ),
            )
        )
    )
    authority = project_section_authority(bundle, comparisons)
    obligations = tuple(
        o for o in bundle.coverage_obligations if o.obligation_id in question.obligation_ids
    )
    context = SectionContext(
        scope=bundle.scope,
        compilation_id=compilation.compilation_id,
        bundle_digest=bundle.bundle_digest,
        plan_id=plan.plan_id,
        as_of=bundle.as_of,
        question_id=question_id,
        question_plan=question,
        authority=authority,
        target_findings=bundle.target_findings,
        overall_finding=bundle.overall_finding,
        language_envelopes=bundle.language_envelopes,
        coverage_obligations=obligations,
        uncertainty=project_uncertainty(bundle),
        selected_basis_refs=selected,
        eligible_citation_refs=tuple(r for r in selected if r.kind == AuthorityKind.PASSAGE),
        limits=compilation.options.limits,
        lens=compilation.options.lens,
        lens_instruction=lens_instruction(compilation.options.lens),
        detail=compilation.options.detail,
        display_chars=0,
        requires_fallback=False,
    )
    context = _count_display(context)
    if context.display_chars > context.limits.max_context_chars:
        context = context.model_copy(
            update={
                "requires_fallback": True,
                "omission_manifest": OmissionManifest(
                    authority_refs=selected,
                    obligation_ids=question.obligation_ids,
                    reason="DISPLAY_LIMIT",
                ),
            }
        )
        context = _count_display(context)
    return context


def project_section_authority(
    bundle: ReportInputBundle, comparisons: tuple[CommittedComparisonView, ...]
) -> SectionAuthority:
    """Public typed meaning shared by separate stateless report tasks."""
    selected_comparisons = {c.comparison.classification.classification_id for c in comparisons}
    commits = {c.commit_id for c in comparisons}
    passage_ids = {p.passage.passage_id for c in comparisons for p in c.cited_passages}
    closure = bundle.judge_resolutions_and_limitations
    return SectionAuthority(
        cir=bundle.cir,
        graph=bundle.graph_or_version,
        target_profiles=bundle.target_profiles,
        comparisons=comparisons,
        authorized_relations=tuple(
            r for r in bundle.authorized_relations if r.commit_id in commits
        ),
        cited_passages=tuple(
            p for p in bundle.cited_passages if p.passage.passage_id in passage_ids
        ),
        source_metadata=tuple(
            m
            for m in bundle.source_metadata
            if any(r.native_id in selected_comparisons for r in m.comparison_refs)
        ),
        gate_findings=bundle.gate_findings,
        qualifications=bundle.qualifications,
        role_cases=closure.role_cases,
        rebuttals=closure.rebuttals,
        judge_runs=closure.judge_runs,
        judge_comparisons=closure.judge_comparisons,
        judge_resolutions=closure.judge_resolutions,
        counterfactuals=bundle.counterfactuals,
        input_needs=bundle.input_needs,
        research_gaps=bundle.research_gaps,
        value_projection=bundle.value_projection,
        coverage=closure.phase6_view.coverage,
        candidate_outcomes=closure.phase6_view.candidate_outcomes,
        multi_source_context=closure.phase6_view.multi_source_context,
        patent_screenings=closure.phase6_view.patent_screenings,
        lineage=closure.phase6_view.lineage,
    )


def _count_display(context: SectionContext) -> SectionContext:
    # The integer's own decimal width is part of the emitted structure.
    while True:
        size = len(canonical_json(context))
        if size == context.display_chars:
            return context
        context = context.model_copy(update={"display_chars": size})


_UNSAFE_TEXT = re.compile(
    r"[a-z][a-z0-9+.-]*://|www\.|javascript\s*:|data\s*:|<[/!?A-Za-z][^>]*>|\[[^\]]*\]\s*\(",
    re.IGNORECASE,
)


def contains_unsafe_public_text(text: str) -> bool:
    """Known markup/link rejection, never a semantic truth check."""
    return _UNSAFE_TEXT.search(text) is not None


def validate_section_draft(draft: SectionDraft, context: SectionContext) -> SectionDraft:
    try:
        draft = SectionDraft.model_validate(draft.model_dump(mode="json"))
        if (draft.scope, draft.compilation_id, draft.question_id) != (
            context.scope,
            context.compilation_id,
            context.question_id,
        ):
            raise ReportProposalError("draft scope or question differs from context")
        if context.requires_fallback:
            raise ReportProposalError(
                "complete writer closure exceeds display limit; fallback required"
            )
        if (
            len(draft.blocks) > context.limits.max_blocks_per_question
            or sum(len(b.text) for b in draft.blocks) > context.limits.max_question_chars
        ):
            raise ReportProposalError("draft generation limit exceeded")
        if len({b.block_id for b in draft.blocks}) != len(draft.blocks):
            raise ReportProposalError("duplicate public block identity")
        selected = set(context.selected_basis_refs)
        citations = set(context.eligible_citation_refs)
        obligations = {o.obligation_id for o in context.coverage_obligations}
        cells: set[tuple[str | None, int | None, int | None]] = set()
        for block in draft.blocks:
            if contains_unsafe_public_text(block.text):
                raise ReportProposalError(
                    "draft must be plain text without HTML, raw links or free URLs"
                )
            validate_authority_refs(block.basis_candidate_refs, context.scope)
            if (
                not set(block.basis_candidate_refs) <= selected
                or not set(block.obligation_ids) <= obligations
                or len(set(block.obligation_ids)) != len(block.obligation_ids)
            ):
                raise ReportProposalError(
                    "draft basis or obligation candidate is foreign or duplicate"
                )
            if block.kind == "HEADING" and block.heading_level > context.limits.max_hierarchy_depth:
                raise ReportProposalError("heading generation depth exceeded")
            for style in block.inline_styles:
                if style.end > len(block.text):
                    raise ReportProposalError("style interval is outside actual public text")
            for token in block.citation_tokens:
                if token.offset > len(block.text) or token.authority_ref not in citations:
                    raise ReportProposalError(
                        "citation token is outside text or admitted passage closure"
                    )
            if block.kind == "TABLE_CELL":
                coordinate = (block.table_id, block.row, block.column)
                if coordinate in cells:
                    raise ReportProposalError("duplicate table cell coordinate")
                cells.add(coordinate)
        return draft
    except ValueError as exc:
        if isinstance(exc, ReportProposalError):
            raise
        raise ReportProposalError("draft violates strict structure") from exc


if TYPE_CHECKING:
    from novelty_harness.reporting.artifacts import ReportCompilationRecord
