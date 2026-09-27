"""Normalize Phase 4 candidate clusters into canonical source/version records.

Policy:

- stable identifiers and primary metadata are preferred; titles never merge;
- every disagreement is retained as a conflict and an unresolved field;
- all Phase 4 discovery paths survive on the canonical source;
- access state reflects what was actually resolved, never what was hoped for;
- no source-to-MCU equivalence reasoning happens here.
"""

from collections.abc import Sequence
from datetime import date, datetime

from pydantic import JsonValue

from novelty_harness.domain.base import UTCDateTime
from novelty_harness.domain.enums import EvidenceFamily
from novelty_harness.domain.evidence import SourceDates
from novelty_harness.domain.idea import ArtifactProvenance
from novelty_harness.evidence.normalization.identifiers import (
    canonical_source_identity,
    merge_identifiers,
    normalize_arxiv_id,
    normalize_doi,
    normalize_openalex_id,
    normalize_patent_number,
    normalize_repository,
    normalize_semantic_scholar_id,
    normalize_url,
)
from novelty_harness.evidence.normalization.models import (
    CanonicalIdentifiers,
    DiscoveryPath,
    ResolvedContent,
    SourceAccessState,
    SourceNormalizationResult,
    SourceRecord,
    SourceType,
    SourceVersionRecord,
    VersionKind,
)
from novelty_harness.evidence.normalization.versions import build_version_record
from novelty_harness.evidence.passages.hashing import text_hash
from novelty_harness.research.expansion.chronology import capture_chronology
from novelty_harness.research.fusion.clustering import CandidateCluster
from novelty_harness.research.retrieval.models import RetrievalCandidate, mechanism_for
from novelty_harness.runtime.tracing.hashing import canonical_hash

_PROVIDER_PRECEDENCE = ("crossref", "openalex", "semantic_scholar", "arxiv", "github")

_SOURCE_DATE_FIELDS = (
    "publication_date",
    "first_public_version",
    "repository_created_at",
    "first_release_date",
    "patent_priority_date",
    "patent_publication_date",
    "product_launch_date",
    "archive_capture_date",
)

_METADATA_TYPES: dict[str, SourceType] = {
    "journal-article": SourceType.PAPER,
    "proceedings-article": SourceType.PAPER,
    "review-article": SourceType.PAPER,
    "article": SourceType.PAPER,
    "posted-content": SourceType.PREPRINT,
    "preprint": SourceType.PREPRINT,
    "dataset": SourceType.DATASET,
    "report": SourceType.REPORT,
    "standard": SourceType.STANDARD,
    "book": SourceType.OTHER,
    "book-chapter": SourceType.OTHER,
    "dissertation": SourceType.REPORT,
    "software": SourceType.REPOSITORY,
}


def _provider_rank(name: str) -> tuple[int, str]:
    if name in _PROVIDER_PRECEDENCE:
        return (_PROVIDER_PRECEDENCE.index(name), name)
    return (len(_PROVIDER_PRECEDENCE), name)


def _ordered(candidates: Sequence[RetrievalCandidate]) -> list[RetrievalCandidate]:
    return sorted(
        candidates,
        key=lambda candidate: (
            *_provider_rank(candidate.provider_name),
            candidate.source.provider_source_id,
            candidate.strategy.value,
            candidate.query_id or "",
            candidate.candidate_key,
        ),
    )


def _strings(raw: dict[str, JsonValue], key: str) -> list[str]:
    value = raw.get(key)
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if isinstance(value, list):
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return []


def _other_identifiers(raw: dict[str, JsonValue]) -> dict[str, str]:
    external = raw.get("externalIds")
    if not isinstance(external, dict):
        return {}
    other: dict[str, str] = {}
    for key, name in (("PubMed", "pmid"), ("MAG", "mag")):
        value = external.get(key)
        if isinstance(value, str) and value.strip():
            other[name] = value.strip()
    return other


def _patent_numbers(raw: dict[str, JsonValue]) -> list[str]:
    observed: list[str] = []
    for value in [*_strings(raw, "patent_number"), *_strings(raw, "patent_numbers")]:
        number = normalize_patent_number(value)
        if number is not None:
            observed.append(number)
    return observed


