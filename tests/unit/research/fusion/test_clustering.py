from novelty_harness.ports.models import SourceRef
from novelty_harness.research.fusion.clustering import cluster_candidates, rekey_lists
from novelty_harness.research.fusion.rrf import reciprocal_rank_fusion
from tests.unit.research.retrieval.test_models import candidate


def record(provider, identity, **updates):
    data = dict(
        candidate_key=provider + ":" + identity,
        provider_name=provider,
        source=SourceRef(provider_name=provider, provider_source_id=identity, title="Shared title"),
    )
    return candidate(**{**data, **updates})


def test_same_doi_across_three_providers_clusters_without_losing_paths_or_dates():
    records = [
        record(
            "openalex",
            "W1",
            raw_metadata={
                "doi": "https://doi.org/10.1234/example",
                "publication_date": "2000-01-02",
            },
        ),
        record(
            "crossref",
            "10.1234/example",
            query_id="qry_crossref",
            raw_metadata={"doi": "10.1234/EXAMPLE", "publication_date": "2001-02-03"},
        ),
        record(
            "semantic_scholar",
            "paper1",
            query_id="qry_s2",
            strategy="SEMANTIC",
            raw_metadata={"externalIds": {"DOI": "10.1234/example"}},
        ),
    ]
    clusters = cluster_candidates(records)
    assert len(clusters) == 1
    c = clusters[0]
    assert len(c.discoveries) == 3 and len(c.source_refs) == 3
    assert c.providers == frozenset({"openalex", "crossref", "semantic_scholar"})
    assert c.earliest_observed_date.isoformat() == "2000-01-02"
    assert c.latest_observed_date.isoformat() == "2001-02-03"
    assert "publication_date" in c.metadata_conflicts
    lists = {str(i): [r] for i, r in enumerate(records)}
    fused = reciprocal_rank_fusion(rekey_lists(lists, clusters))
    assert len(fused) == 1 and len(fused[0].discoveries) == 3
    assert fused[0].rrf_score == 3 / 61


def test_title_similarity_and_distinct_dois_do_not_merge():
    a = record("openalex", "W1", raw_metadata={"doi": "10.1234/one"})
    b = record("crossref", "10.1234/two", raw_metadata={"doi": "10.1234/two"})
    assert len(cluster_candidates([a, b])) == 2
    assert len(cluster_candidates([record("openalex", "W1"), record("crossref", "paper2")])) == 2


def test_forks_same_owner_and_parent_are_not_work_identity():
    a = record(
        "github",
        "1",
        evidence_family="SOFTWARE",
        raw_metadata={"owner": {"id": 2}, "parent": {"id": 3}},
    )
    b = record(
        "github",
        "4",
        evidence_family="SOFTWARE",
        raw_metadata={"owner": {"id": 2}, "parent": {"id": 3}},
    )
    assert len(cluster_candidates([a, b])) == 2


def test_identical_canonical_url_can_link_without_title_guessing():
    a = record(
        "openalex",
        "W1",
        source=SourceRef(
            provider_name="openalex",
            provider_source_id="W1",
            canonical_url="https://example.org/work/1",
        ),
    )
    b = record(
        "crossref",
        "paper2",
        source=SourceRef(
            provider_name="crossref",
            provider_source_id="paper2",
            canonical_url="https://example.org/work/1",
        ),
    )
    assert len(cluster_candidates([a, b])) == 1


def test_exact_bibliographic_fallback_requires_authors_and_full_date():
    meta = {"authors": [{"name": "A. Example"}], "publication_date": "2000-01-02"}
    a = record("openalex", "W1", raw_metadata=meta)
    b = record("crossref", "paper2", raw_metadata=meta)
    assert len(cluster_candidates([a, b])) == 1
    assert (
        len(
            cluster_candidates(
                [a, b.model_copy(update={"raw_metadata": {"publication_date": "2000-01-02"}})]
            )
        )
        == 2
    )


def test_conflicting_explicit_identifiers_cannot_be_bridged_by_a_shared_url():
    shared = "https://example.org/work"
    a = record(
        "openalex",
        "W1",
        source=SourceRef(provider_name="openalex", provider_source_id="W1", canonical_url=shared),
        raw_metadata={"doi": "10.1234/one"},
    )
    b = record(
        "crossref",
        "10.1234/two",
        source=SourceRef(
            provider_name="crossref", provider_source_id="10.1234/two", canonical_url=shared
        ),
        raw_metadata={"doi": "10.1234/two"},
    )
    assert len(cluster_candidates([a, b])) == 2
