"""Stable reproductions for the GPT-6 Sol High Phase 6 review findings.

One regression per finding F01-F11 plus the minor M01; added after the review
recorded them as open. These do not replace the original tests.
"""

import json
from datetime import date

import pytest
from sqlalchemy import text as sql_text

from novelty_harness.domain.enums import PrecedentState, SupportVerificationState
from novelty_harness.evidence.graph.models import EdgeVerificationRef, GraphEdgeKind
from novelty_harness.evidence.graph.phase6_mapping import (
    phase6_graph_provenance,
    verified_edge_graph_fragment,
)
from novelty_harness.evidence.graph.retrieval_mapping import passage_graph_node, version_graph_node
from novelty_harness.evidence.graph.sqlalchemy_repository import (
    SqlAlchemyEvidenceGraphRepository,
)
from novelty_harness.evidence.precedent.gates import (
    _classify_facts as classify_precedent,
)
from novelty_harness.evidence.precedent.patent import PatentEvidenceEntry
from novelty_harness.evidence.verification.gates import (
    EdgeEligibilityError,
    VerificationValidationError,
    build_verified_evidence_edge,
)
from novelty_harness.evidence.verification.integrity import VerifiedEvidenceChain
from novelty_harness.evidence.verification.models import (
    CommitmentStateRecord,
    SupportVerification,
)
from tests.fixtures.phase5 import (
    make_passage,
    make_source,
    make_version,
    phase5_provenance,
)
from tests.unit.evidence.precedent.test_classification import (
    classification_facts as ClassificationFacts,
)
from tests.unit.evidence.precedent.test_classification import (
    commitment,
    facts_for,
)
from tests.unit.evidence.precedent.test_classification import (
    proposition as classification_proposition,
)
from tests.unit.evidence.precedent.test_patent import classification as patent_classification
from tests.unit.evidence.verification.test_eligibility import (
    AS_OF,
    NOW,
    build,
    source,
)
from tests.unit.evidence.verification.test_eligibility import (
    bundle as eligibility_bundle,
)
from tests.unit.evidence.verification.test_eligibility import (
    mapping as eligibility_mapping,
)
from tests.unit.evidence.verification.test_eligibility import (
    proposition as eligibility_proposition,
)
from tests.unit.evidence.verification.test_eligibility import (
    verification as eligibility_verification,
)
from tests.unit.evidence.verification.test_verifier import (
    bundle,
    proposal_data,
    verifier,
)

ORIGIN = phase5_provenance("sol-review-regressions")


# --- F05 ---


async def test_f05_supported_without_citations_is_rejected() -> None:
    data = proposal_data(("mech", "SUPPORTED"), ("outcome", "SUPPORTED"))
    for judgment in data["judgments"]:  # type: ignore[index]
        judgment["passage_ids"] = []  # type: ignore[index]
    with pytest.raises(VerificationValidationError, match="cite at least one"):
        await verifier(data).verify(bundle(), clock=lambda: NOW)


def test_f05_mapper_passages_cannot_substitute_for_verifier_citations() -> None:
    citation_free = SupportVerification(
        verification_id="ver_empty",
        claim_id="claim_1",
        mapping_id="map_1",
        source_id="src_1",
        source_version_id="srcv_1_v1",
        mcu_id="mcu_1",
        state=SupportVerificationState.SUPPORTED,
        commitment_states=(
            CommitmentStateRecord(
                commitment_id="mech",
                dimension=eligibility_proposition().commitments[0].dimension,
                state="SUPPORTED",
                rationale="supported without citation",
                passage_ids=(),
            ),
            CommitmentStateRecord(
                commitment_id="outcome",
                dimension=eligibility_proposition().commitments[1].dimension,
                state="SUPPORTED",
                rationale="supported without citation",
                passage_ids=(),
            ),
        ),
        supported_portions=("mech", "outcome"),
        verifier_prompt_version="support-verifier-v1",
        verifier_rubric_version="support-rubric-v1",
        observed_at=NOW,
        provenance=ORIGIN,
    )
    with pytest.raises(EdgeEligibilityError, match="verifier-cited passages"):
        build_verified_evidence_edge(
            mapping=eligibility_mapping(),
            verification=citation_free,
            proposition=eligibility_proposition(),
            source=source(),
            bundle=eligibility_bundle(),
            version=make_version("src_1", version_id="srcv_1_v1", published_date=date(2020, 1, 1)),
            as_of=AS_OF,
            observed_at=NOW,
        )


# --- F06 ---


def test_f06_foreign_source_version_proposition_joins_are_rejected() -> None:
    target = eligibility_proposition()
    base = dict(
        proposition=target,
        source_id="src_1",
        source_version_id="srcv_1_v1",
        verification=eligibility_verification(SupportVerificationState.SUPPORTED),
        decisive=True,
        chronology_state="PREDATES_CUTOFF",
    )
    with pytest.raises(ValueError, match="Mapping identity"):
        classify_precedent(
            ClassificationFacts(
                **{**base, "mapping": eligibility_mapping(), "source_id": "src_other"},
            ),
            clock=lambda: NOW,
        )
    foreign_mapping = eligibility_mapping().model_copy(update={"source_version_id": "srcv_other"})
    with pytest.raises(ValueError, match="Mapping identity"):
        classify_precedent(
            ClassificationFacts(**{**base, "mapping": foreign_mapping}), clock=lambda: NOW
        )
    foreign_proposition_mapping = eligibility_mapping().model_copy(
        update={"proposition_id": "prop_other"}
    )
    with pytest.raises(ValueError, match="Mapping identity"):
        classify_precedent(
            ClassificationFacts(**{**base, "mapping": foreign_proposition_mapping}),
            clock=lambda: NOW,
        )
    foreign_verification = eligibility_verification(SupportVerificationState.SUPPORTED).model_copy(
        update={"mapping_id": "map_other"}
    )
    with pytest.raises(ValueError, match="Verification identity"):
        classify_precedent(
            ClassificationFacts(
                **{**base, "mapping": eligibility_mapping(), "verification": foreign_verification}
            ),
            clock=lambda: NOW,
        )
    with pytest.raises(EdgeEligibilityError, match="identities must agree"):
        build_verified_evidence_edge(
            mapping=eligibility_mapping().model_copy(update={"proposition_id": "prop_other"}),
            verification=eligibility_verification(SupportVerificationState.SUPPORTED),
            proposition=target,
            source=source(),
            bundle=eligibility_bundle(),
            version=make_version("src_1", version_id="srcv_1_v1", published_date=date(2020, 1, 1)),
            as_of=AS_OF,
            observed_at=NOW,
        )


