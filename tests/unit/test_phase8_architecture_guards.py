"""Phase 8 capability boundaries, including malicious import/call variants."""

import inspect
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2] / "src/novelty_harness"


@pytest.mark.parametrize(
    "source",
    [
        "from ..research import planning",
        "from novelty_harness import providers",
        "import httpx as transport",
        "from tests.fixtures.phase8 import make_report_case",
        "from novelty_harness.domain.adjudication import FrozenAdjudication",
        "import importlib as loader\nloader.import_module('novelty_harness.research')",
        "from importlib import import_module as load\nload('tests.fixtures.phase8')",
        "__import__('novelty_harness.providers')",
        "repo.freeze_phase7_adjudication(run, result)",
        "repo.record_phase6_assessment(run, result)",
        "client.search(query)",
        "repo.exec_driver_sql('DELETE FROM sources')",
    ],
)
def test_guard_detects_relative_dynamic_and_reexported_capability_leak(source):
    from tests.fixtures.phase8_boundaries import reporting_violations

    assert reporting_violations(source, "novelty_harness.reporting")


def test_guard_follows_reexported_capability_and_dynamic_assignment():
    from tests.fixtures.phase8_boundaries import reporting_violations

    modules = {"novelty_harness.shared": "from novelty_harness.research import planning"}
    assert reporting_violations(
        "from novelty_harness.shared import planning", "novelty_harness.reporting", modules=modules
    )
    assert reporting_violations(
        "import importlib\nload = importlib.import_module\nload('tests.fixtures.phase8')",
        "novelty_harness.reporting",
    )
    assert reporting_violations(
        "import importlib\nimportlib.import_module(chosen)", "novelty_harness.reporting"
    )


def test_phase8_has_no_search_research_or_upstream_write_capability():
    from tests.fixtures.phase8_boundaries import reporting_violations

    paths = [p for p in (ROOT / "reporting").glob("*.py") if p.name != "minimal.py"]
    paths += list((ROOT / "application").glob("phase8*.py"))
    for path in paths:
        package = "novelty_harness." + ".".join(path.relative_to(ROOT).parent.parts)
        assert not reporting_violations(
            path.read_text(), package, pure=path.parent.name == "reporting"
        ), path


def test_real_report_cannot_import_fixture_authority():
    from tests.fixtures.phase8_boundaries import reporting_violations

    for path in (ROOT / "application").glob("phase8*.py"):
        assert not reporting_violations(path.read_text(), "novelty_harness.application"), path
    from novelty_harness.ports import reporting

    for protocol in (
        reporting.ReportPlannerPort,
        reporting.SectionWriterPort,
        reporting.ReportClaimExtractorPort,
        reporting.ReportClaimVerifierPort,
    ):
        for name, member in vars(protocol).items():
            if name.startswith("_") or not inspect.isfunction(member):
                continue
            assert not {"repository", "browser", "search", "retrieval"} & set(
                inspect.signature(member).parameters
            )


@pytest.mark.parametrize(
    "source",
    [
        "class Proposal:\n    novelty_score: float",
        "class Proposal:\n    probability: float",
        "fields = {'confidence': 0.9}",
        "from novelty_harness.application.phase8 import compile_assessment_report",
        "from novelty_harness.runtime.semantic import structured",
        "from sqlalchemy import Session",
    ],
)
def test_numeric_novelty_fields_or_tests_imports_are_banned(source):
    from tests.fixtures.phase8_boundaries import reporting_violations

    assert reporting_violations(source, "novelty_harness.reporting", pure=True)


def test_guard_allows_exact_read_contracts_hashing_and_safe_renderer_yaml():
    from tests.fixtures.phase8_boundaries import reporting_violations

    assert not reporting_violations(
        "from novelty_harness.runtime.tracing.hashing import canonical_hash\n"
        "from novelty_harness.evidence.graph.assessment_view import Phase6AssessmentView\n"
        "from novelty_harness.adjudication.frozen import FrozenAdjudication\n"
        "import yaml\nyaml.safe_load(text)",
        "novelty_harness.reporting",
        pure=True,
    )


@pytest.mark.parametrize(
    "source",
    [
        "import importlib; importlib.import_module('.research', 'novelty_harness')",
        "from importlib import import_module as load; load('.research', package='novelty_harness')",
    ],
)
def test_guard_resolves_dynamic_relative_capability_import(source):
    from tests.fixtures.phase8_boundaries import reporting_violations

    assert reporting_violations(source, "novelty_harness.reporting")
