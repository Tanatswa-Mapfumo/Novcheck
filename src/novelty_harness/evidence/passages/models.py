import re
from enum import StrEnum
from typing import Literal, Self

from pydantic import ConfigDict, Field, model_validator

from novelty_harness.domain.base import ContractModel, UTCDateTime
from novelty_harness.domain.idea import ArtifactProvenance, NonBlankText
from novelty_harness.domain.ids import PassageId, SourceId, SourceVersionId
from novelty_harness.evidence.normalization.models import SourceAccessState
from novelty_harness.evidence.passages.hashing import text_hash


class PassageLocatorKind(StrEnum):
    ABSTRACT = "ABSTRACT"
    SECTION = "SECTION"
    BLOCK = "BLOCK"
    PARAGRAPH_WINDOW = "PARAGRAPH_WINDOW"
    README = "README"
    RESOLVED_CONTENT = "RESOLVED_CONTENT"
    USER_SUPPLIED = "USER_SUPPLIED"


class EvidenceUnitScope(StrEnum):
    ABSTRACT = "ABSTRACT"
    PATENT_CLAIM = "PATENT_CLAIM"
    PARAGRAPH = "PARAGRAPH"
    README_SECTION = "README_SECTION"
    DOCUMENT = "DOCUMENT"


class EvidenceUnitBoundary(ContractModel):
    """Extractor-attested limits of the unit containing a passage."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["evidence-unit-boundary-v1"] = "evidence-unit-boundary-v1"
    unit_id: NonBlankText
    scope: EvidenceUnitScope
    starts_unit: bool
    ends_unit: bool


class ResolvedVersionContent(ContractModel):
    """Immutable normalized content resolved for one source/version."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["resolved-version-content-v1"] = "resolved-version-content-v1"
    source_id: SourceId
    source_version_id: SourceVersionId | None
    content_digest: NonBlankText
    content_kind: Literal["DOCUMENT", "ABSTRACT"]
    access_state: SourceAccessState
    text: NonBlankText
    retrieved_at: UTCDateTime | None = None

    @model_validator(mode="after")
    def digest_matches_content(self) -> Self:
        if self.content_digest != text_hash(self.text):
            raise ValueError("Resolved content digest does not match normalized content")
        if (self.content_kind == "ABSTRACT") != (
            self.access_state == SourceAccessState.ABSTRACT_ONLY
        ):
            raise ValueError("Resolved content kind and access state disagree")
        return self


