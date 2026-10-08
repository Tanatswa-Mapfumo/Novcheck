"""Opt-in local guarded batches. Not the final gate until its controls pass.

Existing scripts/verify.py is unchanged. No automatic heavyweight dispatch or
parallel workers: callers explicitly choose a previously reviewed small batch.
"""

import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path

from scripts.recovery.batch_evidence import (
    digest_file,
    inspect_events,
    read_json,
    verify_guard,
    verify_resume,
    write_record,
)
from scripts.recovery.resource_guard import ResourceLimits, run_guarded
from scripts.recovery.sequential import account_batch

POLICY = "guarded-local-inventory-v1"


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def source_tree_identity(cwd):
    # Same byte/mode protocol as the resource supervisor, including new files.
    names = (
        subprocess.check_output(
            [
                "git",
                "--no-optional-locks",
                "-C",
                str(cwd),
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
            ]
        )
        .decode()
        .split("\0")
    )
    digest = hashlib.sha256()
    for name in sorted(set(names) - {""}):
        path = cwd / name
        digest.update(name.encode() + b"\0")
        if not path.exists():
            digest.update(b"MISSING\0")
            continue
        digest.update(str(path.stat().st_mode & 0o7777).encode() + b"\0")
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def execution_identity(cwd, python):
    """Bind full source, interpreter, installed metadata, locked recipe and policy.

    Environment values are hashed, never persisted in receipts (may be secrets).
    Actual loaded versions/plugins are additionally checked in pytest evidence.
    """
    python = python.absolute()
    environment = dict(os.environ)
    for key in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTHONPATH"):
        environment.pop(key, None)
    environment["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment.pop("_", None)
    metadata = []
    for path in sorted(
        (python.parent.parent / "lib").glob("python*/site-packages/*.dist-info/METADATA")
    ):
        metadata.append((str(path.relative_to(python.parent.parent)), digest_file(path)))
    if not metadata:
        raise ValueError("isolated interpreter package metadata unavailable")
    tree = source_tree_identity(cwd)
    identity = _digest(
        {
            "tree": tree,
            "python": str(python),
            "binary": digest_file(python),
            "installed_metadata": metadata,
            "environment": _digest(environment),
            "policy": POLICY,
        }
    )
    return identity, tree, environment


def _command(python, job):
    return (str(python), "-B", "-m", "scripts.recovery.pytest_child", str(job.resolve()))


def _files(directory, guard, job, events):
    return {
        kind: {"name": path.name, "sha256": digest_file(path)}
        for kind, path in {
            "guard": guard,
            "job": job,
            "events": events,
            "log": guard.with_suffix(".log"),
            "samples": guard.with_suffix(".samples.jsonl"),
        }.items()
    }


def _dispatch(cwd, python, directory, nodes, collect_only, limits):
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    job = directory / "job.json"
    events = directory / "pytest.jsonl"
    guard = directory / "guard.json"
    write_record(
        job, {"nodes": nodes, "collect_only": collect_only, "events_path": str(events.resolve())}
    )
    # resource_guard currently inherits the parent's environment. This temporary
    # configuration is local to this single-threaded coordinator, then restored.
    original = dict(os.environ)
    _, _, environment = execution_identity(cwd, python)
    try:
        os.environ.clear()
        os.environ.update(environment)
        result = run_guarded(_command(python, job), cwd=cwd, limits=limits, output=guard)
    finally:
        os.environ.clear()
        os.environ.update(original)
    return result, guard, job, events


def collect_inventory(cwd, python, directory, *, expected_network_exclusions=5):
    started = time.perf_counter()
    before, tree, _ = execution_identity(cwd, python)
    limits = ResourceLimits(soft_bytes=256_000_000, hard_bytes=384_000_000, timeout_seconds=60)
    result, guard, job, events = _dispatch(cwd, python, directory, ["tests/"], True, limits)
    if result.state != "PASSED" or not result.cleanup_complete:
        return {"state": result.state, "reason": result.reason, "guard": str(guard)}
    after, _, _ = execution_identity(cwd, python)
    if before != after or result.source_tree_sha256 != tree:
        raise ValueError("source/environment changed during collection")
    evidence = inspect_events(events, job_digest=digest_file(job))
    if evidence["phases"] or len(evidence["deselected"]) != expected_network_exclusions:
        raise ValueError("collection policy or network exclusion inventory changed")
    receipt = {
        "state": "COLLECTED",
        "source_identity": before,
        "source_tree_sha256": tree,
        "expected_nodes": evidence["nodes"],
        "network_exclusions": evidence["deselected"],
        "configuration": evidence["configuration"],
        "command_sha256": result.command_sha256,
        "limits": asdict(limits),
        "evidence": _files(directory, guard, job, events),
        "import_collection_seconds": evidence["import_collection_seconds"],
        "guard_elapsed_seconds": result.elapsed_seconds,
        "total_seconds": time.perf_counter() - started,
    }
    write_record(directory / "inventory.json", receipt)
    return receipt


def load_inventory(path, cwd, python):
    receipt = read_json(path)
    identity, tree, _ = execution_identity(cwd, python)
    if (
        receipt["state"] != "COLLECTED"
        or receipt["source_identity"] != identity
        or receipt["source_tree_sha256"] != tree
    ):
        raise ValueError("inventory belongs to another source/environment")
    files = receipt["evidence"]
    if set(files) != {"guard", "job", "events", "log", "samples"}:
        raise ValueError("incomplete collection dependencies")
    paths = {}
    for kind, entry in files.items():
        if Path(entry["name"]).name != entry["name"]:
            raise ValueError("foreign collection evidence path")
        paths[kind] = path.parent / entry["name"]
        if paths[kind].is_symlink() or digest_file(paths[kind]) != entry["sha256"]:
            raise ValueError("collection dependency changed")
    guard = verify_guard(paths["guard"], paths["samples"])
    job = read_json(paths["job"])
    if (
        guard["state"] != "PASSED"
        or guard["returncode"] != 0
        or guard["cleanup_complete"] is not True
        or guard["source_tree_sha256"] != tree
        or guard["command_sha256"] != receipt["command_sha256"]
        or guard["limits"] != receipt["limits"]
        or job["collect_only"] is not True
        or job["nodes"] != ["tests/"]
        or Path(job["events_path"]).resolve() != paths["events"].resolve()
    ):
        raise ValueError("invalid collection execution closure")
    actual = inspect_events(paths["events"], job_digest=digest_file(paths["job"]))
    if (
        actual["nodes"] != receipt["expected_nodes"]
        or actual["configuration"] != receipt["configuration"]
        or actual["deselected"] != receipt["network_exclusions"]
        or actual["phases"]
    ):
        raise ValueError("inventory differs from actual collection")
    return receipt


def run_batch(cwd, python, directory, *, inventory, nodes, limits, resume_from=None):
    started = time.perf_counter()
    current, tree, _ = execution_identity(cwd, python)
    if inventory["source_identity"] != current or inventory["source_tree_sha256"] != tree:
        raise ValueError("stale inventory")
    if (
        not nodes
        or len(set(nodes)) != len(nodes)
        or any(node not in inventory["expected_nodes"] for node in nodes)
    ):
        raise ValueError("batch contains duplicate or foreign nodes")
    if (
        limits.soft_bytes > 1_500_000_000
        or limits.hard_bytes > 2_000_000_000
        or limits.min_headroom_bytes < 1_500_000_000
        or limits.max_swap_bytes > 2_000_000_000
        or limits.sample_seconds > 0.1
    ):
        raise ValueError("batch exceeds the approved provisional local ceiling")
    if resume_from is not None and verify_resume(
        resume_from, source_identity=current, expected_nodes=nodes
    ):
        resumed = read_json(resume_from)
        if resumed["configuration"] == inventory["configuration"] and resumed["limits"] == asdict(
            limits
        ):
            return {"state": "RESUMED", "receipt": str(resume_from), "passed": nodes}
    result, guard, job, events = _dispatch(cwd, python, directory, nodes, False, limits)
    receipt = {
        "state": "INCOMPLETE",
        "source_identity": current,
        "source_tree_sha256": tree,
        "expected_nodes": nodes,
        "cleanup_complete": result.cleanup_complete,
        "required_gates": {"guard": result.state},
        "guard": asdict(result),
        "command_sha256": result.command_sha256,
        "limits": asdict(limits),
    }
    if result.state == "PASSED" and result.cleanup_complete:
        try:
            if execution_identity(cwd, python)[0] != current or result.source_tree_sha256 != tree:
                raise ValueError("source/environment changed during batch")
            evidence = inspect_events(events, job_digest=digest_file(job), expected_nodes=nodes)
            if evidence["configuration"] != inventory["configuration"]:
                raise ValueError("actual pytest environment/plugin configuration changed")
            receipt["accounting"] = account_batch(
                nodes, evidence["phases"], child_state=result.state, returncode=result.returncode
            )
            receipt["configuration"] = evidence["configuration"]
            receipt["passed"] = receipt["accounting"]["passed"]
            receipt["state"] = receipt["accounting"]["state"]
            receipt["import_collection_seconds"] = evidence["import_collection_seconds"]
            receipt["evidence"] = _files(directory, guard, job, events)
        except (OSError, ValueError, TypeError, KeyError) as error:
            receipt["accounting_error"] = str(error)
    receipt["total_seconds"] = time.perf_counter() - started
    write_record(directory / "batch.json", receipt)
    return receipt


def plan_measured_batches(inventory_path, cohort_paths, *, cwd, python):
    """Group only complete measured cohorts; unmeasured nodes are not dispatched.

    Same-source capacity proofs are deliberately conservative. Never infer light
    workloads from file names, isolated per-test peaks, or a historical lost tree.
    """
    inventory = load_inventory(inventory_path, cwd, python)
    covered = set()
    batches = []
    measured_seconds = 0.0
    for path in cohort_paths:
        receipt = read_json(path)
        nodes = receipt.get("expected_nodes", [])
        if not verify_resume(
            path, source_identity=inventory["source_identity"], expected_nodes=nodes
        ):
            raise ValueError("cohort lacks complete matching capacity evidence")
        if receipt["configuration"] != inventory["configuration"]:
            raise ValueError("cohort environment differs from collection")
        if any(node not in inventory["expected_nodes"] or node in covered for node in nodes):
            raise ValueError("overlapping or foreign measured cohort")
        guard = receipt["guard"]
        peak = max(guard["peak_rss_bytes"], guard["peak_footprint_bytes"])
        if len(nodes) > 1 and (
            receipt["limits"]["soft_bytes"] > 256_000_000 or peak * 1.25 >= 256_000_000
        ):
            raise ValueError("multi-node cohort does not fit the conservative lightweight tier")
        covered.update(nodes)
        measured_seconds += receipt["total_seconds"]
        batches.append(
            {
                "nodes": nodes,
                "limits": receipt["limits"],
                "capacity_evidence": str(path),
                "state": "MEASURED",
            }
        )
    unmeasured = [node for node in inventory["expected_nodes"] if node not in covered]
    return {
        "batches": batches,
        "unmeasured_nodes": unmeasured,
        "measured_coverage": len(covered),
        "required_count": len(inventory["expected_nodes"]),
        "measured_cohort_seconds": measured_seconds,
        "complete_suite_forecast_seconds": None,
        "state": "PLAN_COMPLETE" if not unmeasured else "CAPACITY_INCOMPLETE",
    }


def account_complete_inventory(inventory_path, batch_paths, *, cwd, python):
    """Reopen every proof before counting coverage; this is not final acceptance.

    Fresh detached/static/golden/review gates remain independently required.
    """
    inventory = load_inventory(inventory_path, cwd, python)
    actual = []
    for path in batch_paths:
        receipt = read_json(path)
        nodes = receipt.get("expected_nodes", [])
        if (
            not verify_resume(
                path, source_identity=inventory["source_identity"], expected_nodes=nodes
            )
            or receipt.get("configuration") != inventory["configuration"]
            or receipt["limits"]["soft_bytes"] > 1_500_000_000
            or receipt["limits"]["hard_bytes"] > 2_000_000_000
        ):
            return {"state": "INCOMPLETE", "reason": "INVALID_BATCH_EVIDENCE"}
        actual.extend(nodes)
    expected = inventory["expected_nodes"]
    complete = len(actual) == len(set(actual)) and set(actual) == set(expected)
    return {
        "state": "PASSED" if complete else "INCOMPLETE",
        "required_count": len(expected),
        "passed_count": len(actual),
        "network_exclusions": inventory["network_exclusions"],
    }


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collect", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.collect:
        parser.error("only explicit guarded collection is enabled at this preparation stage")
    result = collect_inventory(Path.cwd(), Path(sys.executable), args.output)
    print(json.dumps(result, indent=2))
    return 0 if result["state"] == "COLLECTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
