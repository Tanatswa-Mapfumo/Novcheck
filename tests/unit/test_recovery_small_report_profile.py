"""Measured small report reload calibration; danger stops remain mandatory."""

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


def limits():
    return ResourceLimits(
        soft_bytes=320_000_000,
        hard_bytes=448_000_000,
        launch_headroom_bytes=1_400_000_000,
        min_headroom_bytes=1_100_000_000,
        allow_warning=True,
        timeout_seconds=5,
    )


def test_measured_small_report_profile_requires_explicit_reserves_and_caps():
    profile = limits()
    assert approved_local_limits(profile)
    for change in (
        {"launch_headroom_bytes": 1_399_999_999},
        {"min_headroom_bytes": 1_099_999_999},
        {"soft_bytes": 320_000_001},
        {"hard_bytes": 448_000_001},
    ):
        with pytest.raises(ValueError):
            replace(profile, **change)


def test_small_report_launch_floor_refuses_before_any_child(tmp_path):
    marker = tmp_path / "launched"
    result = run_guarded(
        (sys.executable, "-I", "-S", "-c", f"open({str(marker)!r},'w').close()"),
        cwd=Path.cwd(),
        limits=limits(),
        output=tmp_path / "receipt.json",
        lock_path=tmp_path / "lock",
        collector=lambda pgid: replace(
            safe_sample(),
            pressure=2,
            headroom_bytes=1_399_999_999,
            pageins_bytes=0,
            pageouts_bytes=0,
            swapins_bytes=0,
            swapouts_bytes=0,
        ),
    )
    assert (result.state, result.reason) == ("REFUSED", "LOW_HEADROOM")
    assert not marker.exists()


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"headroom_bytes": 1_099_999_999}, "LOW_HEADROOM"),
        ({"pressure": 4}, "MEMORY_PRESSURE"),
        ({"pressure": None}, "MEMORY_PRESSURE_UNKNOWN"),
        ({"rss_bytes": 320_000_000}, "SOFT_MEMORY_LIMIT"),
        ({"footprint_bytes": 320_000_000}, "SOFT_MEMORY_LIMIT"),
        ({"peak_footprint_bytes": 448_000_000}, "HARD_MEMORY_LIMIT"),
        ({"pageouts_bytes": None}, "PAGING_UNKNOWN"),
    ],
)
def test_small_report_calibration_retains_runtime_danger_stops(change, reason):
    sample = replace(
        safe_sample(),
        pressure=2,
        headroom_bytes=1_400_000_000,
        pageins_bytes=0,
        pageouts_bytes=0,
        swapins_bytes=0,
        swapouts_bytes=0,
    )
    assert RiskMonitor(limits()).check(replace(sample, **change)) == reason


def test_small_report_retains_severe_and_capacity_coupled_paging():
    base = replace(
        safe_sample(),
        pressure=2,
        headroom_bytes=1_450_000_000,
        monotonic_seconds=10,
        pageins_bytes=0,
        pageouts_bytes=0,
        swapins_bytes=0,
        swapouts_bytes=0,
    )
    for bytes_out, headroom in ((192_000_000, 1_450_000_000), (48_000_000, 1_300_000_000)):
        monitor = RiskMonitor(limits())
        assert monitor.check(base) is None
        assert (
            monitor.check(
                replace(
                    base,
                    monotonic_seconds=13,
                    swapouts_bytes=bytes_out,
                    headroom_bytes=headroom,
                )
            )
            == "SUSTAINED_PAGING"
        )


def test_small_report_may_run_between_launch_and_runtime_reserves(tmp_path):
    clock = 10

    def collect(pgid):
        nonlocal clock
        clock += 1
        return replace(
            safe_sample(),
            pressure=2,
            monotonic_seconds=clock,
            headroom_bytes=1_200_000_000 if pgid else 1_450_000_000,
            pageins_bytes=0,
            pageouts_bytes=0,
            swapins_bytes=0,
            swapouts_bytes=0,
        )

    result = run_guarded(
        (sys.executable, "-I", "-S", "-c", "pass"),
        cwd=Path.cwd(),
        limits=limits(),
        output=tmp_path / "receipt.json",
        lock_path=tmp_path / "lock",
        collector=collect,
    )
    assert result.state == "PASSED" and result.cleanup_complete
