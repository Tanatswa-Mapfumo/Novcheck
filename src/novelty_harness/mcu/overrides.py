import json
from datetime import datetime
from typing import Literal, Self, cast

from pydantic import ConfigDict, Field, JsonValue, model_validator

from novelty_harness.domain.base import ContractModel, UTCDateTime
from novelty_harness.domain.idea import NonBlankText
from novelty_harness.domain.ids import MCUId
from novelty_harness.domain.mcu import MCU, MCUCombination, MCURelationship
from novelty_harness.mcu.decomposition import validate_graph
from novelty_harness.runtime.tracing.hashing import canonical_hash, canonical_json

OverrideKind = Literal[
    "ADD_MCU",
    "EDIT_MCU",
    "REMOVE_MCU",
    "MERGE_MCUS",
    "SPLIT_MCU",
    "ADD_RELATIONSHIP",
    "REMOVE_RELATIONSHIP",
    "EDIT_COMBINATION",
]


class MCUOverrideOperation(ContractModel):
    model_config = ConfigDict(frozen=True)
    operation_id: NonBlankText
    kind: OverrideKind
    payload: dict[str, JsonValue]
    reason: NonBlankText
    actor: NonBlankText
    occurred_at: UTCDateTime


class MCUOverrideRecord(ContractModel):
    model_config = ConfigDict(frozen=True)
    operation_id: NonBlankText
    kind: OverrideKind
    payload_json: NonBlankText
    reason: NonBlankText
    actor: NonBlankText
    occurred_at: UTCDateTime
    previous_mcus: tuple[MCU, ...]
    previous_combinations: tuple[MCUCombination, ...]
    parent_version_id: NonBlankText
    before_graph_hash: NonBlankText
    after_graph_hash: NonBlankText

    @property
    def payload(self) -> dict[str, JsonValue]:
        return cast(dict[str, JsonValue], json.loads(self.payload_json))


class MCUVersionContent(ContractModel):
    model_config = ConfigDict(frozen=True)
    parent_version_id: NonBlankText | None
    created_at: UTCDateTime
    created_by: NonBlankText
    mcus: tuple[MCU, ...]
    combinations: tuple[MCUCombination, ...]
    overrides: tuple[MCUOverrideRecord, ...]
    source_reconciliation_hash: NonBlankText


class MCUVersion(MCUVersionContent):
    version_id: NonBlankText

    @model_validator(mode="after")
    def valid_snapshot(self) -> Self:
        validate_graph(self.mcus, self.combinations)
        if len({o.operation_id for o in self.overrides}) != len(self.overrides):
            raise ValueError("duplicate override IDs")
        if self.version_id != "mcuv_" + canonical_hash(
            self.model_dump(mode="json", exclude={"version_id"})
        ):
            raise ValueError("MCU version content hash mismatch")
        return self


class MCUPayload(ContractModel):
    mcu: MCU


class RemovePayload(ContractModel):
    mcu_id: MCUId


class MergePayload(ContractModel):
    mcu_ids: tuple[MCUId, ...] = Field(min_length=2)
    mcu: MCU
    combination_updates: tuple[MCUCombination, ...] = ()


class SplitPayload(ContractModel):
    mcu_id: MCUId
    mcus: tuple[MCU, ...] = Field(min_length=2)
    combination_updates: tuple[MCUCombination, ...] = ()


class RelationshipPayload(ContractModel):
    mcu_id: MCUId
    relationship: MCURelationship


class CombinationPayload(ContractModel):
    combination: MCUCombination


def _version(
    *,
    parent_version_id: str | None,
    created_at: datetime,
    created_by: str,
    mcus: tuple[MCU, ...],
    combinations: tuple[MCUCombination, ...],
    overrides: tuple[MCUOverrideRecord, ...],
    source_reconciliation_hash: str,
) -> MCUVersion:
    content = MCUVersionContent(
        parent_version_id=parent_version_id,
        created_at=created_at,
        created_by=created_by,
        mcus=mcus,
        combinations=combinations,
        overrides=overrides,
        source_reconciliation_hash=source_reconciliation_hash,
    )
    return MCUVersion.model_validate(
        {
            **content.model_dump(mode="json"),
            "version_id": "mcuv_" + canonical_hash(content),
        }
    )


class GraphContent(ContractModel):
    mcus: tuple[MCU, ...]
    combinations: tuple[MCUCombination, ...]


