from typing import Literal

from pydantic import ConfigDict

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.idea import NonBlankText
from novelty_harness.domain.ids import MCUId
from novelty_harness.domain.mcu import MCU
from novelty_harness.mcu.models import MCUCandidate, MCUDecomposition
from novelty_harness.ports.models import ContextBlock
from novelty_harness.runtime.semantic.structured import SemanticRunner, SemanticTaskSpec

ALIGNMENT_VERSION = "alignment-v1"


class MCUAlignmentPair(ContractModel):
    model_config = ConfigDict(frozen=True)
    left_mcu_id: MCUId
    right_mcu_id: MCUId
    relation: Literal[
        "EQUIVALENT",
        "OVERLAPPING",
        "LEFT_SUBSUMES_RIGHT",
        "RIGHT_SUBSUMES_LEFT",
        "DISTINCT",
        "UNRESOLVED",
    ]
    structural_reasons: tuple[NonBlankText, ...]
    relationship_differences: tuple[NonBlankText, ...]


class DecompositionAlignment(ContractModel):
    model_config = ConfigDict(frozen=True)
    pairs: tuple[MCUAlignmentPair, ...]
    unmatched_left: tuple[MCUId, ...]
    unmatched_right: tuple[MCUId, ...]
    prompt_version: NonBlankText = ALIGNMENT_VERSION


class FeaturePair(ContractModel):
    model_config = ConfigDict(frozen=True)
    left_feature_id: NonBlankText
    right_feature_id: NonBlankText


class SemanticMapping(ContractModel):
    model_config = ConfigDict(frozen=True)
    left_mcu_id: MCUId
    right_mcu_id: MCUId
    feature_pairs: tuple[FeaturePair, ...]
    explanation: NonBlankText


class AlignmentProposal(ContractModel):
    model_config = ConfigDict(frozen=True)
    prompt_version: NonBlankText
    mappings: tuple[SemanticMapping, ...]


def normalized(text: str | None) -> str:
    return " ".join((text or "").casefold().split())


def signature(mcu: MCU) -> frozenset[tuple[str, str, str]]:
    concepts = {f.feature_id: normalized(f.concept) for f in mcu.features}
    return frozenset(
        (concepts[r.subject], normalized(r.relation), concepts[r.object]) for r in mcu.relationships
    )


def _scope(mcu: MCU) -> tuple[str, ...]:
    return tuple(
        normalized(v)
        for v in (
            mcu.mechanism,
            mcu.purpose,
            mcu.object_or_target,
            mcu.intended_effect,
            mcu.context,
        )
    )


def _compare(left: MCUCandidate, right: MCUCandidate) -> MCUAlignmentPair | None:
    a, b = left.mcu, right.mcu
    fa = frozenset(normalized(f.concept) for f in a.features)
    fb = frozenset(normalized(f.concept) for f in b.features)
    sa, sb = signature(a), signature(b)
    support_overlap = bool(set(left.source_support) & set(right.source_support))
    if not support_overlap and not fa & fb and normalized(a.statement) != normalized(b.statement):
        return None
    relation: Literal[
        "EQUIVALENT",
        "OVERLAPPING",
        "LEFT_SUBSUMES_RIGHT",
        "RIGHT_SUBSUMES_LEFT",
        "DISTINCT",
        "UNRESOLVED",
    ] = "UNRESOLVED"
    differences: tuple[str, ...] = ()
    if _scope(a) != _scope(b):
        differences = ("Material mechanism/purpose/effect/context differs",)
    elif fa == fb and sa == sb and (bool(sa) or normalized(a.statement) == normalized(b.statement)):
        relation = "EQUIVALENT"
    elif fa == fb and sa != sb:
        relation = "DISTINCT"
        differences = ("Directed relationship signatures differ",)
    elif fb < fa and sb <= sa:
        relation = "LEFT_SUBSUMES_RIGHT"
        differences = ("Left graph contains more structure; merge/split disagreement",)
    elif fa < fb and sa <= sb:
        relation = "RIGHT_SUBSUMES_LEFT"
        differences = ("Right graph contains more structure; merge/split disagreement",)
    elif fa & fb:
        relation = "OVERLAPPING"
        differences = ("Partially overlapping features or relationships",)
    else:
        differences = ("Concept correspondence unresolved; topology alone is insufficient",)
    return MCUAlignmentPair(
        left_mcu_id=a.mcu_id,
        right_mcu_id=b.mcu_id,
        relation=relation,
        structural_reasons=("Compared exact support, feature concepts, directed links and scope",),
        relationship_differences=differences,
    )


