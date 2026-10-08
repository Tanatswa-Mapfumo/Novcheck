"""Bounded representation probes of real report contracts; never authority fixtures.

Run each stage in a fresh native-supervised child. No accepted report, SQLite
fixture or historical golden is generated. This cannot qualify full report memory.
"""

import argparse
import ctypes
import hashlib
import json
import os
import resource
import sys
import time
import tracemalloc
from pathlib import Path

STAGES = ("construct", "dump", "canonical_json", "json_validate", "canonical_hash", "yaml")


def measure_stage(stage: str, refs: int, chars: int, output: Path, *, trace: bool = True) -> dict:
    # Imports deliberately occur in the measured fresh child, never the supervisor.
    from pydantic import TypeAdapter

    from novelty_harness.reporting.claims import ClaimBasisLink
    from novelty_harness.reporting.models import AuthorityRef, ReportScope
    from novelty_harness.runtime.tracing.hashing import canonical_hash, canonical_json

    scope = ReportScope(
        assessment_id="asm_representation_probe",
        adjudication_id="p7frozen_probe_shape_only",
        assessment_context_id="p7ctx_probe_shape_only",
        phase6_snapshot_id="p6snap_probe_shape_only",
    )
    text = "x" * chars
    adapter = TypeAdapter(tuple[ClaimBasisLink, ...])

    def build():
        return tuple(
            ClaimBasisLink(
                scope=scope,
                compilation_id="p8run_probe_shape_only",
                claim_id="p8claim_probe",
                authority_ref=AuthorityRef(
                    scope=scope,
                    kind="CIR",
                    native_id="cir_probe",
                    digest="a" * 64,
                    path=("claimed_advantages", index),
                ),
                proposition=text,
                use="ATTRIBUTED_INPUT_CLAIM",
            )
            for index in range(refs)
        )

    links = build() if stage != "construct" else ()
    payload = (
        [link.model_dump(mode="json") for link in links]
        if stage not in ("construct", "dump")
        else None
    )
    encoded = canonical_json(payload) if stage == "json_validate" else None
    if trace:
        tracemalloc.start()
    started = time.perf_counter()
    if stage == "construct":
        result = build()
    elif stage == "dump":
        result = [link.model_dump(mode="json") for link in links]
    elif stage == "canonical_json":
        result = canonical_json(payload)
    elif stage == "json_validate":
        result = adapter.validate_json(encoded)
    elif stage == "canonical_hash":
        result = canonical_hash(payload)
    elif stage == "yaml":
        import yaml

        result = yaml.safe_dump(payload, allow_unicode=True, sort_keys=True)
    else:
        raise ValueError("unknown stage")
    elapsed = time.perf_counter() - started
    current, peak = tracemalloc.get_traced_memory() if trace else (None, None)
    if trace:
        tracemalloc.stop()
    result_links = result if stage in ("construct", "json_validate") else links
    assert len(result_links) == refs
    assert all(link.proposition == text for link in result_links)
    unique_text_objects = len({id(link.proposition) for link in result_links})
    # Byte partition is outside the timed operation; exact reference and text data retained.
    wire = (
        result
        if stage == "canonical_json"
        else canonical_json([link.model_dump(mode="json") for link in result_links])
    )
    repeated_text_bytes = refs * chars
    # Same maps appearing twice serialize twice, as block/global ReportIR collections do.
    flat = [link.model_dump(mode="json") for link in result_links]
    double_collection_bytes = len(
        canonical_json({"block_basis_links": flat, "global_basis_links": flat}).encode()
    )
    # Read native lifetime physical footprint, including serialized byte partition above.
    native = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
    native.proc_pid_rusage.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
    native.proc_pid_rusage.restype = ctypes.c_int
    buffer = (ctypes.c_uint64 * 37)()  # SDK v4: 16-byte UUID + 35 uint64 fields = 296 bytes.
    assert native.proc_pid_rusage(os.getpid(), 4, ctypes.byref(buffer)) == 0
    observation = {
        "stage": stage,
        "refs": refs,
        "paragraph_chars": chars,
        "elapsed_seconds": elapsed,
        "stage_python_current_bytes": current,
        "stage_python_peak_bytes": peak,
        "unique_proposition_string_objects": unique_text_objects,
        "basis_json_bytes": len(wire.encode()),
        "repeated_proposition_bytes": repeated_text_bytes,
        "repeated_proposition_fraction": repeated_text_bytes / len(wire.encode()),
        "duplicated_collection_json_bytes": double_collection_bytes,
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "peak_physical_footprint_bytes": buffer[30],
        "basis_json_sha256": hashlib.sha256(wire.encode()).hexdigest(),
        "scope": "synthetic bounded ClaimBasisLink representation, NOT repository authority",
        "native_fixture_generated": False,
        "report_ir_constructed": False,
        "production_memory_qualified": False,
        "profiling_overhead": "tracemalloc enabled only in stage"
        if trace
        else "tracemalloc disabled",
    }
    with output.open("x") as destination:
        json.dump(observation, destination, indent=2)
        destination.write("\n")
    return observation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=STAGES, required=True)
    parser.add_argument("--refs", type=int, choices=(16, 128), required=True)
    parser.add_argument("--chars", type=int, default=4096)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--no-tracemalloc", action="store_true")
    args = parser.parse_args()
    if not 0 < args.chars <= 8192 or sys.platform != "darwin":
        parser.error("macOS bounded probe requires 1..8192 paragraph chars")
    print(
        json.dumps(
            measure_stage(
                args.stage, args.refs, args.chars, args.output, trace=not args.no_tracemalloc
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
