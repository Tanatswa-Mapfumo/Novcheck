"""Deterministic passage extraction with locator preservation.

Passages are exact slices of normalized source text. Nothing here summarizes,
rewrites or infers content, and there is deliberately no snippet or metadata
extraction path: discovery-only text cannot become passage evidence.
"""

import re
from collections.abc import Sequence

from novelty_harness.domain.base import UTCDateTime
from novelty_harness.domain.idea import ArtifactProvenance
from novelty_harness.domain.ids import PassageId, SourceId, SourceVersionId
from novelty_harness.evidence.normalization.models import SourceAccessState
from novelty_harness.evidence.passages.hashing import normalize_text, text_hash
from novelty_harness.evidence.passages.models import (
    EvidenceUnitBoundary,
    EvidenceUnitScope,
    PassageLocator,
    PassageLocatorKind,
    PassageRecord,
)
from novelty_harness.runtime.tracing.hashing import canonical_hash


class PassageExtractionError(ValueError):
    """The requested locator does not identify a valid passage."""


def passage_id_for(
    source_id: str,
    source_version_id: str | None,
    locator: PassageLocator,
    content_hash: str,
) -> PassageId:
    """Deterministic passage identity from source, version, locator and content."""

    return "pass_" + canonical_hash(
        {
            "source_id": source_id,
            "source_version_id": source_version_id,
            "locator": locator.model_dump(mode="json"),
            "content_hash": content_hash,
        }
    )


def _make_passage(
    *,
    source_id: SourceId,
    source_version_id: SourceVersionId | None,
    text: str,
    locator: PassageLocator,
    access_state: SourceAccessState,
    observed_at: UTCDateTime,
    provenance: ArtifactProvenance,
    limitations: Sequence[str] = (),
    unit_boundary: EvidenceUnitBoundary | None = None,
) -> PassageRecord:
    normalized = normalize_text(text)
    if not normalized:
        raise PassageExtractionError("Locator identifies blank content")
    content_hash = text_hash(normalized)
    return PassageRecord(
        passage_id=passage_id_for(source_id, source_version_id, locator, content_hash),
        source_id=source_id,
        source_version_id=source_version_id,
        text=normalized,
        content_hash=content_hash,
        access_state=access_state,
        locator=locator,
        unit_boundary=unit_boundary,
        limitations=tuple(limitations),
        observed_at=observed_at,
        provenance=provenance,
    )


def extract_span(
    source_id: SourceId,
    document_text: str,
    *,
    char_start: int,
    char_end: int,
    observed_at: UTCDateTime,
    provenance: ArtifactProvenance,
    kind: PassageLocatorKind = PassageLocatorKind.RESOLVED_CONTENT,
    section: str | None = None,
    label: str | None = None,
    start_paragraph: int | None = None,
    end_paragraph: int | None = None,
    source_version_id: SourceVersionId | None = None,
    limitations: Sequence[str] = (),
    notes: Sequence[str] = (),
    unit_boundary: EvidenceUnitBoundary | None = None,
) -> PassageRecord:
    """Extract an explicit half-open character span from normalized document text.

    ``char_start``/``char_end`` address the normalized document, so the same
    source text always yields byte-identical passages.
    """

    normalized = normalize_text(document_text)
    if char_start < 0 or char_end > len(normalized) or char_start >= char_end:
        raise PassageExtractionError(
            f"Character span [{char_start}, {char_end}) is outside the normalized document"
        )
    locator = PassageLocator(
        kind=kind,
        section=section,
        label=label,
        start_paragraph=start_paragraph,
        end_paragraph=end_paragraph,
        char_start=char_start,
        char_end=char_end,
        notes=tuple(notes),
    )
    return _make_passage(
        source_id=source_id,
        source_version_id=source_version_id,
        text=normalized[char_start:char_end],
        locator=locator,
        access_state=SourceAccessState.FULL_TEXT,
        observed_at=observed_at,
        provenance=provenance,
        limitations=limitations,
        unit_boundary=unit_boundary,
    )


