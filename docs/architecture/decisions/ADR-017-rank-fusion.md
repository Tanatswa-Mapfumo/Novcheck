# ADR-017: Rank-only candidate fusion

Status: Accepted for Phase 4 implementation

RRF adds 1/(k + local_rank) per distinct provider/query/strategy/seed stream.
k defaults to 60 as in the approved plan and is configurable/positive; it is not a
novelty/confidence threshold. Only candidates for one MCU/evidence-family objective
may be fused in a call. Pipeline fusion runs separately per research branch.

Provider-local scores never enter arithmetic. Stream identity, not mapping aliases,
controls contributions: repeated lists/pages preserve discoveries but each document
contributes once per stream, using its best observed rank. Citation directions are
distinct ranked paths even though they share a conservative saturation mechanism.
Global ranks across pagination are supplied by retrieval execution.

Tie order uses stable candidate keys. Provider identities, all list labels and full
discovery observations remain auditable. Candidate clustering before final fusion
may unify explicit identities without erasing path/metadata conflicts. This is not
source normalization, evidence independence, equivalence or novelty adjudication.