def test_f06_patent_entry_mcu_and_version_joins_are_rejected() -> None:
    with pytest.raises(ValueError, match="another MCU"):
        PatentEvidenceEntry(
            source_id="src_patent_a",
            mcu_id="mcu_other",
            is_patent=True,
            classification=patent_classification(
                "src_patent_a", PrecedentState.STRONG_PARTIAL_PRECEDENT
            ),
        )
    with pytest.raises(ValueError, match="another version"):
        PatentEvidenceEntry(
            source_id="src_patent_a",
            source_version_id="srcv_other",
            mcu_id="mcu_1",
            is_patent=True,
            classification=patent_classification(
                "src_patent_a", PrecedentState.STRONG_PARTIAL_PRECEDENT
            ),
        )


# --- F07 ---


def _persist_phase6_fragment(repository, edge, classified):
    nodes, graph_edges = verified_edge_graph_fragment(
        (edge,), (classified,), observed_at=NOW, provenance=phase6_graph_provenance()
    )
    from novelty_harness.evidence.graph.models import GraphNode, GraphNodeKind

    existing = (
        GraphNode(
            node_id=edge.source_id,
            kind=GraphNodeKind.SOURCE,
            label="Source",
            observed_at=NOW,
            provenance=ORIGIN,
        ),
        version_graph_node(
            make_version("src_1", version_id="srcv_1_v1", published_date=date(2020, 1, 1)),
            observed_at=NOW,
            provenance=ORIGIN,
        ),
        passage_graph_node(eligibility_bundle().passages[0], observed_at=NOW, provenance=ORIGIN),
        GraphNode(
            node_id="mcu_1",
            kind=GraphNodeKind.MCU,
            label="MCU",
            observed_at=NOW,
            provenance=ORIGIN,
        ),
    )
    repository.upsert(nodes=existing)
    return nodes, graph_edges


def _valid_chain(edge) -> VerifiedEvidenceChain:
    return VerifiedEvidenceChain(
        assessment_id="asm_test",
        source=source(),
        version=make_version("src_1", version_id="srcv_1_v1", published_date=date(2020, 1, 1)),
        proposition=eligibility_proposition(),
        mapping=eligibility_mapping(),
        bundle=eligibility_bundle(),
        verification=eligibility_verification(SupportVerificationState.SUPPORTED),
        edge=edge,
    )


def test_f07_graph_persistence_rejects_unresolved_or_mismatched_verification() -> None:
    edge = build(SupportVerificationState.SUPPORTED, relation=PrecedentState.DIRECT_PRECEDENT)
    from novelty_harness.evidence.precedent.gates import (
        ClassifiedComparison,
        classify_verified_comparison,
    )
    from novelty_harness.evidence.verification.integrity import verified_comparison

    chain = _valid_chain(edge)
    comparison = verified_comparison(chain)
    classified = classify_verified_comparison(comparison, clock=lambda: NOW)

    # Legitimate projected edge persists when its verified artifact is present.
    repository = SqlAlchemyEvidenceGraphRepository()
    _, graph_edges = _persist_phase6_fragment(repository, edge, classified)
    direct = next(item for item in graph_edges if item.kind == GraphEdgeKind.DIRECT_PRECEDENT)
    repository.upsert(
        edges=(direct,),
        verified_edges=(edge,),
        verified_chains=(chain,),
        classified_comparisons=(
            ClassifiedComparison(comparison=comparison, classification=classified),
        ),
    )
    assert repository.get_edge(direct.edge_id) is not None

    fake = direct.model_copy(
        update={
            "verification": EdgeVerificationRef(
                verified_edge_id="edge_does_not_exist",
                support_state=SupportVerificationState.SUPPORTED,
                decisive=True,
                precedent_relation=PrecedentState.DIRECT_PRECEDENT,
            )
        }
    )
    with pytest.raises(ValueError, match="unknown verified edge"):
        repository.upsert(edges=(fake,))
    repository.close()

    # A real verified artifact for another MCU cannot back this edge.
    other_repository = SqlAlchemyEvidenceGraphRepository()
    _persist_phase6_fragment(other_repository, edge, classified)
    other_mcu_edge = edge.model_copy(update={"mcu_id": "mcu_other"})
    with pytest.raises(ValueError, match="resolved semantic chain|semantic chain differs"):
        other_repository.upsert(
            edges=(direct,),
            verified_edges=(other_mcu_edge,),
            verified_chains=(_valid_chain(edge),),
        )
    other_repository.close()


def test_f07_schema_v1_migrates_to_v3(tmp_path) -> None:
    database = tmp_path / "graph.sqlite3"
    repository = SqlAlchemyEvidenceGraphRepository(database)
    # Simulate a v1 database with no Phase 6 edges.
    with repository.engine.begin() as connection:
        connection.execute(sql_text("UPDATE schema_version SET version = 1 WHERE version = 4"))
    repository.close()
    migrated = SqlAlchemyEvidenceGraphRepository(database)
    from novelty_harness.evidence.graph.migrations import SCHEMA_VERSION, schema_version

    assert schema_version(migrated.engine) == SCHEMA_VERSION == 4
    migrated.close()


