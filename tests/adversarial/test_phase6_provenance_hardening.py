"""Adversarial probes for the Phase 6 immutable-content provenance root."""

from datetime import UTC, datetime

import pytest

from novelty_harness.evidence.context.expansion import ContextCompleteness, inspect_passage_context
from novelty_harness.evidence.passages.extraction import (
    extract_resolved_content,
    extract_span,
    resolve_version_content,
)
from novelty_harness.evidence.passages.hashing import text_hash
from tests.fixtures.phase5 import make_source, make_version, phase5_provenance

NOW = datetime(2026, 9, 30, tzinfo=UTC)


def _resolved(text: str):
    source = make_source("src_provenance", content_hash=text_hash(text))
    version = make_version("src_provenance", content_hash=text_hash(text))
    return resolve_version_content(source=source, version=version, text=text, retrieved_at=NOW)


def test_r01_resolved_version_rejects_conflicting_content() -> None:
    source = make_source("src_provenance", content_hash=text_hash("Actual version"))
    version = make_version("src_provenance", content_hash=text_hash("Actual version"))
    with pytest.raises(ValueError, match="digest|hash|content"):
        resolve_version_content(
            source=source, version=version, text="Invented decisive passage", retrieved_at=NOW
        )


def test_r01_genuine_subspan_has_exact_parent_offsets() -> None:
    resolved = _resolved("Before. Support. After.")
    passage = extract_span(
        resolved,
        char_start=8,
        char_end=16,
        observed_at=NOW,
        provenance=phase5_provenance(),
    )
    assert passage.text == "Support."
    assert passage.attestation is not None
    assert passage.attestation.parent_content_digest == resolved.content_digest
    assert passage.attestation.start_offset == 8
    assert passage.attestation.end_offset == 16


def test_r01_complete_document_matches_parent_digest() -> None:
    resolved = _resolved("Support throughout the whole document.")
    passage = extract_resolved_content(resolved, observed_at=NOW, provenance=phase5_provenance())
    assert passage.attestation is not None
    assert passage.attestation.passage_digest == resolved.content_digest


def test_r01_complete_document_rejects_conflicting_parent_digest() -> None:
    from pydantic import ValidationError

    from novelty_harness.evidence.passages.models import PassageAttestation

    resolved = _resolved("A complete document.")
    passage = extract_resolved_content(resolved, observed_at=NOW, provenance=phase5_provenance())
    assert passage.attestation is not None
    payload = passage.attestation.model_dump(mode="json")
    payload["parent_content_digest"] = text_hash("A different document.")
    with pytest.raises(ValidationError, match="digest"):
        PassageAttestation.model_validate(payload)


def test_r01_complete_abstract_has_authenticated_unit_limits() -> None:
    from novelty_harness.evidence.normalization.models import SourceAccessState
    from novelty_harness.evidence.passages.extraction import extract_abstract

    text = "A complete abstract about a relay."
    source = make_source(
        "src_provenance",
        access_state=SourceAccessState.ABSTRACT_ONLY,
        content_hash=text_hash(text),
    )
    version = make_version(
        "src_provenance",
        access_state=SourceAccessState.ABSTRACT_ONLY,
        content_hash=text_hash(text),
    )
    resolved = resolve_version_content(source=source, version=version, text=text)
    passage = extract_abstract(resolved, observed_at=NOW, provenance=phase5_provenance())
    assert passage.attestation is not None
    assert (passage.attestation.unit_start, passage.attestation.unit_end) == (0, len(text))
    assert (
        inspect_passage_context(passage, available_passages=(passage,), attempt=1).completeness
        == ContextCompleteness.COMPLETE
    )


def test_r01_paragraph_and_patent_claim_units_are_extractor_attested() -> None:
    from novelty_harness.evidence.passages.extraction import (
        extract_paragraph_window,
        extract_patent_claim,
    )

    paragraph = extract_paragraph_window(
        _resolved("First paragraph.\n\nSecond paragraph."),
        start_paragraph=1,
        end_paragraph=1,
        observed_at=NOW,
        provenance=phase5_provenance(),
    )
    assert paragraph.attestation is not None
    assert paragraph.attestation.unit_start == paragraph.attestation.start_offset
    assert (
        inspect_passage_context(paragraph, available_passages=(paragraph,), attempt=1).completeness
        == ContextCompleteness.COMPLETE
    )

    claim = extract_patent_claim(
        _resolved("1. A relay controller.\n2. The controller of claim 1 with a sensor."),
        claim_number=1,
        observed_at=NOW,
        provenance=phase5_provenance(),
    )
    assert claim.text == "1. A relay controller."
    assert claim.attestation is not None
    assert claim.attestation.unit_start == claim.attestation.start_offset
    assert (
        inspect_passage_context(claim, available_passages=(claim,), attempt=1).completeness
        == ContextCompleteness.COMPLETE
    )


