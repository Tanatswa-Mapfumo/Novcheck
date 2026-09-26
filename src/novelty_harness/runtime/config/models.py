from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.enums import ResearchMode


class BudgetLimits(ContractModel):
    max_provider_calls: int | None = Field(default=None, ge=0)
    max_llm_input_tokens: int | None = Field(default=None, ge=0)
    max_llm_output_tokens: int | None = Field(default=None, ge=0)
    max_elapsed_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    max_retrieved_documents: int | None = Field(default=None, ge=0)
    max_full_text_fetches: int | None = Field(default=None, ge=0)
    max_deep_search_rounds: int | None = Field(default=None, ge=0)


class HarnessSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NOVELTY_", extra="forbid")
    data_dir: Path = Path(".novelty-harness")
    research_mode: ResearchMode = ResearchMode.STANDARD
    log_level: str = "INFO"
    budget: BudgetLimits = Field(default_factory=BudgetLimits)

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        level = value.upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("unsupported log level")
        return level