def test_f07_legacy_direct_edge_cannot_be_reinterpreted_as_verified(tmp_path) -> None:
    database = tmp_path / "legacy-direct.sqlite3"
    edge = build(SupportVerificationState.SUPPORTED, relation=PrecedentState.DIRECT_PRECEDENT)
    from novelty_harness.evidence.precedent.gates import (
        ClassifiedComparison,
        classify_verified_comparison,
    )
    from novelty_harness.evidence.verification.integrity import verified_comparison

    chain = _valid_chain(edge)
    comparison = verified_comparison(chain)
    classified = classify_verified_comparison(comparison, clock=lambda: NOW)
    repository = SqlAlchemyEvidenceGraphRepository(database)
    _, graph_edges = _persist_phase6_fragment(repository, edge, classified)
    direct = next(item for item in graph_edges if item.kind == GraphEdgeKind.DIRECT_PRECEDENT)
    repository.upsert(
        edges=(direct,),
        verified_edges=(edge,),
        verified_chains=(chain,),
        classified_comparisons=(
            ClassifiedComparison(comparison=comparison, classification=classified),
        ),
    )
    with repository.engine.begin() as connection:
        connection.execute(sql_text("UPDATE schema_version SET version = 1 WHERE version = 4"))
    repository.close()
    with pytest.raises(ValueError, match="Legacy Phase 6 graph edges"):
        SqlAlchemyEvidenceGraphRepository(database)


def test_f06_f05_foundations_hold_on_a_valid_edge() -> None:
    # Sanity: the stricter gates still accept a legitimate cited verification.
    from novelty_harness.evidence.mapping.models import ComparisonDimension

    target = classification_proposition(
        commitment("mech", ComparisonDimension.MECHANISM, text="threshold drives a coil"),
    )
    classification = classify_precedent(
        facts_for(
            target,
            states={"mech": "SUPPORTED"},
            matching=(ComparisonDimension.MECHANISM,),
            decisive=True,
            chronology="PREDATES_CUTOFF",
        ),
        clock=lambda: NOW,
    )
    assert classification.relation == PrecedentState.DIRECT_PRECEDENT
    assert date(2026, 9, 28) == AS_OF


# --- F02 ---


def _f02_edge(*, version_published: date | None, source_overrides: dict | None = None):
    return build_verified_evidence_edge(
        mapping=eligibility_mapping(),
        verification=eligibility_verification(SupportVerificationState.SUPPORTED),
        proposition=eligibility_proposition(),
        source=source(**(source_overrides or {})),
        bundle=eligibility_bundle(),
        version=make_version("src_1", version_id="srcv_1_v1", published_date=version_published),
        as_of=AS_OF,
        observed_at=NOW,
    )


def test_f02_post_cutoff_revision_of_old_source_is_not_decisive() -> None:
    edge = _f02_edge(version_published=date(2027, 1, 1))
    assert edge.chronology.state == "POST_CUTOFF"
    assert not edge.decisive
    classification = classify_precedent(
        ClassificationFacts(
            proposition=eligibility_proposition(),
            source_id="src_1",
            source_version_id="srcv_1_v1",
            mapping=eligibility_mapping(),
            verification=eligibility_verification(SupportVerificationState.SUPPORTED),
            decisive=edge.decisive,
            chronology_state=edge.chronology.state,
        ),
        clock=lambda: NOW,
    )
    assert classification.relation == PrecedentState.UNRESOLVED
    assert classification.relation != PrecedentState.DIRECT_PRECEDENT


def test_f02_unknown_version_timing_stays_uncertain() -> None:
    edge = _f02_edge(version_published=None)
    assert edge.chronology.state == "UNCERTAIN"
    assert not edge.decisive
    assert any("uncertain" in item for item in edge.eligibility.reasons)


def test_f02_older_eligible_version_remains_independently_assessable() -> None:
    edge = _f02_edge(version_published=date(2019, 1, 1))
    assert edge.chronology.state == "PREDATES_CUTOFF"
    assert edge.decisive


def test_f02_later_sibling_source_date_does_not_erase_eligible_preprint() -> None:
    edge = _f02_edge(
        version_published=date(2020, 1, 1),
        source_overrides={"dates": {"publication_date": date(2027, 1, 1)}},
    )
    assert edge.chronology.state == "PREDATES_CUTOFF"
    assert edge.decisive


# --- F04 ---

from novelty_harness.domain.mcu import MCU as _MCU  # noqa: E402
from novelty_harness.evidence.phase6_pipeline import (  # noqa: E402
    select_candidate_sources as _select,
)
from novelty_harness.evidence.phase6_pipeline import (  # noqa: E402
    select_versions as _select_versions,
)
from novelty_harness.evidence.pipeline import (  # noqa: E402
    EvidenceNormalizationResult as _EvidenceResult,
)
from novelty_harness.runtime.semantic.structured import SemanticRunner as _Runner  # noqa: E402
from tests.fixtures.phase5 import (  # noqa: E402
    make_discovery_path as _make_path,
)
from tests.fixtures.phase5 import (  # noqa: E402
    make_version as _make_version,
)
from tests.fixtures.phase6 import scripted_phase6_llm as _scripted  # noqa: E402


def _f04_mcu() -> _MCU:
    return _MCU(
        mcu_id="mcu_1",
        label="Switch",
        statement="threshold switches relay",
        mechanism="threshold switches relay",
        provenance=ORIGIN,
    )


def _f04_evidence(sources_count: int, versions_per_source: int):
    sources: list = []
    versions: list = []
    passages: list = []
    for index in range(sources_count):
        sid = f"src_{index:02d}"
        sources.append(
            make_source(
                sid,
                discovery_paths=(
                    _make_path(provider_source_id=f"W{index}", query_id="qry_1", mcu_id="mcu_1"),
                ),
            )
        )
        for version_index in range(versions_per_source):
            vid = f"srcv_{index:02d}_v{version_index}"
            versions.append(
                _make_version(
                    sid,
                    version_id=vid,
                    version_label=f"v{version_index}",
                    published_date=date(2019 + version_index, 1, 1),
                )
            )
            passages.append(
                make_passage(
                    sid,
                    text=f"threshold switches relay source {index} version {version_index}",
                    passage_id=f"pass_{index:02d}_{version_index}",
                    source_version_id=vid,
                )
            )
    return _EvidenceResult(
        sources=tuple(sources),
        versions=tuple(versions),
        passages=tuple(passages),
        provenance_edges=(),
        lineage_clusters=(),
        quality_assessments=(),
        relevance_assessments=(),
        cycles=(),
        conflicts=(),
        unresolved_fields=(),
        limitations=(),
        graph_ref="phase5/evidence_graph.sqlite3",
    )


