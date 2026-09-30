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
from novelty_harness.evidence.normalization.models import (
    SourceAccessState,
    SourceRecord,
    SourceVersionRecord,
)
from novelty_harness.evidence.passages.hashing import normalize_text, text_hash
from novelty_harness.evidence.passages.models import (
    EvidenceUnitBoundary,
    EvidenceUnitScope,
    PassageAttestation,
    PassageLocator,
    PassageLocatorKind,
    PassageRecord,
    ResolvedVersionContent,
)
from novelty_harness.runtime.tracing.hashing import canonical_hash


class PassageExtractionError(ValueError):
    """The requested locator does not identify a valid passage."""


def resolve_version_content(
    *,
    source: SourceRecord,
    version: SourceVersionRecord | None,
    text: str,
    retrieved_at: UTCDateTime | None = None,
) -> ResolvedVersionContent:
    """Bind resolved text to the immutable owned source/version digest."""

    normalized = normalize_text(text)
    digest = text_hash(normalized)
    if version is not None and version.source_id != source.source_id:
        raise PassageExtractionError("Resolved version belongs to another source")
    authoritative = version.content_hash if version is not None else source.content_hash
    if authoritative is not None and authoritative != digest:
        raise PassageExtractionError("Resolved content digest conflicts with source/version hash")
    access = version.access_state if version is not None else source.access_state
    if access not in {SourceAccessState.FULL_TEXT, SourceAccessState.ABSTRACT_ONLY}:
        raise PassageExtractionError("Unresolved source cannot supply passage content")
    return ResolvedVersionContent(
        source_id=source.source_id,
        source_version_id=version.version_id if version is not None else None,
        content_digest=digest,
        content_kind="ABSTRACT" if access == SourceAccessState.ABSTRACT_ONLY else "DOCUMENT",
        access_state=access,
        text=normalized,
        retrieved_at=retrieved_at,
    )


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
    attestation: PassageAttestation | None = None,
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
        attestation=attestation,
        limitations=tuple(limitations),
        observed_at=observed_at,
        provenance=provenance,
    )


def extract_span(
    source_id: SourceId | ResolvedVersionContent,
    document_text: str | None = None,
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
    _unit_scope: EvidenceUnitScope | None = None,
    _unit_span: tuple[int, int] | None = None,
) -> PassageRecord:
    """Extract an explicit half-open character span from normalized document text.

    ``char_start``/``char_end`` address the normalized document, so the same
    source text always yields byte-identical passages.
    """

    if unit_boundary is not None:
        raise PassageExtractionError("Caller-provided unit boundary is not an attestation")
    resolved = source_id if isinstance(source_id, ResolvedVersionContent) else None
    if resolved is not None:
        if document_text is not None and normalize_text(document_text) != resolved.text:
            raise PassageExtractionError("Extracted document differs from resolved content")
        normalized = resolved.text
        source_version_id = resolved.source_version_id
        actual_source_id = resolved.source_id
    else:
        if document_text is None:
            raise PassageExtractionError("Document text is required")
        normalized = normalize_text(document_text)
        assert isinstance(source_id, str)
        actual_source_id = source_id
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
    attestation = None
    if resolved is not None:
        unit_start, unit_end = _unit_span if _unit_span is not None else (None, None)
        attestation = PassageAttestation(
            parent=resolved,
            parent_content_digest=resolved.content_digest,
            source_id=resolved.source_id,
            source_version_id=resolved.source_version_id,
            start_offset=char_start,
            end_offset=char_end,
            unit_type=_unit_scope,
            unit_start=unit_start,
            unit_end=unit_end,
            passage_digest=text_hash(normalized[char_start:char_end]),
        )
    if resolved is not None and _unit_scope is not None and _unit_span is not None:
        unit_boundary = EvidenceUnitBoundary(
            unit_id="unit_"
            + canonical_hash(
                {
                    "parent": resolved.content_digest,
                    "scope": _unit_scope.value,
                    "span": list(_unit_span),
                }
            ),
            scope=_unit_scope,
            starts_unit=char_start == _unit_span[0],
            ends_unit=char_end == _unit_span[1],
        )
    return _make_passage(
        source_id=actual_source_id,
        source_version_id=source_version_id,
        text=normalized[char_start:char_end],
        locator=locator,
        access_state=resolved.access_state if resolved is not None else SourceAccessState.FULL_TEXT,
        observed_at=observed_at,
        provenance=provenance,
        limitations=limitations,
        unit_boundary=unit_boundary,
        attestation=attestation,
    )


