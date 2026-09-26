# Novelty Assessment Harness

A phase-gated, evidence-grounded novelty assessment project.

The authoritative behavior is in [the master specification](docs/specs/master-design-spec.md).
Implementation follows [the Phase 0 plan](docs/superpowers/plans/2026-09-26-phase-0-repository-governance-contracts.md)
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
enable network access. There are no live provider tests in Phase 0.

The lifecycle smoke test traverses stage labels only. Real research, MCU
extraction, evidence analysis, adjudication, and reporting are not implemented.
There is no CLI or database service yet. UUID4 IDs are opaque; stable content IDs
are deferred. Trace writes are locked within one process, not across processes.
Redaction covers sensitive mapping keys, not secrets embedded in arbitrary prose.

See [Phase 0 traceability](docs/traceability/phase-0.yaml) and
[architecture decisions](docs/architecture/decisions/) for scope and decisions.
