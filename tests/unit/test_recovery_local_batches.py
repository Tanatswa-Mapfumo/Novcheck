"""Coordinator controls without launching application/native test workloads."""

from pathlib import Path

import pytest

from scripts.recovery import local_batches
from scripts.recovery.resource_guard import ResourceLimits


def environment(tmp_path, monkeypatch):
    (tmp_path / "source.py").write_text("source bytes\n")
    (tmp_path / "uv.lock").write_text("locked recipe\n")
    python = tmp_path / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"mechanical interpreter identity, never executed")
    metadata = (
        tmp_path / ".venv" / "lib" / "python3.12" / "site-packages" / "toy.dist-info" / "METADATA"
    )
    metadata.parent.mkdir(parents=True)
    metadata.write_text("Name: mechanical\nVersion: 1\n")
    listing = ["source.py", "uv.lock"]
    monkeypatch.setattr(
        local_batches.subprocess,
        "check_output",
        lambda *args, **kwargs: "\0".join(listing).encode() + b"\0",
    )
    return python, metadata, listing


@pytest.mark.parametrize(
    "attack", ["source", "mode", "new_file", "lock", "environment", "package", "python"]
)
def test_execution_identity_invalidates_every_relevant_change(tmp_path, monkeypatch, attack):
    python, metadata, listing = environment(tmp_path, monkeypatch)
    before = local_batches.execution_identity(tmp_path, python)[0]
    if attack == "source":
        (tmp_path / "source.py").write_text("changed source\n")
    elif attack == "mode":
        (tmp_path / "source.py").chmod(0o700)
    elif attack == "new_file":
        (tmp_path / "new.py").write_text("new untracked implementation\n")
        listing.append("new.py")
    elif attack == "lock":
        (tmp_path / "uv.lock").write_text("different locked recipe\n")
    elif attack == "environment":
        monkeypatch.setenv("NOVCHECK_CONTROL_TEST", "changed")
    elif attack == "package":
        metadata.write_text("Name: mechanical\nVersion: 2\n")
    else:
        python.write_bytes(b"changed interpreter")
    assert local_batches.execution_identity(tmp_path, python)[0] != before


def test_same_bytes_and_configuration_preserve_execution_identity(tmp_path, monkeypatch):
    python, _, _ = environment(tmp_path, monkeypatch)
    before = local_batches.execution_identity(tmp_path, python)[0]
    assert local_batches.execution_identity(tmp_path, python)[0] == before


@pytest.mark.parametrize("attack", ["stale", "foreign", "duplicate"])
def test_invalid_batch_is_rejected_before_guard_dispatch(monkeypatch, attack):
    monkeypatch.setattr(local_batches, "execution_identity", lambda *args: ("source", "tree", {}))

    def forbidden(*args, **kwargs):
        pytest.fail("invalid configuration reached dispatch")

    monkeypatch.setattr(local_batches, "_dispatch", forbidden)
    node = "tests/x.py::test_a"
    inventory = {
        "source_identity": "source",
        "source_tree_sha256": "tree",
        "expected_nodes": [node],
    }
    nodes = [node]
    limits = ResourceLimits(soft_bytes=256000000, hard_bytes=384000000)
    if attack == "stale":
        inventory["source_identity"] = "foreign"
    elif attack == "foreign":
        nodes = ["tests/x.py::test_b"]
    elif attack == "duplicate":
        nodes = [node, node]
    elif attack == "large_limit":
        limits = ResourceLimits(soft_bytes=2_500_000_000, hard_bytes=3_000_000_000)
    elif attack == "weak_headroom":
        limits = ResourceLimits(soft_bytes=256000000, hard_bytes=384000000, min_headroom_bytes=1)
    else:
        limits = ResourceLimits(
            soft_bytes=256000000, hard_bytes=384000000, max_paging_bytes_per_second=64000000
        )
    with pytest.raises(ValueError):
        local_batches.run_batch(
            Path("."),
            Path("python"),
            Path("unused"),
            inventory=inventory,
            nodes=nodes,
            limits=limits,
        )


