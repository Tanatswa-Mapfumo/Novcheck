from datetime import UTC, datetime

from novelty_harness.domain.enums import EvidenceFamily
from novelty_harness.domain.idea import ArtifactProvenance
from novelty_harness.evidence.normalization.identifiers import canonical_source_identity
from novelty_harness.evidence.normalization.models import (
    CanonicalIdentifiers,
    ResolvedContent,
    SourceAccessState,
    SourceType,
)
from novelty_harness.evidence.normalization.source_normalizer import (
    normalize_candidate_cluster,
)
from novelty_harness.evidence.normalization.versions import compare_versions
from novelty_harness.ports.models import SourceRef
from novelty_harness.research.fusion.clustering import CandidateCluster, cluster_candidates
from novelty_harness.research.retrieval.models import RetrievalCandidate, RetrievalStrategy

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
ORIGIN = ArtifactProvenance(kind="implemented", component="source-normalizer-test", detail="test")


def candidate(
    provider: str,
    provider_source_id: str,
    *,
    title: str | None = "Thermal feedback controller",
    url: str | None = None,
    metadata: dict[str, object] | None = None,
    strategy: RetrievalStrategy = RetrievalStrategy.LEXICAL,
    query_id: str | None = "qry_1",
    mcu_id: str | None = "mcu_1",
    rank: int = 1,
    seed: SourceRef | None = None,
) -> RetrievalCandidate:
    return RetrievalCandidate(
        candidate_key=f"{provider}:{provider_source_id}",
        source=SourceRef(
            provider_name=provider,
            provider_source_id=provider_source_id,
            canonical_url=url,
            title=title,
        ),
        mcu_id=mcu_id,
        evidence_family=EvidenceFamily.SCHOLARLY,
        provider_name=provider,
        strategy=strategy,
        query_id=query_id,
        local_rank=rank,
        discovered_at=NOW,
        raw_metadata=metadata or {},
        seed_source=seed,
    )


def one_cluster(*candidates: RetrievalCandidate) -> CandidateCluster:
    clusters = cluster_candidates(candidates)
    assert len(clusters) == 1, [c.candidate_key for c in clusters]
    return clusters[0]


def three_dof_provider_candidates() -> tuple[
    RetrievalCandidate, RetrievalCandidate, RetrievalCandidate
]:
    return (
        candidate(
            "openalex",
            "https://openalex.org/W123",
            url="https://openalex.org/W123",
            metadata={"doi": "https://doi.org/10.1234/shared", "publication_date": "2020-01-01"},
        ),
        candidate(
            "crossref",
            "10.1234/shared",
            metadata={"doi": "10.1234/shared", "type": "journal-article"},
        ),
        candidate(
            "semantic_scholar",
            "a" * 40,
            url=f"https://www.semanticscholar.org/paper/{'a' * 40}",
            metadata={"externalIds": {"DOI": "10.1234/shared"}, "publicationDate": "2020-01-01"},
        ),
    )


async def test_same_doi_from_three_providers_is_one_source_with_all_paths() -> None:
    cluster = one_cluster(*three_dof_provider_candidates())
    result = await normalize_candidate_cluster(cluster, observed_at=NOW, provenance=ORIGIN)
    assert result.source.identifiers.doi == "10.1234/shared"
    assert {path.provider_name for path in result.source.discovery_paths} == {
        "openalex",
        "crossref",
        "semantic_scholar",
    }
    assert set(result.unresolved_fields) <= {"content"}
    assert result.merged_candidate_keys == (
        cluster.candidate_key,
        "crossref:10.1234/shared",
        "openalex:https://openalex.org/W123",
        f"semantic_scholar:{'a' * 40}",
    )
    assert result.source.discovery_queries == ("qry_1",)
    assert result.source.source_type == SourceType.PAPER


