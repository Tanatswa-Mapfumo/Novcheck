import ast
from pathlib import Path

ROOT = Path(__file__).parents[2] / "src/novelty_harness/adjudication"


def test_phase7_domain_has_no_provider_sdk_or_phase8_import() -> None:
    banned = (
        "httpx",
        "openai",
        "anthropic",
        "novelty_harness.providers",
        "novelty_harness.phase8",
        "novelty_harness.application.phase8",
    )
    for path in ROOT.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith(banned), (path, node.module)
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith(banned), (path, alias.name)


def test_real_path_never_uses_fixture_authority() -> None:
    root = ROOT.parent
    for filename in (
        "application/phase7.py",
        "application/phase7_roles.py",
        "application/phase7_research.py",
    ):
        tree = ast.parse((root / filename).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.module not in {
                    "novelty_harness.domain.adjudication",
                    "novelty_harness.application.phase6_fixture",
                }
    source = (root / "application/phase7.py").read_text()
    assert "freeze_phase7_adjudication" in source
    assert "load_frozen_adjudication" in source
    tree = ast.parse((root / "reporting/minimal.py").read_text())
    summary = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "summarize_frozen_phase7"
    )
    assert any(
        isinstance(node, ast.Attribute) and node.attr == "load_frozen_adjudication"
        for node in ast.walk(summary)
    )
    assert not any(
        isinstance(node, ast.Attribute) and node.attr in {"model_validate_json", "model_validate"}
        for node in ast.walk(summary)
    )


def test_phase6_semantics_do_not_import_phase7() -> None:
    root = ROOT.parent
    files = [
        *(root / "evidence/precedent").glob("*.py"),
        *(root / "evidence/verification").glob("*.py"),
        root / "evidence/phase6_pipeline.py",
        root / "evidence/graph/assessment_view.py",
    ]
    for path in files:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith(
                    ("novelty_harness.adjudication", "novelty_harness.application.phase7")
                )
