import re
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import ConfigDict, JsonValue

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.idea import NonBlankText
from novelty_harness.ports.models import SourceRef
from novelty_harness.research.retrieval.models import RetrievalCandidate, RetrievalStrategy
from novelty_harness.runtime.tracing.hashing import canonical_hash


class CandidateCluster(ContractModel):
    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["candidate-cluster-v1"] = "candidate-cluster-v1"
    candidate_key: NonBlankText
    discoveries: tuple[RetrievalCandidate, ...]
    source_refs: tuple[SourceRef, ...]
    providers: frozenset[NonBlankText]
    strategies: frozenset[RetrievalStrategy]
    earliest_observed_date: date | None
    latest_observed_date: date | None
    metadata_conflicts: tuple[str, ...]


def _doi(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().casefold()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if text.startswith(prefix):
            text = text[len(prefix) :].strip()
            break
    return text if re.fullmatch(r"10\.\d{4,9}/\S+", text) else None


def _dois(candidate: RetrievalCandidate) -> set[str]:
    external = candidate.raw_metadata.get("externalIds")
    values = [candidate.raw_metadata.get("doi"), candidate.source.provider_source_id]
    if isinstance(external, dict):
        values.append(external.get("DOI"))
    return {d for v in values if (d := _doi(v)) is not None}


def _url(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        u = urlsplit(value)
        if u.scheme not in {"http", "https"} or not u.hostname or u.username or u.password:
            return None
        return urlunsplit((u.scheme, u.netloc.casefold(), u.path, u.query, ""))
    except ValueError:
        return None


def _full_date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return date.fromisoformat(value)
        if "T" in value:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is not None:
                return parsed.date()
    except ValueError:
        pass
    return None


def _bibliography(candidate: RetrievalCandidate) -> str | None:
    authors = candidate.raw_metadata.get("authors")
    published = _full_date(candidate.raw_metadata.get("publication_date"))
    if (
        not isinstance(authors, list)
        or not authors
        or published is None
        or not candidate.source.title
    ):
        return None
    names: list[JsonValue] = []
    for author in authors:
        name = author.get("name") if isinstance(author, dict) else author
        if not isinstance(name, str) or not name.strip():
            return None
        names.append(" ".join(name.casefold().split()))
    fields: dict[str, JsonValue] = {
        "title": " ".join(candidate.source.title.casefold().split()),
        "authors": names,
        "date": published.isoformat(),
    }
    return canonical_hash(fields)


def cluster_candidates(candidates: Sequence[RetrievalCandidate]) -> list[CandidateCluster]:
    observations = {
        canonical_hash(c.model_dump(mode="json")): RetrievalCandidate.model_validate(c.model_dump())
        for c in candidates
    }
    rows = [observations[h] for h in sorted(observations)]
    parent = list(range(len(rows)))

    def root(index: int) -> int:
        while parent[index] != index:
            index = parent[index]
        return index

    def join(a: int, b: int, *, weak: bool) -> None:
        ra, rb = root(a), root(b)
        if ra == rb:
            return
        members = [r for i, r in enumerate(rows) if root(i) in {ra, rb}]
        if weak:
            if len({doi for r in members for doi in _dois(r)}) > 1:
                return
            identities: dict[str, set[str]] = {}
            for r in members:
                identities.setdefault(r.provider_name, set()).add(r.source.provider_source_id)
            if any(len(ids) > 1 for ids in identities.values()):
                return
        parent[max(ra, rb)] = min(ra, rb)

    # Strong identities precede guarded URL/bibliographic links; titles alone never link.
    for i, a in enumerate(rows):
        for j in range(i):
            b = rows[j]
            if (a.provider_name, a.source.provider_source_id) == (
                b.provider_name,
                b.source.provider_source_id,
            ) or _dois(a) & _dois(b):
                join(i, j, weak=False)
    for i, a in enumerate(rows):
        for j in range(i):
            b = rows[j]
            if (
                (u := _url(a.source.canonical_url)) is not None
                and u == _url(b.source.canonical_url)
                or (bib := _bibliography(a)) is not None
                and bib == _bibliography(b)
            ):
                join(i, j, weak=True)
    groups: dict[int, list[RetrievalCandidate]] = {}
    for i, row in enumerate(rows):
        groups.setdefault(root(i), []).append(row)
    clusters: list[CandidateCluster] = []
    for group in groups.values():
        dois = sorted({doi for r in group for doi in _dois(r)})
        identity = (
            ("doi", dois[0])
            if dois
            else min((r.provider_name, r.source.provider_source_id) for r in group)
        )
        refs = {canonical_hash(r.source.model_dump(mode="json")): r.source for r in group}
        dates = [
            d
            for r in group
            for value in r.raw_metadata.values()
            if (d := _full_date(value)) is not None
        ]
        values: dict[str, set[str]] = {}
        for r in group:
            for key, value in r.raw_metadata.items():
                if key != "provider_local_score":
                    values.setdefault(key, set()).add(canonical_hash(value))
        clusters.append(
            CandidateCluster(
                candidate_key="cluster:" + canonical_hash(list(identity)),
                discoveries=tuple(group),
                source_refs=tuple(refs[h] for h in sorted(refs)),
                providers=frozenset(r.provider_name for r in group),
                strategies=frozenset(r.strategy for r in group),
                earliest_observed_date=min(dates) if dates else None,
                latest_observed_date=max(dates) if dates else None,
                metadata_conflicts=tuple(sorted(k for k, vs in values.items() if len(vs) > 1)),
            )
        )
    return sorted(clusters, key=lambda c: c.candidate_key)


def rekey_lists(
    ranked_lists: Mapping[str, Sequence[RetrievalCandidate]], clusters: Sequence[CandidateCluster]
) -> dict[str, list[RetrievalCandidate]]:
    keys = {
        (c.provider_name, c.source.provider_source_id): cluster.candidate_key
        for cluster in clusters
        for c in cluster.discoveries
    }
    return {
        name: [
            c.model_copy(
                update={"candidate_key": keys[(c.provider_name, c.source.provider_source_id)]}
            )
            for c in rows
        ]
        for name, rows in ranked_lists.items()
    }
