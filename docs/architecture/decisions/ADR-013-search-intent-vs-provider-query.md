# ADR-013: Neutral intents, compiled queries and provider boundaries

Status: Accepted for Phase 3 implementation

ResearchPlan (research-plan-v1) is a new versioned artifact rather than a silent
reinterpretation of the accepted legacy SearchPlan. The legacy contract remains a
projection for the Phase 1 slice. Rich plans, applicability, reviews and coverage
are persisted separately with explicit kinds. PASS reviews bind canonical hashes.

Semantic planning uses the abstract LLMProvider/validated SemanticRunner only.
Provider compilers translate neutral intent into supported request parameters;
unsupported constraints fail explicitly. Provider-specific syntax never flows
back into the planner. HTTP adapters implement the accepted async SearchProvider.
httpx is the single new runtime dependency, needed for async HTTP and MockTransport.
The earlier Phase 1 whole-production HTTP prohibition is narrowed only to permit
httpx inside the explicit providers package. All other SDK/network prohibitions
remain, and no domain, research, orchestration or reporting module may import httpx.

Retries are bounded, idempotent-only and explicit. Safe attempt records omit raw
headers, bodies, URLs with queries and exception messages. Credentials are resolved
from named environment references at request time, not in persisted queries.
Requests are serialized and paced per provider; Retry-After/reset metadata is
honored. Provider-local ranks/scores remain scoped, not comparable across providers.

API documentation checked on 2026-09-27: OpenAlex authentication and paging,
Crossref REST access/query documentation, and GitHub REST repository-search docs.
OpenAlex supports keyless basic use and a maximum per_page of 100; GitHub's current
documented API version is 2026-03-10. Adapter specifics are documented in the matrix.
