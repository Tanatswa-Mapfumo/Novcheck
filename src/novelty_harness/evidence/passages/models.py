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
    contract_kind: Literal["source-passage-v1"] = "source-passage-v1"

    passage_id: PassageId
    source_id: SourceId
    source_version_id: SourceVersionId | None = None
    text: NonBlankText
    content_hash: NonBlankText
    access_state: SourceAccessState
    locator: PassageLocator
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
        return self
