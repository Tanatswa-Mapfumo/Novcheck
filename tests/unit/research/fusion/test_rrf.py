import pytest

from novelty_harness.ports.models import SourceRef
from novelty_harness.research.fusion.rrf import reciprocal_rank_fusion
from tests.unit.research.retrieval.test_models import candidate


def ranked(key, rank=1, query="qry_control", **updates):
    return candidate(
        candidate_key=key,
        local_rank=rank,
        query_id=query,
        source=SourceRef(provider_name="openalex", provider_source_id=key),
        **updates,
    )


def test_exact_rank_arithmetic_across_independent_query_lists():
    lists = {
        "lexical": [ranked("a", 1), ranked("b", 2)],
        "semantic": [
            ranked("b", 1, "qry_other", strategy="SEMANTIC"),
            ranked("a", 2, "qry_other", strategy="SEMANTIC"),
        ],
    }
    result = reciprocal_rank_fusion(lists, k=60)
    assert [c.candidate_key for c in result] == ["a", "b"]
    assert all(c.rrf_score == pytest.approx(1 / 61 + 1 / 62) for c in result)
    assert result[0].best_local_rank == 1 and len(result[0].discoveries) == 2


def test_provider_score_scale_never_changes_fusion_order_or_scores():
    lists = {
        "first": [ranked("a", 1, provider_score=1e200), ranked("b", 2, provider_score=0.0001)],
        "second": [ranked("b", 1, "qry_second"), ranked("a", 2, "qry_second")],
    }
    changed = {
        name: [c.model_copy(update={"provider_score": -1e200}) for c in rows]
        for name, rows in lists.items()
    }
    assert [(c.candidate_key, c.rrf_score) for c in reciprocal_rank_fusion(lists)] == [
        (c.candidate_key, c.rrf_score) for c in reciprocal_rank_fusion(changed)
    ]


def test_duplicate_run_alias_and_pages_count_once_without_losing_discoveries():
    a = ranked("a")
    b = ranked("b", 26)
    result = reciprocal_rank_fusion({"original": [a], "duplicate": [a], "page2": [b]})
    assert {c.candidate_key: c.rrf_score for c in result} == {"a": 1 / 61, "b": 1 / 86}
    assert result[0].contributing_lists == ("duplicate", "original")


def test_repeated_document_within_one_list_does_not_double_count():
    result = reciprocal_rank_fusion({"one": [ranked("a", 2), ranked("a", 1)]})
    assert len(result) == 1 and result[0].rrf_score == 1 / 61


@pytest.mark.parametrize("k", [0, -1, True, 1.5])
def test_invalid_rank_constant_rejects(k):
    with pytest.raises(ValueError):
        reciprocal_rank_fusion({"one": [ranked("a")]}, k=k)


def test_stable_ties_and_objective_scope():
    first = reciprocal_rank_fusion({"b": [ranked("z", 1, "qry_z")], "a": [ranked("a")]})
    second = reciprocal_rank_fusion({"a": [ranked("a")], "b": [ranked("z", 1, "qry_z")]})
    assert [c.candidate_key for c in first] == [c.candidate_key for c in second] == ["a", "z"]
    with pytest.raises(ValueError):
        reciprocal_rank_fusion(
            {"one": [ranked("a")], "unrelated": [ranked("z", mcu_id="mcu_other")]}
        )
