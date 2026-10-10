"""Lossless canonical report storage; physical hashes never grant native authority."""

import codecs
import hashlib
import io
import zlib
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from novelty_harness.runtime.tracing.hashing import canonical_json

SEGMENT_BYTES = 1_048_576
CODEC = "zlib-v1-1048576"
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class DocumentManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    storage_format: Literal["p8-canonical-report-segments-v1"]
    codec: Literal["zlib-v1-1048576"]
    report_id: str
    byte_length: Annotated[int, Field(gt=0)]
    chunk_count: Annotated[int, Field(gt=0)]
    document_digest: Digest


@dataclass(frozen=True)
class DocumentChunk:
    report_id: str
    ordinal: int
    codec: str
    byte_length: int
    content_digest: str
    payload: bytes


def document_segments(document: str) -> Iterator[bytes]:
    """Segment bytes without changing text or assuming character boundaries."""
    pending = bytearray()
    for offset in range(0, len(document), SEGMENT_BYTES):
        pending.extend(document[offset : offset + SEGMENT_BYTES].encode("utf-8"))
        while len(pending) >= SEGMENT_BYTES:
            yield bytes(pending[:SEGMENT_BYTES])
            del pending[:SEGMENT_BYTES]
    if pending:
        yield bytes(pending)


def document_manifest(report_id: str, document: str) -> DocumentManifest:
    digest = hashlib.sha256()
    length = count = 0
    for segment in document_segments(document):
        digest.update(segment)
        length += len(segment)
        count += 1
    return DocumentManifest(
        storage_format="p8-canonical-report-segments-v1",
        codec=CODEC,
        report_id=report_id,
        byte_length=length,
        chunk_count=count,
        document_digest=digest.hexdigest(),
    )


def encode_document(report_id: str, document: str) -> Iterator[DocumentChunk]:
    for ordinal, segment in enumerate(document_segments(document)):
        yield DocumentChunk(
            report_id=report_id,
            ordinal=ordinal,
            codec=CODEC,
            byte_length=len(segment),
            content_digest=hashlib.sha256(segment).hexdigest(),
            payload=zlib.compress(segment),
        )


def decode_document(manifest_json: str, report_id: str, chunks: Iterable[DocumentChunk]) -> str:
    manifest = DocumentManifest.model_validate_json(manifest_json)
    if manifest.report_id != report_id or canonical_json(manifest) != manifest_json:
        raise ValueError("segmented report manifest is foreign or noncanonical")
    digest = hashlib.sha256()
    count = length = 0
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    with io.StringIO() as output:
        for chunk in chunks:
            if (chunk.report_id, chunk.ordinal, chunk.codec) != (report_id, count, manifest.codec):
                raise ValueError("segmented report chunk identity, order or codec differs")
            try:
                inflater = zlib.decompressobj()
                segment = inflater.decompress(chunk.payload) + inflater.flush()
            except zlib.error as error:
                raise ValueError("segmented report chunk compressed data is invalid") from error
            expected = (
                SEGMENT_BYTES
                if count < manifest.chunk_count - 1
                else manifest.byte_length - SEGMENT_BYTES * (manifest.chunk_count - 1)
            )
            if (
                not inflater.eof
                or inflater.unused_data
                or inflater.unconsumed_tail
                or not 0 < expected <= SEGMENT_BYTES
                or len(segment) != chunk.byte_length
                or len(segment) != expected
                or hashlib.sha256(segment).hexdigest() != chunk.content_digest
            ):
                raise ValueError(
                    "segmented report chunk length, digest or compressed framing differs"
                )
            output.write(decoder.decode(segment))
            digest.update(segment)
            count += 1
            length += len(segment)
        output.write(decoder.decode(b"", final=True))
        if (count, length, digest.hexdigest()) != (
            manifest.chunk_count,
            manifest.byte_length,
            manifest.document_digest,
        ):
            raise ValueError("segmented report document count, length or digest differs")
        return output.getvalue()
