"""Independent durable-proof controls, prepared before batch runner execution."""

import hashlib
import json
from dataclasses import asdict

import pytest

from scripts.recovery.batch_evidence import digest_file, verify_resume, write_record
from scripts.recovery.resource_guard import ResourceLimits, ResourceSample, RunReceipt
from scripts.recovery.sequential import account_batch


def evidence(tmp_path):
    node = "tests/unit/x.py::test_case[α β]"
    job = tmp_path / "job.json"
    events = tmp_path / "pytest.jsonl"
    guard = tmp_path / "guard.json"
    write_record(job, {"nodes": [node], "collect_only": False, "events_path": str(events)})
    config = {
        "kind": "configured",
        "environment": {"python": "mechanical only", "invoked_executable": "/mechanical/python"},
        "plugin_policy": "explicit-socket-asyncio-v1",
        "marker_policy": "not network",
    }
    phases = [
        {"nodeid": node, "when": phase, "outcome": "passed", "duration": 0.1}
        for phase in ("setup", "call", "teardown")
    ]
    payload = [
        {"kind": "job", "sha256": digest_file(job)},
        config,
        {"kind": "collection", "nodes": [node], "deselected": [], "import_collection_seconds": 0.1},
        *[{"kind": "phase", **phase} for phase in phases],
        {"kind": "session_finish", "exitstatus": 0, "elapsed_seconds": 0.4},
    ]
    events.write_text("".join(json.dumps(event) + "\n" for event in payload))
    command = [
        "/mechanical/python",
        "-B",
        "-m",
        "scripts.recovery.pytest_child",
        str(job.resolve()),
    ]
    command_digest = hashlib.sha256(json.dumps(command).encode()).hexdigest()
    limits = asdict(ResourceLimits(soft_bytes=256000000, hard_bytes=384000000, policy_version=1))
    samples = [
        ResourceSample(float(index), 10, 5, 5, 1, 2000000000, 0, ()) for index in range(1, 5)
    ]
    write_record(
        guard,
        asdict(
            RunReceipt(
                state="PASSED",
                reason=None,
                returncode=0,
                elapsed_seconds=0.4,
                peak_rss_bytes=10,
                peak_footprint_bytes=5,
                samples=4,
                command_sha256=command_digest,
                source_commit="mechanical",
                source_diff_sha256="d" * 64,
                source_tree_sha256="b" * 64,
                cleanup_complete=True,
                limits=ResourceLimits(**limits),
            )
        ),
    )
    guard.with_suffix(".log").write_text("mechanical proof only; not a native run\n")
    guard.with_suffix(".samples.jsonl").write_text(
        "".join(json.dumps(asdict(sample)) + "\n" for sample in samples)
    )
    files = {
        "guard": guard,
        "job": job,
        "events": events,
        "log": guard.with_suffix(".log"),
        "samples": guard.with_suffix(".samples.jsonl"),
    }
    receipt = tmp_path / "batch.json"
    write_record(
        receipt,
        {
            "source_identity": "a" * 64,
            "expected_nodes": [node],
            "state": "PASSED",
            "cleanup_complete": True,
            "required_gates": {"guard": "PASSED"},
            "source_tree_sha256": "b" * 64,
            "command_sha256": command_digest,
            "command": command,
            "limits": limits,
            "configuration": config,
            "accounting": account_batch([node], phases, child_state="PASSED", returncode=0),
            "evidence": {
                key: {"name": path.name, "sha256": digest_file(path)} for key, path in files.items()
            },
        },
    )
    return receipt, node, files


def test_resume_reopens_all_proof_bytes_and_recomputes_accounting(tmp_path):
    receipt, node, _ = evidence(tmp_path)
    assert verify_resume(receipt, source_identity="a" * 64, expected_nodes=[node])
    assert not verify_resume(receipt, source_identity="d" * 64, expected_nodes=[node])
    assert not verify_resume(receipt, source_identity="a" * 64, expected_nodes=[node, "extra"])


@pytest.mark.parametrize("kind", ["guard", "job", "events", "log", "samples"])
@pytest.mark.parametrize("attack", ["missing", "changed"])
def test_missing_or_changed_dependency_blocks_resume(tmp_path, kind, attack):
    receipt, node, files = evidence(tmp_path)
    if attack == "missing":
        files[kind].unlink()
    else:
        with files[kind].open("a") as stream:
            stream.write("altered")
    assert not verify_resume(receipt, source_identity="a" * 64, expected_nodes=[node])


