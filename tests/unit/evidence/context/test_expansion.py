from datetime import UTC, datetime

import pytest

from novelty_harness.evidence.context.expansion import (
    expand_passage_context,
    expanded_bundle,
)
from novelty_harness.evidence.context.selection import (
    PassageSelectionError,
    SupportEvidenceBundle,
)
from novelty_harness.evidence.passages.models import PassageLocator, PassageLocatorKind
from tests.fixtures.phase5 import make_passage, phase5_provenance

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
ORIGIN = phase5_provenance("expansion-test")
VERSION = "srcv_1_v1"


def inner(text: str = "The method is effective."):
    return make_passage(
        "src_1",
        text=text,
        passage_id="pass_inner",
        source_version_id=VERSION,
        provenance=ORIGIN,
    )


def document(text: str, *, source_id: str = "src_1", version: str | None = VERSION):
    return make_passage(
        source_id,
        text=text,
        passage_id="pass_document",
        source_version_id=version,
        provenance=ORIGIN,
    )


def bundle_for(passage):
    from novelty_harness.evidence.mapping.models import (
        ComparisonDimension,
        EvidenceProposition,
        PropositionCommitment,
    )
    from novelty_harness.evidence.verification.models import PassageSupportClaim

    proposition = EvidenceProposition(
        proposition_id="prop_1",
        mcu_id="mcu_1",
        statement="The method is effective",
        commitments=(
            PropositionCommitment(
                commitment_id="outcome",
                dimension=ComparisonDimension.INTENDED_OUTCOME,
                text="The method is effective",
            ),
        ),
        provenance=ORIGIN,
    )
    claim = PassageSupportClaim(
        claim_id="claim_1",
        mapping_id="map_1",
        source_id=passage.source_id,
        source_version_id=passage.source_version_id,
        mcu_id="mcu_1",
        proposition_id=proposition.proposition_id,
        proposition_statement=proposition.statement,
        commitments=proposition.commitments,
        claimed_dimensions=(ComparisonDimension.INTENDED_OUTCOME,),
        passage_ids=(passage.passage_id,),
    )
    return SupportEvidenceBundle(claim=claim, passages=(passage,))


def test_following_qualifier_is_brought_into_context() -> None:
    target = inner()
    full = document("The method is effective. However, in all tested cases it failed after a week.")
    expansion = expand_passage_context(
        target, available_passages=(target, full), attempt=1, clock=lambda: NOW
    )
    assert expansion.available and expansion.window_passage is not None
    assert expansion.origin_passage_id == "pass_inner"
    assert "However" in expansion.window_passage.text
    assert target.text in expansion.window_passage.text
    assert expansion.window_passage.source_version_id == VERSION
    assert expansion.window_passage.locator.kind == PassageLocatorKind.BLOCK
    assert expansion.window_passage.locator.label == "context-window"


def test_preceding_negation_is_brought_into_context() -> None:
    target = inner()
    full = document(
        "No independent study demonstrated this. The method is effective. "
        "The claim remains unverified."
    )
    expansion = expand_passage_context(
        target, available_passages=(target, full), attempt=1, clock=lambda: NOW
    )
    assert expansion.available and expansion.window_passage is not None
    assert "No independent study" in expansion.window_passage.text
    assert "remains unverified" in expansion.window_passage.text


def test_context_never_crosses_source_or_version() -> None:
    target = inner()
    other_version = document("The method is effective. However it failed.", version="srcv_other")
    other_source = document("The method is effective. However it failed.", source_id="src_other")
    for outsider in (other_version, other_source):
        expansion = expand_passage_context(
            target, available_passages=(target, outsider), attempt=1, clock=lambda: NOW
        )
        assert not expansion.available
        assert expansion.blocked_reason is not None
        assert expansion.window_passage is None


def test_no_wider_context_is_explicitly_blocked() -> None:
    target = inner()
    expansion = expand_passage_context(
        target, available_passages=(target,), attempt=2, clock=lambda: NOW
    )
    assert not expansion.available
    assert expansion.attempt == 2
    assert "No wider same-source" in str(expansion.blocked_reason)
    assert expansion.window_passage is None


def test_expansion_window_is_bounded_and_deterministic() -> None:
    target = inner()
    full = document("prelude " * 200 + target.text + " aftermath" * 200)
    first = expand_passage_context(
        target, available_passages=(target, full), attempt=1, window_chars=50, clock=lambda: NOW
    )
    second = expand_passage_context(
        target, available_passages=(full, target), attempt=1, window_chars=50, clock=lambda: NOW
    )
    assert first == second
    assert first.window_passage is not None
    assert len(first.window_passage.text) <= len(target.text) + 100


def test_repeated_text_expands_the_located_occurrence() -> None:
    text = (
        "The method is effective. An unrelated first observation. "
        "The method is effective. However, the second observation failed."
    )
    position = text.rfind("The method is effective.")
    target = inner().model_copy(
        update={
            "locator": PassageLocator(
                kind=PassageLocatorKind.BLOCK,
                char_start=position,
                char_end=position + len("The method is effective."),
            )
        }
    )
    outer = document(text).model_copy(
        update={
            "locator": PassageLocator(
                kind=PassageLocatorKind.RESOLVED_CONTENT,
                char_start=0,
                char_end=len(text),
            )
        }
    )
    expansion = expand_passage_context(
        target, available_passages=(target, outer), attempt=1, window_chars=55, clock=lambda: NOW
    )
    assert expansion.window_passage is not None
    assert "second observation failed" in expansion.window_passage.text
    assert expansion.window_passage.locator.char_start is not None
    assert expansion.window_passage.locator.char_start <= position


