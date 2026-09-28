"""Counterfactual-removal diagnostic (FR-EQ-004).

Removing the differentiating element/relationship localizes whatever
distinction remains. This is a diagnostic aid only: it never changes a
classification, verification state or verdict.
"""

from novelty_harness.evidence.precedent.models import (
    CounterfactualDiagnostic,
    PrecedentClassification,
)


def counterfactual_removal(
    classification: PrecedentClassification,
    *,
    element: str | None = None,
) -> CounterfactualDiagnostic:
    """Remove one differentiating element and report the remaining distinction."""

    differences = [
        *classification.missing_relationships,
        *classification.missing_elements,
    ]
    if classification.configuration_gap:
        differences.append(classification.configuration_gap)
    if not differences:
        return CounterfactualDiagnostic(
            removed_element=element or "no recorded differentiating element",
            remaining_distinction=None,
            becomes_substantially_equivalent=None,
            basis=(
                "The local classification records no material gap to remove",
                "Diagnostic only; no classification was changed",
            ),
        )
    removed = element or differences[0]
    if removed not in differences:
        raise ValueError("The removed element is not a recorded difference")
    remaining = [item for item in differences if item != removed]
    return CounterfactualDiagnostic(
        removed_element=removed,
        remaining_distinction="; ".join(remaining) if remaining else None,
        becomes_substantially_equivalent=not remaining,
        basis=(
            "Removed one differentiating element/relationship from the recorded gaps",
            "Diagnostic only; mapping, verification and classification are unchanged",
        ),
    )


__all__ = ["counterfactual_removal"]
