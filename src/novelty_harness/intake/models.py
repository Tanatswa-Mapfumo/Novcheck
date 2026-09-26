from pydantic import ConfigDict

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.idea import CanonicalIdeaRepresentation, NonBlankText


class InputSpanAttribution(ContractModel):
    model_config = ConfigDict(frozen=True)
    field_path: NonBlankText
    supporting_excerpt: NonBlankText


class NormalizationDraft(ContractModel):
    model_config = ConfigDict(frozen=True)
    problem: NonBlankText | None
    target_users_or_context: NonBlankText | None
    domains: tuple[NonBlankText, ...]
    application_setting: NonBlankText | None
    mechanism: NonBlankText | None
    relationship_statements: tuple[NonBlankText, ...]
    extracted_claims: tuple[NonBlankText, ...]
    advantage_statements: tuple[NonBlankText, ...]
    constraints: tuple[NonBlankText, ...]
    user_supplied_evidence: tuple[NonBlankText, ...]
    explicit_unknowns: tuple[NonBlankText, ...]
    ambiguities: tuple[NonBlankText, ...]
    source_attributions: tuple[InputSpanAttribution, ...]
    prompt_version: NonBlankText


class NormalizationResult(NormalizationDraft):
    cir: CanonicalIdeaRepresentation
