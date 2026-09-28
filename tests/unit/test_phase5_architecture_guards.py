import ast
from datetime import UTC, datetime
from pathlib import Path

import pytest

from novelty_harness.evidence.graph.models import (
    PHASE5_EDGE_KINDS,
    RESERVED_EDGE_KINDS,
    GraphEdgeKind,
)
from novelty_harness.evidence.graph.sqlalchemy_repository import (
    SqlAlchemyEvidenceGraphRepository,
)
from novelty_harness.evidence.normalization.models import SourceAccessState
from novelty_harness.evidence.passages import extraction
from novelty_harness.evidence.passages.models import PassageLocator, PassageRecord
from novelty_harness.evidence.pipeline import EvidenceNormalizationResult
from novelty_harness.evidence.provenance.clustering import (
    build_lineage_clusters,
    independent_evidence_count,
)
from novelty_harness.evidence.provenance.models import ProvenanceRelation
from novelty_harness.evidence.quality.assessment import assess_quality
from novelty_harness.evidence.quality.models import (
    EvidenceQualityAssessment,
    SourceRelevanceAssessment,
)
from tests.fixtures.phase5 import make_edge, make_source, phase5_provenance
from tests.unit.test_import_boundaries import forbidden_imports

ROOT = Path(__file__).parents[2] / "src/novelty_harness"
EVIDENCE = ROOT / "evidence"
NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)

PHASE6_ADJUDICATION_SYMBOLS = {
    "VerdictState",
    "PrecedentState",
    "SupportVerificationState",
    "FrozenAdjudication",
    "EvidenceEdge",
    "MCUFinding",
}


def _evidence_modules() -> list[Path]:
    return sorted(path for path in EVIDENCE.rglob("*.py"))


#: Phase 5's semantic substrate. The shared evidence-graph domain now also
#: supports Phase 6 verified edges under an explicit eligibility reference, so
#: the Phase 5 no-Phase-6-names guard scopes to these Phase 5-owned modules.
_PHASE5_PACKAGES = frozenset({"normalization", "passages", "provenance", "quality"})
_PHASE5_FILES = frozenset({"pipeline.py"})


def _phase5_modules() -> list[Path]:
    modules: list[Path] = []
    for path in _evidence_modules():
        relative = path.relative_to(EVIDENCE)
        if relative.parts and relative.parts[0] in _PHASE5_PACKAGES:
            modules.append(path)
        elif str(relative) in _PHASE5_FILES:
            modules.append(path)
    return modules


def test_evidence_domain_packages_do_not_import_storage_or_infrastructure() -> None:
    domain_packages = (
        "evidence/normalization",
        "evidence/passages",
        "evidence/provenance",
        "evidence/quality",
    )
    for package in domain_packages:
        for path in (ROOT / package).rglob("*.py"):
            source = path.read_text()
            assert not forbidden_imports(
                source,
                "novelty_harness." + package.replace("/", "."),
                banned=(
                    "novelty_harness.application",
                    "novelty_harness.providers",
                    "novelty_harness.runtime.artifacts",
                    "tests",
                    "sqlalchemy",
                    "httpx",
                    "openai",
                    "anthropic",
                ),
            ), path
    for name in ("models.py", "repository.py"):
        assert "sqlalchemy" not in (EVIDENCE / "graph" / name).read_text().lower()


def test_only_sqlalchemy_adapter_files_import_storage() -> None:
    for path in _evidence_modules():
        source = path.read_text()
        assert not forbidden_imports(
            source, "novelty_harness.evidence", banned=("tests", "httpx", "openai", "anthropic")
        ), path
        if path.name not in {"sqlalchemy_models.py", "sqlalchemy_repository.py", "migrations.py"}:
            assert not forbidden_imports(
                source, "novelty_harness.evidence", banned=("sqlalchemy",)
            ), path


