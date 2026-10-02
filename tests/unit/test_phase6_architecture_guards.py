import ast
import inspect
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from novelty_harness.evidence.verification.models import (
    BlindedVerificationInput,
    SupportVerification,
    VerifiedEvidenceEdge,
)
from novelty_harness.evidence.verification.verifier import IndependentSupportVerifier
from tests.unit.test_import_boundaries import forbidden_imports

ROOT = Path(__file__).parents[2] / "src/novelty_harness"
PHASE6 = ROOT / "evidence"
PHASE6_PACKAGES = ("mapping", "context", "verification", "precedent")
NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)

PHASE7_SYMBOLS = {
    "FrozenAdjudication",
    "VerdictState",
    "MCUFinding",
    "prosecutor",
    "defender",
    "adjudication",
}


def _phase6_modules() -> list[Path]:
    modules = [path for package in PHASE6_PACKAGES for path in (PHASE6 / package).rglob("*.py")]
    modules.append(PHASE6 / "phase6_pipeline.py")
    return sorted(modules)


def test_verifier_api_is_blind_and_minimal() -> None:
    parameters = set(inspect.signature(IndependentSupportVerifier.verify).parameters)
    assert parameters == {"self", "bundle", "clock"}
    forbidden = {
        "verdict",
        "novelty",
        "precedent",
        "relation",
        "prosecutor",
        "defender",
        "quality",
        "tier",
        "rank",
        "provider_score",
        "relevance",
        "report",
    }
    assert not set(BlindedVerificationInput.model_fields) & forbidden
    assert not set(SupportVerification.model_fields) & forbidden
    assert not set(VerifiedEvidenceEdge.model_fields) & {
        "verdict",
        "novelty",
        "probability",
    }
    assert BlindedVerificationInput.model_fields["blinded"].annotation is not None


def test_phase6_modules_do_not_import_phase7_adjudication() -> None:
    for path in _phase6_modules():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in PHASE7_SYMBOLS:
                raise AssertionError(f"{path} references Phase 7 symbol {node.id}")
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                "novelty_harness.domain.adjudication"
            ):
                raise AssertionError(f"{path} imports Phase 7 adjudication")
        assert not forbidden_imports(
            path.read_text(),
            "novelty_harness.evidence",
            banned=("novelty_harness.domain.adjudication", "tests", "httpx"),
        ), path


def test_direct_precedent_is_single_source_by_construction() -> None:
    from novelty_harness.evidence.precedent.gates import MultiSourceAssessment
    from novelty_harness.evidence.precedent.models import PrecedentClassification

    assert PrecedentClassification.model_fields["single_source"].annotation is not None
    summary = MultiSourceAssessment(
        mcu_id="mcu_1",
        combination_context="NONE",
        single_source_direct_eligible=False,
        independent_roots=1,
        contributing_roots=1,
        summary=("local",),
    )
    assert summary.stitched_direct_forbidden is True
    with pytest.raises(ValueError):
        MultiSourceAssessment.model_validate(
            {**summary.model_dump(), "stitched_direct_forbidden": False}
        )


def test_no_phase6_module_reads_provider_scores_or_relevance() -> None:
    for path in _phase6_modules():
        source = path.read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in {
                "provider_score",
                "provider_local_score",
                "relevance_strength",
            }:
                raise AssertionError(f"{path} reads {node.attr}")
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value in {"provider_score", "provider_local_score"}
            ):
                raise AssertionError(f"{path} mentions {node.value}")


def test_no_numeric_novelty_or_confidence_fields_in_phase6_contracts() -> None:
    from novelty_harness.evidence.precedent.models import (
        CounterfactualDiagnostic,
        PatentScreeningResult,
        PrecedentClassification,
    )

    for model in (
        BlindedVerificationInput,
        SupportVerification,
        VerifiedEvidenceEdge,
        PrecedentClassification,
        PatentScreeningResult,
        CounterfactualDiagnostic,
    ):
        for field in model.model_fields:
            assert field not in {
                "novelty_score",
                "confidence",
                "probability",
                "score",
            }, model
    for path in _phase6_modules():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                assert node.id not in {"novelty_score", "confidence"}, path


def test_decisive_edges_require_verified_passage_support() -> None:
    values: dict[str, object] = {
        "edge_id": "edge_1",
        "source_id": "src_1",
        "source_version_id": "srcv_1",
        "mcu_id": "mcu_1",
        "proposition_id": "prop_1",
        "proposition": "claim",
        "mapping_id": "map_1",
        "verification_id": "ver_1",
        "passage_ids": ("pass_1",),
        "support_state": "PARTIALLY_SUPPORTED",
        "decisive": False,
        "chronology": {
            "as_of": date(2026, 9, 28),
            "state": "PREDATES_CUTOFF",
            "decisive_date": date(2024, 1, 1),
        },
        "eligibility": {
            "decisive": False,
            "chronology": {
                "as_of": date(2026, 9, 28),
                "state": "PREDATES_CUTOFF",
                "decisive_date": date(2024, 1, 1),
            },
        },
        "mapper_prompt_version": "evidence-mapper-v1",
        "verifier_prompt_version": "support-verifier-v1",
        "verifier_rubric_version": "support-rubric-v1",
        "observed_at": NOW,
        "provenance": {
            "kind": "implemented",
            "component": "guard",
            "detail": "guard",
        },
    }
    with pytest.raises(ValueError):
        VerifiedEvidenceEdge.model_validate({**values, "decisive": True})
    with pytest.raises(ValueError):
        VerifiedEvidenceEdge.model_validate(
            {
                **values,
                "support_state": "SUPPORTED",
                "decisive": True,
                "chronology": {
                    "as_of": date(2026, 9, 28),
                    "state": "POST_CUTOFF",
                    "decisive_date": date(2027, 1, 1),
                },
                "eligibility": {
                    "decisive": True,
                    "chronology": {
                        "as_of": date(2026, 9, 28),
                        "state": "POST_CUTOFF",
                        "decisive_date": date(2027, 1, 1),
                    },
                },
            }
        )


def test_phase6_pipeline_never_constructs_phase5_only_edges() -> None:
    from novelty_harness.evidence.graph.models import PHASE5_EDGE_KINDS

    for path in _phase6_modules():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id == "GraphEdgeKind"
                and node.attr in {kind.name for kind in PHASE5_EDGE_KINDS}
            ):
                raise AssertionError(f"{path} constructs Phase 5 graph edge {node.attr}")


def test_phase6_production_has_no_fixture_imports_and_default_suite_blocks_network(
    pytestconfig,
) -> None:
    for path in ROOT.rglob("*.py"):
        assert not forbidden_imports(path.read_text(), "novelty_harness", banned=("tests",)), path
    assert pytestconfig.getoption("disable_socket") is True
    assert not pytestconfig.getoption("allow_hosts")


def test_production_has_no_legacy_phase6_projection_surface() -> None:
    for path in ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert node.name != "project_verified_edges", path
            if isinstance(node, ast.ImportFrom):
                assert all(alias.name != "project_verified_edges" for alias in node.names), path
            if isinstance(node, ast.Call):
                function = node.func
                if isinstance(function, ast.Name):
                    assert function.id != "project_verified_edges", path
                if isinstance(function, ast.Attribute):
                    assert function.attr != "project_verified_edges", path
