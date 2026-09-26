import ast
import inspect
from pathlib import Path
from typing import get_origin

import pytest

from novelty_harness.mcu.decomposition import (
    IndependenceFocusedDecomposer,
    RelationshipFocusedDecomposer,
)
from novelty_harness.mcu.models import MCUDecomposition
from novelty_harness.mcu.overrides import MCUOverrideRecord, MCUVersion
from novelty_harness.mcu.reconciliation import ReconciliationResult
from tests.unit.test_import_boundaries import forbidden_imports

ROOT = Path(__file__).resolve().parents[2] / "src/novelty_harness"
SEMANTIC_BANNED = (
    "tests",
    "openai",
    "anthropic",
    "google",
    "httpx",
    "aiohttp",
    "requests",
    "socket",
    "urllib.request",
    "novelty_harness.ports.search",
    "novelty_harness.ports.content",
    "novelty_harness.ports.citations",
    "novelty_harness.ports.embeddings",
    "novelty_harness.domain.adjudication",
    "novelty_harness.domain.evidence",
    "novelty_harness.domain.research",
)


def test_understanding_layers_do_not_import_sdk_research_or_verdict_logic():
    for folder in ("intake", "mcu"):
        for path in (ROOT / folder).rglob("*.py"):
            source = path.read_text()
            assert not forbidden_imports(
                source, "novelty_harness." + folder, banned=SEMANTIC_BANNED
            ), path
            for node in ast.walk(ast.parse(source)):
                if isinstance(node, ast.Name):
                    assert node.id not in {
                        "VerdictState",
                        "novelty_score",
                        "RRF",
                        "SearchProvider",
                    }, path
                if isinstance(node, ast.Attribute):
                    assert node.attr not in {"search", "adjudicate", "embed", "rank"}, path


@pytest.mark.parametrize("cls", [IndependenceFocusedDecomposer, RelationshipFocusedDecomposer])
def test_decomposer_interfaces_only_take_runner_and_shared_idea(cls):
    assert set(inspect.signature(cls).parameters) == {"runner"}
    assert set(inspect.signature(cls.decompose_result).parameters) == {"self", "idea"}
    assert set(inspect.signature(cls.decompose).parameters) == {"self", "idea"}


@pytest.mark.parametrize(
    "model", [MCUVersion, MCUOverrideRecord, MCUDecomposition, ReconciliationResult]
)
def test_nested_understanding_history_uses_immutable_collections(model):
    assert model.model_config["frozen"] is True
    assert all(
        get_origin(f.annotation) not in {dict, list, set} for f in model.model_fields.values()
    )


def test_sufficiency_does_not_use_word_token_or_character_count_thresholds():
    tree = ast.parse((ROOT / "intake/sufficiency.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            assert node.id not in {
                "word_count",
                "token_count",
                "input_length",
                "min_words",
                "min_tokens",
            }
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in {"split", "encode", "tokenize"}
        if isinstance(node, ast.Compare):
            calls = [n for n in ast.walk(node) if isinstance(n, ast.Call)]
            assert not any(
                isinstance(c.func, ast.Name) and c.func.id == "len"
                for c in calls
                if isinstance(node.ops[0], (ast.Lt, ast.LtE, ast.Gt, ast.GtE))
            )


def test_real_component_calls_always_use_named_versioned_specs():
    for path in (ROOT / "intake").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "SemanticTaskSpec"
            ):
                assert len(node.args) == 3
                assert not isinstance(node.args[1], ast.Constant) or bool(node.args[1].value)


@pytest.mark.parametrize(
    "source",
    [
        "from openai import Client",
        "from novelty_harness.ports import search",
        "from ..domain import adjudication",
        "import requests",
        "__import__('tests.fixtures.phase2')",
    ],
)
def test_understanding_guard_detects_concrete_and_later_phase_dependency_leaks(source):
    assert forbidden_imports(source, "novelty_harness.intake", banned=SEMANTIC_BANNED)