def test_repeated_text_without_locator_does_not_guess_occurrence() -> None:
    target = inner()
    outer = document(target.text + " First case. " + target.text + " Second case failed.")
    expansion = expand_passage_context(
        target, available_passages=(target, outer), attempt=1, window_chars=25, clock=lambda: NOW
    )
    assert not expansion.available
    assert "ambiguous" in str(expansion.blocked_reason).lower()


def test_bounded_window_discloses_truncated_known_context() -> None:
    from novelty_harness.evidence.context.expansion import inspect_passage_context

    target = inner()
    full = document(target.text + " " + "filler " * 20 + "However, it failed.")
    inspection = inspect_passage_context(
        target, available_passages=(target, full), attempt=1, window_chars=20, clock=lambda: NOW
    )
    assert inspection.completeness == "TRUNCATED"
    assert len(inspection.expansions) == 1
    assert inspection.expansions[0].window_passage is not None
    assert "However" not in inspection.expansions[0].window_passage.text


def test_entire_stored_context_is_explicitly_complete() -> None:
    from novelty_harness.evidence.context.expansion import inspect_passage_context

    target = inner()
    full = document(target.text + " However, it failed.")
    inspection = inspect_passage_context(
        target, available_passages=(target, full), attempt=1, clock=lambda: NOW
    )
    assert inspection.completeness == "COMPLETE"
    assert inspection.expansions[0].window_passage is not None
    assert "However" in inspection.expansions[0].window_passage.text


def test_no_stored_context_is_unavailable_not_complete() -> None:
    from novelty_harness.evidence.context.expansion import inspect_passage_context

    target = inner()
    inspection = inspect_passage_context(
        target, available_passages=(target,), attempt=1, clock=lambda: NOW
    )
    assert inspection.completeness == "UNAVAILABLE"
    assert not inspection.expansions[0].available


def test_full_resolved_content_with_complete_span_needs_no_expansion() -> None:
    from novelty_harness.evidence.context.expansion import inspect_passage_context

    text = "The full source text states the entire mechanism."
    target = document(text).model_copy(
        update={
            "locator": PassageLocator(
                kind=PassageLocatorKind.RESOLVED_CONTENT, char_start=0, char_end=len(text)
            )
        }
    )
    inspection = inspect_passage_context(
        target, available_passages=(target,), attempt=1, clock=lambda: NOW
    )
    assert inspection.completeness == "COMPLETE"


def test_located_same_version_neighbor_is_supplied_as_exact_passage() -> None:
    from novelty_harness.evidence.context.expansion import inspect_passage_context

    target = inner().model_copy(
        update={
            "locator": PassageLocator(
                kind=PassageLocatorKind.BLOCK,
                char_start=0,
                char_end=len(inner().text),
            )
        }
    )
    neighbor_text = "However, it failed in all cases."
    neighbor = document(neighbor_text).model_copy(
        update={
            "locator": PassageLocator(
                kind=PassageLocatorKind.BLOCK,
                char_start=len(target.text),
                char_end=len(target.text) + len(neighbor_text),
            )
        }
    )
    inspection = inspect_passage_context(
        target,
        available_passages=(target, neighbor),
        attempt=1,
        clock=lambda: NOW,
    )
    assert inspection.completeness == "COMPLETE"
    assert tuple(item.window_passage for item in inspection.expansions) == (neighbor,)


def test_unlocated_repeated_excerpt_has_unknown_completeness() -> None:
    from novelty_harness.evidence.context.expansion import inspect_passage_context

    target = inner()
    full = document(target.text + " First case. " + target.text + " Second case failed.")
    inspection = inspect_passage_context(
        target, available_passages=(target, full), attempt=1, clock=lambda: NOW
    )
    assert inspection.completeness == "UNKNOWN"
    assert not inspection.expansions[0].available


def test_expanded_bundle_keeps_origin_and_window_passages() -> None:
    target = inner()
    full = document("The method is effective. However, it later failed.")
    expansion = expand_passage_context(
        target, available_passages=(target, full), attempt=1, clock=lambda: NOW
    )
    expanded = expanded_bundle(bundle_for(target), (expansion,), attempt=1, clock=lambda: NOW)
    ids = [passage.passage_id for passage in expanded.passages]
    assert ids[0] == "pass_inner" and len(ids) == 2
    assert expanded.claim.passage_ids == tuple(ids)
    assert expanded.claim.claim_id != "claim_1"
    assert any("expanded same-source context" in item for item in expanded.limitations)


def test_expanded_bundle_requires_an_available_window() -> None:
    target = inner()
    blocked = expand_passage_context(
        target, available_passages=(target,), attempt=1, clock=lambda: NOW
    )
    with pytest.raises(PassageSelectionError):
        expanded_bundle(bundle_for(target), (blocked,), attempt=1, clock=lambda: NOW)
