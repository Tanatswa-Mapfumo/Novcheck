"""Complete working case packet derived from one sealed assessment context."""

from datetime import date
from typing import Literal, Self

from pydantic import ConfigDict, Field, model_validator

from novelty_harness.adjudication.context import Phase7InputManifest, SealedAssessmentContext
from novelty_harness.adjudication.models import Phase7Scoped
from novelty_harness.domain.base import ContractModel
from novelty_harness.evidence.graph.assessment_ledger import (
    Phase6CandidateLedgerRecord,
    Phase6CoverageLedger,
)
from novelty_harness.evidence.graph.assessment_view import (
    AuthorizedGraphRelation,
    CitedPassageView,
    CommittedComparisonView,
    Phase6AssessmentView,
)
from novelty_harness.evidence.mapping.dimensions import (
    MCUComparisonProfile,
    build_combination_comparison_profile,
)
from novelty_harness.runtime.tracing.hashing import canonical_hash, canonical_json

BUILDER_VERSION = "phase7-case-builder-v1"


def _case_id(context_id: str, snapshot_id: str, manifest_digest: str, view_digest: str) -> str:
    return "p7case_" + canonical_hash(
        {
            "context_id": context_id,
            "snapshot_id": snapshot_id,
            "manifest_digest": manifest_digest,
            "view_digest": view_digest,
            "builder_version": BUILDER_VERSION,
        }
    )


class AdjudicationCasePacket(Phase7Scoped):
    """Retains exact Phase 6 evidence plus all bound input and research facts."""

    contract_kind: Literal["phase7-adjudication-case-packet-v1"] = (
        "phase7-adjudication-case-packet-v1"
    )
    case_id: str
    manifest_id: str
    manifest_digest: str
    phase6_view_digest: str
    as_of: date
    phase6_view: Phase6AssessmentView
    manifest: Phase7InputManifest
    builder_version: str = BUILDER_VERSION

    @model_validator(mode="after")
    def exact_bound_content(self) -> Self:
        if (
            self.assessment_id != self.phase6_view.assessment_id
            or self.assessment_id != self.manifest.assessment_id
            or self.phase6_snapshot_id != self.phase6_view.snapshot_id
            or self.phase6_snapshot_id != self.manifest.phase6_snapshot_id
            or self.as_of != self.phase6_view.as_of
            or self.as_of != self.manifest.as_of
            or self.manifest_digest != self.manifest.content_digest()
            or self.phase6_view_digest != canonical_hash(self.phase6_view)
            or self.builder_version != BUILDER_VERSION
            or self.case_id
            != _case_id(
                self.assessment_context_id,
                self.phase6_snapshot_id,
                self.manifest_digest,
                self.phase6_view_digest,
            )
        ):
            raise ValueError("Case packet identity differs from bound world-state")
        return self

    @property
    def digest(self) -> str:
        return canonical_hash(self)

    @property
    def target_profiles(self) -> tuple[MCUComparisonProfile, ...]:
        return self.phase6_view.targets

    @property
    def comparisons(self) -> tuple[CommittedComparisonView, ...]:
        return self.phase6_view.committed_comparisons

    @property
    def authorized_relations(self) -> tuple[AuthorizedGraphRelation, ...]:
        return self.phase6_view.authorized_graph_relations

    @property
    def cited_passages(self) -> tuple[CitedPassageView, ...]:
        return tuple(p for comparison in self.comparisons for p in comparison.cited_passages)

    @property
    def candidate_outcomes(self) -> tuple[Phase6CandidateLedgerRecord, ...]:
        return self.phase6_view.candidate_outcomes

    @property
    def coverage(self) -> Phase6CoverageLedger:
        return self.phase6_view.coverage

    @property
    def query_history(self) -> tuple[str, ...]:
        return self.manifest.query_history

    @property
    def providers_attempted(self) -> tuple[str, ...]:
        return self.manifest.providers_attempted

    @property
    def stop_reason(self) -> str | None:
        return self.manifest.stop_reason

    @property
    def target_ids(self) -> frozenset[str]:
        return frozenset(target.target_id for target in self.target_profiles)