def identifier_observations(candidate: RetrievalCandidate) -> tuple[CanonicalIdentifiers, ...]:
    """Every separately-sourced identifier observation from one candidate.

    Observations stay separate so intra-candidate disagreements surface as
    conflicts instead of being silently resolved.
    """

    raw = candidate.raw_metadata
    observed: list[CanonicalIdentifiers] = []

    doi_values: list[JsonValue] = [raw.get("doi")]
    external = raw.get("externalIds")
    if isinstance(external, dict):
        doi_values.append(external.get("DOI"))
        arxiv = external.get("ArXiv")
        if isinstance(arxiv, str) and (identity := normalize_arxiv_id(arxiv)) is not None:
            observed.append(CanonicalIdentifiers(arxiv_id=identity.base_id))
    if candidate.provider_name == "crossref":
        doi_values.append(candidate.source.provider_source_id)
    for value in doi_values:
        if isinstance(value, str) and (doi := normalize_doi(value)) is not None:
            observed.append(CanonicalIdentifiers(doi=doi))

    if candidate.provider_name == "openalex":
        openalex = normalize_openalex_id(candidate.source.provider_source_id)
        if openalex is not None:
            observed.append(CanonicalIdentifiers(openalex_id=openalex))
    if candidate.provider_name == "semantic_scholar":
        paper_id = normalize_semantic_scholar_id(candidate.source.provider_source_id)
        if paper_id is not None:
            observed.append(CanonicalIdentifiers(semantic_scholar_id=paper_id))
    semantic = raw.get("paperId")
    if isinstance(semantic, str) and (paper_id := normalize_semantic_scholar_id(semantic)):
        observed.append(CanonicalIdentifiers(semantic_scholar_id=paper_id))
    if candidate.provider_name == "arxiv":
        identity = normalize_arxiv_id(candidate.source.provider_source_id)
        if identity is not None:
            observed.append(CanonicalIdentifiers(arxiv_id=identity.base_id))
    repository = normalize_repository(candidate.source.canonical_url or "")
    if repository is None and candidate.provider_name == "github":
        repository = normalize_repository(candidate.source.provider_source_id)
    if repository is not None:
        observed.append(CanonicalIdentifiers(repository=repository))

    patents = _patent_numbers(raw)
    if patents:
        observed.append(CanonicalIdentifiers(patent_numbers=tuple(sorted(set(patents)))))

    other = _other_identifiers(raw)
    if other:
        observed.append(CanonicalIdentifiers(other=other))
    return tuple(observed)


def candidate_urls(candidate: RetrievalCandidate) -> tuple[str, ...]:
    values: list[JsonValue] = [
        candidate.source.canonical_url,
        candidate.raw_metadata.get("url"),
        candidate.raw_metadata.get("html_url"),
    ]
    return tuple(
        sorted(
            {url for value in values if isinstance(value, str) and (url := normalize_url(value))}
        )
    )


def _title(ordered: Sequence[RetrievalCandidate]) -> tuple[str | None, list[str]]:
    grouped: dict[str, set[str]] = {}
    chosen: str | None = None
    for candidate in ordered:
        title = candidate.source.title
        if title is None or not title.strip():
            continue
        display = " ".join(title.split())
        grouped.setdefault(display.casefold(), set()).add(display)
        if chosen is None:
            chosen = display
    conflicts: list[str] = []
    if len(grouped) > 1:
        observed = sorted({display for displays in grouped.values() for display in displays})
        conflicts.append("title: " + " | ".join(observed))
    return chosen, conflicts


def _author_names(value: JsonValue) -> list[str]:
    if not isinstance(value, list):
        return []
    names: list[str] = []
    for item in value:
        name: JsonValue = None
        if isinstance(item, str):
            name = item
        elif isinstance(item, dict):
            name = item.get("name")
            if not isinstance(name, str):
                author = item.get("author")
                if isinstance(author, dict):
                    name = author.get("display_name")
            if not isinstance(name, str):
                name = item.get("display_name")
        if isinstance(name, str) and name.strip():
            names.append(" ".join(name.split()))
    return names


def _authors(ordered: Sequence[RetrievalCandidate]) -> tuple[list[str], list[str]]:
    per_provider: dict[str, frozenset[str]] = {}
    chosen: list[str] = []
    for candidate in ordered:
        names = _author_names(candidate.raw_metadata.get("authors"))
        if not names:
            continue
        normalized = frozenset(" ".join(name.casefold().split()) for name in names)
        per_provider[candidate.provider_name] = normalized
        if not chosen:
            chosen = names
    conflicts: list[str] = []
    values = list(per_provider.values())
    if len(values) > 1:
        first, *rest = values
        if not first.intersection(*rest):
            observed = sorted({name for item in values for name in item})
            conflicts.append("authors: " + " | ".join(observed))
    return chosen, conflicts


def _dates(ordered: Sequence[RetrievalCandidate]) -> tuple[SourceDates, list[str]]:
    per_field: dict[str, set[date]] = {}
    for candidate in ordered:
        chronology = capture_chronology(candidate)
        for field in _SOURCE_DATE_FIELDS:
            value = getattr(chronology, field)
            if isinstance(value, datetime):
                value = value.date()
            if isinstance(value, date):
                per_field.setdefault(field, set()).add(value)
    conflicts: list[str] = []
    for field, values in sorted(per_field.items()):
        if len(values) > 1:
            conflicts.append(
                f"dates.{field}: " + " | ".join(sorted(value.isoformat() for value in values))
            )
    selected: dict[str, date] = {field: min(values) for field, values in per_field.items()}
    return SourceDates.model_validate(selected), conflicts


