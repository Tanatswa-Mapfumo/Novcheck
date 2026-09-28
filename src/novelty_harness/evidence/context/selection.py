"""Select the exact mapped passages that a support claim is verified against.

Verification never starts from a summary, a ranking or a different source:
only the passages the mapper cited for this source/version become the claim,
and cross-source evidence cannot rescue a one-source claim.
"""

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Literal, Self

from pydantic import ConfigDict, Field, model_validator

from novelty_harness.domain.base import ContractModel, utc_now
from novelty_harness.domain.idea import ArtifactProvenance, NonBlankText
from novelty_harness.domain.ids import SupportClaimId
from novelty_harness.evidence.mapping.models import (
    RELATIONSHIP_DIMENSIONS,
    EvidenceProposition,
    SourceMCUMapping,
)
from novelty_harness.evidence.normalization.models import (
    SourceAccessState,
    SourceRecord,
    SourceVersionRecord,
)
from novelty_harness.evidence.passages.models import PassageRecord
from novelty_harness.evidence.verification.models import PassageSupportClaim
from novelty_harness.runtime.tracing.hashing import canonical_hash


class PassageSelectionError(ValueError):
    """The mapping cannot be grounded in exact same-source passages."""


class SupportEvidenceBundle(ContractModel):
    """A claim plus the exact passage records it is verified against."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["support-evidence-bundle-v1"] = "support-evidence-bundle-v1"

    claim: PassageSupportClaim
    passages: tuple[PassageRecord, ...] = Field(min_length=1)
    limitations: tuple[NonBlankText, ...] = ()

    @model_validator(mode="after")
    def passages_match_claim(self) -> Self:
        if tuple(passage.passage_id for passage in self.passages) != self.claim.passage_ids:
            raise ValueError("Bundle passages must match the claim's cited passages in order")
        for passage in self.passages:
            if passage.source_id != self.claim.source_id:
                raise ValueError("A support claim cannot cite another source")
            if (
                self.claim.source_version_id is not None
                and passage.source_version_id != self.claim.source_version_id
            ):
                raise ValueError("A support claim cannot cite another source version")
        return self


def select_support_passages(
    *,
    mapping: SourceMCUMapping,
    proposition: EvidenceProposition,
    source: SourceRecord,
    version: SourceVersionRecord | None,
    passages: Sequence[PassageRecord],
    clock: Callable[[], datetime] = utc_now,
) -> SupportEvidenceBundle:
    """Build the exact-passage claim for a mapping.

    Raises :class:`PassageSelectionError` when the mapping cites no grounded
    passage at all; the caller records that as unassessable rather than
    fabricating support.
    """

    if (
        mapping.source_id != source.source_id
        or mapping.proposition_id != proposition.proposition_id
    ):
        raise PassageSelectionError("Mapping does not belong to this source/proposition")
    version_id = version.version_id if version else None
    if version_id is not None and mapping.source_version_id not in {None, version_id}:
        raise PassageSelectionError("Mapping belongs to another source version")

    mapped_ids = list(mapping.mapped_passage_ids())
    if not mapped_ids:
        raise PassageSelectionError("Mapping cites no exact passage for any dimension")

    index: dict[str, PassageRecord] = {}
    for passage in passages:
        if passage.source_id != source.source_id:
            continue
        if passage.source_version_id != version_id:
            continue
        index.setdefault(passage.passage_id, passage)

    selected: list[PassageRecord] = []
    for identity in mapped_ids:
        passage = index.get(identity)
        if passage is None:
            raise PassageSelectionError(
                f"Mapped passage {identity} does not exist for source {source.source_id}"
            )
        selected.append(passage)

    claimed_dimensions = tuple(
        dimension.dimension
        for dimension in mapping.dimensions
        if dimension.matching or dimension.conflicting
    )
    relationship_claims = tuple(
        statement.relationship
        for dimension in mapping.dimensions
        if dimension.dimension in RELATIONSHIP_DIMENSIONS
        for statement in dimension.matching
        if statement.relationship is not None
    )
    limitations: list[str] = []
    if source.access_state == SourceAccessState.ABSTRACT_ONLY:
        limitations.append("Abstract-only evidence; conclusion strength is limited")
    elif source.access_state != SourceAccessState.FULL_TEXT:
        limitations.append("Content access is limited beyond abstract level")
    for passage in selected:
        limitations.extend(passage.limitations)

    identity = canonical_hash(
        {
            "mapping_id": mapping.mapping_id,
            "source_id": source.source_id,
            "source_version_id": version_id,
            "mcu_id": proposition.mcu_id,
            "proposition_id": proposition.proposition_id,
            "passage_ids": [passage.passage_id for passage in selected],
        }
    )
    claim_id: SupportClaimId = "claim_" + identity
    claim = PassageSupportClaim(
        claim_id=claim_id,
        mapping_id=mapping.mapping_id,
        source_id=source.source_id,
        source_version_id=version_id,
        mcu_id=proposition.mcu_id,
        proposition_id=proposition.proposition_id,
        proposition_statement=proposition.statement,
        commitments=proposition.commitments,
        claimed_dimensions=claimed_dimensions,
        relationship_claims=relationship_claims,
        passage_ids=tuple(passage.passage_id for passage in selected),
    )
    return SupportEvidenceBundle(
        claim=claim,
        passages=tuple(selected),
        limitations=tuple(dict.fromkeys(limitations)),
    )


def selection_provenance() -> ArtifactProvenance:
    return ArtifactProvenance(
        kind="implemented",
        component="support_passage_selection",
        detail="Exact mapped passages only; no cross-source or summary evidence.",
    )


__all__ = [
    "PassageSelectionError",
    "SupportEvidenceBundle",
    "select_support_passages",
    "selection_provenance",
]