async def _run_f04_pipeline(tmp_path, evidence, *, max_sources=3, max_versions=3):
    from novelty_harness.evidence.graph.models import GraphNode, GraphNodeKind
    from novelty_harness.evidence.graph.sqlalchemy_repository import (
        SqlAlchemyEvidenceGraphRepository as _Repo,
    )
    from novelty_harness.evidence.phase6_pipeline import (
        verify_evidence_against_mcus as _verify,
    )
    from novelty_harness.runtime.artifacts.writer import RunArtifactWriter as _Writer
    from novelty_harness.runtime.tracing.sinks import InMemoryTraceSink as _Sink

    repository = _Repo()
    repository.upsert(
        nodes=tuple(
            GraphNode(
                node_id=item.source_id,
                kind=GraphNodeKind.SOURCE,
                label=item.canonical_title,
                observed_at=NOW,
                provenance=ORIGIN,
            )
            for item in evidence.sources
        )
    )
    result = await _verify(
        assessment_id="asm_f04",
        evidence=evidence,
        mcus=(_f04_mcu(),),
        as_of=AS_OF,
        runner=_Runner(_scripted()),
        repository=repository,
        writer=_Writer(tmp_path),
        trace_sink=_Sink(),
        max_sources_per_mcu=max_sources,
        max_versions_per_source=max_versions,
        clock=lambda: NOW,
    )
    repository.close()
    return result


async def test_f04_fourth_source_is_explicitly_unassessed(tmp_path) -> None:
    evidence = _f04_evidence(4, 1)
    result = await _run_f04_pipeline(tmp_path, evidence)
    assert "src_03" in result.unassessed_sources
    assert result.coverage_limitations
    coverage = json.loads((tmp_path / "asm_f04" / "phase6" / "coverage.json").read_text())
    assert "src_03" in coverage["unassessed_sources"]


async def test_f04_older_version_is_assessed_not_silently_dropped(tmp_path) -> None:
    evidence = _f04_evidence(1, 4)
    result = await _run_f04_pipeline(tmp_path, evidence)
    selected_versions = {mapping.source_version_id for mapping in result.mappings}
    assert {
        "srcv_00_v0",
        "srcv_00_v1",
        "srcv_00_v2",
    } <= selected_versions
    assert "src_00:srcv_00_v3" in result.unassessed_versions
    assert any(vid in result.unassessed_versions[0] for vid in ("srcv_00_v3",))


def test_f04_selection_helpers_report_bounds() -> None:
    evidence = _f04_evidence(5, 4)
    selection = _select(
        target_id="mcu_1",
        member_ids=("mcu_1",),
        sources=evidence.sources,
        passages_by_source={
            passage.source_id: tuple(
                item for item in evidence.passages if item.source_id == passage.source_id
            )
            for passage in evidence.passages
        },
        max_sources=2,
    )
    assert len(selection.selected) == 2
    assert len(selection.unassessed_sources) == 3
    slots, excluded = _select_versions(tuple(evidence.versions), evidence.passages, max_versions=2)
    assert len(slots) == 2 and len(excluded) >= 2


# --- F01 ---

from novelty_harness.domain.mcu import (  # noqa: E402
    MCUFeature as _MCUFeature,
)
from novelty_harness.domain.mcu import (  # noqa: E402
    MCURelationship as _MCURelationship,
)
from novelty_harness.evidence.mapping.dimensions import (  # noqa: E402
    build_mcu_comparison_profile as _build_profile,
)
from novelty_harness.evidence.mapping.dimensions import (  # noqa: E402
    build_proposition as _build_prop,
)
from novelty_harness.evidence.mapping.models import (  # noqa: E402
    ComparisonDimension as _Dimension,
)
from tests.unit.evidence.precedent.test_classification import (  # noqa: E402
    RELATIONSHIP,
    basic_commitments,
)
from tests.unit.evidence.precedent.test_classification import (  # noqa: E402
    facts_for as _facts_for,
)


def _f01_states(proposition, supported_ids: set[str]) -> dict[str, str]:
    return {
        item.commitment_id: (
            "SUPPORTED" if item.commitment_id in supported_ids else "NOT_SUPPORTED"
        )
        for item in proposition.commitments
    }


def test_f01_statement_only_condition_is_material_and_blocks_generic_direct() -> None:
    proposition = _build_prop(
        _build_profile(
            _MCU(
                mcu_id="mcu_1",
                label="Conditional controller",
                statement="A relay activates only after two independent sensors agree",
                mechanism="threshold switches relay",
                provenance=ORIGIN,
            )
        )
    )
    identifiers = {item.commitment_id for item in proposition.commitments}
    assert "statement:material" in identifiers
    material = next(
        item for item in proposition.commitments if item.commitment_id == "statement:material"
    )
    assert material.dimension == _Dimension.CONSTRAINTS
    assert material.relationship is None  # no fabricated relationship
    assert "two independent sensors agree" in material.text

    generic = classify_precedent(
        _facts_for(
            proposition,
            states=_f01_states(proposition, {"mech"}),
            matching=(_Dimension.MECHANISM,),
            decisive=False,
        ),
        clock=lambda: NOW,
    )
    assert generic.relation != PrecedentState.DIRECT_PRECEDENT
    assert not generic.decisive

    complete = classify_precedent(
        _facts_for(
            proposition,
            states=_f01_states(
                proposition, {item.commitment_id for item in proposition.commitments}
            ),
            matching=(_Dimension.MECHANISM, _Dimension.CONSTRAINTS),
            decisive=True,
            chronology="PREDATES_CUTOFF",
        ),
        clock=lambda: NOW,
    )
    assert complete.relation == PrecedentState.DIRECT_PRECEDENT


