import json
import sqlite3
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from typing import cast

import httpx
import pytest

from novelty_harness.application.evidence_phase5 import Phase5EvidenceComponents
from novelty_harness.application.evidence_phase6 import Phase6EvidenceComponents
from novelty_harness.application.research import Phase3ResearchComponents
from novelty_harness.application.research_phase4 import Phase4ResearchComponents
from novelty_harness.application.vertical_slice import run_vertical_slice
from novelty_harness.domain.adjudication import FrozenAdjudication, MCUFinding
from novelty_harness.domain.enums import (
    PrecedentState,
    VerdictState,
)
from novelty_harness.domain.evidence import SourceDates
from novelty_harness.domain.mcu import MCUCombination, MCURelationship
from novelty_harness.evidence.graph.sqlalchemy_repository import (
    SqlAlchemyEvidenceGraphRepository,
)
from novelty_harness.evidence.normalization.models import CanonicalIdentifiers, SourceType
from novelty_harness.evidence.passages.extraction import (
    extract_resolved_content,
    extract_span,
    resolve_version_content,
)
from novelty_harness.evidence.passages.hashing import text_hash
from novelty_harness.evidence.passages.models import PassageLocatorKind
from novelty_harness.intake.pipeline import UnderstandingComponents
from novelty_harness.research.applicability import EvidenceFamilyApplicabilityAssessor
from novelty_harness.research.coverage import CoveragePolicy
from novelty_harness.research.critique import SearchPlanCritic
from novelty_harness.research.planning import SearchStrategist
from novelty_harness.research.revision import SearchPlanReviser
from novelty_harness.research.screening import ScreeningExecutor
from novelty_harness.runtime.artifacts.writer import RunArtifactWriter
from novelty_harness.runtime.config.models import BudgetLimits
from novelty_harness.runtime.semantic.structured import SemanticRunner
from novelty_harness.runtime.tracing.sinks import InMemoryTraceSink
from tests.fixtures.phase1 import FIXED_TIME, fixture_provenance, make_fixture
from tests.fixtures.phase2 import RecordedLLM, understanding_responses
from tests.fixtures.phase3 import applicability_response, planning_response
from tests.fixtures.phase4 import registry, stop_policy, wire
from tests.fixtures.phase5 import SyntheticContentResolver
from tests.fixtures.phase6 import (
    StubLLMProvider,
    context_json,
    map_evidence_response,
)
from tests.unit.research.test_search_critique import critic_response


class CombinationReconciler:
    """Wrap the real understanding reconciler and add a combination contribution."""

    def __init__(self, inner) -> None:
        self.inner = inner

    async def reconcile(self, idea, candidates):
        graph = await self.inner.reconcile(idea, candidates)
        if graph.combinations or len(graph.mcus) < 2:
            return graph
        combination = MCUCombination(
            combination_id="C1",
            label="Combined control and indication",
            statement="Control the relay and show its status",
            member_ids=tuple(mcu.mcu_id for mcu in graph.mcus[:2]),
            relationships=(
                MCURelationship(subject="control", relation="triggers", object="indication"),
            ),
            provenance=fixture_provenance("CombinationReconciler"),
        )
        return graph.model_copy(update={"combinations": (combination,)})


