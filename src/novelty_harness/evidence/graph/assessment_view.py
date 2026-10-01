"""Immutable Phase 6 assessment read-model contracts.

Constructing these contracts does not establish repository authority; only a
repository loader can validate and return an authoritative assessment view.
"""

from datetime import date
from typing import Literal, Self

from pydantic import ConfigDict, model_validator

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.ids import AssessmentId, ClassificationId, EvidenceEdgeId
from novelty_harness.evidence.graph.assessment_ledger import (
    Phase6CandidateLedgerRecord,
    Phase6CoverageLedger,
    Phase6DerivedLedgerRecord,
)
from novelty_harness.evidence.graph.models import GraphEdge, GraphNode
from novelty_harness.evidence.mapping.dimensions import MCUComparisonProfile
from novelty_harness.evidence.passages.models import PassageRecord
from novelty_harness.evidence.precedent.gates import ClassifiedComparison
from novelty_harness.evidence.provenance.models import EvidenceLineageCluster


class Phase6AssessmentAuthorityError(ValueError):
    """Fail-closed signal for a repository assessment loader."""


class CitedPassageView(ContractModel):
    """An unchanged passage and the commitment judgments that cite it."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["phase6-cited-passage-view-v1"] = "phase6-cited-passage-view-v1"

    passage: PassageRecord
    commitment_ids: tuple[str, ...]

    @model_validator(mode="after")
    def commitment_ids_are_unique(self) -> Self:
        if len(set(self.commitment_ids)) != len(self.commitment_ids):
            raise ValueError("Cited passage commitment IDs must be unique")
        return self


class CommittedComparisonView(ContractModel):
    """A full classified chain with its repository-derived projection status."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["phase6-committed-comparison-view-v1"] = (
        "phase6-committed-comparison-view-v1"
    )

    comparison: ClassifiedComparison
    commit_id: str
    projection_status: Literal["GRAPH_AUTHORIZED", "SEMANTIC_ONLY", "NONRELATIONAL_STATUS"]
    proposition_node_id: str | None
    graph_edge_ids: tuple[str, ...]
    cited_passages: tuple[CitedPassageView, ...]

    @model_validator(mode="after")
    def projection_shape_is_consistent(self) -> Self:
        has_graph_projection = self.projection_status == "GRAPH_AUTHORIZED"
        if has_graph_projection != bool(self.proposition_node_id and self.graph_edge_ids):
            raise ValueError("Graph-authorized status requires proposition and relation IDs")
        if not has_graph_projection and (self.proposition_node_id or self.graph_edge_ids):
            raise ValueError("Non-authorized status cannot claim graph projection IDs")
        if len(set(self.graph_edge_ids)) != len(self.graph_edge_ids):
            raise ValueError("Graph edge IDs must be unique")

        chain = self.comparison.comparison.chain
        exact_passages = {
            passage.passage_id: passage
            for passage in (*chain.bundle.passages, *chain.context_passages)
        }
        cited_commitments: dict[str, set[str]] = {}
        for state in chain.verification.commitment_states:
            for passage_id in state.passage_ids:
                cited_commitments.setdefault(passage_id, set()).add(state.commitment_id)
        actual_passage_ids = {item.passage.passage_id for item in self.cited_passages}
        if actual_passage_ids != set(cited_commitments):
            raise ValueError("Committed comparison must retain all verifier-cited passages")
        for cited in self.cited_passages:
            if exact_passages.get(cited.passage.passage_id) != cited.passage:
                raise ValueError("Cited passage must exactly match the committed chain passage")
            if set(cited.commitment_ids) != cited_commitments.get(cited.passage.passage_id, set()):
                raise ValueError("Passage commitment IDs must match scoped verification citations")
        if len({item.passage.passage_id for item in self.cited_passages}) != len(
            self.cited_passages
        ):
            raise ValueError("Cited passage IDs must be unique")
        return self


class AuthorizedGraphRelation(ContractModel):
    """A relation already validated against repository commit membership."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["phase6-authorized-graph-relation-v1"] = (
        "phase6-authorized-graph-relation-v1"
    )

    edge: GraphEdge
    proposition_node: GraphNode
    commit_id: str
    verified_edge_id: EvidenceEdgeId
    classification_id: ClassificationId


class Phase6AssessmentView(ContractModel):
    """Complete frozen read model; construction alone conveys no authority."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["phase6-assessment-view-v1"] = "phase6-assessment-view-v1"

    assessment_id: AssessmentId
    snapshot_id: str
    as_of: date
    view_version: Literal[1]
    commit_ids: tuple[str, ...]
    committed_comparisons: tuple[CommittedComparisonView, ...]
    authorized_graph_relations: tuple[AuthorizedGraphRelation, ...]
    targets: tuple[MCUComparisonProfile, ...]
    candidate_outcomes: tuple[Phase6CandidateLedgerRecord, ...]
    coverage: Phase6CoverageLedger
    multi_source_context: tuple[Phase6DerivedLedgerRecord, ...]
    patent_screenings: tuple[Phase6DerivedLedgerRecord, ...]
    lineage: tuple[EvidenceLineageCluster, ...]
    audit_refs: tuple[str, ...]

    @model_validator(mode="after")
    def graph_relations_match_comparisons(self) -> Self:
        if len(set(self.commit_ids)) != len(self.commit_ids):
            raise ValueError("Assessment view commit IDs must be unique")
        comparisons = {
            (
                item.commit_id,
                item.comparison.comparison.chain.edge.edge_id,
                item.comparison.classification.classification_id,
            ): item
            for item in self.committed_comparisons
        }
        if len(comparisons) != len(self.committed_comparisons):
            raise ValueError("Committed comparison identities must be unique")
        for item in self.committed_comparisons:
            if item.commit_id not in self.commit_ids:
                raise ValueError("Comparison commit is absent from assessment commit IDs")
        for relation in self.authorized_graph_relations:
            key = (relation.commit_id, relation.verified_edge_id, relation.classification_id)
            comparison = comparisons.get(key)
            if comparison is None:
                raise ValueError(
                    "Authorized graph relation IDs do not match a committed comparison"
                )
            if comparison.projection_status != "GRAPH_AUTHORIZED":
                raise ValueError("Authorized relation requires graph-authorized comparison status")
            if relation.edge.edge_id not in comparison.graph_edge_ids:
                raise ValueError("Authorized edge ID is absent from its committed comparison")
            if relation.proposition_node.node_id != comparison.proposition_node_id:
                raise ValueError("Authorized proposition node does not match its comparison")
            if relation.edge.verification is None or (
                relation.edge.verification.verified_edge_id != relation.verified_edge_id
            ):
                raise ValueError("Authorized edge verification ID does not match comparison")
        return self
