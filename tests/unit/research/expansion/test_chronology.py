from datetime import UTC, date, datetime

import pytest

from novelty_harness.research.expansion.chronology import (
    CandidateChronology,
    assess_temporal,
    capture_chronology,
)
from tests.unit.research.retrieval.test_models import candidate


@pytest.mark.parametrize(
    "published,expected", [("1999-01-01", True), ("2020-01-01", True), ("2020-01-02", False)]
)
def test_cutoff_preserves_post_cutoff_context_but_excludes_historical_negation(published, expected):
    c = candidate(raw_metadata={"publication_date": published})
    chronology = capture_chronology(c)
    assessment = assess_temporal(chronology, as_of=date(2020, 1, 1))
    assert assessment.predates_cutoff is expected
    assert assessment.decisive_date_field == "publication_date"
    assert c.raw_metadata["publication_date"] == published


def test_repo_creation_not_public_release_and_priority_not_publication():
    chronology = CandidateChronology(
        repository_created_at=datetime(1990, 1, 1, tzinfo=UTC),
        first_release_date=date(2021, 1, 1),
        patent_priority_date=date(1980, 1, 1),
        patent_publication_date=date(2022, 1, 1),
    )
    result = assess_temporal(chronology, as_of=date(2020, 1, 1))
    assert result.predates_cutoff is False and result.decisive_date_field == "first_release_date"
    assert chronology.patent_priority_date == date(1980, 1, 1)
    assert (
        assess_temporal(
            CandidateChronology(patent_priority_date=date(1980, 1, 1)), as_of=date(2020, 1, 1)
        ).predates_cutoff
        is None
    )


def test_partial_crossref_dates_and_year_do_not_become_guessed_days():
    c = candidate(
        raw_metadata={"date_parts": {"published": {"date-parts": [[1999]]}}, "year": 1999}
    )
    chronology = capture_chronology(c)
    result = assess_temporal(chronology, as_of=date(2020, 1, 1))
    assert result.predates_cutoff is None and result.ambiguity
    assert chronology.publication_date is None


def test_later_seed_does_not_overwrite_earlier_predecessor_date():
    seed = candidate(raw_metadata={"publication_date": "2022-01-01"}).source
    old = candidate(
        strategy="CITATION_BACKWARD",
        seed_source=seed,
        raw_metadata={"publication_date": "1995-01-01"},
    )
    assert assess_temporal(capture_chronology(old), as_of=date(2000, 1, 1)).predates_cutoff is True


def test_github_date_types_retained_separately_and_naive_timestamp_rejected():
    chronology = capture_chronology(
        candidate(
            raw_metadata={
                "created_at": "2010-01-01T00:00:00Z",
                "first_release_date": "2012-03-04",
                "updated_at": "2025-01-01T00:00:00Z",
            }
        )
    )
    assert chronology.repository_created_at == datetime(2010, 1, 1, tzinfo=UTC)
    assert chronology.first_release_date == date(2012, 3, 4)
    with pytest.raises(ValueError):
        CandidateChronology(repository_created_at=datetime(2010, 1, 1))
