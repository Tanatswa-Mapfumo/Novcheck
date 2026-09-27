import ast
import inspect
from pathlib import Path
from typing import get_origin

import pytest

from novelty_harness.domain.adjudication import FrozenAdjudication, MCUFinding
from novelty_harness.domain.idea import ArtifactProvenance, ClaimedAdvantage
from novelty_harness.domain.research import CoverageEntry
from novelty_harness.reporting.minimal import compile_minimal_report
from tests.unit.test_import_boundaries import forbidden_imports

ROOT = Path(__file__).resolve().parents[2]
NETWORK_IMPORTS = (
    "tests",
    "httpx",
    "requests",
    "aiohttp",
    "openai",
    "anthropic",
    "google",
    "socket",
    "urllib.request",
    "http.client",
)


def test_reporting_has_only_domain_and_standard_library_dependencies():
    for path in (ROOT / "src/novelty_harness/reporting").rglob("*.py"):
        source = path.read_text()
        assert not forbidden_imports(source, "novelty_harness.reporting")
        for node in ast.walk(ast.parse(source)):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith("novelty_harness")
            ):
                assert node.module.startswith("novelty_harness.domain.")


def test_production_has_no_test_imports_or_concrete_network_provider_dependencies():
    for path in (ROOT / "src").rglob("*.py"):
        package = ".".join(path.relative_to(ROOT / "src").parent.parts)
        permitted_http = path.parent == ROOT / "src/novelty_harness/providers"
        banned = tuple(i for i in NETWORK_IMPORTS if not (permitted_http and i == "httpx"))
        assert not forbidden_imports(path.read_text(), package, banned=banned), path


def test_no_concrete_provider_implementations_were_added():
    operations = {"search", "generate_structured", "embed", "rank", "resolve", "resolve_passage"}
    for path in (ROOT / "src").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ClassDef):
                methods = {
                    child.name for child in node.body if isinstance(child, ast.AsyncFunctionDef)
                }
                if methods & operations:
                    assert any(
                        isinstance(base, ast.Name) and base.id == "Protocol" for base in node.bases
                    ), path


def test_no_numeric_novelty_or_confidence_fields_or_thresholds_added():
    banned = {
        "novelty_score",
        "confidence_score",
        "confidence",
        "novelty_probability",
        "overall_novelty_score",
        "strong_novelty_threshold",
        "saturation_threshold",
    }
    for path in (ROOT / "src").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Name):
                assert node.id not in banned, path
            elif isinstance(node, ast.Attribute):
                assert node.attr not in banned, path
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert node.value not in banned, path


def test_report_compiler_api_accepts_frozen_findings_not_services():
    assert set(inspect.signature(compile_minimal_report).parameters) == {
        "idea",
        "sufficiency",
        "mcus",
        "edges",
        "adjudication",
    }
    source = inspect.getsource(compile_minimal_report)
    assert "adjudicate(" not in source
    assert "generate_structured(" not in source
    assert "search(" not in source


@pytest.mark.parametrize(
    "model", [FrozenAdjudication, MCUFinding, ArtifactProvenance, ClaimedAdvantage, CoverageEntry]
)
def test_every_nested_findings_contract_is_frozen_without_mutable_collections(model):
    assert model.model_config["frozen"] is True
    for field in model.model_fields.values():
        assert get_origin(field.annotation) not in {list, dict, set}


def test_default_suite_is_network_blocked_without_host_allowances(pytestconfig):
    assert pytestconfig.getoption("disable_socket") is True
    assert not pytestconfig.getoption("allow_hosts")
