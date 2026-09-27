# Phase 4 independent review and resolution

Reviewed range: `da34f36..a8d48a3`. The independent reviewer considered all
31 acceptance gates, made no file/index/HEAD changes and spawned no agents.
Assessment: **With fixes**, seven Important findings, no Critical or Minor findings.
The separate deployed OpenAlex semantic-filter correction is commit `7e09d7c`.

## Important findings

| Finding | Reproduced problem | Author ruling and exact correction |
| --- | --- | --- |
| 1. Deferred neighborhoods | A new top candidate W100 was never expanded, but the depth cap removed its actions and stopping counted it explored. | Agree. Track required and successfully completed neighborhoods separately. Record depth-deferred neighborhoods in branch artifacts. Unexplored major neighborhoods prevent SATURATED; configured depth is not silently increased. |
| 2. Last logical round | With max_deep_search_rounds=1, one round was charged but its physical requests were refused. | Agree. Round admission charges once; per-wire guards no longer reapply that already reserved logical-round limit. Call/document/time limits still apply to every attempt and hydration. |
| 3. Elapsed deadline | Retry-After=86400 caused an 86400-second wait under a two-second budget. | Agree. Cap pacing/cooldown waits at the remaining deadline and bound in-flight requests with asyncio and HTTP timeouts. Deadline expiry is BUDGET_STOPPED with safe attempt records. |
| 4. Hostile dates | Crossref date-parts=[[2**100,1,1]] raised OverflowError and crashed other branches. | Agree. Catch invalid/overflowing full dates and retain original metadata with unknown chronology. Other providers continue. |
| 5. Opaque IDs | An arbitrary provider-local ID shaped like a DOI merged with Crossref's explicit DOI. | Agree. Only explicit DOI fields or Crossref's documented DOI namespace establish DOI identity. Native OpenAlex work and Semantic Scholar paper IDs are schema-validated before candidate admission. |
| 6. Hydration binding | A W100 reference was hydrated as W999 and recorded as a complete seed relationship. | Agree. Normalize hydrated IDs and reject backward/related results outside the selected reference set as PARSE_FAILURE. |
| 7. Missing edges/ranks | A null S2 edge followed by a valid edge became rank 1 and a complete batch; subsequent offsets used surviving counts. | Agree. Preserve wire positions, record consumed rank_span, advance pagination by that span and mark missing records explicitly incomplete/access-limited. |

All seven findings were reproduced with deterministic, network-blocked tests before
their fixes. `tests/adversarial/test_phase4_review_regressions.py` includes 11 cases:
the eight initial reproductions (both OpenAlex hydration directions), two additional
malformed-native-ID RED-to-GREEN cases, and an in-flight cancellation check.
The latter was added after the deadline fix; temporarily disabling its production
safeguard for an additional RED demonstration was rejected by the tool safety guard.
The safeguard was not removed. No permission override was needed to finish.
All 11 cases pass; the final full verification results are in the completion report.

There was one author fix pass, not a second independent review. No Important
finding remains open after regression and full-suite verification.

## Rulings and costs

- Required/deferred exploration is kept truthful; cost: bounded runs can remain
  inconclusive instead of saturated when a new major neighborhood needs deeper work.
- Logical-round and physical-request admission are separate; cost: two explicit
  budget boundaries, without extra retries or quota allowances.
- Deadlines bound waits and in-flight work; cost: cancellation can retain only a
  safe failed-attempt record rather than a provider response.
- Invalid dates remain unknown; cost: no historical eligibility from those dates
  until later source verification.
- Opaque IDs are not global identity; cost: conservative candidate duplicates
  remain possible until explicit shared identifiers are available.
- Hydration mismatches are access/parse failures; cost: faulty responses cannot
  supply an expansion path or convergence credit.
- Missing graph targets retain wire rank gaps; cost: incomplete graph access blocks
  convergence even when other candidates from the page remain usable.

## Declined-to-judge rulings

- Phase 5+ source truth, provenance, support, equivalence and verdict intelligence:
  uphold deferral; cost: the accepted end-to-end evidence/findings remain synthetic.
- Automated translation and empirical live retrieval calibration: uphold deferral;
  cost: translated-query hooks and a controlled benchmark are not language coverage
  or production retrieval-quality claims.
- Ongoing OpenAlex semantic-filter patch, outside the review range: author-owned
  verification completed with recorded regression and opt-in live smoke; cost:
  provider-side year filtering is coarse and exact eligibility remains local.

The reviewer used read-only in-memory probes and mock HTTP responses, and checked
`git diff --check da34f36..a8d48a3`. It did not rerun the full suite. The implementer
ran full verification in the implementation worktree and an independent local clone.