def build_adjudication_case(
    context: SealedAssessmentContext, view: Phase6AssessmentView
) -> AdjudicationCasePacket:
    if (
        context.assessment_id != view.assessment_id
        or context.snapshot_id != view.snapshot_id
        or context.phase6_view_digest != canonical_hash(view)
        or context.manifest_digest != context.manifest.content_digest()
    ):
        raise ValueError("Case context and Phase 6 view differ")
    expected_targets = {mcu.mcu_id for mcu in context.manifest.mcu_graph.mcus} | {
        build_combination_comparison_profile(combination, context.manifest.mcu_graph.mcus).target_id
        for combination in context.manifest.mcu_graph.combinations
    }
    if {target.target_id for target in view.targets} != expected_targets:
        raise ValueError("Case target universe differs from sealed input topology")
    return AdjudicationCasePacket(
        case_id=_case_id(
            context.context_id,
            context.snapshot_id,
            context.manifest_digest,
            context.phase6_view_digest,
        ),
        assessment_id=context.assessment_id,
        assessment_context_id=context.context_id,
        phase6_snapshot_id=context.snapshot_id,
        manifest_id=context.manifest_id,
        manifest_digest=context.manifest_digest,
        phase6_view_digest=context.phase6_view_digest,
        as_of=view.as_of,
        phase6_view=view,
        manifest=context.manifest,
    )


class RoleDisplay(ContractModel):
    """Bounded presentation; omitted content cannot support a decisive finding."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["phase7-role-display-v1"] = "phase7-role-display-v1"
    packet_id: str
    target_id: str
    rendered_text: str
    displayed_comparison_ids: tuple[str, ...] = ()
    omitted_comparison_ids: tuple[str, ...] = ()
    displayed_passage_ids: tuple[str, ...] = ()
    omitted_passage_ids: tuple[str, ...] = ()
    displayed_relation_ids: tuple[str, ...] = ()
    omitted_relation_ids: tuple[str, ...] = ()
    displayed_material_ids: tuple[str, ...] = ()
    omitted_material_ids: tuple[str, ...] = ()
    max_chars: int = Field(ge=0)


def select_role_display(
    packet: AdjudicationCasePacket, *, target_id: str, max_chars: int
) -> RoleDisplay:
    if target_id not in packet.target_ids:
        raise ValueError("Unknown packet target")
    if max_chars < 0:
        raise ValueError("max_chars must be nonnegative")
    displayed_comparisons: list[str] = []
    omitted_comparisons: list[str] = []
    displayed_passages: list[str] = []
    omitted_passages: list[str] = []
    rendered: list[str] = []
    total = 0
    for item in packet.comparisons:
        if item.comparison.comparison.chain.edge.mcu_id != target_id:
            continue
        comparison_id = str(item.comparison.classification.classification_id)
        passage_ids = [str(passage.passage.passage_id) for passage in item.cited_passages]
        text = canonical_json(item)
        if total + len(text) <= max_chars:
            rendered.append(text)
            total += len(text)
            displayed_comparisons.append(comparison_id)
            displayed_passages.extend(passage_ids)
        else:
            omitted_comparisons.append(comparison_id)
            omitted_passages.extend(passage_ids)
    displayed_relation_ids = tuple(
        relation.edge.edge_id
        for relation in packet.authorized_relations
        if str(relation.classification_id) in displayed_comparisons
    )
    omitted_relation_ids = tuple(
        relation.edge.edge_id
        for relation in packet.authorized_relations
        if str(relation.classification_id) not in displayed_comparisons
    )
    # The display currently renders exact comparisons only. Record every
    # other packet component it omits; the full packet remains authoritative.
    omitted_material_ids = tuple(
        "p7display_" + canonical_hash(item)
        for item in (
            packet.manifest,
            *packet.target_profiles,
            *packet.candidate_outcomes,
            packet.coverage,
            *packet.phase6_view.multi_source_context,
            *packet.phase6_view.patent_screenings,
            *packet.phase6_view.lineage,
        )
    )
    return RoleDisplay(
        packet_id=packet.case_id,
        target_id=target_id,
        rendered_text="\n".join(rendered),
        displayed_comparison_ids=tuple(displayed_comparisons),
        omitted_comparison_ids=tuple(omitted_comparisons),
        displayed_passage_ids=tuple(displayed_passages),
        omitted_passage_ids=tuple(omitted_passages),
        displayed_relation_ids=displayed_relation_ids,
        omitted_relation_ids=omitted_relation_ids,
        omitted_material_ids=omitted_material_ids,
        max_chars=max_chars,
    )


def validate_decisive_basis(
    display: RoleDisplay,
    *,
    comparison_ids: tuple[str, ...] = (),
    passage_ids: tuple[str, ...] = (),
    relation_ids: tuple[str, ...] = (),
    material_ids: tuple[str, ...] = (),
) -> None:
    if (
        set(comparison_ids) - set(display.displayed_comparison_ids)
        or set(passage_ids) - set(display.displayed_passage_ids)
        or set(relation_ids) - set(display.displayed_relation_ids)
        or set(material_ids) - set(display.displayed_material_ids)
    ):
        raise ValueError("Decisive basis was omitted from the displayed packet content")
