# ADR-018: Explicit, policy-bound research stopping

Status: Accepted for Phase 4 implementation

## Decision

Stopping policy is supplied by the caller, not inferred from novelty or calibrated
confidence. It specifies provider/mechanism floors, a convergence window of at
least two observations, a maximum marginal candidate yield, and whether citation
convergence is required. These are operational search settings, not universal
novelty thresholds. No default production saturation threshold is invented.

SATURATED requires every gate: configured successful-provider diversity;
genuine mechanism diversity (text paraphrases share one mechanism); covered
applicable-family floor; diminishing yield throughout the configured window;
nonempty stable strongest clusters; observed cross-mechanism overlap; exploration
of major candidates; and, when required, diminishing citation yield. An empty
field alone never supplies convergence evidence.

Required, completed and depth-deferred neighborhoods are tracked separately.
Suppressing an action at the configured depth limit is not exploration. A major
candidate's required neighborhood remains an unresolved gate until actually
completed; the controller does not silently increase the approved depth.

Budget preventing the next reasonable action has precedence and yields
BUDGET_STOPPED. Material unresolved access gaps yield ACCESS_BLOCKED and block
saturation, including unavailable applicable families. Remaining reasonable work
without convergence remains CONTINUE. Unsupported multilingual work is explicit;
if configured as material its unavailability is an access gap.

## Consequences

The pipeline retains inconclusive outcomes when configured strategies run out
before convergence. This deliberately favors traceable limitations over invented
exhaustiveness. Candidate convergence is not source provenance, supported evidence,
claim equivalence, a novelty verdict or a probability. Capture-recapture is deferred.