class PassageAttestation(ContractModel):
    """Extractor proof of a passage's exact slice of immutable parent content."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["passage-attestation-v1"] = "passage-attestation-v1"
    parent: ResolvedVersionContent
    parent_content_digest: NonBlankText
    source_id: SourceId
    source_version_id: SourceVersionId | None
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    unit_type: EvidenceUnitScope | None = None
    unit_start: int | None = Field(default=None, ge=0)
    unit_end: int | None = Field(default=None, gt=0)
    passage_digest: NonBlankText

    @model_validator(mode="after")
    def exact_parent_slice(self) -> Self:
        parent = self.parent
        if (
            self.parent_content_digest != parent.content_digest
            or self.source_id != parent.source_id
            or self.source_version_id != parent.source_version_id
        ):
            raise ValueError("Passage attestation parent identity or digest disagrees")
        if self.end_offset > len(parent.text) or self.start_offset >= self.end_offset:
            raise ValueError("Passage attestation offsets are outside parent content")
        if self.passage_digest != text_hash(parent.text[self.start_offset : self.end_offset]):
            raise ValueError("Passage attestation digest does not match parent slice")
        if (self.unit_start is None) != (self.unit_end is None):
            raise ValueError("Evidence unit requires both boundaries")
        if self.unit_start is not None and self.unit_end is not None:
            if self.unit_type is None:
                raise ValueError("Evidence unit boundaries require a type")
            if not (
                0
                <= self.unit_start
                <= self.start_offset
                < self.end_offset
                <= self.unit_end
                <= len(parent.text)
            ):
                raise ValueError("Evidence unit does not enclose the passage")
            if self.unit_type in {EvidenceUnitScope.DOCUMENT, EvidenceUnitScope.ABSTRACT}:
                if (self.unit_start, self.unit_end) != (0, len(parent.text)):
                    raise ValueError("Complete document or abstract must span parent content")
                if (
                    self.unit_type == EvidenceUnitScope.ABSTRACT
                    and parent.content_kind != "ABSTRACT"
                ):
                    raise ValueError("Abstract unit requires abstract parent content")
            elif self.unit_type == EvidenceUnitScope.README_SECTION:
                heading = re.compile(r"^(#{1,6})[ \t]+.+$", re.MULTILINE)
                found = list(heading.finditer(parent.text))
                sections: set[tuple[int, int]] = set()
                for index, item in enumerate(found):
                    level = len(item.group(1))
                    next_start = next(
                        (
                            later.start()
                            for later in found[index + 1 :]
                            if len(later.group(1)) <= level
                        ),
                        len(parent.text),
                    )
                    sections.add((item.start(), len(parent.text[:next_start].rstrip())))
                if (self.unit_start, self.unit_end) not in sections:
                    raise ValueError("Section boundaries are not present in parent content")
            elif self.unit_type == EvidenceUnitScope.PARAGRAPH:
                separators = list(re.finditer(r"\n[ \t]*\n", parent.text))
                starts = [0, *(item.end() for item in separators)]
                ends = [*(item.start() for item in separators), len(parent.text)]
                paragraphs = {
                    (start, end)
                    for start, end in zip(starts, ends, strict=True)
                    if parent.text[start:end].strip()
                }
                if (self.unit_start, self.unit_end) not in paragraphs:
                    raise ValueError("Paragraph boundaries are not present in parent content")
            elif self.unit_type == EvidenceUnitScope.PATENT_CLAIM:
                headings = list(
                    re.finditer(
                        r"^(?:claim[ \t]+)?\d+[.):][ \t]+",
                        parent.text,
                        re.MULTILINE | re.IGNORECASE,
                    )
                )
                claims = {
                    (item.start(), len(parent.text[:end].rstrip()))
                    for item, end in (
                        (
                            heading,
                            headings[index + 1].start()
                            if index + 1 < len(headings)
                            else len(parent.text),
                        )
                        for index, heading in enumerate(headings)
                    )
                }
                if (self.unit_start, self.unit_end) not in claims:
                    raise ValueError("Patent claim boundaries are not present in parent content")
            else:
                raise ValueError("Unsupported evidence unit type")
        return self


class PassageLocator(ContractModel):
    """Where exactly a passage came from inside its source/version."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["passage-locator-v1"] = "passage-locator-v1"

    kind: PassageLocatorKind
    label: NonBlankText | None = None
    section: NonBlankText | None = None
    start_paragraph: int | None = Field(default=None, ge=0)
    end_paragraph: int | None = Field(default=None, ge=0)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    notes: tuple[NonBlankText, ...] = ()

    @model_validator(mode="after")
    def consistent_spans(self) -> Self:
        char_start, char_end = self.char_start, self.char_end
        if (char_start is None) != (char_end is None):
            raise ValueError("Character span requires both char_start and char_end")
        if char_start is not None and char_end is not None and char_start >= char_end:
            raise ValueError("Character span must be a non-empty half-open range")
        start_paragraph, end_paragraph = self.start_paragraph, self.end_paragraph
        if (start_paragraph is None) != (end_paragraph is None):
            raise ValueError("Paragraph window requires both start and end")
        if (
            start_paragraph is not None
            and end_paragraph is not None
            and start_paragraph > end_paragraph
        ):
            raise ValueError("Paragraph window start must not exceed its end")
        if self.kind == PassageLocatorKind.SECTION and self.section is None:
            raise ValueError("Section locators require a section label")
        return self


class PassageRecord(ContractModel):
    """Exact source-derived text, never an LLM rewrite.

    Discovery-only text (snippets, metadata, marketing claims) cannot be
    represented here at all; only resolved content or abstracts qualify.
    """

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["source-passage-v2"] = "source-passage-v2"

    passage_id: PassageId
    source_id: SourceId
    source_version_id: SourceVersionId | None = None
    text: NonBlankText
    content_hash: NonBlankText
    access_state: SourceAccessState
    locator: PassageLocator
    unit_boundary: EvidenceUnitBoundary | None = None
    attestation: PassageAttestation | None = None
    limitations: tuple[NonBlankText, ...] = ()
    observed_at: UTCDateTime
    provenance: ArtifactProvenance

    @model_validator(mode="after")
    def exact_hashed_content(self) -> Self:
        if self.access_state not in {SourceAccessState.FULL_TEXT, SourceAccessState.ABSTRACT_ONLY}:
            raise ValueError("Only resolved content or abstracts can become passage evidence")
        if self.access_state == SourceAccessState.ABSTRACT_ONLY and (
            self.locator.kind != PassageLocatorKind.ABSTRACT
        ):
            raise ValueError("Abstract-only access requires an abstract locator")
        if self.content_hash != text_hash(self.text):
            raise ValueError("Passage content hash must match its exact normalized text")
        if self.attestation is not None:
            proof = self.attestation
            if (
                proof.source_id != self.source_id
                or proof.source_version_id != self.source_version_id
                or proof.passage_digest != self.content_hash
                or proof.parent.text[proof.start_offset : proof.end_offset] != self.text
            ):
                raise ValueError("Passage text does not match its parent content attestation")
            if self.locator.char_start is not None and (
                self.locator.char_start != proof.start_offset
                or self.locator.char_end != proof.end_offset
            ):
                raise ValueError("Passage locator disagrees with attested offsets")
        return self
