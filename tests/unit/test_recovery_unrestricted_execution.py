"""Current execution ignores memory conditions while retaining lifecycle gates."""

import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.recovery.batch_evidence import verify_guard
from scripts.recovery.resource_guard import ResourceLimits, ResourceSample, run_guarded


@pytest.mark.parametrize("pressure", [None, 1, 2, 4])
def test_memory_conditions_never_prevent_launch_or_stop_child(tmp_path, pressure):
    marker = tmp_path / "finished"

    def observe(pid):
        return ResourceSample(
            time.monotonic(),
            100_000_000_000,
            100_000_000_000,
            100_000_000_000,
            pressure,
            0,
            100_000_000_000,
            (pid,) if pid else (),
            None,
            100_000_000_000,
            None,
            100_000_000_000,
        )

    receipt = run_guarded(
        (
            sys.executable,
            "-I",
            "-S",
            "-c",
            f"import time; time.sleep(.25); open({str(marker)!r}, 'w').write('done')",
        ),
        cwd=Path.cwd(),
        limits=ResourceLimits(timeout_seconds=3),
        output=tmp_path / "guard.json",
        collector=observe,
        lock_path=tmp_path / "lock",
    )
    assert receipt.state == "PASSED"
    assert marker.read_text() == "done"
    assert receipt.limits.policy_version == 3
    assert receipt.limits.soft_bytes == receipt.limits.hard_bytes == 0
    assert receipt.limits.min_headroom_bytes == receipt.limits.launch_headroom_bytes == 0
    assert (
        verify_guard(tmp_path / "guard.json", tmp_path / "guard.samples.jsonl")["state"] == "PASSED"
    )


@pytest.mark.parametrize("slow", [False, True])
def test_unavailable_or_slow_memory_observer_does_not_control_execution(tmp_path, slow):
    def observe(pid):
        if slow:
            time.sleep(0.21)
        raise PermissionError("memory metrics unavailable")

    receipt = run_guarded(
        (sys.executable, "-I", "-S", "-c", "pass"),
        cwd=Path.cwd(),
        limits=ResourceLimits(timeout_seconds=3),
        output=tmp_path / "guard.json",
        collector=observe,
        lock_path=tmp_path / "lock",
    )
    assert receipt.state == "PASSED"
    assert receipt.cleanup_complete
    assert (
        verify_guard(tmp_path / "guard.json", tmp_path / "guard.samples.jsonl")["state"] == "PASSED"
    )


def test_old_recipe_cannot_reenable_memory_limits(tmp_path):
    old = ResourceLimits(policy_version=2, soft_bytes=1, hard_bytes=2, min_headroom_bytes=1)
    receipt = run_guarded(
        (sys.executable, "-I", "-S", "-c", "pass"),
        cwd=Path.cwd(),
        limits=replace(old, timeout_seconds=3),
        output=tmp_path / "guard.json",
        lock_path=tmp_path / "lock",
    )
    assert receipt.state == "PASSED"
    assert receipt.limits.policy_version == 3
    assert receipt.samples == 0


def test_batch_normalizes_historical_recipe_before_dispatch(tmp_path, monkeypatch):
    from scripts.recovery import local_batches

    monkeypatch.setattr(local_batches, "execution_identity", lambda *args: ("source", "tree", {}))
    node = "tests/x.py::test_a"
    inventory = {
        "source_identity": "source",
        "source_tree_sha256": "tree",
        "expected_nodes": [node],
    }

    class Dispatched(Exception):
        pass

    def dispatch(cwd, python, directory, nodes, collect_only, limits):
        assert nodes == [node]
        assert limits.policy_version == 3
        assert limits.soft_bytes == limits.hard_bytes == limits.min_headroom_bytes == 0
        raise Dispatched

    monkeypatch.setattr(local_batches, "_dispatch", dispatch)
    with pytest.raises(Dispatched):
        local_batches.run_batch(
            Path.cwd(),
            Path(sys.executable),
            tmp_path,
            inventory=inventory,
            nodes=[node],
            limits=ResourceLimits(
                policy_version=2, soft_bytes=1, hard_bytes=2, min_headroom_bytes=1
            ),
        )