@pytest.mark.parametrize(
    "statement",
    [
        "The system works if the cache is warm",
        "The relay activates and the lamp lights",
        "At least three independent sensors must agree",
        "First arm the sensor, then trigger the relay",
        "The relay stays off unless two sensors agree",
        "The relay activates only after two independent sensors agree",
    ],
)
def test_f01_conditional_conjunction_quantified_sequence_and_only_if_conditions(
    statement: str,
) -> None:
    proposition = _build_prop(
        _build_profile(
            _MCU(
                mcu_id="mcu_1",
                label="Conditional controller",
                statement=statement,
                mechanism="threshold switches relay",
                provenance=ORIGIN,
            )
        )
    )
    material = [
        item for item in proposition.commitments if item.commitment_id == "statement:material"
    ]
    assert material, statement
    assert material[0].relationship is None
    generic = classify_precedent(
        _facts_for(
            proposition,
            states=_f01_states(proposition, {"mech"}),
            matching=(_Dimension.MECHANISM,),
            decisive=False,
        ),
        clock=lambda: NOW,
    )
    assert generic.relation != PrecedentState.DIRECT_PRECEDENT


def test_f01_structured_statement_coverage_does_not_add_material_noise() -> None:
    mcu = _MCU(
        mcu_id="mcu_1",
        label="Plain controller",
        statement="A sensor controls a relay",
        mechanism="threshold drives a coil",
        features=(
            _MCUFeature(feature_id="F1", concept="sensor"),
            _MCUFeature(feature_id="F2", concept="relay"),
        ),
        relationships=(_MCURelationship(subject="sensor", relation="controls", object="relay"),),
        provenance=ORIGIN,
    )
    proposition = _build_prop(_build_profile(mcu))
    assert all(item.commitment_id != "statement:material" for item in proposition.commitments)


# --- F10 ---


async def test_f10_narrower_special_case_is_scoped_partial_support() -> None:
    from tests.unit.evidence.verification.test_verifier import OUTCOME, bundle, verifier

    scoped = {
        "prompt_version": "support-verifier-v1",
        "judgments": [
            {
                "commitment_id": "mech",
                "state": "SUPPORTED",
                "rationale": "mechanism stated",
                "passage_ids": ["pass_1"],
            },
            {
                "commitment_id": "outcome",
                "state": "PARTIALLY_SUPPORTED",
                "rationale": "only the read-only subset is stated",
                "passage_ids": ["pass_1"],
                "supported_subset": "read-only workloads",
                "unsupported_remainder": "all workloads",
            },
        ],
        "context_needed": [],
    }
    verification = await verifier(scoped).verify(bundle(), clock=lambda: NOW)
    assert verification.state == SupportVerificationState.PARTIALLY_SUPPORTED
    assert any("read-only workloads" in item for item in verification.supported_portions)
    assert any("all workloads" in item for item in verification.unsupported_portions)
    assert any(item.state == "PARTIALLY_SUPPORTED" for item in verification.commitment_states)
    assert OUTCOME.text

    universal = {
        "prompt_version": "support-verifier-v1",
        "judgments": [
            {
                "commitment_id": "mech",
                "state": "SUPPORTED",
                "rationale": "stated",
                "passage_ids": ["pass_1"],
            },
            {
                "commitment_id": "outcome",
                "state": "SUPPORTED",
                "rationale": "unqualified statement",
                "passage_ids": ["pass_1"],
            },
        ],
        "context_needed": [],
    }
    fully = await verifier(universal).verify(bundle(), clock=lambda: NOW)
    assert fully.state == SupportVerificationState.SUPPORTED


async def test_f10_partial_commitment_requires_a_citation_and_scoped_fields() -> None:
    from novelty_harness.evidence.verification.gates import (
        VerificationValidationError as _VVE,
    )
    from tests.unit.evidence.verification.test_verifier import bundle, verifier

    uncited = {
        "prompt_version": "support-verifier-v1",
        "judgments": [
            {
                "commitment_id": "mech",
                "state": "PARTIALLY_SUPPORTED",
                "rationale": "subset only",
                "passage_ids": [],
                "supported_subset": "subset",
                "unsupported_remainder": "remainder",
            },
        ],
        "context_needed": [],
    }
    with pytest.raises((_VVE, ValueError)):
        await verifier(uncited).verify(bundle(), clock=lambda: NOW)


# --- F03 ---


async def test_f03_nearby_negation_cannot_be_hidden_by_a_short_excerpt() -> None:
    from novelty_harness.evidence.verification.verifier import (
        verify_with_context_retry as _retry,
    )
    from tests.unit.evidence.verification.test_context_retry import (
        CLAIM_TEXT,
        expanded_document,
        qualifier_aware_response,
        retry_verifier,
    )

    target = bundle(CLAIM_TEXT)
    document = expanded_document("However, the operator must always switch it manually.")
    result = await _retry(
        retry_verifier(qualifier_aware_response),
        target,
        available_passages=(target.passages[0], document),
        clock=lambda: NOW,
    )
    assert result.verification.state == SupportVerificationState.CONTRADICTED
    assert result.verification_attempts == 1
    assert any(expansion.available for expansion in result.expansions)


async def test_f03_benign_nearby_context_preserves_support() -> None:
    from novelty_harness.evidence.verification.verifier import (
        verify_with_context_retry as _retry,
    )
    from tests.unit.evidence.verification.test_context_retry import (
        CLAIM_TEXT,
        expanded_document,
        qualifier_aware_response,
        retry_verifier,
    )

    target = bundle(CLAIM_TEXT)
    document = expanded_document("Additional detail supports the same claim.")
    result = await _retry(
        retry_verifier(qualifier_aware_response),
        target,
        available_passages=(target.passages[0], document),
        clock=lambda: NOW,
    )
    assert result.verification.state == SupportVerificationState.SUPPORTED
    assert result.verification_attempts == 1
    assert any(expansion.available for expansion in result.expansions)


