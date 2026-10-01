"""SQLAlchemy 2.x evidence graph repository over SQLite.

Returns domain models only. Batch writes are transactional; identical
re-persistence is idempotent; different content under an existing identity is
rejected because graph history is append-only.
"""

import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, JsonValue
from sqlalchemy import Engine, create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from novelty_harness.domain.enums import PrecedentState
from novelty_harness.domain.ids import SourceId
from novelty_harness.evidence.graph.assessment_ledger import (
    Phase6AssessmentSnapshotRecord,
    Phase6CandidateLedgerRecord,
    Phase6DerivedLedgerRecord,
    Phase6TargetLedgerRecord,
    phase6_assessment_snapshot_id,
    phase6_candidate_record_id,
    phase6_derived_record_id,
    phase6_target_record_id,
)
from novelty_harness.evidence.graph.migrations import ensure_schema
from novelty_harness.evidence.graph.models import (
    PHASE6_EDGE_KINDS,
    GraphEdge,
    GraphEdgeKind,
    GraphNode,
    GraphNodeKind,
)
from novelty_harness.evidence.graph.phase6_mapping import verified_edge_graph_fragment
from novelty_harness.evidence.graph.repository import (
    ContentAuthorityError,
    GraphDirection,
    Phase6CommitReceipt,
    Phase6CommitRecord,
    ResolvedPhase6Commit,
)
from novelty_harness.evidence.graph.sqlalchemy_models import (
    GraphEdgeRow,
    GraphNodeRow,
    LineageClusterMemberRow,
    LineageClusterRow,
    Phase6AssessmentCandidateRow,
    Phase6AssessmentDerivedRow,
    Phase6AssessmentSnapshotRow,
    Phase6AssessmentTargetRow,
    Phase6CommitRow,
    Phase6GraphEdgeMembershipRow,
    Phase6GraphNodeMembershipRow,
    VerificationObservationRow,
    VerifiedChainRow,
    VerifiedClassificationRow,
    VerifiedEdgeRow,
)
from novelty_harness.evidence.precedent.gates import ClassifiedComparison
from novelty_harness.evidence.provenance.models import EvidenceLineageCluster
from novelty_harness.evidence.verification.gates import validate_verified_chain
from novelty_harness.evidence.verification.integrity import VerifiedEvidenceChain
from novelty_harness.evidence.verification.models import VerifiedEvidenceEdge
from novelty_harness.runtime.tracing.hashing import canonical_hash, canonical_json


def _semantic_document(value: JsonValue | BaseModel) -> str:
    """Compare immutable meaning while observation times live in separate events."""

    def without_clock(item: JsonValue) -> JsonValue:
        if isinstance(item, dict):
            return {key: without_clock(part) for key, part in item.items() if key != "observed_at"}
        if isinstance(item, list):
            return [without_clock(part) for part in item]
        return item

    document = cast(
        JsonValue,
        json.loads(value) if isinstance(value, str) else json.loads(canonical_json(value)),
    )
    return canonical_json(without_clock(document))


def _phase6_commit_id(
    assessment_id: str,
    edge_ids: tuple[str, ...],
    classification_ids: tuple[str, ...],
) -> str:
    return "p6commit_" + canonical_hash(
        cast(
            JsonValue,
            {
                "assessment_id": assessment_id,
                "edge_ids": list(edge_ids),
                "classification_ids": list(classification_ids),
            },
        )
    )


def _sqlite_engine(database: Path | None) -> Engine:
    if database is None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        engine = create_engine(f"sqlite:///{database}")

    @event.listens_for(engine, "connect")
    def _enforce_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