def test_phase_5_never_constructs_reserved_adjudication_graph_edges() -> None:
    reserved_names = {kind.name for kind in RESERVED_EDGE_KINDS}
    assert reserved_names == {
        "SUPPORTS",
        "CHALLENGES",
        "DIRECT_PRECEDENT",
        "STRONG_PARTIAL_PRECEDENT",
        "COMPONENT_PRECEDENT",
        "ANALOGOUS",
        "NO_MATCH",
        "CONTRADICTS",
    }
    for path in _phase5_modules():
        if path.name == "models.py":
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "GraphEdgeKind"
                and node.attr in reserved_names
            ):
                raise AssertionError(f"{path} constructs reserved edge kind {node.attr}")


def test_phase_5_contains_no_phase_6_adjudication_symbols() -> None:
    for path in _phase5_modules():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in PHASE6_ADJUDICATION_SYMBOLS:
                raise AssertionError(f"{path} references Phase 6 symbol {node.id}")


def test_repository_interface_returns_domain_models_not_orm_rows() -> None:
    repository = SqlAlchemyEvidenceGraphRepository()
    nodes, edges = (
        (
            make_source("src_alpha"),
            make_source("src_beta"),
        ),
        (make_edge("src_alpha", "src_beta"),),
    )
    from novelty_harness.evidence.graph.retrieval_mapping import (
        discovery_graph,
        provenance_graph_edges,
    )

    graph_nodes, _ = discovery_graph(
        (nodes[0], nodes[1]), observed_at=NOW, provenance=phase5_provenance()
    )
    repository.upsert(nodes=graph_nodes, edges=provenance_graph_edges(edges))
    loaded_node = repository.get_node("src_alpha")
    loaded_edge = repository.get_edge(provenance_graph_edges(edges)[0].edge_id)
    assert loaded_node is not None and loaded_edge is not None
    assert type(loaded_node).__module__ == "novelty_harness.evidence.graph.models"
    assert type(loaded_edge).__module__ == "novelty_harness.evidence.graph.models"
    assert not hasattr(loaded_node, "_sa_instance_state")
    repository.close()


def test_raw_source_count_is_never_independent_evidence_count() -> None:
    release = make_source("src_release")
    derivatives = tuple(make_source(f"src_page_{index:02d}") for index in range(50))
    edges = tuple(
        make_edge(
            derivative.source_id,
            release.source_id,
            relation=ProvenanceRelation.DERIVES_FROM,
        )
        for derivative in derivatives
    )
    clusters = build_lineage_clusters((release, *derivatives), edges)
    assert len(clusters[0].source_ids) == 51
    assert independent_evidence_count(clusters) == 1
    summary_fields = EvidenceNormalizationResult.__dataclass_fields__
    assert "lineage_clusters" in summary_fields
    assert not summary_fields["sources"].name == "independent_evidence_count"


def test_quality_and_relevance_remain_disjoint_contracts() -> None:
    quality_fields = set(EvidenceQualityAssessment.model_fields)
    relevance_fields = set(SourceRelevanceAssessment.model_fields)
    assert not quality_fields & {"relevance", "relevance_strength"}
    assert not relevance_fields & {"tier", "evidence_quality"}
    assert (
        "relevance"
        not in assess_quality.__code__.co_varnames[: assess_quality.__code__.co_argcount]
    )


def test_metadata_snippets_cannot_become_full_text_passages() -> None:
    assert not hasattr(extraction, "extract_snippet")
    assert not hasattr(extraction, "extract_metadata")
    with pytest.raises(ValueError):
        PassageRecord.model_validate(
            {
                "passage_id": "pass_snippet",
                "source_id": "src_x",
                "text": "Search snippet text",
                "content_hash": "0" * 64,
                "access_state": SourceAccessState.METADATA_ONLY,
                "locator": PassageLocator(kind="RESOLVED_CONTENT"),
                "observed_at": NOW,
                "provenance": phase5_provenance(),
            }
        )


def test_default_suite_remains_network_blocked(pytestconfig) -> None:
    assert pytestconfig.getoption("disable_socket") is True
    assert not pytestconfig.getoption("allow_hosts")


def test_graph_edge_kinds_are_exactly_phase_5_plus_reserved() -> None:
    assert PHASE5_EDGE_KINDS | RESERVED_EDGE_KINDS == frozenset(GraphEdgeKind)
    assert not PHASE5_EDGE_KINDS & RESERVED_EDGE_KINDS
