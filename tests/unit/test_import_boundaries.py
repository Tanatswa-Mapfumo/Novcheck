import ast
from pathlib import Path

import pytest

FORBIDDEN = (
    "novelty_harness.application",
    "novelty_harness.runtime",
    "novelty_harness.ports",
    "tests",
    "httpx",
    "openai",
    "anthropic",
    "google",
    "requests",
    "sqlalchemy",
)


def forbidden_imports(
    source: str, package: str, *, banned: tuple[str, ...] = FORBIDDEN
) -> list[str]:
    violations: list[str] = []
    for node in ast.walk(ast.parse(source)):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                parent = package.split(".")[: len(package.split(".")) - node.level + 1]
                base = ".".join(parent + ([node.module] if node.module else []))
            else:
                base = node.module or ""
            names = [base, *(base + "." + alias.name for alias in node.names)]
        elif isinstance(node, ast.Call) and node.args:
            dynamic_import = (isinstance(node.func, ast.Name) and node.func.id == "__import__") or (
                isinstance(node.func, ast.Attribute) and node.func.attr == "import_module"
            )
            argument = node.args[0]
            if (
                dynamic_import
                and isinstance(argument, ast.Constant)
                and isinstance(argument.value, str)
            ):
                names = [argument.value]
        violations.extend(
            name
            for name in names
            if any(name == prefix or name.startswith(prefix + ".") for prefix in banned)
        )
    return violations


def test_domain_has_no_infrastructure_or_provider_imports() -> None:
    root = Path(__file__).resolve().parents[2] / "src"
    violations: dict[str, list[str]] = {}
    for path in (root / "novelty_harness" / "domain").rglob("*.py"):
        package = ".".join(path.relative_to(root).parent.parts)
        found = forbidden_imports(path.read_text(), package)
        if found:
            violations[str(path)] = found
    assert not violations


@pytest.mark.parametrize(
    "source",
    [
        "import httpx",
        "import openai.client",
        "from anthropic import Client",
        "from novelty_harness import runtime",
        "from .. import ports",
        "from ..runtime.config import models",
        "from google import cloud",
        "import requests",
        "from sqlalchemy import Column",
    ],
)
def test_import_guard_detects_absolute_and_relative_boundaries(source: str) -> None:
    assert forbidden_imports(source, "novelty_harness.domain")


@pytest.mark.parametrize(
    "source",
    [
        "from novelty_harness import application",
        "from ..application import models",
        "import tests.fixtures.phase1",
        "from tests import fixtures",
        "__import__('tests.fixtures.phase1')",
        "import importlib\nimportlib.import_module('novelty_harness.application')",
    ],
)
def test_domain_guard_detects_application_and_test_dependency_leaks(source):
    assert forbidden_imports(source, "novelty_harness.domain")
