# ADR-042: Unrestricted memory in development and test execution

- Date: 10 October 2026
- Status: Accepted by explicit user instruction
- Scope: Local development and test supervision; no product contract change

## Decision

The user explicitly authorizes macOS to manage RAM and swap and accepts severe swapping, system unresponsiveness, OS process termination and a possible crash. Current execution policy v3 has no soft/hard memory caps, available-memory or launch-headroom requirements, pressure/swap/paging vetoes, or memory-triggered termination. Older recipe arguments cannot restore those restrictions. Memory collectors are optional observations and are not a launch dependency. Explicit V8 heap caps are not used in verification commands.

The global execution lock keeps heavyweight jobs sequential. Finite timeouts, functional exit detection, interruption handling, descendant cleanup, offline test policy, source/inventory identity and durable evidence accounting remain mandatory. Valuable source changes are committed and backed up before demanding runs. Functional, semantic, scientific, security, provenance and acceptance assertions are unchanged.

## Compatibility and evidence

Historical v1/v2 memory policy definitions remain solely to interpret old receipts accurately. Every actual supervisor run normalizes its policy to v3. Current receipts explicitly record policy v3 and zero (disabled) memory fields. A run without an optional memory observer records zero samples; this means memory was not measured, never zero memory consumption. Historical refusals and aborts retain their original meaning and source identity.

This decision supersedes the execution restrictions in the local 8 GB remediation proposal and earlier recovery readiness holds. It does not waive Phase 8 acceptance, final verification, exact detached-checkout verification or independent review.
