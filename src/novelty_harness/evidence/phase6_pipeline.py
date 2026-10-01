"""Phase 6 evidence-verification pipeline.

Flow: build MCU profiles and propositions; choose candidate source/MCU pairs
without assigning precedent; map exact passages; select support passages;
verify independently; expand same-source context only when insufficient; apply
chronology/quality eligibility; classify the local precedent relation; persist
propositions and verified graph edges; write phase6 artifacts and trace events.

No Phase 7 adjudication, prosecutor/defender reasoning or novelty verdict is
produced here.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from pydantic import ConfigDict, JsonValue, model_validator

from novelty_harness.domain.base import ContractModel, utc_now
from novelty_harness.domain.enums import AssessmentStage, PrecedentState, TraceStatus
from novelty_harness.domain.idea import ArtifactProvenance
from novelty_harness.domain.ids import (
    AssessmentId,
    MCUId,
    SourceId,
    SourceVersionId,
    new_trace_event_id,
)
from novelty_harness.domain.mcu import MCU, MCUCombination
from novelty_harness.evidence.context.expansion import DEFAULT_WINDOW_CHARS
from novelty_harness.evidence.context.selection import (
    PassageSelectionError,
    SupportEvidenceBundle,
    select_support_passages,
)
from novelty_harness.evidence.graph.assessment_ledger import (
    AUTHORITY_REJECTED_DESCRIPTOR_LIMITATION,
    Phase6AssessmentSnapshotRecord,
    Phase6CandidateLedgerRecord,
    Phase6CoverageExclusion,
    Phase6CoverageLedger,
    Phase6DerivedLedgerRecord,
    Phase6TargetLedgerRecord,
    phase6_assessment_snapshot_id,
    phase6_candidate_record_id,
    phase6_derived_record_id,
    phase6_target_record_id,
)
from novelty_harness.evidence.graph.models import GraphNode, GraphNodeKind
from novelty_harness.evidence.graph.phase6_mapping import (
    phase6_graph_provenance,
    verified_edge_graph_fragment,
)
from novelty_harness.evidence.graph.repository import (
    ContentAuthorityError,
    EvidenceGraphRepository,
    Phase6CommitReceipt,
)
from novelty_harness.evidence.graph.retrieval_mapping import (
    passage_graph_node,
    source_graph_node,
    version_graph_node,
)
from novelty_harness.evidence.mapping.dimensions import (
    MCUComparisonProfile,
    build_combination_comparison_profile,
    build_mcu_comparison_profile,
    build_proposition,
)
from novelty_harness.evidence.mapping.mapper import EvidenceMapperV2, MappingValidationError
from novelty_harness.evidence.mapping.models import EvidenceProposition, SourceMCUMapping
from novelty_harness.evidence.normalization.models import (
    SourceAccessState,
    SourceRecord,
    SourceVersionRecord,
)
from novelty_harness.evidence.passages.models import PassageRecord
from novelty_harness.evidence.pipeline import EvidenceNormalizationResult
from novelty_harness.evidence.precedent.gates import (
    ClassificationFacts,
    ClassifiedComparison,
    MultiSourceAssessment,
    classify_precedent,
    classify_verified_comparison,
    summarize_multi_source,
)
from novelty_harness.evidence.precedent.models import (
    PatentScreeningResult,
    PrecedentClassification,
)
from novelty_harness.evidence.precedent.patent import (
    PatentEvidenceEntry,
    patent_entry_from_comparison,
    patent_locator_from_passage,
    screen_patent_references,
)
from novelty_harness.evidence.provenance.independence import (
    independent_root_map,
    independent_roots_for_sources,
)
from novelty_harness.evidence.quality.models import EvidenceQualityAssessment
from novelty_harness.evidence.verification.gates import build_verified_evidence_edge
from novelty_harness.evidence.verification.integrity import (
    VerifiedComparison,
    VerifiedEvidenceChain,
    verified_comparison,
)
from novelty_harness.evidence.verification.models import (
    ContextExpansion,
    SupportVerification,
    VerifiedEvidenceEdge,
)
from novelty_harness.evidence.verification.verifier import (
    IndependentSupportVerifier,
    verify_with_context_retry,
)
from novelty_harness.runtime.artifacts.writer import RunArtifactWriter
from novelty_harness.runtime.semantic.structured import (
    SemanticOutputValidationError,
    SemanticRunner,
)
from novelty_harness.runtime.tracing.hashing import canonical_hash
from novelty_harness.runtime.tracing.models import TraceEvent
from novelty_harness.runtime.tracing.sinks import TraceSink

_PIPELINE_PROVENANCE = ArtifactProvenance(
    kind="implemented",
    component="phase6_pipeline",
    detail="Passage-grounded mapping, independent verification and local classification.",
)


class CandidateAssessmentResult(ContractModel):
    """One aligned local result, including explicit failures without a chain."""

    model_config = ConfigDict(frozen=True)
    assessment_id: AssessmentId
    source_id: SourceId
    source_version_id: SourceVersionId | None = None
    target_mcu_id: MCUId
    target_kind: Literal["MCU", "COMBINATION"]
    combination_id: str | None = None
    status: Literal[
        "ASSESSED",
        "FAILED_MAPPING",
        "FAILED_PASSAGE_SELECTION",
        "UNASSESSABLE",
        "AUTHORITY_REJECTED",
    ]
    chain: VerifiedComparison | None = None
    classification: PrecedentClassification
    failure: str | None = None
    failure_stage: str | None = None
    expansions: tuple[ContextExpansion, ...] = ()
    limitations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def aligned(self) -> "CandidateAssessmentResult":
        from novelty_harness.runtime.tracing.hashing import canonical_hash

        if (self.target_kind == "COMBINATION") != (self.combination_id is not None):
            raise ValueError("Candidate combination target identity is incomplete")
        if self.target_kind == "COMBINATION" and self.target_mcu_id != (
            "mcu_comb_" + canonical_hash(self.combination_id)[:24]
        ):
            raise ValueError("Candidate combination target identity differs")
        if (
            self.classification.source_id != self.source_id
            or self.classification.mcu_id != self.target_mcu_id
            or self.classification.source_version_id != self.source_version_id
        ):
            raise ValueError("Candidate classification belongs to another source/version/target")
        if self.status != "ASSESSED":
            if (
                self.chain is not None
                or self.failure is None
                or self.classification.relation != PrecedentState.UNASSESSABLE
            ):
                raise ValueError("Unassessable candidate requires a failure and no chain")
        elif self.chain is None or self.failure is not None:
            raise ValueError("Assessed candidate requires a chain and no failure")
        else:
            chain = VerifiedComparison.model_validate(self.chain.model_dump(mode="json"))
            if (
                chain.assessment_id != self.assessment_id
                or chain.source_id != self.source_id
                or (chain.chain.version.version_id if chain.chain.version is not None else None)
                != self.source_version_id
                or chain.mcu_id != self.target_mcu_id
            ):
                raise ValueError("Candidate chain belongs to another comparison")
            ClassifiedComparison(comparison=chain, classification=self.classification)
        return self


@dataclass(frozen=True, slots=True)
class Phase6EvidenceResult:
    profiles: tuple[MCUComparisonProfile, ...]
    propositions: tuple[EvidenceProposition, ...]
    mappings: tuple[SourceMCUMapping, ...]
    claims: tuple[SupportEvidenceBundle, ...]
    verifications: tuple[SupportVerification, ...]
    expansions: tuple[ContextExpansion, ...]
    edges: tuple[VerifiedEvidenceEdge, ...]
    chains: tuple[VerifiedEvidenceChain, ...]
    classifications: tuple[PrecedentClassification, ...]
    commit_receipts: tuple[Phase6CommitReceipt, ...]
    candidate_assessments: tuple[CandidateAssessmentResult, ...]
    multi_source: tuple[MultiSourceAssessment, ...]
    patent_screenings: tuple[PatentScreeningResult, ...]
    unassessed_sources: tuple[SourceId, ...]
    unassessed_versions: tuple[str, ...]
    coverage_limitations: tuple[str, ...]
    failures: tuple[str, ...]
    limitations: tuple[str, ...]
    graph_ref: str
    snapshot_id: str


def _profile_and_proposition(target: MCU) -> tuple[MCUComparisonProfile, EvidenceProposition]:
    profile = build_mcu_comparison_profile(target)
    return profile, build_proposition(profile)


def _combination_profile_and_proposition(
    combination: MCUCombination, members: Sequence[MCU]
) -> tuple[MCUComparisonProfile, EvidenceProposition]:
    profile = build_combination_comparison_profile(combination, members)
    return profile, build_proposition(profile)


@dataclass(frozen=True, slots=True)
class CandidateSelection:
    """Selected candidates plus the bounded remainder (F04)."""

    selected: tuple[SourceRecord, ...]
    unassessed_sources: tuple[SourceId, ...]


def select_candidate_sources(
    *,
    target_id: MCUId,
    member_ids: Sequence[MCUId],
    sources: Sequence[SourceRecord],
    passages_by_source: Mapping[SourceId, tuple[PassageRecord, ...]],
    max_sources: int,
) -> CandidateSelection:
    """Choose candidate sources by discovery routing only; no rank or quality.

    Sources beyond the bound are returned as explicitly unassessed so a local
    classification never implies exhaustive coverage (F04).
    """

    wanted = {target_id, *member_ids}
    eligible = [
        source
        for source in sources
        if source.access_state in {SourceAccessState.FULL_TEXT, SourceAccessState.ABSTRACT_ONLY}
        and passages_by_source.get(source.source_id)
    ]
    ordered = sorted(
        eligible,
        key=lambda source: (
            not any(path.mcu_id in wanted for path in source.discovery_paths),
            source.source_id,
        ),
    )
    return CandidateSelection(
        selected=tuple(ordered[:max_sources]),
        unassessed_sources=tuple(source.source_id for source in ordered[max_sources:]),
    )


def select_versions(
    versions: Sequence[SourceVersionRecord],
    passages: Sequence[PassageRecord],
    *,
    max_versions: int,
) -> tuple[tuple[SourceVersionRecord | None, ...], tuple[str, ...]]:
    """Documented multi-version policy: assess every version with passages up to a
    bound, oldest-first, and report the remainder as unassessed (F04)."""

    usable = [
        version
        for version in versions
        if any(passage.source_version_id == version.version_id for passage in passages)
    ]
    usable.sort(
        key=lambda version: (
            version.published_date is None,
            version.published_date or date.min,
            version.observed_at,
            version.version_id,
        )
    )
    unversioned = tuple(
        passage.passage_id for passage in passages if passage.source_version_id is None
    )
    slots: list[SourceVersionRecord | None] = [*usable]
    if unversioned and not versions:
        slots.append(None)
    selected = tuple(slots[:max_versions])
    excluded = tuple(
        version.version_id if version is not None else "unversioned:" + ",".join(unversioned)
        for version in slots[max_versions:]
    )
    if unversioned and versions:
        excluded += ("unversioned:" + ",".join(unversioned),)
    known_versions = {version.version_id for version in versions}
    excluded += tuple(
        "missing-version-record:" + identity
        for identity in sorted(
            {
                passage.source_version_id
                for passage in passages
                if passage.source_version_id is not None
                and passage.source_version_id not in known_versions
            }
        )
    )
    return selected, excluded


def _commit_candidate(
    *,
    repository: EvidenceGraphRepository,
    candidate: CandidateAssessmentResult,
    profile: MCUComparisonProfile,
    clock: Callable[[], datetime],
) -> Phase6CommitReceipt:
    """Persist one comparison and return its post-transaction authority receipt."""

    if candidate.chain is None:
        raise ValueError("Only an assessed candidate can be committed")
    chain = candidate.chain.chain
    classified = ClassifiedComparison(
        comparison=candidate.chain, classification=candidate.classification
    )
    observed_at = clock()
    fragment_nodes, fragment_edges = verified_edge_graph_fragment(
        (chain.edge,),
        (candidate.classification,),
        observed_at=observed_at,
        provenance=phase6_graph_provenance(),
    )
    candidates = (
        GraphNode(
            node_id=profile.target_id,
            kind=GraphNodeKind.MCU,
            label=profile.label,
            attributes={
                "statement": profile.statement,
                "target_kind": profile.target_kind,
                "combination_id": profile.combination_id,
            },
            observed_at=observed_at,
            provenance=_PIPELINE_PROVENANCE,
        ),
        source_graph_node(chain.source, observed_at=observed_at, provenance=_PIPELINE_PROVENANCE),
        *(
            (
                version_graph_node(
                    chain.version, observed_at=observed_at, provenance=_PIPELINE_PROVENANCE
                ),
            )
            if chain.version is not None
            else ()
        ),
        *(
            passage_graph_node(passage, observed_at=observed_at, provenance=_PIPELINE_PROVENANCE)
            for passage in (*chain.bundle.passages, *chain.context_passages)
        ),
        *fragment_nodes,
    )
    nodes: dict[str, GraphNode] = {}
    for node in candidates:
        if node.node_id not in nodes and repository.get_node(node.node_id) is None:
            nodes[node.node_id] = node
    receipt = repository.upsert(
        nodes=tuple(nodes.values()),
        edges=fragment_edges,
        verified_edges=(chain.edge,),
        verified_chains=(chain,),
        classified_comparisons=(classified,),
    )
    if (
        receipt is None
        or receipt.assessment_id != candidate.assessment_id
        or receipt.committed_edge_ids != (chain.edge.edge_id,)
        or receipt.committed_classification_ids != (candidate.classification.classification_id,)
    ):
        raise ValueError("Repository did not confirm the committed Phase 6 comparison")
    resolved = repository.resolve_phase6_commit(receipt)
    if (
        resolved.record.commit_id != receipt.commit_id
        or len(resolved.comparisons) != 1
        or resolved.comparisons[0].comparison.chain.edge.edge_id != chain.edge.edge_id
        or resolved.comparisons[0].classification.classification_id
        != candidate.classification.classification_id
    ):
        raise ValueError("Repository did not resolve the committed Phase 6 comparison")
    return receipt


class EvidenceVerificationPipeline:
    """Orchestrates the four separated Phase 6 semantic stages."""

    def __init__(
        self,
        runner: SemanticRunner,
        *,
        max_sources_per_mcu: int = 3,
        max_versions_per_source: int = 3,
        max_expansions: int = 2,
        window_chars: int = DEFAULT_WINDOW_CHARS,
    ) -> None:
        if max_sources_per_mcu < 1 or max_versions_per_source < 1:
            raise ValueError("Candidate source/version bounds must be positive")
        self.mapper = EvidenceMapperV2(runner)
        self.verifier = IndependentSupportVerifier(runner)
        self.max_sources_per_mcu = max_sources_per_mcu
        self.max_versions_per_source = max_versions_per_source
        self.max_expansions = max_expansions
        self.window_chars = window_chars

    async def _assess_candidate(
        self,
        *,
        assessment_id: AssessmentId,
        target_kind: Literal["MCU", "COMBINATION"],
        combination_id: str | None,
        proposition: EvidenceProposition,
        source: SourceRecord,
        version: SourceVersionRecord | None,
        source_passages: tuple[PassageRecord, ...],
        as_of: date,
        quality_by_source: Mapping[SourceId, EvidenceQualityAssessment],
        mappings: list[SourceMCUMapping],
        claims: list[SupportEvidenceBundle],
        verifications: list[SupportVerification],
        expansions: list[ContextExpansion],
        edges: list[VerifiedEvidenceEdge],
        chains: list[VerifiedEvidenceChain],
        classifications: list[PrecedentClassification],
        candidate_assessments: list[CandidateAssessmentResult],
        target_classifications: list[PrecedentClassification],
        failures: list[str],
        emit: Callable[..., None],
        clock: Callable[[], datetime],
    ) -> None:
        """Map, select, verify, gate and classify one source/version candidate."""

        try:
            mapping = await self.mapper.map_source_to_mcu(
                proposition=proposition,
                source=source,
                version=version,
                passages=source_passages,
                clock=clock,
            )
        except (SemanticOutputValidationError, MappingValidationError) as error:
            failure = (
                f"{source.source_id}->{proposition.mcu_id}: mapping failed: {type(error).__name__}"
            )
            failures.append(failure)
            emit("EVIDENCE_MAPPING_FAILED", {"detail": failure}, failure=True)
            unassessable = classify_precedent(
                ClassificationFacts(
                    proposition=proposition,
                    source_id=source.source_id,
                    source_version_id=version.version_id if version else None,
                    selection_failure="Mapping could not be validated",
                ),
                clock=clock,
            )
            classifications.append(unassessable)
            target_classifications.append(unassessable)
            candidate_assessments.append(
                CandidateAssessmentResult(
                    assessment_id=assessment_id,
                    source_id=source.source_id,
                    source_version_id=version.version_id if version else None,
                    target_mcu_id=proposition.mcu_id,
                    target_kind=target_kind,
                    combination_id=combination_id,
                    status="FAILED_MAPPING",
                    classification=unassessable,
                    failure=failure,
                    failure_stage="MAPPING",
                )
            )
            return
        mappings.append(mapping)
        emit(
            "EVIDENCE_MAPPING",
            {
                "mapping_id": mapping.mapping_id,
                "source_id": source.source_id,
                "mcu_id": proposition.mcu_id,
                "dimension_count": len(mapping.dimensions),
            },
        )
        try:
            bundle = select_support_passages(
                mapping=mapping,
                proposition=proposition,
                source=source,
                version=version,
                passages=source_passages,
                clock=clock,
            )
        except PassageSelectionError as error:
            failure = f"{source.source_id}->{proposition.mcu_id}: {error}"
            failures.append(failure)
            unassessable = classify_precedent(
                ClassificationFacts(
                    proposition=proposition,
                    source_id=source.source_id,
                    source_version_id=version.version_id if version else None,
                    mapping=mapping,
                    selection_failure=str(error),
                ),
                clock=clock,
            )
            classifications.append(unassessable)
            target_classifications.append(unassessable)
            candidate_assessments.append(
                CandidateAssessmentResult(
                    assessment_id=assessment_id,
                    source_id=source.source_id,
                    source_version_id=version.version_id if version else None,
                    target_mcu_id=proposition.mcu_id,
                    target_kind=target_kind,
                    combination_id=combination_id,
                    status="FAILED_PASSAGE_SELECTION",
                    classification=unassessable,
                    failure=failure,
                    failure_stage="PASSAGE_SELECTION",
                )
            )
            return
        retry = await verify_with_context_retry(
            self.verifier,
            bundle,
            available_passages=source_passages,
            max_expansions=self.max_expansions,
            window_chars=self.window_chars,
            clock=clock,
        )
        claims.append(retry.verified_bundle)
        verifications.append(retry.verification)
        expansions.extend(retry.expansions)
        for expansion in retry.expansions:
            emit(
                "CONTEXT_EXPANSION",
                {
                    "origin_passage_id": expansion.origin_passage_id,
                    "available": expansion.available,
                    "attempt": expansion.attempt,
                },
                failure=not expansion.available,
                stage=AssessmentStage.EVIDENCE_VERIFIED,
            )
        emit(
            "SUPPORT_VERIFICATION",
            {
                "verification_id": retry.verification.verification_id,
                "source_id": source.source_id,
                "mcu_id": proposition.mcu_id,
                "state": retry.verification.state.value,
            },
            stage=AssessmentStage.EVIDENCE_VERIFIED,
        )
        edge = build_verified_evidence_edge(
            mapping=mapping,
            verification=retry.verification,
            proposition=proposition,
            source=source,
            bundle=retry.verified_bundle,
            as_of=as_of,
            observed_at=clock(),
            assessment_id=assessment_id,
            version=version,
            context_passages=tuple(
                item.window_passage for item in retry.expansions if item.window_passage is not None
            ),
            quality=quality_by_source.get(source.source_id),
        )
        context_passages = tuple(
            item.window_passage for item in retry.expansions if item.window_passage is not None
        )
        preliminary_chain = VerifiedEvidenceChain(
            assessment_id=assessment_id,
            source=source,
            version=version,
            proposition=proposition,
            mapping=mapping,
            bundle=retry.verified_bundle,
            verification=retry.verification,
            context_passages=context_passages,
            edge=edge,
        )
        provisional_classification = classify_verified_comparison(
            verified_comparison(preliminary_chain),
            clock=clock,
        )
        if provisional_classification.relation != PrecedentState.UNASSESSABLE:
            edge = build_verified_evidence_edge(
                mapping=mapping,
                verification=retry.verification,
                proposition=proposition,
                source=source,
                bundle=retry.verified_bundle,
                as_of=as_of,
                observed_at=clock(),
                assessment_id=assessment_id,
                version=version,
                context_passages=tuple(
                    item.window_passage
                    for item in retry.expansions
                    if item.window_passage is not None
                ),
                quality=quality_by_source.get(source.source_id),
                relation=provisional_classification.relation,
            )
        edges.append(edge)
        final_chain = VerifiedEvidenceChain(
            assessment_id=assessment_id,
            source=source,
            version=version,
            proposition=proposition,
            mapping=mapping,
            bundle=retry.verified_bundle,
            verification=retry.verification,
            context_passages=context_passages,
            edge=edge,
        )
        classification = classify_verified_comparison(verified_comparison(final_chain), clock=clock)
        chains.append(final_chain)
        ClassifiedComparison(
            comparison=verified_comparison(final_chain),
            classification=classification,
        )
        classifications.append(classification)
        target_classifications.append(classification)
        candidate_assessments.append(
            CandidateAssessmentResult(
                assessment_id=assessment_id,
                source_id=source.source_id,
                source_version_id=version.version_id if version else None,
                target_mcu_id=proposition.mcu_id,
                target_kind=target_kind,
                combination_id=combination_id,
                status="ASSESSED",
                chain=verified_comparison(final_chain),
                classification=classification,
                expansions=retry.expansions,
                limitations=tuple(
                    "Context expansion was unavailable for passage " + item.origin_passage_id
                    for item in retry.expansions
                    if not item.available
                ),
            )
        )
        emit(
            "PRECEDENT_CLASSIFICATION",
            {
                "classification_id": classification.classification_id,
                "source_id": source.source_id,
                "mcu_id": proposition.mcu_id,
                "relation": classification.relation.value,
                "local_only": True,
            },
        )

    async def run(
        self,
        *,
        assessment_id: AssessmentId,
        evidence: EvidenceNormalizationResult,
        mcus: Sequence[MCU],
        combinations: Sequence[MCUCombination],
        as_of: date,
        repository: EvidenceGraphRepository,
        writer: RunArtifactWriter,
        trace_sink: TraceSink,
        graph_ref: str,
        clock: Callable[[], datetime] = utc_now,
    ) -> Phase6EvidenceResult:
        sources = evidence.sources
        persisted_lineage_by_id = {
            cluster.cluster_id: cluster for cluster in repository.lineage_clusters()
        }
        phase5_lineage_clusters = tuple(
            cluster
            for cluster in evidence.lineage_clusters
            if persisted_lineage_by_id.get(cluster.cluster_id) == cluster
        )
        passages_by_source: dict[SourceId, tuple[PassageRecord, ...]] = {}
        for passage in evidence.passages:
            passages_by_source.setdefault(passage.source_id, ())
            passages_by_source[passage.source_id] = (
                *passages_by_source[passage.source_id],
                passage,
            )
        versions_by_source: dict[SourceId, tuple[SourceVersionRecord, ...]] = {}
        for version in evidence.versions:
            versions_by_source.setdefault(version.source_id, ())
            versions_by_source[version.source_id] = (
                *versions_by_source[version.source_id],
                version,
            )
        quality_by_source = {
            assessment.source_id: assessment for assessment in evidence.quality_assessments
        }
        independent_root_of = {
            source_id: root_id
            for source_id, root_id in independent_root_map(phase5_lineage_clusters).items()
            if root_id is not None
        }

        def lineage_facts(
            source_ids: Sequence[SourceId],
        ) -> tuple[tuple[SourceId, ...], tuple[str, ...]]:
            return independent_roots_for_sources(source_ids, phase5_lineage_clusters)

        pending_success: list[tuple[str, dict[str, JsonValue], AssessmentStage]] = []
        post_commit_trace_refs: list[str] = []
        pending_derived_publications: list[
            tuple[str, dict[str, JsonValue], tuple[Phase6CommitReceipt, ...]]
        ] = []
        derived_records: list[Phase6DerivedLedgerRecord] = []
        coverage_limitations: list[str] = []

        def publish(
            reason: str,
            data: dict[str, JsonValue],
            *,
            failure: bool = False,
            stage: AssessmentStage = AssessmentStage.EVIDENCE_MAPPED,
            receipts: Sequence[Phase6CommitReceipt] = (),
        ) -> str:
            if not failure and not receipts:
                raise ValueError("Authoritative semantic success requires a commit receipt")
            if any(item.assessment_id != assessment_id for item in receipts):
                raise ValueError("Commit receipt belongs to another assessment")
            committed: dict[str, JsonValue] = (
                {
                    "committed_edge_ids": [
                        identity for item in receipts for identity in item.committed_edge_ids
                    ],
                    "committed_classification_ids": [
                        identity
                        for item in receipts
                        for identity in item.committed_classification_ids
                    ],
                }
                if receipts
                else {}
            )
            event_data = {
                "execution": "implemented",
                "semantics_implemented": True,
                **data,
                **committed,
                "publication_kind": (
                    "OPERATIONAL_DIAGNOSTIC" if failure else "POST_COMMIT_AUTHORITY"
                ),
            }
            event = TraceEvent(
                event_id=(
                    "trace_"
                    + canonical_hash(
                        {"assessment_id": assessment_id, "reason": reason, "data": event_data}
                    )
                    if receipts
                    else new_trace_event_id()
                ),
                assessment_id=assessment_id,
                occurred_at=clock(),
                stage=stage,
                component="phase6_evidence",
                status=TraceStatus.FAILURE if failure else TraceStatus.SUCCESS,
                reason_code=reason,
                data=event_data,
            )
            trace_sink.emit(event)
            return event.event_id

        def emit(
            reason: str,
            data: dict[str, JsonValue],
            *,
            failure: bool = False,
            stage: AssessmentStage = AssessmentStage.EVIDENCE_MAPPED,
        ) -> None:
            if reason == "SUPPORT_VERIFICATION" and failure:
                raise ValueError("A verifier conclusion is semantic, not an operational failure")
            if failure:
                publish(reason, data, failure=True, stage=stage)
            else:
                pending_success.append((reason, data, stage))

        def publish_pending(receipt: Phase6CommitReceipt) -> None:
            queued = tuple(pending_success)
            pending_success.clear()
            for reason, data, stage in queued:
                post_commit_trace_refs.append(
                    publish(reason, data, stage=stage, receipts=(receipt,))
                )

        targets: list[tuple[MCUComparisonProfile, EvidenceProposition, tuple[MCUId, ...]]] = []
        for mcu in sorted(mcus, key=lambda item: item.mcu_id):
            profile, proposition = _profile_and_proposition(mcu)
            targets.append((profile, proposition, (mcu.mcu_id,)))
        members_by_id = {mcu.mcu_id: mcu for mcu in mcus}
        for combination in sorted(combinations, key=lambda item: item.combination_id):
            members = tuple(members_by_id[identity] for identity in combination.member_ids)
            profile, proposition = _combination_profile_and_proposition(combination, members)
            targets.append((profile, proposition, combination.member_ids))

        profiles: list[MCUComparisonProfile] = []
        propositions: list[EvidenceProposition] = []
        mappings: list[SourceMCUMapping] = []
        claims: list[SupportEvidenceBundle] = []
        verifications: list[SupportVerification] = []
        expansions: list[ContextExpansion] = []
        edges: list[VerifiedEvidenceEdge] = []
        chains: list[VerifiedEvidenceChain] = []
        classifications: list[PrecedentClassification] = []
        candidate_assessments: list[CandidateAssessmentResult] = []
        multi_source_summaries: list[MultiSourceAssessment] = []
        unassessed_sources: list[SourceId] = []
        unassessed_versions: list[str] = []
        selected_source_ids: list[SourceId] = []
        selected_version_ids: list[str] = []
        source_exclusions: list[Phase6CoverageExclusion] = []
        version_exclusions: list[Phase6CoverageExclusion] = []
        candidate_descriptors: dict[
            tuple[MCUId, SourceId, str | None],
            tuple[SourceRecord, SourceVersionRecord | None, int],
        ] = {}
        excluded_candidate_facts: list[
            tuple[
                MCUId,
                SourceRecord,
                SourceVersionRecord | None,
                int,
                Literal["EXCLUDED_SOURCE_BOUND", "EXCLUDED_VERSION_BOUND"],
                Literal["SOURCE_BOUND", "VERSION_BOUND", "UNVERSIONED", "MISSING_VERSION_RECORD"],
            ]
        ] = []
        eligible_selection_count = 0
        failures: list[str] = []
        committed_comparisons: list[ClassifiedComparison] = []
        committed_receipts: list[Phase6CommitReceipt] = []
        receipt_by_edge: dict[str, Phase6CommitReceipt] = {}

        for profile, proposition, member_ids in targets:
            profiles.append(profile)
            propositions.append(proposition)
            selection = select_candidate_sources(
                target_id=profile.target_id,
                member_ids=member_ids,
                sources=sources,
                passages_by_source=passages_by_source,
                max_sources=self.max_sources_per_mcu,
            )
            eligible_selection_count += len(selection.selected) + len(selection.unassessed_sources)
            unassessed_sources.extend(selection.unassessed_sources)
            selected_source_ids.extend(item.source_id for item in selection.selected)
            for source_id in selection.unassessed_sources:
                source = next(item for item in sources if item.source_id == source_id)
                priority = int(
                    not any(
                        path.mcu_id in {profile.target_id, *member_ids}
                        for path in source.discovery_paths
                    )
                )
                source_exclusions.append(
                    Phase6CoverageExclusion(
                        source_id=source.source_id,
                        target_id=profile.target_id,
                        reason="SOURCE_BOUND",
                        source_content_hash=source.content_hash,
                        source_access_state=source.access_state,
                        evidence_families=tuple(
                            sorted(item.value for item in source.evidence_families)
                        ),
                        routing_priority=priority,
                    )
                )
                source_versions = versions_by_source.get(source.source_id, ())
                version_ids = {item.version_id for item in source_versions}
                for version in source_versions:
                    version_exclusions.append(
                        Phase6CoverageExclusion(
                            source_id=source.source_id,
                            target_id=profile.target_id,
                            source_version_id=version.version_id,
                            reason="SOURCE_BOUND",
                            source_content_hash=source.content_hash,
                            source_access_state=source.access_state,
                            version_content_hash=version.content_hash,
                            version_access_state=version.access_state,
                            evidence_families=tuple(
                                sorted(item.value for item in source.evidence_families)
                            ),
                            routing_priority=priority,
                        )
                    )
                    excluded_candidate_facts.append(
                        (
                            profile.target_id,
                            source,
                            version,
                            priority,
                            "EXCLUDED_SOURCE_BOUND",
                            "SOURCE_BOUND",
                        )
                    )
                source_passages = passages_by_source.get(source.source_id, ())
                if any(passage.source_version_id is None for passage in source_passages):
                    version_exclusions.append(
                        Phase6CoverageExclusion(
                            source_id=source.source_id,
                            target_id=profile.target_id,
                            reason="UNVERSIONED",
                            source_content_hash=source.content_hash,
                            source_access_state=source.access_state,
                            evidence_families=tuple(
                                sorted(item.value for item in source.evidence_families)
                            ),
                            routing_priority=priority,
                        )
                    )
                    excluded_candidate_facts.append(
                        (
                            profile.target_id,
                            source,
                            None,
                            priority,
                            "EXCLUDED_SOURCE_BOUND",
                            "UNVERSIONED",
                        )
                    )
                missing_version_ids = sorted(
                    {
                        passage.source_version_id
                        for passage in source_passages
                        if passage.source_version_id is not None
                        and passage.source_version_id not in version_ids
                    }
                )
                for source_version_id in missing_version_ids:
                    version_exclusions.append(
                        Phase6CoverageExclusion(
                            source_id=source.source_id,
                            target_id=profile.target_id,
                            source_version_id=source_version_id,
                            reason="MISSING_VERSION_RECORD",
                            source_content_hash=source.content_hash,
                            source_access_state=source.access_state,
                            evidence_families=tuple(
                                sorted(item.value for item in source.evidence_families)
                            ),
                            routing_priority=priority,
                        )
                    )
            target_classifications: list[PrecedentClassification] = []
            for source in selection.selected:
                all_passages = passages_by_source[source.source_id]
                routing_priority = int(
                    not any(
                        path.mcu_id in {profile.target_id, *member_ids}
                        for path in source.discovery_paths
                    )
                )
                version_slots, excluded_versions = select_versions(
                    versions_by_source.get(source.source_id, ()),
                    all_passages,
                    max_versions=self.max_versions_per_source,
                )
                unassessed_versions.extend(
                    f"{source.source_id}:{version_id}" for version_id in excluded_versions
                )
                known_versions = {
                    item.version_id: item for item in versions_by_source.get(source.source_id, ())
                }
                for exclusion in excluded_versions:
                    if exclusion.startswith("unversioned:"):
                        version = None
                        source_version_id = None
                        reason = "UNVERSIONED"
                    elif exclusion.startswith("missing-version-record:"):
                        source_version_id = exclusion.removeprefix("missing-version-record:")
                        version = None
                        reason = "MISSING_VERSION_RECORD"
                    else:
                        source_version_id = exclusion
                        version = known_versions.get(exclusion)
                        reason = "VERSION_BOUND"
                    version_exclusions.append(
                        Phase6CoverageExclusion(
                            source_id=source.source_id,
                            target_id=profile.target_id,
                            source_version_id=source_version_id,
                            reason=reason,
                            source_content_hash=source.content_hash,
                            source_access_state=source.access_state,
                            version_content_hash=version.content_hash
                            if version is not None
                            else None,
                            version_access_state=version.access_state
                            if version is not None
                            else None,
                            evidence_families=tuple(
                                sorted(item.value for item in source.evidence_families)
                            ),
                            routing_priority=routing_priority,
                        )
                    )
                    if reason != "MISSING_VERSION_RECORD":
                        excluded_candidate_facts.append(
                            (
                                profile.target_id,
                                source,
                                version,
                                routing_priority,
                                "EXCLUDED_VERSION_BOUND",
                                reason,
                            )
                        )
                for version in version_slots:
                    source_passages = tuple(
                        passage
                        for passage in all_passages
                        if passage.source_version_id
                        == (version.version_id if version is not None else None)
                    )
                    if not source_passages:
                        continue
                    if version is not None:
                        selected_version_ids.append(version.version_id)
                    candidate_descriptors[
                        (
                            profile.target_id,
                            source.source_id,
                            version.version_id if version is not None else None,
                        )
                    ] = (source, version, routing_priority)
                    start = (
                        len(mappings),
                        len(claims),
                        len(verifications),
                        len(expansions),
                        len(edges),
                        len(chains),
                        len(classifications),
                        len(candidate_assessments),
                        len(target_classifications),
                    )
                    await self._assess_candidate(
                        assessment_id=assessment_id,
                        target_kind=profile.target_kind,
                        combination_id=profile.combination_id,
                        proposition=proposition,
                        source=source,
                        version=version,
                        source_passages=source_passages,
                        as_of=as_of,
                        quality_by_source=quality_by_source,
                        mappings=mappings,
                        claims=claims,
                        verifications=verifications,
                        expansions=expansions,
                        edges=edges,
                        chains=chains,
                        classifications=classifications,
                        candidate_assessments=candidate_assessments,
                        target_classifications=target_classifications,
                        failures=failures,
                        emit=emit,
                        clock=clock,
                    )
                    candidate = candidate_assessments[-1]
                    if candidate.chain is None:
                        pending_success.clear()
                        continue
                    try:
                        receipt = _commit_candidate(
                            repository=repository,
                            candidate=candidate,
                            profile=profile,
                            clock=clock,
                        )
                    except ContentAuthorityError as error:
                        for items, offset in zip(
                            (
                                mappings,
                                claims,
                                verifications,
                                expansions,
                                edges,
                                chains,
                                classifications,
                                candidate_assessments,
                                target_classifications,
                            ),
                            start,
                            strict=True,
                        ):
                            del items[offset:]
                        pending_success.clear()
                        failure = (
                            f"{source.source_id}->{profile.target_id}: "
                            f"content authority rejected: {error}"
                        )
                        failures.append(failure)
                        unassessable = classify_precedent(
                            ClassificationFacts(
                                proposition=proposition,
                                source_id=source.source_id,
                                source_version_id=version.version_id if version else None,
                                selection_failure="Stored content authority rejected comparison",
                            ),
                            clock=clock,
                        )
                        classifications.append(unassessable)
                        target_classifications.append(unassessable)
                        candidate_assessments.append(
                            CandidateAssessmentResult(
                                assessment_id=assessment_id,
                                source_id=source.source_id,
                                source_version_id=version.version_id if version else None,
                                target_mcu_id=profile.target_id,
                                target_kind=profile.target_kind,
                                combination_id=profile.combination_id,
                                status="AUTHORITY_REJECTED",
                                classification=unassessable,
                                failure=failure,
                                failure_stage="CONTENT_AUTHORITY",
                            )
                        )
                        publish(
                            "CONTENT_AUTHORITY_REJECTED",
                            {
                                "source_id": source.source_id,
                                "source_version_id": version.version_id if version else None,
                                "mcu_id": profile.target_id,
                                "detail": str(error),
                            },
                            failure=True,
                        )
                        continue
                    committed_receipts.append(receipt)
                    receipt_by_edge[candidate.chain.chain.edge.edge_id] = receipt
                    committed_comparisons.append(
                        ClassifiedComparison(
                            comparison=candidate.chain,
                            classification=candidate.classification,
                        )
                    )
                    publish_pending(receipt)
            target_comparisons = tuple(
                item
                for item in committed_comparisons
                if item.comparison.mcu_id == profile.target_id
            )
            if not target_comparisons:
                continue
            summary_source_ids = tuple(
                item.comparison.chain.source.source_id for item in target_comparisons
            )
            summary_roots, summary_lineage_limitations = lineage_facts(summary_source_ids)
            if summary_lineage_limitations:
                coverage_limitations.extend(summary_lineage_limitations)
                continue
            summary = summarize_multi_source(
                target_comparisons,
                mcu_id=profile.target_id,
                independent_root_of=independent_root_of,
                assessment_id=assessment_id,
                target_kind=profile.target_kind,
                combination_id=profile.combination_id,
            )
            multi_source_summaries.append(summary)
            summary_receipts = tuple(
                receipt_by_edge[item.comparison.chain.edge.edge_id] for item in target_comparisons
            )
            summary_inputs = tuple(
                (item, receipt_by_edge[item.comparison.chain.edge.edge_id])
                for item in target_comparisons
            )
            derived_records.append(
                Phase6DerivedLedgerRecord(
                    snapshot_id="pending",
                    assessment_id=assessment_id,
                    target_id=profile.target_id,
                    kind="MULTI_SOURCE",
                    input_commit_ids=tuple(
                        receipt.commit_id for _, receipt in summary_inputs if receipt.commit_id
                    ),
                    input_edge_ids=tuple(
                        item.comparison.chain.edge.edge_id for item, _ in summary_inputs
                    ),
                    input_classification_ids=tuple(
                        item.classification.classification_id for item, _ in summary_inputs
                    ),
                    lineage_root_ids=summary_roots,
                    as_of=as_of,
                    method_version="phase6-v1",
                    result=summary,
                    lineage_limitations=summary_lineage_limitations,
                )
            )
            pending_derived_publications.append(
                (
                    "MULTI_SOURCE_ASSESSMENT",
                    {
                        "mcu_id": profile.target_id,
                        "combination_context": summary.combination_context,
                        "single_source_direct_eligible": summary.single_source_direct_eligible,
                    },
                    summary_receipts,
                )
            )

        patent_screenings: list[PatentScreeningResult] = []
        classified_by_edge = {
            item.comparison.chain.edge.edge_id: item for item in committed_comparisons
        }
        for profile, proposition, _ in targets:
            entries: list[PatentEvidenceEntry] = []
            for edge in edges:
                if edge.mcu_id != profile.target_id:
                    continue
                source = next((item for item in sources if item.source_id == edge.source_id), None)
                if source is None:
                    continue
                classified = classified_by_edge.get(edge.edge_id)
                if classified is None:
                    continue
                all_cited_passages = (
                    *classified.comparison.chain.bundle.passages,
                    *classified.comparison.chain.context_passages,
                )
                locators = tuple(
                    patent_locator_from_passage(edge.source_id, passage_id, passage.locator)
                    for passage_id in edge.passage_ids
                    for passage in all_cited_passages
                    if passage.passage_id == passage_id
                )
                entries.append(patent_entry_from_comparison(classified, locators=locators))
            if entries:
                screening = screen_patent_references(
                    mcu_id=profile.target_id,
                    entries=tuple(entries),
                    as_of=as_of,
                    observed_at=clock(),
                    independent_root_of=independent_root_of,
                )
                patent_comparisons = tuple(
                    item.comparison for item in entries if item.comparison is not None
                )
                patent_receipts = tuple(
                    receipt_by_edge[item.comparison.chain.edge.edge_id]
                    for item in patent_comparisons
                )
                patent_inputs = tuple(
                    (item, receipt_by_edge[item.comparison.chain.edge.edge_id])
                    for item in patent_comparisons
                )
                patent_roots, patent_lineage_limitations = lineage_facts(
                    tuple(item.comparison.chain.source.source_id for item, _ in patent_inputs)
                )
                if (
                    patent_lineage_limitations
                    and screening.mode == "MULTI_REFERENCE_COMBINATION_LIKE"
                ):
                    coverage_limitations.extend(patent_lineage_limitations)
                    continue
                patent_screenings.append(screening)
                derived_records.append(
                    Phase6DerivedLedgerRecord(
                        snapshot_id="pending",
                        assessment_id=assessment_id,
                        target_id=profile.target_id,
                        kind="PATENT",
                        input_commit_ids=tuple(
                            receipt.commit_id for _, receipt in patent_inputs if receipt.commit_id
                        ),
                        input_edge_ids=tuple(
                            item.comparison.chain.edge.edge_id for item, _ in patent_inputs
                        ),
                        input_classification_ids=tuple(
                            item.classification.classification_id for item, _ in patent_inputs
                        ),
                        lineage_root_ids=patent_roots,
                        as_of=as_of,
                        method_version="phase6-v1",
                        result=screening,
                        lineage_limitations=patent_lineage_limitations,
                    )
                )
                pending_derived_publications.append(
                    (
                        "PATENT_SCREENING",
                        {
                            "screening_id": screening.screening_id,
                            "mcu_id": profile.target_id,
                            "mode": screening.mode,
                        },
                        patent_receipts,
                    )
                )
        if committed_receipts:
            graph_edge_count = sum(
                len(
                    verified_edge_graph_fragment(
                        (item.comparison.chain.edge,),
                        (item.classification,),
                        observed_at=clock(),
                        provenance=phase6_graph_provenance(),
                    )[1]
                )
                for item in committed_comparisons
            )
            post_commit_trace_refs.append(
                publish(
                    "PHASE6_GRAPH_PERSISTED",
                    {
                        "graph_ref": graph_ref,
                        "edge_count": graph_edge_count,
                        "proposition_count": len(edges),
                    },
                    receipts=tuple(committed_receipts),
                )
            )

        unavailable_expansion_count = sum(
            not expansion.available
            for candidate in candidate_assessments
            for expansion in candidate.expansions
        )
        if unavailable_expansion_count:
            coverage_limitations.append(
                f"{unavailable_expansion_count} requested context expansion(s) were unavailable; "
                "the affected source passages remain context limited"
            )
        if unassessed_sources:
            coverage_limitations.append(
                f"{len(unassessed_sources)} candidate source(s) were outside the "
                "bounded local coverage and remain unassessed"
            )
        if unassessed_versions:
            coverage_limitations.append(
                f"{len(unassessed_versions)} source version(s) were outside the "
                "bounded local coverage and remain unassessed"
            )
        if eligible_selection_count == 0:
            coverage_limitations.append(
                "No eligible source candidate with accessible passages was selected in this "
                "bounded local run; this ledger does not establish search completeness or absence."
            )
        limitations: list[str] = [
            "Mapping and verification are local source/MCU comparisons; "
            "no global absence or novelty claim is produced",
            "Local classifications cover only the assessed sources/versions; "
            "unassessed coverage is recorded explicitly",
            "Relevance/quality did not enter the blinded verifier input",
        ]
        limitations.extend(coverage_limitations)
        if not edges:
            limitations.append("No source could be mapped to any MCU target locally")
        target_records = tuple(
            Phase6TargetLedgerRecord(
                snapshot_id="pending",
                assessment_id=assessment_id,
                profile=profile,
            )
            for profile in profiles
        )
        outcome_by_key = {
            (
                candidate.target_mcu_id,
                candidate.source_id,
                candidate.source_version_id,
            ): candidate
            for candidate in candidate_assessments
        }
        candidate_records: list[Phase6CandidateLedgerRecord] = []
        for key, (source, version, routing_priority) in candidate_descriptors.items():
            outcome = outcome_by_key.get(key)
            if outcome is None:
                continue
            if outcome.chain is None:
                audit_limitations = outcome.limitations
                if (
                    outcome.status == "AUTHORITY_REJECTED"
                    and outcome.failure_stage == "CONTENT_AUTHORITY"
                ):
                    audit_limitations = (
                        *audit_limitations,
                        AUTHORITY_REJECTED_DESCRIPTOR_LIMITATION,
                    )
                candidate_records.append(
                    Phase6CandidateLedgerRecord(
                        snapshot_id="pending",
                        assessment_id=assessment_id,
                        target_id=key[0],
                        source_id=source.source_id,
                        source_version_id=version.version_id if version is not None else None,
                        source_content_hash=source.content_hash,
                        version_content_hash=version.content_hash if version is not None else None,
                        source_access_state=source.access_state,
                        version_access_state=version.access_state if version is not None else None,
                        evidence_families=tuple(
                            sorted(item.value for item in source.evidence_families)
                        ),
                        routing_priority=routing_priority,
                        decision=outcome.status,
                        reason=outcome.failure,
                        failure_stage=outcome.failure_stage,
                        expansions=outcome.expansions,
                        limitations=audit_limitations,
                    )
                )
                continue
            verified_edge = outcome.chain.chain.edge
            receipt = receipt_by_edge[verified_edge.edge_id]
            if receipt.commit_id is None:
                raise ValueError("Repository returned a Phase 6 receipt without a commit ID")
            candidate_records.append(
                Phase6CandidateLedgerRecord(
                    snapshot_id="pending",
                    assessment_id=assessment_id,
                    target_id=key[0],
                    source_id=source.source_id,
                    source_version_id=version.version_id if version is not None else None,
                    source_content_hash=source.content_hash,
                    version_content_hash=version.content_hash if version is not None else None,
                    source_access_state=source.access_state,
                    version_access_state=version.access_state if version is not None else None,
                    evidence_families=tuple(
                        sorted(item.value for item in source.evidence_families)
                    ),
                    routing_priority=routing_priority,
                    decision="ASSESSED",
                    projection_intent="GRAPH_BACKED",
                    commit_id=receipt.commit_id,
                    verified_edge_id=verified_edge.edge_id,
                    classification_id=outcome.classification.classification_id,
                    expansions=outcome.expansions,
                    limitations=outcome.limitations,
                )
            )
        for target_id, source, version, priority, decision, reason in excluded_candidate_facts:
            candidate_records.append(
                Phase6CandidateLedgerRecord(
                    snapshot_id="pending",
                    assessment_id=assessment_id,
                    target_id=target_id,
                    source_id=source.source_id,
                    source_version_id=version.version_id if version is not None else None,
                    source_content_hash=source.content_hash,
                    version_content_hash=version.content_hash if version is not None else None,
                    source_access_state=source.access_state,
                    version_access_state=version.access_state if version is not None else None,
                    evidence_families=tuple(
                        sorted(item.value for item in source.evidence_families)
                    ),
                    routing_priority=priority,
                    decision=decision,
                    reason=reason,
                )
            )
        coverage = Phase6CoverageLedger(
            selected_source_ids=tuple(dict.fromkeys(selected_source_ids)),
            excluded_sources=tuple(source_exclusions),
            selected_version_ids=tuple(dict.fromkeys(selected_version_ids)),
            excluded_versions=tuple(version_exclusions),
            limitations=tuple(coverage_limitations),
        )
        # Ledger rows carry source/version foreign keys. Ensure those descriptive
        # nodes exist even for bounded-out candidates; node storage alone does not
        # create a semantic commit or graph relation. Existing nodes are left intact
        # so repository content-authority checks remain in force for later commits.
        ledger_sources: dict[SourceId, SourceRecord] = {}
        ledger_versions: dict[str, SourceVersionRecord] = {}
        for _, (source, version, _) in candidate_descriptors.items():
            ledger_sources[source.source_id] = source
            if version is not None:
                ledger_versions[version.version_id] = version
        for _, source, version, _, _, _ in excluded_candidate_facts:
            ledger_sources[source.source_id] = source
            if version is not None:
                ledger_versions[version.version_id] = version
        descriptive_nodes = [
            source_graph_node(source, observed_at=clock(), provenance=_PIPELINE_PROVENANCE)
            for source in ledger_sources.values()
            if repository.get_node(source.source_id) is None
        ]
        descriptive_nodes.extend(
            version_graph_node(version, observed_at=clock(), provenance=_PIPELINE_PROVENANCE)
            for version in ledger_versions.values()
            if repository.get_node(version.version_id) is None
        )
        if descriptive_nodes:
            repository.upsert(nodes=tuple(descriptive_nodes))
        lineage_cluster_ids = tuple(cluster.cluster_id for cluster in phase5_lineage_clusters)
        missing_lineage_count = len(evidence.lineage_clusters) - len(lineage_cluster_ids)
        if missing_lineage_count:
            coverage_limitations.append(
                f"{missing_lineage_count} input lineage cluster(s) were not present in the "
                "repository snapshot and are not represented as repository lineage authority"
            )
            coverage = coverage.model_copy(update={"limitations": tuple(coverage_limitations)})
        commit_ids = tuple(
            receipt.commit_id for receipt in committed_receipts if receipt.commit_id is not None
        )
        snapshot = Phase6AssessmentSnapshotRecord(
            snapshot_id="pending",
            assessment_id=assessment_id,
            as_of=as_of,
            method_version="phase6-v1",
            max_sources_per_mcu=self.max_sources_per_mcu,
            max_versions_per_source=self.max_versions_per_source,
            max_expansions=self.max_expansions,
            window_chars=self.window_chars,
            target_record_ids=(),
            candidate_record_ids=(),
            derived_record_ids=(),
            lineage_cluster_ids=lineage_cluster_ids,
            commit_ids=commit_ids,
            coverage=coverage,
            audit_refs=tuple(dict.fromkeys(post_commit_trace_refs)),
            completed_at=clock(),
        )
        candidate_record_tuple = tuple(candidate_records)
        derived_record_tuple = tuple(derived_records)
        snapshot_id = phase6_assessment_snapshot_id(
            snapshot,
            targets=target_records,
            candidates=candidate_record_tuple,
            derived=derived_record_tuple,
        )
        target_records = tuple(
            item.model_copy(update={"snapshot_id": snapshot_id}) for item in target_records
        )
        candidate_record_tuple = tuple(
            item.model_copy(update={"snapshot_id": snapshot_id}) for item in candidate_record_tuple
        )
        derived_record_tuple = tuple(
            item.model_copy(update={"snapshot_id": snapshot_id}) for item in derived_record_tuple
        )
        snapshot = snapshot.model_copy(
            update={
                "snapshot_id": snapshot_id,
                "target_record_ids": tuple(
                    phase6_target_record_id(item) for item in target_records
                ),
                "candidate_record_ids": tuple(
                    phase6_candidate_record_id(item) for item in candidate_record_tuple
                ),
                "derived_record_ids": tuple(
                    phase6_derived_record_id(item) for item in derived_record_tuple
                ),
            }
        )
        stored_snapshot_id = repository.record_phase6_assessment(
            snapshot,
            targets=target_records,
            candidates=candidate_record_tuple,
            derived=derived_record_tuple,
        )
        for reason, data, receipts in pending_derived_publications:
            post_commit_trace_refs.append(publish(reason, data, receipts=receipts))
        result = Phase6EvidenceResult(
            profiles=tuple(profiles),
            propositions=tuple(propositions),
            mappings=tuple(mappings),
            claims=tuple(claims),
            verifications=tuple(verifications),
            expansions=tuple(expansions),
            edges=tuple(edges),
            chains=tuple(chains),
            classifications=tuple(classifications),
            commit_receipts=tuple(committed_receipts),
            candidate_assessments=tuple(candidate_assessments),
            multi_source=tuple(multi_source_summaries),
            patent_screenings=tuple(patent_screenings),
            unassessed_sources=tuple(dict.fromkeys(unassessed_sources)),
            unassessed_versions=tuple(dict.fromkeys(unassessed_versions)),
            coverage_limitations=tuple(coverage_limitations),
            failures=tuple(failures),
            limitations=tuple(limitations),
            graph_ref=graph_ref,
            snapshot_id=stored_snapshot_id,
        )
        write_phase6_artifacts(writer, assessment_id, result)
        return result


def write_phase6_artifacts(
    writer: RunArtifactWriter,
    assessment_id: AssessmentId,
    result: Phase6EvidenceResult,
) -> None:
    writer.write_jsonl(assessment_id, "phase6/profiles.jsonl", result.profiles)
    writer.write_jsonl(assessment_id, "phase6/propositions.jsonl", result.propositions)
    writer.write_jsonl(assessment_id, "phase6/mappings.jsonl", result.mappings)
    writer.write_jsonl(
        assessment_id,
        "phase6/support_claims.jsonl",
        [bundle.claim for bundle in result.claims],
    )
    writer.write_jsonl(assessment_id, "phase6/support_verifications.jsonl", result.verifications)
    writer.write_jsonl(assessment_id, "phase6/context_expansions.jsonl", result.expansions)
    writer.write_jsonl(assessment_id, "phase6/verified_edges.jsonl", result.edges)
    writer.write_jsonl(assessment_id, "phase6/verified_chains.jsonl", result.chains)
    writer.write_jsonl(
        assessment_id, "phase6/precedent_classifications.jsonl", result.classifications
    )
    writer.write_jsonl(assessment_id, "phase6/commit_receipts.jsonl", result.commit_receipts)
    writer.write_jsonl(assessment_id, "phase6/multi_source_assessments.jsonl", result.multi_source)
    writer.write_jsonl(assessment_id, "phase6/patent_screenings.jsonl", result.patent_screenings)
    writer.write_json(
        assessment_id,
        "phase6/coverage.json",
        {
            "unassessed_sources": list(result.unassessed_sources),
            "unassessed_versions": list(result.unassessed_versions),
            "coverage_limitations": list(result.coverage_limitations),
        },
    )
    writer.write_json(
        assessment_id,
        "phase6/phase6_result.json",
        {
            "graph_ref": result.graph_ref,
            "snapshot_id": result.snapshot_id,
            "mapping_count": len(result.mappings),
            "verification_count": len(result.verifications),
            "verified_edge_count": len(result.edges),
            "classification_count": len(result.classifications),
            "expansion_count": len(result.expansions),
            "unassessed_source_count": len(result.unassessed_sources),
            "unassessed_version_count": len(result.unassessed_versions),
            "failures": list(result.failures),
            "limitations": list(result.limitations),
        },
    )


async def verify_evidence_against_mcus(
    *,
    assessment_id: AssessmentId,
    evidence: EvidenceNormalizationResult,
    mcus: Sequence[MCU],
    combinations: Sequence[MCUCombination] = (),
    as_of: date,
    runner: SemanticRunner,
    repository: EvidenceGraphRepository,
    writer: RunArtifactWriter,
    trace_sink: TraceSink,
    graph_ref: str = "phase5/evidence_graph.sqlite3",
    max_sources_per_mcu: int = 3,
    max_versions_per_source: int = 3,
    max_expansions: int = 2,
    window_chars: int = DEFAULT_WINDOW_CHARS,
    clock: Callable[[], datetime] = utc_now,
) -> Phase6EvidenceResult:
    """Run the complete Phase 6 pipeline and persist its graph fragment."""

    pipeline = EvidenceVerificationPipeline(
        runner,
        max_sources_per_mcu=max_sources_per_mcu,
        max_versions_per_source=max_versions_per_source,
        max_expansions=max_expansions,
        window_chars=window_chars,
    )
    return await pipeline.run(
        assessment_id=assessment_id,
        evidence=evidence,
        mcus=mcus,
        combinations=combinations,
        as_of=as_of,
        repository=repository,
        writer=writer,
        trace_sink=trace_sink,
        graph_ref=graph_ref,
        clock=clock,
    )


__all__ = [
    "EvidenceVerificationPipeline",
    "Phase6EvidenceResult",
    "select_candidate_sources",
    "verify_evidence_against_mcus",
    "write_phase6_artifacts",
]