class Phase7FixtureAdjudicator:
    """Fixture-backed Phase 7 adjudication over a repository assessment view."""

    def __init__(self, *, tamper_root: Path | None = None) -> None:
        self.view = None
        self.tamper_root = tamper_root

    async def adjudicate_phase6(
        self, *, assessment_id, as_of, idea, sufficiency, mcus, view
    ) -> FrozenAdjudication:
        self.view = view
        if self.tamper_root is not None and view.authorized_graph_relations:
            path = self.tamper_root / assessment_id / "phase5" / "evidence_graph.sqlite3"
            relation = view.authorized_graph_relations[0]
            with sqlite3.connect(path) as connection:
                connection.execute(
                    "DELETE FROM phase6_graph_edge_memberships WHERE edge_id = ?",
                    (relation.edge.edge_id,),
                )
        decisive_by_mcu: dict[str, str] = {}
        relation_by_mcu: dict[str, PrecedentState] = {}
        for relation in view.authorized_graph_relations:
            edge = relation.edge
            if edge.kind.value == "DIRECT_PRECEDENT" and edge.verification is not None:
                decisive_by_mcu.setdefault(edge.target_node_id, relation.verified_edge_id)
                relation_by_mcu.setdefault(edge.target_node_id, PrecedentState.DIRECT_PRECEDENT)
        findings = tuple(
            MCUFinding(
                mcu_id=mcu.mcu_id,
                precedent_state=relation_by_mcu.get(mcu.mcu_id, PrecedentState.UNRESOLVED),
                verdict=VerdictState.UNASSESSABLE,
                decisive_edges=(
                    (decisive_by_mcu[mcu.mcu_id],) if mcu.mcu_id in decisive_by_mcu else ()
                ),
                limiting_factors=("Phase 7 adjudication remains explicitly fixture-backed",),
            )
            for mcu in mcus
        )
        return FrozenAdjudication(
            assessment_id=assessment_id,
            as_of=as_of,
            frozen_at=FIXED_TIME,
            overall_state=VerdictState.UNASSESSABLE,
            mcus=findings,
            established_findings=("Phase 6 verified local source/MCU comparisons are present",),
            value_findings=(),
            validation_requirements=("Real adjudication gates are deferred to Phase 7",),
            permitted_language=(
                "This run proves architecture through Phase 6; novelty is unassessed.",
            ),
            forbidden_claims=("Nobody has ever done this",),
            unresolved_questions=("Phase 7 adjudication, challenge and defence are deferred",),
            evidence_limitations=(
                "Fixture adjudication over real Phase 6 verified evidence; no novelty verdict",
            ),
            coverage_matrix=(),
            provenance=fixture_provenance("Phase7FixtureAdjudicator"),
        )


class ExpandedPhase5EvidenceComponents(Phase5EvidenceComponents):
    async def execute(self, **kwargs):
        result = await super().execute(**kwargs)
        full = next(
            passage
            for passage in result.passages
            if passage.locator.kind == PassageLocatorKind.RESOLVED_CONTENT
        )
        assert full.attestation is not None
        excerpt = extract_span(
            full.attestation.parent,
            char_start=0,
            char_end=min(25, len(full.text)),
            observed_at=FIXED_TIME,
            provenance=fixture_provenance("expanded-phase5-slice"),
            kind=PassageLocatorKind.BLOCK,
            source_version_id=full.source_version_id,
        )
        return replace(result, passages=(excerpt, *result.passages))


class MixedProvenancePhase5EvidenceComponents(ExpandedPhase5EvidenceComponents):
    async def execute(self, **kwargs):
        result = await super().execute(**kwargs)
        base = next(passage for passage in result.passages if passage.attestation is not None)
        base_source = next(
            source for source in result.sources if source.source_id == base.source_id
        )
        base_version = next(
            version for version in result.versions if version.version_id == base.source_version_id
        )
        sources = list(result.sources)
        versions = list(result.versions)
        passages = list(result.passages)
        for label in ("direct", "patent_partial", "contradiction", "mapper_failure"):
            source_id = f"src_lifecycle_{label}"
            text = f"{label.upper()} authenticated evidence for the relay configuration."
            source = base_source.model_copy(
                update={
                    "source_id": source_id,
                    "canonical_title": label,
                    "identifiers": CanonicalIdentifiers(),
                    "source_type": SourceType.PATENT
                    if label == "patent_partial"
                    else SourceType.PAPER,
                    "dates": SourceDates(
                        publication_date=base_version.published_date,
                        patent_publication_date=base_version.published_date
                        if label == "patent_partial"
                        else None,
                    ),
                    "content_hash": text_hash(text),
                }
            )
            version = base_version.model_copy(
                update={
                    "version_id": f"srcv_lifecycle_{label}",
                    "source_id": source_id,
                    "content_hash": text_hash(text),
                }
            )
            resolved = resolve_version_content(source=source, version=version, text=text)
            passage = extract_resolved_content(
                resolved,
                observed_at=FIXED_TIME,
                provenance=fixture_provenance("mixed-provenance-lifecycle"),
            )
            sources.append(source)
            versions.append(version)
            passages.append(passage)
        return replace(
            result, sources=tuple(sources), versions=tuple(versions), passages=tuple(passages)
        )