def test_r02_short_excerpt_cannot_be_declared_complete_document() -> None:
    from novelty_harness.evidence.passages.models import EvidenceUnitBoundary, EvidenceUnitScope

    resolved = _resolved("Support. However not in production.")
    with pytest.raises(ValueError, match="boundary|attestation|unit"):
        extract_span(
            resolved,
            char_start=0,
            char_end=8,
            observed_at=NOW,
            provenance=phase5_provenance(),
            unit_boundary=EvidenceUnitBoundary(
                unit_id="forged",
                scope=EvidenceUnitScope.DOCUMENT,
                starts_unit=True,
                ends_unit=True,
            ),
        )
    passage = extract_span(
        resolved,
        char_start=0,
        char_end=8,
        observed_at=NOW,
        provenance=phase5_provenance(),
    )
    inspection = inspect_passage_context(passage, available_passages=(passage,), attempt=1)
    assert inspection.completeness != ContextCompleteness.COMPLETE


def test_r01_public_edge_rejects_self_hashed_passage_from_other_version_content() -> None:
    from novelty_harness.domain.enums import SupportVerificationState
    from novelty_harness.evidence.verification.gates import (
        EdgeEligibilityError,
        build_verified_evidence_edge,
    )
    from tests.unit.evidence.verification.test_eligibility import (
        AS_OF,
        bundle,
        mapping,
        proposition,
        source,
        verification,
    )

    with pytest.raises(EdgeEligibilityError, match="provenance|digest|hash|attestation"):
        build_verified_evidence_edge(
            mapping=mapping(),
            verification=verification(SupportVerificationState.SUPPORTED),
            proposition=proposition(),
            source=source(content_hash=text_hash("Actual version content")),
            bundle=bundle(),
            version=make_version(
                "src_1", version_id="srcv_1_v1", content_hash=text_hash("Actual version content")
            ),
            as_of=AS_OF,
            observed_at=NOW,
            assessment_id="asm_provenance",
        )


def test_r01_conflicting_version_digest_rolls_back_graph_transaction() -> None:
    from novelty_harness.evidence.graph.models import GraphEdgeKind
    from tests.adversarial.test_phase6_contract_consolidation import _direct_graph_case

    repository, edge, chain, classified, nodes, edges = _direct_graph_case()
    assert chain.version is not None
    forged_version = chain.version.model_copy(
        update={"content_hash": text_hash("Other immutable version content")}
    )
    forged_chain = chain.model_copy(update={"version": forged_version})
    with pytest.raises(ValueError, match="digest|hash|content"):
        repository.upsert(
            nodes=nodes,
            edges=edges,
            verified_edges=(edge,),
            verified_chains=(forged_chain,),
            classified_comparisons=(classified,),
        )
    assert not any(item.kind == GraphEdgeKind.DIRECT_PRECEDENT for item in repository.edges())
    assert repository.observations(edge.edge_id) == ()
    repository.close()


def test_r03_duplicate_commitment_judgments_are_invalid() -> None:
    from pydantic import ValidationError

    from novelty_harness.domain.enums import SupportVerificationState
    from novelty_harness.evidence.verification.models import SupportVerification
    from tests.unit.evidence.verification.test_eligibility import verification

    payload = verification(SupportVerificationState.SUPPORTED).model_dump(mode="json")
    payload["commitment_states"].append(payload["commitment_states"][0])
    with pytest.raises(ValidationError, match="duplicate|unique"):
        SupportVerification.model_validate(payload)


@pytest.mark.parametrize("change", ["missing", "extra"])
def test_r03_exact_material_commitment_set_is_required(change: str) -> None:
    from pydantic import ValidationError

    from novelty_harness.domain.enums import SupportVerificationState
    from novelty_harness.evidence.verification.models import SupportVerification
    from tests.unit.evidence.verification.test_eligibility import verification

    payload = verification(SupportVerificationState.SUPPORTED).model_dump(mode="json")
    payload["material_commitment_ids"] = ["mech", "outcome"]
    if change == "missing":
        payload["commitment_states"].pop()
    else:
        extra = dict(payload["commitment_states"][0])
        extra["commitment_id"] = "unclaimed"
        payload["commitment_states"].append(extra)
    with pytest.raises(ValidationError, match="material commitment"):
        SupportVerification.model_validate(payload)