def extract_abstract(
    source_id: SourceId,
    abstract: str,
    *,
    observed_at: UTCDateTime,
    provenance: ArtifactProvenance,
    source_version_id: SourceVersionId | None = None,
    label: str = "Abstract",
    limitations: Sequence[str] = (),
) -> PassageRecord:
    """Extract an abstract that stays explicitly abstract-only."""

    return _make_passage(
        source_id=source_id,
        source_version_id=source_version_id,
        text=abstract,
        locator=PassageLocator(
            kind=PassageLocatorKind.ABSTRACT,
            label=label,
            notes=("Abstract-only access; full text was not available",),
        ),
        access_state=SourceAccessState.ABSTRACT_ONLY,
        observed_at=observed_at,
        provenance=provenance,
        limitations=tuple(
            dict.fromkeys((*limitations, "Abstract-only access limits completeness"))
        ),
        unit_boundary=EvidenceUnitBoundary(
            unit_id="unit_"
            + canonical_hash(
                {
                    "source": source_id,
                    "version": source_version_id,
                    "scope": "abstract",
                    "text": normalize_text(abstract),
                }
            ),
            scope=EvidenceUnitScope.ABSTRACT,
            starts_unit=True,
            ends_unit=True,
        ),
    )


def extract_resolved_content(
    source_id: SourceId,
    text: str,
    *,
    observed_at: UTCDateTime,
    provenance: ArtifactProvenance,
    source_version_id: SourceVersionId | None = None,
    limitations: Sequence[str] = (),
) -> PassageRecord:
    """Whole resolved content as one exact passage."""

    normalized = normalize_text(text)
    return extract_span(
        source_id,
        normalized,
        char_start=0,
        char_end=len(normalized),
        observed_at=observed_at,
        provenance=provenance,
        kind=PassageLocatorKind.RESOLVED_CONTENT,
        source_version_id=source_version_id,
        limitations=limitations,
        unit_boundary=EvidenceUnitBoundary(
            unit_id="unit_"
            + canonical_hash(
                {
                    "source": source_id,
                    "version": source_version_id,
                    "scope": "document",
                    "text": normalized,
                }
            ),
            scope=EvidenceUnitScope.DOCUMENT,
            starts_unit=True,
            ends_unit=True,
        ),
    )


def extract_readme(
    source_id: SourceId,
    text: str,
    *,
    path: str,
    observed_at: UTCDateTime,
    provenance: ArtifactProvenance,
    source_version_id: SourceVersionId | None = None,
    limitations: Sequence[str] = (),
) -> PassageRecord:
    """Repository documentation file content with its path as locator label."""

    normalized = normalize_text(text)
    return extract_span(
        source_id,
        normalized,
        char_start=0,
        char_end=len(normalized),
        observed_at=observed_at,
        provenance=provenance,
        kind=PassageLocatorKind.README,
        label=path,
        source_version_id=source_version_id,
        limitations=limitations,
        unit_boundary=EvidenceUnitBoundary(
            unit_id="unit_"
            + canonical_hash(
                {
                    "source": source_id,
                    "version": source_version_id,
                    "scope": "readme",
                    "path": path,
                    "text": normalized,
                }
            ),
            scope=EvidenceUnitScope.DOCUMENT,
            starts_unit=True,
            ends_unit=True,
        ),
    )


def extract_user_supplied(
    source_id: SourceId,
    text: str,
    *,
    label: str,
    observed_at: UTCDateTime,
    provenance: ArtifactProvenance,
    source_version_id: SourceVersionId | None = None,
    limitations: Sequence[str] = (),
) -> PassageRecord:
    """Exact passage text supplied by a user/provider with an explicit label."""

    normalized = normalize_text(text)
    return extract_span(
        source_id,
        normalized,
        char_start=0,
        char_end=len(normalized),
        observed_at=observed_at,
        provenance=provenance,
        kind=PassageLocatorKind.USER_SUPPLIED,
        label=label,
        source_version_id=source_version_id,
        limitations=limitations,
    )


_MARKDOWN_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$", re.MULTILINE)
_PARAGRAPH_SEPARATOR = re.compile(r"\n[ \t]*\n")


class _Heading:
    __slots__ = ("level", "title", "start")

    def __init__(self, level: int, title: str, start: int) -> None:
        self.level = level
        self.title = title
        self.start = start


