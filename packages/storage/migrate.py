"""Small SQLite migration runner using the Python standard library."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from packages.storage.database import DEFAULT_DB_PATH, connect

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


@dataclass(frozen=True)
class Migration:
    """A single SQL migration file."""

    version: str
    name: str
    path: Path


def list_migrations(migrations_dir: Path | str = MIGRATIONS_DIR) -> list[Migration]:
    """Return migrations in filename order."""

    migrations: list[Migration] = []
    for path in sorted(Path(migrations_dir).glob("*.sql")):
        version, separator, name = path.stem.partition("_")
        if not separator or not version.isdigit() or not name:
            raise ValueError(f"invalid migration filename {path.name!r}; expected NNNN_name.sql")
        migrations.append(Migration(version=version, name=name, path=path))
    return migrations


def ensure_migration_table(connection) -> None:
    """Create the migration metadata table if it is missing."""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
        )
        """
    )
    connection.commit()


def applied_versions(connection) -> set[str]:
    """Return migration versions already applied to the database."""

    ensure_migration_table(connection)
    rows = connection.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
    return {row["version"] for row in rows}


def pending_migrations(
    db_path: Path | str = DEFAULT_DB_PATH,
    migrations_dir: Path | str = MIGRATIONS_DIR,
) -> list[Migration]:
    """Return migrations that have not been applied."""

    with connect(db_path) as connection:
        applied = applied_versions(connection)
    return [migration for migration in list_migrations(migrations_dir) if migration.version not in applied]


def migrate(
    db_path: Path | str = DEFAULT_DB_PATH,
    migrations_dir: Path | str = MIGRATIONS_DIR,
) -> list[Migration]:
    """Apply all pending migrations and return the migrations applied."""

    migrations = list_migrations(migrations_dir)
    applied: list[Migration] = []

    with connect(db_path) as connection:
        existing_versions = applied_versions(connection)
        for migration in migrations:
            if migration.version in existing_versions:
                continue

            sql = migration.path.read_text(encoding="utf-8")
            with connection:
                connection.executescript(sql)
                connection.execute(
                    "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
                    (migration.version, migration.name),
                )
            applied.append(migration)

    return applied


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply local SQLite migrations.")
    parser.add_argument(
        "--db-path",
        default=str(DEFAULT_DB_PATH),
        help=f"SQLite database path (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--migrations-dir",
        default=str(MIGRATIONS_DIR),
        help="Directory containing numbered .sql migrations.",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Print pending migrations without applying them.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.status:
        pending = pending_migrations(args.db_path, args.migrations_dir)
        if pending:
            print("Pending migrations:")
            for migration in pending:
                print(f"- {migration.version}_{migration.name}")
        else:
            print("No pending migrations.")
        return 0

    applied = migrate(args.db_path, args.migrations_dir)
    if applied:
        for migration in applied:
            print(f"Applied migration {migration.version}_{migration.name}")
    else:
        print("Database already up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