def test_r03_copied_partial_cannot_construct_decisive_edge() -> None:
    from novelty_harness.domain.enums import SupportVerificationState
    from novelty_harness.evidence.verification.gates import build_verified_evidence_edge
    from tests.unit.evidence.verification.test_eligibility import (
        AS_OF,
        bundle,
        mapping,
        proposition,
        source,
        verification,
    )

    partial = verification(SupportVerificationState.PARTIALLY_SUPPORTED)
    copied = partial.model_copy(update={"state": SupportVerificationState.SUPPORTED})
    with pytest.raises(ValueError, match="aggregate|commitment"):
        build_verified_evidence_edge(
            mapping=mapping(),
            verification=copied,
            proposition=proposition(),
            source=source(),
            bundle=bundle(),
            version=make_version("src_1", version_id="srcv_1_v1"),
            as_of=AS_OF,
            observed_at=NOW,
            assessment_id="asm_provenance",
        )


def test_r04_unrouted_eligible_source_is_selected_or_unassessed() -> None:
    from novelty_harness.evidence.phase6_pipeline import select_candidate_sources
    from tests.fixtures.phase5 import make_discovery_path, make_passage

    routed = make_source("src_routed", discovery_paths=(make_discovery_path(mcu_id="mcu_A"),))
    other = make_source("src_other", discovery_paths=(make_discovery_path(mcu_id="mcu_B"),))
    selection = select_candidate_sources(
        target_id="mcu_A",
        member_ids=("mcu_A",),
        sources=(routed, other),
        passages_by_source={
            routed.source_id: (make_passage(routed.source_id),),
            other.source_id: (make_passage(other.source_id),),
        },
        max_sources=1,
    )
    assert selection.selected[0].source_id == routed.source_id
    assert other.source_id in selection.unassessed_sources


async def test_r05_invalid_mapper_output_returns_unassessable_without_zip_crash(tmp_path) -> None:
    import httpx

    from novelty_harness.domain.enums import PrecedentState
    from novelty_harness.evidence.graph.sqlalchemy_repository import (
        SqlAlchemyEvidenceGraphRepository,
    )
    from novelty_harness.evidence.phase6_pipeline import verify_evidence_against_mcus
    from novelty_harness.runtime.artifacts.writer import RunArtifactWriter
    from novelty_harness.runtime.semantic.structured import SemanticRunner
    from novelty_harness.runtime.tracing.sinks import InMemoryTraceSink
    from tests.fixtures.phase1 import make_fixture
    from tests.fixtures.phase4 import assessment, wire
    from tests.fixtures.phase6 import StubLLMProvider, verify_support_response
    from tests.integration.test_phase6_evidence_pipeline import graph_database, run_phase5

    writer = RunArtifactWriter(tmp_path)
    database = graph_database(tmp_path)
    async with httpx.AsyncClient(transport=httpx.MockTransport(wire)) as client:
        evidence = await run_phase5(writer, client, database)
    repository = SqlAlchemyEvidenceGraphRepository(database)
    try:
        result = await verify_evidence_against_mcus(
            assessment_id="asm_research",
            evidence=evidence,
            mcus=make_fixture().graph.mcus,
            combinations=make_fixture().graph.combinations,
            as_of=assessment().request.as_of,
            runner=SemanticRunner(
                StubLLMProvider(
                    {
                        "map_evidence": {
                            "prompt_version": "evidence-mapper-v1",
                            "dimensions": [],
                            "unresolved": [],
                        },
                        "verify_support": verify_support_response,
                    }
                )
            ),
            repository=repository,
            writer=writer,
            trace_sink=InMemoryTraceSink(),
            graph_ref="phase5/evidence_graph.sqlite3",
            clock=lambda: NOW,
        )
        assert result.classifications
        assert all(item.relation == PrecedentState.UNASSESSABLE for item in result.classifications)
        assert all(item.chain is None for item in result.candidate_assessments)
        assert result.failures
    finally:
        repository.close()


