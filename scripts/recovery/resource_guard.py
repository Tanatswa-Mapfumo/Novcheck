"""Fail-closed macOS test supervisor; does not import the application.

Sampled thresholds reduce risk but cannot prevent transient allocation overshoot.
Receipts describe execution only, never repository acceptance or report authority.
"""

import argparse
import ctypes
import errno
import fcntl
import hashlib
import json
import math
import os
import re
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class ResourceLimits:
    soft_bytes: int = 2_500_000_000
    hard_bytes: int = 3_000_000_000
    min_headroom_bytes: int = 1_500_000_000
    max_swap_bytes: int = 2_000_000_000
    sample_seconds: float = 0.1
    timeout_seconds: float = 60
    grace_seconds: float = 0.5

    def __post_init__(self):
        if not all(math.isfinite(value) for value in asdict(self).values()):
            raise ValueError("limits must be finite")
        if not 0 < self.soft_bytes <= self.hard_bytes <= 3_000_000_000:
            raise ValueError("memory limits must be positive and at most 3 GB")
        if not 0 < self.sample_seconds <= 0.2:
            raise ValueError("sample cadence must be at most 0.2 seconds")
        if min(self.min_headroom_bytes, self.timeout_seconds, self.grace_seconds) <= 0:
            raise ValueError("headroom, timeout and grace must be positive")
        if self.max_swap_bytes < 0:
            raise ValueError("swap limit cannot be negative")


@dataclass(frozen=True)
class ResourceSample:
    monotonic_seconds: float
    rss_bytes: int
    footprint_bytes: int
    peak_footprint_bytes: int
    pressure: int | None
    headroom_bytes: int | None
    swap_bytes: int | None
    pids: tuple[int, ...]


@dataclass(frozen=True)
class RunReceipt:
    state: str
    reason: str | None
    returncode: int | None
    elapsed_seconds: float
    peak_rss_bytes: int
    peak_footprint_bytes: int
    samples: int
    command_sha256: str
    source_commit: str
    source_diff_sha256: str
    source_tree_sha256: str
    cleanup_complete: bool
    limits: ResourceLimits


def stop_reason(sample: ResourceSample, limits: ResourceLimits) -> str | None:
    peak = max(sample.rss_bytes, sample.footprint_bytes, sample.peak_footprint_bytes)
    if peak >= limits.hard_bytes:
        return "HARD_MEMORY_LIMIT"
    if peak >= limits.soft_bytes:
        return "SOFT_MEMORY_LIMIT"
    if sample.pressure != 1:
        return "MEMORY_PRESSURE_UNKNOWN" if sample.pressure is None else "MEMORY_PRESSURE"
    if sample.headroom_bytes is None or sample.swap_bytes is None:
        return "UNKNOWN_SYSTEM_MEMORY"
    if sample.headroom_bytes < limits.min_headroom_bytes:
        return "LOW_HEADROOM"
    if sample.swap_bytes > limits.max_swap_bytes:
        return "SWAP_LIMIT"
    return None


def _output(command: tuple[str, ...]) -> str:
    return subprocess.check_output(command, text=True, stderr=subprocess.PIPE, timeout=2)


def group_members(pgid: int) -> tuple[int, ...]:
    table = _output(("/bin/ps", "-axo", "pid=,pgid=,stat="))
    return tuple(
        int(pid)
        for line in table.splitlines()
        for pid, group, state in [line.split()]
        if int(group) == pgid and not state.startswith("Z")
    )


def process_tree_members(pgid: int, known: set[int]) -> tuple[int, ...]:
    table = _output(("/bin/ps", "-axo", "pid=,ppid=,pgid=,stat="))
    rows = [line.split() for line in table.splitlines()]
    living = {int(pid) for pid, parent, group, state in rows if not state.startswith("Z")}
    selected = ({pgid} | known) & living
    while True:
        expanded = selected | {
            int(pid)
            for pid, parent, group, state in rows
            if int(parent) in selected or int(group) == pgid
        }
        expanded &= living
        if expanded == selected:
            return tuple(sorted(selected))
        selected = expanded


# Exact RUSAGE_INFO_V4 layout from the installed macOS SDK sys/resource.h.
_RUSAGE_FIELDS = (
    "user_time system_time pkg_idle_wkups interrupt_wkups pageins wired_size "
    "resident_size phys_footprint proc_start_abstime proc_exit_abstime child_user_time "
    "child_system_time child_pkg_idle_wkups child_interrupt_wkups child_pageins "
    "child_elapsed_abstime diskio_bytesread diskio_byteswritten cpu_time_qos_default "
    "cpu_time_qos_maintenance cpu_time_qos_background cpu_time_qos_utility "
    "cpu_time_qos_legacy cpu_time_qos_user_initiated cpu_time_qos_user_interactive "
    "billed_system_time serviced_system_time logical_writes lifetime_max_phys_footprint "
    "instructions cycles billed_energy serviced_energy interval_max_phys_footprint runnable_time"
).split()


