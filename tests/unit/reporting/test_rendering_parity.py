"""Complete format parity with no simultaneous expected rendition bundle."""

import json
from dataclasses import replace

import pytest
import yaml

from novelty_harness.domain.reporting import CANONICAL_QUESTIONS
from novelty_harness.reporting.ir import report_id
from novelty_harness.reporting.models import ReportProposalError
from novelty_harness.reporting.rendering import render_compiled_report, validate_rendition_parity
from tests.unit.reporting.test_compiled_revalidation import proposed_report


def canonical_shape():
    report = proposed_report()
    original = report.ir.sections[0]
    sections = tuple(
        original.model_copy(
            update={
                "question_id": index,
                "question_label": label,
                "question_plan": original.question_plan.model_copy(update={"question_id": index}),
                "blocks": (),
            }
        )
        for index, label in enumerate(CANONICAL_QUESTIONS, 1)
    )
    # Contract shape only; no native accepted authority is created here.
    report = report.model_copy(
        update={
            "ir": report.ir.model_copy(
                update={
                    "sections": sections,
                    "material_claims": (),
                    "claim_basis_links": (),
                    "citation_registry": report.ir.citation_registry.model_copy(
                        update={"claim_basis_links": ()}
                    ),
                }
            )
        }
    )
    return report.model_copy(update={"report_id": report_id(report)})


def original_parity(report, renditions):
    expected = render_compiled_report(report, renderer_version=renditions.renderer_version)
    try:
        json_value = json.loads(renditions.json)
        yaml_value = yaml.safe_load(renditions.yaml)
    except (ValueError, yaml.YAMLError) as error:
        raise ReportProposalError(
            "report rendition is not safe structured serialization"
        ) from error
    if (
        json_value != report.model_dump(mode="json")
        or yaml_value != json_value
        or renditions != expected
    ):
        raise ReportProposalError("report rendition omits or changes canonical visible content")


def test_expected_format_iteration_preserves_complete_rendition_bytes_and_digests():
    from novelty_harness.reporting.rendering import _rendition_parts, _validated_render_report

    report = canonical_shape()
    expected = render_compiled_report(report)
    actual = list(
        _rendition_parts(_validated_render_report(report, "p8-render-v1"), "p8-render-v1")
    )
    assert [kind for kind, content, digest in actual] == ["json", "yaml", "markdown"]
    for kind, content, digest in actual:
        assert content == getattr(expected, kind)
        assert digest == getattr(expected, kind + "_digest")


@pytest.mark.parametrize(
    "field,changed",
    [
        (None, None),
        ("json", "{}"),
        ("json", "{"),
        ("yaml", "{}"),
        ("yaml", "!!python/object/apply:os.system ['untrusted']"),
        ("markdown", "omitted visible content"),
        ("json_digest", "forged"),
        ("yaml_digest", "forged"),
        ("markdown_digest", "forged"),
        ("scope", None),
        ("compilation_id", "other"),
        ("renderer_version", "unknown"),
        ("contract_kind", "unknown"),
    ],
)
def test_bounded_parity_preserves_original_complete_rejection(field, changed):
    report = canonical_shape()
    rendered = render_compiled_report(report)
    if field is not None:
        rendered = replace(rendered, **{field: changed})
    results = []
    for check in (original_parity, validate_rendition_parity):
        try:
            check(report, rendered)
            results.append(None)
        except ReportProposalError as error:
            results.append(str(error))
    assert results[0] == results[1]
    assert (results[1] is None) == (field is None)


def test_bounded_parity_preserves_dataclass_subclass_rejection():
    from novelty_harness.reporting.rendering import ReportRenditions

    class ExtendedRenditions(ReportRenditions):
        pass

    report = canonical_shape()
    rendered = render_compiled_report(report)
    extended = ExtendedRenditions(**vars(rendered))
    with pytest.raises(ReportProposalError):
        original_parity(report, extended)
    with pytest.raises(ReportProposalError):
        validate_rendition_parity(report, extended)


def test_parity_bounds_complete_expected_format_retention(record_property):
    import gc
    import tracemalloc

    report = canonical_shape()
    report = report.model_copy(
        update={
            "ir": report.ir.model_copy(
                update={
                    "report_limitations": ("qualified scope " + "x" * 32768,) * 12,
                }
            )
        }
    )
    report = report.model_copy(update={"report_id": report_id(report)})
    rendered = render_compiled_report(report)
    peaks = []
    for check in (original_parity, validate_rendition_parity):
        gc.collect()
        tracemalloc.start()
        try:
            check(report, rendered)
            peaks.append(tracemalloc.get_traced_memory()[1])
        finally:
            tracemalloc.stop()
    record_property("original_parity_peak_bytes", peaks[0])
    record_property("bounded_parity_peak_bytes", peaks[1])
    assert peaks[1] < peaks[0] * 0.9, peaks


def test_expected_json_comparison_bounds_full_text_and_digest_retention(record_property):
    import gc
    import tracemalloc

    from novelty_harness.reporting.rendering import _digest, _expected_json_matches
    from novelty_harness.runtime.tracing.hashing import canonical_json

    report = canonical_shape()
    report = report.model_copy(
        update={
            "ir": report.ir.model_copy(
                update={
                    "report_limitations": ('é雪😀"\\ scope ' + "x" * 32768,) * 64,
                }
            )
        }
    )
    report = report.model_copy(update={"report_id": report_id(report)})
    text = canonical_json(report)
    digest = _digest(report, "p8-render-v1", "json", text)
    peaks = []
    for compare in (
        lambda value, content, identity: (
            canonical_json(value) == content
            and _digest(value, "p8-render-v1", "json", canonical_json(value)) == identity
        ),
        lambda value, content, identity: _expected_json_matches(
            value, "p8-render-v1", content, identity
        ),
    ):
        gc.collect()
        tracemalloc.start()
        try:
            assert compare(report, text, digest)
            peaks.append(tracemalloc.get_traced_memory()[1])
        finally:
            tracemalloc.stop()
    record_property("original_expected_json_peak_bytes", peaks[0])
    record_property("bounded_expected_json_peak_bytes", peaks[1])
    assert peaks[1] < peaks[0] * 0.5, peaks
    assert not _expected_json_matches(report, "p8-render-v1", text + " ", digest)
    assert not _expected_json_matches(report, "p8-render-v1", text[:-1] + " ", digest)
    assert not _expected_json_matches(report, "p8-render-v1", text, "forged")