def _headings(text: str) -> list[_Heading]:
    found: list[_Heading] = []
    for match in _MARKDOWN_HEADING.finditer(text):
        found.append(
            _Heading(
                level=len(match.group(1)),
                title=" ".join(match.group(2).split()),
                start=match.start(),
            )
        )
    return found


def _paragraph_spans(text: str) -> list[tuple[int, int]]:
    separators = list(_PARAGRAPH_SEPARATOR.finditer(text))
    starts = [0, *(match.end() for match in separators)]
    ends = [*(match.start() for match in separators), len(text)]
    return [
        (start, end_a)
        for start, end_a in zip(starts, ends, strict=True)
        if text[start:end_a].strip()
    ]


def extract_section(
    source_id: SourceId,
    document_text: str,
    *,
    section: str,
    observed_at: UTCDateTime,
    provenance: ArtifactProvenance,
    occurrence: int = 0,
    source_version_id: SourceVersionId | None = None,
    limitations: Sequence[str] = (),
) -> PassageRecord:
    """Extract a markdown-style section exactly up to the next same/higher heading."""

    if occurrence < 0:
        raise PassageExtractionError("Section occurrence must be non-negative")
    normalized = normalize_text(document_text)
    headings = _headings(normalized)
    wanted = " ".join(section.split()).casefold()
    matching = [heading for heading in headings if heading.title.casefold() == wanted]
    if not matching:
        raise PassageExtractionError(f"Section not found: {section}")
    if occurrence >= len(matching):
        raise PassageExtractionError(
            f"Section {section} has {len(matching)} occurrence(s); {occurrence} requested"
        )
    selected = matching[occurrence]
    end = len(normalized)
    for heading in headings:
        if heading.start > selected.start and heading.level <= selected.level:
            end = heading.start
            break
    notes = (
        (f"Multiple headings match; occurrence {occurrence} selected",) if len(matching) > 1 else ()
    )
    return extract_span(
        source_id,
        normalized,
        char_start=selected.start,
        char_end=end,
        observed_at=observed_at,
        provenance=provenance,
        kind=PassageLocatorKind.SECTION,
        section=selected.title,
        source_version_id=source_version_id,
        limitations=limitations,
        notes=notes,
        unit_boundary=EvidenceUnitBoundary(
            unit_id="unit_"
            + canonical_hash(
                {
                    "source": source_id,
                    "version": source_version_id,
                    "scope": "section",
                    "start": selected.start,
                    "end": end,
                    "text": normalized[selected.start : end],
                }
            ),
            scope=EvidenceUnitScope.README_SECTION,
            starts_unit=True,
            ends_unit=True,
        ),
    )


def extract_paragraph_window(
    source_id: SourceId,
    document_text: str,
    *,
    start_paragraph: int,
    end_paragraph: int,
    observed_at: UTCDateTime,
    provenance: ArtifactProvenance,
    source_version_id: SourceVersionId | None = None,
    limitations: Sequence[str] = (),
) -> PassageRecord:
    """Extract an inclusive window of blank-line-separated paragraphs exactly."""

    if start_paragraph < 0 or end_paragraph < start_paragraph:
        raise PassageExtractionError("Invalid paragraph window")
    normalized = normalize_text(document_text)
    spans = _paragraph_spans(normalized)
    if not spans:
        raise PassageExtractionError("Document contains no paragraphs")
    if end_paragraph >= len(spans):
        raise PassageExtractionError(
            f"Paragraph window ends at {end_paragraph}; document has {len(spans)}"
        )
    char_start = spans[start_paragraph][0]
    char_end = spans[end_paragraph][1]
    return extract_span(
        source_id,
        normalized,
        char_start=char_start,
        char_end=char_end,
        observed_at=observed_at,
        provenance=provenance,
        kind=PassageLocatorKind.PARAGRAPH_WINDOW,
        start_paragraph=start_paragraph,
        end_paragraph=end_paragraph,
        source_version_id=source_version_id,
        limitations=limitations,
        notes=(f"Paragraph window {start_paragraph}-{end_paragraph}",),
    )