async def test_f03_no_expandable_context_is_explicit_and_bounded() -> None:
    from novelty_harness.evidence.verification.verifier import (
        verify_with_context_retry as _retry,
    )
    from tests.unit.evidence.verification.test_context_retry import (
        CLAIM_TEXT,
        qualifier_aware_response,
        retry_verifier,
    )

    target = bundle(CLAIM_TEXT)
    result = await _retry(
        retry_verifier(qualifier_aware_response),
        target,
        available_passages=(target.passages[0],),
        clock=lambda: NOW,
    )
    assert result.verification.state == SupportVerificationState.INSUFFICIENT_CONTEXT
    assert result.expansions and not any(item.available for item in result.expansions)
    assert result.expansions[0].blocked_reason is not None


def test_f03_expansion_never_crosses_source_or_version() -> None:
    from novelty_harness.evidence.context.expansion import (
        expand_passage_context as _expand,
    )

    target = make_passage(
        "src_1",
        text="The method is effective.",
        passage_id="pass_inner",
        source_version_id="srcv_1_v1",
    )
    other_version = make_passage(
        "src_1",
        text="The method is effective. However it failed.",
        passage_id="pass_doc",
        source_version_id="srcv_other",
    )
    other_source = make_passage(
        "src_other",
        text="The method is effective. However it failed.",
        passage_id="pass_doc2",
        source_version_id="srcv_1_v1",
    )
    for outsider in (other_version, other_source):
        expansion = _expand(
            target, available_passages=(target, outsider), attempt=1, clock=lambda: NOW
        )
        assert not expansion.available
        assert expansion.blocked_reason is not None


# --- F09 ---


def test_f09_unverified_purpose_match_cannot_upgrade_to_analogy() -> None:
    target = classification_proposition(*basic_commitments())
    classification = classify_precedent(
        _facts_for(
            target,
            states={"mech": "NOT_SUPPORTED", "feat": "SUPPORTED", "rel": "NOT_SUPPORTED"},
            matching=(_Dimension.PURPOSE, _Dimension.FEATURES),
        ),
        clock=lambda: NOW,
    )
    assert classification.relation == PrecedentState.COMPONENT_PRECEDENT_ONLY
    assert classification.functional_similarity == ()
    assert not classification.decisive


def test_f09_verified_functional_commitment_supports_analogy() -> None:
    target = classification_proposition(
        commitment("mech", _Dimension.MECHANISM, text="threshold drives a coil"),
        commitment("purpose", _Dimension.PURPOSE, text="avoid manual switching"),
        commitment(
            "rel", _Dimension.RELATIONSHIPS, text="sensor controls relay", relationship=RELATIONSHIP
        ),
    )
    classification = classify_precedent(
        _facts_for(
            target,
            states={
                "mech": "NOT_SUPPORTED",
                "purpose": "SUPPORTED",
                "rel": "NOT_SUPPORTED",
            },
            matching=(_Dimension.PURPOSE,),
        ),
        clock=lambda: NOW,
    )
    assert classification.relation == PrecedentState.ANALOGOUS_PRECEDENT
    assert _Dimension.PURPOSE in classification.functional_similarity
    assert not classification.decisive


def test_f09_verified_relationship_uncertainty_blocks_direct_until_resolved() -> None:
    target = classification_proposition(*basic_commitments())
    all_supported = {
        "mech": "SUPPORTED",
        "feat": "SUPPORTED",
        "rel": "SUPPORTED",
    }
    conflicted = classify_precedent(
        _facts_for(
            target,
            states={"mech": "SUPPORTED", "feat": "SUPPORTED", "rel": "INSUFFICIENT"},
            matching=(
                _Dimension.MECHANISM,
                _Dimension.FEATURES,
                _Dimension.RELATIONSHIPS,
            ),
            conflicting=(_Dimension.CONTROL_FLOW,),
            decisive=False,
            chronology="PREDATES_CUTOFF",
        ),
        clock=lambda: NOW,
    )
    assert conflicted.relation == PrecedentState.UNRESOLVED
    assert conflicted.relation != PrecedentState.DIRECT_PRECEDENT
    assert conflicted.unresolved

    resolved = classify_precedent(
        _facts_for(
            target,
            states=all_supported,
            matching=(
                _Dimension.MECHANISM,
                _Dimension.FEATURES,
                _Dimension.RELATIONSHIPS,
            ),
            decisive=True,
            chronology="PREDATES_CUTOFF",
        ),
        clock=lambda: NOW,
    )
    assert resolved.relation == PrecedentState.DIRECT_PRECEDENT
    mapper_only_conflict = classify_precedent(
        _facts_for(
            target,
            states=all_supported,
            conflicting=(_Dimension.CONTROL_FLOW,),
            decisive=True,
            chronology="PREDATES_CUTOFF",
        ),
        clock=lambda: NOW,
    )
    assert mapper_only_conflict.relation == resolved.relation


# --- F08 ---


def _f08_entry(
    source_id: str,
    relation,
    *,
    publication: date,
    priority: date | None = None,
    decisive: bool = False,
):
    from tests.unit.evidence.precedent.test_patent import entry as _entry

    return _entry(
        source_id,
        relation,
        decisive=decisive,
        publication=publication,
        priority=priority,
    )


def test_f08_future_patent_references_cannot_challenge_the_cutoff() -> None:
    from novelty_harness.evidence.precedent.patent import (
        screen_patent_references as _screen,
    )

    result = _screen(
        mcu_id="mcu_1",
        entries=(
            _f08_entry(
                "src_patent_a",
                PrecedentState.STRONG_PARTIAL_PRECEDENT,
                publication=date(2027, 1, 1),
            ),
            _f08_entry(
                "src_patent_b",
                PrecedentState.COMPONENT_PRECEDENT_ONLY,
                publication=date(2027, 6, 1),
            ),
        ),
        as_of=AS_OF,
        observed_at=NOW,
        clock=lambda: NOW,
    )
    assert result.mode == "LIMITED"
    assert result.mode != "MULTI_REFERENCE_COMBINATION_LIKE"
    assert result.reference_source_ids == ()
    assert any("post-cutoff" in item for item in result.limitations)


