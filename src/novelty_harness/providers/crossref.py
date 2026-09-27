from datetime import date

from pydantic import Field, FiniteFloat, JsonValue

from novelty_harness.domain.enums import EvidenceFamily
from novelty_harness.ports.models import SearchPage, SearchQuery, SearchResult, SourceRef
from novelty_harness.providers._base import HTTPSearchAdapter, WireModel, validate_wire
from novelty_harness.providers.errors import FailureCategory, provider_error
from novelty_harness.providers.http import HTTPResult, HTTPRuntime
from novelty_harness.providers.registry import CredentialRef, ProviderDescriptor
from novelty_harness.research.models import SearchIntent
from novelty_harness.research.provider_queries import CompiledProviderQuery
from novelty_harness.runtime.tracing.hashing import canonical_hash


class CrossrefCompiler:
    def compile(self, intent: SearchIntent, *, as_of: date) -> CompiledProviderQuery:
        if (
            intent.evidence_family != EvidenceFamily.SCHOLARLY
            or intent.filters
            or any(t in {"AND", "OR", "NOT"} or t.startswith("NEAR/") for t in intent.text.split())
        ):
            raise provider_error(
                "crossref",
                FailureCategory.CAPABILITY_MISMATCH,
                "Bibliographic matching does not reproduce Boolean/proximity/full-text intent",
                intent.query_id,
            )
        return CompiledProviderQuery(
            query_id=intent.query_id,
            provider_name="crossref",
            evidence_family=intent.evidence_family,
            endpoint="https://api.crossref.org/works",
            method="GET",
            params={
                "query.bibliographic": intent.text,
                "filter": "until-pub-date:" + as_of.isoformat(),
                "rows": 25,
                "cursor": "*",
            },
            compilation_notes=("Bibliographic matching, not OpenAlex Boolean/full-text semantics",),
        )


class DateParts(WireModel):
    parts: list[list[int]] = Field(alias="date-parts")


class CrossrefWork(WireModel):
    doi: str | None = Field(default=None, alias="DOI")
    title: list[str] = Field(default_factory=lambda: list[str]())
    type: str | None = None
    published: DateParts | None = None
    published_print: DateParts | None = Field(default=None, alias="published-print")
    published_online: DateParts | None = Field(default=None, alias="published-online")
    url: str | None = Field(default=None, alias="URL")
    publisher: str | None = None
    container: list[str] = Field(default_factory=lambda: list[str](), alias="container-title")
    score: FiniteFloat | None = None


class Message(WireModel):
    items: list[CrossrefWork]
    next_cursor: str | None = Field(default=None, alias="next-cursor")


class CrossrefResponse(WireModel):
    status: str
    message: Message


class CrossrefProvider(HTTPSearchAdapter):
    name = "crossref"
    compiler = CrossrefCompiler()
    descriptor = ProviderDescriptor(
        name=name,
        evidence_families=frozenset({EvidenceFamily.SCHOLARLY}),
        search_capabilities=frozenset({"bibliographic", "publication-cutoff"}),
        auth_mode="optional-mailto",
        supports_pagination=True,
    )

    def __init__(self, runtime: HTTPRuntime, *, mailto: CredentialRef | None = None) -> None:
        super().__init__(runtime)
        self.mailto = mailto

    def min_interval(self) -> float:
        return 0.2

    def request_params(
        self, params: dict[str, str | int | float | bool]
    ) -> dict[str, str | int | float | bool]:
        email = self.mailto.resolve() if self.mailto else None
        return {**params, "mailto": email} if email else params

    def parse(
        self, data: JsonValue, result: HTTPResult, query: SearchQuery, cutoff: date
    ) -> tuple[SearchPage, tuple[str, ...]]:
        wire = validate_wire(
            CrossrefResponse, data, provider=self.name, query_id=query.query_id, result=result
        )
        if wire.status != "ok":
            raise provider_error(
                self.name,
                FailureCategory.PARSE_FAILURE,
                "Crossref status not ok",
                query.query_id,
                result.call,
            )
        hits: list[SearchResult] = []
        notes: list[str] = []
        for rank, work in enumerate(wire.message.items, 1):
            dates: list[date] = []
            for field in (work.published, work.published_online, work.published_print):
                if field is None:
                    continue
                for parts in field.parts:
                    try:
                        if not 1 <= len(parts) <= 3:
                            raise ValueError("invalid date parts")
                        dates.append(
                            date(
                                parts[0],
                                parts[1] if len(parts) > 1 else 1,
                                parts[2] if len(parts) > 2 else 1,
                            )
                        )
                        if len(parts) < 3:
                            notes.append("Partial publication date; exact chronology unresolved")
                    except ValueError:
                        notes.append("Invalid publication date; chronology unresolved")
            if dates and min(dates) > cutoff:
                notes.append("Post-cutoff record omitted")
                continue
            if not dates:
                notes.append("Publication chronology unavailable")
            if not work.doi:
                notes.append("Missing DOI; metadata hash is a provider-local identifier only")
            if not work.title:
                notes.append("Missing title")
            hits.append(
                SearchResult(
                    source=SourceRef(
                        provider_name=self.name,
                        provider_source_id=work.doi
                        or "metadata_" + canonical_hash(work.model_dump(mode="json")),
                        title=work.title[0] if work.title else None,
                        canonical_url=work.url,
                    ),
                    rank=rank,
                    metadata={
                        "doi": work.doi,
                        "type": work.type,
                        "publisher": work.publisher,
                        "container": list[JsonValue](work.container),
                        "publication_date": min(dates).isoformat() if dates else None,
                        "provider_local_score": work.score,
                    },
                )
            )
        return SearchPage(
            results=hits, next_cursor=wire.message.next_cursor, call=result.call
        ), tuple(notes)