class _Rusage(ctypes.Structure):
    _fields_ = [("uuid", ctypes.c_uint8 * 16)] + [
        (name, ctypes.c_uint64) for name in _RUSAGE_FIELDS
    ]


class MacCollector:
    def __init__(self):
        if sys.platform != "darwin":
            raise RuntimeError("native collector requires macOS")
        self.libproc = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        self.libproc.proc_pid_rusage.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
        self.libproc.proc_pid_rusage.restype = ctypes.c_int
        self.peaks: dict[int, int] = {}
        self.known: set[int] = set()

    def __call__(self, pgid: int | None) -> ResourceSample:
        pressure = int(_output(("/usr/sbin/sysctl", "-n", "kern.memorystatus_vm_pressure_level")))
        vm = _output(("/usr/bin/vm_stat",))
        page_size = int(re.search(r"page size of (\d+) bytes", vm).group(1))
        # Conservative estimate, explicitly excludes compressed/speculative/purgeable pages.
        free = int(re.search(r"Pages free:\s+(\d+)", vm).group(1))
        inactive = int(re.search(r"Pages inactive:\s+(\d+)", vm).group(1))
        swap = _output(("/usr/sbin/sysctl", "vm.swapusage"))
        used, unit = re.search(r"used\s*=\s*([\d.]+)([KMGT])", swap).groups()
        swap_bytes = int(float(used) * 1024 ** ("KMGT".index(unit) + 1))
        rss = footprint = 0
        pids = process_tree_members(pgid, self.known) if pgid else ()
        self.known = set(pids)
        for pid in pids:
            usage = _Rusage()
            if self.libproc.proc_pid_rusage(pid, 4, ctypes.byref(usage)) != 0:
                error = ctypes.get_errno()
                if error == errno.ESRCH or pid not in process_tree_members(pid, set()):
                    continue  # Independently confirmed gone/zombie, including macOS EPERM race.
                raise OSError(ctypes.get_errno(), "cannot sample child memory")
            rss += usage.resident_size
            footprint += usage.phys_footprint
            self.peaks[pid] = max(self.peaks.get(pid, 0), usage.lifetime_max_phys_footprint)
        self.peaks = {pid: peak for pid, peak in self.peaks.items() if pid in pids}
        return ResourceSample(
            time.monotonic(),
            rss,
            footprint,
            sum(self.peaks.values()),
            pressure,
            (free + inactive) * page_size,
            swap_bytes,
            pids,
        )


def _cleanup(process: subprocess.Popen, grace: float, known: set[int]) -> bool:
    def send(sig):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            pass

    def members():
        return process_tree_members(process.pid, known)

    def signal_tree(sig):
        current = members()
        if not current:
            return
        if group_members(process.pid):
            send(sig)
        for pid in current:
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass

    if process.poll() is not None and not members():
        return True
    signal_tree(signal.SIGTERM)
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        process.poll()
        if not members():
            break
        time.sleep(0.02)
    signal_tree(signal.SIGKILL)
    process.wait(timeout=2)
    deadline = time.monotonic() + 2
    while members() and time.monotonic() < deadline:
        time.sleep(0.02)
    return not members()