def test_pytest_observation_state_does_not_prevent_cross_node_fixture_reuse(tmp_path, monkeypatch):
    python, _, _ = environment(tmp_path, monkeypatch)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/x.py::test_first (setup)")
    first = local_batches.execution_identity(tmp_path, python)[0]
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/x.py::test_second (call)")
    assert local_batches.execution_identity(tmp_path, python)[0] == first


@pytest.mark.parametrize("resume", [False, True])
def test_measured_dispatch_is_sequential_and_partial_inventory_is_not_a_suite_pass(
    tmp_path, monkeypatch, resume
):
    from dataclasses import asdict

    nodes = ["tests/x.py::test_a", "tests/x.py::test_b"]
    limits = ResourceLimits(
        soft_bytes=256000000,
        hard_bytes=384000000,
        policy_version=2,
        allow_warning=True,
        min_headroom_bytes=1000000000,
    )
    batches = [
        {
            "nodes": [node],
            "limits": asdict(limits),
            "capacity_evidence": str(tmp_path / f"proof-{i}.json"),
        }
        for i, node in enumerate(nodes)
    ]
    monkeypatch.setattr(
        local_batches,
        "plan_measured_batches",
        lambda *args, **kwargs: {"batches": batches, "unmeasured_nodes": ["tests/x.py::test_c"]},
    )
    monkeypatch.setattr(local_batches, "load_inventory", lambda *args: {"total_seconds": 2})
    calls = []

    def run(cwd, python, directory, **kwargs):
        calls.append((kwargs["nodes"], kwargs["resume_from"]))
        return (
            {"state": "RESUMED", "receipt": str(kwargs["resume_from"])}
            if resume
            else {"state": "PASSED"}
        )

    monkeypatch.setattr(local_batches, "run_batch", run)
    monkeypatch.setattr(
        local_batches, "account_complete_inventory", lambda *args, **kwargs: {"state": "INCOMPLETE"}
    )
    result = local_batches.execute_measured_plan(
        Path("inventory"),
        [],
        tmp_path / "session",
        cwd=tmp_path,
        python=Path("python"),
        resume=resume,
    )
    assert [call[0] for call in calls] == [[node] for node in nodes]
    assert all((call[1] is not None) == resume for call in calls)
    assert result["execution_state"] == "PASSED"
    assert result["coverage"]["state"] == "INCOMPLETE"
    assert result["final_acceptance"] == "NOT_ESTABLISHED"


def test_measured_dispatch_stops_after_resource_refusal(tmp_path, monkeypatch):
    from dataclasses import asdict

    limits = ResourceLimits(soft_bytes=256000000, hard_bytes=384000000)
    monkeypatch.setattr(
        local_batches,
        "plan_measured_batches",
        lambda *args, **kwargs: {
            "batches": [
                {
                    "nodes": ["tests/x.py::test_a"],
                    "limits": asdict(limits),
                    "capacity_evidence": "proof",
                }
            ]
            * 2,
            "unmeasured_nodes": [],
        },
    )
    monkeypatch.setattr(local_batches, "load_inventory", lambda *args: {"total_seconds": 2})
    calls = []

    def refuse(*args, **kwargs):
        calls.append(1)
        return {"state": "INCOMPLETE", "guard": {"reason": "LOW_HEADROOM"}}

    monkeypatch.setattr(local_batches, "run_batch", refuse)
    monkeypatch.setattr(
        local_batches, "account_complete_inventory", lambda *args, **kwargs: {"state": "INCOMPLETE"}
    )
    result = local_batches.execute_measured_plan(
        Path("inventory"), [], tmp_path / "session", cwd=tmp_path, python=Path("python")
    )
    assert calls == [1]
    assert result["execution_state"] == "INCOMPLETE"
    assert result["outcomes"][0]["reason"] == "LOW_HEADROOM"