def test_r07_foreign_mcu_direct_cannot_change_target_summary() -> None:
    from novelty_harness.evidence.precedent.gates import summarize_multi_source
    from tests.unit.evidence.precedent.test_anti_stitching import (
        classify_precedent,
        combination_proposition,
    )
    from tests.unit.evidence.precedent.test_classification import NOW as CLASSIFY_NOW
    from tests.unit.evidence.precedent.test_classification import facts_for

    direct = classify_precedent(
        facts_for(
            combination_proposition(),
            states={"f1": "SUPPORTED", "f2": "SUPPORTED", "rel": "SUPPORTED"},
        ),
        clock=lambda: CLASSIFY_NOW,
    )
    with pytest.raises(ValueError, match="MCU|target"):
        summarize_multi_source((direct,), mcu_id="mcu_other")


def test_r07_foreign_mcu_partials_cannot_make_combination_context() -> None:
    from novelty_harness.evidence.precedent.gates import summarize_multi_source
    from tests.unit.evidence.precedent.test_anti_stitching import (
        classify_precedent,
        combination_proposition,
    )
    from tests.unit.evidence.precedent.test_classification import NOW as CLASSIFY_NOW
    from tests.unit.evidence.precedent.test_classification import facts_for

    target = combination_proposition()
    partials = tuple(
        classify_precedent(
            facts_for(target, states=states, source_id=source_id),
            clock=lambda: CLASSIFY_NOW,
        )
        for source_id, states in (
            ("src_a", {"f1": "SUPPORTED", "f2": "NOT_SUPPORTED", "rel": "NOT_SUPPORTED"}),
            ("src_b", {"f1": "NOT_SUPPORTED", "f2": "SUPPORTED", "rel": "NOT_SUPPORTED"}),
        )
    )
    with pytest.raises(ValueError, match="MCU|target"):
        summarize_multi_source(partials, mcu_id="mcu_other")


def test_r07_authoritative_summary_rejects_foreign_assessment_or_target_type() -> None:
    from novelty_harness.domain.enums import PrecedentState
    from novelty_harness.evidence.precedent.gates import summarize_multi_source
    from tests.unit.evidence.precedent.test_patent import entry

    classified = entry("src_summary", PrecedentState.DIRECT_PRECEDENT, decisive=True).comparison
    assert classified is not None
    with pytest.raises(ValueError, match="assessment"):
        summarize_multi_source(
            (classified,), mcu_id="mcu_1", assessment_id="asm_foreign", target_kind="MCU"
        )
    with pytest.raises(ValueError, match="combination|target"):
        summarize_multi_source(
            (classified,),
            mcu_id="mcu_1",
            assessment_id="asm_src_summary",
            target_kind="COMBINATION",
            combination_id="C1",
        )


def test_r05_candidate_result_cannot_pair_foreign_classification() -> None:
    from novelty_harness.domain.enums import PrecedentState
    from novelty_harness.evidence.phase6_pipeline import CandidateAssessmentResult
    from tests.unit.evidence.precedent.test_patent import entry

    classified = entry("src_pair", PrecedentState.DIRECT_PRECEDENT, decisive=True).comparison
    assert classified is not None
    wrong = classified.classification.model_copy(update={"mapping_id": "map_foreign"})
    with pytest.raises(ValueError, match="classification|comparison|basis"):
        CandidateAssessmentResult(
            assessment_id="asm_src_pair",
            source_id="src_pair",
            target_mcu_id="mcu_1",
            target_kind="MCU",
            status="ASSESSED",
            chain=classified.comparison,
            classification=wrong,
        )


