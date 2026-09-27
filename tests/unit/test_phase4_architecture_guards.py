import ast
from pathlib import Path

import pytest

from novelty_harness.research.adaptive.stopping import StopAssessment
from novelty_harness.research.expansion.chronology import CandidateChronology
from tests.unit.test_import_boundaries import forbidden_imports

ROOT = Path(__file__).parents[2] / "src/novelty_harness"


def test_rrf_cannot_read_provider_scores_or_import_concrete_providers():
    text = (ROOT / "research/fusion/rrf.py").read_text()
    tree = ast.parse(text)
    assert not any(
        isinstance(n, ast.Attribute) and n.attr in {"provider_score", "provider_local_score"}
        for n in ast.walk(tree)
    )
    assert not any(
        isinstance(n, ast.Constant) and n.value in {"provider_score", "provider_local_score"}
        for n in ast.walk(tree)
    )
    assert not forbidden_imports(
        text, "novelty_harness.research.fusion", banned=("novelty_harness.providers",)
    )


def test_phase4_modules_cannot_assign_verdicts_or_promote_retrieval_to_evidence():
    for subdir in (
        "research/adaptive",
        "research/retrieval",
        "research/fusion",
        "research/expansion",
    ):
        for path in (ROOT / subdir).glob("*.py"):
            tree = ast.parse(path.read_text())
            assert not any(
                isinstance(n, ast.Name)
                and n.id
                in {
                    "VerdictState",
                    "EvidenceEdge",
                    "SourceRecord",
                    "FrozenAdjudication",
                    "SupportVerificationState",
                }
                for n in ast.walk(tree)
            ), path


@pytest.mark.parametrize(
    "signals,gaps",
    [({"budget_blocked": True}, ()), ({"budget_blocked": False}, ("unresolved provider",))],
)
def test_saturated_artifacts_reject_hard_budget_or_access_gaps(signals, gaps):
    with pytest.raises(ValueError):
        StopAssessment.model_validate(
            {"reason": "SATURATED", "signals": signals, "unresolved_gaps": gaps}
        )


def test_chronology_keeps_all_public_priority_repository_release_and_archive_fields():
    assert {
        "publication_date",
        "first_public_version",
        "repository_created_at",
        "first_release_date",
        "patent_priority_date",
        "patent_publication_date",
        "product_launch_date",
        "archive_capture_date",
    } <= CandidateChronology.model_fields.keys()


def test_production_has_no_fixture_or_vendor_sdk_dependencies_and_domain_has_no_http():
    for path in ROOT.rglob("*.py"):
        assert not forbidden_imports(
            path.read_text(),
            "novelty_harness",
            banned=("tests", "openai", "anthropic", "semanticscholar", "pyalex"),
        ), path
    for path in (ROOT / "domain").rglob("*.py"):
        assert not forbidden_imports(
            path.read_text(),
            "novelty_harness.domain",
            banned=("novelty_harness.providers", "httpx"),
        ), path
