import ast
from pathlib import Path

import pytest

FORBIDDEN = (
    "novelty_harness.runtime",
    "novelty_harness.ports",
    "httpx",
    "openai",
    "anthropic",
    "google",
    "requests",
    "sqlalchemy",
)


def forbidden_imports(source: str, package: str) -> list[str]:
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
        violations.extend(
            name
            for name in names
            if any(name == banned or name.startswith(banned + ".") for banned in FORBIDDEN)
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