def _consistent_mapping(mapping: SemanticMapping, left: MCU, right: MCU) -> bool:
    ids = {p.left_feature_id: p.right_feature_id for p in mapping.feature_pairs}
    if len(ids) != len(mapping.feature_pairs) or len(set(ids.values())) != len(ids):
        return False
    if (
        set(ids) != {f.feature_id for f in left.features}
        or set(ids.values()) != {f.feature_id for f in right.features}
        or not ids
        or _scope(left) != _scope(right)
    ):
        return False
    mapped = {(ids[r.subject], normalized(r.relation), ids[r.object]) for r in left.relationships}
    expected = {(r.subject, normalized(r.relation), r.object) for r in right.relationships}
    return bool(mapped) and mapped == expected


async def align_decompositions(
    left: MCUDecomposition,
    right: MCUDecomposition,
    *,
    runner: SemanticRunner | None = None,
) -> DecompositionAlignment:
    pairs = [
        pair
        for a in left.candidates
        for b in right.candidates
        if (pair := _compare(a, b)) is not None
    ]
    if runner is not None and any(p.relation == "UNRESOLVED" for p in pairs):
        proposal = await runner.run(
            SemanticTaskSpec("align_mcus", ALIGNMENT_VERSION, AlignmentProposal),
            "Map equivalent feature concepts for unresolved MCU pairs only. "
            "Never infer equivalence from text similarity or topology alone; "
            "preserve directed predicates and material scope. prompt_version: " + ALIGNMENT_VERSION,
            [
                ContextBlock(label="left", text=left.model_dump_json()),
                ContextBlock(label="right", text=right.model_dump_json()),
            ],
        )
        if proposal.prompt_version != ALIGNMENT_VERSION:
            raise ValueError("alignment version mismatch")
        mappings = {(m.left_mcu_id, m.right_mcu_id): m for m in proposal.mappings}
        if len(mappings) != len(proposal.mappings) or not set(mappings) <= {
            (p.left_mcu_id, p.right_mcu_id) for p in pairs if p.relation == "UNRESOLVED"
        }:
            raise ValueError("invalid semantic alignment references")
        a_by_id = {c.mcu.mcu_id: c for c in left.candidates}
        b_by_id = {c.mcu.mcu_id: c for c in right.candidates}
        for index, pair in enumerate(pairs):
            mapping = mappings.get((pair.left_mcu_id, pair.right_mcu_id))
            if mapping is not None and _consistent_mapping(
                mapping, a_by_id[pair.left_mcu_id].mcu, b_by_id[pair.right_mcu_id].mcu
            ):
                pairs[index] = MCUAlignmentPair.model_validate(
                    {
                        **pair.model_dump(),
                        "relation": "EQUIVALENT",
                        "relationship_differences": (),
                        "structural_reasons": (*pair.structural_reasons, mapping.explanation),
                    }
                )
    equivalent_pairs = tuple(p for p in pairs if p.relation == "EQUIVALENT")
    for index, pair in enumerate(pairs):
        if pair.relation == "EQUIVALENT" and (
            sum(p.left_mcu_id == pair.left_mcu_id for p in equivalent_pairs) > 1
            or sum(p.right_mcu_id == pair.right_mcu_id for p in equivalent_pairs) > 1
        ):
            pairs[index] = MCUAlignmentPair.model_validate(
                {
                    **pair.model_dump(),
                    "relation": "UNRESOLVED",
                    "relationship_differences": ("Ambiguous multiple matches",),
                }
            )
    return DecompositionAlignment(
        pairs=tuple(pairs),
        unmatched_left=tuple(
            c.mcu.mcu_id
            for c in left.candidates
            if not any(p.left_mcu_id == c.mcu.mcu_id for p in pairs)
        ),
        unmatched_right=tuple(
            c.mcu.mcu_id
            for c in right.candidates
            if not any(p.right_mcu_id == c.mcu.mcu_id for p in pairs)
        ),
    )
