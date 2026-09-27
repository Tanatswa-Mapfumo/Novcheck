from datetime import date

from pydantic import Field, FiniteFloat, JsonValue

from novelty_harness.domain.enums import EvidenceFamily
from novelty_harness.domain.idea import NonBlankText
from novelty_harness.ports.models import SearchPage, SearchQuery, SearchResult, SourceRef
from novelty_harness.providers._base import HTTPSearchAdapter, WireModel, validate_wire
from novelty_harness.providers.errors import FailureCategory, provider_error
from novelty_harness.providers.http import HTTPResult
from novelty_harness.providers.registry import ProviderDescriptor
from novelty_harness.research.models import SearchIntent
from novelty_harness.research.provider_queries import CompiledProviderQuery


class OpenAlexCompiler:
    def compile(self, intent: SearchIntent, *, as_of: date) -> CompiledProviderQuery:
        if intent.evidence_family != EvidenceFamily.SCHOLARLY or intent.filters:
            raise provider_error(
                "openalex",
                FailureCategory.CAPABILITY_MISMATCH,
                "Only scholarly text screening without extra filters supported",
                intent.query_id,
            )
        return CompiledProviderQuery(
            query_id=intent.query_id,
            provider_name="openalex",
            evidence_family=intent.evidence_family,
            endpoint="https://api.openalex.org/works",
            method="GET",
            params={
                "search": intent.text,
                "filter": "to_publication_date:" + as_of.isoformat(),
                "per_page": 25,
                "cursor": "*",
            },
            compilation_notes=("Works text screening only; no semantic or citation expansion",),
        )


class Work(WireModel):
    id: NonBlankText
    title: str | None = None
    doi: str | None = None
    publication_date: str | None = None
    publication_year: int | None = None
    relevance_score: FiniteFloat | None = None
    authorships: list[JsonValue] = Field(default_factory=lambda: list[JsonValue]())
    abstract_inverted_index: dict[str, list[int]] | None = None


class WorksMeta(WireModel):
    next_cursor: str | None = None
    count: int = Field(ge=0)


class WorksResponse(WireModel):
    meta: WorksMeta
    results: list[Work]


class OpenAlexProvider(HTTPSearchAdapter):
    name = "openalex"
    compiler = OpenAlexCompiler()
    descriptor = ProviderDescriptor(
        name=name,
        evidence_families=frozenset({EvidenceFamily.SCHOLARLY}),
        search_capabilities=frozenset({"works-text", "publication-cutoff"}),
        auth_mode="optional-bearer",
        supports_pagination=True,
    )

    def parse(
        self, data: JsonValue, result: HTTPResult, query: SearchQuery, cutoff: date
    ) -> tuple[SearchPage, tuple[str, ...]]:
        wire = validate_wire(
            WorksResponse, data, provider=self.name, query_id=query.query_id, result=result
        )
        hits: list[SearchResult] = []
        notes: list[str] = []
        for rank, work in enumerate(wire.results, 1):
            published: date | None = None
            if work.publication_date:
                try:
                    published = date.fromisoformat(work.publication_date)
                except ValueError:
                    notes.append("Invalid publication date; chronology unresolved")
            if published is not None and published > cutoff:
                notes.append("Post-cutoff record omitted from screening results")
                continue
            if published is None:
                notes.append("Publication date unavailable; chronology unresolved")
            hits.append(
                SearchResult(
                    source=SourceRef(
                        provider_name=self.name,
                        provider_source_id=work.id,
                        title=work.title,
                        canonical_url=work.id,
                    ),
                    rank=rank,
                    metadata={
                        "doi": work.doi,
                        "publication_date": work.publication_date,
                        "publication_year": work.publication_year,
                        "authors": work.authorships,
                        "abstract_available": work.abstract_inverted_index is not None,
                        "provider_local_score": work.relevance_score,
                    },
                )
            )
        return SearchPage(results=hits, next_cursor=wire.meta.next_cursor, call=result.call), tuple(
            notes
        )
