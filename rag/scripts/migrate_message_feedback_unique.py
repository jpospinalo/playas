"""Check or explicitly add the one message-feedback unique index.

Reads DATABASE_URL from the environment without loading application config or
dotenv files. Existing SQLite files and PostgreSQL/asyncpg are supported. A
successful check with status ``ready`` is only a preflight: the index is absent.
No rows are updated, deleted or selected for automatic duplicate resolution.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, NoReturn
from urllib.parse import quote

from sqlalchemy import Column, Index, MetaData, String, Table, func, inspect, select, text
from sqlalchemy.engine import URL, Connection, make_url
from sqlalchemy.ext.asyncio import create_async_engine

TABLE_NAME = "message_feedback"
INDEX_NAME = "uq_message_feedback_user_message"
KEY_COLUMNS = ["user_id", "message_id"]
CONNECTION_TIMEOUT_SECONDS = 10
COMMAND_TIMEOUT_SECONDS = 30
LOCK_TIMEOUT_SECONDS = 5


@dataclass(frozen=True)
class MigrationReport:
    status: Literal["ready", "verified", "applied", "blocked", "error"]
    row_count: int | None = None
    duplicate_groups: int | None = None
    index_verified: bool = False


def _database_url(value: str, apply: bool) -> URL:
    """Select only an explicit database, never create a missing SQLite file."""
    url = make_url(value)
    if url.drivername == "postgresql+asyncpg":
        if not url.database:
            raise ValueError("An explicit PostgreSQL database is required")
        return url
    if url.drivername != "sqlite+aiosqlite":
        raise ValueError("Unsupported database driver")
    if url.host or url.username or url.password or url.port or url.query:
        raise ValueError("SQLite requires an unambiguous file URL without query options")
    if not url.database or url.database == ":memory:" or url.database.startswith("file:"):
        raise ValueError("An existing SQLite file is required")
    path = Path(url.database).expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError("An existing SQLite file is required")
    # URI open modes enforce non-creation even if the file disappears after stat.
    return URL.create(
        "sqlite+aiosqlite",
        database=f"file:{quote(str(path), safe='/')}",
        query={"mode": "rw" if apply else "ro", "uri": "true"},
    )


def _preflight(connection: Connection) -> MigrationReport:
    inspector = inspect(connection)
    sqlite = connection.dialect.name == "sqlite"
    schema = None if sqlite else inspector.default_schema_name
    if TABLE_NAME not in inspector.get_table_names(schema=schema):
        return MigrationReport("blocked")
    if sqlite:
        table_sql = connection.execute(
            text("SELECT sql FROM sqlite_schema WHERE type = 'table' AND name = :name"),
            {"name": TABLE_NAME},
        ).scalar_one()
        if not table_sql or "VIRTUAL TABLE" in table_sql.upper():
            return MigrationReport("blocked")
    else:
        kind = connection.execute(
            text(
                "SELECT c.relkind FROM pg_catalog.pg_class c "
                "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = :schema AND c.relname = :name"
            ),
            {"schema": schema, "name": TABLE_NAME},
        ).scalar_one_or_none()
        if kind != "r":
            return MigrationReport("blocked")

    columns = {column["name"]: column for column in inspector.get_columns(TABLE_NAME, schema)}
    primary = inspector.get_pk_constraint(TABLE_NAME, schema).get("constrained_columns")
    if primary != ["id"] or any(
        name not in columns
        or not isinstance(columns[name]["type"], String)
        or columns[name].get("nullable") is not False
        for name in ["id", *KEY_COLUMNS]
    ):
        return MigrationReport("blocked")

    table = Table(
        TABLE_NAME,
        MetaData(),
        *(Column(name, String) for name in KEY_COLUMNS),
        schema=schema,
    )
    row_count = int(connection.scalar(select(func.count()).select_from(table)) or 0)
    duplicates = (
        select(table.c.user_id, table.c.message_id)
        .group_by(table.c.user_id, table.c.message_id)
        .having(func.count() > 1)
        .subquery()
    )
    duplicate_groups = int(connection.scalar(select(func.count()).select_from(duplicates)) or 0)

    # An older equivalent unique index can win the same collision under its
    # own name. Do not create redundant enforcement which the exact API
    # classifier cannot safely recognize; leave that decision to the operator.
    constraints = inspector.get_unique_constraints(TABLE_NAME, schema)
    if sqlite and any(
        len(definition.get("column_names") or []) == 2
        and set(definition["column_names"]) == set(KEY_COLUMNS)
        for definition in constraints
    ):
        # SQLite enforces table constraints with autoindex names, even when
        # the logical constraint was given the requested index's name.
        return MigrationReport("blocked", row_count, duplicate_groups)
    unique_definitions: list[Mapping[str, Any]] = [
        *inspector.get_indexes(TABLE_NAME, schema),
        *({**definition, "unique": True} for definition in constraints),
    ]
    if any(
        definition.get("name") != INDEX_NAME
        and definition.get("unique")
        and len(definition.get("column_names") or []) == 2
        and set(definition["column_names"]) == set(KEY_COLUMNS)
        for definition in unique_definitions
    ):
        return MigrationReport("blocked", row_count, duplicate_groups)

    index_verified = False
    if sqlite:
        existing = connection.execute(
            text(
                "SELECT type, tbl_name FROM sqlite_schema "
                "WHERE type IN ('table', 'view', 'index') AND name = :name"
            ),
            {"name": INDEX_NAME},
        ).first()
        if existing is not None:
            definitions = connection.exec_driver_sql(
                f'PRAGMA index_list("{TABLE_NAME}")'
            ).mappings()
            sqlite_definition = next(
                (item for item in definitions if item["name"] == INDEX_NAME), None
            )
            keys = [
                item
                for item in connection.exec_driver_sql(
                    f'PRAGMA index_xinfo("{INDEX_NAME}")'
                ).mappings()
                if item["key"]
            ]
            index_verified = bool(
                existing[0] == "index"
                and existing[1] == TABLE_NAME
                and sqlite_definition is not None
                and sqlite_definition["unique"] == 1
                and sqlite_definition["partial"] == 0
                and [item["name"] for item in keys] == KEY_COLUMNS
                and all(item["desc"] == 0 and item["coll"] == "BINARY" for item in keys)
            )
            if not index_verified:
                return MigrationReport("blocked", row_count, duplicate_groups)
    else:
        existing = connection.execute(
            text(
                "SELECT c.relkind, t.relname, i.indisvalid, i.indisready, i.indimmediate, "
                "CASE WHEN i.indexrelid IS NOT NULL THEN pg_get_indexdef(c.oid, 1, true) END, "
                "CASE WHEN i.indexrelid IS NOT NULL THEN pg_get_indexdef(c.oid, 2, true) END "
                "FROM pg_catalog.pg_class c "
                "JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace "
                "LEFT JOIN pg_catalog.pg_index i ON i.indexrelid = c.oid "
                "LEFT JOIN pg_catalog.pg_class t ON t.oid = i.indrelid "
                "WHERE n.nspname = :schema AND c.relname = :name"
            ),
            {"schema": schema, "name": INDEX_NAME},
        ).first()
        if existing is not None:
            postgres_definition = next(
                (
                    item
                    for item in inspector.get_indexes(TABLE_NAME, schema)
                    if item["name"] == INDEX_NAME
                ),
                None,
            )
            index_verified = bool(
                existing[0] == "i"
                and existing[1] == TABLE_NAME
                and existing[2]
                and existing[3]
                and existing[4]
                and list(existing[5:7]) == KEY_COLUMNS
                and postgres_definition is not None
                and postgres_definition.get("unique") is True
                and postgres_definition.get("column_names") == KEY_COLUMNS
                and not postgres_definition.get("column_sorting")
                and not postgres_definition.get("include_columns")
                and not any(postgres_definition.get("dialect_options", {}).values())
            )
            if not index_verified:
                return MigrationReport("blocked", row_count, duplicate_groups)

    if duplicate_groups:
        return MigrationReport("blocked", row_count, duplicate_groups, index_verified)
    return MigrationReport(
        "verified" if index_verified else "ready", row_count, duplicate_groups, index_verified
    )


def _create_index(connection: Connection) -> None:
    table = Table(
        TABLE_NAME,
        MetaData(),
        *(Column(name, String) for name in KEY_COLUMNS),
        schema=None
        if connection.dialect.name == "sqlite"
        else inspect(connection).default_schema_name,
    )
    Index(INDEX_NAME, table.c.user_id, table.c.message_id, unique=True).create(connection)


async def migrate(database_url: str, *, apply: bool = False) -> MigrationReport:
    """Check or add this index only; database errors propagate without raw logs."""
    url = _database_url(database_url, apply)
    connect_args = (
        {"timeout": LOCK_TIMEOUT_SECONDS}
        if url.drivername == "sqlite+aiosqlite"
        else {"timeout": CONNECTION_TIMEOUT_SECONDS, "command_timeout": COMMAND_TIMEOUT_SECONDS}
    )
    engine = create_async_engine(url, connect_args=connect_args)
    try:
        async with engine.connect() as connection:
            try:
                if connection.dialect.name == "sqlite":
                    # A real BEGIN is required: legacy sqlite drivers otherwise
                    # execute standalone DDL outside the SQLAlchemy transaction.
                    await connection.exec_driver_sql("BEGIN IMMEDIATE" if apply else "BEGIN")
                else:
                    await connection.begin()
                    if not apply:
                        await connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                    await connection.exec_driver_sql(
                        f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT_SECONDS}s'"
                    )
                    await connection.exec_driver_sql(
                        f"SET LOCAL statement_timeout = '{COMMAND_TIMEOUT_SECONDS}s'"
                    )
                before = await connection.run_sync(_preflight)
                if before.status == "blocked":
                    await connection.rollback()
                    return before
                report = before
                if apply and not before.index_verified:
                    await connection.run_sync(_create_index)
                    after = await connection.run_sync(_preflight)
                    if not after.index_verified or after.row_count != before.row_count:
                        await connection.rollback()
                        return MigrationReport("blocked", after.row_count, after.duplicate_groups)
                    report = MigrationReport(
                        "applied", after.row_count, after.duplicate_groups, True
                    )
                await connection.commit()
                return report
            except BaseException:
                await connection.rollback()
                raise
    finally:
        await engine.dispose()


class _PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        # argparse's default includes invalid argv, which can contain a DSN.
        self.exit(2, "message_feedback_migration_invalid_arguments\n")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _PrivateArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Explicitly add the index if preflight passes"
    )
    args = parser.parse_args(argv)
    value = os.environ.get("DATABASE_URL", "").strip()
    if not value:
        print(json.dumps(asdict(MigrationReport("error"))))
        print("DATABASE_URL must explicitly select the existing database.", file=sys.stderr)
        return 2
    try:
        report = asyncio.run(migrate(value, apply=args.apply))
    except Exception as exc:
        # Database exceptions may contain URLs, SQL or values. Never print them.
        print(json.dumps(asdict(MigrationReport("error"))))
        print(f"message_feedback_migration_failed error_type={type(exc).__name__}", file=sys.stderr)
        return 1
    print(json.dumps(asdict(report)))
    return 1 if report.status == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
