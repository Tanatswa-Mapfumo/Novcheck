from datetime import UTC, datetime

from novelty_harness.evidence.provenance.lineage import (
    citation_edge,
    derivation_edge,
    documentation_edge,
    found_by_edge,
    implementation_edge,
    patent_family_edge,
    provenance_edge,
    repost_edge,
    retrieval_provenance_edges,
    version_edge,
)
from novelty_harness.evidence.provenance.models import (
    LineageConfidence,
    ProvenanceRelation,
)
from novelty_harness.research.retrieval.models import RetrievalStrategy
from tests.fixtures.phase5 import make_discovery_path, make_source, phase5_provenance

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
ORIGIN = phase5_provenance("lineage-test")


def test_paper_cites_predecessor_is_confirmed_structured_lineage() -> None:
    edge = citation_edge(
        citing="src_new",
        cited="src_old",
        evidence=("crossref:reference-list", "doi:10.1/old"),
        observed_at=NOW,
        provenance=ORIGIN,
    )
    assert edge.relation == ProvenanceRelation.CITES
    assert edge.lineage_confidence == LineageConfidence.CONFIRMED
    assert edge.evidence == ("crossref:reference-list", "doi:10.1/old")


def test_blog_derives_from_press_release_stays_possible_by_default() -> None:
    edge = derivation_edge(
        derivative="src_blog",
        origin="src_release",
        evidence=("blog:footer-credit",),
        observed_at=NOW,
        provenance=ORIGIN,
    )
    assert edge.relation == ProvenanceRelation.DERIVES_FROM
    assert edge.lineage_confidence == LineageConfidence.POSSIBLE
    explicit = derivation_edge(
        derivative="src_blog",
        origin="src_release",
        evidence=("structured:basedOn",),
        observed_at=NOW,
        provenance=ORIGIN,
        confidence=LineageConfidence.CONFIRMED,
    )
    assert explicit.lineage_confidence == LineageConfidence.CONFIRMED


def test_repo_implements_paper_does_not_claim_confirmation_by_default() -> None:
    edge = implementation_edge(
        implementation="src_repo",
        specification="src_paper",
        evidence=("readme:implementation-note",),
        observed_at=NOW,
        provenance=ORIGIN,
    )
    assert edge.relation == ProvenanceRelation.IMPLEMENTS
    assert edge.lineage_confidence == LineageConfidence.POSSIBLE
    docs = documentation_edge(
        documentation="src_docs",
        artifact="src_repo",
        evidence=("repo:documentation-link",),
        observed_at=NOW,
        provenance=ORIGIN,
    )
    assert docs.relation == ProvenanceRelation.DOCUMENTS


def test_patent_family_and_version_relations_collapse_lineage_when_confirmed() -> None:
    family = patent_family_edge(
        member="src_us",
        family_primary="src_wo",
        evidence=("epo:family-id-123",),
        observed_at=NOW,
        provenance=ORIGIN,
    )
    assert family.relation == ProvenanceRelation.PATENT_FAMILY_OF
    assert family.lineage_confidence == LineageConfidence.CONFIRMED
    version = version_edge(
        version="src_journal",
        version_of="src_preprint",
        evidence=("arxiv:journal-ref",),
        observed_at=NOW,
        provenance=ORIGIN,
    )
    assert version.relation == ProvenanceRelation.VERSION_OF


def test_repost_and_found_by_edges() -> None:
    mirror = repost_edge(
        repost="src_mirror",
        original="src_original",
        evidence=("site:syndication-notice",),
        observed_at=NOW,
        provenance=ORIGIN,
    )
    assert mirror.relation == ProvenanceRelation.REPOSTS
    seed = found_by_edge(
        found="src_candidate",
        seed="src_seed",
        evidence=("openalex:CITATION_BACKWARD",),
        observed_at=NOW,
        provenance=ORIGIN,
    )
    assert seed.relation == ProvenanceRelation.FOUND_BY


