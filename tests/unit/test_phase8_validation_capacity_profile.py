"""Measured Phase 8 validation reserve; unchanged paging and dangerous-case stops."""

import sys
from dataclasses import replace
from pathlib import Path

import pytest

from scripts.recovery.resource_guard import (
    ResourceLimits,
    RiskMonitor,
    approved_local_limits,
    run_guarded,
)
from tests.unit.test_recovery_resource_guard import safe_sample


def validation_limits():
    return ResourceLimits(
        soft_bytes=704_000_000,
        hard_bytes=896_000_000,
        min_headroom_bytes=1_100_000_000,
        launch_headroom_bytes=1_700_000_000,
        timeout_seconds=5,
        allow_warning=True,
    )


def sample(**changes):
    return replace(
        safe_sample(),
        **{
            "monotonic_seconds": 10,
            "pressure": 2,
            "headroom_bytes": 2_100_000_000,
            "swap_bytes": 8_000_000_000,
            "pageins_bytes": 0,
            "pageouts_bytes": 0,
            "swapins_bytes": 0,
            "swapouts_bytes": 0,
            **changes,
        },
    )


def test_measured_validation_profile_requires_explicit_extra_reserves():
    limits = validation_limits()
    assert approved_local_limits(limits)
    for change in (
        {"launch_headroom_bytes": 1_699_999_999},
        {"min_headroom_bytes": 1_099_999_999},
        {"soft_bytes": 704_000_001},
        {"hard_bytes": 896_000_001},
    ):
        with pytest.raises(ValueError):
            replace(limits, **change)
    # The original IR profile still has its existing ceiling and reserve.
    with pytest.raises(ValueError):
        replace(limits, launch_headroom_bytes=1_500_000_000, min_headroom_bytes=1_000_000_000)


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"rss_bytes": 704_000_000}, "SOFT_MEMORY_LIMIT"),
        ({"footprint_bytes": 704_000_000}, "SOFT_MEMORY_LIMIT"),
        ({"peak_footprint_bytes": 704_000_000}, "SOFT_MEMORY_LIMIT"),
        ({"rss_bytes": 896_000_000}, "HARD_MEMORY_LIMIT"),
        ({"pressure": 4}, "MEMORY_PRESSURE"),
        ({"pressure": 8}, "MEMORY_PRESSURE"),
        ({"pressure": None}, "MEMORY_PRESSURE_UNKNOWN"),
        ({"headroom_bytes": 1_099_999_999}, "LOW_HEADROOM"),
        ({"headroom_bytes": None}, "UNKNOWN_SYSTEM_MEMORY"),
        ({"swapouts_bytes": None}, "PAGING_UNKNOWN"),
    ],
)
def test_validation_profile_preserves_each_immediate_danger_stop(changes, reason):
    assert RiskMonitor(validation_limits()).check(sample(**changes)) == reason


@pytest.mark.parametrize(
    "last",
    [
        {"swapouts_bytes": 51_000_000, "headroom_bytes": 1_600_000_000},
        {"swapouts_bytes": 51_000_000, "footprint_bytes": 600_000_000},
        {"swapouts_bytes": 192_000_000},
    ],
)
def test_validation_profile_preserves_sustained_capacity_and_severe_paging(last):
    monitor = RiskMonitor(validation_limits())
    assert monitor.check(sample()) is None
    assert monitor.check(sample(monotonic_seconds=13, **last)) == "SUSTAINED_PAGING"


@pytest.mark.parametrize("launch_qualified", [False, True])
def test_validation_profile_launch_and_runtime_reserve_are_both_enforced(
    tmp_path, launch_qualified
):
    marker = tmp_path / "child"
    clock = 10

    def collect(pgid):
        nonlocal clock
        clock += 1
        return sample(
            monotonic_seconds=clock,
            headroom_bytes=1_200_000_000
            if pgid
            else 1_700_000_000
            if launch_qualified
            else 1_699_999_999,
        )

    receipt = run_guarded(
        (sys.executable, "-I", "-S", "-c", f"open({str(marker)!r}, 'w').close()"),
        cwd=Path.cwd(),
        limits=validation_limits(),
        output=tmp_path / "receipt.json",
        lock_path=tmp_path / "lock",
        collector=collect,
    )
    assert (receipt.state, receipt.reason) == (
        ("PASSED", None) if launch_qualified else ("REFUSED", "LOW_HEADROOM")
    )
    assert marker.exists() == launch_qualified
    assert receipt.cleanup_complete
