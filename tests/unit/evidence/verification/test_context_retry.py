import json
from datetime import UTC, datetime

from novelty_harness.domain.enums import SupportVerificationState
from novelty_harness.evidence.verification.prompts import VERIFIER_PROMPT_VERSION
from novelty_harness.evidence.verification.verifier import (
    VERIFIER_TASK,
    IndependentSupportVerifier,
    verify_with_context_retry,
)
from novelty_harness.runtime.semantic.structured import SemanticRunner
from tests.fixtures.phase5 import make_passage
from tests.fixtures.phase6 import StubLLMProvider, context_payload
from tests.unit.evidence.verification.test_verifier import (
    MECHANISM,
    OUTCOME,
    bundle,
)

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
VERSION = "srcv_1_v1"
CLAIM_TEXT = "A threshold drives a relay coil and the load switches."


def judgments(*states: tuple[str, str]) -> dict[str, object]:
    return {
        "prompt_version": VERIFIER_PROMPT_VERSION,
        "judgments": [
            {
                "commitment_id": commitment_id,
                "state": state,
                "rationale": f"judgment for {commitment_id}",
                "passage_ids": ["pass_1"],
            }
            for commitment_id, state in states
        ],
        "context_needed": ["the following qualifier sentence"],
    }


def expanded_document(*extra: str):
    text = CLAIM_TEXT + " " + " ".join(extra)
    return make_passage(
        "src_1",
        text=text,
        passage_id="pass_document",
        source_version_id=VERSION,
    )


def qualifier_aware_response(context) -> dict[str, object]:
    payload = json.loads(str(context_payload(context, "verification_input")))
    expanded = any(passage["locator"] == "BLOCK" for passage in payload["passages"])
    if expanded and any("However" in passage["text"] for passage in payload["passages"]):
        return judgments(("mech", "SUPPORTED"), ("outcome", "CONTRADICTED"))
    if expanded:
        return judgments(("mech", "SUPPORTED"), ("outcome", "SUPPORTED"))
    return judgments(("mech", "SUPPORTED"), ("outcome", "INSUFFICIENT"))


def retry_verifier(response) -> IndependentSupportVerifier:
    return IndependentSupportVerifier(SemanticRunner(StubLLMProvider({VERIFIER_TASK: response})))


async def test_insufficient_context_then_supported_after_same_source_expansion() -> None:
    target = bundle(CLAIM_TEXT)
    document = expanded_document("Additional detail supports the same claim.")
    result = await verify_with_context_retry(
        retry_verifier(qualifier_aware_response),
        target,
        available_passages=(target.passages[0], document),
        clock=lambda: NOW,
    )
    # The F03 completeness precheck supplies the bounded window before the
    # first judgment, so a single verification already sees the full context.
    assert result.verification.state == SupportVerificationState.SUPPORTED
    assert result.verification_attempts == 1
    assert result.verification.context_expansions == 1
    assert len(result.expansions) == 1 and result.expansions[0].available
    window = result.expansions[0].window_passage
    assert window is not None and "Additional detail" in window.text
    assert result.verification.relied_on_passage_ids  # includes the expanded window


async def test_expansion_can_reveal_a_contradiction() -> None:
    target = bundle(CLAIM_TEXT)
    document = expanded_document("However, the operator must always switch it manually.")
    result = await verify_with_context_retry(
        retry_verifier(qualifier_aware_response),
        target,
        available_passages=(target.passages[0], document),
        clock=lambda: NOW,
    )
    assert result.verification.state == SupportVerificationState.CONTRADICTED
    assert result.verification_attempts == 1
    assert result.expansions[0].available
    assert any(
        "However" in item or OUTCOME.text in item for item in result.verification.contradictions
    )


async def test_no_available_context_leaves_explicit_insufficient_state() -> None:
    target = bundle(CLAIM_TEXT)
    result = await verify_with_context_retry(
        retry_verifier(qualifier_aware_response),
        target,
        available_passages=(target.passages[0],),
        clock=lambda: NOW,
    )
    assert result.verification.state == SupportVerificationState.INSUFFICIENT_CONTEXT
    assert result.verification_attempts == 1
    assert len(result.expansions) == 1 and not result.expansions[0].available
    assert result.expansions[0].blocked_reason is not None


async def test_unsupported_and_partial_results_are_never_retried() -> None:
    for state in ("NOT_SUPPORTED", "PARTIALLY_SUPPORTED", "CONTRADICTED"):
        with_states = {
            "NOT_SUPPORTED": (("mech", "NOT_SUPPORTED"), ("outcome", "NOT_SUPPORTED")),
            "PARTIALLY_SUPPORTED": (("mech", "SUPPORTED"), ("outcome", "NOT_SUPPORTED")),
            "CONTRADICTED": (("mech", "SUPPORTED"), ("outcome", "CONTRADICTED")),
        }[state]
        target = bundle(CLAIM_TEXT)
        document = expanded_document("More text.")
        result = await verify_with_context_retry(
            retry_verifier(judgments(*with_states)),
            target,
            available_passages=(target.passages[0], document),
            clock=lambda: NOW,
        )
        assert result.verification.state.value == state
        assert result.verification_attempts == 1
        # Only the precheck expansion may be recorded; no retry round runs.
        assert len(result.expansions) <= 1


