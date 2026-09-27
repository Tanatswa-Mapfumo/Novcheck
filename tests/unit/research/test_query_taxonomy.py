from novelty_harness.research.query_taxonomy import QueryFamily


def test_all_eleven_query_families_round_trip_as_distinct_categories():
    names = (
        "DIRECT_CANONICAL",
        "SYNONYM_ACRONYM",
        "FUNCTIONAL",
        "MECHANISM",
        "RELATIONSHIP",
        "OUTCOME_OBJECTIVE",
        "HISTORICAL_TERMINOLOGY",
        "ADJACENT_DOMAIN",
        "COMPONENT",
        "COMBINATION",
        "ENTITY_DISCOVERY",
    )
    assert {QueryFamily(name).value for name in names} == {item.value for item in QueryFamily}
