# ADR-022: Evidence graph storage — SQLAlchemy 2.x over SQLite

Status: Accepted for Phase 5 implementation

## Decision

The evidence graph domain (`evidence/graph/models.py`) is storage-independent
Pydantic. A `Protocol` (`evidence/graph/repository.py`) defines node/edge
upsert, lookup, neighbour and lineage-cluster access. The first implementation
is SQLAlchemy 2.x with SQLite; PostgreSQL-compatible column choices are
preferred (string keys, ISO-8601 timestamp strings, JSON text payloads, no
SQLite-specific column types, no reliance on rowid).

Repository methods return domain models. ORM rows never leak through the
protocol, and domain modules never import SQLAlchemy.

## Schema

- `schema_version(version INTEGER PRIMARY KEY, applied_at TEXT)` — one row;
  `ensure_schema` creates the schema at the current version and refuses
  unknown/newer versions instead of reinterpreting data.
- `graph_nodes(node_id TEXT PRIMARY KEY, kind TEXT, label TEXT, document_json TEXT)`
  — `document_json` is the canonical JSON of the domain `GraphNode`; `kind`
  and `label` are denormalized for querying.
- `graph_edges(edge_id TEXT PRIMARY KEY, kind TEXT, source_node_id TEXT REFERENCES graph_nodes,
  target_node_id TEXT REFERENCES graph_nodes, document_json TEXT)`. Canonical
  edge uniqueness is content-addressed: deterministic edge IDs derive from the
  relation and its evidence, so identical canonical edges cannot exist twice
  while two edges of the same kind between the same nodes with different
  evidence remain legitimately distinct rows.
- `lineage_clusters(cluster_id TEXT PRIMARY KEY, document_json TEXT)` and
  `lineage_cluster_members(source_id TEXT PRIMARY KEY REFERENCES graph_nodes,
  cluster_id TEXT REFERENCES lineage_clusters)` — a source belongs to at most
  one lineage cluster, enforced by the primary key.

## Rules

- `PRAGMA foreign_keys=ON` is set for every connection; dangling edges are
  additionally rejected before flush with a clear domain error.
- `upsert(nodes, edges, clusters)` runs in one transaction. Identical
  re-persistence is idempotent. Persisting different canonical content under
  an existing identity raises instead of overwriting; corrections require a
  new identity/run, preserving append-only history.
- In-memory SQLite databases use a `StaticPool` so the schema survives across
  sessions inside one repository instance.
- Domain enforcement of reserved edge kinds stays in `GraphEdge`; the database
  stores what the domain accepts.

## Consequences

The graph can be reopened, queried and verified without any contract change if
a later phase moves to PostgreSQL. The cost is duplicated denormalized columns
and canonical-JSON payload comparison on upsert, which is acceptable at
personal-system scale.