def test_fabricated_complete_flags_without_proof_are_not_resume_evidence(tmp_path):
    receipt = tmp_path / "flags.json"
    write_record(
        receipt,
        {
            "source_identity": "a" * 64,
            "expected_nodes": ["node"],
            "state": "PASSED",
            "cleanup_complete": True,
            "required_gates": {"guard": "PASSED"},
        },
    )
    assert not verify_resume(receipt, source_identity="a" * 64, expected_nodes=["node"])


def test_rehashed_events_still_need_actual_complete_phases(tmp_path):
    receipt, node, files = evidence(tmp_path)
    lines = files["events"].read_text().splitlines()
    files["events"].write_text("\n".join(line for line in lines if '"teardown"' not in line) + "\n")
    payload = json.loads(receipt.read_text())
    payload["evidence"]["events"]["sha256"] = digest_file(files["events"])
    receipt.write_text(json.dumps(payload))
    assert not verify_resume(receipt, source_identity="a" * 64, expected_nodes=[node])


def test_foreign_plugin_policy_fails_even_with_updated_file_hash(tmp_path):
    receipt, node, files = evidence(tmp_path)
    files["events"].write_text(
        files["events"].read_text().replace("explicit-socket-asyncio-v1", "unrestricted")
    )
    payload = json.loads(receipt.read_text())
    payload["evidence"]["events"]["sha256"] = digest_file(files["events"])
    receipt.write_text(json.dumps(payload))
    assert not verify_resume(receipt, source_identity="a" * 64, expected_nodes=[node])


def test_rehashed_unsafe_native_sample_cannot_resume(tmp_path):
    receipt, node, files = evidence(tmp_path)
    values = [json.loads(line) for line in files["samples"].read_text().splitlines()]
    values[-1]["pressure"] = 2
    files["samples"].write_text("".join(json.dumps(value) + "\n" for value in values))
    payload = json.loads(receipt.read_text())
    payload["evidence"]["samples"]["sha256"] = digest_file(files["samples"])
    receipt.write_text(json.dumps(payload))
    assert not verify_resume(receipt, source_identity="a" * 64, expected_nodes=[node])


def test_guard_for_another_command_cannot_certify_pytest_resume(tmp_path):
    receipt, node, files = evidence(tmp_path)
    payload = json.loads(receipt.read_text())
    guard = json.loads(files["guard"].read_text())
    guard["command_sha256"] = "e" * 64
    files["guard"].write_text(json.dumps(guard))
    payload["command_sha256"] = "e" * 64
    payload["evidence"]["guard"]["sha256"] = digest_file(files["guard"])
    receipt.write_text(json.dumps(payload))
    assert not verify_resume(receipt, source_identity="a" * 64, expected_nodes=[node])


@pytest.mark.parametrize("attack", [None, "paging", "unknown", "early_child"])
def test_v2_proof_replays_paging_and_completed_preflight(tmp_path, attack):
    from dataclasses import replace

    from scripts.recovery.batch_evidence import verify_guard

    _, _, files = evidence(tmp_path)
    guard = json.loads(files["guard"].read_text())
    guard["limits"] = asdict(
        ResourceLimits(
            soft_bytes=256000000,
            hard_bytes=384000000,
            allow_warning=True,
            min_headroom_bytes=1000000000,
        )
    )
    files["guard"].write_text(json.dumps(guard))
    samples = [
        ResourceSample(float(i), 10, 5, 5, 2, 2000000000, 5000000000, (), 0, 0, 0, 0)
        for i in range(1, 5)
    ]
    if attack == "paging":
        samples[-1] = replace(samples[-1], swapouts_bytes=200000000)
    elif attack == "unknown":
        samples[-1] = replace(samples[-1], swapouts_bytes=None)
    elif attack == "early_child":
        samples[1] = replace(samples[1], pids=(123,))
    files["samples"].write_text("".join(json.dumps(asdict(s)) + "\n" for s in samples))
    if attack is None:
        assert verify_guard(files["guard"], files["samples"])["state"] == "PASSED"
    else:
        with pytest.raises(ValueError):
            verify_guard(files["guard"], files["samples"])
