import json
from pathlib import Path

import httpx

from novelty_harness.research.critique import bind_review
from tests.fixtures.phase3 import planning_response
from tests.fixtures.phase4 import wire
from tests.unit.providers.test_openalex import response
from tests.unit.research.test_search_critique import critique
from tests.unit.research.test_strategist import build

CASES = json.loads(Path(__file__).with_name("cases.json").read_text())


async def reviewed_case(case):
    data = planning_response()
    for q in data["intents"]:
        if q["mcu_id"] == "mcu_control" and q["query_family"] == "DIRECT_CANONICAL":
            q["text"] = case["input"]
    plan, _ = await build(data)
    review, _ = await critique(plan)
    return bind_review(plan, review)


def recording(case):
    def respond(request):
        host = request.url.host
        if host == "api.openalex.org":
            if request.url.path.startswith("/works/W"):
                work = response()["results"][0]
                work.update(
                    id="https://openalex.org/" + request.url.path.rsplit("/", 1)[-1],
                    referenced_works=["https://openalex.org/W101"]
                    if case["case_id"] == "mechanism"
                    else [],
                    related_works=[],
                )
                return httpx.Response(200, json=work)
            params = request.url.params
            graph = str(params.get("filter", "")).startswith("openalex:")
            semantic = "search.semantic" in params
            text = str(params.get("search.semantic", params.get("search", "")))
            hit = (
                case["case_id"] == "canonical"
                and not semantic
                and not graph
                and "cites:" not in str(params.get("filter", ""))
                or case["case_id"] == "paraphrase"
                and semantic
                or case["case_id"] == "mechanism"
                and graph
                or case["case_id"] == "cross_domain"
                and "process instrumentation" in text
                or case["case_id"] == "translated"
                and "La mesure" in text
            )
            seed = (
                case["case_id"] == "mechanism"
                and not semantic
                and not graph
                and "cites:" not in str(params.get("filter", ""))
            )
            data = response()
            data["meta"]["next_cursor"] = None
            if hit:
                data["results"][0].update(
                    id="https://openalex.org/W101",
                    doi="https://doi.org/10.1234/known",
                    publication_date="1990-01-01",
                )
            elif seed:
                data["results"][0].update(
                    id="https://openalex.org/W500",
                    doi="https://doi.org/10.1234/later",
                    publication_date="2020-01-01",
                )
            else:
                data["results"] = []
            return httpx.Response(200, json=data)
        result = wire(request)
        data = result.json()
        if host == "api.semanticscholar.org" and case["case_id"] == "renamed":
            paper = {
                "paperId": "b" * 40,
                "title": "Known thermal controller",
                "externalIds": {"DOI": "10.1234/known"},
                "publicationDate": "1990-01-01",
                "authors": [],
            }
            return httpx.Response(
                200,
                json={"data": [paper], "offset": 0, "total": 1}
                if request.url.path.endswith("/search")
                else {"data": []},
            )
        if host == "api.crossref.org":
            data["message"]["items"] = []
        elif host == "api.github.com":
            data["items"] = []
        else:
            data = {"data": [], "offset": 0, "total": 0}
        return httpx.Response(200, json=data)

    return respond