def test_f08_family_publications_count_as_one_lineage_root() -> None:
    from novelty_harness.evidence.precedent.patent import (
        screen_patent_references as _screen,
    )

    result = _screen(
        mcu_id="mcu_1",
        entries=(
            _f08_entry(
                "src_patent_us",
                PrecedentState.STRONG_PARTIAL_PRECEDENT,
                publication=date(2020, 1, 1),
            ),
            _f08_entry(
                "src_patent_ep",
                PrecedentState.COMPONENT_PRECEDENT_ONLY,
                publication=date(2021, 1, 1),
            ),
        ),
        as_of=AS_OF,
        observed_at=NOW,
        independent_root_of={"src_patent_us": "src_family", "src_patent_ep": "src_family"},
        clock=lambda: NOW,
    )
    assert result.mode == "LIMITED"
    assert any("one root" in item or "one patent" in item for item in result.limitations)


def test_f08_independent_pre_cutoff_partials_remain_combination_context() -> None:
    from novelty_harness.evidence.precedent.patent import (
        screen_patent_references as _screen,
    )

    result = _screen(
        mcu_id="mcu_1",
        entries=(
            _f08_entry(
                "src_patent_a",
                PrecedentState.STRONG_PARTIAL_PRECEDENT,
                publication=date(2019, 1, 1),
            ),
            _f08_entry(
                "src_patent_b",
                PrecedentState.STRONG_PARTIAL_PRECEDENT,
                publication=date(2020, 1, 1),
            ),
        ),
        as_of=AS_OF,
        observed_at=NOW,
        clock=lambda: NOW,
    )
    assert result.mode == "MULTI_REFERENCE_COMBINATION_LIKE"
    assert result.single_reference_id is None
    assert any("never one-reference anticipation" in item for item in result.limitations)


def test_f08_future_decisive_reference_is_not_selected_over_eligible_one() -> None:
    from novelty_harness.evidence.precedent.patent import (
        screen_patent_references as _screen,
    )

    result = _screen(
        mcu_id="mcu_1",
        entries=(
            _f08_entry(
                "src_patent_future",
                PrecedentState.DIRECT_PRECEDENT,
                publication=date(2027, 1, 1),
                decisive=True,
            ),
            _f08_entry(
                "src_patent_eligible",
                PrecedentState.DIRECT_PRECEDENT,
                publication=date(2019, 1, 1),
                decisive=True,
            ),
        ),
        as_of=AS_OF,
        observed_at=NOW,
        clock=lambda: NOW,
    )
    assert result.mode == "SINGLE_REFERENCE_ANTICIPATION_LIKE"
    assert result.single_reference_id == "src_patent_eligible"
    assert any("post-cutoff" in item for item in result.limitations)


# --- F11 ---

from novelty_harness.domain.enums import (  # noqa: E402
    PrecedentState as _PrecedentState,
)
from novelty_harness.domain.enums import (  # noqa: E402
    SupportVerificationState as _SupportState,
)
from novelty_harness.domain.evidence import (  # noqa: E402
    EvidenceComparison as _LegacyComparison,
)
from novelty_harness.domain.evidence import (  # noqa: E402
    EvidenceEdge as _LegacyEdge,
)
from novelty_harness.domain.evidence import (  # noqa: E402
    SourcePassage as _LegacyPassage,
)
from novelty_harness.domain.evidence import (  # noqa: E402
    SourceRecord as _LegacySource,
)


def _legacy_source(source_id: str = "src_1") -> _LegacySource:
    return _LegacySource(
        source_id=source_id,
        canonical_title="Legacy source",
        source_type="paper",
        access_state="full_text",
        content_hash="legacy-hash-" + source_id,
        provider_name="fixture",
        provider_source_id="x",
        provenance=ORIGIN,
    )


def _legacy_passage(passage_id: str = "pass_1", source_id: str = "src_1") -> _LegacyPassage:
    return _LegacyPassage(
        passage_id=passage_id,
        source_id=source_id,
        text="Exact legacy text.",
        content_hash="legacy-passage-hash",
        provenance=ORIGIN,
    )


def _legacy_edge(*, edge_id: str, mcu_id: str, passage_ids: tuple[str, ...]) -> _LegacyEdge:
    return _LegacyEdge(
        edge_id=edge_id,
        source_id="src_1",
        mcu_id=mcu_id,
        proposition="legacy proposition",
        passage_ids=passage_ids,
        comparison=_LegacyComparison(),
        relation_type=_PrecedentState.STRONG_PARTIAL_PRECEDENT,
        support_verification=_SupportState.SUPPORTED,
        provenance=ORIGIN,
    )


def test_f11_bridge_accepts_combination_and_expanded_passage_identities() -> None:
    from novelty_harness.application.vertical_slice import _check_edges
    from novelty_harness.domain.mcu import MCU as _BridgeMCU

    mcu = _BridgeMCU(mcu_id="mcu_1", label="MCU", statement="statement", provenance=ORIGIN)
    sources = (_legacy_source(),)
    passages = (_legacy_passage(),)
    combination_edge = _legacy_edge(
        edge_id="edge_comb", mcu_id="mcu_comb_abc", passage_ids=("pass_1",)
    )
    expanded_edge = _legacy_edge(
        edge_id="edge_window", mcu_id="mcu_1", passage_ids=("pass_window",)
    )
    with pytest.raises(ValueError, match="unknown MCU"):
        _check_edges((combination_edge,), (mcu,), sources, passages)
    with pytest.raises(ValueError, match="does not belong"):
        _check_edges((expanded_edge,), (mcu,), sources, passages)

    _check_edges(
        (combination_edge, expanded_edge),
        (mcu,),
        sources,
        passages,
        extra_mcu_ids=("mcu_comb_abc",),
        extra_passage_sources={"pass_window": "src_1"},
    )
    with pytest.raises(ValueError, match="does not belong"):
        _check_edges(
            (expanded_edge,),
            (mcu,),
            sources,
            passages,
            extra_passage_sources={"pass_window": "src_other"},
        )
    with pytest.raises(ValueError, match="unknown MCU"):
        _check_edges(
            (_legacy_edge(edge_id="edge_foreign", mcu_id="mcu_foreign", passage_ids=("pass_1",)),),
            (mcu,),
            sources,
            passages,
            extra_mcu_ids=("mcu_comb_abc",),
        )


