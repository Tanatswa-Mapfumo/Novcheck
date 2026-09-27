import inspect
from pathlib import Path

from novelty_harness.research.applicability import EvidenceFamilyApplicabilityAssessor
from novelty_harness.research.coverage import CoverageState
from tests.unit.test_import_boundaries import forbidden_imports

ROOT = Path(__file__).parents[2]


def test_semantic_planning_and_domain_do_not_import_concrete_providers():
    for path in (ROOT / "src/novelty_harness/domain").rglob("*.py"):
        assert not forbidden_imports(
            path.read_text(),
            "novelty_harness.domain",
            banned=("novelty_harness.providers", "httpx"),
        ), path
    for name in (
        "applicability",
        "planning",
        "critique",
        "revision",
        "models",
        "coverage",
        "provider_queries",
    ):
        path = ROOT / f"src/novelty_harness/research/{name}.py"
        assert not forbidden_imports(
            path.read_text(),
            "novelty_harness.research",
            banned=("novelty_harness.providers", "httpx", "tests"),
        ), path


def test_applicability_has_no_provider_availability_input_and_no_saturation_state():
    assert set(inspect.signature(EvidenceFamilyApplicabilityAssessor.assess).parameters) == {
        "self",
        "idea",
        "mcus",
    }
    assert "SATURATED" not in CoverageState.__members__


def test_phase3_modules_stay_separate_from_later_engines_and_vendor_sdks():
    root = ROOT / "src/novelty_harness"
    for path in root.rglob("*.py"):
        assert not forbidden_imports(
            path.read_text(), "novelty_harness", banned=("openai", "anthropic", "tests")
        ), path
    for path in (root / "research").glob("*.py"):
        assert path.stem not in {
            "rrf",
            "fusion",
            "adaptive",
            "saturation",
            "citation_chasing",
            "entity_expansion",
        }
    for path in (root / "providers").glob("*.py"):
        text = path.read_text()
        assert "novelty_score" not in text and "VerdictState" not in text


def test_network_suite_is_excluded_by_default_and_requires_explicit_enable(pytestconfig):
    assert pytestconfig.getoption("disable_socket") is True
    assert pytestconfig.getoption("markexpr") == "not network"
    assert not pytestconfig.getoption("allow_hosts")
