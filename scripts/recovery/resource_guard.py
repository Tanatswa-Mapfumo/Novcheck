"""Sequential timeout supervisor; does not import the application.

Execution policy v3 imposes no memory limits or memory preflight. Versions 1/2
remain replay-only definitions for historical receipts; execution always uses v3.
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
from dataclasses import asdict, dataclass, replace
from pathlib import Path


@dataclass(frozen=True)
class ResourceLimits:
    soft_bytes: int = 1_500_000_000
    hard_bytes: int = 2_000_000_000
    min_headroom_bytes: int = 1_500_000_000
    # Zero preserves the original identical launch/runtime floor. An explicit
    # calibrated recipe can reserve more before dispatch than during execution.
    launch_headroom_bytes: int = 0
    max_swap_bytes: int = 2_000_000_000
    sample_seconds: float = 0.1
    timeout_seconds: float = 60
    grace_seconds: float = 0.5
    # Versions 1/2 are retained solely for interpreting historical receipts.
    policy_version: int = 3
    allow_warning: bool = False
    max_paging_bytes_per_second: int = 16_000_000
    paging_window_seconds: float = 3.0

    def __post_init__(self):
        if self.policy_version == 3:
            if not all(
                math.isfinite(value) and value > 0
                for value in (self.sample_seconds, self.timeout_seconds, self.grace_seconds)
            ):
                raise ValueError("poll interval, timeout and grace must be finite and positive")
            # Compatibility arguments cannot restore a memory restriction.
            for name in (
                "soft_bytes",
                "hard_bytes",
                "min_headroom_bytes",
                "launch_headroom_bytes",
                "max_swap_bytes",
                "max_paging_bytes_per_second",
                "paging_window_seconds",
            ):
                object.__setattr__(self, name, 0)
            object.__setattr__(self, "allow_warning", True)
            return
        if not all(math.isfinite(value) for value in asdict(self).values()):
            raise ValueError("limits must be finite")
        if not 0 < self.soft_bytes <= self.hard_bytes <= 3_000_000_000:
            raise ValueError("memory limits must be positive and at most 3 GB")
        if not 0 < self.sample_seconds <= 0.2:
            raise ValueError("sample cadence must be at most 0.2 seconds")
        if min(self.min_headroom_bytes, self.timeout_seconds, self.grace_seconds) <= 0:
            raise ValueError("headroom, timeout and grace must be positive")
        if self.launch_headroom_bytes < 0:
            raise ValueError("launch headroom cannot be negative")
        if self.max_swap_bytes < 0:
            raise ValueError("swap limit cannot be negative")
        if self.policy_version not in (1, 2) or type(self.allow_warning) is not bool:
            raise ValueError("invalid risk policy")
        if self.max_paging_bytes_per_second <= 0 or self.paging_window_seconds < 1:
            raise ValueError("paging policy requires a positive rate and one-second window")
        # Medium warning execution is calibrated only after a measured small
        # attempt; require extra native headroom while retaining runtime stops.
        warning_headroom = (
            1_500_000_000
            if self.soft_bytes > 256_000_000 or self.hard_bytes > 384_000_000
            else 1_000_000_000
        )
        calibrated_small_report = (
            self.launch_headroom_bytes >= 1_400_000_000
            and self.soft_bytes <= 320_000_000
            and self.hard_bytes <= 448_000_000
            and (self.soft_bytes > 256_000_000 or self.hard_bytes > 384_000_000)
        )
        calibrated_ir = self.launch_headroom_bytes >= 1_500_000_000
        calibrated_validation = (
            self.launch_headroom_bytes >= 1_700_000_000 and self.soft_bytes > 640_000_000
        )
        warning_soft = (
            704_000_000 if calibrated_validation else 640_000_000 if calibrated_ir else 384_000_000
        )
        warning_hard = 896_000_000 if calibrated_ir else 512_000_000
        if calibrated_validation:
            # Measured complete report validation reached 650 MB. Retain the
            # existing hard ceiling and require extra launch/runtime reserves.
            warning_headroom = 1_100_000_000
        elif calibrated_ir:
            warning_headroom = 1_000_000_000
        elif calibrated_small_report:
            # Measured smaller native report load: narrower caps, explicit
            # launch reserve, and more runtime reserve than the IR profile.
            warning_headroom = 1_100_000_000
        if self.allow_warning and (
            self.policy_version != 2
            or self.soft_bytes > warning_soft
            or self.hard_bytes > warning_hard
            or self.min_headroom_bytes < warning_headroom
        ):
            raise ValueError("warning-pressure execution exceeds bounded profile or headroom")


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
    pageins_bytes: int | None = None
    pageouts_bytes: int | None = None
    swapins_bytes: int | None = None
    swapouts_bytes: int | None = None


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
    if limits.policy_version == 3:
        return None
    peak = max(sample.rss_bytes, sample.footprint_bytes, sample.peak_footprint_bytes)
    if peak >= limits.hard_bytes:
        return "HARD_MEMORY_LIMIT"
    if peak >= limits.soft_bytes:
        return "SOFT_MEMORY_LIMIT"
    if sample.pressure != 1 and not (
        limits.policy_version == 2 and limits.allow_warning and sample.pressure == 2
    ):
        return "MEMORY_PRESSURE_UNKNOWN" if sample.pressure is None else "MEMORY_PRESSURE"
    if sample.headroom_bytes is None or sample.swap_bytes is None:
        return "UNKNOWN_SYSTEM_MEMORY"
    if sample.headroom_bytes < limits.min_headroom_bytes:
        return "LOW_HEADROOM"
    if limits.policy_version == 1 and sample.swap_bytes > limits.max_swap_bytes:
        return "SWAP_LIMIT"
    return None


class RiskMonitor:
    """Replayable capacity/paging decisions; allocated swap is not a v2 veto.

    Output paging includes page-outs and swap-outs conservatively. A three-second
    rolling window avoids treating a single counter burst as sustained thrashing.
    Critical/unknown pressure, unreadable counters and low headroom stop at once.
    """

    def __init__(self, limits: ResourceLimits):
        self.limits = limits
        self.history: list[ResourceSample] = []
        self.started: float | None = None

    def ready(self, sample: ResourceSample) -> bool:
        return self.limits.policy_version in (1, 3) or (
            self.started is not None
            and sample.monotonic_seconds - self.started >= self.limits.paging_window_seconds
        )

    def check(self, sample: ResourceSample) -> str | None:
        reason = stop_reason(sample, self.limits)
        if reason or self.limits.policy_version in (1, 3):
            return reason
        counters = ("pageins_bytes", "pageouts_bytes", "swapins_bytes", "swapouts_bytes")
        if any(
            type(getattr(sample, key)) is not int or getattr(sample, key) < 0 for key in counters
        ):
            return "PAGING_UNKNOWN"
        if self.started is None:
            self.started = sample.monotonic_seconds
        if self.history:
            previous = self.history[-1]
            if sample.monotonic_seconds <= previous.monotonic_seconds or any(
                getattr(sample, key) < getattr(previous, key) for key in counters
            ):
                return "PAGING_COUNTER_INVALID"
        self.history.append(sample)
        window = self.limits.paging_window_seconds
        while len(self.history) > 2 and (
            sample.monotonic_seconds - self.history[1].monotonic_seconds >= window
        ):
            self.history.pop(0)
        first = self.history[0]
        elapsed = sample.monotonic_seconds - first.monotonic_seconds
        if elapsed >= window:
            output_rate = (
                sample.pageouts_bytes
                - first.pageouts_bytes
                + sample.swapouts_bytes
                - first.swapouts_bytes
            ) / elapsed
            input_rate = (sample.swapins_bytes - first.swapins_bytes) / elapsed
            swap_growth = max(0, sample.swap_bytes - first.swap_bytes) / elapsed
            paging_rate = max(output_rate, swap_growth)
            # Moderate background paging is only dangerous with shrinking
            # capacity or growing children; severe paging remains an absolute stop.
            headroom_loss = first.headroom_bytes - sample.headroom_bytes
            process_growth = max(sample.rss_bytes, sample.footprint_bytes) - max(
                first.rss_bytes, first.footprint_bytes
            )
            capacity_risk = (
                sample.headroom_bytes < self.limits.min_headroom_bytes + self.limits.soft_bytes
                or headroom_loss >= 128_000_000
                or (
                    process_growth >= 64_000_000
                    and max(sample.rss_bytes, sample.footprint_bytes)
                    >= 0.75 * self.limits.soft_bytes
                )
            )
            if paging_rate >= 4 * self.limits.max_paging_bytes_per_second or (
                paging_rate >= self.limits.max_paging_bytes_per_second and capacity_risk
            ):
                return "SUSTAINED_PAGING"
            if input_rate >= 16 * self.limits.max_paging_bytes_per_second or (
                input_rate >= 4 * self.limits.max_paging_bytes_per_second and capacity_risk
            ):
                return "SUSTAINED_SWAPINS"
        return None


def execution_limits(limits: ResourceLimits) -> ResourceLimits:
    """Preserve lifecycle options; force unrestricted memory policy for every run."""
    return replace(limits, policy_version=3)


def approved_local_limits(limits: ResourceLimits) -> bool:
    if limits.policy_version == 3:
        return True
    headroom = (
        1_000_000_000
        if limits.policy_version == 2
        and limits.allow_warning
        and (
            (limits.soft_bytes <= 256_000_000 and limits.hard_bytes <= 384_000_000)
            or (
                limits.launch_headroom_bytes >= 1_500_000_000
                and limits.soft_bytes <= 640_000_000
                and limits.hard_bytes <= 896_000_000
            )
        )
        else 1_500_000_000
    )
    if (
        limits.policy_version == 2
        and limits.allow_warning
        and 1_400_000_000 <= limits.launch_headroom_bytes < 1_500_000_000
        and limits.soft_bytes <= 320_000_000
        and limits.hard_bytes <= 448_000_000
        and (limits.soft_bytes > 256_000_000 or limits.hard_bytes > 384_000_000)
    ):
        headroom = 1_100_000_000
    if (
        limits.policy_version == 2
        and limits.allow_warning
        and limits.launch_headroom_bytes >= 1_700_000_000
        and 640_000_000 < limits.soft_bytes <= 704_000_000
        and limits.hard_bytes <= 896_000_000
    ):
        headroom = 1_100_000_000
    return (
        limits.soft_bytes <= 1_500_000_000
        and limits.hard_bytes <= 2_000_000_000
        and limits.min_headroom_bytes >= headroom
        and limits.sample_seconds <= 0.1
        and (limits.policy_version == 2 or limits.max_swap_bytes <= 2_000_000_000)
        and limits.max_paging_bytes_per_second <= 16_000_000
        and limits.paging_window_seconds == 3.0
    )


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
            *(
                int(re.search(rf"{name}:\s+(\d+)", vm).group(1)) * page_size
                for name in ("Pageins", "Pageouts", "Swapins", "Swapouts")
            ),
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
    limits = execution_limits(limits)
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
                # Launch immediately under the global lock. macOS manages RAM/swap.
                # Memory observers are optional diagnostics, never execution gates.
                process = subprocess.Popen(
                    command,
                    cwd=cwd,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                collect = collector
                while True:
                    before = time.monotonic()
                    known.update(process_tree_members(process.pid, known))
                    if collect is not None:
                        try:
                            sample = collect(process.pid)
                        except Exception as exc:
                            log.write(
                                "Optional memory observation unavailable: "
                                + type(exc).__name__
                                + "\n"
                            )
                            collect = None
                        else:
                            count += 1
                            peak_rss = max(peak_rss, sample.rss_bytes)
                            peak_footprint = max(
                                peak_footprint,
                                sample.peak_footprint_bytes,
                                sample.footprint_bytes,
                            )
                            samples.write(json.dumps(asdict(sample)) + "\n")
                            samples.flush()
                    if process.poll() is not None:
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
    parser.add_argument("--soft-bytes", type=int, default=0, help="Deprecated; ignored")
    parser.add_argument("--hard-bytes", type=int, default=0, help="Deprecated; ignored")
    parser.add_argument("--timeout", type=float, default=60)
    profile = parser.add_mutually_exclusive_group()
    profile.add_argument("--small-workload", action="store_true")
    profile.add_argument(
        "--qualified-medium",
        action="store_true",
        help="Deprecated compatibility flag; memory is unrestricted",
    )
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = tuple(args.command[1:] if args.command[:1] == ["--"] else args.command)
    result = run_guarded(
        command,
        cwd=Path.cwd(),
        limits=ResourceLimits(
            soft_bytes=args.soft_bytes,
            hard_bytes=args.hard_bytes,
            timeout_seconds=args.timeout,
            policy_version=3,
            allow_warning=args.small_workload or args.qualified_medium,
        ),
        output=args.output,
    )
    print(json.dumps(asdict(result), indent=2))
    return 0 if result.state == "PASSED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
