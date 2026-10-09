"""Bounded caller wrapper snapshots preserve the original JSON contract."""

import gc
import tracemalloc

import pytest
from pydantic import ValidationError

from novelty_harness.reporting.ir import CompiledAssessmentReport
from tests.unit.reporting.test_ir_revalidation import shape_ir_with_basis
from tests.unit.reporting.test_rendering_digest import shape_report


def proposed_report():
    report = shape_report()
    return report.model_copy(update={"ir": shape_ir_with_basis(count=32)})


def test_compiled_snapshot_bounds_full_wire_and_duplicate_basis(record_property):
    from novelty_harness.reporting.ir import _revalidate_compiled_report

    proposed = proposed_report()
    functions = (
        lambda value: CompiledAssessmentReport.model_validate_json(value.model_dump_json()),
        _revalidate_compiled_report,
    )
    peaks, results = [], []
    for function in functions:
        gc.collect()
        tracemalloc.start()
        try:
            results.append(function(proposed))
            peaks.append(tracemalloc.get_traced_memory()[1])
        finally:
            tracemalloc.stop()
    record_property("original_compiled_snapshot_peak_bytes", peaks[0])
    record_property("bounded_compiled_snapshot_peak_bytes", peaks[1])
    assert results[0].model_dump_json() == results[1].model_dump_json()
    assert peaks[1] < peaks[0] * 0.5, peaks


def test_compiled_snapshot_keeps_original_coercion_and_nested_field_strictness():
    from novelty_harness.reporting.ir import _revalidate_compiled_report

    proposed = proposed_report()
    provenance = proposed.ir.generation_provenance
    options = provenance.options.model_copy(update={"compact_summary": "true"})
    provenance = provenance.model_copy(update={"options": options})
    proposed = proposed.model_copy(
        update={"ir": proposed.ir.model_copy(update={"generation_provenance": provenance})}
    )
    expected = CompiledAssessmentReport.model_validate_json(proposed.model_dump_json())
    actual = _revalidate_compiled_report(proposed)
    assert actual.model_dump_json() == expected.model_dump_json()
    assert actual.ir.generation_provenance.options.compact_summary is True
    # Do not accidentally override explicitly strict nested field metadata.
    original_section = proposed.ir.sections[0]
    bad_block = original_section.blocks[0].draft_block.model_copy(
        update={"kind": "TABLE_CELL", "table_id": "table", "row": "1", "column": 0}
    )
    block = original_section.blocks[0].model_copy(update={"draft_block": bad_block})
    bad_section = original_section.model_copy(update={"blocks": (block,)})
    corrupted = proposed.model_copy(
        update={"ir": proposed.ir.model_copy(update={"sections": (bad_section,)})}
    )
    with pytest.raises(ValidationError):
        CompiledAssessmentReport.model_validate_json(corrupted.model_dump_json())
    with pytest.raises(ValidationError):
        _revalidate_compiled_report(corrupted)


@pytest.mark.parametrize("field", ["ir", "scope", "accepted_at"])
def test_compiled_snapshot_rejects_missing_required_fields(field):
    from novelty_harness.reporting.ir import _revalidate_compiled_report

    proposed = proposed_report()
    proposed.__dict__.pop(field)
    with pytest.raises(ValidationError):
        CompiledAssessmentReport.model_validate_json(proposed.model_dump_json())
    with pytest.raises(ValidationError):
        _revalidate_compiled_report(proposed)


def test_compiled_snapshot_keeps_top_and_nested_subclass_wire_behavior():
    from novelty_harness.reporting.ir import ReportIR, _revalidate_compiled_report

    class ExtraReport(CompiledAssessmentReport):
        undeclared: str = "must be rejected"

    class ExtraIR(ReportIR):
        subclass_only: str = "original enclosing serializer projects declared IR fields"

    proposed = proposed_report()
    extra = ExtraReport.model_validate(proposed.model_dump())
    with pytest.raises(ValidationError):
        _revalidate_compiled_report(extra)
    nested = proposed.model_copy(update={"ir": ExtraIR.model_validate(proposed.ir.model_dump())})
    assert (
        _revalidate_compiled_report(nested).model_dump_json()
        == CompiledAssessmentReport.model_validate_json(nested.model_dump_json()).model_dump_json()
    )


def test_compiled_snapshot_never_adopts_mutable_caller_containers():
    from novelty_harness.reporting.ir import _revalidate_compiled_report

    proposed = proposed_report()
    actual = _revalidate_compiled_report(proposed)
    expected = actual.model_dump_json()
    proposed.ir.sections[0].blocks[0].__dict__["origin"] = "GENERATIVE_ACCEPTED"
    assert actual.model_dump_json() == expected
    assert actual.ir is not proposed.ir
    assert actual.ir.sections[0] is not proposed.ir.sections[0]


def test_repository_proposal_boundary_preserves_bounded_serialized_snapshot(record_property):
    from novelty_harness.evidence.graph.report_validation import _revalidate_proposal
    from novelty_harness.reporting.repository import ReportAuthorityError

    proposed = proposed_report()
    gc.collect()
    tracemalloc.start()
    try:
        actual = _revalidate_proposal(proposed)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    record_property("repository_proposal_snapshot_peak_bytes", peak)
    expected = CompiledAssessmentReport.model_validate_json(proposed.model_dump_json())
    assert actual.model_dump_json() == expected.model_dump_json()
    proposition_bytes = sum(len(link.proposition) for link in proposed.ir.claim_basis_links)
    assert peak < proposition_bytes * 3, (peak, proposition_bytes)
    with pytest.raises(ReportAuthorityError):
        _revalidate_proposal({"report_id": proposed.report_id, "accepted": True})