def test_edges_are_deterministic_and_evidence_bound() -> None:
    first = provenance_edge(
        source_id="src_a",
        related_source_id="src_b",
        relation=ProvenanceRelation.DERIVES_FROM,
        evidence=("a", "b"),
        confidence=LineageConfidence.POSSIBLE,
        observed_at=NOW,
        provenance=ORIGIN,
    )
    second = provenance_edge(
        source_id="src_a",
        related_source_id="src_b",
        relation=ProvenanceRelation.DERIVES_FROM,
        evidence=("b", "a"),
        confidence=LineageConfidence.POSSIBLE,
        observed_at=NOW,
        provenance=ORIGIN,
    )
    assert first.edge_id == second.edge_id
    different_evidence = provenance_edge(
        source_id="src_a",
        related_source_id="src_b",
        relation=ProvenanceRelation.DERIVES_FROM,
        evidence=("a", "c"),
        confidence=LineageConfidence.POSSIBLE,
        observed_at=NOW,
        provenance=ORIGIN,
    )
    assert different_evidence.edge_id != first.edge_id


def test_expansion_paths_preserve_discovery_direction() -> None:
    seed = make_source(
        "src_seed",
        discovery_paths=(
            make_discovery_path(
                provider_source_id="W-seed", strategy=RetrievalStrategy.LEXICAL, query_id="qry_1"
            ),
        ),
    )
    backward = make_source(
        "src_backward",
        discovery_paths=(
            make_discovery_path(
                provider_source_id="W-back",
                strategy=RetrievalStrategy.CITATION_BACKWARD,
                query_id=None,
                seed_source={
                    "provider_name": "openalex",
                    "provider_source_id": "W-seed",
                },
            ),
        ),
    )
    forward = make_source(
        "src_forward",
        discovery_paths=(
            make_discovery_path(
                provider_source_id="W-forward",
                strategy=RetrievalStrategy.CITATION_FORWARD,
                query_id=None,
                seed_source={
                    "provider_name": "openalex",
                    "provider_source_id": "W-seed",
                },
            ),
        ),
    )
    related = make_source(
        "src_related",
        discovery_paths=(
            make_discovery_path(
                provider_source_id="W-related",
                strategy=RetrievalStrategy.RELATED_WORK,
                query_id=None,
                seed_source={
                    "provider_name": "openalex",
                    "provider_source_id": "W-seed",
                },
            ),
        ),
    )
    edges = retrieval_provenance_edges(
        (seed, backward, forward, related), observed_at=NOW, provenance=ORIGIN
    )
    by_key = {(edge.source_id, edge.related_source_id, edge.relation) for edge in edges}
    assert ("src_backward", "src_seed", ProvenanceRelation.FOUND_BY) in by_key
    assert ("src_backward", "src_seed", ProvenanceRelation.CITES) in by_key
    assert ("src_forward", "src_seed", ProvenanceRelation.FOUND_BY) in by_key
    assert ("src_seed", "src_forward", ProvenanceRelation.CITES) in by_key
    assert ("src_related", "src_seed", ProvenanceRelation.FOUND_BY) in by_key
    assert not any(
        edge.relation == ProvenanceRelation.CITES
        for edge in edges
        if {edge.source_id, edge.related_source_id} == {"src_seed", "src_related"}
    )
    assert all(edge.lineage_confidence == LineageConfidence.CONFIRMED for edge in edges)


def test_expansion_paths_with_unknown_seed_are_not_invented() -> None:
    orphan = make_source(
        "src_orphan",
        discovery_paths=(
            make_discovery_path(
                provider_source_id="W-orphan",
                strategy=RetrievalStrategy.CITATION_BACKWARD,
                query_id=None,
                seed_source={
                    "provider_name": "openalex",
                    "provider_source_id": "W-never-normalized",
                },
            ),
        ),
    )
    assert retrieval_provenance_edges((orphan,), observed_at=NOW, provenance=ORIGIN) == ()