def create_mcu_version(
    *,
    mcus: tuple[MCU, ...],
    combinations: tuple[MCUCombination, ...],
    source_reconciliation_hash: str,
    created_at: datetime,
    created_by: str,
) -> MCUVersion:
    return _version(
        parent_version_id=None,
        created_at=created_at,
        created_by=created_by,
        mcus=mcus,
        combinations=combinations,
        overrides=(),
        source_reconciliation_hash=source_reconciliation_hash,
    )


def apply_override(parent: MCUVersion, operation: MCUOverrideOperation) -> MCUVersion:
    parent = MCUVersion.model_validate_json(parent.model_dump_json())
    op = MCUOverrideOperation.model_validate_json(operation.model_dump_json())
    if any(o.operation_id == op.operation_id for o in parent.overrides):
        raise ValueError("duplicate override operation")
    if op.occurred_at < parent.created_at:
        raise ValueError("override predates parent version")
    mcus = {m.mcu_id: m for m in parent.mcus}
    combinations = {c.combination_id: c for c in parent.combinations}

    def require(mcu_id: str) -> MCU:
        if mcu_id not in mcus:
            raise ValueError("unknown MCU reference")
        return mcus[mcu_id]

    def insert(mcu: MCU) -> None:
        if mcu.mcu_id in mcus:
            raise ValueError("duplicate MCU ID")
        mcus[mcu.mcu_id] = mcu

    raw = canonical_json(op.payload)
    if op.kind in ("ADD_MCU", "EDIT_MCU"):
        item = MCUPayload.model_validate_json(raw, strict=True).mcu
        if op.kind == "ADD_MCU":
            insert(item)
        else:
            require(item.mcu_id)
            mcus[item.mcu_id] = item
    elif op.kind == "REMOVE_MCU":
        item_id = RemovePayload.model_validate_json(raw, strict=True).mcu_id
        require(item_id)
        del mcus[item_id]
    elif op.kind in ("MERGE_MCUS", "SPLIT_MCU"):
        if op.kind == "MERGE_MCUS":
            merge = MergePayload.model_validate_json(raw, strict=True)
            if len(set(merge.mcu_ids)) != len(merge.mcu_ids):
                raise ValueError("duplicate merge input")
            removed, added, updates = merge.mcu_ids, (merge.mcu,), merge.combination_updates
        else:
            split = SplitPayload.model_validate_json(raw, strict=True)
            removed, added, updates = (split.mcu_id,), split.mcus, split.combination_updates
        for mcu_id in removed:
            require(mcu_id)
        for mcu_id in removed:
            del mcus[mcu_id]
        for mcu in added:
            insert(mcu)
        if len({c.combination_id for c in updates}) != len(updates):
            raise ValueError("duplicate combination update")
        for combination in updates:
            combinations[combination.combination_id] = combination
    elif op.kind in ("ADD_RELATIONSHIP", "REMOVE_RELATIONSHIP"):
        relation = RelationshipPayload.model_validate_json(raw, strict=True)
        item = require(relation.mcu_id)
        relationships = list(item.relationships)
        if op.kind == "ADD_RELATIONSHIP":
            if relation.relationship in relationships:
                raise ValueError("duplicate relationship")
            relationships.append(relation.relationship)
        else:
            if relation.relationship not in relationships:
                raise ValueError("relationship absent")
            relationships.remove(relation.relationship)
        mcus[item.mcu_id] = MCU.model_validate(
            {**item.model_dump(), "relationships": relationships}
        )
    else:
        item = CombinationPayload.model_validate_json(raw, strict=True).combination
        combinations[item.combination_id] = item
    frozen_mcus, frozen_combinations = tuple(mcus.values()), tuple(combinations.values())
    validate_graph(frozen_mcus, frozen_combinations)
    audit = MCUOverrideRecord(
        operation_id=op.operation_id,
        kind=op.kind,
        payload_json=raw,
        reason=op.reason,
        actor=op.actor,
        occurred_at=op.occurred_at,
        parent_version_id=parent.version_id,
        previous_mcus=parent.mcus,
        previous_combinations=parent.combinations,
        before_graph_hash=canonical_hash(
            GraphContent(mcus=parent.mcus, combinations=parent.combinations)
        ),
        after_graph_hash=canonical_hash(
            GraphContent(mcus=frozen_mcus, combinations=frozen_combinations)
        ),
    )
    return _version(
        parent_version_id=parent.version_id,
        created_at=op.occurred_at,
        created_by=op.actor,
        mcus=frozen_mcus,
        combinations=frozen_combinations,
        overrides=(*parent.overrides, audit),
        source_reconciliation_hash=parent.source_reconciliation_hash,
    )
