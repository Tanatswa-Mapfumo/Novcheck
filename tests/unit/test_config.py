import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from novelty_harness.domain.enums import ResearchMode
from novelty_harness.runtime.config.loader import load_settings
from novelty_harness.runtime.config.models import BudgetLimits, HarnessSettings

LIMITS = [
    "max_provider_calls",
    "max_llm_input_tokens",
    "max_llm_output_tokens",
    "max_elapsed_seconds",
    "max_retrieved_documents",
    "max_full_text_fetches",
    "max_deep_search_rounds",
]


@pytest.fixture(autouse=True)
def clean_settings_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    import os

    for key in os.environ:
        if key.startswith("NOVELTY_"):
            monkeypatch.delenv(key)


@pytest.mark.parametrize("mode", list(ResearchMode))
def test_modes_do_not_invent_budgets(mode: ResearchMode) -> None:
    settings = HarnessSettings(research_mode=mode)
    assert all(getattr(settings.budget, field) is None for field in LIMITS)
    assert settings.data_dir == Path(".novelty-harness")
    assert settings.log_level == "INFO"
    assert HarnessSettings().research_mode == ResearchMode.STANDARD


@pytest.mark.parametrize("field", LIMITS)
def test_budgets_reject_negative_and_accept_zero(field: str) -> None:
    with pytest.raises(ValidationError):
        BudgetLimits.model_validate({field: -1})
    budget = BudgetLimits.model_validate({field: 0})
    assert getattr(budget, field) == 0
    assert BudgetLimits.model_validate_json(budget.model_dump_json()) == budget


def test_settings_load_environment_without_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOVELTY_DATA_DIR", "/tmp/nah-test")
    monkeypatch.setenv("NOVELTY_RESEARCH_MODE", "DEEP")
    monkeypatch.setenv("NOVELTY_LOG_LEVEL", "warning")
    monkeypatch.setenv("NOVELTY_BUDGET", '{"max_provider_calls": 2}')
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "test-only-token")
    settings = load_settings()
    assert settings.data_dir == Path("/tmp/nah-test")
    assert settings.research_mode == ResearchMode.DEEP
    assert settings.log_level == "WARNING"
    assert settings.budget.max_provider_calls == 2
    dumped = json.dumps(settings.model_dump(mode="json"))
    assert "test-only-secret" not in dumped and "test-only-token" not in dumped
    assert set(HarnessSettings.model_fields) == {"data_dir", "research_mode", "log_level", "budget"}


@pytest.mark.parametrize("level", ["debug", "info", "warning", "error", "critical"])
def test_log_levels_normalize(level: str) -> None:
    assert HarnessSettings(log_level=level).log_level == level.upper()


def test_unknown_settings_and_invalid_levels_are_rejected() -> None:
    for data in ({"log_level": "VERBOSE"}, {"api_key": "test-only-secret"}):
        with pytest.raises(ValidationError):
            HarnessSettings.model_validate(data)
    with pytest.raises(ValidationError):
        BudgetLimits.model_validate({"saturation": 3})
