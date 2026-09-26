# Novelty Assessment Harness

A phase-gated, evidence-grounded novelty assessment project.

The authoritative behavior is in [the master specification](docs/specs/master-design-spec.md).
Implementation follows [the Phase 0 plan](docs/superpowers/plans/2026-09-26-phase-0-repository-governance-contracts.md)
[the Phase 1 plan](docs/superpowers/plans/2026-09-26-phase-1-deterministic-thin-vertical-slice-implementation-plan.md)
and [AGENTS.md](AGENTS.md).

Phase 0 provides versioned Pydantic contracts, canonical enums and opaque IDs,
pure audited lifecycle transitions, credential-free settings with unset budget
limits, six abstract async provider ports, deterministic test fixtures, canonical
hashing, append-only JSONL traces with secret-key redaction, and JSON logging.

Python 3.12+ and uv are required. Install and verify:

```bash
uv sync --dev
uv run python scripts/verify.py
```

The gate runs Ruff lint, Ruff format checks, strict Pyright application checks,
and pytest. Unit, contract, and integration tests block IPv4/IPv6 sockets; local
Unix sockets are allowed for asyncio wakeups. The `network` marker alone does not
enable network access. There are no live providers or live provider tests.

## Phase 1: Deterministic thin vertical slice

Phase 1 adds versioned CIR, sufficiency, MCU/combination, research, evidence and
deeply frozen adjudication contracts; nine replaceable async semantic-component
ports; an atomic per-file artifact writer; a deterministic nine-question report
compiler; and complete lifecycle orchestration. It does not assess real novelty.

Run the synthetic end-to-end fixture with the default network block:

```bash
uv run pytest tests/integration/test_phase1_vertical_slice.py -v
```

`run_vertical_slice` in `application/vertical_slice.py` accepts a request,
injected components, abstract search/content providers, trace sink, artifact
writer and clock. Production code never imports test fixtures. The fixture lives
only in `tests/fixtures/phase1.py`; production has no default semantic engine.

Each run retains the original request, CIR, sufficiency, MCU graph, reviewed
search plan, source/passages, verified edge snapshots, frozen adjudication,
`assessment.json`, `report.json`, `report.md`, `assessment_record.json` and
append-only `trace.jsonl`. Successful runs reach REPORTED/COMPLETED. The report
copies frozen verdicts and value maturity, records the adjudication hash, and
answers all nine canonical questions without providers or new novelty decisions.

**Fixture-backed/deferred:** normalization, sufficiency judgments, MCU
decomposition/reconciliation, query planning/review, evidence interpretation and
adjudication. Adaptive research, prosecutor/defender and robustness stages are
explicitly deferred in the trace. An empty coverage matrix is not saturation;
fixture support states and verdicts are synthetic test data, not real conclusions.
Source wrapping copies transport data and hashes exact content, without semantic
normalization, fuzzy deduplication, source-quality judgments or chronology checks.
Unknown source type/access completeness stay unknown. No novelty/confidence
scores, numerical thresholds, budgets or real external providers were added.

There is no CLI, database service, retry/resume or general partial-failure service
yet. Writes are atomic individually, not as a multi-file transaction. Assessment
and lifecycle/trace IDs remain opaque UUID4 IDs; transport source/passages use
stable exact-identity/content hashes (not semantic source identity resolution).
Trace writes are locked within one process, not across processes.
Redaction covers sensitive mapping keys, not secrets embedded in arbitrary prose.
Phase 2 has not started.

See [Phase 0 traceability](docs/traceability/phase-0.yaml),
[Phase 1 traceability](docs/traceability/phase-1.yaml) and
[architecture decisions](docs/architecture/decisions/) for scope and decisions.
