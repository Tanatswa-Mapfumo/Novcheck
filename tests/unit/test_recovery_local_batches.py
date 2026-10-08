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


@pytest.mark.parametrize(
    "attack", ["stale", "foreign", "duplicate", "large_limit", "weak_headroom", "weak_swap"]
)
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
        limits = ResourceLimits()
    elif attack == "weak_headroom":
        limits = ResourceLimits(soft_bytes=256000000, hard_bytes=384000000, min_headroom_bytes=1)
    else:
        limits = ResourceLimits(
            soft_bytes=256000000, hard_bytes=384000000, max_swap_bytes=9000000000
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