class SqlAlchemyEvidenceGraphRepository:
    """First storage implementation of the evidence graph repository protocol."""

    def __init__(self, database: Path | str | None = None) -> None:
        path = Path(database) if database is not None else None
        self._engine = _sqlite_engine(path)
        ensure_schema(self._engine)

    @property
    def engine(self) -> Engine:
        return self._engine

    def upsert(
        self,
        *,
        nodes: Sequence[GraphNode] = (),
        edges: Sequence[GraphEdge] = (),
        clusters: Sequence[EvidenceLineageCluster] = (),
        verified_edges: Sequence[VerifiedEvidenceEdge] = (),
        verified_chains: Sequence[VerifiedEvidenceChain] = (),
        classified_comparisons: Sequence[ClassifiedComparison] = (),
    ) -> Phase6CommitReceipt | None:
        receipt: Phase6CommitReceipt | None = None
        commit_record: Phase6CommitRecord | None = None
        if classified_comparisons:
            assessments = {item.comparison.assessment_id for item in classified_comparisons}
            if len(assessments) != 1:
                raise ValueError("One Phase 6 commit must belong to one assessment")
            assessment_id = next(iter(assessments))
            edge_ids = tuple(item.comparison.chain.edge.edge_id for item in classified_comparisons)
            classification_ids = tuple(
                item.classification.classification_id for item in classified_comparisons
            )
            commit_record = Phase6CommitRecord(
                commit_id=_phase6_commit_id(assessment_id, edge_ids, classification_ids),
                assessment_id=assessment_id,
                committed_edge_ids=edge_ids,
                committed_classification_ids=classification_ids,
            )
            receipt = Phase6CommitReceipt(
                commit_id=commit_record.commit_id,
                assessment_id=commit_record.assessment_id,
                committed_edge_ids=commit_record.committed_edge_ids,
                committed_classification_ids=commit_record.committed_classification_ids,
            )
        with Session(self._engine) as session, session.begin():
            self._verify_edge_endpoints(session, nodes, edges)
            batch_chains = {chain.edge.edge_id: chain for chain in verified_chains}
            batch_classifications = {
                item.comparison.chain.edge.edge_id: item for item in classified_comparisons
            }
            for verified in verified_edges:
                chain = batch_chains.get(verified.edge_id) or self._resolve_verified_chain(
                    session, verified.edge_id
                )
                if chain is None or _semantic_document(chain.edge) != _semantic_document(verified):
                    raise ValueError("Verified edge has no matching resolved semantic chain")
                validate_verified_chain(chain)
                self._check_content_authority(session, chain, nodes)
                if (
                    verified.relation is not None
                    and verified.edge_id not in batch_classifications
                    and session.get(VerifiedClassificationRow, verified.edge_id) is None
                ):
                    raise ValueError("Classified verified edge has no authoritative classification")
                self._persist_verified_edge(session, verified)
            for chain in verified_chains:
                self._persist_verified_chain(session, chain, nodes)
            for classified in classified_comparisons:
                self._persist_classification(session, classified, nodes)
            derived_nodes, derived_edges = self._verify_phase6_edges(
                session, nodes, edges, verified_edges, verified_chains, classified_comparisons
            )
            if commit_record is None and (
                any(edge.kind in PHASE6_EDGE_KINDS for edge in edges)
                or any(node.kind == GraphNodeKind.EVIDENCE_PROPOSITION for node in nodes)
            ):
                raise ValueError("Phase 6 graph projection requires a semantic commit")
            for node in nodes:
                self._persist_node(session, derived_nodes.get(node.node_id, node))
            for edge in edges:
                self._persist_edge(session, derived_edges.get(edge.edge_id, edge))
            for cluster in clusters:
                self._persist_cluster(session, cluster)
            if commit_record is not None:
                self._persist_phase6_commit(session, commit_record)
                for edge in edges:
                    if edge.kind in PHASE6_EDGE_KINDS:
                        self._persist_phase6_graph_membership(session, edge, commit_record)
                for node in nodes:
                    if node.kind == GraphNodeKind.EVIDENCE_PROPOSITION:
                        self._persist_phase6_node_membership(session, node, commit_record)
        return receipt

    def record_phase6_assessment(
        self,
        snapshot: Phase6AssessmentSnapshotRecord,
        *,
        targets: Sequence[Phase6TargetLedgerRecord],
        candidates: Sequence[Phase6CandidateLedgerRecord],
        derived: Sequence[Phase6DerivedLedgerRecord],
    ) -> str:
        """Persist one complete append-only Phase 6 assessment transaction."""

        snapshot = Phase6AssessmentSnapshotRecord.model_validate(snapshot.model_dump(mode="json"))
        target_records = tuple(
            Phase6TargetLedgerRecord.model_validate(item.model_dump(mode="json"))
            for item in targets
        )
        candidate_records = tuple(
            Phase6CandidateLedgerRecord.model_validate(item.model_dump(mode="json"))
            for item in candidates
        )
        derived_records = tuple(
            Phase6DerivedLedgerRecord.model_validate(item.model_dump(mode="json"))
            for item in derived
        )

        expected_snapshot_id = phase6_assessment_snapshot_id(
            snapshot,
            targets=target_records,
            candidates=candidate_records,
            derived=derived_records,
        )
        if snapshot.snapshot_id != expected_snapshot_id:
            raise ValueError("Phase 6 snapshot ID does not match its immutable facts")
        target_ids = tuple(phase6_target_record_id(item) for item in target_records)
        candidate_ids = tuple(phase6_candidate_record_id(item) for item in candidate_records)
        derived_ids = tuple(phase6_derived_record_id(item) for item in derived_records)
        if (
            snapshot.target_record_ids != target_ids
            or snapshot.candidate_record_ids != candidate_ids
            or snapshot.derived_record_ids != derived_ids
        ):
            raise ValueError("Phase 6 snapshot record IDs do not match its ledger records")

        for item in (*target_records, *candidate_records, *derived_records):
            if item.snapshot_id != snapshot.snapshot_id:
                raise ValueError("Ledger record belongs to a different snapshot")
            if item.assessment_id != snapshot.assessment_id:
                raise ValueError("Ledger record assessment does not match its snapshot")
        target_by_id = {item.profile.target_id: item for item in target_records}
        if len(target_by_id) != len(target_records):
            raise ValueError("Assessment ledger contains duplicate target IDs")
        if len(
            {(item.target_id, item.source_id, item.source_version_id) for item in candidate_records}
        ) != len(candidate_records):
            raise ValueError("Assessment ledger contains duplicate candidate identities")
        if any(item.target_id not in target_by_id for item in candidate_records):
            raise ValueError("Candidate references a target absent from its snapshot")
        if any(item.target_id not in target_by_id for item in derived_records):
            raise ValueError("Derived record references a target absent from its snapshot")

        assessed_commit_ids = {
            item.commit_id for item in candidate_records if item.decision == "ASSESSED"
        }
        if None in assessed_commit_ids or assessed_commit_ids != set(snapshot.commit_ids):
            raise ValueError("Snapshot commit IDs must exactly match assessed candidate commits")

        with Session(self._engine) as session, session.begin():
            for candidate in candidate_records:
                source_row = session.get(GraphNodeRow, candidate.source_id)
                source_node = (
                    GraphNode.model_validate_json(source_row.document_json)
                    if source_row is not None
                    else None
                )
                if source_node is None or source_node.kind != GraphNodeKind.SOURCE:
                    raise ValueError("Candidate source does not resolve to a source record")
                if candidate.source_version_id is not None:
                    version_row = session.get(GraphNodeRow, candidate.source_version_id)
                    version_node = (
                        GraphNode.model_validate_json(version_row.document_json)
                        if version_row is not None
                        else None
                    )
                    if (
                        version_node is None
                        or version_node.kind != GraphNodeKind.SOURCE_VERSION
                        or version_node.attributes.get("source_id") != candidate.source_id
                    ):
                        raise ValueError("Candidate source version does not belong to its source")
                if candidate.decision == "ASSESSED":
                    assert candidate.commit_id is not None
                    commit_row = session.get(Phase6CommitRow, candidate.commit_id)
                    if commit_row is None:
                        raise ValueError("Assessed candidate references a missing commit")
                    commit = Phase6CommitRecord.model_validate_json(commit_row.document_json)
                    receipt = Phase6CommitReceipt(
                        commit_id=commit.commit_id,
                        assessment_id=commit.assessment_id,
                        committed_edge_ids=commit.committed_edge_ids,
                        committed_classification_ids=commit.committed_classification_ids,
                    )
                    resolved = self._resolve_phase6_commit_in_session(session, receipt)
                    matches = [
                        comparison
                        for comparison in resolved.comparisons
                        if comparison.comparison.chain.edge.edge_id == candidate.verified_edge_id
                        and comparison.classification.classification_id
                        == candidate.classification_id
                    ]
                    if commit.assessment_id != snapshot.assessment_id or len(matches) != 1:
                        raise ValueError("Assessed candidate does not join to its commit manifest")
                    chain = matches[0].comparison.chain
                    if (
                        chain.source.source_id != candidate.source_id
                        or chain.edge.mcu_id != candidate.target_id
                        or (chain.version.version_id if chain.version is not None else None)
                        != candidate.source_version_id
                    ):
                        raise ValueError("Assessed candidate source/version/target join is invalid")
            for commit_id in snapshot.commit_ids:
                row = session.get(Phase6CommitRow, commit_id)
                if (
                    row is None
                    or Phase6CommitRecord.model_validate_json(row.document_json).assessment_id
                    != snapshot.assessment_id
                ):
                    raise ValueError("Snapshot references a missing or foreign assessment commit")
            for record in derived_records:
                if not set(record.input_commit_ids) <= set(snapshot.commit_ids):
                    raise ValueError("Derived record references a commit outside its snapshot")
                for commit_id, edge_id, classification_id in zip(
                    record.input_commit_ids,
                    record.input_edge_ids,
                    record.input_classification_ids,
                    strict=True,
                ):
                    commit_row = session.get(Phase6CommitRow, commit_id)
                    if commit_row is None:
                        raise ValueError("Derived record references a missing commit")
                    commit = Phase6CommitRecord.model_validate_json(commit_row.document_json)
                    if (edge_id, classification_id) not in set(
                        zip(
                            commit.committed_edge_ids,
                            commit.committed_classification_ids,
                            strict=True,
                        )
                    ):
                        raise ValueError("Derived input is absent from its commit manifest")

            for cluster_id in snapshot.lineage_cluster_ids:
                if session.get(LineageClusterRow, cluster_id) is None:
                    raise ValueError("Snapshot references a missing lineage cluster")

            self._insert_or_verify_ledger_row(
                session,
                Phase6AssessmentSnapshotRow,
                snapshot.snapshot_id,
                {
                    "snapshot_id": snapshot.snapshot_id,
                    "assessment_id": snapshot.assessment_id,
                    "document_json": canonical_json(snapshot),
                },
                "Phase 6 snapshot",
            )
            for record, record_id in zip(target_records, target_ids, strict=True):
                self._insert_or_verify_ledger_row(
                    session,
                    Phase6AssessmentTargetRow,
                    record_id,
                    {
                        "record_id": record_id,
                        "snapshot_id": record.snapshot_id,
                        "assessment_id": record.assessment_id,
                        "target_id": record.profile.target_id,
                        "document_json": canonical_json(record),
                    },
                    "Phase 6 target",
                )
            for record, record_id in zip(candidate_records, candidate_ids, strict=True):
                self._insert_or_verify_ledger_row(
                    session,
                    Phase6AssessmentCandidateRow,
                    record_id,
                    {
                        "record_id": record_id,
                        "snapshot_id": record.snapshot_id,
                        "assessment_id": record.assessment_id,
                        "target_id": record.target_id,
                        "source_id": record.source_id,
                        "source_version_id": record.source_version_id,
                        "commit_id": record.commit_id,
                        "document_json": canonical_json(record),
                    },
                    "Phase 6 candidate",
                )
            for record, record_id in zip(derived_records, derived_ids, strict=True):
                self._insert_or_verify_ledger_row(
                    session,
                    Phase6AssessmentDerivedRow,
                    record_id,
                    {
                        "record_id": record_id,
                        "snapshot_id": record.snapshot_id,
                        "assessment_id": record.assessment_id,
                        "target_id": record.target_id,
                        "kind": record.kind,
                        "document_json": canonical_json(record),
                    },
                    "Phase 6 derived record",
                )
        return snapshot.snapshot_id

    @staticmethod
    def _insert_or_verify_ledger_row(
        session: Session,
        row_type: type[Any],
        row_id: str,
        values: dict[str, Any],
        label: str,
    ) -> None:
        row = session.get(row_type, row_id)
        if row is None:
            session.add(row_type(**values))
        elif any(getattr(row, key) != value for key, value in values.items()):
            raise ValueError(f"{label} identity already exists with different content")

    def _persist_phase6_graph_membership(
        self, session: Session, edge: GraphEdge, commit: Phase6CommitRecord
    ) -> None:
        """Bind a derived graph relation to its exact semantic transaction."""

        reference = edge.verification
        if reference is None:
            raise ValueError("Phase 6 graph projection lacks a verified edge")
        membership = dict(
            zip(commit.committed_edge_ids, commit.committed_classification_ids, strict=True)
        )
        classification_id = membership.get(reference.verified_edge_id)
        if classification_id is None:
            raise ValueError("Phase 6 graph projection is outside the semantic commit")
        row = session.get(Phase6GraphEdgeMembershipRow, edge.edge_id)
        if row is None:
            session.add(
                Phase6GraphEdgeMembershipRow(
                    edge_id=edge.edge_id,
                    commit_id=commit.commit_id,
                    verified_edge_id=reference.verified_edge_id,
                    classification_id=classification_id,
                )
            )
        elif (
            row.commit_id != commit.commit_id
            or row.verified_edge_id != reference.verified_edge_id
            or row.classification_id != classification_id
        ):
            raise ValueError("Phase 6 graph projection has different commit membership")

    def _persist_phase6_node_membership(
        self, session: Session, node: GraphNode, commit: Phase6CommitRecord
    ) -> None:
        verified_edge_id = node.attributes.get("verified_edge_id")
        membership = dict(
            zip(commit.committed_edge_ids, commit.committed_classification_ids, strict=True)
        )
        classification_id = (
            membership.get(verified_edge_id) if isinstance(verified_edge_id, str) else None
        )
        if classification_id is None:
            raise ValueError("Phase 6 proposition node is outside the semantic commit")
        row = session.get(Phase6GraphNodeMembershipRow, node.node_id)
        if row is None:
            session.add(
                Phase6GraphNodeMembershipRow(
                    node_id=node.node_id,
                    commit_id=commit.commit_id,
                    verified_edge_id=verified_edge_id,
                    classification_id=classification_id,
                )
            )
        elif (
            row.commit_id != commit.commit_id
            or row.verified_edge_id != verified_edge_id
            or row.classification_id != classification_id
        ):
            raise ValueError("Phase 6 proposition node has different commit membership")

    def _persist_phase6_commit(self, session: Session, record: Phase6CommitRecord) -> None:
        """Write the manifest inside the transaction that wrote its semantic rows."""

        session.flush()
        for edge_id, classification_id in zip(
            record.committed_edge_ids, record.committed_classification_ids, strict=True
        ):
            edge = session.get(VerifiedEdgeRow, edge_id)
            chain = session.get(VerifiedChainRow, edge_id)
            classification = session.get(VerifiedClassificationRow, edge_id)
            if (
                edge is None
                or chain is None
                or classification is None
                or classification.classification_id != classification_id
            ):
                raise ValueError("Phase 6 commit references unresolved semantic artifacts")
        document = canonical_json(record)
        row = session.get(Phase6CommitRow, record.commit_id)
        if row is None:
            session.add(
                Phase6CommitRow(
                    commit_id=record.commit_id,
                    assessment_id=record.assessment_id,
                    document_json=document,
                )
            )
        elif row.document_json != document:
            raise ValueError("Phase 6 commit identity already exists with different content")

    def resolve_phase6_commit(self, receipt: Phase6CommitReceipt) -> ResolvedPhase6Commit:
        """Resolve caller-held IDs to the exact persisted transaction manifest."""

        receipt = Phase6CommitReceipt.model_validate(receipt.model_dump(mode="json"))
        if receipt.commit_id is None:
            raise ValueError("Phase 6 commit receipt has no persisted commit identity")
        with Session(self._engine) as session:
            return self._resolve_phase6_commit_in_session(session, receipt)

    def _resolve_phase6_commit_in_session(
        self, session: Session, receipt: Phase6CommitReceipt
    ) -> ResolvedPhase6Commit:
        if receipt.commit_id is None:
            raise ValueError("Phase 6 commit receipt has no persisted commit identity")
        row = session.get(Phase6CommitRow, receipt.commit_id)
        if row is None:
            raise ValueError("Phase 6 commit receipt has no persisted commit record")
        record = Phase6CommitRecord.model_validate_json(row.document_json)
        if (
            row.assessment_id != record.assessment_id
            or record.commit_id != receipt.commit_id
            or record.assessment_id != receipt.assessment_id
            or record.committed_edge_ids != receipt.committed_edge_ids
            or record.committed_classification_ids != receipt.committed_classification_ids
            or record.commit_id
            != _phase6_commit_id(
                record.assessment_id,
                record.committed_edge_ids,
                record.committed_classification_ids,
            )
        ):
            raise ValueError("Phase 6 commit receipt differs from persisted authority")
        comparisons: list[ClassifiedComparison] = []
        for edge_id, classification_id in zip(
            record.committed_edge_ids, record.committed_classification_ids, strict=True
        ):
            edge = self._resolve_verified_edge(session, edge_id)
            chain = self._resolve_verified_chain(session, edge_id)
            classification_row = session.get(VerifiedClassificationRow, edge_id)
            if edge is None or chain is None or classification_row is None:
                raise ValueError("Phase 6 commit has missing authoritative semantic artifacts")
            classified = ClassifiedComparison.model_validate_json(classification_row.document_json)
            self._check_chain_nodes(session, chain, ())
            if (
                classification_row.classification_id != classification_id
                or classified.classification.classification_id != classification_id
                or classified.comparison.assessment_id != record.assessment_id
                or chain.assessment_id != record.assessment_id
                or _semantic_document(chain.edge) != _semantic_document(edge)
                or _semantic_document(classified.comparison.chain) != _semantic_document(chain)
            ):
                raise ValueError("Phase 6 commit artifacts differ from persisted authority")
            comparisons.append(classified)
        return ResolvedPhase6Commit(record=record, comparisons=tuple(comparisons))

    def _verify_edge_endpoints(
        self,
        session: Session,
        nodes: Sequence[GraphNode],
        edges: Sequence[GraphEdge],
    ) -> None:
        batch_ids = {node.node_id for node in nodes}
        persisted = set(session.scalars(select(GraphNodeRow.node_id)).all())
        known = batch_ids | persisted
        for edge in edges:
            for endpoint in (edge.source_node_id, edge.target_node_id):
                if endpoint not in known:
                    raise ValueError(
                        f"Graph edge {edge.edge_id} has a dangling endpoint: {endpoint}"
                    )

    def _persist_node(self, session: Session, node: GraphNode) -> None:
        document = canonical_json(node)
        row = session.get(GraphNodeRow, node.node_id)
        if row is None:
            session.add(
                GraphNodeRow(
                    node_id=node.node_id,
                    kind=node.kind.value,
                    label=node.label,
                    document_json=document,
                )
            )
            return
        if _semantic_document(row.document_json) != _semantic_document(document):
            raise ValueError(
                f"Graph node {node.node_id} already exists with different content; "
                "history is append-only"
            )

    def _persist_verified_edge(self, session: Session, verified: VerifiedEvidenceEdge) -> None:
        document = canonical_json(verified)
        row = session.get(VerifiedEdgeRow, verified.edge_id)
        if row is None:
            session.add(
                VerifiedEdgeRow(
                    edge_id=verified.edge_id,
                    source_id=verified.source_id,
                    mcu_id=verified.mcu_id,
                    document_json=document,
                )
            )
        elif _semantic_document(row.document_json) != _semantic_document(document):
            raise ValueError(
                f"Verified edge {verified.edge_id} already exists with different content; "
                "history is append-only"
            )
        observation_id = "obs_" + canonical_hash(
            {
                "edge_id": verified.edge_id,
                "observed_at": verified.observed_at.isoformat(),
            }
        )
        if session.get(VerificationObservationRow, observation_id) is None:
            session.add(
                VerificationObservationRow(
                    observation_id=observation_id,
                    edge_id=verified.edge_id,
                    observed_at=verified.observed_at.isoformat(),
                )
            )

    def _resolve_verified_edge(
        self, session: Session, verified_edge_id: str
    ) -> VerifiedEvidenceEdge | None:
        row = session.get(VerifiedEdgeRow, verified_edge_id)
        if row is None:
            return None
        return VerifiedEvidenceEdge.model_validate_json(row.document_json)

    def _resolve_verified_chain(
        self, session: Session, verified_edge_id: str
    ) -> VerifiedEvidenceChain | None:
        row = session.get(VerifiedChainRow, verified_edge_id)
        return VerifiedEvidenceChain.model_validate_json(row.document_json) if row else None

    def _persist_verified_chain(
        self,
        session: Session,
        chain: VerifiedEvidenceChain,
        batch_nodes: Sequence[GraphNode],
    ) -> None:
        self._check_chain_nodes(session, chain, batch_nodes)
        document = canonical_json(chain)
        row = session.get(VerifiedChainRow, chain.edge.edge_id)
        if row is None:
            session.add(VerifiedChainRow(edge_id=chain.edge.edge_id, document_json=document))
        elif _semantic_document(row.document_json) != _semantic_document(document):
            raise ValueError(
                f"Verified semantic chain {chain.edge.edge_id} already exists "
                "with different content"
            )

    def _check_chain_nodes(
        self,
        session: Session,
        chain: VerifiedEvidenceChain,
        batch_nodes: Sequence[GraphNode],
    ) -> None:
        cited = validate_verified_chain(chain)
        self._check_content_authority(session, chain, batch_nodes)
        by_id = {node.node_id: node for node in batch_nodes}

        def node(identity: str) -> GraphNode | None:
            present = by_id.get(identity)
            if present is not None:
                return present
            row = session.get(GraphNodeRow, identity)
            return GraphNode.model_validate_json(row.document_json) if row else None

        source_node = node(chain.source.source_id)
        if source_node is None or source_node.kind != GraphNodeKind.SOURCE:
            raise ValueError("Verified semantic chain has no persisted source node")
        if chain.version is not None:
            version_node = node(chain.version.version_id)
            if (
                version_node is None
                or version_node.kind != GraphNodeKind.SOURCE_VERSION
                or version_node.attributes.get("source_id") != chain.source.source_id
            ):
                raise ValueError("Verified semantic chain has no matching source-version node")
        for passage in cited:
            passage_node = node(passage.passage_id)
            if (
                passage_node is None
                or passage_node.kind != GraphNodeKind.PASSAGE
                or passage_node.attributes.get("source_id") != passage.source_id
                or passage_node.attributes.get("source_version_id") != passage.source_version_id
                or passage_node.attributes.get("content_hash") != passage.content_hash
            ):
                raise ValueError(
                    f"Verified semantic chain cites unresolved passage {passage.passage_id}"
                )

    def _check_content_authority(
        self,
        session: Session,
        chain: VerifiedEvidenceChain,
        batch_nodes: Sequence[GraphNode],
    ) -> None:
        """Bind chain provenance to one stored or concurrently supplied node authority."""

        def authority(identity: str, kind: GraphNodeKind, fields: tuple[str, ...]) -> GraphNode:
            row = session.get(GraphNodeRow, identity)
            stored = GraphNode.model_validate_json(row.document_json) if row is not None else None
            supplied = tuple(node for node in batch_nodes if node.node_id == identity)
            candidates = ((stored,) if stored is not None else ()) + supplied
            if not candidates or any(node.kind != kind for node in candidates):
                raise ContentAuthorityError(
                    f"No matching {kind.value} content authority for {identity}"
                )
            first = candidates[0]
            for node in candidates[1:]:
                if any(
                    node.attributes.get(field) != first.attributes.get(field) for field in fields
                ):
                    raise ContentAuthorityError(
                        f"Conflicting {kind.value} content authority for {identity}"
                    )
            return first

        source = authority(
            chain.source.source_id,
            GraphNodeKind.SOURCE,
            ("content_hash", "access_state"),
        )
        stored_source_hash = source.attributes.get("content_hash")
        stored_source_access = source.attributes.get("access_state")
        if stored_source_hash is not None and stored_source_hash != chain.source.content_hash:
            raise ContentAuthorityError("Source content authority conflicts with semantic chain")
        if (
            stored_source_access is not None
            and stored_source_access != chain.source.access_state.value
        ):
            raise ContentAuthorityError("Source access authority conflicts with semantic chain")

        if chain.version is None:
            expected_digest = chain.source.content_hash
            expected_access = chain.source.access_state.value
            if expected_digest is None or stored_source_hash != expected_digest:
                raise ContentAuthorityError("Unversioned source has no matching content authority")
            if stored_source_access != expected_access:
                raise ContentAuthorityError(
                    "Unversioned source access authority conflicts with semantic chain"
                )
        else:
            version = authority(
                chain.version.version_id,
                GraphNodeKind.SOURCE_VERSION,
                ("source_id", "content_hash", "access_state"),
            )
            expected_digest = chain.version.content_hash
            expected_access = chain.version.access_state.value
            if (
                version.attributes.get("source_id") != chain.source.source_id
                or version.attributes.get("content_hash") != expected_digest
                or version.attributes.get("access_state") != expected_access
            ):
                raise ContentAuthorityError(
                    "Version content authority conflicts with semantic chain"
                )

        for passage in (*chain.bundle.passages, *chain.context_passages):
            proof = passage.attestation
            if (
                proof is None
                or proof.parent_content_digest != expected_digest
                or proof.parent.access_state.value != expected_access
                or passage.access_state.value != expected_access
            ):
                raise ContentAuthorityError("Passage provenance conflicts with content authority")

    def _verify_phase6_edges(
        self,
        session: Session,
        nodes: Sequence[GraphNode],
        edges: Sequence[GraphEdge],
        batch: Sequence[VerifiedEvidenceEdge],
        chains: Sequence[VerifiedEvidenceChain],
        classified_comparisons: Sequence[ClassifiedComparison],
    ) -> tuple[dict[str, GraphNode], dict[str, GraphEdge]]:
        """Resolve every Phase 6 verification reference against a real artifact."""

        derived_nodes: dict[str, GraphNode] = {}
        derived_edges: dict[str, GraphEdge] = {}
        batch_by_id = {verified.edge_id: verified for verified in batch}
        chain_by_id = {chain.edge.edge_id: chain for chain in chains}
        classification_by_id = {
            item.comparison.chain.edge.edge_id: item for item in classified_comparisons
        }
        for item in classified_comparisons:
            ClassifiedComparison.model_validate(item.model_dump(mode="json"))
        expected_relation = {
            GraphEdgeKind.DIRECT_PRECEDENT: PrecedentState.DIRECT_PRECEDENT,
            GraphEdgeKind.STRONG_PARTIAL_PRECEDENT: PrecedentState.STRONG_PARTIAL_PRECEDENT,
            GraphEdgeKind.COMPONENT_PRECEDENT: PrecedentState.COMPONENT_PRECEDENT_ONLY,
            GraphEdgeKind.ANALOGOUS: PrecedentState.ANALOGOUS_PRECEDENT,
            GraphEdgeKind.NO_MATCH: PrecedentState.NO_DIRECT_PRECEDENT_IDENTIFIED,
        }
        for edge in edges:
            if edge.kind not in PHASE6_EDGE_KINDS:
                continue
            reference = edge.verification
            if reference is None:
                raise ValueError(
                    f"Phase 6 graph edge {edge.edge_id} lacks a verification reference"
                )
            verified = batch_by_id.get(reference.verified_edge_id) or self._resolve_verified_edge(
                session, reference.verified_edge_id
            )
            if verified is None:
                raise ValueError(
                    f"Graph edge {edge.edge_id} references unknown verified edge "
                    f"{reference.verified_edge_id}"
                )
            chain = chain_by_id.get(reference.verified_edge_id) or self._resolve_verified_chain(
                session, reference.verified_edge_id
            )
            if chain is None:
                raise ValueError(f"Graph edge {edge.edge_id} has no resolved semantic chain")
            validate_verified_chain(chain)
            self._check_content_authority(session, chain, nodes)
            if chain.edge != verified:
                if _semantic_document(chain.edge) != _semantic_document(verified):
                    raise ValueError("Graph edge semantic chain differs from verified artifact")
            classified = classification_by_id.get(reference.verified_edge_id)
            if classified is None:
                row = session.get(VerifiedClassificationRow, reference.verified_edge_id)
                if row is not None:
                    classified = ClassifiedComparison.model_validate_json(row.document_json)
            if classified is None:
                raise ValueError("Phase 6 graph edge has no authoritative classification")
            if _semantic_document(classified.comparison.chain) != _semantic_document(chain):
                raise ValueError("Graph classification belongs to another semantic chain")
            _, expected_edges = verified_edge_graph_fragment(
                (chain.edge,),
                (classified.classification,),
                observed_at=edge.observed_at,
                provenance=edge.provenance,
            )
            expected = next((item for item in expected_edges if item.edge_id == edge.edge_id), None)
            if expected is None or (
                expected.kind != edge.kind
                or expected.source_node_id != edge.source_node_id
                or expected.target_node_id != edge.target_node_id
                or expected.attributes != edge.attributes
                or expected.verification != edge.verification
            ):
                raise ValueError(
                    "Phase 6 graph attributes differ from repository-derived projection"
                )
            derived_edges[edge.edge_id] = expected
            if verified.source_id != edge.source_node_id or verified.mcu_id != edge.target_node_id:
                raise ValueError(
                    f"Graph edge {edge.edge_id} endpoints do not match the verified artifact"
                )
            if (
                verified.support_state != reference.support_state
                or verified.decisive != reference.decisive
                or verified.relation != reference.precedent_relation
            ):
                raise ValueError(
                    f"Graph edge {edge.edge_id} support state, decisiveness or relation "
                    "does not match the verified artifact"
                )
            relation_expected = expected_relation.get(edge.kind)
            if relation_expected is not None and verified.relation != relation_expected:
                raise ValueError(
                    f"Graph edge {edge.edge_id} kind does not match the verified relation"
                )
            if reference.decisive and (
                not verified.eligibility.decisive or verified.chronology.state != "PREDATES_CUTOFF"
            ):
                raise ValueError(
                    f"Graph edge {edge.edge_id} claims decisiveness without eligible chronology"
                )
        for node in nodes:
            if node.kind != GraphNodeKind.EVIDENCE_PROPOSITION:
                continue
            edge_id = node.attributes.get("verified_edge_id")
            if not isinstance(edge_id, str):
                raise ValueError("Proposition node lacks a verified edge identity")
            classified = classification_by_id.get(edge_id)
            if classified is None:
                row = session.get(VerifiedClassificationRow, edge_id)
                if row is not None:
                    classified = ClassifiedComparison.model_validate_json(row.document_json)
            if classified is None:
                raise ValueError("Proposition node lacks authoritative classification")
            self._check_content_authority(session, classified.comparison.chain, nodes)
            expected_nodes, _ = verified_edge_graph_fragment(
                (classified.comparison.chain.edge,),
                (classified.classification,),
                observed_at=node.observed_at,
                provenance=node.provenance,
            )
            expected = next((item for item in expected_nodes if item.node_id == node.node_id), None)
            if expected is None or expected.attributes != node.attributes:
                raise ValueError("Proposition node attributes differ from authoritative comparison")
            derived_nodes[node.node_id] = expected
        return derived_nodes, derived_edges

    def _persist_classification(
        self,
        session: Session,
        classified: ClassifiedComparison,
        batch_nodes: Sequence[GraphNode],
    ) -> None:
        ClassifiedComparison.model_validate(classified.model_dump(mode="json"))
        self._check_content_authority(session, classified.comparison.chain, batch_nodes)
        edge_id = classified.comparison.chain.edge.edge_id
        if session.get(VerifiedChainRow, edge_id) is None:
            raise ValueError("Classification has no persisted verified chain")
        document = canonical_json(classified)
        row = session.get(VerifiedClassificationRow, edge_id)
        if row is None:
            session.add(
                VerifiedClassificationRow(
                    edge_id=edge_id,
                    classification_id=classified.classification.classification_id,
                    document_json=document,
                )
            )
        elif _semantic_document(row.document_json) != _semantic_document(document):
            raise ValueError("Verified classification identity or basis changed")

    def _persist_edge(self, session: Session, edge: GraphEdge) -> None:
        if edge.kind in PHASE6_EDGE_KINDS:
            if edge.verification is None or (
                edge.kind == GraphEdgeKind.DIRECT_PRECEDENT and not edge.verification.decisive
            ):
                raise ValueError("Phase 6 graph edges require an eligible verification reference")
        document = canonical_json(edge)
        row = session.get(GraphEdgeRow, edge.edge_id)
        if row is None:
            session.add(
                GraphEdgeRow(
                    edge_id=edge.edge_id,
                    kind=edge.kind.value,
                    source_node_id=edge.source_node_id,
                    target_node_id=edge.target_node_id,
                    document_json=document,
                )
            )
            return
        if _semantic_document(row.document_json) != _semantic_document(document):
            raise ValueError(
                f"Graph edge {edge.edge_id} already exists with different content; "
                "history is append-only"
            )

    def _persist_cluster(self, session: Session, cluster: EvidenceLineageCluster) -> None:
        document = canonical_json(cluster)
        row = session.get(LineageClusterRow, cluster.cluster_id)
        if row is None:
            session.add(LineageClusterRow(cluster_id=cluster.cluster_id, document_json=document))
        elif row.document_json != document:
            raise ValueError(
                f"Lineage cluster {cluster.cluster_id} already exists with different content; "
                "history is append-only"
            )
        session.flush()
        for source_id in cluster.source_ids:
            existing = session.get(LineageClusterMemberRow, source_id)
            if existing is not None:
                if existing.cluster_id != cluster.cluster_id:
                    raise ValueError(
                        f"Source {source_id} already belongs to lineage cluster "
                        f"{existing.cluster_id}"
                    )
                continue
            session.add(LineageClusterMemberRow(source_id=source_id, cluster_id=cluster.cluster_id))

    def get_node(self, node_id: str) -> GraphNode | None:
        with Session(self._engine) as session:
            row = session.get(GraphNodeRow, node_id)
            return self._authoritative_graph_node(session, row) if row else None

    def _committed_graph_comparison(
        self,
        session: Session,
        *,
        commit_id: str,
        verified_edge_id: str,
        classification_id: str,
    ) -> ClassifiedComparison | None:
        commit_row = session.get(Phase6CommitRow, commit_id)
        if commit_row is None:
            return None
        try:
            record = Phase6CommitRecord.model_validate_json(commit_row.document_json)
            resolved = self._resolve_phase6_commit_in_session(
                session,
                Phase6CommitReceipt(
                    commit_id=record.commit_id,
                    assessment_id=record.assessment_id,
                    committed_edge_ids=record.committed_edge_ids,
                    committed_classification_ids=record.committed_classification_ids,
                ),
            )
        except ValueError:
            return None
        if commit_id != record.commit_id:
            return None
        for classified in resolved.comparisons:
            if classified.comparison.chain.edge.edge_id == verified_edge_id:
                return (
                    classified
                    if classified.classification.classification_id == classification_id
                    else None
                )
        return None

    def _authoritative_graph_node(self, session: Session, row: GraphNodeRow) -> GraphNode | None:
        node = GraphNode.model_validate_json(row.document_json)
        if row.node_id != node.node_id or row.kind != node.kind.value or row.label != node.label:
            return None
        if node.kind != GraphNodeKind.EVIDENCE_PROPOSITION:
            return node
        membership = session.get(Phase6GraphNodeMembershipRow, row.node_id)
        if membership is None:
            return None
        classified = self._committed_graph_comparison(
            session,
            commit_id=membership.commit_id,
            verified_edge_id=membership.verified_edge_id,
            classification_id=membership.classification_id,
        )
        if (
            classified is None
            or node.attributes.get("verified_edge_id") != membership.verified_edge_id
        ):
            return None
        expected_nodes, _ = verified_edge_graph_fragment(
            (classified.comparison.chain.edge,),
            (classified.classification,),
            observed_at=node.observed_at,
            provenance=node.provenance,
        )
        return node if node in expected_nodes else None

    def observations(self, edge_id: str) -> tuple[datetime, ...]:
        """Return append-only observation times for one semantic edge."""

        with Session(self._engine) as session:
            rows = session.scalars(
                select(VerificationObservationRow.observed_at)
                .where(VerificationObservationRow.edge_id == edge_id)
                .order_by(VerificationObservationRow.observed_at)
            ).all()
        return tuple(datetime.fromisoformat(value) for value in rows)

    def get_edge(self, edge_id: str) -> GraphEdge | None:
        with Session(self._engine) as session:
            row = session.get(GraphEdgeRow, edge_id)
            return self._authoritative_graph_edge(session, row) if row else None

    def _authoritative_graph_edge(self, session: Session, row: GraphEdgeRow) -> GraphEdge | None:
        edge = GraphEdge.model_validate_json(row.document_json)
        if (
            row.kind != edge.kind.value
            or row.source_node_id != edge.source_node_id
            or row.target_node_id != edge.target_node_id
            or row.edge_id != edge.edge_id
        ):
            return None
        if edge.kind not in PHASE6_EDGE_KINDS:
            return edge
        membership = session.get(Phase6GraphEdgeMembershipRow, row.edge_id)
        if membership is None or edge.verification is None:
            return None
        classified = self._committed_graph_comparison(
            session,
            commit_id=membership.commit_id,
            verified_edge_id=membership.verified_edge_id,
            classification_id=membership.classification_id,
        )
        if (
            classified is None
            or edge.verification.verified_edge_id != membership.verified_edge_id
            or edge.attributes.get("classification_id") != membership.classification_id
        ):
            return None
        try:
            self._verify_phase6_edges(session, (), (edge,), (), (), ())
        except ValueError:
            return None
        return edge

    def nodes(self, *, kinds: frozenset[GraphNodeKind] | None = None) -> tuple[GraphNode, ...]:
        statement = select(GraphNodeRow).order_by(GraphNodeRow.node_id)
        if kinds is not None:
            statement = statement.where(GraphNodeRow.kind.in_([kind.value for kind in kinds]))
        with Session(self._engine) as session:
            rows = session.scalars(statement).all()
            return tuple(
                node
                for row in rows
                if (node := self._authoritative_graph_node(session, row)) is not None
            )

    def edges(
        self,
        *,
        node_id: str | None = None,
        direction: GraphDirection = GraphDirection.OUT,
        kinds: frozenset[GraphEdgeKind] | None = None,
    ) -> tuple[GraphEdge, ...]:
        statement = select(GraphEdgeRow).order_by(GraphEdgeRow.edge_id)
        if node_id is not None:
            if direction == GraphDirection.OUT:
                statement = statement.where(GraphEdgeRow.source_node_id == node_id)
            elif direction == GraphDirection.IN:
                statement = statement.where(GraphEdgeRow.target_node_id == node_id)
            else:
                statement = statement.where(
                    (GraphEdgeRow.source_node_id == node_id)
                    | (GraphEdgeRow.target_node_id == node_id)
                )
        if kinds is not None:
            statement = statement.where(GraphEdgeRow.kind.in_([kind.value for kind in kinds]))
        with Session(self._engine) as session:
            rows = session.scalars(statement).all()
            return tuple(
                edge
                for row in rows
                if (edge := self._authoritative_graph_edge(session, row)) is not None
            )

    def neighbors(
        self,
        node_id: str,
        *,
        direction: GraphDirection = GraphDirection.OUT,
        kinds: frozenset[GraphEdgeKind] | None = None,
    ) -> tuple[GraphNode, ...]:
        edge_rows = self.edges(node_id=node_id, direction=direction, kinds=kinds)
        neighbour_ids: set[str] = set()
        for edge in edge_rows:
            if edge.source_node_id == node_id:
                neighbour_ids.add(edge.target_node_id)
            if edge.target_node_id == node_id:
                neighbour_ids.add(edge.source_node_id)
        with Session(self._engine) as session:
            rows = session.scalars(
                select(GraphNodeRow)
                .where(GraphNodeRow.node_id.in_(sorted(neighbour_ids)))
                .order_by(GraphNodeRow.node_id)
            ).all()
            return tuple(
                node
                for row in rows
                if (node := self._authoritative_graph_node(session, row)) is not None
            )

    def lineage_cluster_for_source(self, source_id: SourceId) -> EvidenceLineageCluster | None:
        with Session(self._engine) as session:
            member = session.get(LineageClusterMemberRow, source_id)
            if member is None:
                return None
            row = session.get(LineageClusterRow, member.cluster_id)
        return EvidenceLineageCluster.model_validate_json(row.document_json) if row else None

    def lineage_clusters(self) -> tuple[EvidenceLineageCluster, ...]:
        with Session(self._engine) as session:
            rows = session.scalars(
                select(LineageClusterRow).order_by(LineageClusterRow.cluster_id)
            ).all()
        return tuple(EvidenceLineageCluster.model_validate_json(row.document_json) for row in rows)

    def close(self) -> None:
        self._engine.dispose()
