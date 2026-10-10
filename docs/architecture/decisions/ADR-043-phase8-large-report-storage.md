# ADR-043: Lossless storage for reports beyond a SQLite row

- Date: 10 October 2026
- Status: ACCEPTED — explicitly approved by the user on 10 October 2026
- Scope: Phase 8 accepted-report persistence; public report contracts remain unchanged

## Observed failure

With all development/test memory restrictions removed, the exact native Task 22 export-failure owner reached acceptance and SQLite rejected the compiled-report INSERT with `sqlite3.DataError: string or blob too big`. The exception was translated to `ReportAuthorityError`; the intended export failure was never reached. Receipt `task22-unrestricted-readiness-00-133` records functional exit 1, all pytest phases and complete cleanup after 1,593.497s. No memory sample or memory stop occurred. A transient process-list timeout was tolerated by the corrected supervisor.

The installed Python SQLite engine reports version 3.50.4 and both runtime `SQLITE_LIMIT_LENGTH` and compiled `MAX_LENGTH` equal to 1,000,000,000 bytes (`task22-sqlite-native-limit-135`). SQLite applies this intrinsic boundary to strings, blobs and complete rows; see [SQLite implementation limits](https://www.sqlite.org/limits.html). The failed private database retains all nine FALLBACK artifacts (individual JSON lengths 55,636; 20,603,297; 81,379,182; 100,961,360; 1,047,121; 47,322; 3,195,629; 81,007,435; 101,075,798 bytes), DRAFTED/VERIFIED status and zero accepted rows. These measurements do not establish the exact complete attempted row length or a native pass.

The approved Phase 8 plan stores one canonical report document in `compiled_reports.document_json` at schema v9. Changing that persisted representation requires the explicit versioning/decision required by AGENTS.md §§2/7. The user explicitly approved this storage change. Unrestricted execution under ADR-042 continues.

## Decision

Introduce schema v10 with additive `compiled_report_document_chunks`, owned by `compiled_reports.report_id`, with a primary key `(report_id, ordinal)` and nonnegative ordinal constraint. Each row stores one physical segment of the exact original canonical UTF-8 report document, with a versioned lossless codec, byte length and content digest. Use fixed physical segment granularity (1 MiB before standard-library zlib compression). Segment granularity is a storage format: there is no limit on total report bytes, segment count or process memory, and no execution veto or termination follows from it.

For segmented reports, the existing document column stores a strict versioned manifest identifying the report, codec, complete canonical-document digest/length and segment count. Existing inline canonical report documents remain valid and are not rewritten. Select segmentation when a document cannot safely fit the engine's intrinsic row representation; keep small documents inline. No SQLite limit is raised or test resource limit introduced. New schema-version checks prevent older code from silently interpreting v10.

Accepted report IDs, compilation IDs, all public Pydantic contracts, canonical logical document bytes, native IR/citation/fallback identities, scientific findings and JSON/YAML/Markdown output rules remain unchanged. The same complete validated private report is persisted. Any implementation that requires changing logical bytes, hashes, field projections or public renderer versions falls outside this proposal.

## Required authority and transaction behavior

1. All existing native input, artifact, terminal-state, exact IR/provenance/dependency and rendition-parity checks run before publication.
2. Header, manifest, every segment, exact dependency rows and ACCEPTED status publish atomically in the existing explicit transaction. Failure during any segment/dependency/status write rolls everything back.
3. Authoritative load and immutable replay select exactly one report's segments in ordinal order in the same explicit read transaction. They reject missing/extra/reordered/foreign segments, wrong codecs, malformed compressed data, false lengths/digests and noncanonical reconstructed documents.
4. Reconstructed bytes strictly parse to the original report contract and must match its canonical serialization. Existing header/scope/dependency joins and full native recomputation remain mandatory. A manifest or digest never grants authority.
5. Existing inline v9 accepted records remain byte-for-byte preserved through additive migration and reload. Existing frozen Phase 6/7 records are never rewritten or synthesized.
6. Compiler/semantic ports acquire no SQL, filesystem, search, research or upstream mutation capability; storage stays in the report repository.

## Required RED/GREEN and acceptance evidence

- Reproduce the native SQLite failure as the owning RED; preserve its protected receipt.
- Exact codec roundtrip/differential tests, including Unicode/control characters, arbitrary segment boundaries, malformed/unknown codec, truncation, extra data and caller immutability.
- Native inline/segmented acceptance, authoritative reload, exact replay and all-format equality; force format selection in tests without lowering SQLite or process memory limits.
- Native missing/extra/foreign/reordered segment and coherently rehashed semantic attacks; require the intended typed native rejection, not an unrelated immutable-conflict or FK failure.
- Native transactional rollback during segment/dependency/status publication and additive v9→v10 migration/reopen/failure rollback, preserving old canonical records and FK enforcement.
- Fresh exact Task 22 real-slice, generation/export-failure, completed-lifecycle and export owners with every original target, nine-question, limitation, upstream-row, scope, trace and output assertion retained.
- All affected owning/upstream/adversarial/golden suites, full strict typing, `scripts/verify.py`, exact fresh detached verification and the required independent whole-phase review.

## Alternatives and limits

Increasing/recompiling SQLite's row maximum only moves an intrinsic boundary and changes the engine dependency; it does not solve arbitrary complete-report growth. Lossless compression in one row can help repeated text but still fails for sufficiently large incompressible documents. Reducing report content, replacing propositions with weaker summaries or bypassing validation would change approved report semantics and is excluded.

The proposed storage format does not correct logical payload amplification or prove a runtime improvement. Complete reconstruction/validation/rendering can still require substantial RAM, swap and time. macOS continues to manage memory naturally, with only finite execution timeouts and functional detection. Original lost-tree equivalence remains unproved.
