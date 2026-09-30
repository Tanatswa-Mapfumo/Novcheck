"""Bounded, same-source context expansion for insufficient verifications.

Only ``INSUFFICIENT_CONTEXT`` normally triggers expansion. Every window stays
inside the same source and version, retains the origin passage linkage, and
records an explicit block reason when no wider context is stored. Cross-source
or cross-version text can never be used to rescue a claim.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from novelty_harness.domain.base import utc_now
from novelty_harness.domain.idea import ArtifactProvenance
from novelty_harness.evidence.context.selection import (
    PassageSelectionError,
    SupportEvidenceBundle,
)
from novelty_harness.evidence.passages.extraction import extract_span
from novelty_harness.evidence.passages.models import PassageLocatorKind, PassageRecord
from novelty_harness.evidence.verification.models import ContextExpansion
from novelty_harness.runtime.tracing.hashing import canonical_hash

DEFAULT_WINDOW_CHARS = 600


class ContextCompleteness(StrEnum):
    """Completeness relative to stored, bounded same-version context."""

    COMPLETE = "COMPLETE"
    TRUNCATED = "TRUNCATED"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class ContextInspection:
    completeness: ContextCompleteness
    expansions: tuple[ContextExpansion, ...]
    reason: str


def expansion_provenance() -> ArtifactProvenance:
    return ArtifactProvenance(
        kind="implemented",
        component="context_expansion",
        detail="Bounded same-source/version context window; no cross-source rescue.",
    )


def _attested_boundary(passage: PassageRecord) -> tuple[str, bool, bool] | None:
    """Read complete-unit flags only from a checked parent-content attestation."""

    proof = passage.attestation
    if proof is None or proof.unit_start is None or proof.unit_end is None:
        return None
    # Revalidation defeats model_copy/model_construct changes to the passage.
    checked = PassageRecord.model_validate(passage.model_dump(mode="json"))
    proof = checked.attestation
    assert proof is not None and proof.unit_start is not None and proof.unit_end is not None
    key = f"{proof.parent_content_digest}:{proof.unit_type}:{proof.unit_start}:{proof.unit_end}"
    return key, proof.start_offset == proof.unit_start, proof.end_offset == proof.unit_end


def expand_passage_context(
    passage: PassageRecord,
    *,
    available_passages: Sequence[PassageRecord],
    attempt: int,
    window_chars: int = DEFAULT_WINDOW_CHARS,
    clock: Callable[[], datetime] = utc_now,
) -> ContextExpansion:
    """Expand one passage inside a wider stored same-source/version passage."""

    if attempt < 1 or window_chars < 1:
        raise ValueError("Expansion attempt and window size must be positive")
    inner = passage.text.strip()
    located, reason = _containing_candidate(passage, available_passages)
    if located is None:
        return _blocked(passage, attempt, reason, clock)
    outer, position = located
    start = max(0, position - window_chars)
    end = min(len(outer.text), position + len(inner) + window_chars)
    window_text = outer.text[start:end]
    if window_text == passage.text:
        return _blocked(passage, attempt, "Expansion adds no additional context", clock)
    limitations = [f"Expanded same-source context for {passage.passage_id}"]
    if start > 0 or end < len(outer.text):
        limitations.append("Known same-version context lies outside this bounded window")
    outer_proof = outer.attestation
    parent = outer_proof.parent if outer_proof is not None else passage.source_id
    offset = outer_proof.start_offset if outer_proof is not None else 0
    window = extract_span(
        parent,
        outer.text if outer_proof is None else None,
        char_start=offset + start,
        char_end=offset + end,
        observed_at=clock(),
        provenance=expansion_provenance(),
        kind=PassageLocatorKind.BLOCK,
        label="context-window",
        source_version_id=passage.source_version_id,
        limitations=tuple(limitations),
        notes=(f"context-expansion-attempt={attempt}",),
        _unit_scope=outer_proof.unit_type if outer_proof is not None else None,
        _unit_span=(outer_proof.unit_start, outer_proof.unit_end)
        if outer_proof is not None
        and outer_proof.unit_start is not None
        and outer_proof.unit_end is not None
        else None,
    )
    return ContextExpansion(
        origin_passage_id=passage.passage_id,
        source_id=passage.source_id,
        source_version_id=passage.source_version_id,
        attempt=attempt,
        available=True,
        window_passage=window,
        observed_at=clock(),
        provenance=expansion_provenance(),
    )


def _containing_candidate(
    passage: PassageRecord, available_passages: Sequence[PassageRecord]
) -> tuple[tuple[PassageRecord, int] | None, str]:
    inner = passage.text.strip()
    candidates = [
        candidate
        for candidate in available_passages
        if candidate.passage_id != passage.passage_id
        and candidate.source_id == passage.source_id
        and candidate.source_version_id == passage.source_version_id
        and len(candidate.text) > len(passage.text)
        and inner in candidate.text
    ]
    if not candidates:
        return None, "No wider same-source/version passage containing this text is stored"
    located = [
        (candidate, position)
        for candidate in candidates
        if (position := _located_position(passage, candidate, inner)) is not None
    ]
    if not located:
        return None, "The occurrence is ambiguous or its locator does not match stored context"
    return max(located, key=lambda item: (len(item[0].text), item[0].passage_id)), ""


def _located_position(passage: PassageRecord, outer: PassageRecord, inner: str) -> int | None:
    origin_start = passage.locator.char_start
    outer_start = outer.locator.char_start
    if origin_start is not None and outer_start is not None:
        position = origin_start - outer_start
        if outer.text[position : position + len(inner)] == inner:
            return position
        return None
    first = outer.text.find(inner)
    if first < 0 or outer.text.find(inner, first + 1) >= 0:
        return None
    return first


def inspect_passage_context(
    passage: PassageRecord,
    *,
    available_passages: Sequence[PassageRecord],
    attempt: int,
    window_chars: int = DEFAULT_WINDOW_CHARS,
    clock: Callable[[], datetime] = utc_now,
) -> ContextInspection:
    """Inspect the bounded stored context without claiming unseen text is complete."""

    if attempt < 1 or window_chars < 1:
        raise ValueError("Expansion attempt and window size must be positive")
    peers = tuple(
        candidate
        for candidate in available_passages
        if candidate.passage_id != passage.passage_id
        and candidate.source_id == passage.source_id
        and candidate.source_version_id == passage.source_version_id
        and candidate.locator.label != "context-window"
    )
    boundary = _attested_boundary(passage)
    if boundary is not None and boundary[1] and boundary[2]:
        return ContextInspection(
            ContextCompleteness.COMPLETE,
            (),
            "Extractor attests a complete immutable-content evidence unit",
        )
    containing, reason = _containing_candidate(passage, peers)
    if containing is not None:
        outer, _ = containing
        expansion = expand_passage_context(
            passage,
            available_passages=peers,
            attempt=attempt,
            window_chars=window_chars,
            clock=clock,
        )
        window = expansion.window_passage
        if window is None:
            return ContextInspection(
                ContextCompleteness.UNKNOWN, (expansion,), str(expansion.blocked_reason)
            )
        span = window.locator
        offset = outer.attestation.start_offset if outer.attestation is not None else 0
        omitted = any(
            candidate.passage_id != outer.passage_id and candidate.text not in outer.text
            for candidate in peers
        )
        outer_boundary = _attested_boundary(outer)
        if (
            span.char_start == offset
            and span.char_end == offset + len(outer.text)
            and not omitted
            and outer_boundary is not None
            and outer_boundary[1]
            and outer_boundary[2]
        ):
            return ContextInspection(
                ContextCompleteness.COMPLETE,
                (expansion,),
                "Stored same-version context is contained in the supplied window",
            )
        return ContextInspection(
            ContextCompleteness.TRUNCATED
            if span.char_start != offset or span.char_end != offset + len(outer.text)
            else ContextCompleteness.UNKNOWN,
            (expansion,),
            "Truncated: bounded window does not prove both evidence-unit boundaries"
            if span.char_start != offset or span.char_end != offset + len(outer.text)
            else "Stored content does not prove both evidence-unit boundaries",
        )
    if "ambiguous" in reason:
        return ContextInspection(
            ContextCompleteness.UNKNOWN,
            (_blocked(passage, attempt, reason, clock),),
            reason,
        )
    start, end = passage.locator.char_start, passage.locator.char_end
    if start is None or end is None:
        completeness = ContextCompleteness.UNKNOWN if peers else ContextCompleteness.UNAVAILABLE
        return ContextInspection(
            completeness,
            (_blocked(passage, attempt, reason, clock),),
            reason,
        )
    located_peers = tuple(
        candidate
        for candidate in peers
        if candidate.locator.char_start is not None
        and candidate.locator.char_end is not None
        and candidate.locator.char_end - candidate.locator.char_start == len(candidate.text)
    )
    before = [candidate for candidate in located_peers if candidate.locator.char_end == start]
    after = [candidate for candidate in located_peers if candidate.locator.char_start == end]
    if len(before) > 1 or len(after) > 1:
        return ContextInspection(
            ContextCompleteness.UNKNOWN,
            (_blocked(passage, attempt, "Ambiguous same-version neighboring locators", clock),),
            "Ambiguous same-version neighboring locators",
        )
    neighbors = tuple((*before, *after))
    if not neighbors:
        completeness = ContextCompleteness.UNKNOWN if peers else ContextCompleteness.UNAVAILABLE
        return ContextInspection(
            completeness,
            (_blocked(passage, attempt, "No adjacent same-version context is stored", clock),),
            "No adjacent same-version context is stored",
        )
    expansions = tuple(
        ContextExpansion(
            origin_passage_id=passage.passage_id,
            source_id=passage.source_id,
            source_version_id=passage.source_version_id,
            attempt=attempt,
            available=True,
            window_passage=neighbor,
            observed_at=clock(),
            provenance=expansion_provenance(),
        )
        for neighbor in neighbors
        if len(neighbor.text) <= window_chars
    )
    if len(expansions) != len(neighbors) or len(neighbors) != len(peers):
        return ContextInspection(
            ContextCompleteness.TRUNCATED,
            expansions
            or (_blocked(passage, attempt, "Neighbor exceeds bounded context window", clock),),
            "Truncated: known same-version context lies outside the neighboring window",
        )
    boundaries = (boundary, *(_attested_boundary(neighbor) for neighbor in neighbors))
    same_unit = (
        all(item is not None for item in boundaries)
        and len({item[0] for item in boundaries if item is not None}) == 1
    )
    before_boundary = _attested_boundary(before[0]) if before else None
    after_boundary = _attested_boundary(after[0]) if after else None
    starts = bool(before_boundary[1]) if before_boundary else bool(boundary and boundary[1])
    ends = bool(after_boundary[2]) if after_boundary else bool(boundary and boundary[2])
    return ContextInspection(
        ContextCompleteness.COMPLETE
        if same_unit and starts and ends
        else ContextCompleteness.UNKNOWN,
        expansions,
        "Both evidence-unit boundaries are attested"
        if same_unit and starts and ends
        else "Neighbor presence does not establish both evidence-unit boundaries",
    )


def _blocked(
    passage: PassageRecord,
    attempt: int,
    reason: str,
    clock: Callable[[], datetime],
) -> ContextExpansion:
    return ContextExpansion(
        origin_passage_id=passage.passage_id,
        source_id=passage.source_id,
        source_version_id=passage.source_version_id,
        attempt=attempt,
        available=False,
        blocked_reason=reason,
        observed_at=clock(),
        provenance=expansion_provenance(),
    )


def expanded_bundle(
    bundle: SupportEvidenceBundle,
    expansions: Sequence[ContextExpansion],
    *,
    attempt: int,
    clock: Callable[[], datetime] = utc_now,
) -> SupportEvidenceBundle:
    """Add available windows to the bundle while keeping origin passages.

    Raises :class:`PassageSelectionError` when no window is available; the
    caller then keeps the exhausted INSUFFICIENT_CONTEXT result.
    """

    windows = [
        expansion.window_passage
        for expansion in expansions
        if expansion.available and expansion.window_passage is not None
    ]
    if not windows:
        raise PassageSelectionError("No context window is available to expand")
    passages = tuple(
        {passage.passage_id: passage for passage in (*bundle.passages, *windows)}.values()
    )
    claim = bundle.claim.model_copy(
        update={
            "claim_id": "claim_"
            + canonical_hash(
                {
                    "origin_claim_id": bundle.claim.claim_id,
                    "attempt": attempt,
                    "passage_ids": [passage.passage_id for passage in passages],
                }
            ),
            "passage_ids": tuple(passage.passage_id for passage in passages),
        }
    )
    return SupportEvidenceBundle(
        claim=claim,
        passages=passages,
        limitations=tuple(
            dict.fromkeys(
                (
                    *bundle.limitations,
                    "Verification used bounded expanded same-source context",
                )
            )
        ),
    )


__all__ = [
    "DEFAULT_WINDOW_CHARS",
    "ContextCompleteness",
    "ContextInspection",
    "expand_passage_context",
    "expanded_bundle",
    "expansion_provenance",
    "inspect_passage_context",
]
