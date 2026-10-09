# ADR-041: Deterministic Phase 8 bundle identity

- Date: 2026-10-09
- Status: Accepted compatibility design — user approved on 2026-10-09; implementation and acceptance gates remain open
- Governing design: [Phase 8 full report compiler](../../superpowers/specs/2026-10-05-phase-8-full-report-compiler-design.md)
- Existing acceptance decision: [ADR-040](ADR-040-phase8-citations-and-report-acceptance.md)

## Reproduced problem

`report_bundle_digest` converts the native bundle to JSON-mode data before calling
`canonical_hash`. Research coverage fields include frozen sets of planned query
families and retrieval strategies. JSON-mode conversion turns these sets into
lists whose order depends on the Python process hash seed. The canonical encoder
correctly preserves list order, so it cannot recover the lost set semantics.

Two isolated native reloads of the same unchanged real-slice SQLite database,
with hash seeds 1 and 2, produced different bundle digests. All differences in
research state were coverage-set ordering. Scope, native rows and source bytes
were unchanged. A tracked native cross-process regression checks complete
canonical native projection equality before requiring digest equality.

This can prevent resume, artifact publication and accepted-report reload across
processes even when upstream authority is unchanged. Removing the digest check
would weaken authority. Replacing the v1 algorithm silently would reinterpret
identities already bound into compilation keys, artifacts, ReportIR and headers.

## Approved decision

1. Add the supported deterministic policy `p8-bundle-v2`. New default report
   configurations select v2 instead of v1. The existing configuration's
   `deterministic_versions` pins the selected algorithm in persisted compilation
   documents; no unrecorded process default chooses a stored attempt's algorithm.
2. V2 hashes the complete native bundle using Python-mode data and the existing
   canonical encoder, which sorts sets while preserving ordered tuples/lists.
   The digest excludes only `bundle_digest` and includes `bundle_version`.
   The v2 bundle contract is explicitly versioned. No other native field,
   dependency, validator, research finding or rendering policy is changed.
   Attributed native record projections for v2 inputs likewise canonicalize
   sets before public-field filtering and quoted formatting, retaining every
   original JSON scalar and ordered sequence. The existing fallback method
   operates on the explicitly versioned input; its v1 input byte path remains
   exact. This prevents the same coverage-set ordering defect from invalidating
   fallback recomputation after a v2 bundle reload.
3. Retain v1 parsing and its original digest algorithm. Native revalidation of
   a stored attempt selects its pinned v1 or v2 policy. Configurations with no
   supported bundle pin, multiple bundle pins or inconsistent version/digest
   must fail closed. Status artifact policy versions must match the selected
   bundle policy; v1 status artifacts retain their original meaning. New v1
   requests remain explicit compatibility requests.
4. Do not rewrite any existing compilation, artifact, accepted report or golden
   as a migration shortcut. A v1 record remains loadable only when its original
   exact digest and complete native closure validate. If unstable v1 ordering
   prevents validation, create a fresh v2 compilation from the original frozen
   adjudication; do not adopt the old report as authoritative under a new hash.
5. Keep Phase 6/7 authority and persisted bytes unchanged. Configuration pinning
   and the existing canonical document storage can carry this extension without
   changing the four report SQL tables. Any implementation that needs a schema
   change must supply a separate versioned migration before use.

## Required implementation proof

- Observe the real native cross-process regression fail under v1 and pass under
  v2, with complete native projection and unchanged source-byte checks.
- Exercise ordered-sequence sensitivity, set-order invariance, caller corruption,
  missing/ambiguous/unsupported policy pins and v1/v2 identity separation.
- Validate exact v1 compatibility against preserved records; an unstable v1
  rejection is disclosed, never counted as a successful migration.
- Run native begin/resume, acceptance/load/export, transplant, rollback, golden
  and adversarial owners with the selected policy. Revalidate every dependency
  in the original transaction boundaries. No cache or digest-only authority.
- Record versioned provenance for any regenerated v2 golden. Preserve original
  rendering evidence and existing v1 replacement provenance separately.
- Complete strict typing, full suites, clean detached verification and independent
  whole-phase acceptance. This decision alone closes no task or acceptance gate.

## Approved compatibility choice

The user approved the versioned v2 extension and the explicit fresh-compilation route for
v1 records that cannot validate across processes. The alternative is to defer
this extension and keep affected real-slice resume/read gates pending. Silently
changing v1 hashes or relaxing native authority is not proposed.