def extract_abstract(
    source_id: SourceId | ResolvedVersionContent,
    abstract: str | None = None,
    *,
    observed_at: UTCDateTime,
    provenance: ArtifactProvenance,
    source_version_id: SourceVersionId | None = None,
    label: str = "Abstract",
    limitations: Sequence[str] = (),
) -> PassageRecord:
    """Extract an abstract that stays explicitly abstract-only."""

    if isinstance(source_id, ResolvedVersionContent):
        resolved = source_id
        if resolved.content_kind != "ABSTRACT":
            raise PassageExtractionError("Abstract extraction requires resolved abstract content")
        return extract_span(
            resolved,
            char_start=0,
            char_end=len(resolved.text),
            observed_at=observed_at,
            provenance=provenance,
            kind=PassageLocatorKind.ABSTRACT,
            label=label,
            limitations=(*limitations, "Abstract-only access limits completeness"),
            _unit_scope=EvidenceUnitScope.ABSTRACT,
            _unit_span=(0, len(resolved.text)),
        )
    if abstract is None:
        raise PassageExtractionError("Abstract text is required")
    normalized = normalize_text(abstract)
    return _make_passage(
        source_id=source_id,
        source_version_id=source_version_id,
        text=normalized,
        locator=PassageLocator(kind=PassageLocatorKind.ABSTRACT, label=label),
        access_state=SourceAccessState.ABSTRACT_ONLY,
        observed_at=observed_at,
        provenance=provenance,
        limitations=(*limitations, "Abstract-only access limits completeness"),
    )


def extract_resolved_content(
    source_id: SourceId | ResolvedVersionContent,
    text: str | None = None,
    *,
    observed_at: UTCDateTime,
    provenance: ArtifactProvenance,
    source_version_id: SourceVersionId | None = None,
    limitations: Sequence[str] = (),
) -> PassageRecord:
    """Whole resolved content as one exact passage."""

    if isinstance(source_id, ResolvedVersionContent):
        normalized = source_id.text
        if source_id.content_kind != "DOCUMENT":
            raise PassageExtractionError("Document extraction requires resolved document content")
    else:
        if text is None:
            raise PassageExtractionError("Resolved text is required")
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
        _unit_scope=EvidenceUnitScope.DOCUMENT
        if isinstance(source_id, ResolvedVersionContent)
        else None,
        _unit_span=(0, len(normalized)) if isinstance(source_id, ResolvedVersionContent) else None,
    )


def extract_readme(
    source_id: SourceId | ResolvedVersionContent,
    text: str | None = None,
    *,
    path: str,
    observed_at: UTCDateTime,
    provenance: ArtifactProvenance,
    source_version_id: SourceVersionId | None = None,
    limitations: Sequence[str] = (),
) -> PassageRecord:
    """Repository documentation file content with its path as locator label."""

    if isinstance(source_id, ResolvedVersionContent):
        normalized = source_id.text
    elif text is not None:
        normalized = normalize_text(text)
    else:
        raise PassageExtractionError("README text is required")
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
        _unit_scope=EvidenceUnitScope.DOCUMENT
        if isinstance(source_id, ResolvedVersionContent)
        else None,
        _unit_span=(0, len(normalized)) if isinstance(source_id, ResolvedVersionContent) else None,
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
    source_id: SourceId | ResolvedVersionContent,
    document_text: str | None = None,
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
    if isinstance(source_id, ResolvedVersionContent):
        normalized = source_id.text
    elif document_text is not None:
        normalized = normalize_text(document_text)
    else:
        raise PassageExtractionError("Document text is required")
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
    end = len(normalized[:end].rstrip())
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
        _unit_scope=EvidenceUnitScope.README_SECTION
        if isinstance(source_id, ResolvedVersionContent)
        else None,
        _unit_span=(selected.start, end) if isinstance(source_id, ResolvedVersionContent) else None,
    )


def extract_paragraph_window(
    source_id: SourceId | ResolvedVersionContent,
    document_text: str | None = None,
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
    if isinstance(source_id, ResolvedVersionContent):
        normalized = source_id.text
    elif document_text is not None:
        normalized = normalize_text(document_text)
    else:
        raise PassageExtractionError("Document text is required")
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
        _unit_scope=EvidenceUnitScope.PARAGRAPH
        if isinstance(source_id, ResolvedVersionContent) and start_paragraph == end_paragraph
        else None,
        _unit_span=spans[start_paragraph]
        if isinstance(source_id, ResolvedVersionContent) and start_paragraph == end_paragraph
        else None,
    )


def extract_patent_claim(
    resolved: ResolvedVersionContent,
    *,
    claim_number: int,
    observed_at: UTCDateTime,
    provenance: ArtifactProvenance,
    limitations: Sequence[str] = (),
) -> PassageRecord:
    """Extract one numbered claim from resolved text with proven claim limits."""

    if claim_number < 1 or resolved.content_kind != "DOCUMENT":
        raise PassageExtractionError("Patent claim requires a numbered resolved document")
    headings = list(
        re.finditer(
            r"^(?:claim[ \t]+)?(\d+)[.):][ \t]+",
            resolved.text,
            re.MULTILINE | re.IGNORECASE,
        )
    )
    found = [
        (index, match)
        for index, match in enumerate(headings)
        if int(match.group(1)) == claim_number
    ]
    if len(found) != 1:
        raise PassageExtractionError("Patent claim number is missing or ambiguous")
    index, match = found[0]
    next_start = headings[index + 1].start() if index + 1 < len(headings) else len(resolved.text)
    end = len(resolved.text[:next_start].rstrip())
    return extract_span(
        resolved,
        char_start=match.start(),
        char_end=end,
        observed_at=observed_at,
        provenance=provenance,
        kind=PassageLocatorKind.SECTION,
        section=f"Claim {claim_number}",
        limitations=limitations,
        _unit_scope=EvidenceUnitScope.PATENT_CLAIM,
        _unit_span=(match.start(), end),
    )
