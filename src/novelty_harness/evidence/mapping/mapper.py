"""Source-to-MCU candidate mapper.

The mapper turns an MCU proposition and a source's exact passages into a
strict, passage-grounded *proposal*. Deterministic gates then verify that every
cited passage exists, belongs to the source/version, and that relationship
dimensions carry directed structure. A mapping never asserts support.
"""

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Literal

from pydantic import ConfigDict

from novelty_harness.domain.base import ContractModel, utc_now
from novelty_harness.domain.idea import ArtifactProvenance, NonBlankText
from novelty_harness.domain.ids import MappingId
from novelty_harness.evidence.mapping.models import (
    RELATIONSHIP_DIMENSIONS,
    ComparisonDimension,
    DimensionMapping,
    EvidenceProposition,
    MappedStatement,
    SourceMCUMapping,
)
from novelty_harness.evidence.mapping.prompts import (
    MAPPER_INSTRUCTION,
    MAPPER_PROMPT_VERSION,
    MAPPER_RUBRIC_VERSION,
    MapperDimensionResult,
    MapperProposal,
    MapperStatement,
)
from novelty_harness.evidence.normalization.models import SourceRecord, SourceVersionRecord
from novelty_harness.evidence.passages.models import PassageRecord
from novelty_harness.ports.models import ContextBlock
from novelty_harness.runtime.semantic.structured import SemanticRunner, SemanticTaskSpec
from novelty_harness.runtime.tracing.hashing import canonical_hash, canonical_json

MAPPER_TASK = "map_evidence"


class MappingValidationError(ValueError):
    """The mapper proposal violated passage integrity or structure rules."""


class MapperInput(ContractModel):
    """What the mapper stage is allowed to see (no quality, rank or verdict)."""

    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["mapper-input-v1"] = "mapper-input-v1"

    source_id: NonBlankText
    source_version_id: NonBlankText | None
    proposition: EvidenceProposition
    passages: tuple[PassageRecord, ...]


def _passage_index(
    source_id: str,
    source_version_id: str | None,
    passages: Sequence[PassageRecord],
) -> dict[str, PassageRecord]:
    index: dict[str, PassageRecord] = {}
    for passage in passages:
        if passage.source_id != source_id:
            raise MappingValidationError("Passage does not belong to the mapped source")
        if source_version_id is not None and passage.source_version_id not in {
            None,
            source_version_id,
        }:
            raise MappingValidationError("Passage belongs to another source version")
        index[passage.passage_id] = passage
    return index


def _mapped_statement(
    statement: MapperStatement,
    dimension: ComparisonDimension,
    index: dict[str, PassageRecord],
) -> MappedStatement:
    unknown = [identity for identity in statement.passage_ids if identity not in index]
    if unknown:
        raise MappingValidationError(
            f"Mapper cited passages that do not belong to the source/version: {unknown}"
        )
    return MappedStatement(
        dimension=dimension,
        statement=statement.statement,
        passage_ids=statement.passage_ids,
        relationship=statement.relationship,
    )


def build_mapping(
    *,
    source: SourceRecord,
    version: SourceVersionRecord | None,
    proposition: EvidenceProposition,
    passages: Sequence[PassageRecord],
    proposal: MapperProposal,
    observed_at: datetime,
) -> SourceMCUMapping:
    """Deterministically validate an untrusted proposal into a mapping."""

    index = _passage_index(source.source_id, version.version_id if version else None, passages)
    dimensions: list[DimensionMapping] = []
    for result in proposal.dimensions:
        if result.dimension in RELATIONSHIP_DIMENSIONS:
            if any(item.relationship is None for item in (*result.matching, *result.conflicting)):
                raise MappingValidationError(
                    f"{result.dimension.value} mappings require directed relationships"
                )
        dimensions.append(
            DimensionMapping(
                dimension=result.dimension,
                matching=tuple(
                    _mapped_statement(item, result.dimension, index) for item in result.matching
                ),
                missing=result.missing,
                conflicting=tuple(
                    _mapped_statement(item, result.dimension, index) for item in result.conflicting
                ),
            )
        )
    if not dimensions:
        raise MappingValidationError("A mapping must address at least one dimension")
    identity = canonical_hash(
        {
            "source_id": source.source_id,
            "source_version_id": version.version_id if version else None,
            "mcu_id": proposition.mcu_id,
            "proposition_id": proposition.proposition_id,
            "dimensions": [item.model_dump(mode="json") for item in dimensions],
            "unresolved": list(proposal.unresolved),
            "mapper_prompt_version": MAPPER_PROMPT_VERSION,
        }
    )
    mapping_id: MappingId = "map_" + identity
    return SourceMCUMapping(
        mapping_id=mapping_id,
        source_id=source.source_id,
        source_version_id=version.version_id if version else None,
        mcu_id=proposition.mcu_id,
        proposition_id=proposition.proposition_id,
        dimensions=tuple(dimensions),
        unresolved=proposal.unresolved,
        mapper_prompt_version=MAPPER_PROMPT_VERSION,
        mapper_rubric_version=MAPPER_RUBRIC_VERSION,
        observed_at=observed_at,
        provenance=_mapper_provenance(),
    )


def _mapper_provenance() -> ArtifactProvenance:
    return ArtifactProvenance(
        kind="implemented",
        component="evidence_mapper",
        detail="Passage-grounded mapping proposal; support verification is a separate stage.",
    )


class EvidenceMapperV2:
    """LLM-assisted proposal stage; never a verification or classification stage."""

    def __init__(self, runner: SemanticRunner) -> None:
        self.runner = runner

    async def map_source_to_mcu(
        self,
        *,
        proposition: EvidenceProposition,
        source: SourceRecord,
        version: SourceVersionRecord | None,
        passages: Sequence[PassageRecord],
        clock: Callable[[], datetime] = utc_now,
    ) -> SourceMCUMapping:
        inputs = MapperInput(
            source_id=source.source_id,
            source_version_id=version.version_id if version else None,
            proposition=proposition,
            passages=tuple(passages),
        )
        proposal = await self.runner.run(
            SemanticTaskSpec(MAPPER_TASK, MAPPER_PROMPT_VERSION, MapperProposal),
            MAPPER_INSTRUCTION,
            [
                ContextBlock(
                    label="proposition",
                    text=canonical_json(inputs.proposition.model_dump(mode="json")),
                ),
                ContextBlock(
                    label="source_identity",
                    text=canonical_json(
                        {
                            "source_id": inputs.source_id,
                            "source_version_id": inputs.source_version_id,
                        }
                    ),
                ),
                ContextBlock(
                    label="passages",
                    text=canonical_json(
                        [
                            {
                                "passage_id": passage.passage_id,
                                "locator": passage.locator.kind.value,
                                "text": passage.text,
                            }
                            for passage in inputs.passages
                        ]
                    ),
                ),
            ],
        )
        return build_mapping(
            source=source,
            version=version,
            proposition=proposition,
            passages=passages,
            proposal=proposal,
            observed_at=clock(),
        )


def propose_dimension(
    dimension: ComparisonDimension,
    *,
    matching: Sequence[MapperStatement] = (),
    missing: Sequence[str] = (),
    conflicting: Sequence[MapperStatement] = (),
) -> MapperDimensionResult:
    """Small helper for deterministic fixtures and tests."""

    return MapperDimensionResult(
        dimension=dimension,
        matching=tuple(matching),
        missing=tuple(missing),
        conflicting=tuple(conflicting),
    )
