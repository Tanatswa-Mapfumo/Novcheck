# Phase 6 provenance hardening implementation plan

Status: approved scope supplied in the 30 September 2026 user instruction.
This file records implementation choices because the referenced plan was absent
from both available checkouts. Gate 30 remains open and Phase 7 stays blocked.

1. Reproduce R01-R03 in the new adversarial suite. Add immutable resolved
   source/version content and extractor-owned span attestations. Resolve every
   cited passage against the original normalized content and its authoritative
   source/version digest at public edge, comparison and graph boundaries.
2. Reproduce R04-R05. Make routing a priority over all eligible sources and
   carry each candidate's classification and optional chain in one result.
3. Reproduce R06-R09. Build patent entries from classified comparisons, bind
   multi-source summaries to one target/assessment, revalidate all public
   semantic inputs, and reject v2/v3 orphan verified artifacts in migration.
4. Exercise the authenticated lifecycle, run the full repository verifier,
   document schema/contract decisions and limitations, commit, and verify the
   exact commit in a fresh checkout.

Each deterministic behavioral change starts with a failing regression and
then a passing focused run. The final suite and fresh checkout are acceptance
evidence for the implementation only; they cannot close Gate 30.
