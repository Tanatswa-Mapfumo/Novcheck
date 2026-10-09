"""Strict serialized IR shapes and bounded copying; shapes confer no authority."""

import gc
import tracemalloc
from datetime import date

import pytest
from pydantic import ValidationError

from novelty_harness.reporting.ir import ReportIR


def shape_ir():
    from novelty_harness.adjudication.frozen import OverallFinding
    from novelty_harness.evidence.graph.assessment_ledger import Phase6CoverageLedger
    from novelty_harness.reporting.citations import CitationRegistry
    from novelty_harness.reporting.ir import ReportGenerationProvenance
    from tests.unit.reporting.test_contracts import _compilation

    compilation = _compilation()
    scope = compilation.scope
    empty = {
        name: ()
        for name in (
            "target_findings",
            "sections",
            "material_claims",
            "claim_basis_links",
            "verification_refs",
            "coverage_obligations",
            "coverage_satisfaction",
            "uncertainty_summary",
            "supported_and_qualified_wording",
            "unsupported_wording_examples",
            "validation_requirements",
            "value_availability",
            "report_limitations",
            "source_dependency_manifest",
            "report_artifact_dependencies",
        )
    }
    return ReportIR(
        scope=scope,
        compilation_id=compilation.compilation_id,
        as_of=date(2026, 10, 5),
        bundle_digest=compilation.bundle_digest,
        overall_finding=OverallFinding(
            assessment_id=scope.assessment_id,
            assessment_context_id=scope.assessment_context_id,
            phase6_snapshot_id=scope.phase6_snapshot_id,
            verdict="UNASSESSABLE",
            target_ids=(),
        ),
        citation_registry=CitationRegistry(
            scope=scope,
            compilation_id=compilation.compilation_id,
            citations=(),
            claim_basis_links=(),
        ),
        coverage_summary=Phase6CoverageLedger(),
        compact_summary=None,
        generation_provenance=ReportGenerationProvenance(
            scope=scope,
            compilation_id=compilation.compilation_id,
            options=compilation.options,
            configuration=compilation.configuration,
            approved_versions=compilation.configuration.deterministic_versions,
            method_refs=(),
            configuration_refs=(),
            execution_refs=(),
        ),
        **empty,
    )


def test_bounded_ir_roundtrip_matches_complete_strict_roundtrip():
    from novelty_harness.reporting.ir import _revalidate_report_ir

    proposed = shape_ir()
    expected = ReportIR.model_validate_json(proposed.model_dump_json(), strict=True)
    actual = _revalidate_report_ir(proposed)
    assert actual == expected
    assert actual.model_dump_json() == expected.model_dump_json()
    assert actual is not proposed


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", "unknown"),
        ("bundle_digest", "wrong"),
        ("compilation_id", " "),
        ("as_of", 42),
        ("report_limitations", (True,)),
    ],
)
def test_bounded_ir_roundtrip_preserves_strict_field_rejection(field, value):
    from novelty_harness.reporting.ir import _revalidate_report_ir

    proposed = shape_ir().model_copy(update={field: value})
    with pytest.raises(ValidationError):
        ReportIR.model_validate_json(proposed.model_dump_json(), strict=True)
    with pytest.raises(ValidationError):
        _revalidate_report_ir(proposed)


def test_bounded_ir_roundtrip_keeps_nested_model_validators():
    from novelty_harness.reporting.ir import _revalidate_report_ir

    proposed = shape_ir()
    proposed = proposed.model_copy(
        update={
            "coverage_summary": proposed.coverage_summary.model_copy(
                update={"selected_source_ids": ("src_duplicate", "src_duplicate")}
            )
        }
    )
    with pytest.raises(ValidationError, match="unique"):
        _revalidate_report_ir(proposed)


def test_bounded_ir_roundtrip_does_not_hide_subclass_serialized_extras():
    from novelty_harness.reporting.ir import _revalidate_report_ir

    class ExtraIR(ReportIR):
        extra_content: str = "must be rejected by the base contract"

    proposed = ExtraIR.model_validate(shape_ir().model_dump())
    with pytest.raises(ValidationError):
        _revalidate_report_ir(proposed)


