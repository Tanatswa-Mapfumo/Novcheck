"""Source-version construction and chronology-preserving version comparison.

A changed content hash creates a new version record. Nothing is overwritten and
hash equality never implies conceptual equivalence; it only means the exact
observed content is unchanged.
"""

from collections.abc import Sequence
from datetime import date
from typing import Literal

from pydantic import ConfigDict, Field

from novelty_harness.domain.base import ContractModel, UTCDateTime
from novelty_harness.domain.idea import ArtifactProvenance, NonBlankText
from novelty_harness.domain.ids import SourceId, SourceVersionId
from novelty_harness.evidence.normalization.models import (
    CanonicalIdentifiers,
    SourceAccessState,
    SourceVersionRecord,
    VersionKind,
)
from novelty_harness.runtime.tracing.hashing import canonical_hash


def version_id_for(source_id: str, version_label: str, content_hash: str) -> SourceVersionId:
    """Deterministic version identity: same content/label/source, same ID."""

    return "srcv_" + canonical_hash(
        {"source_id": source_id, "version_label": version_label, "content_hash": content_hash}
    )


def build_version_record(
    *,
    source_id: SourceId,
    content_hash: str,
    access_state: SourceAccessState,
    observed_at: UTCDateTime,
    provenance: ArtifactProvenance,
    version_kind: VersionKind = VersionKind.GENERIC,
    version_label: str | None = None,
    identifiers: CanonicalIdentifiers | None = None,
    published_date: date | None = None,
    predecessor_version_id: SourceVersionId | None = None,
    limitations: tuple[str, ...] = (),
) -> SourceVersionRecord:
    """Build one immutable version record; the caller links chronology."""

    label = version_label or version_kind.value.casefold()
    return SourceVersionRecord(
        version_id=version_id_for(source_id, label, content_hash),
        source_id=source_id,
        version_label=label,
        version_kind=version_kind,
        content_hash=content_hash,
        access_state=access_state,
        identifiers=identifiers or CanonicalIdentifiers(),
        published_date=published_date,
        predecessor_version_id=predecessor_version_id,
        limitations=limitations,
        observed_at=observed_at,
        provenance=provenance,
    )


class VersionComparison(ContractModel):
    """How a candidate version relates to the versions already observed."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["version-comparison-v1"] = "version-comparison-v1"

    relation: Literal["FIRST_VERSION", "SAME_CONTENT", "CONTENT_CHANGED"]
    predecessor_version_id: SourceVersionId | None = None
    chronology_certain: bool
    rationale: tuple[NonBlankText, ...] = Field(min_length=1)


def compare_versions(
    existing: Sequence[SourceVersionRecord], candidate: SourceVersionRecord
) -> VersionComparison:
    """Classify a candidate against known versions without rewriting history.

    Identical normalized content is ``SAME_CONTENT``. Different content is
    ``CONTENT_CHANGED`` with the most plausible predecessor retained; when
    chronology is missing, tied or contradicted by observation order, the
    comparison stays explicitly uncertain instead of guessing.
    """

    if not existing:
        return VersionComparison(
            relation="FIRST_VERSION",
            chronology_certain=True,
            rationale=("First observed version of this canonical source",),
        )

    same = sorted(v.version_id for v in existing if v.content_hash == candidate.content_hash)
    if same:
        return VersionComparison(
            relation="SAME_CONTENT",
            predecessor_version_id=same[0],
            chronology_certain=True,
            rationale=(f"Normalized content matches existing version {same[0]}",),
        )

    dated: list[tuple[date, SourceVersionRecord]] = [
        (version.published_date, version)
        for version in existing
        if version.published_date is not None
    ]
    rationale: list[str] = ["Normalized content differs from every existing version"]
    certain = True
    if not dated:
        certain = False
        rationale.append("No existing version has a comparable publication date")
        predecessor = min(existing, key=lambda v: (v.observed_at, v.version_id))
    else:
        latest_date = max(published for published, _ in dated)
        latest = [version for published, version in dated if published == latest_date]
        if len(latest) > 1:
            certain = False
            rationale.append("Multiple existing versions share the latest publication date")
        predecessor = min(latest, key=lambda v: v.version_id)
        if any(
            published > candidate.published_date
            for published, _ in dated
            if candidate.published_date is not None
        ):
            certain = False
            rationale.append(
                "Candidate publication date precedes an existing version; chronology unresolved"
            )
    if not certain:
        rationale.append("Predecessor link is provisional")
    else:
        rationale.append(f"Latest comparable existing version is {predecessor.version_id}")
    return VersionComparison(
        relation="CONTENT_CHANGED",
        predecessor_version_id=predecessor.version_id,
        chronology_certain=certain,
        rationale=tuple(rationale),
    )
