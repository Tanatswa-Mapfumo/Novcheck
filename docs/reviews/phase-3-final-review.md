# Phase 3 independent review and closure

Scope: accepted Phase 2 base 558a22a through initial Phase 3 implementation 84a28a2.
The independent read-only reviewer found six Important findings, no Critical findings.
The original review ran Ruff, Pyright and 901 deterministic tests successfully;
passing tests did not conceal or excuse the reproductions below.

All reproductions and regression tests use recordings or httpx.MockTransport with
network blocked. Every fix was preceded by observed failing tests and followed by
the full verification gate before its separate commit.

| Finding | Reproduction / exact fix | Regression cases | Commit |
| --- | --- | --- | --- |
| 1. Credential echoes in rate diagnostics | Synthetic GitHub token echoed in X-RateLimit-Resource survived JSON-body redaction. Redact retained rate metadata using the resolved-secret mechanism. | 1: resolved credential header echo absent from diagnostics | fa1c4f8 |
| 2. Canonical collapse disguised by family labels | Nine family labels with only ZetaFlow text passed strategy/critic/coverage. Require distinct normalized texts, reject noun-only relationship terms and unchanged historical terms. Shared lexical guards do not claim semantic entailment. | 7: three strategist attacks, three optimistic-critic attacks, one normalized coverage-floor attack | 6ada468 |
| 3. Malformed values escape isolation | Infinite rate limit and huge Crossref year raised OverflowError. Validate finite/bounded rates; record PARSE_FAILURE; retain invalid-date chronology limitations and continue unrelated providers. | 7: five malformed rate numbers, huge Crossref year, multi-provider continuation | 6b92cf7 |
| 4. Provider metadata lost in hits | Publication dates and repository details were discarded after adapter parsing. Deep-copy provider-scoped metadata into ScreeningHit and persist it unchanged. No chronology decision added. | 1: OpenAlex/Crossref dates and GitHub timestamps/topics/license survive artifact model round-trip | 24c447e |
| 5. Final failed attempt loses cooldown | max_attempts=1 plus Retry-After:60 allowed next query after only six seconds. Persist per-provider cooldown independently of retry eligibility, trace it, and pace once. Invalid Retry-After is a safe parse failure. | 10: seconds/date/reset after exhaustion, six invalid values, provider-scoped retry with no double sleep | 4d490e9 |
| 6. Crossref Boolean bypass | sensor AND(relay) bypassed whitespace-split checks. Detect punctuation-delimited uppercase operators/proximity; reject unsupported constraints explicitly while preserving plain words. | 8: five operator forms rejected, three ordinary word forms preserved | cd3ffdc |

Review regression total: 34. Full corrected verification at 6ada468: 935 passed,
3 live deselected; Ruff clean, 138 files formatted, Pyright zero errors/warnings.
Independent clone at the same commit: 935 passed, 3 deselected; git diff --check
and clean status passed. Explicit opt-in live smoke suite: all three providers PASS.

## Follow-up review and final closure

The reviewer confirmed all six original findings closed at 6ada468, but identified
one new Important security regression: retained nested metadata object keys could
echo a resolved GitHub credential. JSON value redaction left keys unchanged.

A failing persisted-artifact regression reproduced the leak. e64bbb8 recursively
omits secret-bearing object keys before wire validation/metadata retention, preserving
safe sibling metadata and avoiding redacted-key collisions. The test checks the whole
serialized result and every persisted artifact, not only the license field.

Final independent read-only review at e64bbb8: all seven findings closed; no remaining
Important/Critical blockers or material regressions within Phase 3 scope. The reviewer
checked exact, embedded and nested-list secret-bearing keys and safe siblings.
Fresh reviewer checks: 936 passed, 3 live deselected; Ruff/Pyright/diff checks PASS.
No files, commits or live calls were made by the reviewer.

Final review regression total: 35. Worktree and independent clone full verification:
936 passed, 3 deselected, 939 collected. Explicit opt-in live smokes after the final
fix: three providers PASS in 3.62s. Review closure: PASS.

Other original-review safeguards held: complete family accounting, missing-provider
blockers, coverage floors, isolated critic context, hash-bound PASS revalidation,
explicit fixture continuation and one logical screening event per query/provider.

Remaining evaluation limitation: fixed metamorphic strategist recordings establish
validator stability, not contextual generation quality. Production model robustness,
historical-content verification, fusion, adaptive research, provenance and novelty
adjudication are not claimed. Phase 4 has not started.
