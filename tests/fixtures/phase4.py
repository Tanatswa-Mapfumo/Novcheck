"""Synthetic HTTP recordings; all Phase 4 domain components remain real."""

from datetime import date

import httpx

from novelty_harness.domain.assessment import AssessmentRecord
from novelty_harness.providers.crossref_pagination import CrossrefRetrievalProvider
from novelty_harness.providers.github_expansion import GitHubRetrievalProvider
from novelty_harness.providers.http import HTTPRuntime, RetryPolicy
from novelty_harness.providers.openalex_semantic import OpenAlexRetrievalProvider
from novelty_harness.providers.registry import ProviderRegistry
from novelty_harness.providers.semantic_scholar import SemanticScholarProvider
from novelty_harness.research.adaptive.stopping import StoppingPolicy
from tests.fixtures.phase1 import make_fixture
from tests.unit.providers.test_crossref import response as crossref_response
from tests.unit.providers.test_github import response as github_response
from tests.unit.providers.test_openalex import no_sleep
from tests.unit.providers.test_openalex import response as openalex_response


def registry(client, *, clock=None, retries=1, sleeper=no_sleep):
    runtime = HTTPRuntime(
        client,
        policy=RetryPolicy(max_attempts=retries),
        sleeper=sleeper,
        **({"clock": clock} if clock else {}),
    )
    result = ProviderRegistry()
    for cls in (
        OpenAlexRetrievalProvider,
        CrossrefRetrievalProvider,
        GitHubRetrievalProvider,
        SemanticScholarProvider,
    ):
        p = cls(runtime)
        result.register(p, p.descriptor, compiler=p.compiler)
    return result, runtime


def wire(request):
    if request.url.host == "api.openalex.org":
        data = openalex_response()
        data["meta"]["next_cursor"] = None
        if request.url.path.startswith("/works/W"):
            work = data["results"][0]
            work.update(
                id="https://openalex.org/" + request.url.path.rsplit("/", 1)[-1],
                referenced_works=["https://openalex.org/W100"],
                related_works=[],
            )
            return httpx.Response(200, json=work)
        if str(request.url.params.get("filter", "")).startswith("openalex:"):
            data["results"][0].update(
                id="https://openalex.org/W100",
                doi="https://doi.org/10.1234/predecessor",
                publication_date="1995-01-01",
            )
        return httpx.Response(200, json=data)
    if request.url.host == "api.crossref.org":
        return httpx.Response(200, json=crossref_response())
    if request.url.host == "api.github.com":
        data = github_response()
        if request.url.path.startswith("/repositories/"):
            repo = data["items"][0]
            repo["owner"] = {"id": 5, "login": "example", "type": "Organization"}
            return httpx.Response(200, json=repo)
        if request.url.path.startswith("/orgs/"):
            return httpx.Response(200, json=data["items"])
        return httpx.Response(200, json=data)
    paper = {
        "paperId": "a" * 40,
        "title": "Thermal feedback controller",
        "url": "https://www.semanticscholar.org/paper/" + "a" * 40,
        "externalIds": {"DOI": "10.1234/s2"},
        "year": 2001,
        "publicationDate": "2001-01-01",
        "authors": [{"authorId": "1", "name": "Example"}],
    }
    path = request.url.path
    if path.endswith("/references"):
        return httpx.Response(200, json={"data": [{"citedPaper": paper}]})
    if path.endswith("/citations"):
        return httpx.Response(200, json={"data": [{"citingPaper": paper}]})
    if "/paper/" in path and not path.endswith("/search"):
        return httpx.Response(200, json=paper)
    return httpx.Response(200, json={"data": [paper], "total": 1, "offset": 0})


def assessment():
    f = make_fixture()
    return AssessmentRecord(
        assessment_id="asm_research",
        request=f.request.model_copy(update={"as_of": date(2026, 9, 26)}),
        created_at=f.clock(),
        updated_at=f.clock(),
    )


def stop_policy():
    return StoppingPolicy(
        min_providers=2, min_mechanisms=2, convergence_rounds=2, max_new_candidates=0
    )