def run_guarded(
    command: tuple[str, ...],
    *,
    cwd: Path,
    limits: ResourceLimits,
    output: Path,
    collector: Callable[[int | None], ResourceSample] | None = None,
    lock_path: Path | None = None,
) -> RunReceipt:
    if not command:
        raise ValueError("empty command")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Reserve receipt before launch; no replay may overwrite previous evidence.
    receipt_file = output.open("x")
    started = time.monotonic()
    process = None
    state, reason, code = "REFUSED", None, None
    peak_rss = peak_footprint = count = 0
    cleanup_complete = True
    known: set[int] = set()
    commit = _output(("git", "--no-optional-locks", "-C", str(cwd), "rev-parse", "HEAD")).strip()
    diff = _output(("git", "--no-optional-locks", "-C", str(cwd), "diff", "HEAD", "--binary"))
    files = (
        subprocess.check_output(
            ("git", "-C", str(cwd), "ls-files", "--cached", "--others", "--exclude-standard", "-z")
        )
        .decode()
        .split("\0")
    )
    tree_digest = hashlib.sha256()
    for name in sorted(set(files) - {""}):
        path = cwd / name
        tree_digest.update(name.encode() + b"\0")
        if not path.exists():
            tree_digest.update(b"MISSING\0")
            continue
        tree_digest.update(str(path.stat().st_mode & 0o7777).encode() + b"\0")
        with path.open("rb") as source:
            for part in iter(lambda: source.read(1024 * 1024), b""):
                tree_digest.update(part)
        tree_digest.update(b"\0")
    if lock_path is None:
        common = _output(("git", "-C", str(cwd), "rev-parse", "--git-common-dir")).strip()
        lock_path = (cwd / common).resolve() / "novcheck-resource.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with (
        lock_path.open("a") as lock,
        output.with_suffix(".log").open("x") as log,
        output.with_suffix(".samples.jsonl").open("x") as samples,
    ):
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            reason = "ANOTHER_RUN_ACTIVE"
        else:

            def interrupted(signum, frame):
                raise KeyboardInterrupt("termination requested")

            previous_term = signal.signal(signal.SIGTERM, interrupted)
            try:
                collect = collector or MacCollector()
                while True:
                    before = time.monotonic()
                    sample = collect(process.pid if process else None)
                    known = set(sample.pids)
                    count += 1
                    peak_rss = max(peak_rss, sample.rss_bytes)
                    peak_footprint = max(
                        peak_footprint, sample.peak_footprint_bytes, sample.footprint_bytes
                    )
                    samples.write(json.dumps(asdict(sample)) + "\n")
                    samples.flush()
                    reason = stop_reason(sample, limits)
                    if reason is None and time.monotonic() - before > 0.2:
                        reason = "MONITOR_TOO_SLOW"
                    if reason:
                        state = "ABORTED" if process else "REFUSED"
                        break
                    if process is None:
                        # Three stable samples before any actual command launch.
                        if count >= 3:
                            process = subprocess.Popen(
                                command,
                                cwd=cwd,
                                stdout=log,
                                stderr=subprocess.STDOUT,
                                start_new_session=True,
                            )
                    elif process.poll() is not None:
                        code = process.returncode
                        if process_tree_members(process.pid, known):
                            state, reason = "ABORTED", "DESCENDANTS_AFTER_EXIT"
                        else:
                            state = "PASSED" if code == 0 else "FAILED"
                        break
                    if time.monotonic() - started >= limits.timeout_seconds:
                        state, reason = "ABORTED", "TIME_LIMIT"
                        break
                    time.sleep(max(0, limits.sample_seconds - (time.monotonic() - before)))
            except KeyboardInterrupt:
                state, reason = "ABORTED" if process else "REFUSED", "INTERRUPTED"
            except Exception as exc:
                state, reason = "ABORTED" if process else "REFUSED", "MONITOR_FAILURE"
                log.write(type(exc).__name__ + ": " + str(exc) + "\n")
            finally:
                try:
                    if process:
                        cleanup_complete = _cleanup(process, limits.grace_seconds, known)
                        code = process.returncode
                except Exception as exc:
                    cleanup_complete = False
                    log.write("Cleanup failure: " + type(exc).__name__ + "\n")
                finally:
                    signal.signal(signal.SIGTERM, previous_term)
                if not cleanup_complete:
                    state, reason = "ABORTED", "CLEANUP_INCOMPLETE"
    receipt = RunReceipt(
        state,
        reason,
        code,
        time.monotonic() - started,
        peak_rss,
        peak_footprint,
        count,
        hashlib.sha256(json.dumps(command).encode()).hexdigest(),
        commit,
        hashlib.sha256(diff.encode()).hexdigest(),
        tree_digest.hexdigest(),
        cleanup_complete,
        limits,
    )
    with receipt_file:
        json.dump(asdict(receipt), receipt_file, indent=2)
        receipt_file.write("\n")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--soft-bytes", type=int, default=256_000_000)
    parser.add_argument("--hard-bytes", type=int, default=384_000_000)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = tuple(args.command[1:] if args.command[:1] == ["--"] else args.command)
    result = run_guarded(
        command,
        cwd=Path.cwd(),
        limits=ResourceLimits(
            soft_bytes=args.soft_bytes, hard_bytes=args.hard_bytes, timeout_seconds=args.timeout
        ),
        output=args.output,
    )
    print(json.dumps(asdict(result), indent=2))
    return 0 if result.state == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
