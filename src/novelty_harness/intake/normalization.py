from typing import cast

from pydantic import JsonValue

from novelty_harness.domain.assessment import AssessmentRequest
from novelty_harness.domain.idea import (
    ArtifactProvenance,
    CanonicalIdeaRepresentation,
    ClaimedAdvantage,
    IdeaContext,
    ProblemDescription,
)
from novelty_harness.intake.models import NormalizationDraft, NormalizationResult
from novelty_harness.intake.prompts import NORMALIZATION_INSTRUCTION, NORMALIZATION_VERSION
from novelty_harness.ports.models import ContextBlock
from novelty_harness.runtime.semantic.structured import SemanticRunner, SemanticTaskSpec


class GroundingError(ValueError):
    """A material extracted field lacks exact supplied-input support."""


def validate_extractive_grounding(draft: NormalizationDraft, original: str) -> None:
    values = cast(dict[str, JsonValue], draft.model_dump(mode="json"))
    material: dict[str, str] = {}
    for key in (
        "problem",
        "target_users_or_context",
        "domains",
        "application_setting",
        "mechanism",
        "relationship_statements",
        "extracted_claims",
        "advantage_statements",
        "constraints",
        "user_supplied_evidence",
    ):
        value = values[key]
        if isinstance(value, str):
            material[key] = value
        elif isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, str):
                    material[f"{key}.{index}"] = item
    attrs = {a.field_path: a.supporting_excerpt for a in draft.source_attributions}
    if len(attrs) != len(draft.source_attributions) or set(attrs) != set(material):
        raise GroundingError("material field attributions must match exactly")
    for path, value in material.items():
        if attrs[path] != value or value not in original:
            raise GroundingError(f"unsupported material field: {path}")


class FaithfulIdeaNormalizer:
    def __init__(self, runner: SemanticRunner) -> None:
        self.runner = runner

    async def normalize_result(self, request: AssessmentRequest) -> NormalizationResult:
        snapshot = request.model_copy(deep=True)
        draft = await self.runner.run(
            SemanticTaskSpec("normalize_idea", NORMALIZATION_VERSION, NormalizationDraft),
            NORMALIZATION_INSTRUCTION + f"\nprompt_version: {NORMALIZATION_VERSION}",
            [ContextBlock(label="original_input", text=snapshot.input_text)],
        )
        if draft.prompt_version != NORMALIZATION_VERSION:
            raise GroundingError("normalization prompt version mismatch")
        validate_extractive_grounding(draft, snapshot.input_text)
        unknowns = (*draft.explicit_unknowns, *draft.ambiguities)
        if draft.problem is None:
            unknowns += ("Problem unspecified in supplied input.",)
        cir = CanonicalIdeaRepresentation(
            idea_id=snapshot.idea_id,
            original_input=snapshot.input_text,
            original_input_ref="request.json#/input_text",
            title=snapshot.title,
            problem=ProblemDescription(
                statement=draft.problem or "Problem unspecified in supplied input.",
                target_users_or_context=draft.target_users_or_context,
            ),
            context=IdeaContext(
                temporal_cutoff=snapshot.as_of,
                domains=draft.domains,
                application_setting=draft.application_setting,
            ),
            claimed_advantages=tuple(
                ClaimedAdvantage(dimension="user_claim", statement=s)
                for s in draft.advantage_statements
            ),
            user_supplied_evidence=draft.user_supplied_evidence,
            constraints=draft.constraints,
            unknowns=tuple(dict.fromkeys(unknowns)),
            provenance=ArtifactProvenance(
                kind="implemented",
                component="FaithfulIdeaNormalizer",
                detail=f"Extractive grounding; prompt {NORMALIZATION_VERSION}; model-assisted.",
            ),
        )
        return NormalizationResult(**draft.model_dump(), cir=cir)

    async def normalize(self, request: AssessmentRequest) -> CanonicalIdeaRepresentation:
        return (await self.normalize_result(request)).cir
