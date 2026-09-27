from datetime import date

import pytest

from novelty_harness.research.models import SearchIntent
from novelty_harness.research.provider_queries import CompiledProviderQuery, compile_intent
from tests.unit.research.test_search_planning import plan_data


class StubCompiler:
    def compile(self, intent, *, as_of):
        intent.filters["mutated"] = True
        return CompiledProviderQuery(
            query_id=intent.query_id,
            provider_name="stub",
            evidence_family=intent.evidence_family,
            endpoint="https://stub.test/works",
            method="GET",
            params={"q": intent.text, "cutoff": as_of.isoformat()},
            compilation_notes=("Supported cutoff filter",),
        )


def test_compilation_is_reproducible_and_cannot_mutate_neutral_intent():
    intent = SearchIntent.model_validate(plan_data()["intents"][0])
    compiled = compile_intent(StubCompiler(), intent, as_of=date(2026, 9, 26))
    assert compiled.query_id == intent.query_id
    assert compiled.params["cutoff"] == "2026-09-26"
    assert not intent.filters
    assert CompiledProviderQuery.model_validate_json(compiled.model_dump_json()) == compiled


@pytest.mark.parametrize(
    "params,endpoint",
    [
        ({"api_key": "secret"}, "https://stub.test/works"),
        ({"q": "term"}, "https://stub.test/works?token=secret"),
        ({}, "https://user:secret@stub.test/works"),
        ({"nested": {"Authorization": "secret"}}, "https://stub.test/works"),
    ],
)
def test_compiled_artifacts_cannot_contain_credential_fields(params, endpoint):
    with pytest.raises(ValueError):
        CompiledProviderQuery(
            query_id="qry_1",
            provider_name="stub",
            evidence_family="SCHOLARLY",
            endpoint=endpoint,
            method="GET",
            params=params,
        )
