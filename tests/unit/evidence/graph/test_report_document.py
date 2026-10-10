"""Exact physical bytes, framing and corruption rejection for schema v10."""

from dataclasses import replace

import pytest

from novelty_harness.evidence.graph.report_document import (
    SEGMENT_BYTES,
    decode_document,
    document_manifest,
    encode_document,
)
from novelty_harness.runtime.tracing.hashing import canonical_json


@pytest.mark.parametrize(
    "document",
    [
        canonical_json({"text": "Unicode é 漢字 😀\n\t\x00\ud800", "ordered": [3, 1, 2]}),
        "x" * (SEGMENT_BYTES - 1) + "😀" + "y" * SEGMENT_BYTES,
        "x" * SEGMENT_BYTES,
    ],
)
def test_segmented_document_retains_every_original_utf8_byte(document):
    chunks = tuple(encode_document("report_exact", document))
    manifest = document_manifest("report_exact", document)
    assert decode_document(canonical_json(manifest), "report_exact", chunks) == document
    assert manifest.byte_length == len(document.encode("utf-8"))
    assert manifest.chunk_count == len(chunks)


@pytest.mark.parametrize(
    "attack",
    [
        "missing",
        "extra",
        "order",
        "foreign",
        "codec",
        "payload",
        "truncated",
        "trailing",
        "length",
        "digest",
        "manifest_count",
        "manifest_length",
        "manifest_digest",
        "manifest_codec",
        "manifest_extra",
        "manifest_bool",
        "manifest_noncanonical",
        "manifest_foreign",
    ],
)
def test_segmented_document_refuses_corrupt_physical_projection(attack):
    document = "a" * SEGMENT_BYTES + "b" * 20
    chunks = list(encode_document("report_exact", document))
    manifest = document_manifest("report_exact", document)
    wire = manifest.model_dump(mode="json")
    if attack == "missing":
        chunks.pop()
    elif attack == "extra":
        chunks.append(chunks[-1])
    elif attack == "order":
        chunks.reverse()
    elif attack == "foreign":
        chunks[0] = replace(chunks[0], report_id="report_foreign")
    elif attack == "codec":
        chunks[0] = replace(chunks[0], codec="unknown")
    elif attack == "payload":
        chunks[0] = replace(chunks[0], payload=b"bad")
    elif attack == "truncated":
        chunks[0] = replace(chunks[0], payload=chunks[0].payload[:-1])
    elif attack == "trailing":
        chunks[0] = replace(chunks[0], payload=chunks[0].payload + b"extra")
    elif attack == "length":
        chunks[0] = replace(chunks[0], byte_length=1)
    elif attack == "digest":
        chunks[0] = replace(chunks[0], content_digest="0" * 64)
    elif attack == "manifest_count":
        wire["chunk_count"] += 1
    elif attack == "manifest_length":
        wire["byte_length"] += 1
    elif attack == "manifest_digest":
        wire["document_digest"] = "0" * 64
    elif attack == "manifest_codec":
        wire["codec"] = "unknown"
    elif attack == "manifest_extra":
        wire["extra"] = True
    elif attack == "manifest_bool":
        wire["chunk_count"] = True
    elif attack == "manifest_foreign":
        wire["report_id"] = "report_foreign"
    encoded = canonical_json(wire)
    if attack == "manifest_noncanonical":
        encoded = " " + encoded
    with pytest.raises(ValueError):
        decode_document(encoded, "report_exact", chunks)


def test_segmented_document_matches_independent_literal_wire_and_digest():
    import hashlib
    import zlib

    document = '{"a":[3,1,2],"text":"\\u00e9\\n"}'
    manifest = document_manifest("report_exact", document)
    chunks = tuple(encode_document("report_exact", document))
    assert manifest.byte_length == 31
    assert manifest.document_digest == hashlib.sha256(document.encode("ascii")).hexdigest()
    assert len(chunks) == 1
    assert zlib.decompress(chunks[0].payload) == document.encode("ascii")
    assert chunks[0].content_digest == manifest.document_digest
