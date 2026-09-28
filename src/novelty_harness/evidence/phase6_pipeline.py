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

from pydantic import JsonValue

from novelty_harness.domain.base import utc_now
from novelty_harness.domain.enums import AssessmentStage, PrecedentState, TraceStatus
from novelty_harness.domain.idea import ArtifactProvenance
from novelty_harness.domain.ids import AssessmentId, MCUId, SourceId, new_trace_event_id
from novelty_harness.domain.mcu import MCU, MCUCombination
from novelty_harness.evidence.context.expansion import DEFAULT_WINDOW_CHARS
from novelty_harness.evidence.context.selection import (
    PassageSelectionError,
    SupportEvidenceBundle,
    select_support_passages,
)
from novelty_harness.evidence.graph.models import GraphNode, GraphNodeKind
from novelty_harness.evidence.graph.phase6_mapping import (
    phase6_graph_provenance,
    verified_edge_graph_fragment,
)
from novelty_harness.evidence.graph.repository import EvidenceGraphRepository
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
    SourceType,
    SourceVersionRecord,
)
from novelty_harness.evidence.passages.models import PassageRecord
from novelty_harness.evidence.pipeline import EvidenceNormalizationResult
from novelty_harness.evidence.precedent.gates import (
    ClassificationFacts,
    MultiSourceAssessment,
    classify_precedent,
    summarize_multi_source,
)
from novelty_harness.evidence.precedent.models import (
    PatentScreeningResult,
    PrecedentClassification,
)
from novelty_harness.evidence.precedent.patent import (
    PatentEvidenceEntry,
    patent_locator_from_passage,
    screen_patent_references,
)
from novelty_harness.evidence.quality.models import EvidenceQualityAssessment
from novelty_harness.evidence.verification.gates import build_verified_evidence_edge
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
from novelty_harness.runtime.tracing.models import TraceEvent
from novelty_harness.runtime.tracing.sinks import TraceSink

_PIPELINE_PROVENANCE = ArtifactProvenance(
    kind="implemented",
    component="phase6_pipeline",
    detail="Passage-grounded mapping, independent verification and local classification.",
)


