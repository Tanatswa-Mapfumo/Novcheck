"""Bounded, same-source context expansion for insufficient verifications.

Only ``INSUFFICIENT_CONTEXT`` normally triggers expansion. Every window stays
inside the same source and version, retains the origin passage linkage, and
records an explicit block reason when no wider context is stored. Cross-source
or cross-version text can never be used to rescue a claim.
"""

from collections.abc import Callable, Sequence
from datetime import datetime

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


def expansion_provenance() -> ArtifactProvenance:
    return ArtifactProvenance(
        kind="implemented",
        component="context_expansion",
        detail="Bounded same-source/version context window; no cross-source rescue.",
    )


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
        return _blocked(
            passage,
            attempt,
            "No wider same-source/version passage containing this text is stored",
            clock,
        )
    outer = max(candidates, key=lambda candidate: (len(candidate.text), candidate.passage_id))
    position = outer.text.find(inner)
    start = max(0, position - window_chars)
    end = min(len(outer.text), position + len(inner) + window_chars)
    window_text = outer.text[start:end]
    if window_text == passage.text:
        return _blocked(passage, attempt, "Expansion adds no additional context", clock)
    window = extract_span(
        passage.source_id,
        outer.text,
        char_start=start,
        char_end=end,
        observed_at=clock(),
        provenance=expansion_provenance(),
        kind=PassageLocatorKind.BLOCK,
        label="context-window",
        source_version_id=passage.source_version_id,
        limitations=(f"Expanded same-source context for {passage.passage_id}",),
        notes=(f"context-expansion-attempt={attempt}",),
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
    "expand_passage_context",
    "expanded_bundle",
    "expansion_provenance",
]
