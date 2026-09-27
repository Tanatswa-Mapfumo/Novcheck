from datetime import date
from urllib.parse import parse_qs, urlsplit

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

API_VERSION = "2026-03-10"
ENDPOINT = "https://api.github.com/search/repositories"


class GitHubCompiler:
    def compile(self, intent: SearchIntent, *, as_of: date) -> CompiledProviderQuery:
        if (
            intent.evidence_family != EvidenceFamily.SOFTWARE
            or intent.filters
            or ":" in intent.text
            or len(intent.text) > 256
        ):
            raise provider_error(
                "github",
                FailureCategory.CAPABILITY_MISMATCH,
                "Only repository keyword screening supported; code search/qualifiers deferred",
                intent.query_id,
            )
        return CompiledProviderQuery(
            query_id=intent.query_id,
            provider_name="github",
            evidence_family=intent.evidence_family,
            endpoint=ENDPOINT,
            method="GET",
            params={
                "q": intent.text + " created:<=" + as_of.isoformat(),
                "per_page": 25,
                "page": 1,
            },
            headers_profile="github-rest-" + API_VERSION,
            compilation_notes=(
                "Repository creation/update dates are not invention dates",
                "Current metadata requires later historical-content verification",
            ),
        )


class Repository(WireModel):
    id: int = Field(gt=0)
    full_name: NonBlankText
    html_url: NonBlankText
    description: str | None = None
    topics: list[str] = Field(default_factory=lambda: list[str]())
    created_at: str | None = None
    updated_at: str | None = None
    archived: bool = False
    default_branch: str | None = None
    license: dict[str, JsonValue] | None = None
    score: FiniteFloat | None = None


class RepositoriesResponse(WireModel):
    total_count: int = Field(ge=0)
    incomplete_results: bool
    items: list[Repository]


class GitHubProvider(HTTPSearchAdapter):
    name = "github"
    compiler = GitHubCompiler()
    descriptor = ProviderDescriptor(
        name=name,
        evidence_families=frozenset({EvidenceFamily.SOFTWARE}),
        search_capabilities=frozenset({"repository-keywords", "repository-creation-cutoff"}),
        auth_mode="optional-bearer",
        supports_pagination=True,
    )

    def min_interval(self) -> float:
        return 2 if self.credential and self.credential.resolve() else 6

    def headers(self) -> dict[str, str]:
        return {
            **super().headers(),
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": API_VERSION,
        }

    def apply_cursor(self, params: dict[str, str | int | float | bool], cursor: str | None) -> None:
        if cursor is not None and (not cursor.isdecimal() or not 1 <= int(cursor) <= 40):
            raise provider_error(self.name, FailureCategory.BAD_REQUEST, "Invalid repository page")
        params["page"] = int(cursor) if cursor else 1

    def parse(
        self, data: JsonValue, result: HTTPResult, query: SearchQuery, cutoff: date
    ) -> tuple[SearchPage, tuple[str, ...]]:
        wire = validate_wire(
            RepositoriesResponse, data, provider=self.name, query_id=query.query_id, result=result
        )
        notes: list[str] = []
        if wire.incomplete_results:
            notes.append("Incomplete provider result set")
        hits: list[SearchResult] = []
        for rank, repo in enumerate(wire.items, 1):
            if repo.created_at is not None:
                try:
                    created = date.fromisoformat(repo.created_at[:10])
                except ValueError:
                    created = None
                if created is not None and created > cutoff:
                    notes.append("Post-cutoff repository omitted")
                    continue
                if created is None:
                    notes.append("Invalid repository creation chronology")
            else:
                notes.append("Repository creation chronology unavailable")
            hits.append(
                SearchResult(
                    source=SourceRef(
                        provider_name=self.name,
                        provider_source_id=str(repo.id),
                        title=repo.full_name,
                        canonical_url=repo.html_url,
                    ),
                    rank=rank,
                    snippet=repo.description,
                    metadata={
                        "topics": list[JsonValue](repo.topics),
                        "created_at": repo.created_at,
                        "updated_at": repo.updated_at,
                        "archived": repo.archived,
                        "default_branch": repo.default_branch,
                        "license": repo.license,
                        "provider_local_score": repo.score,
                        "api_version": API_VERSION,
                    },
                )
            )
        next_cursor: str | None = None
        link = result.response.links.get("next", {}).get("url")
        if link:
            parts = urlsplit(link)
            page = parse_qs(parts.query).get("page", [""])[0]
            if (
                parts.netloc == "api.github.com"
                and parts.path == "/search/repositories"
                and page.isdecimal()
            ):
                next_cursor = page
            else:
                notes.append("Invalid next-page metadata ignored")
        return SearchPage(results=hits, next_cursor=next_cursor, call=result.call), tuple(notes)
