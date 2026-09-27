from datetime import UTC, datetime

import pytest

from novelty_harness.domain.enums import EvidenceFamily
from novelty_harness.ports.models import ProviderCallMetadata, SourceRef
from novelty_harness.research.retrieval.models import (
    RetrievalBatch,
    RetrievalCandidate,
    RetrievalMechanism,
    RetrievalStrategy,
    mechanism_for,
)


def candidate(**updates):
    data = dict(
        candidate_key="openalex:W1",
        source=SourceRef(provider_name="openalex", provider_source_id="W1"),
        mcu_id="mcu_control",
        evidence_family=EvidenceFamily.SCHOLARLY,
        provider_name="openalex",
        strategy="LEXICAL",
        query_id="qry_control",
        local_rank=1,
        provider_score=4.2,
        discovered_at=datetime(2026, 9, 27, tzinfo=UTC),
    )
    return RetrievalCandidate.model_validate({**data, **updates})


def call(provider="openalex"):
    now = datetime(2026, 9, 27, tzinfo=UTC)
    return ProviderCallMetadata(
        provider_name=provider,
        started_at=now,
        finished_at=now,
        request_hash="request_hash",
        status="SUCCESS",
    )


def test_final_shape_retains_identity_rank_local_score_seed_and_round_trip():
    seed = SourceRef(provider_name="openalex", provider_source_id="W0")
    c = candidate(strategy="CITATION_BACKWARD", query_id=None, seed_source=seed)
    batch = RetrievalBatch(
        strategy=c.strategy, provider_name=c.provider_name, candidates=[c], call=call()
    )
    assert RetrievalBatch.model_validate_json(batch.model_dump_json()) == batch
    assert c.seed_source == seed
    assert c.local_rank == 1 and c.provider_score == 4.2
    assert c.source.provider_source_id == "W1"
    with pytest.raises(ValueError):
        c.local_rank = 2


@pytest.mark.parametrize(
    "updates",
    [
        {"candidate_key": " "},
        {"local_rank": 0},
        {"provider_name": ""},
        {"discovered_at": datetime(2026, 9, 27)},
        {"provider_score": float("nan")},
        {"provider_score": float("inf")},
        {"strategy": "NOVELTY"},
        {"strategy": "CITATION_FORWARD", "query_id": None},
        {"confidence": 0.99},
    ],
)
def test_untrusted_candidate_fields_reject(updates):
    with pytest.raises(ValueError):
        candidate(**updates)


@pytest.mark.parametrize("defect", ["duplicate", "provider", "strategy", "call"])
def test_batch_rejects_identity_inconsistency(defect):
    c = candidate()
    data = dict(strategy=c.strategy, provider_name=c.provider_name, candidates=[c], call=call())
    if defect == "duplicate":
        data["candidates"] = [c, c]
    elif defect == "call":
        data["call"] = call("crossref")
    else:
        data[defect if defect == "strategy" else "provider_name"] = (
            "SEMANTIC" if defect == "strategy" else "crossref"
        )
    with pytest.raises(ValueError):
        RetrievalBatch.model_validate(data)


def test_perspectives_do_not_manufacture_retrieval_mechanism_diversity():
    assert len(RetrievalStrategy) == 9
    assert {
        mechanism_for(s)
        for s in [
            RetrievalStrategy.LEXICAL,
            RetrievalStrategy.RELATIONAL,
            RetrievalStrategy.HISTORICAL_TERM,
            RetrievalStrategy.ADJACENT_DOMAIN,
        ]
    } == {RetrievalMechanism.TEXT_SEARCH}
    assert mechanism_for(RetrievalStrategy.SEMANTIC) != mechanism_for(RetrievalStrategy.LEXICAL)


def test_equal_provider_scores_are_retained_without_shared_probability_semantics():
    oa = candidate(provider_score=0.9)
    s2 = candidate(
        candidate_key="s2:P1",
        provider_name="semantic_scholar",
        source=SourceRef(provider_name="semantic_scholar", provider_source_id="P1"),
        provider_score=0.9,
    )
    assert oa.provider_score == s2.provider_score
    assert oa.candidate_key != s2.candidate_key
    assert "confidence" not in oa.model_dump() and "novelty" not in s2.model_dump()
