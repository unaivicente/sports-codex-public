# Storage Package

Local SQLite storage abstractions for the metadata labeller.

The storage layer is local-first: it uses a SQLite database on the developer
machine and does not introduce cloud storage, remote inference, or remote
services.

## Migration Tool

This repo uses `packages.storage.migrate`, a small migration runner built on the
Python standard library `sqlite3` module. This matches the current backend
conventions: Python modules, `unittest`, and root `make` commands without a
separate ORM or package manager for database tooling.

Commands:

```sh
make db-migrate
make db-seed
make db-dev
```

By default these commands use `data/dev.sqlite3`. Override with `DB_PATH`:

```sh
make db-dev DB_PATH=/tmp/metadata-labeller.sqlite3
```

Generated local database files under `data/` are ignored by git.

## Migration Strategy

- Migrations live in `packages/storage/migrations` as numbered SQL files:
  `NNNN_name.sql`.
- Applied versions are tracked in the SQLite `schema_migrations` table.
- Migrations are append-only once shared. Fixes should be added as a new
  numbered migration rather than rewriting an applied migration.
- Tests and local development should run migrations against disposable SQLite
  files before seeding data.
- The database stores video metadata and local path references only. Uploaded
  video binaries must remain on disk/object-local storage outside SQLite.

## Initial Schema

The initial migration creates tables for:

- `videos`
- `ontology_versions`
- `model_versions`
- `evidence_records`
- `predictions`
- `prediction_evidence`
- `learning_modes`
- `reviewer_roles`
- `corrections`
- `correction_trust_metadata`

Prediction rows preserve timestamp, label, confidence, model version, ontology
version, inference config, and evidence links. Correction rows preserve the
source prediction, source model version, ontology version, evidence snapshot,
learning mode, reviewer role, reviewer confidence, trust weight, review status,
and model-agreement metadata.

See the [implementation guide](../../docs/STORAGE.md) and
[documentation index](../../docs/README.md) for examples and integration limits.
