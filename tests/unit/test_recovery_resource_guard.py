"""Safety control tests: removing refusal, locking or cleanup must fail these tests."""

import fcntl
import json
import os
import sys
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path

from scripts.recovery.resource_guard import ResourceLimits, ResourceSample, run_guarded, stop_reason


def safe_sample(pgid=None):
    return ResourceSample(time.monotonic(), 0, 0, 0, 1, 4_000_000_000, 0, ())


class ResourceGuardTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.output = self.root / "receipt.json"
        self.lock = self.root / "exclusive.lock"
        self.limits = ResourceLimits(
            soft_bytes=2_500_000_000,
            hard_bytes=3_000_000_000,
            timeout_seconds=2,
            grace_seconds=0.2,
            policy_version=1,
        )

    def tearDown(self):
        self.directory.cleanup()

    def run_child(self, code, collector=safe_sample, **kwargs):
        return run_guarded(
            (sys.executable, "-I", "-S", "-c", code),
            cwd=Path.cwd(),
            limits=self.limits,
            output=self.output,
            collector=collector,
            lock_path=self.lock,
            **kwargs,
        )

    def test_warning_or_unknown_pressure_prevents_child_launch(self):
        for pressure in (None, 2, 4):
            with self.subTest(pressure=pressure):
                self.output = self.root / f"receipt-pressure-{pressure}.json"
                marker = self.root / "launched"
                result = self.run_child(
                    f"open({str(marker)!r}, 'w').close()",
                    collector=lambda pgid: replace(safe_sample(), pressure=pressure),
                )
                self.assertEqual(result.state, "REFUSED")
                self.assertFalse(marker.exists())

    def test_native_exited_process_race_is_distinct_from_live_unreadable_process(self):
        import ctypes
        import errno
        from types import SimpleNamespace
        from unittest.mock import patch

        from scripts.recovery import resource_guard as guard

        collector = guard.MacCollector()

        def failed(pid, flavor, buffer):
            ctypes.set_errno(errno.EPERM)
            return -1

        collector.libproc = SimpleNamespace(proc_pid_rusage=failed)

        def output(command):
            if "vm_stat" in command[0]:
                return (
                    "page size of 16384 bytes\nPages free: 200000.\nPages inactive: 1.\n"
                    "Pageins: 0.\nPageouts: 0.\nSwapins: 0.\nSwapouts: 0."
                )
            return "used = 0.00M" if "vm.swapusage" in command else "1"

        with patch.object(guard, "_output", side_effect=output):
            with patch.object(guard, "process_tree_members", side_effect=[(99,), ()]):
                sample = collector(98)
                self.assertEqual(sample.rss_bytes, 0)
            with patch.object(guard, "process_tree_members", return_value=(99,)):
                with self.assertRaises(PermissionError):
                    collector(98)

    def test_nonoverlapping_child_peaks_are_not_summed(self):
        import ctypes
        from types import SimpleNamespace
        from unittest.mock import patch

        from scripts.recovery import resource_guard as guard

        collector = guard.MacCollector()

        def usage(pid, flavor, buffer):
            value = ctypes.cast(buffer, ctypes.POINTER(guard._Rusage)).contents
            value.resident_size = 100
            value.phys_footprint = 80
            value.lifetime_max_phys_footprint = 90
            return 0

        collector.libproc = SimpleNamespace(proc_pid_rusage=usage)

        def output(command):
            if "vm_stat" in command[0]:
                return (
                    "page size of 16384 bytes\nPages free: 200000.\nPages inactive: 1.\n"
                    "Pageins: 0.\nPageouts: 0.\nSwapins: 0.\nSwapouts: 0."
                )
            return "used = 0.00M" if "vm.swapusage" in command else "1"

        with (
            patch.object(guard, "_output", side_effect=output),
            patch.object(guard, "process_tree_members", side_effect=[(11,), (12,), (12, 13)]),
        ):
            first, second, concurrent = collector(10), collector(10), collector(10)
        self.assertEqual(first.peak_footprint_bytes, 90)
        self.assertEqual(second.peak_footprint_bytes, 90)
        self.assertEqual(concurrent.peak_footprint_bytes, 180)

    def test_slow_monitor_prevents_launch(self):
        marker = self.root / "launched"

        def slow(pgid):
            time.sleep(0.21)
            return safe_sample()

        result = self.run_child(f"open({str(marker)!r},'w').close()", collector=slow)
        self.assertEqual(result.reason, "MONITOR_TOO_SLOW")
        self.assertEqual(result.state, "REFUSED")
        self.assertFalse(marker.exists())

    def test_child_tree_peak_triggers_stop(self):
        def collect(pgid):
            sample = safe_sample()
            return replace(sample, peak_footprint_bytes=3_000_000_001) if pgid else sample

        result = self.run_child("import time; time.sleep(30)", collector=collect)
        self.assertEqual(result.state, "ABORTED")
        self.assertEqual(result.reason, "HARD_MEMORY_LIMIT")
        self.assertIsNotNone(result.returncode)
        self.assertLess(result.elapsed_seconds, 2)

    def test_second_intensive_run_cannot_acquire_lock(self):
        with self.lock.open("a") as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            marker = self.root / "launched"
            result = self.run_child(f"open({str(marker)!r}, 'w').close()")
            self.assertEqual(result.reason, "ANOTHER_RUN_ACTIVE")
            self.assertFalse(marker.exists())

    def test_monitor_failure_and_interrupt_reap_child_group(self):
        for failure in (RuntimeError, KeyboardInterrupt):
            with self.subTest(failure=failure):
                self.output = self.root / f"receipt-{failure.__name__}.json"
                pids = []

                def collect(pgid):
                    if pgid:
                        pids.append(pgid)
                        raise failure("controlled monitoring failure")
                    return safe_sample()

                result = self.run_child("import time; time.sleep(30)", collector=collect)
                self.assertEqual(result.state, "ABORTED")
                self.assertIsNotNone(result.returncode)
                with self.assertRaises(ProcessLookupError):
                    os.kill(pids[0], 0)

    def test_aborted_run_never_reports_pass(self):
        result = self.run_child(
            "import time; time.sleep(30)",
            collector=lambda pgid: (
                replace(safe_sample(), headroom_bytes=1) if pgid else safe_sample()
            ),
        )
        self.assertEqual(result.state, "ABORTED")
        self.assertEqual(json.loads(self.output.read_text())["state"], "ABORTED")

    def test_success_failure_timeout_and_no_overwrite(self):
        result = self.run_child("print('tiny child complete')")
        self.assertEqual(result.state, "PASSED")
        self.assertEqual(result.returncode, 0)
        with self.assertRaises(FileExistsError):
            self.run_child("pass")
        self.output = self.root / "receipt-failure.json"
        self.assertEqual(self.run_child("raise SystemExit(7)").state, "FAILED")
        self.output = self.root / "receipt-timeout.json"
        self.limits = replace(self.limits, timeout_seconds=0.15)
        self.assertEqual(self.run_child("import time; time.sleep(30)").reason, "TIME_LIMIT")

    def test_nonfinite_limits_cannot_disable_timeout_or_swap_guard(self):
        for changes in (
            {"timeout_seconds": float("inf")},
            {"grace_seconds": float("nan")},
            {"max_swap_bytes": float("nan")},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(self.limits, **changes)

    def test_limits_and_each_system_guard(self):
        for changes in (
            {"hard_bytes": 3_000_000_001},
            {"soft_bytes": 0},
            {"sample_seconds": 0.3},
            {"timeout_seconds": 0},
        ):
            with self.assertRaises(ValueError):
                replace(self.limits, **changes)
        for changes, reason in (
            ({"rss_bytes": 2_500_000_000}, "SOFT_MEMORY_LIMIT"),
            ({"footprint_bytes": 3_000_000_000}, "HARD_MEMORY_LIMIT"),
            ({"headroom_bytes": None}, "UNKNOWN_SYSTEM_MEMORY"),
            ({"swap_bytes": 3_000_000_000}, "SWAP_LIMIT"),
        ):
            self.assertEqual(stop_reason(replace(safe_sample(), **changes), self.limits), reason)

    def test_sigterm_interrupts_supervisor_and_reaps_its_child(self):
        import subprocess

        child_pidfile = self.root / "child-pid"
        control = self.root / "supervisor-pid"
        code = (
            "import os,time; "
            f"open({str(child_pidfile)!r},'w').write(str(os.getpid())); time.sleep(30)"
        )
        driver = (
            "import os,time; from pathlib import Path; "
            "from scripts.recovery.resource_guard import "
            "run_guarded,ResourceLimits,ResourceSample; "
            f"open({str(control)!r},'w').write(str(os.getpid())); "
            "collect=lambda pg:ResourceSample(time.monotonic(),0,0,0,1,4000000000,0,()); "
            f"run_guarded(({sys.executable!r},'-I','-S','-c',{code!r}),cwd=Path.cwd(),"
            f"limits=ResourceLimits(policy_version=1),output=Path({str(self.output)!r}),collector=collect,"
            f"lock_path=Path({str(self.lock)!r}))"
        )
        supervisor = subprocess.Popen([sys.executable, "-S", "-B", "-c", driver])
        try:
            deadline = time.monotonic() + 3
            while not child_pidfile.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(child_pidfile.exists())
            supervisor.terminate()
            supervisor.wait(timeout=3)
            pid = int(child_pidfile.read_text())
            status = subprocess.run(
                ["/bin/ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True
            ).stdout.strip()
            self.assertTrue(not status or status.startswith("Z"), status)
            self.assertEqual(json.loads(self.output.read_text())["state"], "ABORTED")
        finally:
            if supervisor.poll() is None:
                supervisor.kill()
                supervisor.wait()
            if child_pidfile.exists():
                try:
                    os.kill(int(child_pidfile.read_text()), 9)
                except ProcessLookupError:
                    pass

    def test_new_session_descendant_is_accounted_and_cleaned(self):
        import subprocess

        from scripts.recovery import resource_guard

        known = set()

        def collect(pgid):
            if not pgid:
                return safe_sample()
            pids = resource_guard.process_tree_members(pgid, known)
            known.update(pids)
            return replace(safe_sample(), pids=pids)

        pidfile = self.root / "escaped-child"
        code = (
            "import subprocess,sys,time; "
            "p=subprocess.Popen([sys.executable,'-I','-S','-c','import time; time.sleep(30)'],"
            "start_new_session=True); "
            f"open({str(pidfile)!r},'w').write(str(p.pid)); time.sleep(.4)"
        )
        try:
            result = self.run_child(code, collector=collect)
            self.assertEqual(result.reason, "DESCENDANTS_AFTER_EXIT")
            pid = int(pidfile.read_text())
            self.assertIn(pid, known)
            status = subprocess.run(
                ["/bin/ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True
            ).stdout.strip()
            self.assertTrue(not status or status.startswith("Z"), status)
        finally:
            if pidfile.exists():
                try:
                    os.kill(int(pidfile.read_text()), 9)
                except ProcessLookupError:
                    pass

    def test_descendant_is_terminated_when_root_finishes(self):
        pidfile = self.root / "descendant"
        code = (
            "import subprocess,sys,time; "
            "p=subprocess.Popen([sys.executable,'-I','-S','-c','import time; time.sleep(30)']); "
            f"open({str(pidfile)!r},'w').write(str(p.pid)); time.sleep(.2)"
        )
        result = self.run_child(code)
        self.assertEqual(result.reason, "DESCENDANTS_AFTER_EXIT")
        pid = int(pidfile.read_text())
        # A dead zombie awaiting OS reaping is harmless; a running child is not.
        import subprocess

        state = subprocess.run(
            ["/bin/ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True
        ).stdout.strip()
        self.assertTrue(not state or state.startswith("Z"), state)


if __name__ == "__main__":
    unittest.main()


class RiskPolicyTests(unittest.TestCase):
    def setUp(self):
        from scripts.recovery.resource_guard import RiskMonitor

        self.limits = ResourceLimits(
            soft_bytes=256_000_000,
            hard_bytes=384_000_000,
            min_headroom_bytes=1_000_000_000,
            policy_version=2,
            allow_warning=True,
        )
        self.monitor = RiskMonitor(self.limits)

    def sample(self, seconds, **changes):
        return replace(
            safe_sample(),
            monotonic_seconds=seconds,
            pressure=2,
            swap_bytes=5_000_000_000,
            pageins_bytes=0,
            pageouts_bytes=0,
            swapins_bytes=0,
            swapouts_bytes=0,
            **changes,
        )

    def test_retained_swap_and_warning_allow_small_workload_after_observed_window(self):
        first = self.sample(10)
        self.assertIsNone(self.monitor.check(first))
        self.assertFalse(self.monitor.ready(first))
        final = self.sample(13)
        self.assertIsNone(self.monitor.check(final))
        self.assertTrue(self.monitor.ready(final))

    def test_sustained_output_paging_refuses_despite_ample_headroom(self):
        self.monitor.check(self.sample(10))
        sample = replace(self.sample(13), swapouts_bytes=192_000_000)
        self.assertEqual(self.monitor.check(sample), "SUSTAINED_PAGING")

    def test_severe_swapins_unknown_counters_and_counter_rewind_stop(self):
        self.monitor.check(self.sample(10))
        self.assertEqual(
            self.monitor.check(replace(self.sample(13), swapins_bytes=768_000_000)),
            "SUSTAINED_SWAPINS",
        )
        from scripts.recovery.resource_guard import RiskMonitor

        monitor = RiskMonitor(self.limits)
        self.assertEqual(
            monitor.check(replace(self.sample(10), swapouts_bytes=None)), "PAGING_UNKNOWN"
        )
        monitor.check(replace(self.sample(10), swapouts_bytes=10))
        self.assertEqual(monitor.check(self.sample(11)), "PAGING_COUNTER_INVALID")

    def test_critical_unknown_pressure_headroom_and_process_limits_still_stop(self):
        for changes, reason in (
            ({"pressure": 4}, "MEMORY_PRESSURE"),
            ({"pressure": None}, "MEMORY_PRESSURE_UNKNOWN"),
            ({"headroom_bytes": 999_999_999}, "LOW_HEADROOM"),
            ({"rss_bytes": 256_000_000}, "SOFT_MEMORY_LIMIT"),
            ({"footprint_bytes": 384_000_000}, "HARD_MEMORY_LIMIT"),
        ):
            self.assertEqual(self.monitor.check(replace(self.sample(10), **changes)), reason)

    def test_warning_permission_cannot_authorize_large_workload(self):
        with self.assertRaises(ValueError):
            replace(self.limits, soft_bytes=1_500_000_000, hard_bytes=2_000_000_000)

    def test_v2_heavy_policy_ignores_allocated_swap_but_refuses_warning(self):
        from scripts.recovery.resource_guard import RiskMonitor

        limits = replace(self.limits, allow_warning=False, min_headroom_bytes=1_500_000_000)
        self.assertEqual(RiskMonitor(limits).check(self.sample(10)), "MEMORY_PRESSURE")
        self.assertIsNone(RiskMonitor(limits).check(replace(self.sample(10), pressure=1)))

    def test_moderate_paging_requires_capacity_or_growth_evidence(self):
        from scripts.recovery.resource_guard import RiskMonitor

        self.monitor.check(self.sample(10))
        stable = replace(self.sample(13), swapouts_bytes=60_000_000)
        self.assertIsNone(self.monitor.check(stable))
        for change in (
            {"headroom_bytes": 1_100_000_000},
            {"rss_bytes": 200_000_000},
            {"headroom_bytes": 3_800_000_000},
        ):
            monitor = RiskMonitor(self.limits)
            monitor.check(self.sample(10))
            self.assertEqual(monitor.check(replace(stable, **change)), "SUSTAINED_PAGING")


class QualifiedMediumPolicyTests(unittest.TestCase):
    def limits(self):
        return ResourceLimits(
            soft_bytes=320_000_000,
            hard_bytes=448_000_000,
            min_headroom_bytes=1_500_000_000,
            allow_warning=True,
        )

    def test_measured_medium_warning_profile_preserves_runtime_protection(self):
        from scripts.recovery.resource_guard import RiskMonitor, approved_local_limits

        limits = self.limits()
        self.assertTrue(approved_local_limits(limits))
        base = replace(
            safe_sample(),
            pressure=2,
            headroom_bytes=1_800_000_000,
            swap_bytes=5_000_000_000,
            pageins_bytes=0,
            pageouts_bytes=0,
            swapins_bytes=0,
            swapouts_bytes=0,
            monotonic_seconds=10,
        )
        monitor = RiskMonitor(limits)
        self.assertIsNone(monitor.check(base))
        self.assertIsNone(monitor.check(replace(base, monotonic_seconds=13)))
        self.assertEqual(
            monitor.check(replace(base, monotonic_seconds=14, footprint_bytes=320_000_000)),
            "SOFT_MEMORY_LIMIT",
        )

    def test_medium_profile_cannot_borrow_small_headroom_or_heavy_caps(self):
        with self.assertRaises(ValueError):
            replace(self.limits(), min_headroom_bytes=1_000_000_000)
        with self.assertRaises(ValueError):
            replace(self.limits(), soft_bytes=384_000_001, hard_bytes=512_000_000)
        with self.assertRaises(ValueError):
            replace(self.limits(), hard_bytes=512_000_001)

    def test_medium_profile_keeps_severe_paging_and_critical_pressure_stops(self):
        from scripts.recovery.resource_guard import RiskMonitor

        base = replace(
            safe_sample(),
            pressure=2,
            headroom_bytes=1_800_000_000,
            pageins_bytes=0,
            pageouts_bytes=0,
            swapins_bytes=0,
            swapouts_bytes=0,
            monotonic_seconds=10,
        )
        monitor = RiskMonitor(self.limits())
        self.assertIsNone(monitor.check(base))
        self.assertEqual(
            monitor.check(replace(base, monotonic_seconds=13, swapouts_bytes=192_000_000)),
            "SUSTAINED_PAGING",
        )
        self.assertEqual(
            RiskMonitor(self.limits()).check(replace(base, pressure=4)), "MEMORY_PRESSURE"
        )
        self.assertEqual(
            RiskMonitor(self.limits()).check(replace(base, headroom_bytes=1_499_999_999)),
            "LOW_HEADROOM",
        )


class CalibratedIRPolicyTests(unittest.TestCase):
    def limits(self):
        return ResourceLimits(
            soft_bytes=640_000_000,
            hard_bytes=896_000_000,
            min_headroom_bytes=1_000_000_000,
            launch_headroom_bytes=1_500_000_000,
            allow_warning=True,
            timeout_seconds=5,
        )

    def test_calibration_requires_explicit_launch_margin_and_keeps_caps(self):
        from scripts.recovery.resource_guard import approved_local_limits

        limits = self.limits()
        self.assertTrue(approved_local_limits(limits))
        for change in (
            {"launch_headroom_bytes": 1_499_999_999},
            {"min_headroom_bytes": 999_999_999},
            {"soft_bytes": 640_000_001},
            {"hard_bytes": 896_000_001},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replace(limits, **change)

    def test_launch_floor_is_enforced_before_any_child(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "launched"
            result = run_guarded(
                (sys.executable, "-I", "-S", "-c", f"open({str(marker)!r},'w').close()"),
                cwd=Path.cwd(),
                limits=self.limits(),
                output=root / "receipt.json",
                lock_path=root / "lock",
                collector=lambda pgid: replace(
                    safe_sample(),
                    pressure=2,
                    headroom_bytes=1_499_999_999,
                    pageins_bytes=0,
                    pageouts_bytes=0,
                    swapins_bytes=0,
                    swapouts_bytes=0,
                ),
            )
            self.assertEqual((result.state, result.reason), ("REFUSED", "LOW_HEADROOM"))
            self.assertFalse(marker.exists())

    def test_qualified_child_may_use_capacity_between_launch_and_runtime_floors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clock = 10

            def collect(pgid):
                nonlocal clock
                clock += 1
                return replace(
                    safe_sample(),
                    monotonic_seconds=clock,
                    pressure=2,
                    headroom_bytes=1_200_000_000 if pgid else 1_600_000_000,
                    pageins_bytes=0,
                    pageouts_bytes=0,
                    swapins_bytes=0,
                    swapouts_bytes=0,
                )

            result = run_guarded(
                (sys.executable, "-I", "-S", "-c", "pass"),
                cwd=Path.cwd(),
                limits=self.limits(),
                output=root / "receipt.json",
                lock_path=root / "lock",
                collector=collect,
            )
            self.assertEqual(result.state, "PASSED")
            self.assertTrue(result.cleanup_complete)

    def test_runtime_danger_still_stops_calibrated_profile(self):
        from scripts.recovery.resource_guard import RiskMonitor

        base = replace(
            safe_sample(),
            pressure=2,
            headroom_bytes=1_600_000_000,
            monotonic_seconds=10,
            pageins_bytes=0,
            pageouts_bytes=0,
            swapins_bytes=0,
            swapouts_bytes=0,
        )
        for change, reason in (
            ({"headroom_bytes": 999_999_999}, "LOW_HEADROOM"),
            ({"pressure": 4}, "MEMORY_PRESSURE"),
            ({"footprint_bytes": 640_000_000}, "SOFT_MEMORY_LIMIT"),
            ({"rss_bytes": 896_000_000}, "HARD_MEMORY_LIMIT"),
        ):
            with self.subTest(reason=reason):
                self.assertEqual(RiskMonitor(self.limits()).check(replace(base, **change)), reason)
        monitor = RiskMonitor(self.limits())
        self.assertIsNone(monitor.check(base))
        self.assertEqual(
            monitor.check(replace(base, monotonic_seconds=13, swapouts_bytes=192_000_000)),
            "SUSTAINED_PAGING",
        )