async def test_conflicting_titles_and_authors_are_retained_as_conflicts() -> None:
    cluster = one_cluster(
        candidate(
            "openalex",
            "https://openalex.org/W1",
            title="Thermal feedback controller",
            metadata={
                "doi": "10.1234/shared",
                "authors": [{"author": {"display_name": "Ada Example"}}],
                "publication_date": "2020-01-01",
            },
        ),
        candidate(
            "crossref",
            "10.1234/shared",
            title="A different unrelated title",
            metadata={"doi": "10.1234/shared", "publication_date": "2021-05-05"},
        ),
    )
    result = await normalize_candidate_cluster(cluster, observed_at=NOW, provenance=ORIGIN)
    assert any(conflict.startswith("title:") for conflict in result.conflicts)
    assert any(conflict.startswith("dates.publication_date:") for conflict in result.conflicts)
    assert "title" in result.unresolved_fields
    assert "dates.publication_date" in result.unresolved_fields
    # Crossref metadata has precedence for bibliographic fields; the losing
    # title is retained in the conflict rather than silently discarded.
    assert result.source.canonical_title == "A different unrelated title"


async def test_metadata_only_source_never_invents_content_or_version() -> None:
    cluster = one_cluster(
        candidate(
            "crossref",
            "10.1234/meta",
            metadata={"doi": "10.1234/meta"},
        )
    )
    result = await normalize_candidate_cluster(cluster, observed_at=NOW, provenance=ORIGIN)
    assert result.source.access_state == SourceAccessState.METADATA_ONLY
    assert result.source.content_hash is not None
    assert result.version is None
    assert any("metadata-only" in item for item in result.source.limitations)
    assert "content" in result.unresolved_fields


async def test_blocked_full_text_stays_blocked_with_limitations() -> None:
    cluster = one_cluster(
        candidate("crossref", "10.1234/blocked", metadata={"doi": "10.1234/blocked"})
    )
    resolved = ResolvedContent(
        access_state=SourceAccessState.BLOCKED,
        limitations=("Publisher returned 403 after two attempts",),
    )
    result = await normalize_candidate_cluster(
        cluster, observed_at=NOW, provenance=ORIGIN, resolved=resolved
    )
    assert result.source.access_state == SourceAccessState.BLOCKED
    assert result.version is None
    assert "Publisher returned 403 after two attempts" in result.source.limitations


async def test_github_repository_source_gets_repository_identity() -> None:
    cluster = one_cluster(
        candidate(
            "github",
            "42",
            title="example/thermal-controller",
            url="https://github.com/example/thermal-controller",
            metadata={"created_at": "2019-04-01T00:00:00Z"},
        )
    )
    result = await normalize_candidate_cluster(cluster, observed_at=NOW, provenance=ORIGIN)
    assert result.source.source_type == SourceType.REPOSITORY
    assert result.source.identifiers.repository == "example/thermal-controller"
    expected = canonical_source_identity(
        CanonicalIdentifiers(repository="example/thermal-controller")
    )
    assert result.source.source_id == expected.source_id


async def test_same_title_with_different_dois_stays_distinct() -> None:
    first = one_cluster(
        candidate("crossref", "10.1234/one", title="Shared title", metadata={"doi": "10.1234/one"})
    )
    second = one_cluster(
        candidate("crossref", "10.1234/two", title="Shared title", metadata={"doi": "10.1234/two"})
    )
    left = await normalize_candidate_cluster(first, observed_at=NOW, provenance=ORIGIN)
    right = await normalize_candidate_cluster(second, observed_at=NOW, provenance=ORIGIN)
    assert left.source.source_id != right.source.source_id
    assert left.source.canonical_title == right.source.canonical_title


async def test_abstract_only_resolution_builds_abstract_version() -> None:
    cluster = one_cluster(
        candidate(
            "arxiv",
            "2001.00001v3",
            metadata={
                "arxiv_id": "2001.00001v3",
                "publication_date": "2020-02-02",
            },
        )
    )
    abstract = "We present a thermal feedback controller with exact passages."
    resolved = ResolvedContent(access_state=SourceAccessState.ABSTRACT_ONLY, abstract=abstract)
    result = await normalize_candidate_cluster(
        cluster, observed_at=NOW, provenance=ORIGIN, resolved=resolved
    )
    assert result.source.access_state == SourceAccessState.ABSTRACT_ONLY
    assert result.source.source_type == SourceType.PREPRINT
    assert result.version is not None
    assert result.version.version_label == "v3"
    assert result.version.access_state == SourceAccessState.ABSTRACT_ONLY
    assert result.version.content_hash == result.source.content_hash
    assert result.source.identifiers.arxiv_id == "2001.00001"


