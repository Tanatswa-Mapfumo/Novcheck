"""Patent-mode single-reference screening (screening only, not legal advice).

One-reference anticipation-like screening requires exactly one earlier patent
reference whose verified classification is a decisive direct precedent for the
MCU. Multiple partial references are combination/obviousness-like context and
are never relabeled as one-reference anticipation. Priority and publication
dates stay separate, claim/specification locators are retained, and missing
patent evidence stays limited/unassessable rather than becoming an absence
finding.
"""

from collections.abc import Callable, Sequence
from datetime import date, datetime
from typing import Literal, Self

from pydantic import ConfigDict, model_validator

from novelty_harness.domain.base import ContractModel, utc_now
from novelty_harness.domain.enums import PrecedentState
from novelty_harness.domain.idea import ArtifactProvenance
from novelty_harness.domain.ids import MCUId, SourceId, SourceVersionId
from novelty_harness.evidence.passages.models import PassageLocator
from novelty_harness.evidence.precedent.models import (
    PatentScreeningDateRecord,
    PatentScreeningLocator,
    PatentScreeningResult,
    PrecedentClassification,
)
from novelty_harness.runtime.tracing.hashing import canonical_hash

PATENT_SCREENING_VERSION = "patent-screening-v1"

CONTRIBUTING_RELATIONS = frozenset(
    {
        PrecedentState.STRONG_PARTIAL_PRECEDENT,
        PrecedentState.COMPONENT_PRECEDENT_ONLY,
        PrecedentState.ANALOGOUS_PRECEDENT,
    }
)