def _languages(ordered: Sequence[RetrievalCandidate]) -> list[str]:
    values: list[str] = []
    for candidate in ordered:
        raw = candidate.raw_metadata
        values.extend(_strings(raw, "language"))
        values.extend(_strings(raw, "languages"))
    return sorted({value.casefold() for value in values})


def _source_type(
    ordered: Sequence[RetrievalCandidate], identifiers: CanonicalIdentifiers
) -> SourceType:
    if identifiers.repository:
        return SourceType.REPOSITORY
    if identifiers.patent_numbers:
        return SourceType.PATENT
    for candidate in ordered:
        raw = candidate.raw_metadata
        types = [raw.get("type"), raw.get("publicationTypes")]
        for value in types:
            if isinstance(value, str) and (mapped := _METADATA_TYPES.get(value.casefold())):
                return mapped
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and (mapped := _METADATA_TYPES.get(item.casefold())):
                        return mapped
        if candidate.provider_name == "github":
            return SourceType.REPOSITORY
    if identifiers.arxiv_id:
        return SourceType.PREPRINT
    if identifiers.doi:
        return SourceType.PAPER
    return SourceType.WEB


def _version_label(ordered: Sequence[RetrievalCandidate]) -> str | None:
    for candidate in ordered:
        raw = candidate.raw_metadata
        values: list[JsonValue] = [raw.get("arxiv_id"), raw.get("arxivId")]
        external = raw.get("externalIds")
        if isinstance(external, dict):
            values.append(external.get("ArXiv"))
        if candidate.provider_name == "arxiv":
            values.append(candidate.source.provider_source_id)
        for value in values:
            if isinstance(value, str):
                identity = normalize_arxiv_id(value)
                if identity is not None and identity.version is not None:
                    return f"v{identity.version}"
    return None


def _version_kind(source_type: SourceType) -> VersionKind:
    return {
        SourceType.PREPRINT: VersionKind.PREPRINT,
        SourceType.PAPER: VersionKind.JOURNAL,
        SourceType.PATENT: VersionKind.PATENT_PUBLICATION,
        SourceType.REPOSITORY: VersionKind.REPOSITORY_RELEASE,
    }.get(source_type, VersionKind.GENERIC)


def merge_paths(paths: Sequence[DiscoveryPath]) -> tuple[DiscoveryPath, ...]:
    """Collapse identical retrieval paths while retaining rank/time best values."""

    merged: dict[tuple[str, ...], DiscoveryPath] = {}
    for path in paths:
        key = path.path_key()
        previous = merged.get(key)
        if previous is None:
            merged[key] = path
            continue
        ranks = [rank for rank in (previous.local_rank, path.local_rank) if rank is not None]
        merged[key] = previous.model_copy(
            update={
                "local_rank": min(ranks) if ranks else None,
                "discovered_at": min(previous.discovered_at, path.discovered_at),
            }
        )
    return tuple(merged[key] for key in sorted(merged))


def merge_discovery_paths(
    candidates: Sequence[RetrievalCandidate],
) -> tuple[DiscoveryPath, ...]:
    """Collapse identical retrieval paths while retaining rank/time best values."""

    return merge_paths(
        [
            DiscoveryPath(
                provider_name=candidate.provider_name,
                provider_source_id=candidate.source.provider_source_id,
                strategy=candidate.strategy,
                mechanism=mechanism_for(candidate.strategy),
                evidence_family=candidate.evidence_family,
                query_id=candidate.query_id,
                search_run_id=None,
                seed_source=candidate.seed_source,
                mcu_id=candidate.mcu_id,
                local_rank=candidate.local_rank,
                discovered_at=candidate.discovered_at,
            )
            for candidate in candidates
        ]
    )


