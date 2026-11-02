# Local storage

The storage package uses Python's `sqlite3` module and local files. Default
database: `data/dev.sqlite3`. It stores media metadata and local path references,
not video binaries. Generated files under `data/` are ignored by Git.

## Create a development database

```sh
make db-migrate
make db-seed
make db-dev
```

`db-migrate` applies pending migrations. `db-seed` runs migrations before
inserting deterministic development fixtures. `db-dev` invokes the seed path.
Seeding uses replacement inserts and is intended for a development database;
avoid running it on curated review data.

Override the database without changing code:

```sh
make db-dev DB_PATH=/tmp/sports-labeller-demo.sqlite3
python -m packages.storage.migrate --db-path /tmp/sports-labeller-demo.sqlite3 --status
```

`--status` reports pending migrations, but opens/creates the database and
migration metadata table. It is not a filesystem-side-effect-free operation.
The connection helper creates parent directories, enables foreign keys and
returns named SQLite rows.

## Tables and relationships

Defined in
[`0001_initial.sql`](../packages/storage/migrations/0001_initial.sql):

| Table | Purpose |
| --- | --- |
| `schema_migrations` | Applied SQL version, name and time; created by migration runner |
| `ontology_versions` | Versioned JSON definition and sport metadata |
| `model_versions` | Model identity, source, metadata and optional promotion time |
| `videos` | Local path, original filename, duration/timebase/frame rate/hash |
| `evidence_records` | Timestamp, modality, value JSON, confidence and source model |
| `predictions` | One-second label output with video/model/ontology foreign keys |
| `prediction_evidence` | Many-to-many links preserving prediction evidence |
| `learning_modes` | Seeded `training` and `soft` vocabulary |
| `reviewer_roles` | Seeded reviewer role vocabulary |
| `corrections` | Flat corrected interval and reviewer/provenance fields |
| `correction_trust_metadata` | Validity, assigned weight, policy version and reviewer/consensus signals |

Prediction and evidence records reference videos and model versions;
predictions also reference ontology versions. Corrections reference the video,
source prediction/model, ontology, learning mode and reviewer role. Trust
metadata belongs to a correction. SQL constraints enforce bounds on confidence,
intervals, enums and selected trust rules. Label membership and richer
application semantics still require contract/ontology validation.

## Migration policy

SQL files are numbered `NNNN_name.sql` and applied in filename order. Applied
versions are recorded in `schema_migrations`; rerunning the migration command
skips them. Add a new migration when a shared schema changes. There is no
down-migration command, migration checksum verification or backup automation.
Use disposable databases for migration development and preserve valued data
before schema work.

## Transport and database boundaries

Neither HTTP implementation writes UI uploads, predictions or corrections into
SQLite. API acknowledgements do not create training examples. The development
seed and tests populate database fixtures independently.

The correction transport schema contains nested target/corrected intervals and
multiple immutable source snapshots. SQLite currently stores a flat interval,
`original_label`, `corrected_label`, one `source_prediction_id` and an evidence
snapshot JSON field. It does not have tables for full multi-source split/merge
lineage. SQL requires a source prediction for every correction except `add`,
while transport validation also allows source-free ontology-gap reports.
An explicit persistence mapping and additional schema work are needed.

The prediction transport agreement field is boolean/null, while SQLite stores
a bounded numeric agreement value. Do not assume SQL row dictionaries can be
sent unchanged as transport contracts. The training exporter performs an
explicit row-to-record mapping and preserves the provenance it can represent.

## Inspect data

```python
from packages.storage.database import connect

with connect("data/dev.sqlite3") as connection:
    for row in connection.execute(
        "SELECT correction_id, review_status, trust_weight FROM corrections"
    ):
        print(dict(row))
```

Training preparation reads accepted correction rows joined to trust metadata,
video timebase and ontology definitions. Missing/invalid trust, zero weight,
non-trainable types and invalid derived contracts are skipped with reasons.
See [learning workflows](ML_WORKFLOWS.md).
