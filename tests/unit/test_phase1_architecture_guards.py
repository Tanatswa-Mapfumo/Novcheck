import ast
import inspect
from pathlib import Path
from typing import get_origin

import pytest

from novelty_harness.domain.adjudication import FrozenAdjudication, MCUFinding
from novelty_harness.domain.idea import ArtifactProvenance, ClaimedAdvantage
from novelty_harness.domain.research import CoverageEntry
from novelty_harness.reporting.minimal import compile_minimal_report
from tests.unit.test_import_boundaries import FORBIDDEN, forbidden_imports

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
    # Approved Phase 6/7 summaries consume only typed domain/evidence read
    # contracts and repository ports; application services remain forbidden.
    phase_read_contracts = {
        "novelty_harness.adjudication.repository",
        "novelty_harness.evidence.graph.assessment_view",
        "novelty_harness.evidence.graph.models",
        "novelty_harness.evidence.graph.repository",
    }
    report_read_contracts = {
        "bundle.py": {
            "novelty_harness.adjudication.context",
            "novelty_harness.adjudication.counterfactual",
            "novelty_harness.adjudication.frozen",
            "novelty_harness.adjudication.gates",
            "novelty_harness.adjudication.judge",
            "novelty_harness.adjudication.models",
            "novelty_harness.adjudication.needs",
            "novelty_harness.adjudication.qualifications",
            "novelty_harness.adjudication.roles",
            "novelty_harness.evidence.graph.assessment_view",
            "novelty_harness.evidence.mapping.dimensions",
            "novelty_harness.evidence.normalization.models",
            "novelty_harness.mcu.overrides",
        },
        "obligations.py": {
            "novelty_harness.adjudication.models",
            "novelty_harness.adjudication.roles",
        },
        "fallback.py": {
            "novelty_harness.adjudication.roles",
            "novelty_harness.evidence.passages.models",
        },
        "ir.py": {
            "novelty_harness.adjudication.frozen",
            "novelty_harness.adjudication.models",
            "novelty_harness.evidence.graph.assessment_ledger",
        },
        "citations.py": {
            "novelty_harness.evidence.normalization.models",
            "novelty_harness.evidence.passages.models",
        },
        "firewall.py": {"novelty_harness.adjudication.frozen"},
        "verification.py": {"novelty_harness.adjudication.frozen"},
        "wording.py": {
            "novelty_harness.adjudication.frozen",
            "novelty_harness.adjudication.models",
        },
        "claims.py": {
            "novelty_harness.adjudication.frozen",
            "novelty_harness.adjudication.models",
        },
        "drafts.py": {
            "novelty_harness.adjudication.counterfactual",
            "novelty_harness.adjudication.frozen",
            "novelty_harness.adjudication.judge",
            "novelty_harness.adjudication.needs",
            "novelty_harness.adjudication.roles",
            "novelty_harness.evidence.graph.assessment_ledger",
            "novelty_harness.evidence.graph.assessment_view",
            "novelty_harness.evidence.mapping.dimensions",
            "novelty_harness.evidence.provenance.models",
            "novelty_harness.mcu.overrides",
        },
        "plan.py": {
            "novelty_harness.adjudication.frozen",
            "novelty_harness.adjudication.models",
            "novelty_harness.evidence.graph.assessment_view",
            "novelty_harness.evidence.mapping.dimensions",
            "novelty_harness.mcu.overrides",
        },
        "value.py": {"novelty_harness.adjudication.models"},
        "uncertainty.py": {
            "novelty_harness.adjudication.models",
            "novelty_harness.adjudication.roles",
        },
    }
    for path in (ROOT / "src/novelty_harness/reporting").rglob("*.py"):
        source = path.read_text()
        # The one runtime import is pure canonical serialization, never execution.
        violations = forbidden_imports(source, "novelty_harness.reporting")
        assert not [
            v
            for v in violations
            if v != "novelty_harness.runtime.tracing.hashing"
            and not v.startswith("novelty_harness.runtime.tracing.hashing.")
        ]
        assert not forbidden_imports(
            source,
            "novelty_harness.reporting",
            banned=tuple(prefix for prefix in FORBIDDEN if prefix != "novelty_harness.runtime"),
        )
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                imported = (
                    [alias.name for alias in node.names]
                    if isinstance(node, ast.Import)
                    else [node.module or ""]
                )
                if any(name == "yaml" or name.startswith("yaml.") for name in imported):
                    assert path.name == "rendering.py", path
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith("novelty_harness")
            ):
                assert (
                    node.module.startswith("novelty_harness.domain.")
                    or node.module.startswith("novelty_harness.reporting.")
                    or (path.name == "minimal.py" and node.module in phase_read_contracts)
                    or (
                        path.name
                        in {
                            "models.py",
                            "artifacts.py",
                            "execution.py",
                            "bundle.py",
                            "obligations.py",
                            "uncertainty.py",
                            "plan.py",
                            "drafts.py",
                            "claims.py",
                            "firewall.py",
                            "verification.py",
                            "recommendations.py",
                            "fallback.py",
                            "repair.py",
                            "citations.py",
                            "ir.py",
                            "rendering.py",
                        }
                        and node.module == "novelty_harness.runtime.tracing.hashing"
                    )
                    or (
                        path.name == "models.py"
                        and node.module == "novelty_harness.adjudication.models"
                    )
                    or node.module in report_read_contracts.get(path.name, set())
                ), (path, node.module)


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
                    if path.name == "_base.py" and path.parent.name == "providers":
                        assert methods & operations == {"search"}
                        continue
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


def test_yaml_serialization_is_confined_to_report_renderer():
    renderer = ROOT / "src/novelty_harness/reporting/rendering.py"
    for path in (ROOT / "src").rglob("*.py"):
        package = ".".join(path.relative_to(ROOT / "src").parent.parts)
        violations = forbidden_imports(path.read_text(), package, banned=("yaml",))
        assert path == renderer or not violations, (path, violations)
