import re

from novelty_harness.domain.idea import ArtifactProvenance, CanonicalIdeaRepresentation
from novelty_harness.domain.mcu import MCU, MCUCombination
from novelty_harness.intake.normalization import GroundingError
from novelty_harness.mcu.models import MCUCandidate, MCUDecomposition
from novelty_harness.mcu.prompts import (
    DECOMPOSITION_A_INSTRUCTION,
    DECOMPOSITION_A_VERSION,
    DECOMPOSITION_B_INSTRUCTION,
    DECOMPOSITION_B_VERSION,
)
from novelty_harness.ports.models import ContextBlock
from novelty_harness.runtime.semantic.structured import SemanticRunner, SemanticTaskSpec


def validate_graph(mcus: tuple[MCU, ...], combinations: tuple[MCUCombination, ...]) -> None:
    ids = {m.mcu_id for m in mcus}
    if len(ids) != len(mcus):
        raise ValueError("duplicate MCU IDs")
    combination_ids = {c.combination_id for c in combinations}
    if len(combination_ids) != len(combinations) or ids & combination_ids:
        raise ValueError("duplicate or colliding combination IDs")
    for mcu in mcus:
        features = {f.feature_id for f in mcu.features}
        if len(features) != len(mcu.features):
            raise ValueError("duplicate feature IDs")
        if any(r.subject not in features or r.object not in features for r in mcu.relationships):
            raise ValueError("dangling feature relationship")
        if len(set(mcu.relationships)) != len(mcu.relationships):
            raise ValueError("duplicate relationship")
    for combination in combinations:
        members = set(combination.member_ids)
        if not members <= ids:
            raise ValueError("dangling combination member")
        if any(
            r.subject not in members or r.object not in members for r in combination.relationships
        ):
            raise ValueError("dangling combination relationship")


def validate_candidate(candidate: MCUCandidate, original: str) -> None:
    support = candidate.source_support
    if any(excerpt not in original for excerpt in support):
        raise GroundingError("candidate support absent from original")
    mcu = candidate.mcu
    for value in (
        mcu.statement,
        mcu.mechanism,
        mcu.purpose,
        mcu.object_or_target,
        mcu.intended_effect,
        mcu.context,
    ):
        if value is not None and not any(value in excerpt for excerpt in support):
            raise GroundingError("unsupported material MCU field")
    for feature in mcu.features:
        if not any(feature.concept.casefold() in excerpt.casefold() for excerpt in support):
            raise GroundingError("unsupported feature concept")
    validate_graph((mcu,), ())
    concepts = {f.feature_id: (f.concept,) for f in mcu.features}
    for relationship in mcu.relationships:
        if not _relationship_supported(
            relationship.relation,
            concepts[relationship.subject],
            concepts[relationship.object],
            support,
        ):
            raise GroundingError("relationship predicate lacks input support")


def _relationship_supported(
    predicate: str,
    subjects: tuple[str, ...],
    objects: tuple[str, ...],
    support: tuple[str, ...],
) -> bool:
    words = re.findall(r"\w+", predicate.casefold())
    if not words:
        return False
    # Surface inflections permit active/passive wording, never inferred synonym predicates.
    last = words[-1]
    base = last[:-1] if len(last) > 1 and last.endswith("s") and not last.endswith("ss") else last
    forms = {last, base, base + "s", base + "ed", base + "ing"}
    forms.update((base + base[-1] + "ed", base + base[-1] + "ing"))
    if base.endswith("e"):
        forms.update((base + "d", base[:-1] + "ing"))
    predicates = {tuple((*words[:-1], form)) for form in forms}
    for excerpt in support:
        lowered = excerpt.casefold()
        if not any(s.casefold() in lowered for s in subjects) or not any(
            o.casefold() in lowered for o in objects
        ):
            continue
        tokens = re.findall(r"\w+", lowered)
        if any(
            tuple(tokens[i : i + len(words)]) in predicates
            for i in range(len(tokens) - len(words) + 1)
        ):
            return True
    return False


def validate_decomposition(result: MCUDecomposition, original: str) -> None:
    for candidate in result.candidates:
        validate_candidate(candidate, original)
    for item in result.combinations:
        if any(excerpt not in original for excerpt in item.source_support) or not any(
            item.combination.statement in excerpt for excerpt in item.source_support
        ):
            raise GroundingError("unsupported combination")
    validate_graph(
        tuple(c.mcu for c in result.candidates), tuple(c.combination for c in result.combinations)
    )
    by_id = {c.mcu.mcu_id: c.mcu for c in result.candidates}
    for item in result.combinations:
        for relationship in item.combination.relationships:
            subject = by_id[relationship.subject]
            obj = by_id[relationship.object]
            if not _relationship_supported(
                relationship.relation,
                tuple(f.concept for f in subject.features) or (subject.statement,),
                tuple(f.concept for f in obj.features) or (obj.statement,),
                item.source_support,
            ):
                raise GroundingError("combination relationship predicate lacks input support")


class IndependenceFocusedDecomposer:
    def __init__(self, runner: SemanticRunner) -> None:
        self.runner = runner

    async def decompose_result(self, idea: CanonicalIdeaRepresentation) -> MCUDecomposition:
        return await _decompose(self.runner, idea, "a")

    async def decompose(self, idea: CanonicalIdeaRepresentation) -> tuple[MCU, ...]:
        return tuple(c.mcu for c in (await self.decompose_result(idea)).candidates)


class RelationshipFocusedDecomposer:
    def __init__(self, runner: SemanticRunner) -> None:
        self.runner = runner

    async def decompose_result(self, idea: CanonicalIdeaRepresentation) -> MCUDecomposition:
        return await _decompose(self.runner, idea, "b")

    async def decompose(self, idea: CanonicalIdeaRepresentation) -> tuple[MCU, ...]:
        return tuple(c.mcu for c in (await self.decompose_result(idea)).candidates)


async def _decompose(
    runner: SemanticRunner,
    idea: CanonicalIdeaRepresentation,
    strategy: str,
) -> MCUDecomposition:
    version = DECOMPOSITION_A_VERSION if strategy == "a" else DECOMPOSITION_B_VERSION
    instruction = DECOMPOSITION_A_INSTRUCTION if strategy == "a" else DECOMPOSITION_B_INSTRUCTION
    result = await runner.run(
        SemanticTaskSpec("decompose_" + strategy, version, MCUDecomposition),
        instruction + f"\nprompt_version: {version}",
        [ContextBlock(label="canonical_idea", text=idea.model_dump_json())],
    )
    expected = "INDEPENDENCE_FOCUSED" if strategy == "a" else "RELATIONSHIP_FOCUSED"
    if result.strategy != expected or result.prompt_version != version:
        raise ValueError("decomposition strategy or prompt mismatch")
    validate_decomposition(result, idea.original_input)
    # Provenance is application-authored, never trusted from model output.
    candidates = tuple(
        MCUCandidate.model_validate(
            {
                **c.model_dump(),
                "mcu": {
                    **c.mcu.model_dump(),
                    "provenance": ArtifactProvenance(
                        kind="implemented",
                        component="decompose_" + strategy,
                        detail=f"Grounded model-assisted decomposition; prompt {version}.",
                    ),
                },
            }
        )
        for c in result.candidates
    )
    return MCUDecomposition.model_validate({**result.model_dump(), "candidates": candidates})
