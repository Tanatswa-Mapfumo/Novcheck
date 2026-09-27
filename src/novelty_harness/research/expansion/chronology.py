import re
from datetime import date, datetime
from typing import Literal

from pydantic import ConfigDict

from novelty_harness.domain.base import ContractModel, UTCDateTime
from novelty_harness.research.retrieval.models import RetrievalCandidate


class CandidateChronology(ContractModel):
    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["candidate-chronology-v1"] = "candidate-chronology-v1"
    publication_date: date | None = None
    first_public_version: date | None = None
    repository_created_at: UTCDateTime | None = None
    first_release_date: date | None = None
    patent_priority_date: date | None = None
    patent_publication_date: date | None = None
    product_launch_date: date | None = None
    archive_capture_date: date | None = None
    ambiguity: tuple[str, ...] = ()


class TemporalAssessment(ContractModel):
    model_config = ConfigDict(frozen=True)
    contract_kind: Literal["temporal-assessment-v1"] = "temporal-assessment-v1"
    as_of: date
    predates_cutoff: bool | None
    decisive_date_field: str | None
    ambiguity: tuple[str, ...] = ()


PUBLIC_DATE_FIELDS = (
    "publication_date",
    "first_public_version",
    "first_release_date",
    "patent_publication_date",
    "product_launch_date",
    "archive_capture_date",
)


def capture_chronology(candidate: RetrievalCandidate) -> CandidateChronology:
    data = candidate.raw_metadata
    dates: dict[str, date | None] = {}
    ambiguity: list[str] = [
        "Provider metadata chronology is provisional; public content is not verified"
    ]
    for field in (*PUBLIC_DATE_FIELDS, "patent_priority_date"):
        raw = data.get(field)
        if field == "publication_date" and raw is None:
            raw = data.get("publicationDate")
        parsed: date | None = None
        if isinstance(raw, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            try:
                parsed = date.fromisoformat(raw)
            except ValueError:
                pass
        if raw is not None and parsed is None:
            ambiguity.append(f"{field}: incomplete or invalid date")
        dates[field] = parsed
    created: datetime | None = None
    raw_created = data.get("repository_created_at", data.get("created_at"))
    if isinstance(raw_created, str):
        try:
            timestamp = datetime.fromisoformat(raw_created)
            if timestamp.tzinfo is not None and timestamp.utcoffset() is not None:
                created = timestamp
        except ValueError:
            pass
    if raw_created is not None and created is None:
        ambiguity.append("repository_created_at: incomplete or timezone missing")
    if dates["publication_date"] is None and ("year" in data or "date_parts" in data):
        ambiguity.append(
            "Incomplete bibliographic dates retained in raw metadata without guessed days"
        )
    return CandidateChronology.model_validate(
        {**dates, "repository_created_at": created, "ambiguity": tuple(ambiguity)}
    )


def assess_temporal(chronology: CandidateChronology, *, as_of: date) -> TemporalAssessment:
    dates = [
        (value, field)
        for field in PUBLIC_DATE_FIELDS
        if isinstance(value := getattr(chronology, field), date)
    ]
    ambiguity = list(chronology.ambiguity)
    if chronology.repository_created_at or chronology.patent_priority_date:
        ambiguity.append("Creation/priority dates do not establish public disclosure")
    if not dates:
        return TemporalAssessment(
            as_of=as_of,
            predates_cutoff=None,
            decisive_date_field=None,
            ambiguity=tuple([*ambiguity, "No complete public-disclosure date"]),
        )
    decisive, field = min(dates)
    return TemporalAssessment(
        as_of=as_of,
        predates_cutoff=decisive <= as_of,
        decisive_date_field=field,
        ambiguity=tuple(ambiguity),
    )
