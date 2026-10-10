# Phase 8 schema v10 report storage implementation plan

> **For agentic workers:** Use superpowers:executing-plans for inline execution with test-driven development. The user has authorized autonomous implementation of ADR-043; no additional implementation approval is pending.

**Goal:** Persist arbitrarily large logical canonical Phase 8 reports across SQLite rows without changing their contents or authority.

**Architecture:** Preserve inline accepted reports and add report-owned compressed canonical byte segments with a strict versioned manifest. All reconstruction and full native validation remain inside existing repository transactions.

**Tech stack:** Existing Python 3.12, Pydantic v2, SQLAlchemy/SQLite and standard-library zlib; no added dependency.

**Spec:** docs/specs/master-design-spec.md and docs/architecture/decisions/ADR-043-phase8-large-report-storage.md.

## Review focus

- Old accepted inline records must retain exact bytes through migration and full native reload.
- A manifest with coherent attacker-controlled hashes must not authorize changed report semantics.
- UTF-8 boundaries and compressed trailing data must preserve exact original bytes or fail closed.
- Failure after some segments publish must leave no header, segments, dependencies or accepted status.
- Every direct accepted-document reader must support both formats in the same transaction.


Approved authority: user approval of ADR-043 on 10 October 2026, plus unrestricted development execution under ADR-042. This supplements Tasks 19–24 of the approved Phase 8 plan. It does not authorize Phase 9 or changes to logical report content.

Specification: master design §§38–39 and Phase 8 exit criteria; frozen findings, complete traceability and exact JSON/YAML/Markdown outputs remain mandatory. No dependencies, public domain schemas, scientific findings, canonical logical identities or method/renderer versions change.

## 1. Physical codec

Write exact-byte and corruption controls before implementation. Run the exact codec owner against absent implementation and record the missing-feature failure. Implement a private strict versioned manifest and ordered lossless zlib segments of 1 MiB canonical UTF-8 bytes. The reconstructed document must be byte-identical; each row binds report ID, ordinal, codec, uncompressed length and content SHA. Reject missing/extra/reordered/foreign segments, malformed/truncated/trailing compressed data, false manifest lengths/counts/digest, unknown codec and noncanonical manifest. Test ASCII escaping, Unicode/control/surrogates and UTF-8 boundaries independently. No total document/chunk/process memory limit.

## 2. Additive schema v10

Write v9→v10 atomic migration/reopen/failure controls before implementation. Add compiled_report_document_chunks, PK(report_id, ordinal), report FK and nonnegative ordinal constraint. Register with existing Base; update schema version and supported additive migration range. Preserve unsafe legacy guards and every existing row. Update current-version expectations only, retaining upstream and FK assertions; include the new table in report-only accounting and historical topology teardown. Older implementations must reject schema 10.

## 3. Acceptance, load and replay

The native owning RED is task22-unrestricted-readiness-00-133: SQLite DataError at report INSERT, zero accepted rows, complete cleanup. Preserve its closed native VERIFIED database and checksum.

Keep small canonical documents inline when the document plus complete header and SQLite record overhead safely fits the engine's intrinsic row limit. This selection is a physical representation rule, never a test memory criterion. Query the actual connection limit; do not modify it. Larger documents use a canonical strict manifest and complete segments.

All three existing direct readers (accepted header, immutable replay, authoritative load) must reconstruct within their existing explicit transaction. Inline rows must have no segments. Strictly parse and compare the reconstructed document to the original canonical serialization; preserve existing ID/header/dependency/terminal/provenance/IR/fallback/citation/rendition checks. Atomic acceptance writes header, complete chunks, exact dependencies and ACCEPTED status; failure rolls all back.

Native tests force representation selection only, without lowering any engine/test/process memory limit. Cover exact inline and segmented authority/load/replay/export, missing/extra/foreign/reordered chunks, coherently rehashed semantic attacks with intended typed native rejection, segment/dependency/status rollback, and preserved accepted-inline migration/load. Keep native scope/upstream assertions and original nine-question coverage.

## 4. Required verification and recovery

Run codec/schema controls, existing storage/migration/authority/capability owners, full strict Pyright and Ruff. Commit and independently back up the source before demanding native work. Run the exact real-slice/export-failure/completed-lifecycle owners against final schema-v10 source, then Task 23 accepted delivery, Task 24 integrated cases and independently verified rendering replacements. Heavy tests remain sequential with finite timeouts, offline plugin/socket policy, functional detection and cleanup; no memory observations can veto or stop execution.

Run full owning/upstream/adversarial/golden suites, uv run python scripts/verify.py, exact fresh clean detached verification and independent whole-phase review before acceptance. Preserve every receipt at its actual source identity. No incomplete test or aborted owner counts as passing; no speedup or memory-saving claim follows from representation changes. Original lost-tree equivalence remains unproved.

## Files and interfaces

- Create src/novelty_harness/evidence/graph/report_document.py: document_segments(document: str) -> Iterator[bytes], document_manifest(report_id: str, document: str) -> DocumentManifest, encode_document(report_id: str, document: str) -> Iterator[DocumentChunk], decode_document(manifest_json: str, report_id: str, chunks: Iterable[DocumentChunk]) -> str. These are physical codecs, never native authority validators.
- Modify report_models.py: CompiledReportChunkRow on existing Base. Modify migrations.py: schema10 with unchanged additive atomic behavior.
- Modify report_store.py: _inline_document_capacity(session: Session, accepted: CompiledAssessmentReport) -> int and _load_report_document(session: Session, row: CompiledReportRow) -> tuple[CompiledAssessmentReport, str]. Acceptance writes all rows; existing header/replay/load consume the exact logical document.
- Create tests/unit/evidence/graph/test_report_document.py, test_report_segments_schema.py, test_report_segment_authority.py. Update current-version expectations in existing migration owners and report-table accounting only.

## Execution checklist

- [ ] Run codec missing-feature RED: .venv/bin/python -B -m pytest -p pytest_socket -p pytest_asyncio.plugin tests/unit/evidence/graph/test_report_document.py -q, supervised with finite timeout and unrestricted memory. Expect missing codec implementation; record exact output.
- [ ] Implement codec and run the same owner GREEN, retaining independent literal-wire and corruption expectations.
- [ ] Run additive migration RED: same supervised command for test_report_segments_schema.py. Expect schema9 instead of10. Implement additive rows/version and run exact GREEN.
- [ ] Integrate all three document readers and atomic acceptance, using preserved native SQLite owner failure as RED; run native segmented/inline/migration/corruption/rollback owners GREEN.
- [ ] Run affected complete owners, full strict typing, Ruff and format checks; commit and independently back up before demanding native tests.
- [ ] Run exact real-slice, export-failure and completed-lifecycle owners; complete Task23/24, rendering replacements and all final gates before any completion claim.
