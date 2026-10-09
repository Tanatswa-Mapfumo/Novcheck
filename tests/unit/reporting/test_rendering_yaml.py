"""Exact PyYAML output without retaining its emitter buffers after publication."""

import gc
import tracemalloc

import pytest
import yaml


def test_yaml_output_bounds_simultaneous_emitter_and_text_retention(record_property):
    from novelty_harness.reporting.rendering import _yaml_text

    text = "qualified é雪 claim; " * 8192
    payload = {str(index): text for index in range(6)}
    results, peaks = [], []
    for function in (
        lambda value: yaml.safe_dump(
            value, allow_unicode=True, sort_keys=True, default_flow_style=False
        ),
        _yaml_text,
    ):
        gc.collect()
        tracemalloc.start()
        try:
            results.append(function(payload))
            peaks.append(tracemalloc.get_traced_memory()[1])
        finally:
            tracemalloc.stop()
    record_property("original_yaml_output_peak_bytes", peaks[0])
    record_property("bounded_yaml_output_peak_bytes", peaks[1])
    assert results[0] == results[1]
    assert peaks[1] < peaks[0] * 0.75, peaks


@pytest.mark.parametrize(
    "payload",
    [
        {},
        [],
        None,
        True,
        -0.0,
        {"z": "yes", "a": [None, False, 1, 0.625, "é雪 😀", "line\nbreak", "a\x00b", "a\ud800b"]},
        {"wrap": "word " * 100, "indent": {"empty": [], "colon": "a: b", "quote": '"'}},
    ],
)
def test_yaml_output_preserves_original_safe_dump_bytes(payload):
    from novelty_harness.reporting.rendering import _yaml_text

    assert _yaml_text(payload) == yaml.safe_dump(
        payload, allow_unicode=True, sort_keys=True, default_flow_style=False
    )


def test_yaml_output_closes_private_stream_on_emitter_failure(monkeypatch):
    from novelty_harness.reporting.rendering import _yaml_text

    streams = []

    def fail(value, stream=None, **kwargs):
        streams.append(stream)
        raise OSError("controlled emitter failure")

    monkeypatch.setattr(yaml, "safe_dump", fail)
    with pytest.raises(OSError, match="controlled emitter failure"):
        _yaml_text({"text": "shape only"})
    assert streams[0].closed


@pytest.mark.parametrize("failure", ["mapping", "decode"])
def test_yaml_output_closes_mapping_and_stream_on_read_failure(monkeypatch, failure):
    from novelty_harness.reporting import rendering

    mappings, streams = [], []
    original_file, original_map = rendering.TemporaryFile, rendering.mmap

    def capture_file(**kwargs):
        stream = original_file(**kwargs)
        streams.append(stream)
        return stream

    def capture_map(*args, **kwargs):
        if failure == "mapping":
            raise OSError("controlled read failure")
        mapping = original_map(*args, **kwargs)
        mappings.append(mapping)
        return mapping

    def fail_decode(*args, **kwargs):
        raise OSError("controlled read failure")

    monkeypatch.setattr(rendering, "TemporaryFile", capture_file)
    monkeypatch.setattr(rendering, "mmap", capture_map)
    if failure == "decode":
        monkeypatch.setattr(rendering.codecs, "decode", fail_decode)
    with pytest.raises(OSError, match="controlled read failure"):
        rendering._yaml_text({"shape": "only"})
    assert streams[0].closed
    assert all(mapping.closed for mapping in mappings)
