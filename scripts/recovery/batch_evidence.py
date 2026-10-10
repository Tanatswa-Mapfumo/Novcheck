"""Disk evidence joins for guarded batches; mutable flags cannot certify a pass."""

import hashlib
import json
import math
import os
from dataclasses import asdict, fields
from pathlib import Path

from scripts.recovery.resource_guard import (
    HistoricalResourceLimits,
    ResourceLimits,
    ResourceSample,
    RiskMonitor,
    RunReceipt,
    approved_local_limits,
)
from scripts.recovery.sequential import account_batch, eligible_resume


def digest_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate evidence key")
        result[key] = value
    return result


def read_json(path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream, object_pairs_hook=_unique)


def write_record(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def inspect_events(path, *, job_digest, expected_nodes=None):
    with path.open(encoding="utf-8") as stream:
        events = [json.loads(line, object_pairs_hook=_unique) for line in stream]
    kinds = {
        "job",
        "configured",
        "collection",
        "session_finish",
        "phase",
        "subtest",
        "collection_nonpass",
    }
    if any(not isinstance(event, dict) or event.get("kind") not in kinds for event in events):
        raise ValueError("unknown pytest evidence event")
    jobs = [event for event in events if event.get("kind") == "job"]
    configs = [event for event in events if event.get("kind") == "configured"]
    collections = [event for event in events if event.get("kind") == "collection"]
    endings = [event for event in events if event.get("kind") == "session_finish"]
    if (
        len(jobs) != 1
        or jobs[0].get("sha256") != job_digest
        or len(configs) != 1
        or configs[0].get("plugin_policy") != "explicit-socket-asyncio-v1"
        or configs[0].get("marker_policy") != "not network"
        or len(collections) != 1
        or len(endings) != 1
        or endings[0].get("exitstatus") != 0
        or any(event.get("kind") == "collection_nonpass" for event in events)
    ):
        raise ValueError("incomplete pytest job/configuration/collection/session evidence")
    nodes = collections[0]["nodes"]
    if not nodes or len(set(nodes)) != len(nodes):
        raise ValueError("empty or duplicate collection inventory")
    if expected_nodes is not None and nodes != expected_nodes:
        raise ValueError("selected test inventory differs from requested batch")
    deselected = collections[0]["deselected"]
    if any(item.get("network") is not True for item in deselected):
        raise ValueError("non-network test excluded from inventory")
    if len({item["nodeid"] for item in deselected}) != len(deselected):
        raise ValueError("duplicate deselected test")
    phases = [
        {key: event[key] for key in ("nodeid", "when", "outcome", "duration")}
        for event in events
        if event.get("kind") == "phase"
    ]
    subtests = [
        {key: event[key] for key in ("nodeid", "outcome", "duration", "identity")}
        for event in events
        if event.get("kind") == "subtest"
    ]
    if endings[0].get("subtest_count", 0) != len(subtests):
        raise ValueError("incomplete subtest evidence")
    return {
        "nodes": nodes,
        "subtests": subtests,
        "deselected": deselected,
        "phases": phases,
        "configuration": configs[0],
        "import_collection_seconds": collections[0]["import_collection_seconds"],
        "session_seconds": endings[0]["elapsed_seconds"],
    }


def verify_guard(guard_path, samples_path):
    """Stream native sample accounting; do not trust a PASSED label alone."""
    guard = read_json(guard_path)
    if set(guard) != {field.name for field in fields(RunReceipt)}:
        raise ValueError("unexpected supervisor receipt fields")
    if (
        guard["state"] != "PASSED"
        or type(guard["returncode"]) is not int
        or guard["returncode"] != 0
        or guard["reason"] is not None
        or guard["cleanup_complete"] is not True
    ):
        raise ValueError("supervisor did not complete safely")
    recorded_limits = {"policy_version": 1, **guard["limits"]}
    limits = (
        ResourceLimits(**recorded_limits)
        if recorded_limits["policy_version"] == 3
        else HistoricalResourceLimits(**recorded_limits)
    )
    if not approved_local_limits(limits):
        raise ValueError("supervisor policy exceeds approved local limits")
    if limits.policy_version == 3 and guard["limits"] != asdict(limits):
        raise ValueError("noncanonical unrestricted execution policy")
    risk = RiskMonitor(limits)
    count = peak_rss = peak_footprint = 0
    previous = -math.inf
    with samples_path.open(encoding="utf-8") as stream:
        for line in stream:
            sample = ResourceSample(**json.loads(line, object_pairs_hook=_unique))
            if not math.isfinite(sample.monotonic_seconds) or sample.monotonic_seconds <= previous:
                raise ValueError("invalid sample chronology")
            for value in (sample.rss_bytes, sample.footprint_bytes, sample.peak_footprint_bytes):
                if type(value) is not int or value < 0:
                    raise ValueError("invalid native memory measurement")
            if limits.policy_version != 3 and (
                type(sample.pressure) is not int
                or type(sample.headroom_bytes) is not int
                or sample.headroom_bytes < 0
                or type(sample.swap_bytes) is not int
                or sample.swap_bytes < 0
            ):
                raise ValueError("invalid system memory measurement")
            if risk.check(sample) is not None:
                raise ValueError("unsafe sample in supposedly passing run")
            if sample.pids and not risk.ready(sample):
                raise ValueError("child observed before paging preflight completed")
            previous = sample.monotonic_seconds
            count += 1
            peak_rss = max(peak_rss, sample.rss_bytes)
            peak_footprint = max(
                peak_footprint, sample.footprint_bytes, sample.peak_footprint_bytes
            )
    if (
        (limits.policy_version != 3 and (count < 4 or not risk.ready(sample)))
        or count != guard["samples"]
        or peak_rss != guard["peak_rss_bytes"]
        or peak_footprint != guard["peak_footprint_bytes"]
    ):
        raise ValueError("native sample/peak accounting mismatch")
    return guard


def verify_invocation(guard, job_path, configuration, recorded_command):
    command = [
        configuration["environment"]["invoked_executable"],
        "-B",
        "-m",
        "scripts.recovery.pytest_child",
        str(job_path.resolve()),
    ]
    if (
        recorded_command != command
        or hashlib.sha256(json.dumps(command).encode()).hexdigest() != guard["command_sha256"]
    ):
        raise ValueError("supervisor invocation does not match actual pytest job")


def verify_resume(receipt_path, *, source_identity, expected_nodes):
    """Require exact committed artifact hashes, guard identity and actual phases.

    This is integrity protection against missing, stale or accidentally edited
    receipts, not a cryptographic claim against an attacker replacing every file.
    """
    try:
        receipt = read_json(receipt_path)
        if not eligible_resume(
            receipt, source_identity=source_identity, expected_nodes=expected_nodes
        ):
            return False
        files = receipt["evidence"]
        if set(files) != {"guard", "job", "events", "log", "samples"}:
            return False
        paths = {}
        for kind, entry in files.items():
            name = entry["name"]
            if not isinstance(name, str) or Path(name).name != name:
                return False
            path = receipt_path.parent / name
            if path.is_symlink() or digest_file(path) != entry["sha256"]:
                return False
            paths[kind] = path
        guard = verify_guard(paths["guard"], paths["samples"])
        if receipt.get("guard", guard) != guard:
            return False
        if (
            guard["state"] != "PASSED"
            or guard["returncode"] != 0
            or guard["cleanup_complete"] is not True
            or guard["source_tree_sha256"] != receipt["source_tree_sha256"]
            or guard["command_sha256"] != receipt["command_sha256"]
            or guard["limits"] != receipt["limits"]
        ):
            return False
        job = read_json(paths["job"])
        if job["nodes"] != expected_nodes or job["collect_only"] is not False:
            return False
        if Path(job["events_path"]).resolve() != paths["events"].resolve():
            return False
        evidence = inspect_events(
            paths["events"], job_digest=digest_file(paths["job"]), expected_nodes=expected_nodes
        )
        if evidence["configuration"] != receipt["configuration"]:
            return False
        verify_invocation(guard, paths["job"], evidence["configuration"], receipt.get("command"))
        actual = account_batch(
            expected_nodes,
            evidence["phases"],
            child_state=guard["state"],
            returncode=guard["returncode"],
            subtests=evidence["subtests"],
        )
        return actual["state"] == "PASSED" and actual == receipt["accounting"]
    except (OSError, ValueError, TypeError, KeyError):
        return False