def test_bounded_ir_roundtrip_peak_reduces_full_wire_retention(record_property):
    from novelty_harness.reporting.ir import _revalidate_report_ir

    proposed = shape_ir()
    repeated = ("x" * 65536,) * 128
    proposed = proposed.model_copy(
        update={
            "report_limitations": repeated,
            "coverage_summary": proposed.coverage_summary.model_copy(
                update={"limitations": repeated}
            ),
            "overall_finding": proposed.overall_finding.model_copy(
                update={"limiting_factors": repeated}
            ),
        }
    )
    peaks = []
    for load in (
        lambda value: ReportIR.model_validate_json(value.model_dump_json(), strict=True),
        _revalidate_report_ir,
    ):
        gc.collect()
        tracemalloc.start()
        try:
            result = load(proposed)
            peaks.append(tracemalloc.get_traced_memory()[1])
        finally:
            tracemalloc.stop()
        assert result == proposed
        del result
    record_property("original_ir_roundtrip_peak", peaks[0])
    record_property("bounded_ir_roundtrip_peak", peaks[1])
    assert peaks[1] < peaks[0] * 0.85, peaks


def shape_ir_with_basis(count=128):
    from novelty_harness.reporting.claims import ClaimBasisLink
    from novelty_harness.reporting.drafts import DraftBlock
    from novelty_harness.reporting.ir import AcceptedBlock, ReportSection
    from novelty_harness.reporting.models import AuthorityRef
    from novelty_harness.reporting.plan import QuestionPlan

    proposed = shape_ir()
    links = tuple(
        ClaimBasisLink(
            scope=proposed.scope,
            compilation_id=proposed.compilation_id,
            claim_id=f"claim_{index}",
            proposition="record " + "x" * 65536,
            use="ASSERTION",
            authority_ref=AuthorityRef(
                kind="FROZEN", native_id="frozen_shape", digest="a" * 64, scope=proposed.scope
            ),
        )
        for index in range(count)
    )
    block = AcceptedBlock(
        scope=proposed.scope,
        compilation_id=proposed.compilation_id,
        draft_block=DraftBlock(block_id="block", kind="PARAGRAPH", text="Shape only"),
        claims=(),
        basis_links=links,
        verification_refs=(),
        obligation_satisfaction=(),
        origin="DETERMINISTIC_FALLBACK",
        source_artifact_refs=(),
    )
    section = ReportSection(
        scope=proposed.scope,
        compilation_id=proposed.compilation_id,
        question_id=1,
        question_label="Shape only",
        question_plan=QuestionPlan(
            question_id=1,
            analytical_thesis="Shape only",
            subsections=(),
            target_ids=(),
            evidence_refs=(),
            adjudication_refs=(),
            required_limitation_refs=(),
            obligation_ids=(),
        ),
        blocks=(block,),
    )
    return proposed.model_copy(
        update={
            "sections": (section,),
            "claim_basis_links": links,
            "citation_registry": proposed.citation_registry.model_copy(
                update={"claim_basis_links": links}
            ),
        }
    )


def test_ir_roundtrip_sharing_never_repairs_divergent_global_basis():
    from novelty_harness.reporting.ir import _revalidate_report_ir

    proposed = shape_ir_with_basis(count=3)
    changed = proposed.claim_basis_links[0].model_copy(update={"proposition": "Different meaning"})
    proposed = proposed.model_copy(
        update={"claim_basis_links": (changed, *proposed.claim_basis_links[1:])}
    )
    actual = _revalidate_report_ir(proposed)
    expected = ReportIR.model_validate_json(proposed.model_dump_json(), strict=True)
    for name in ReportIR.model_fields:
        assert actual.model_dump_json(include={name}) == expected.model_dump_json(include={name})
    assert actual.claim_basis_links[0].proposition == "Different meaning"
    assert actual.sections[0].blocks[0].basis_links[0].proposition != "Different meaning"


def test_ir_roundtrip_does_not_retain_duplicate_validated_global_basis(record_property):
    from novelty_harness.reporting.ir import _revalidate_report_ir

    proposed = shape_ir_with_basis()
    gc.collect()
    tracemalloc.start()
    try:
        actual = _revalidate_report_ir(proposed)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    record_property("shared_ir_roundtrip_peak", peak)
    # Three unchanged v1 projections stay on wire. Retain two validated copies
    # plus one-field temporary space, with no extra global proposition copy.
    proposition_bytes = sum(len(link.proposition) for link in proposed.claim_basis_links)
    assert peak < proposition_bytes * 3.5, (peak, proposition_bytes)
    expected = ReportIR.model_validate_json(proposed.model_dump_json(), strict=True)
    for name in ReportIR.model_fields:
        assert actual.model_dump_json(include={name}) == expected.model_dump_json(include={name})


