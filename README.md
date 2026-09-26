# Novelty Assessment Harness

A phase-gated, evidence-grounded novelty assessment project.

The authoritative behavior is in [the master specification](docs/specs/master-design-spec.md).
Implementation follows [the Phase 0 plan](docs/superpowers/plans/2026-09-26-phase-0-repository-governance-contracts.md)
[the Phase 1 plan](docs/superpowers/plans/2026-09-26-phase-1-deterministic-thin-vertical-slice-implementation-plan.md)
and [the Phase 2 plan](docs/superpowers/plans/2026-09-26-phase-2-intake-sufficiency-robust-mcu-engine-implementation-plan.md),
with [AGENTS.md](AGENTS.md).

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
The accepted Phase 1 snapshot is retained; Phase 2 extends understanding as below.

## Phase 2: Intake, sufficiency and robust MCU engine

Phase 2 adds real provider-independent, model-assisted understanding behind the
four existing intake/sufficiency/MCU ports. Strict structured validation, extractive
material-field grounding and explicit unknowns preserve original input. Structural
sufficiency ceilings do not use length/fluency or inferred novelty. Missing/withheld
mechanisms stay unassessable; claimed advantages remain CLAIMED.

Independent A/B prompts share only CIR/original input, never the other's result.
Alignment compares feature concepts, directed relationships and material scope;
semantic alias proposals must pass structural checks. Reconciliation retains
resolutions/disagreements and separate combinations. All six structural tests run.
Material unresolved instability caps affected contributions at EXPLORATORY and
reduces aggregate sufficiency before research; it does not decide a novelty verdict.

`understand_idea` in `intake/pipeline.py` accepts a request, SemanticRunner wrapping
the abstract LLMProvider, optional artifact writer/assessment ID and clock. It
returns frozen CIR/sufficiency, A/B, reconciliation and an immutable MCUVersion.
`UnderstandingComponents` is a fresh request-scoped adapter for the four existing
vertical-slice ports. It publishes A/B, alignment, critic, version and semantic-call
audits; initial CIR/sufficiency remain retained when final bindings/ceilings change.

```bash
uv run pytest tests/integration/test_phase1_slice_with_phase2_components.py -v
uv run pytest tests/adversarial/test_phase2_mcu_attacks.py -v
```

Default responses are recorded test data; production never imports fixtures.
No vendor SDK, live model, literature/web/patent search, evidence-family planner,
search critic, RRF, adaptive controller, prior-art equivalence, evidence support
reasoning, prosecutor/defender or novelty adjudication is implemented. Later
research/evidence/adjudication remain fixture-backed in the end-to-end tests.

Overrides use strict operation payloads and return new content-hashed versions
with actor/reason/time, parent and before/after graph audit. Merge/split explicitly
update affected combinations; dangling references reject the edit. No in-place
API, implicit cascading edit, database or UI. Rollback selects a retained parent.
Old structural ceilings are not erased by an override.

Span/schema checks do not prove semantic entailment or deployed model robustness.
Fixtures prove safeguards and architectural flow, not general model intelligence.
No real novelty assessment is possible yet. Phase 3 has not started.

See [Phase 0 traceability](docs/traceability/phase-0.yaml),
[Phase 1 traceability](docs/traceability/phase-1.yaml),
[Phase 2 traceability](docs/traceability/phase-2.yaml),
[Phase 2 completion](docs/phase-2-completion.md) and
[architecture decisions](docs/architecture/decisions/) for scope and decisions.