def mixed_map_response(context):
    identity = context_json(context, "source_identity")
    assert isinstance(identity, dict)
    if identity["source_id"] == "src_lifecycle_mapper_failure":
        return {"prompt_version": "evidence-mapper-v1", "dimensions": [], "unresolved": []}
    return map_evidence_response(context)


def mixed_verify_response(context):
    payload = context_json(context, "verification_input")
    assert isinstance(payload, dict)
    passage = payload["passages"][-1]
    text = passage["text"]
    if "CONTRADICTION" in text:
        state = "CONTRADICTED"
    elif "PATENT_PARTIAL" in text:
        state = "PARTIALLY_SUPPORTED"
    else:
        state = "SUPPORTED"
    return {
        "prompt_version": "support-verifier-v1",
        "judgments": [
            {
                "commitment_id": item["commitment_id"],
                "state": state,
                "rationale": "scripted authenticated lifecycle case",
                "passage_ids": [passage["passage_id"]],
                **(
                    {"supported_subset": "relay control", "unsupported_remainder": "all contexts"}
                    if state == "PARTIALLY_SUPPORTED"
                    else {}
                ),
            }
            for item in payload["commitments"]
        ],
        "context_needed": [],
    }


def verify_expanded_response(context):
    payload = context_json(context, "verification_input")
    assert isinstance(payload, dict)
    cited = payload["passages"][-1]["passage_id"]
    return {
        "prompt_version": "support-verifier-v1",
        "judgments": [
            {
                "commitment_id": item["commitment_id"],
                "state": "PARTIALLY_SUPPORTED" if index == 0 else "SUPPORTED",
                "rationale": "scripted fixture support over expanded context",
                "passage_ids": [cited],
                **(
                    {
                        "supported_subset": "read-only operations",
                        "unsupported_remainder": "all operations",
                    }
                    if index == 0
                    else {}
                ),
            }
            for index, item in enumerate(payload["commitments"])
        ],
        "context_needed": [],
    }