def test_ir_roundtrip_bounds_citation_basis_copy_retention(record_property):
    from novelty_harness.reporting.ir import _revalidate_report_ir

    proposed = shape_ir_with_basis()
    gc.collect()
    tracemalloc.start()
    try:
        actual = _revalidate_report_ir(proposed)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    record_property("citation_shared_roundtrip_peak", peak)
    proposition_bytes = sum(len(link.proposition) for link in proposed.claim_basis_links)
    assert peak < proposition_bytes * 2.75, (peak, proposition_bytes)
    assert actual.citation_registry == proposed.citation_registry


def test_ir_roundtrip_preserves_citation_basis_order_duplicates_and_differences():
    from novelty_harness.reporting.ir import _revalidate_report_ir

    proposed = shape_ir_with_basis(count=3)
    links = proposed.citation_registry.claim_basis_links
    changed = links[1].model_copy(update={"proposition": "Wrong citation proposition"})
    proposed = proposed.model_copy(
        update={
            "citation_registry": proposed.citation_registry.model_copy(
                update={"claim_basis_links": (links[2], links[0], links[0], changed)}
            )
        }
    )
    expected = ReportIR.model_validate_json(proposed.model_dump_json(), strict=True)
    actual = _revalidate_report_ir(proposed)
    assert actual.model_dump_json() == expected.model_dump_json()


def test_ir_roundtrip_bounds_section_array_wire_retention(record_property):
    from novelty_harness.reporting.ir import _revalidate_report_ir

    proposed = shape_ir_with_basis(count=4)
    section = proposed.sections[0]
    sections = tuple(
        section.model_copy(update={"question_id": question}) for question in range(1, 10)
    )
    proposed = proposed.model_copy(
        update={
            "sections": sections,
            "claim_basis_links": (),
            "citation_registry": proposed.citation_registry.model_copy(
                update={"claim_basis_links": ()}
            ),
        }
    )
    gc.collect()
    tracemalloc.start()
    try:
        actual = _revalidate_report_ir(proposed)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    record_property("section_roundtrip_peak", peak)
    proposition_bytes = 9 * sum(len(link.proposition) for link in section.blocks[0].basis_links)
    assert peak < proposition_bytes * 2, (peak, proposition_bytes)
    assert (
        actual.model_dump_json()
        == ReportIR.model_validate_json(proposed.model_dump_json(), strict=True).model_dump_json()
    )


@pytest.mark.parametrize("field", ["sections", "claim_basis_links", "citation_registry"])
def test_ir_missing_required_caller_fields_keep_strict_rejection(field):
    from novelty_harness.reporting.ir import _revalidate_report_ir, validate_report_ir
    from novelty_harness.reporting.models import ReportProposalError

    proposed = shape_ir()
    proposed.__dict__.pop(field)  # Deliberately malformed untrusted caller.
    with pytest.raises(ValidationError):
        ReportIR.model_validate_json(proposed.model_dump_json(), strict=True)
    with pytest.raises(ValidationError):
        _revalidate_report_ir(proposed)
    with pytest.raises(ReportProposalError, match="strict serialized validation"):
        validate_report_ir(proposed, None, None, ())


def test_ir_missing_nested_citation_basis_keeps_strict_rejection():
    from novelty_harness.reporting.ir import _revalidate_report_ir, validate_report_ir
    from novelty_harness.reporting.models import ReportProposalError

    proposed = shape_ir()
    proposed.citation_registry.__dict__.pop("claim_basis_links")
    with pytest.raises(ValidationError):
        ReportIR.model_validate_json(proposed.model_dump_json(), strict=True)
    with pytest.raises(ValidationError):
        _revalidate_report_ir(proposed)
    with pytest.raises(ReportProposalError, match="strict serialized validation"):
        validate_report_ir(proposed, None, None, ())
