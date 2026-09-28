# Phase 6 Contract Consolidation Plan

**Branch:** `phase-6-evidence-verification`
**Reviewed commit:** `75cee5e926b27a2ae695c7ad37db2eedc6404a6f`
**Gate 30:** FAIL
**Open findings:** F02, F03, F06, F07, F10, N02
**Closed and to preserve:** F01, F04, F05, F08, F09, N01, F11, M01
**Phase 7:** BLOCKED

## Why this is a consolidation, not another patch round

The remaining findings all arise because downstream code can still construct semantically inconsistent but schema-valid objects.

Round 3 should therefore replace caller-asserted semantic state with **derived canonical state** at five boundaries:

1. cited disclosure chronology;
2. evidence context completeness;
3. verification aggregate state;
4. verified classification/graph projection;
5. semantic edge identity vs observation history.

Do not redesign unrelated Phase 6 behavior.

## Model policy

Use **GPT-6 Sol High/Max as the primary implementation model** for this consolidation.

Do not use DeepSeek as the semantic implementation owner for these changes.

After implementation, use a **fresh independent GPT-6 Sol High/Max session** for Gate 30 review.

## Consolidated architecture

```text
Evidence Source + Exact Version
          │
          ▼
Authoritative Disclosure Record
          │
          ▼
Exact Passage Unit + Boundary Proof
          │
          ▼
Canonical Verification Result
  (aggregate state DERIVED)
          │
          ▼
Canonical Verified Evidence Chain
          │
          ▼
Canonical Local Classification
          │
          ▼
Repository-derived Graph Projection
          │
          ├── Semantic Edge (immutable)
          │
          └── Observation Events (append-only)
```

No later stage may independently assert information that an earlier authoritative artifact owns.

## Task 1 — Make cited disclosure an authoritative object (F02)

Introduce one chronology object bound to the exact source version.

Rules:
- versioned evidence requires an owned version record;
- exact cited version disclosure is the primary chronology authority;
- source-wide first-public metadata can contradict the cited version and force uncertainty;
- later sibling editions must not invalidate an independently cited earlier preprint;
- unknown cited disclosure is nondecisive;
- decisive classification with ineligible chronology must be rejected.

Required regressions:
- source first-public 2027 + cited version 2020 => uncertain/nondecisive;
- cited preprint 2020 + later journal sibling 2027 => preprint remains independently assessable;
- old source + post-cutoff revision;
- missing/foreign version;
- unknown version date;
- decisive + POST_CUTOFF impossible.

## Task 2 — Make context completeness depend on proven unit boundaries (F03)

Introduce explicit evidence-unit boundary metadata.

Context is `COMPLETE` only when relevant content-unit boundaries are known.

Rules:
- previous-only or next-only neighbor data is insufficient;
- `TRUNCATED` when content is known to continue outside the supplied context;
- `UNKNOWN` when continuation may exist but boundaries are not known;
- a complete abstract or claim may be complete within its explicit scope;
- zero context budget never means complete;
- repeated text resolves by locator/offset, not first matching string;
- decisive support requires complete-enough context.

Required regressions:
- previous block only;
- next block only;
- both boundaries known;
- complete abstract;
- qualifier just outside window;
- repeated occurrence;
- zero budget;
- blocked context.

## Task 3 — Make `SupportVerification` aggregate state derived, not asserted (F10)

Derive aggregate support state deterministically from commitment judgments.

If compatibility requires storing the aggregate state, require exact equality with the derived result.

Classifier rule:
`DIRECT_PRECEDENT` requires aggregate support state == `SUPPORTED`.

Required regressions:
- forged `PARTIALLY_SUPPORTED` aggregate + all-supported commitments rejected;
- forged `SUPPORTED` aggregate + partial commitment rejected;
- genuine partial remains partial;
- partial + contradiction remains non-direct;
- all-supported becomes supported.

## Task 4 — Introduce authoritative `VerifiedComparison` artifact (F06)

Create one canonical object after full semantic-chain validation containing:

- assessment;
- source;
- version;
- MCU/combination target;
- proposition;
- mapping;
- claim;
- verification;
- canonical passage IDs;
- chronology;
- context completeness;
- verified semantic facts.

Classification must consume this object rather than a loose set of caller-supplied IDs.

Required regressions:
- foreign mapping classification rejected;
- alternate proposition/claim rejected;
- wrong version owner rejected;
- valid combination comparison accepted.

## Task 5 — Make graph projection repository-derived (F07)

Persist Phase 6 graph relations from the authoritative `VerifiedComparison` plus classification.

Do not trust caller-provided semantic graph attributes such as:
- passage IDs;
- mapping ID;
- classification basis;
- chronology;
- verification state;
- precedent relation.

Repository should derive or exact-match them against the authoritative chain.

Required regressions:
- mutate graph passage IDs to nonexistent passage => rejected;
- foreign classification mapping/basis => rejected;
- valid multi-passage direct edge persists;
- valid combination edge persists;
- reopen/idempotence passes;
- unsafe legacy decisive edges remain blocked/quarantined.

## Task 6 — Separate semantic edge identity from observation events (N02)

Persist immutable semantic edge content separately from observation history.

Suggested split:

```text
verified_edges
verified_edge_observations
```

Rules:
- semantic edge ID excludes volatile `observed_at`;
- same semantic assessment replay reuses semantic edge;
- each observation event can append separately;
- exact repeat can remain idempotent;
- different `as_of`/assessment remains a different semantic edge, preserving N01.

Required regressions:
- same edge observed twice one second apart => one semantic edge, two observations;
- exact replay idempotent;
- different cutoff => distinct semantic edge;
- different assessment => distinct semantic edge;
- observation history survives reopen.

## Task 7 — Consolidation regression suite

Create:

`tests/adversarial/test_phase6_contract_consolidation.py`

Cover:
- F02 contradictory chronology and sibling-version cases;
- F03 previous-only/next-only/complete-unit context;
- F06 foreign classification identity;
- F07 false graph citation/classification attributes;
- F10 aggregate-state inconsistency;
- N02 repeated observation semantics.

Keep every prior regression suite.

## Task 8 — Full lifecycle validation

Run the real Phase 6 slice with:
- combination target;
- context-expanded citation;
- scoped partial support;
- version-specific chronology;
- authoritative graph projection.

Require:
`REPORTED -> COMPLETED`

Also reject:
- foreign source;
- foreign version;
- foreign mapping/classification;
- nonexistent passage.

## Task 9 — Verification and migration QA

Run:

```bash
uv sync --dev
uv run python scripts/verify.py
git diff --check
```

Repeat from a fresh checkout.

If schema changes:
- test fresh DB;
- safe migration;
- unsafe legacy migration block/quarantine;
- reopen;
- rollback;
- idempotence;
- observation append.

## Task 10 — Documentation

Preserve all prior FAIL records.

Update completion/review/traceability and add ADRs for:
- authoritative `VerifiedComparison`;
- repository-derived Phase 6 graph projection;
- semantic-edge vs observation identity.

Implementation record must end with:

`Gate 30 remains OPEN pending fresh independent semantic re-review.`

## Task 11 — Fresh independent Gate-30 review

Use a NEW GPT-6 Sol High/Max session.

It must:
- re-attack F02, F03, F06, F07, F10, N02;
- verify closed findings remain closed;
- attack the new authoritative artifacts;
- run full verification;
- run fresh checkout;
- find no open Critical/Important issues.

Gate 30 PASS only if all conditions hold.

## Current state

Phase 6: NOT ACCEPTED
Gate 30: FAIL
Phase 7: BLOCKED
