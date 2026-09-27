# Phase 3 provider matrix

IMPLEMENTED means an adapter/compiler tested using synthetic recorded responses
and httpx.MockTransport, not guaranteed live availability or complete corpus coverage.
Descriptors model families, search capabilities, auth, pagination, full text and
citation capabilities independently. Registry presence never controls applicability.

| Provider | Family | Status | Auth | Query / pagination | Rate behavior | Full text / citations | Phase 3 limitations / later activation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OpenAlex | SCHOLARLY | IMPLEMENTED | Optional OPENALEX_API_KEY, bearer header | Works text search; publication cutoff; cursor; 25 results/page | 0.1s minimum spacing, response budget/reset headers and retry backoff | Text index may cover abstracts/full text; content retrieval and citation expansion not implemented | Provider-local relevance only; unknown dates remain uncertain; semantic search/citations deferred |
| Crossref | SCHOLARLY | IMPLEMENTED | Optional CROSSREF_MAILTO, resolved only for HTTP | query.bibliographic; publication cutoff; cursor; 25 rows | Conservative 0.2s spacing; rate/interval/concurrency headers; serialized calls | Bibliographic metadata only; full text/citation traversal not implemented | No Boolean/proximity equivalence to OpenAlex; missing DOI gets metadata-local hash, not canonical identity |
| GitHub | SOFTWARE | IMPLEMENTED | Optional GITHUB_TOKEN, bearer header | Repository keywords and creation cutoff; numeric page; 25 results | Search bucket; 6s anonymous / 2s authenticated spacing; primary/secondary 403 and 429 distinguished | No code search, repository-content fetching or citation engine | Archived repos retained; timestamps are not invention dates; current metadata needs historical verification; API version 2026-03-10 |
| Semantic Scholar | SCHOLARLY | PLANNED | To be specified in approved adapter phase | To be modelled explicitly | Not implemented | Not implemented | No adapter registered; future scholarly complement |
| EPO OPS | PATENT | PLANNED | To be specified | Patent syntax/coverage not implemented | Not implemented | Not implemented | PATENT stays plausible and BLOCKED_NO_PROVIDER |
| Brave / general web | GENERAL_WEB, PRODUCT, GREY_LITERATURE | PLANNED | To be specified | Not implemented | Not implemented | Not implemented | No web search or extraction yet |
| Standards providers | STANDARDS | PLANNED | To be specified | Not implemented | Not implemented | Not implemented | Applicability independent of access/provider availability |
| Government / regulatory providers | REGULATORY_GOVERNMENT | PLANNED | To be specified | Not implemented | Not implemented | Not implemented | Applicable branches explicitly blocked |
| Historical / archive providers | HISTORICAL_ARCHIVAL | PLANNED | To be specified | Not implemented | Not implemented | Not implemented | Historical terminology queries do not imply archive coverage |

Every intent is compiled separately for each registered family provider. Unsupported
filters/features produce CAPABILITY_MISMATCH, not silently dropped restrictions.
First-page screening never exhausts pages, fuses scores or counts independent evidence.
Duplicate DOIs may coexist as provider-local hits. Missing ecosystems and provider
failures appear in the coverage matrix; zero results never mean no prior art.

HTTP configuration defaults to 20s timeout, three attempts and 1s exponential
backoff. Only idempotent requests with transient failures retry. Retry-After (seconds
or HTTP date) and provider reset cooldowns are retained across logical requests,
including after retry exhaustion. Malformed rate metadata becomes an explicit parse
failure. 400/401/ordinary 403 do not
retry. Serial execution stays below concurrency limits. Every attempt retains query
identity, timestamp, safe request hash, response status, delays and rate snapshot.
No headers, error body, credential-bearing URL or raw transport exception is persisted.
Known resolved credential/email values are redacted from returned JSON and retained
rate header values before parsing/persistence. Provider-scoped metadata is retained
with secret-bearing object keys omitted recursively,
in screening hits, without cross-provider score comparison or chronology adjudication.
Fallbacks require explicit registry events; the executor does not silently substitute.
Health reports local configuration only, not an unperformed live probe.

Semantic applicability, strategy, criticism and revision use separately versioned
tasks over the abstract LLMProvider. The critic sees only CIR, MCUs, applicability
and the persisted plan. It never sees strategist call history/private context.
Its complete checklist and deterministic guards are required before PASS binding.
No production LLM adapter, calibrated confidence or novelty judgment exists.

## Operational coverage profile

standard-screening-v1 requires two distinct query families and one provider for each
plausible family, with at least as many distinct normalized query texts as the family
floor. Required query families and per-query inspection minima default
to none. Load a complete JSON CoveragePolicy with runtime/config/search.py; all floors
are configurable within the multi-query contract. They are operational floors, not
confidence thresholds. All planned query/provider pairs must succeed; retry failures
or incomplete GitHub responses degrade coverage even if some results are returned.
Exclusion needs explicit semantic rationale and input support; unsupported exclusions
remain UNRESOLVED. Textual grounding does not prove semantic incompatibility, so the
independent critic must review exclusions too.

## Official API references

Checked 2026-09-27; these are provider capabilities, not claims of corpus completeness:

- [OpenAlex authentication and rate metadata](https://help.openalex.org/api/authentication/)
- [OpenAlex text search](https://help.openalex.org/api/searching/)
- [OpenAlex supported paging](https://help.openalex.org/api/paging/)
- [Crossref access and rate limits](https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/)
- [Crossref query/filter reference](https://github.com/CrossRef/rest-api-doc)
- [GitHub repository search](https://docs.github.com/en/rest/search/search#search-repositories)
- [GitHub rate-limit metadata](https://docs.github.com/en/rest/using-the-rest-api/rate-limits-for-the-rest-api)
