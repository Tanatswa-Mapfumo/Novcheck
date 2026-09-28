"""Blinded independent support verifier and its bounded context-retry loop.

The verifier is a separate stage from mapping and classification. Its only
input is the blinded verification input built from a support bundle, and its
only output is a support state for the claimed proposition. It cannot see a
novelty verdict, a proposed precedent class, a prosecutor/defender role, a
source-quality tier, a retrieval rank, a provider score, a user novelty claim
or report wording.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime

from novelty_harness.domain.base import utc_now
from novelty_harness.domain.enums import SupportVerificationState
from novelty_harness.evidence.context.expansion import (
    DEFAULT_WINDOW_CHARS,
    ContextCompleteness,
    expanded_bundle,
    inspect_passage_context,
)
from novelty_harness.evidence.context.selection import SupportEvidenceBundle
from novelty_harness.evidence.passages.models import PassageRecord
from novelty_harness.evidence.verification.gates import (
    PassageIntegrityError,
    VerificationValidationError,
    aggregate_verification,
    build_blinded_input,
    check_passage_integrity,
)
from novelty_harness.evidence.verification.models import (
    ContextExpansion,
    SupportVerification,
)
from novelty_harness.evidence.verification.prompts import (
    VERIFIER_INSTRUCTION,
    VERIFIER_PROMPT_VERSION,
    VerifierProposal,
)
from novelty_harness.ports.models import ContextBlock
from novelty_harness.runtime.semantic.structured import SemanticRunner, SemanticTaskSpec
from novelty_harness.runtime.tracing.hashing import canonical_hash, canonical_json

VERIFIER_TASK = "verify_support"


class IndependentSupportVerifier:
    """LLM-assisted, deterministically gated entailment judgment."""

    def __init__(self, runner: SemanticRunner) -> None:
        self.runner = runner

    async def verify(
        self,
        bundle: SupportEvidenceBundle,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> SupportVerification:
        check_passage_integrity(bundle)
        blinded = build_blinded_input(bundle)
        proposal = await self.runner.run(
            SemanticTaskSpec(VERIFIER_TASK, VERIFIER_PROMPT_VERSION, VerifierProposal),
            VERIFIER_INSTRUCTION,
            [
                ContextBlock(
                    label="verification_input",
                    text=canonical_json(blinded.model_dump(mode="json")),
                )
            ],
        )
        return aggregate_verification(
            bundle=bundle, blinded=blinded, proposal=proposal, clock=clock
        )


@dataclass(frozen=True, slots=True)
class ContextRetryResult:
    verification: SupportVerification
    expansions: tuple[ContextExpansion, ...]
    verification_attempts: int
    expansion_rounds: int
    context_completeness: ContextCompleteness
    context_reasons: tuple[str, ...]
    verified_bundle: SupportEvidenceBundle


def _bounded_verification(
    verification: SupportVerification,
    *,
    expansions: Sequence[ContextExpansion],
    completeness: ContextCompleteness,
    reasons: tuple[str, ...],
) -> SupportVerification:
    payload = verification.model_dump(mode="python")
    payload["context_expansions"] = len(expansions)
    payload["context_completeness"] = completeness.value
    if completeness != ContextCompleteness.COMPLETE and verification.state in {
        SupportVerificationState.SUPPORTED,
        SupportVerificationState.PARTIALLY_SUPPORTED,
    }:
        needed = tuple(dict.fromkeys((*verification.context_needed, *reasons)))
        payload["state"] = SupportVerificationState.INSUFFICIENT_CONTEXT
        payload["context_needed"] = needed
        payload["verification_id"] = "ver_" + canonical_hash(
            {
                "original_verification_id": verification.verification_id,
                "context_completeness": completeness.value,
                "context_needed": list(needed),
                "expansion_ids": [
                    item.window_passage.passage_id
                    for item in expansions
                    if item.window_passage is not None
                ],
            }
        )
    return SupportVerification.model_validate(payload)


async def verify_with_context_retry(
    verifier: IndependentSupportVerifier,
    bundle: SupportEvidenceBundle,
    *,
    available_passages: Sequence[PassageRecord],
    max_expansions: int = 2,
    window_chars: int = DEFAULT_WINDOW_CHARS,
    clock: Callable[[], datetime] = utc_now,
) -> ContextRetryResult:
    """Verify, then expand same-source context only for INSUFFICIENT_CONTEXT.

    ``NOT_SUPPORTED``, ``PARTIALLY_SUPPORTED`` and ``CONTRADICTED`` results are
    final: nothing is retried merely to obtain a preferred answer. Expansion is
    bounded; when no wider window exists the insufficient result stands.
    """

    if max_expansions < 0 or window_chars < 1:
        raise ValueError("Retry bounds must be non-negative and positive")
    check_passage_integrity(bundle)
    current = bundle
    expansions: list[ContextExpansion] = []
    rounds = 0
    completeness = ContextCompleteness.UNKNOWN
    reasons: tuple[str, ...] = ("Context precheck was not run within the expansion budget",)
    if max_expansions > 0:
        rounds = 1
        inspections = tuple(
            inspect_passage_context(
                passage,
                available_passages=available_passages,
                attempt=1,
                window_chars=window_chars,
                clock=clock,
            )
            for passage in bundle.passages
        )
        precheck = tuple(item for inspection in inspections for item in inspection.expansions)
        expansions.extend(precheck)
        statuses = {inspection.completeness for inspection in inspections}
        completeness = next(
            (
                status
                for status in (
                    ContextCompleteness.TRUNCATED,
                    ContextCompleteness.UNKNOWN,
                    ContextCompleteness.UNAVAILABLE,
                )
                if status in statuses
            ),
            ContextCompleteness.COMPLETE,
        )
        reasons = tuple(
            dict.fromkeys(
                inspection.reason
                for inspection in inspections
                if inspection.completeness != ContextCompleteness.COMPLETE
            )
        )
        if any(expansion.available for expansion in precheck):
            current = expanded_bundle(bundle, precheck, attempt=1, clock=clock)
    attempts = 0
    while True:
        attempts += 1
        verification = await verifier.verify(current, clock=clock)
        if verification.state != SupportVerificationState.INSUFFICIENT_CONTEXT:
            return ContextRetryResult(
                verification=_bounded_verification(
                    verification,
                    expansions=expansions,
                    completeness=completeness,
                    reasons=reasons,
                ),
                expansions=tuple(expansions),
                verification_attempts=attempts,
                expansion_rounds=rounds,
                context_completeness=completeness,
                context_reasons=reasons,
                verified_bundle=current,
            )
        if rounds >= max_expansions:
            return ContextRetryResult(
                verification=_bounded_verification(
                    verification,
                    expansions=expansions,
                    completeness=completeness,
                    reasons=reasons,
                ),
                expansions=tuple(expansions),
                verification_attempts=attempts,
                expansion_rounds=rounds,
                context_completeness=completeness,
                context_reasons=reasons,
                verified_bundle=current,
            )
        skip = {expansion.origin_passage_id for expansion in expansions}
        new_expansions = tuple(
            expansion
            for passage in current.passages
            if passage.passage_id not in skip and passage.locator.label != "context-window"
            for expansion in inspect_passage_context(
                passage,
                available_passages=available_passages,
                attempt=rounds + 1,
                window_chars=window_chars,
                clock=clock,
            ).expansions
        )
        expansions.extend(new_expansions)
        rounds += 1
        if not any(expansion.available for expansion in new_expansions):
            return ContextRetryResult(
                verification=_bounded_verification(
                    verification,
                    expansions=expansions,
                    completeness=completeness,
                    reasons=reasons,
                ),
                expansions=tuple(expansions),
                verification_attempts=attempts,
                expansion_rounds=rounds,
                context_completeness=completeness,
                context_reasons=reasons,
                verified_bundle=current,
            )
        current = expanded_bundle(current, new_expansions, attempt=rounds, clock=clock)


__all__ = [
    "ContextRetryResult",
    "IndependentSupportVerifier",
    "PassageIntegrityError",
    "SupportVerificationState",
    "VerificationValidationError",
    "VERIFIER_TASK",
    "verify_with_context_retry",
]
