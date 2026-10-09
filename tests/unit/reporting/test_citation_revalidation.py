"""Citation snapshot controls; synthetic shapes never confer native authority."""

import gc
import tracemalloc

import pytest
from pydantic import ValidationError

from novelty_harness.reporting.citations import CitationRegistry, validate_citation_registry
from novelty_harness.reporting.models import ReportProposalError
from tests.unit.reporting.test_ir_revalidation import shape_ir_with_basis


def test_citation_validation_bounds_wire_and_normalized_basis_retention(
    monkeypatch, record_property
):
    from novelty_harness.reporting import citations

    proposed = shape_ir_with_basis(count=32).citation_registry
    seen = []

    def expected(sections, bundle):
        seen.append((sections, bundle))
        return proposed

    monkeypatch.setattr(citations, "build_citation_registry", expected)
    gc.collect()
    tracemalloc.start()
    try:
        validate_citation_registry(proposed, (), None)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    record_property("citation_validation_snapshot_peak", peak)
    payload_bytes = sum(len(link.proposition) for link in proposed.claim_basis_links)
    assert seen == [((), None)]
    # All occurrences still parse. Retain only private models/equal immutable
    # text and one item wire, rather than the entire wire plus text copies.
    assert peak < payload_bytes * 0.6, (peak, payload_bytes)


def test_citation_snapshot_matches_original_strict_roundtrip():
    from novelty_harness.reporting.citations import _revalidate_citation_registry

    proposed = shape_ir_with_basis(count=3).citation_registry
    expected = CitationRegistry.model_validate_json(proposed.model_dump_json(), strict=True)
    actual = _revalidate_citation_registry(proposed)
    assert actual == expected
    assert actual.model_dump_json() == expected.model_dump_json()
    assert actual is not proposed
    assert actual.claim_basis_links[0] is not proposed.claim_basis_links[0]


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", "unknown"),
        ("compilation_id", " "),
        ("citations", (42,)),
        ("claim_basis_links", (42,)),
    ],
)
def test_citation_snapshot_keeps_strict_field_rejection(field, value):
    from novelty_harness.reporting.citations import _revalidate_citation_registry

    proposed = shape_ir_with_basis(count=2).citation_registry.model_copy(update={field: value})
    with pytest.raises(ValidationError):
        CitationRegistry.model_validate_json(proposed.model_dump_json(), strict=True)
    with pytest.raises(ValidationError):
        _revalidate_citation_registry(proposed)


def test_citation_snapshot_preserves_duplicates_order_and_divergence():
    from novelty_harness.reporting.citations import _revalidate_citation_registry

    proposed = shape_ir_with_basis(count=3).citation_registry
    links = proposed.claim_basis_links
    altered = links[1].model_copy(update={"proposition": "Changed meaning"})
    proposed = proposed.model_copy(
        update={"claim_basis_links": (links[2], altered, links[2], links[0])}
    )
    actual = _revalidate_citation_registry(proposed)
    expected = CitationRegistry.model_validate_json(proposed.model_dump_json(), strict=True)
    assert actual.model_dump_json() == expected.model_dump_json()
    assert len(actual.claim_basis_links) == 4
    assert actual.claim_basis_links[1].proposition == "Changed meaning"


def test_citation_snapshot_keeps_subclass_extras_and_nested_scope_rejection():
    from novelty_harness.reporting.citations import _revalidate_citation_registry

    class ExtraRegistry(CitationRegistry):
        unauthorized: str = "must not be projected away"

    proposed = shape_ir_with_basis(count=1).citation_registry
    extra = ExtraRegistry.model_validate(proposed.model_dump())
    with pytest.raises(ValidationError):
        _revalidate_citation_registry(extra)
    corrupted = proposed.claim_basis_links[0].model_copy(update={"scope": {"unknown": "scope"}})
    with pytest.raises(ValidationError):
        _revalidate_citation_registry(
            proposed.model_copy(update={"claim_basis_links": (corrupted,)})
        )


def test_citation_validation_still_recomputes_and_compares_complete_registry(monkeypatch):
    from novelty_harness.reporting import citations

    proposed = shape_ir_with_basis(count=2).citation_registry
    changed = proposed.model_copy(
        update={"claim_basis_links": tuple(reversed(proposed.claim_basis_links))}
    )
    calls = []

    def expected(sections, bundle):
        calls.append((sections, bundle))
        return changed

    monkeypatch.setattr(citations, "build_citation_registry", expected)
    with pytest.raises(ReportProposalError, match="exact accepted claim ancestry"):
        validate_citation_registry(proposed, (), None)
    assert calls == [((), None)]


@pytest.mark.parametrize("field", ["claim_basis_links", "citations", "scope"])
def test_citation_missing_required_caller_field_keeps_strict_rejection(field):
    from novelty_harness.reporting.citations import _revalidate_citation_registry

    proposed = shape_ir_with_basis(count=1).citation_registry
    proposed.__dict__.pop(field)  # Deliberately malformed untrusted caller.
    with pytest.raises(ValidationError):
        CitationRegistry.model_validate_json(proposed.model_dump_json(), strict=True)
    with pytest.raises(ValidationError):
        _revalidate_citation_registry(proposed)
    with pytest.raises(ReportProposalError, match="serialized validation"):
        validate_citation_registry(proposed, (), None)