async def test_slice_runs_real_phase_6_and_keeps_phase_7_fixture_backed(tmp_path) -> None:
    f = make_fixture()
    understanding = UnderstandingComponents(
        SemanticRunner(RecordedLLM(understanding_responses())), clock=f.clock
    )
    runner = SemanticRunner(
        RecordedLLM(
            {
                "assess_families": applicability_response(),
                "plan_research": planning_response(),
                "criticize_search": critic_response(),
            }
        )
    )
    phase7 = Phase7FixtureAdjudicator()
    components = replace(
        f.components,
        normalizer=understanding,
        sufficiency_analyzer=understanding,
        decomposer=understanding,
        reconciler=CombinationReconciler(understanding),
        adjudicator=phase7,
    )
    sink = InMemoryTraceSink()
    async with httpx.AsyncClient(transport=httpx.MockTransport(wire)) as client:
        providers, _ = registry(client, clock=f.clock)
        policy = CoveragePolicy.standard()
        research = Phase3ResearchComponents(
            EvidenceFamilyApplicabilityAssessor(runner),
            SearchStrategist(runner),
            SearchPlanCritic(runner),
            SearchPlanReviser(runner),
            ScreeningExecutor(providers, policy),
        )
        adaptive = Phase4ResearchComponents(
            providers, policy, BudgetLimits(max_deep_search_rounds=80), stop_policy()
        )
        result = await run_vertical_slice(
            request=f.request,
            components=components,
            search_provider=f.search_provider,
            content_resolver=SyntheticContentResolver(),
            trace_sink=sink,
            artifact_writer=RunArtifactWriter(tmp_path),
            clock=f.clock,
            research=research,
            adaptive_research=adaptive,
            evidence=ExpandedPhase5EvidenceComponents(),
            phase6=Phase6EvidenceComponents(
                SemanticRunner(
                    StubLLMProvider(
                        {
                            "map_evidence": map_evidence_response,
                            "verify_support": verify_expanded_response,
                        }
                    )
                )
            ),
            phase6_fixture_adjudicator=phase7,
        )
    assert result.record.stage.value == "REPORTED" and result.record.status.value == "COMPLETED"
    assert result.adjudication.provenance.kind == "fixture"
    reasons = [event.reason_code for event in sink.events]
    assert "PHASE7_FIXTURE_BOUNDARY" in reasons
    assert "PHASE6_FIXTURE_BOUNDARY" not in reasons
    assert "EVIDENCE_MAPPING" in reasons and "SUPPORT_VERIFICATION" in reasons
    assert "PHASE6_GRAPH_PERSISTED" in reasons

    run_dir = result.run_dir
    phase6 = run_dir / "phase6"
    assert {
        "profiles.jsonl",
        "propositions.jsonl",
        "mappings.jsonl",
        "support_claims.jsonl",
        "support_verifications.jsonl",
        "context_expansions.jsonl",
        "verified_edges.jsonl",
        "precedent_classifications.jsonl",
        "multi_source_assessments.jsonl",
        "patent_screenings.jsonl",
        "phase6_result.json",
    } <= {path.name for path in phase6.iterdir()}
    summary = json.loads((phase6 / "phase6_result.json").read_text())
    assert summary["mapping_count"] > 0
    assert summary["verified_edge_count"] > 0
    assert not (run_dir / "evidence_edges.jsonl").exists()
    assert phase7.view is not None
    exported_view = json.loads((phase6 / "assessment_view.json").read_text())
    assert exported_view["export_kind"] == "derived_repository_assessment_view"
    assert exported_view["snapshot_id"] == phase7.view.snapshot_id
    assert exported_view["commit_ids"] == list(phase7.view.commit_ids)
    verified_edges = [
        json.loads(line)
        for line in (phase6 / "verified_edges.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert all(
        edge["disclosure"]["source_version_id"] == edge["source_version_id"]
        for edge in verified_edges
    )
    assert any(target.target_kind == "COMBINATION" for target in phase7.view.targets)
    expansions = [
        json.loads(line)
        for line in (phase6 / "context_expansions.jsonl").read_text().splitlines()
        if line.strip()
    ]
    expanded_ids = {
        item["window_passage"]["passage_id"]
        for item in expansions
        if item["available"] and item["window_passage"] is not None
    }
    assert expanded_ids
    assert any(
        item.comparison.comparison.chain.edge.mcu_id.startswith("mcu_comb_")
        and expanded_ids.intersection(cited.passage.passage_id for cited in item.cited_passages)
        for item in phase7.view.committed_comparisons
    )
    classifications = [
        json.loads(line)
        for line in (phase6 / "precedent_classifications.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert any(item["scoped_coverage"] for item in classifications)
    assert all(not item["decisive"] for item in classifications if item["scoped_coverage"])

    repository = SqlAlchemyEvidenceGraphRepository(run_dir / "phase5" / "evidence_graph.sqlite3")
    kinds = {node.kind.value for node in repository.nodes()}
    assert {"SOURCE", "MCU", "EVIDENCE_PROPOSITION"} <= kinds
    assert any(edge.verification is not None for edge in repository.edges())
    assert all(
        "classification_id" in edge.attributes
        for edge in repository.edges()
        if edge.kind.value in {"DIRECT_PRECEDENT", "STRONG_PARTIAL_PRECEDENT"}
    )
    repository.close()

    assert {f"q{i}" for i in range(1, 10)} <= json.loads((run_dir / "report.json").read_text())[
        "answers"
    ].keys()


async def test_real_phase6_requires_explicit_fixture_adjudicator(tmp_path) -> None:
    fixture = make_fixture()
    with pytest.raises(ValueError, match="explicit Phase 7 fixture adjudicator"):
        await run_vertical_slice(
            request=fixture.request,
            components=fixture.components,
            search_provider=fixture.search_provider,
            content_resolver=SyntheticContentResolver(),
            trace_sink=InMemoryTraceSink(),
            artifact_writer=RunArtifactWriter(tmp_path),
            clock=fixture.clock,
            phase6=cast(Phase6EvidenceComponents, object()),
        )
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("delete_membership", [False, True])
async def test_authenticated_mixed_phase6_lifecycle_reaches_completed(
    tmp_path, delete_membership: bool
) -> None:
    fixture = make_fixture()
    understanding = UnderstandingComponents(
        SemanticRunner(RecordedLLM(understanding_responses())), clock=fixture.clock
    )
    research_runner = SemanticRunner(
        RecordedLLM(
            {
                "assess_families": applicability_response(),
                "plan_research": planning_response(),
                "criticize_search": critic_response(),
            }
        )
    )
    phase7 = Phase7FixtureAdjudicator(tamper_root=tmp_path if delete_membership else None)
    components = replace(
        fixture.components,
        normalizer=understanding,
        sufficiency_analyzer=understanding,
        decomposer=understanding,
        reconciler=CombinationReconciler(understanding),
        adjudicator=phase7,
    )
    sink = InMemoryTraceSink()
    expected = (
        pytest.raises(ValueError, match="membership|authorized|projection")
        if delete_membership
        else nullcontext()
    )
    with expected:
        async with httpx.AsyncClient(transport=httpx.MockTransport(wire)) as client:
            providers, _ = registry(client, clock=fixture.clock)
            policy = CoveragePolicy.standard()
            result = await run_vertical_slice(
                request=fixture.request,
                components=components,
                search_provider=fixture.search_provider,
                content_resolver=SyntheticContentResolver(),
                trace_sink=sink,
                artifact_writer=RunArtifactWriter(tmp_path),
                clock=fixture.clock,
                research=Phase3ResearchComponents(
                    EvidenceFamilyApplicabilityAssessor(research_runner),
                    SearchStrategist(research_runner),
                    SearchPlanCritic(research_runner),
                    SearchPlanReviser(research_runner),
                    ScreeningExecutor(providers, policy),
                ),
                adaptive_research=Phase4ResearchComponents(
                    providers, policy, BudgetLimits(max_deep_search_rounds=80), stop_policy()
                ),
                evidence=MixedProvenancePhase5EvidenceComponents(),
                phase6=Phase6EvidenceComponents(
                    SemanticRunner(
                        StubLLMProvider(
                            {
                                "map_evidence": mixed_map_response,
                                "verify_support": mixed_verify_response,
                            }
                        )
                    ),
                    max_sources_per_mcu=100,
                ),
                phase6_fixture_adjudicator=phase7,
            )
    if delete_membership:
        assert phase7.view is not None
        failed_run = tmp_path / phase7.view.assessment_id
        assert json.loads((failed_run / "assessment_record.json").read_text())["status"] == "FAILED"
        assert not (failed_run / "report.json").exists()
        assert not (failed_run / "assessment.json").exists()
        return
    assert result.record.stage.value == "REPORTED"
    assert result.record.status.value == "COMPLETED"
    assert phase7.view is not None
    assert any(
        item.classification.scoped_coverage
        for item in (committed.comparison for committed in phase7.view.committed_comparisons)
    )
    assert any(item.decision == "FAILED_MAPPING" for item in phase7.view.candidate_outcomes)
    phase6 = result.run_dir / "phase6"
    classifications = [
        json.loads(line)
        for line in (phase6 / "precedent_classifications.jsonl").read_text().splitlines()
    ]
    relations = {item["relation"] for item in classifications}
    assert {"DIRECT_PRECEDENT", "CONTRADICTORY_EVIDENCE", "UNASSESSABLE"} <= relations
    assert any(item["scoped_coverage"] for item in classifications)
    direct = next(
        item
        for item in classifications
        if item["source_id"] == "src_lifecycle_direct" and item["relation"] == "DIRECT_PRECEDENT"
    )
    assert direct["decisive"]
    chains = [
        json.loads(line) for line in (phase6 / "verified_chains.jsonl").read_text().splitlines()
    ]
    authenticated = next(
        item for item in chains if item["source"]["source_id"] == "src_lifecycle_direct"
    )
    assert (
        authenticated["bundle"]["passages"][0]["attestation"]["parent_content_digest"]
        == (authenticated["version"]["content_hash"])
    )
    repository = SqlAlchemyEvidenceGraphRepository(
        result.run_dir / "phase5" / "evidence_graph.sqlite3"
    )
    try:
        assert any(
            edge.kind.value == "DIRECT_PRECEDENT" and edge.source_node_id == "src_lifecycle_direct"
            for edge in repository.edges()
        )
    finally:
        repository.close()
    summary = json.loads((phase6 / "phase6_result.json").read_text())
    assert any("mapping failed" in failure for failure in summary["failures"])
    assert any(item["mcu_id"].startswith("mcu_comb_") for item in classifications)
    assert (phase6 / "context_expansions.jsonl").read_text().strip()
    assert (phase6 / "patent_screenings.jsonl").read_text().strip()
    assert "PHASE7_FIXTURE_BOUNDARY" in {event.reason_code for event in sink.events}