def _ordered_unique(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _metadata_bundle(
    *,
    title: str | None,
    identifiers: CanonicalIdentifiers,
    canonical_url: str | None,
    authors: Sequence[str],
    dates: SourceDates,
) -> dict[str, JsonValue]:
    return {
        "title": title,
        "identifiers": identifiers.model_dump(mode="json"),
        "canonical_url": canonical_url,
        "authors": list(authors),
        "dates": dates.model_dump(mode="json"),
    }


async def normalize_candidate_cluster(
    cluster: CandidateCluster,
    *,
    observed_at: UTCDateTime,
    provenance: ArtifactProvenance,
    resolved: ResolvedContent | None = None,
) -> SourceNormalizationResult:
    """Build one canonical source (and newest version) from a Phase 4 cluster.

    ``resolved`` describes what content resolution actually returned. ``None``
    means resolution was never attempted and the source stays metadata-only.
    """

    ordered = _ordered(cluster.discoveries)
    observations = [
        observation for candidate in ordered for observation in identifier_observations(candidate)
    ]
    merge = merge_identifiers(observations)
    identifiers = merge.identifiers
    urls = tuple(sorted({url for candidate in ordered for url in candidate_urls(candidate)}))
    identity = canonical_source_identity(
        identifiers,
        urls=urls,
        discovery_ids=[(c.provider_name, c.source.provider_source_id) for c in ordered],
    )

    title, title_conflicts = _title(ordered)
    authors, author_conflicts = _authors(ordered)
    dates, date_conflicts = _dates(ordered)
    languages = _languages(ordered)
    source_type = _source_type(ordered, identifiers)

    families = _ordered_unique([c.evidence_family.value for c in ordered])
    queries = _ordered_unique([c.query_id for c in ordered if c.query_id is not None])

    conflicts: list[str] = []
    unresolved: list[str] = []
    if not identity.stable:
        conflicts.append(
            "identity: no globally stable identifier; identity is scoped to discovered records"
        )
        unresolved.append("identity")
    covered = {
        "doi",
        "publication_date",
        "publicationDate",
        "authors",
        "title",
        "provider_local_score",
    }
    uncovered = [key for key in cluster.metadata_conflicts if key not in covered]
    conflicts.extend(f"metadata.{key}: providers disagree" for key in uncovered)
    unresolved.extend(f"metadata.{key}" for key in uncovered)
    conflicts.extend(title_conflicts)
    if title_conflicts:
        unresolved.append("title")
    conflicts.extend(author_conflicts)
    if author_conflicts:
        unresolved.append("authors")
    conflicts.extend(date_conflicts)
    unresolved.extend(conflict.split(":", 1)[0] for conflict in date_conflicts)
    conflicts.extend(
        f"identifiers.{conflict.field}: {' | '.join(conflict.observed_values)}"
        for conflict in merge.conflicts
    )
    unresolved.extend(merge.unresolved)

    canonical_url = next(
        (url for candidate in ordered if (url := candidate.source.canonical_url)),
        None,
    )
    if canonical_url is not None:
        canonical_url = normalize_url(canonical_url)
    metadata_bundle = _metadata_bundle(
        title=title,
        identifiers=identifiers,
        canonical_url=canonical_url,
        authors=authors,
        dates=dates,
    )

    limitations: list[str] = []
    access_state = SourceAccessState.METADATA_ONLY
    version: SourceVersionRecord | None = None
    if resolved is None:
        content_hash = canonical_hash(metadata_bundle)
        limitations.append("Content was not resolved; metadata-only record")
        unresolved.append("content")
    else:
        limitations.extend(resolved.limitations)
        if resolved.access_state in {SourceAccessState.FULL_TEXT, SourceAccessState.ABSTRACT_ONLY}:
            payload = resolved.text if resolved.text is not None else resolved.abstract
            assert payload is not None
            content_hash = text_hash(payload)
        else:
            content_hash = canonical_hash(metadata_bundle)
            unresolved.append("content")
        access_state = resolved.access_state
        if resolved.access_state in {SourceAccessState.FULL_TEXT, SourceAccessState.ABSTRACT_ONLY}:
            version_label = _version_label(ordered)
            version = build_version_record(
                source_id=identity.source_id,
                content_hash=content_hash,
                access_state=access_state,
                observed_at=observed_at,
                provenance=provenance,
                version_kind=_version_kind(source_type),
                version_label=version_label,
                identifiers=identifiers,
                published_date=dates.publication_date or dates.first_public_version,
                limitations=tuple(limitations),
            )

    source = SourceRecord(
        source_id=identity.source_id,
        canonical_title=title or identity.value,
        source_type=source_type,
        canonical_url=canonical_url,
        identifiers=identifiers,
        authors_or_owners=tuple(authors),
        dates=dates,
        languages=tuple(languages),
        access_state=access_state,
        evidence_families=tuple(EvidenceFamily(value) for value in families),
        content_hash=content_hash,
        discovery_queries=tuple(queries),
        discovery_paths=merge_discovery_paths(ordered),
        limitations=tuple(dict.fromkeys(limitations)),
        provenance=provenance,
    )
    return SourceNormalizationResult(
        source=source,
        version=version,
        conflicts=tuple(dict.fromkeys(conflicts)),
        unresolved_fields=tuple(dict.fromkeys(unresolved)),
        merged_candidate_keys=tuple(
            dict.fromkeys([cluster.candidate_key, *(c.candidate_key for c in ordered)])
        ),
    )
