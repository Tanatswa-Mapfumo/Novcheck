"""Structured pytest child for the guarded local runner; never a safety bypass.

Run only through resource_guard. Captures real collection and all three pytest
phases, including partial output if the supervisor terminates this process.
"""

import hashlib
import importlib.metadata
import json
import os
import sys
import time
from pathlib import Path


class EvidencePlugin:
    def __init__(self, path):
        self.stream = path.open("x", encoding="utf-8")
        self.started = time.perf_counter()
        self.deselected = []
        self.subtest_count = 0

    def emit(self, kind, **fields):
        self.stream.write(json.dumps({"kind": kind, **fields}, ensure_ascii=False) + "\n")
        self.stream.flush()

    def pytest_configure(self, config):
        if (
            os.environ.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD") != "1"
            or config.option.markexpr != "not network"
            or not getattr(config.option, "disable_socket", False)
            or not getattr(config.option, "allow_unix_socket", False)
            or getattr(config.option, "force_enable_socket", False)
            or getattr(config.option, "allow_hosts", None)
        ):
            raise ValueError("required pytest socket/marker/plugin policy mismatch")
        environment = {
            "python": sys.version,
            "executable": str(Path(sys.executable).resolve()),
            "invoked_executable": str(Path(sys.executable).absolute()),
            "packages": sorted(
                (distribution.metadata["Name"], distribution.version)
                for distribution in importlib.metadata.distributions()
            ),
        }
        self.emit(
            "configured",
            environment=environment,
            plugin_policy="explicit-socket-asyncio-v1",
            marker_policy="not network",
        )

    def pytest_deselected(self, items):
        self.deselected.extend(
            {"nodeid": item.nodeid, "network": item.get_closest_marker("network") is not None}
            for item in items
        )

    def pytest_collection_finish(self, session):
        self.emit(
            "collection",
            nodes=[item.nodeid for item in session.items],
            deselected=self.deselected,
            import_collection_seconds=time.perf_counter() - self.started,
        )

    def pytest_collectreport(self, report):
        if report.failed or report.skipped:
            self.emit("collection_nonpass", nodeid=report.nodeid, outcome=report.outcome)

    def pytest_runtest_logreport(self, report):
        outcome = "xfailed" if hasattr(report, "wasxfail") else report.outcome
        if hasattr(report, "context"):
            self.subtest_count += 1
            # Record identity only: parameter values can contain evidence prose.
            context = report.context
            identity = hashlib.sha256(
                json.dumps(
                    [context.msg, dict(context.kwargs)], sort_keys=True, default=repr
                ).encode()
            ).hexdigest()
            self.emit(
                "subtest",
                nodeid=report.nodeid,
                outcome=outcome,
                duration=report.duration,
                identity=identity,
            )
            return
        self.emit(
            "phase",
            nodeid=report.nodeid,
            when=report.when,
            outcome=outcome,
            duration=report.duration,
        )

    def pytest_sessionfinish(self, session, exitstatus):
        self.emit(
            "session_finish",
            exitstatus=int(exitstatus),
            subtest_count=self.subtest_count,
            elapsed_seconds=time.perf_counter() - self.started,
        )
        os.fsync(self.stream.fileno())

    def close(self):
        self.stream.close()


def main():
    # Arguments are serialized data, not historical commands or shell input.
    job_path = Path(sys.argv[1])
    job_bytes = job_path.read_bytes()
    job = json.loads(job_bytes)
    if set(job) != {"nodes", "collect_only", "events_path"}:
        raise ValueError("unexpected pytest job fields")
    nodes = job["nodes"]
    if (
        not isinstance(nodes, list)
        or not nodes
        or any(not isinstance(node, str) or not node.startswith("tests/") for node in nodes)
        or len(set(nodes)) != len(nodes)
        or type(job["collect_only"]) is not bool
    ):
        raise ValueError("invalid exact pytest node inventory")
    for key in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTHONPATH"):
        if os.environ.get(key):
            raise ValueError("ambient pytest configuration is not permitted")
    plugin = EvidencePlugin(Path(job["events_path"]))
    plugin.emit("job", sha256=hashlib.sha256(job_bytes).hexdigest())
    try:
        import pytest

        arguments = ["-p", "pytest_socket", "-p", "pytest_asyncio.plugin", "-q"]
        if job["collect_only"]:
            arguments.append("--collect-only")
        return int(pytest.main([*arguments, *nodes], plugins=[plugin]))
    finally:
        plugin.close()


if __name__ == "__main__":
    raise SystemExit(main())
