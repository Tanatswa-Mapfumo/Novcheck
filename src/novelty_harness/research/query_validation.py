from collections.abc import Sequence

from novelty_harness.research.models import SearchIntent
from novelty_harness.research.query_taxonomy import QueryFamily


def normalized_query_text(text: str) -> str:
    return " ".join(text.casefold().split())


def distinct_query_texts(queries: Sequence[SearchIntent]) -> set[str]:
    return {normalized_query_text(q.text) for q in queries}


def terms_add_perspective(query: SearchIntent, canonical_queries: Sequence[SearchIntent]) -> bool:
    # This lexical guard rejects relabelled nouns; semantic faithfulness remains the critic's job.
    terms = (
        query.relationship_terms
        if query.query_family == QueryFamily.RELATIONSHIP
        else query.historical_terms
    )
    unchanged_words = {word for c in query.concepts for word in normalized_query_text(c).split()}
    if query.query_family == QueryFamily.HISTORICAL_TERMINOLOGY:
        unchanged_words.update(
            word for q in canonical_queries for word in normalized_query_text(q.text).split()
        )
    return (
        bool(terms)
        and all(normalized_query_text(t) in normalized_query_text(query.text) for t in terms)
        and any(set(normalized_query_text(t).split()) - unchanged_words for t in terms)
    )