class PatentEvidenceEntry(ContractModel):
    """One classified reference considered by patent-mode screening."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["patent-evidence-entry-v1"] = "patent-evidence-entry-v1"

    source_id: SourceId
    source_version_id: SourceVersionId | None = None
    is_patent: bool
    classification: PrecedentClassification
    priority_date: date | None = None
    publication_date: date | None = None
    locators: tuple[PatentScreeningLocator, ...] = ()

    @model_validator(mode="after")
    def classification_matches_source(self) -> Self:
        if self.classification.source_id != self.source_id:
            raise ValueError("Patent entry classification belongs to another source")
        return self


def patent_locator_from_passage(
    source_id: SourceId, passage_id: str, locator: PassageLocator
) -> PatentScreeningLocator:
    """Classify a passage locator as claims/specification/other."""

    label = " ".join(
        part for part in (locator.section, locator.label, *(locator.notes or ())) if part
    ).casefold()
    if "claim" in label:
        section = "CLAIMS"
    elif any(token in label for token in ("spec", "description", "embodiment")):
        section = "SPECIFICATION"
    else:
        section = "OTHER"
    return PatentScreeningLocator(
        source_id=source_id,
        passage_id=passage_id,
        locator=label or locator.kind.value,
        section=section,
    )


def screen_patent_references(
    *,
    mcu_id: MCUId,
    entries: Sequence[PatentEvidenceEntry],
    observed_at: datetime,
    clock: Callable[[], datetime] = utc_now,
    provenance: ArtifactProvenance | None = None,
) -> PatentScreeningResult:
    """Produce a one-reference versus multi-reference screening result."""

    patent_entries = [entry for entry in entries if entry.is_patent]
    limitations: list[str] = []
    if not patent_entries:
        mode = "UNASSESSABLE" if not entries else "LIMITED"
        limitations.append(
            "No patent reference evidence is available; this is not a finding of absence"
            if mode == "UNASSESSABLE"
            else "No relevant patent reference was available locally; not a finding of absence"
        )
        limitations.append("Non-patent sources are handled by normal precedent classification")
        return _result(
            mcu_id=mcu_id,
            mode=mode,
            entries=(),
            limitations=limitations,
            observed_at=observed_at,
            clock=clock,
            provenance=provenance,
        )

    direct = sorted(
        (
            entry
            for entry in patent_entries
            if entry.classification.relation == PrecedentState.DIRECT_PRECEDENT
            and entry.classification.decisive
        ),
        key=lambda entry: (
            entry.priority_date or entry.publication_date or date.max,
            entry.source_id,
        ),
    )
    if direct:
        chosen = direct[0]
        limitations.append(
            "Anticipation-like screening uses exactly one earlier reference; "
            "it is not a legal patentability determination"
        )
        return _result(
            mcu_id=mcu_id,
            mode="SINGLE_REFERENCE_ANTICIPATION_LIKE",
            entries=(chosen,),
            limitations=limitations,
            observed_at=observed_at,
            clock=clock,
            provenance=provenance,
        )

    contributing = sorted(
        (
            entry
            for entry in patent_entries
            if entry.classification.relation in CONTRIBUTING_RELATIONS
        ),
        key=lambda entry: (entry.publication_date or date.max, entry.source_id),
    )
    if len(contributing) >= 2:
        limitations.append(
            "Multiple references each cover parts of the claimed configuration; this is "
            "combination/obviousness-like context, never one-reference anticipation"
        )
        return _result(
            mcu_id=mcu_id,
            mode="MULTI_REFERENCE_COMBINATION_LIKE",
            entries=tuple(contributing),
            limitations=limitations,
            observed_at=observed_at,
            clock=clock,
            provenance=provenance,
        )
    if len(contributing) == 1:
        limitations.append(
            "A single partial reference does not establish the claimed configuration and "
            "cannot be one-reference anticipation"
        )
    else:
        limitations.append("No contributing patent reference was verified locally")
    return _result(
        mcu_id=mcu_id,
        mode="LIMITED",
        entries=tuple(contributing),
        limitations=limitations,
        observed_at=observed_at,
        clock=clock,
        provenance=provenance,
    )


def _result(
    *,
    mcu_id: MCUId,
    mode: str,
    entries: Sequence[PatentEvidenceEntry],
    limitations: Sequence[str],
    observed_at: datetime,
    clock: Callable[[], datetime],
    provenance: ArtifactProvenance | None,
) -> PatentScreeningResult:
    reference_ids = tuple(entry.source_id for entry in entries)
    single_reference = (
        entries[0].source_id if entries and mode == ("SINGLE_REFERENCE_ANTICIPATION_LIKE") else None
    )
    covered_elements: list[str] = []
    covered_relationships: list[str] = []
    missing_elements: list[str] = []
    missing_relationships: list[str] = []
    locators: list[PatentScreeningLocator] = []
    dates: list[PatentScreeningDateRecord] = []
    for entry in entries:
        covered_elements.extend(entry.classification.covered_elements)
        covered_relationships.extend(entry.classification.covered_relationships)
        missing_elements.extend(entry.classification.missing_elements)
        missing_relationships.extend(entry.classification.missing_relationships)
        if entry.classification.configuration_gap:
            missing_relationships.append(entry.classification.configuration_gap)
        locators.extend(entry.locators)
        dates.append(
            PatentScreeningDateRecord(
                source_id=entry.source_id,
                priority_date=entry.priority_date,
                publication_date=entry.publication_date,
            )
        )
    identity = canonical_hash(
        {
            "mcu_id": mcu_id,
            "mode": mode,
            "reference_source_ids": list(reference_ids),
            "version": PATENT_SCREENING_VERSION,
        }
    )
    return PatentScreeningResult(
        screening_id="psr_" + identity,
        mcu_id=mcu_id,
        mode=mode,  # type: ignore[arg-type]
        single_reference_id=single_reference,
        reference_source_ids=reference_ids,
        covered_elements=tuple(dict.fromkeys(covered_elements)),
        covered_relationships=tuple(dict.fromkeys(covered_relationships)),
        missing_elements=tuple(dict.fromkeys(missing_elements)),
        missing_relationships=tuple(dict.fromkeys(missing_relationships)),
        dates=tuple(dates),
        locators=tuple(locators),
        limitations=tuple(dict.fromkeys(limitations)),
        observed_at=clock(),
        provenance=provenance
        or ArtifactProvenance(
            kind="implemented",
            component="patent_mode_screening",
            detail="One-reference screening only; not legal advice.",
        ),
    )


__all__ = [
    "PATENT_SCREENING_VERSION",
    "PatentEvidenceEntry",
    "patent_locator_from_passage",
    "screen_patent_references",
]