@dataclass(frozen=True, slots=True)
class Phase6EvidenceResult:
    profiles: tuple[MCUComparisonProfile, ...]
    propositions: tuple[EvidenceProposition, ...]
    mappings: tuple[SourceMCUMapping, ...]
    claims: tuple[SupportEvidenceBundle, ...]
    verifications: tuple[SupportVerification, ...]
    expansions: tuple[ContextExpansion, ...]
    edges: tuple[VerifiedEvidenceEdge, ...]
    classifications: tuple[PrecedentClassification, ...]
    multi_source: tuple[MultiSourceAssessment, ...]
    patent_screenings: tuple[PatentScreeningResult, ...]
    unassessed_sources: tuple[SourceId, ...]
    unassessed_versions: tuple[str, ...]
    coverage_limitations: tuple[str, ...]
    failures: tuple[str, ...]
    limitations: tuple[str, ...]
    graph_ref: str


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
    routed = [
        source
        for source in sources
        if any(path.mcu_id in wanted for path in source.discovery_paths)
    ]
    pool = routed or list(sources)
    eligible = [
        source
        for source in pool
        if source.access_state in {SourceAccessState.FULL_TEXT, SourceAccessState.ABSTRACT_ONLY}
        and passages_by_source.get(source.source_id)
    ]
    ordered = sorted(eligible, key=lambda source: source.source_id)
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
    selected: tuple[SourceVersionRecord | None, ...] = tuple(usable[:max_versions])
    excluded = tuple(version.version_id for version in usable[max_versions:])
    if not selected:
        return (None,), excluded
    return selected, excluded


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
        classifications: list[PrecedentClassification],
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
            return
        claims.append(bundle)
        retry = await verify_with_context_retry(
            self.verifier,
            bundle,
            available_passages=source_passages,
            max_expansions=self.max_expansions,
            window_chars=self.window_chars,
            clock=clock,
        )
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
            failure=retry.verification.state.value in {"NOT_SUPPORTED", "CONTRADICTED"},
            stage=AssessmentStage.EVIDENCE_VERIFIED,
        )
        edge = build_verified_evidence_edge(
            mapping=mapping,
            verification=retry.verification,
            proposition=proposition,
            source=source,
            as_of=as_of,
            observed_at=clock(),
            version=version,
            quality=quality_by_source.get(source.source_id),
        )
        classification = classify_precedent(
            ClassificationFacts(
                proposition=proposition,
                source_id=source.source_id,
                source_version_id=version.version_id if version else None,
                mapping=mapping,
                verification=retry.verification,
                claim_id=retry.verification.claim_id,
                decisive=edge.decisive,
                chronology_state=edge.chronology.state,
            ),
            clock=clock,
        )
        if classification.relation != PrecedentState.UNASSESSABLE:
            edge = build_verified_evidence_edge(
                mapping=mapping,
                verification=retry.verification,
                proposition=proposition,
                source=source,
                as_of=as_of,
                observed_at=clock(),
                version=version,
                quality=quality_by_source.get(source.source_id),
                relation=classification.relation,
            )
        edges.append(edge)
        classifications.append(classification)
        target_classifications.append(classification)
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
            source_id: cluster.root_source_ids[0]
            for cluster in evidence.lineage_clusters
            for source_id in cluster.source_ids
            if cluster.root_source_ids
        }

        def emit(
            reason: str,
            data: dict[str, JsonValue],
            *,
            failure: bool = False,
            stage: AssessmentStage = AssessmentStage.EVIDENCE_MAPPED,
        ) -> None:
            trace_sink.emit(
                TraceEvent(
                    event_id=new_trace_event_id(),
                    assessment_id=assessment_id,
                    occurred_at=clock(),
                    stage=stage,
                    component="phase6_evidence",
                    status=TraceStatus.FAILURE if failure else TraceStatus.SUCCESS,
                    reason_code=reason,
                    data={"execution": "implemented", "semantics_implemented": True, **data},
                )
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
        classifications: list[PrecedentClassification] = []
        multi_source_summaries: list[MultiSourceAssessment] = []
        unassessed_sources: list[SourceId] = []
        unassessed_versions: list[str] = []
        failures: list[str] = []

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
            unassessed_sources.extend(selection.unassessed_sources)
            target_classifications: list[PrecedentClassification] = []
            for source in selection.selected:
                all_passages = passages_by_source[source.source_id]
                version_slots, excluded_versions = select_versions(
                    versions_by_source.get(source.source_id, ()),
                    all_passages,
                    max_versions=self.max_versions_per_source,
                )
                unassessed_versions.extend(
                    f"{source.source_id}:{version_id}" for version_id in excluded_versions
                )
                for version in version_slots:
                    source_passages = tuple(
                        passage
                        for passage in all_passages
                        if version is not None and passage.source_version_id == version.version_id
                    ) or (all_passages if version is None else ())
                    if not source_passages:
                        continue
                    await self._assess_candidate(
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
                        classifications=classifications,
                        target_classifications=target_classifications,
                        failures=failures,
                        emit=emit,
                        clock=clock,
                    )
            summary = summarize_multi_source(
                target_classifications,
                mcu_id=profile.target_id,
                independent_root_of=independent_root_of,
            )
            multi_source_summaries.append(summary)
            emit(
                "MULTI_SOURCE_ASSESSMENT",
                {
                    "mcu_id": profile.target_id,
                    "combination_context": summary.combination_context,
                    "single_source_direct_eligible": summary.single_source_direct_eligible,
                },
            )

        patent_screenings: list[PatentScreeningResult] = []
        classification_by_verification = {
            classification.verification_id: classification
            for classification in classifications
            if classification.verification_id is not None
        }
        for profile, proposition, _ in targets:
            entries: list[PatentEvidenceEntry] = []
            for edge in edges:
                if edge.mcu_id != profile.target_id:
                    continue
                source = next((item for item in sources if item.source_id == edge.source_id), None)
                if source is None:
                    continue
                classification = classification_by_verification.get(edge.verification_id)
                if classification is None:
                    continue
                locators = tuple(
                    patent_locator_from_passage(edge.source_id, passage_id, passage.locator)
                    for passage_id in edge.passage_ids
                    for passage in passages_by_source.get(edge.source_id, ())
                    if passage.passage_id == passage_id
                )
                entries.append(
                    PatentEvidenceEntry(
                        source_id=edge.source_id,
                        source_version_id=edge.source_version_id,
                        mcu_id=profile.target_id,
                        is_patent=source.source_type == SourceType.PATENT,
                        classification=classification,
                        priority_date=source.dates.patent_priority_date,
                        publication_date=source.dates.patent_publication_date,
                        locators=locators,
                    )
                )
            if entries:
                screening = screen_patent_references(
                    mcu_id=profile.target_id,
                    entries=tuple(entries),
                    as_of=as_of,
                    observed_at=clock(),
                    independent_root_of=independent_root_of,
                )
                patent_screenings.append(screening)
                emit(
                    "PATENT_SCREENING",
                    {
                        "screening_id": screening.screening_id,
                        "mcu_id": profile.target_id,
                        "mode": screening.mode,
                    },
                )

        mcu_nodes = tuple(
            GraphNode(
                node_id=profile.target_id,
                kind=GraphNodeKind.MCU,
                label=profile.label,
                attributes={
                    "statement": profile.statement,
                    "target_kind": profile.target_kind,
                    "combination_id": profile.combination_id,
                },
                observed_at=clock(),
                provenance=_PIPELINE_PROVENANCE,
            )
            for profile in profiles
        )
        expansion_passages = tuple(
            expansion.window_passage
            for expansion in expansions
            if expansion.available and expansion.window_passage is not None
        )
        fragment_nodes, fragment_edges = verified_edge_graph_fragment(
            tuple(edges),
            tuple(classifications),
            passages=expansion_passages,
            observed_at=clock(),
            provenance=phase6_graph_provenance(),
        )
        repository.upsert(
            nodes=(*mcu_nodes, *fragment_nodes),
            edges=fragment_edges,
            verified_edges=tuple(edges),
        )
        emit(
            "PHASE6_GRAPH_PERSISTED",
            {
                "graph_ref": graph_ref,
                "edge_count": len(fragment_edges),
                "proposition_count": len(edges),
            },
        )

        coverage_limitations: list[str] = []
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
        result = Phase6EvidenceResult(
            profiles=tuple(profiles),
            propositions=tuple(propositions),
            mappings=tuple(mappings),
            claims=tuple(claims),
            verifications=tuple(verifications),
            expansions=tuple(expansions),
            edges=tuple(edges),
            classifications=tuple(classifications),
            multi_source=tuple(multi_source_summaries),
            patent_screenings=tuple(patent_screenings),
            unassessed_sources=tuple(dict.fromkeys(unassessed_sources)),
            unassessed_versions=tuple(dict.fromkeys(unassessed_versions)),
            coverage_limitations=tuple(coverage_limitations),
            failures=tuple(failures),
            limitations=tuple(limitations),
            graph_ref=graph_ref,
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
    writer.write_jsonl(
        assessment_id, "phase6/precedent_classifications.jsonl", result.classifications
    )
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
