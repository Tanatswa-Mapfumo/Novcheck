"""Exact batch accounting. Metadata eligibility alone never authorizes resume.

No tests are dispatched here; execution must use the native resource supervisor.
Independent durable evidence checks are required in addition to these predicates.
"""

import math
from collections import Counter


def account_batch(expected, reports, *, child_state, returncode):
    if not expected or any(not isinstance(node, str) or not node for node in expected):
        raise ValueError("nonempty exact test inventory required")
    if len(set(expected)) != len(expected):
        raise ValueError("duplicate expected node")
    totals = {"setup": 0.0, "call": 0.0, "teardown": 0.0}
    counts = Counter()
    by_node = {node: [] for node in expected}
    invalid = []
    for report in reports:
        if set(report) != {"nodeid", "when", "outcome", "duration"}:
            invalid.append("REPORT_SCHEMA")
            continue
        node, phase = report["nodeid"], report["when"]
        duration = report["duration"]
        if (
            node not in by_node
            or phase not in totals
            or type(duration) not in (int, float)
            or not math.isfinite(duration)
            or duration < 0
            or report["outcome"] not in {"passed", "failed", "skipped", "xfailed"}
        ):
            invalid.append("INVALID_REPORT")
            continue
        counts[node, phase] += 1
        totals[phase] += duration
        by_node[node].append(report)
    passed = []
    for node in expected:
        events = by_node[node]
        if (
            [event["when"] for event in events] == ["setup", "call", "teardown"]
            and all(counts[node, phase] == 1 for phase in totals)
            and all(event["outcome"] == "passed" for event in events)
        ):
            passed.append(node)
    safe = child_state == "PASSED" and type(returncode) is int and returncode == 0
    complete = safe and not invalid and passed == expected
    return {
        "state": "PASSED" if complete else "INCOMPLETE",
        "passed": passed if safe and not invalid else [],
        "expected_nodes": list(expected),
        "setup_seconds": totals["setup"],
        "execution_seconds": totals["call"],
        "teardown_seconds": totals["teardown"],
        "invalid_reasons": invalid,
        "child_state": child_state,
        "returncode": returncode,
    }


def eligible_resume(receipt, *, source_identity, expected_nodes):
    """Metadata prefilter only. A True result is NOT permission to skip a test.

    The runner must separately authenticate immutable guard, collection, pytest,
    output and sample bytes and recompute complete accounting before reuse.
    """
    return (
        receipt.get("source_identity") == source_identity
        and receipt.get("expected_nodes") == expected_nodes
        and bool(expected_nodes)
        and len(set(expected_nodes)) == len(expected_nodes)
        and receipt.get("state") == "PASSED"
        and receipt.get("cleanup_complete") is True
        and receipt.get("required_gates") == {"guard": "PASSED"}
    )
