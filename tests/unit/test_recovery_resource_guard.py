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
        self.limits = ResourceLimits(timeout_seconds=2, grace_seconds=0.2)

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
                return "page size of 16384 bytes\nPages free: 200000.\nPages inactive: 1."
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
                return "page size of 16384 bytes\nPages free: 200000.\nPages inactive: 1."
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
            f"limits=ResourceLimits(),output=Path({str(self.output)!r}),collector=collect,"
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