async def test_f11_pipeline_projection_passes_the_bridge_with_combination_and_window(
    tmp_path,
) -> None:
    from novelty_harness.application.evidence_phase5 import (
        project_passage as _project_passage,
    )
    from novelty_harness.application.evidence_phase5 import (
        project_source as _project_source,
    )
    from novelty_harness.application.evidence_phase6 import (
        project_verified_edges as _project_edges,
    )
    from novelty_harness.application.vertical_slice import _check_edges
    from novelty_harness.domain.mcu import (
        MCU as _BridgeMCU,
    )
    from novelty_harness.domain.mcu import (
        MCUCombination as _Combination,
    )
    from novelty_harness.domain.mcu import (
        MCURelationship as _Relationship,
    )
    from novelty_harness.evidence.graph.models import GraphNode, GraphNodeKind
    from novelty_harness.evidence.phase6_pipeline import (
        verify_evidence_against_mcus as _verify,
    )
    from novelty_harness.runtime.artifacts.writer import RunArtifactWriter as _Writer
    from novelty_harness.runtime.semantic.structured import SemanticRunner as _Runner2
    from novelty_harness.runtime.tracing.sinks import InMemoryTraceSink as _Sink2
    from tests.fixtures.phase6 import (
        StubLLMProvider as _Stub,
    )
    from tests.fixtures.phase6 import context_json as _ctx_json
    from tests.fixtures.phase6 import (
        map_evidence_response as _map_response,
    )

    def verify_citing_last(context):
        payload = _ctx_json(context, "verification_input")
        last = payload["passages"][-1]["passage_id"]
        return {
            "prompt_version": "support-verifier-v1",
            "judgments": [
                {
                    "commitment_id": commitment["commitment_id"],
                    "state": "SUPPORTED",
                    "rationale": "cites the expanded window",
                    "passage_ids": [last],
                }
                for commitment in payload["commitments"]
            ],
            "context_needed": [],
        }

    source = make_source(
        "src_1",
        discovery_paths=(
            _make_path(provider_source_id="W1", query_id="qry_1", mcu_id="mcu_1"),
            _make_path(provider_source_id="W1", query_id="qry_1", mcu_id="mcu_2"),
        ),
    )
    version = make_version("src_1", version_id="srcv_1_v1", published_date=date(2020, 1, 1))
    section = make_passage(
        "src_1",
        text="The method is effective.",
        passage_id="pass_section",
        source_version_id="srcv_1_v1",
    )
    document = make_passage(
        "src_1",
        text="The method is effective. However, it failed after a week.",
        passage_id="pass_document",
        source_version_id="srcv_1_v1",
    )
    evidence = _EvidenceResult(
        sources=(source,),
        versions=(version,),
        passages=(section, document),
        provenance_edges=(),
        lineage_clusters=(),
        quality_assessments=(),
        relevance_assessments=(),
        cycles=(),
        conflicts=(),
        unresolved_fields=(),
        limitations=(),
        graph_ref="phase5/evidence_graph.sqlite3",
    )
    mcus = (
        _BridgeMCU(
            mcu_id="mcu_1",
            label="One",
            statement="threshold switches relay",
            mechanism="threshold switches relay",
            provenance=ORIGIN,
        ),
        _BridgeMCU(
            mcu_id="mcu_2",
            label="Two",
            statement="indicator shows state",
            mechanism="lamp follows relay",
            provenance=ORIGIN,
        ),
    )
    combination = _Combination(
        combination_id="C1",
        label="Combined",
        statement="threshold switches relay and lamp follows",
        member_ids=("mcu_1", "mcu_2"),
        relationships=(_Relationship(subject="relay", relation="controls", object="lamp"),),
        provenance=ORIGIN,
    )
    repository = SqlAlchemyEvidenceGraphRepository()
    repository.upsert(
        nodes=tuple(
            GraphNode(
                node_id=item.source_id,
                kind=GraphNodeKind.SOURCE,
                label=item.canonical_title,
                observed_at=NOW,
                provenance=ORIGIN,
            )
            for item in evidence.sources
        )
    )
    runner = _Runner2(_Stub({"map_evidence": _map_response, "verify_support": verify_citing_last}))
    result = await _verify(
        assessment_id="asm_f11",
        evidence=evidence,
        mcus=mcus,
        combinations=(combination,),
        as_of=AS_OF,
        runner=runner,
        repository=repository,
        writer=_Writer(tmp_path),
        trace_sink=_Sink2(),
        clock=lambda: NOW,
    )
    repository.close()
    assert any(edge.mcu_id.startswith("mcu_comb_") for edge in result.edges)
    window_ids = {
        expansion.window_passage.passage_id
        for expansion in result.expansions
        if expansion.available and expansion.window_passage is not None
    }
    assert window_ids
    projected = _project_edges(result)
    assert any(set(edge.passage_ids) & window_ids for edge in projected)

    legacy_sources = tuple(
        _project_source(item, provenance=item.provenance) for item in evidence.sources
    )
    legacy_passages = tuple(
        _project_passage(item, provenance=item.provenance) for item in evidence.passages
    )
    _check_edges(
        projected,
        mcus,
        legacy_sources,
        legacy_passages,
        extra_mcu_ids=tuple(item.mcu_id for item in result.propositions),
        extra_passage_sources={
            expansion.window_passage.passage_id: expansion.window_passage.source_id
            for expansion in result.expansions
            if expansion.available and expansion.window_passage is not None
        },
    )
    with pytest.raises(ValueError, match="does not belong"):
        _check_edges(
            tuple(edge for edge in projected if set(edge.passage_ids) & window_ids),
            mcus,
            legacy_sources,
            legacy_passages,
            extra_mcu_ids=tuple(item.mcu_id for item in result.propositions),
        )
