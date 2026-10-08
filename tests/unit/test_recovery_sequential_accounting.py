"""Prepared runner controls: process exit 0 is not complete test coverage."""

import pytest


def account(expected, reports, *, state="PASSED", returncode=0):
    from scripts.recovery.sequential import account_batch

    return account_batch(expected, reports, child_state=state, returncode=returncode)


def phases(node, *, call="passed"):
    return [
        {"nodeid": node, "when": stage, "outcome": call if stage == "call" else "passed",
         "duration": 0.1}
        for stage in ("setup", "call", "teardown")
    ]


def test_exact_inventory_handles_unicode_and_parameterized_ids():
    nodes = ["tests/unit/x.py::test_case[α β]", "tests/unit/x.py::test_case[other]"]
    result = account(nodes, [report for node in nodes for report in phases(node)])
    assert result["state"] == "PASSED"
    assert result["passed"] == nodes
    assert result["setup_seconds"] == pytest.approx(0.2)
    assert result["execution_seconds"] == pytest.approx(0.2)
    assert result["teardown_seconds"] == pytest.approx(0.2)


@pytest.mark.parametrize("attack", ["missing", "extra", "duplicate", "missing_teardown"])
def test_zero_child_exit_cannot_hide_incomplete_or_wrong_inventory(attack):
    expected = ["tests/x.py::test_a", "tests/x.py::test_b"]
    reports = phases(expected[0]) + phases(expected[1])
    if attack == "missing":
        reports = phases(expected[0])
    elif attack == "extra":
        reports += phases("tests/x.py::test_unrequested")
    elif attack == "duplicate":
        reports += [dict(reports[0])]
    else:
        reports = reports[:-1]
    assert account(expected, reports)["state"] != "PASSED"


@pytest.mark.parametrize("state,code", [("REFUSED", None), ("ABORTED", -15),
                                        ("FAILED", 1), ("PASSED", 7)])
def test_partial_reports_never_override_guard_or_process_failure(state, code):
    node = "tests/x.py::test_a"
    result = account([node], phases(node), state=state, returncode=code)
    assert result["state"] != "PASSED"


@pytest.mark.parametrize("outcome", ["skipped", "failed", "xfailed"])
def test_required_nonpass_is_not_counted_as_complete_verification(outcome):
    node = "tests/x.py::test_a"
    result = account([node], phases(node, call=outcome))
    assert result["state"] != "PASSED"
    assert result["passed"] == []


def test_duplicate_expected_nodes_are_rejected():
    node = "tests/x.py::test_a"
    with pytest.raises(ValueError):
        account([node, node], phases(node))


def test_resume_requires_exact_source_inventory_and_complete_receipt():
    from scripts.recovery.sequential import eligible_resume

    node = "tests/x.py::test_a"
    receipt = {
        "source_identity": "a" * 64, "expected_nodes": [node], "state": "PASSED",
        "cleanup_complete": True, "required_gates": {"guard": "PASSED"},
    }
    assert eligible_resume(receipt, source_identity="a" * 64, expected_nodes=[node])
    assert not eligible_resume(receipt, source_identity="b" * 64, expected_nodes=[node])
    assert not eligible_resume(receipt, source_identity="a" * 64,
                               expected_nodes=[node, "tests/x.py::test_b"])
    for patch in ({"state": "ABORTED"}, {"cleanup_complete": False},
                  {"required_gates": {"guard": "REFUSED"}}):
        assert not eligible_resume(receipt | patch, source_identity="a" * 64,
                                   expected_nodes=[node])
