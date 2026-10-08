"""Bounded before/after native fixture recipe. Run only under resource_guard.

Does not compile/render/accept reports or regenerate goldens. Start with one
copy only after the unchanged minimum native primary and cache controls pass.
"""

import argparse
import hashlib
import json
import resource
import sys
import time
from pathlib import Path

from scripts.recovery.batch_evidence import write_record
from scripts.recovery.local_batches import execution_identity
from tests.fixtures.native_baselines import reusable_report_case
from tests.fixtures.phase8 import make_report_case
from tests.fixtures.sqlite_baselines import _timed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("original", "cached"), required=True)
    parser.add_argument("--copies", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    stages = args.directory / "stages.jsonl"
    started = time.perf_counter()
    source, _, _ = execution_identity(Path.cwd(), Path(sys.executable))
    # Both modes bind the same exact builder and environment recipe. No historical
    # timings are silently substituted for an unsafe fresh measurement.
    recipe = hashlib.sha256((source + ":minimum-native-report-case-v1").encode()).hexdigest()
    fingerprints = []
    with stages.open("x", encoding="utf-8") as stream:

        def observe(event):
            stream.write(
                json.dumps({**event, "elapsed_seconds": time.perf_counter() - started}) + "\n"
            )
            stream.flush()

        def build(path):
            return make_report_case(path, observe=observe)

        for index in range(args.copies):
            if args.mode == "original":
                with _timed("fixture_construction", observe):
                    case = build(args.directory / f"source-{index}")
            else:
                case = reusable_report_case(
                    args.directory / "cache",
                    args.directory / f"copy-{index}.db",
                    recipe_digest=recipe,
                    environment_digest=source,
                    builder=build,
                    observe=observe,
                )
            try:
                fingerprints.append(case.bundle.bundle_digest)
            finally:
                with _timed("fixture_teardown", observe):
                    case.repository.close()
            del case
        if len(set(fingerprints)) != 1:
            raise ValueError("native scenarios differ; no paired speedup may be claimed")
    write_record(
        args.directory / "result.json",
        {
            "state": "PROFILE_COMPLETED",
            "mode": args.mode,
            "copies": args.copies,
            "recipe": recipe,
            "source_identity": source,
            "bundle_digests": fingerprints,
            "total_seconds": time.perf_counter() - started,
            "child_ru_maxrss": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "ru_maxrss_units": "bytes" if sys.platform == "darwin" else "KiB",
            "guard_receipt_required": True,
            "notes": "nested stage durations are not additive; native peaks require supervisor evidence",
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