async def test_r08_copied_verified_comparison_chronology_fails_public_classifier(tmp_path) -> None:
    import httpx

    from novelty_harness.evidence.graph.sqlalchemy_repository import (
        SqlAlchemyEvidenceGraphRepository,
    )
    from novelty_harness.evidence.phase6_pipeline import verify_evidence_against_mcus
    from novelty_harness.evidence.precedent.gates import classify_verified_comparison
    from novelty_harness.evidence.verification.integrity import verified_comparison
    from novelty_harness.runtime.artifacts.writer import RunArtifactWriter
    from novelty_harness.runtime.semantic.structured import SemanticRunner
    from novelty_harness.runtime.tracing.sinks import InMemoryTraceSink
    from tests.fixtures.phase1 import make_fixture
    from tests.fixtures.phase4 import assessment, wire
    from tests.fixtures.phase6 import scripted_phase6_llm
    from tests.integration.test_phase6_evidence_pipeline import graph_database, run_phase5

    writer = RunArtifactWriter(tmp_path)
    database = graph_database(tmp_path)
    async with httpx.AsyncClient(transport=httpx.MockTransport(wire)) as client:
        evidence = await run_phase5(writer, client, database)
    repository = SqlAlchemyEvidenceGraphRepository(database)
    try:
        result = await verify_evidence_against_mcus(
            assessment_id="asm_research",
            evidence=evidence,
            mcus=make_fixture().graph.mcus,
            combinations=make_fixture().graph.combinations,
            as_of=assessment().request.as_of,
            runner=SemanticRunner(scripted_phase6_llm()),
            repository=repository,
            writer=writer,
            trace_sink=InMemoryTraceSink(),
            graph_ref="phase5/evidence_graph.sqlite3",
            clock=lambda: NOW,
        )
        original = verified_comparison(result.chains[0])
        forged_chronology = original.chronology.model_copy(
            update={"as_of": assessment().request.as_of.replace(year=2019)}
        )
        forged_edge = original.chain.edge.model_copy(update={"chronology": forged_chronology})
        forged_chain = original.chain.model_copy(update={"edge": forged_edge})
        forged = original.model_copy(
            update={"chain": forged_chain, "chronology": forged_chronology}
        )
        with pytest.raises(ValueError, match="chronology|chain|edge|identity"):
            classify_verified_comparison(forged)
    finally:
        repository.close()


def test_r09_v2_orphan_verified_row_cannot_silently_migrate(tmp_path) -> None:
    from sqlalchemy import create_engine, text

    from novelty_harness.evidence.graph.migrations import ensure_schema

    engine = create_engine(f"sqlite:///{tmp_path / 'legacy-v2.sqlite'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE schema_version ("
                "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
        )
        connection.execute(text("INSERT INTO schema_version VALUES (2, 'legacy')"))
        connection.execute(
            text("CREATE TABLE verified_edges (edge_id TEXT PRIMARY KEY, document TEXT NOT NULL)")
        )
        connection.execute(text("INSERT INTO verified_edges VALUES ('edge_orphan', '{}')"))
    with pytest.raises(ValueError, match="Legacy verified edges|reprocessing"):
        ensure_schema(engine)
    engine.dispose()


def test_r06_caller_asserted_patent_date_cannot_override_cited_version() -> None:
    from datetime import date

    from novelty_harness.domain.enums import PrecedentState
    from novelty_harness.evidence.precedent.patent import screen_patent_references
    from tests.unit.evidence.precedent.test_patent import (
        AS_OF,
        cited_chronology,
        entry,
    )

    forged = entry(
        "src_future_patent",
        PrecedentState.DIRECT_PRECEDENT,
        decisive=True,
        source_version_id="srcv_future",
        publication=date(2027, 1, 1),
        chronology=cited_chronology(date(2020, 1, 1)),
        authenticated=False,
    )
    result = screen_patent_references(
        mcu_id="mcu_1",
        entries=(forged,),
        as_of=AS_OF,
        observed_at=NOW,
    )
    assert result.mode != "SINGLE_REFERENCE_ANTICIPATION_LIKE"


def test_r02_copied_complete_context_cannot_rescue_authenticated_short_span() -> None:
    from novelty_harness.domain.enums import SupportVerificationState
    from novelty_harness.evidence.verification.gates import build_verified_evidence_edge
    from tests.unit.evidence.verification.test_eligibility import (
        AS_OF,
        bundle,
        mapping,
        proposition,
        verification,
    )

    short = "A threshold drives a relay coil and switches a load without an operator."
    full = short + " However, the operator must reset the relay."
    source = make_source("src_1", content_hash=text_hash(full))
    from datetime import date

    version = make_version(
        "src_1",
        version_id="srcv_1_v1",
        content_hash=text_hash(full),
        published_date=date(2020, 1, 1),
    )
    resolved = resolve_version_content(source=source, version=version, text=full)
    passage = extract_span(
        resolved,
        char_start=0,
        char_end=len(short),
        observed_at=NOW,
        provenance=phase5_provenance(),
    ).model_copy(update={"passage_id": "pass_1"})
    claim_bundle = bundle().model_copy(update={"passages": (passage,)})
    edge = build_verified_evidence_edge(
        mapping=mapping(),
        verification=verification(SupportVerificationState.SUPPORTED),
        proposition=proposition(),
        source=source,
        bundle=claim_bundle,
        version=version,
        as_of=AS_OF,
        observed_at=NOW,
        assessment_id="asm_provenance",
    )
    assert not edge.decisive
