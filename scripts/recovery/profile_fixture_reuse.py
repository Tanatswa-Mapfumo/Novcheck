"""Bounded before/after native fixture recipe. Run only under resource_guard.

Does not compile/render/accept reports or regenerate goldens. Start with one
copy only after the unchanged minimum native primary and cache controls pass.
"""

import argparse
import hashlib
import importlib.metadata
import json
import resource
import sys
import time
from pathlib import Path

from scripts.recovery.batch_evidence import digest_file, write_record
from scripts.recovery.local_batches import execution_identity
from tests.fixtures.native_baselines import reusable_report_case
from tests.fixtures.phase8 import make_report_case
from tests.fixtures.recorded_clock import recorded_observation_clock
from tests.fixtures.sqlite_baselines import _timed
from tests.integration.test_phase6_evidence_pipeline import NOW


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("original", "cached"), required=True)
    parser.add_argument("--copies", type=int, choices=(1, 2, 3), default=1)
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    stages = args.directory / "stages.jsonl"
    started = time.perf_counter()
    source, _, environment = execution_identity(Path.cwd(), Path(sys.executable))
    scenario = {
        "recipe_version": "minimum-native-report-case-v2",
        "synthetic_observation_clock": NOW.isoformat(),
        "copies": args.copies,
        "unassessable": False,
        "clock_controls": "explicit-provider-normalization-and-utc-defaults-v1",
    }
    recipe = hashlib.sha256(json.dumps(scenario, sort_keys=True).encode()).hexdigest()
    locked_environment = hashlib.sha256(
        json.dumps(
            {
                "lock": digest_file(Path("uv.lock")),
                "python": sys.version,
                "binary": digest_file(Path(sys.executable).resolve()),
                "packages": sorted(
                    (d.metadata["Name"], d.version) for d in importlib.metadata.distributions()
                ),
                "environment": environment,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    fingerprints = []
    with stages.open("x", encoding="utf-8") as stream:

        def observe(event):
            stream.write(
                json.dumps({**event, "elapsed_seconds": time.perf_counter() - started}) + "\n"
            )
            stream.flush()

        def build(path):
            with recorded_observation_clock(NOW) as clock:
                return make_report_case(path, observe=observe, observation_clock=clock)

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
            "scenario": scenario,
            "locked_environment_sha256": locked_environment,
            "synthetic_observation_clock": NOW.isoformat(),
            "source_identity": source,
            "bundle_digests": fingerprints,
            "total_seconds": time.perf_counter() - started,
            "child_ru_maxrss": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "ru_maxrss_units": "bytes" if sys.platform == "darwin" else "KiB",
            "guard_receipt_required": True,
            "notes": (
                "nested stage durations are not additive; native peaks require supervisor evidence"
            ),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
