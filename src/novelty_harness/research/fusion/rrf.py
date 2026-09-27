from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import ConfigDict, Field, FiniteFloat

from novelty_harness.domain.base import ContractModel
from novelty_harness.domain.idea import NonBlankText
from novelty_harness.ports.models import SourceRef
from novelty_harness.research.retrieval.models import RetrievalCandidate, RetrievalStrategy
from novelty_harness.runtime.tracing.hashing import canonical_hash


class FusedCandidate(ContractModel):
    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["fused-candidate-v1"] = "fused-candidate-v1"
    candidate_key: NonBlankText
    source_refs: tuple[SourceRef, ...]
    contributing_lists: tuple[NonBlankText, ...]
    rrf_score: FiniteFloat = Field(gt=0)
    best_local_rank: int = Field(ge=1)
    strategies: frozenset[RetrievalStrategy]
    providers: frozenset[NonBlankText]
    discoveries: tuple[RetrievalCandidate, ...]


def stream_identity(candidate: RetrievalCandidate) -> tuple[str, ...]:
    seed = candidate.seed_source
    return (
        candidate.provider_name,
        candidate.strategy.value,
        candidate.query_id or "",
        seed.provider_name if seed else "",
        seed.provider_source_id if seed else "",
    )


def reciprocal_rank_fusion(
    ranked_lists: Mapping[str, Sequence[RetrievalCandidate]], *, k: int = 60
) -> list[FusedCandidate]:
    if type(k) is not int or k <= 0:
        raise ValueError("RRF constant must be a positive integer")
    ranks: dict[str, dict[tuple[str, ...], int]] = {}
    list_names: dict[str, set[str]] = {}
    discoveries: dict[str, dict[str, RetrievalCandidate]] = {}
    objectives: set[tuple[str | None, str]] = set()
    for name, rows in ranked_lists.items():
        if not name.strip():
            raise ValueError("Ranked list identity cannot be blank")
        streams: set[tuple[str, ...]] = set()
        for raw in rows:
            candidate = RetrievalCandidate.model_validate(raw.model_dump())
            objectives.add((candidate.mcu_id, candidate.evidence_family.value))
            stream = stream_identity(candidate)
            streams.add(stream)
            key = candidate.candidate_key
            stream_ranks = ranks.setdefault(key, {})
            stream_ranks[stream] = min(
                stream_ranks.get(stream, candidate.local_rank), candidate.local_rank
            )
            list_names.setdefault(key, set()).add(name)
            discoveries.setdefault(key, {})[canonical_hash(candidate.model_dump(mode="json"))] = (
                candidate
            )
        if len(streams) > 1:
            raise ValueError("One ranked list must represent one provider/query/strategy run")
    if len(objectives) > 1:
        raise ValueError("Fusion cannot combine unrelated MCU/family objectives")
    fused: list[FusedCandidate] = []
    for key in sorted(ranks):
        observations = tuple(discoveries[key][h] for h in sorted(discoveries[key]))
        refs = {canonical_hash(c.source.model_dump(mode="json")): c.source for c in observations}
        fused.append(
            FusedCandidate(
                candidate_key=key,
                source_refs=tuple(refs[h] for h in sorted(refs)),
                contributing_lists=tuple(sorted(list_names[key])),
                rrf_score=sum(1 / (k + ranks[key][stream]) for stream in sorted(ranks[key])),
                best_local_rank=min(ranks[key].values()),
                strategies=frozenset(c.strategy for c in observations),
                providers=frozenset(c.provider_name for c in observations),
                discoveries=observations,
            )
        )
    return sorted(fused, key=lambda c: (-c.rrf_score, c.candidate_key))