async def test_retry_cap_is_enforced() -> None:
    always_insufficient = {
        "prompt_version": VERIFIER_PROMPT_VERSION,
        "judgments": [
            {
                "commitment_id": MECHANISM.commitment_id,
                "state": "SUPPORTED",
                "rationale": "still insufficient for outcome",
                "passage_ids": ["pass_1"],
            },
            {
                "commitment_id": OUTCOME.commitment_id,
                "state": "INSUFFICIENT",
                "rationale": "no context yet",
                "passage_ids": ["pass_1"],
            },
        ],
        "context_needed": ["more context"],
    }
    target = bundle(CLAIM_TEXT)
    document = expanded_document("Even more text without the needed qualifier.")
    result = await verify_with_context_retry(
        retry_verifier(always_insufficient),
        target,
        available_passages=(target.passages[0], document),
        max_expansions=1,
        clock=lambda: NOW,
    )
    assert result.verification.state == SupportVerificationState.INSUFFICIENT_CONTEXT
    assert result.verification_attempts == 1
    assert result.expansion_rounds == 1
    assert len(result.expansions) == 1

    capped = await verify_with_context_retry(
        retry_verifier(always_insufficient),
        bundle(CLAIM_TEXT),
        available_passages=(bundle(CLAIM_TEXT).passages[0], document),
        max_expansions=0,
        clock=lambda: NOW,
    )
    assert capped.verification.state == SupportVerificationState.INSUFFICIENT_CONTEXT
    assert capped.expansion_rounds == 0
    assert capped.expansions == ()


async def test_qualifier_beyond_window_cannot_leave_support_decisive() -> None:
    target = bundle(CLAIM_TEXT)
    document = expanded_document(*(["filler"] * 20), "However, the operator switches manually.")
    result = await verify_with_context_retry(
        retry_verifier(qualifier_aware_response),
        target,
        available_passages=(target.passages[0], document),
        window_chars=20,
        clock=lambda: NOW,
    )
    assert result.context_completeness == "TRUNCATED"
    assert result.verification.state == SupportVerificationState.INSUFFICIENT_CONTEXT
    assert any("truncated" in reason.lower() for reason in result.verification.context_needed)


async def test_zero_expansion_budget_cannot_make_short_excerpt_decisive() -> None:
    target = bundle(CLAIM_TEXT)
    result = await verify_with_context_retry(
        retry_verifier(judgments(("mech", "SUPPORTED"), ("outcome", "SUPPORTED"))),
        target,
        available_passages=(
            target.passages[0],
            expanded_document("However, the operator switches manually."),
        ),
        max_expansions=0,
        clock=lambda: NOW,
    )
    assert result.context_completeness == "UNKNOWN"
    assert result.verification.state == SupportVerificationState.INSUFFICIENT_CONTEXT
    assert result.expansion_rounds == 0


async def test_unavailable_context_does_not_count_as_complete() -> None:
    target = bundle(CLAIM_TEXT)
    result = await verify_with_context_retry(
        retry_verifier(judgments(("mech", "SUPPORTED"), ("outcome", "SUPPORTED"))),
        target,
        available_passages=(target.passages[0],),
        clock=lambda: NOW,
    )
    assert result.context_completeness == "UNAVAILABLE"
    assert result.verification.state == SupportVerificationState.INSUFFICIENT_CONTEXT


async def test_adjacent_same_version_qualifier_reaches_initial_verifier() -> None:
    from novelty_harness.evidence.passages.models import PassageLocator, PassageLocatorKind

    target = bundle(CLAIM_TEXT)
    passage = target.passages[0].model_copy(
        update={
            "locator": PassageLocator(
                kind=PassageLocatorKind.BLOCK, char_start=0, char_end=len(CLAIM_TEXT)
            )
        }
    )
    target = target.model_copy(update={"passages": (passage,)})
    qualifier = "However, the operator switches manually."
    neighbor = make_passage(
        "src_1",
        text=qualifier,
        passage_id="pass_neighbor",
        source_version_id=VERSION,
        locator=PassageLocator(
            kind=PassageLocatorKind.BLOCK,
            char_start=len(CLAIM_TEXT),
            char_end=len(CLAIM_TEXT) + len(qualifier),
        ),
    )

    def response(context) -> dict[str, object]:
        payload = json.loads(str(context_payload(context, "verification_input")))
        seen = {item["passage_id"]: item["text"] for item in payload["passages"]}
        assert seen["pass_neighbor"] == qualifier
        return judgments(("mech", "SUPPORTED"), ("outcome", "CONTRADICTED"))

    result = await verify_with_context_retry(
        retry_verifier(response),
        target,
        available_passages=(passage, neighbor),
        clock=lambda: NOW,
    )
    assert result.context_completeness == "COMPLETE"
    assert result.verification.state == SupportVerificationState.CONTRADICTED
    assert result.verification_attempts == 1