async def test_conflicting_identifier_values_cannot_establish_identity() -> None:
    cluster = one_cluster(
        candidate(
            "crossref",
            "10.1234/one",
            title="Conflicted record",
            metadata={"doi": "10.1234/one", "externalIds": {"DOI": "10.1234/two"}},
        )
    )
    result = await normalize_candidate_cluster(cluster, observed_at=NOW, provenance=ORIGIN)
    assert result.source.identifiers.doi is None
    assert "doi" in result.unresolved_fields
    assert any(conflict.startswith("identifiers.doi:") for conflict in result.conflicts)
    assert not result.source.has_stable_identity()


async def test_unstable_identity_records_scoped_limitation() -> None:
    cluster = one_cluster(
        candidate(
            "openalex",
            "W999",
            title="Anonymous unpublished note",
            metadata={"publication_date": "2018-01-01"},
        )
    )
    result = await normalize_candidate_cluster(cluster, observed_at=NOW, provenance=ORIGIN)
    assert result.source.identifiers.openalex_id == "W999"
    assert result.source.has_stable_identity()
    limited = one_cluster(
        candidate("fixture-search", "opaque-1", title="No identifiers anywhere", metadata={})
    )
    unstable = await normalize_candidate_cluster(limited, observed_at=NOW, provenance=ORIGIN)
    assert not unstable.source.has_stable_identity()
    assert "identity" in unstable.unresolved_fields
    assert any("scoped to discovered records" in item for item in unstable.conflicts)


async def test_discovery_paths_dedupe_repeated_identical_observations() -> None:
    cluster = one_cluster(
        candidate(
            "openalex",
            "https://openalex.org/W1",
            title="Repeat discovery",
            rank=5,
            metadata={"doi": "10.1234/repeat", "publication_date": "2020-01-01"},
        ),
        candidate(
            "openalex",
            "https://openalex.org/W1",
            title="Repeat discovery",
            rank=2,
            strategy=RetrievalStrategy.SEMANTIC,
            query_id="qry_2",
            metadata={"doi": "10.1234/repeat", "publication_date": "2020-01-01"},
        ),
    )
    result = await normalize_candidate_cluster(cluster, observed_at=NOW, provenance=ORIGIN)
    assert {(path.strategy, path.query_id) for path in result.source.discovery_paths} == {
        (RetrievalStrategy.LEXICAL, "qry_1"),
        (RetrievalStrategy.SEMANTIC, "qry_2"),
    }
    assert result.source.discovery_queries == ("qry_1", "qry_2")


async def test_content_change_produces_new_version_not_overwrite() -> None:
    cluster = one_cluster(
        candidate(
            "arxiv",
            "2001.00001v1",
            metadata={"arxiv_id": "2001.00001v1", "publication_date": "2020-01-01"},
        )
    )
    first = await normalize_candidate_cluster(
        cluster,
        observed_at=NOW,
        provenance=ORIGIN,
        resolved=ResolvedContent(access_state=SourceAccessState.FULL_TEXT, text="first text"),
    )
    second = await normalize_candidate_cluster(
        cluster,
        observed_at=NOW,
        provenance=ORIGIN,
        resolved=ResolvedContent(access_state=SourceAccessState.FULL_TEXT, text="changed text"),
    )
    assert first.version is not None and second.version is not None
    assert first.source.source_id == second.source.source_id
    assert first.version.version_id != second.version.version_id
    comparison = compare_versions((first.version,), second.version)
    assert comparison.relation == "CONTENT_CHANGED"
    assert comparison.predecessor_version_id == first.version.version_id
    assert comparison.chronology_certain
