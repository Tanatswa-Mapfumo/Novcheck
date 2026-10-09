"""Exact rendition identities with bounded text encoding; no native authority."""

import gc
import tracemalloc

import pytest

from novelty_harness.reporting.rendering import _digest
from novelty_harness.runtime.tracing.hashing import canonical_hash


def shape_report():
    from datetime import UTC, datetime

    from novelty_harness.reporting.ir import CompiledAssessmentReport
    from tests.unit.reporting.test_ir_revalidation import shape_ir

    ir = shape_ir()
    return CompiledAssessmentReport(
        scope=ir.scope,
        compilation_id=ir.compilation_id,
        report_id="p8report_synthetic_digest_control",
        ir=ir,
        dependencies=(),
        approved_versions=(),
        configuration_refs=(),
        execution_refs=(),
        accepted_at=datetime(2026, 10, 6, tzinfo=UTC),
    )


def original_digest(report, kind, content):
    return canonical_hash(
        {
            "report_id": report.report_id,
            "renderer_version": "p8-render-v1",
            "format": kind,
            "content": content,
        }
    )


def test_rendition_digest_bounds_complete_text_encoding(record_property):
    report = shape_report()
    content = ('é雪😀"\\\n' + "x" * 64) * 32768
    peaks, values = [], []
    for function in (original_digest, lambda r, k, t: _digest(r, "p8-render-v1", k, t)):
        gc.collect()
        tracemalloc.start()
        try:
            values.append(function(report, "json", content))
            peaks.append(tracemalloc.get_traced_memory()[1])
        finally:
            tracemalloc.stop()
    record_property("original_rendition_digest_peak_bytes", peaks[0])
    record_property("bounded_rendition_digest_peak_bytes", peaks[1])
    assert values[0] == values[1]
    assert peaks[1] < peaks[0] * 0.25, peaks


@pytest.mark.parametrize("kind", ["json", "yaml", "markdown"])
@pytest.mark.parametrize(
    "content",
    ["", 'é雪😀"\\\b\f\n\r\t\x00\x1f', "\ud800\udfff", "x" * 65535 + "😀\\\n" + "é" * 65537],
)
def test_rendition_digest_preserves_original_canonical_bytes(kind, content):
    report = shape_report()
    assert _digest(report, "p8-render-v1", kind, content) == original_digest(report, kind, content)


def test_rendition_digest_preserves_legacy_non_string_projection():
    # The private helper historically used the generic encoder. Retain that
    # behavior for values outside its declared str contract, without coercion.
    report = shape_report()
    assert _digest(report, "p8-render-v1", "json", None) == original_digest(report, "json", None)


@pytest.mark.parametrize("content", [float("nan"), float("inf"), -float("inf")])
def test_rendition_digest_preserves_nonfinite_rejection(content):
    report = shape_report()
    with pytest.raises(ValueError):
        original_digest(report, "json", content)
    with pytest.raises(ValueError):
        _digest(report, "p8-render-v1", "json", content)


def test_rendition_digest_preserves_string_subclass_and_metadata_escaping():
    class Text(str):
        pass

    report = shape_report().model_copy(update={"report_id": 'report"\\é😀'})
    content = Text('content"\\é😀')
    kind = 'format"\\é'
    version = 'version"\\雪'
    assert _digest(report, version, kind, content) == canonical_hash(
        {
            "report_id": report.report_id,
            "renderer_version": version,
            "format": kind,
            "content": content,
        }
    )
