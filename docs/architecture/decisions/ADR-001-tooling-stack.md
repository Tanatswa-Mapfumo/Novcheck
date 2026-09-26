# ADR-001: Python and tooling baseline

Status: Accepted for Phase 0
Date: 2026-09-26

## Context

Master-spec Sections 43 and 60 require a local, typed, testable foundation.
The approved Phase 0 plan selects Python 3.12+, uv, and Pydantic v2.

## Decision

Use a src-layout package built by Hatchling, uv with a committed lockfile,
Pydantic v2 contracts, pydantic-settings, pytest, pytest-asyncio, pytest-socket,
Ruff, and strict Pyright application checks. Hatchling is build tooling only.
The verification script runs lint, format, typing, and tests in order and stops
on the first failure.

Defer Typer, SQLAlchemy, HTTPX, and provider SDKs until an approved phase uses
them. No research defaults, saturation thresholds, or novelty scores are chosen.

Ruff formats Python only; supplied authoritative Markdown is preserved verbatim.
Its str/Enum modernization rule is disabled to match the plan's explicit enum base.
pytest-socket blocks IPv4/IPv6 sockets by default, with no allowed hosts. Local
Unix sockets are allowed solely because asyncio constructs a socket pair for
event-loop wakeups. A failing async setup demonstrated this requirement; tests
verify TCP and UDP socket construction remain blocked for both IP families.

## Consequences

Phase 0 installs without any external-provider credentials. Later phases must
introduce their own used dependencies and preserve the domain boundary.
