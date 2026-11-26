"""A02 migration contracts against existing, synthetic SQLite files only.

These tests neither connect to PostgreSQL nor certify its DDL/locking behavior.
The legacy schema is built independently of the application's current metadata.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from scripts import migrate_message_feedback_unique as migration

_TABLE_DDL = (
    "CREATE TABLE message_feedback ("
    "id VARCHAR NOT NULL PRIMARY KEY, user_id VARCHAR NOT NULL, "
    "user_email VARCHAR NOT NULL, conversation_id VARCHAR NOT NULL, "
    "message_id VARCHAR NOT NULL, ratings JSON NOT NULL, "
    "expected_answer TEXT, created_at DATETIME NOT NULL)"
)
_INSERT = text(
    "INSERT INTO message_feedback "
    "(id, user_id, user_email, conversation_id, message_id, ratings, expected_answer, created_at) "
    "VALUES (:id, :user_id, :email, :conversation_id, :message_id, :ratings, :answer, :created_at)"
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _row(ident: str, message_id: str = "message-a", user_id: str = "user-a") -> dict:
    return {
        "id": ident,
        "user_id": user_id,
        "email": "synthetic@example.invalid",
        "conversation_id": "conversation-a",
        "message_id": message_id,
        "ratings": json.dumps({"pertinence": 4, "accuracy": 5}),
        "answer": "Synthetic expected answer.",
        "created_at": "2026-01-01 12:00:00.000000",
    }


async def _legacy(
    path: Path,
    *,
    rows: list[dict] | None = None,
    table_ddl: str = _TABLE_DDL,
    index_ddl: str | None = None,
) -> str:
    url = f"sqlite+aiosqlite:///{path}"
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.exec_driver_sql(table_ddl)
            if rows:
                await connection.execute(_INSERT, rows)
            if index_ddl:
                await connection.exec_driver_sql(index_ddl)
    finally:
        await engine.dispose()
    return url


async def _snapshot(url: str) -> tuple[list[tuple], list[tuple]]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            rows = await connection.execute(text("SELECT * FROM message_feedback ORDER BY id"))
            schema = await connection.execute(
                text("SELECT type, name, tbl_name, sql FROM sqlite_schema ORDER BY type, name")
            )
            return [tuple(row) for row in rows], [tuple(row) for row in schema]
    finally:
        await engine.dispose()


@pytest.mark.anyio
@pytest.mark.parametrize("populated", [False, True], ids=["empty", "populated"])
async def test_check_then_apply_preserves_rows_and_enforces_only_the_pair(
    tmp_path: Path, populated: bool
) -> None:
    path = tmp_path / "legacy with spaces.sqlite"
    initial_rows = [_row("feedback-a"), _row("feedback-b", "message-b")] if populated else []
    url = await _legacy(path, rows=initial_rows)
    before_rows, before_schema = await _snapshot(url)
    before_mode = path.stat().st_mode

    ready = await migration.migrate(url)
    assert ready == migration.MigrationReport("ready", len(initial_rows), 0, False)
    assert await _snapshot(url) == (before_rows, before_schema)

    applied = await migration.migrate(url, apply=True)
    assert applied == migration.MigrationReport("applied", len(initial_rows), 0, True)
    after_rows, after_schema = await _snapshot(url)
    assert after_rows == before_rows
    assert [
        row for row in after_schema if row[0] != "index" or row[1] != migration.INDEX_NAME
    ] == before_schema
    assert path.stat().st_mode == before_mode

    engine = create_async_engine(url)
    try:
        if not populated:
            async with engine.begin() as connection:
                await connection.execute(_INSERT, _row("feedback-a"))
        async with engine.begin() as connection:
            with pytest.raises(IntegrityError):
                await connection.execute(_INSERT, _row("duplicate-a"))
        async with engine.begin() as connection:
            await connection.execute(_INSERT, _row("different-message", "message-c"))
            await connection.execute(_INSERT, _row("different-user", user_id="user-b"))
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_correct_existing_index_is_verified_without_recreation(tmp_path: Path) -> None:
    url = await _legacy(
        tmp_path / "already.sqlite",
        rows=[_row("feedback-a")],
        index_ddl=(
            f"CREATE UNIQUE INDEX {migration.INDEX_NAME} ON message_feedback (user_id, message_id)"
        ),
    )
    before = await _snapshot(url)
    for apply in (False, True):
        report = await migration.migrate(url, apply=apply)
        assert report == migration.MigrationReport("verified", 1, 0, True)
        assert await _snapshot(url) == before


@pytest.mark.anyio
async def test_legacy_duplicates_block_without_changing_rows_or_schema(tmp_path: Path) -> None:
    rows = [_row("first"), _row("second"), _row("other", "message-b")]
    rows[1]["answer"] = "A different synthetic answer, never automatically selected."
    url = await _legacy(tmp_path / "duplicates.sqlite", rows=rows)
    before = await _snapshot(url)
    for apply in (False, True):
        report = await migration.migrate(url, apply=apply)
        assert report == migration.MigrationReport("blocked", 3, 1, False)
        assert await _snapshot(url) == before


@pytest.mark.anyio
@pytest.mark.parametrize("apply", [False, True])
async def test_missing_sqlite_file_is_not_created(tmp_path: Path, apply: bool) -> None:
    path = tmp_path / "absent.sqlite"
    with pytest.raises(FileNotFoundError):
        await migration.migrate(f"sqlite+aiosqlite:///{path}", apply=apply)
    assert not path.exists()


@pytest.mark.anyio
@pytest.mark.parametrize("apply", [False, True])
async def test_uri_mode_prevents_creation_if_file_disappears_after_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, apply: bool
) -> None:
    path = tmp_path / "disappearing.sqlite"
    url = await _legacy(path)
    original = migration._database_url

    def select_then_remove(value: str, selected_apply: bool):
        selected = original(value, selected_apply)
        path.unlink()
        return selected

    monkeypatch.setattr(migration, "_database_url", select_then_remove)
    with pytest.raises(DBAPIError):
        await migration.migrate(url, apply=apply)
    assert not path.exists()


@pytest.mark.anyio
async def test_default_check_connection_cannot_execute_ddl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = await _legacy(tmp_path / "readonly.sqlite", rows=[_row("feedback-a")])
    before = await _snapshot(url)
    original = migration._preflight

    def attempt_write(connection: Connection):
        with pytest.raises(DBAPIError, match="readonly"):
            connection.exec_driver_sql("CREATE TABLE forbidden_write (id INTEGER)")
        return original(connection)

    monkeypatch.setattr(migration, "_preflight", attempt_write)
    assert (await migration.migrate(url)).status == "ready"
    assert await _snapshot(url) == before


@pytest.mark.anyio
@pytest.mark.parametrize(
    "definition",
    [
        "CREATE INDEX {name} ON message_feedback (user_id, message_id)",
        "CREATE UNIQUE INDEX {name} ON message_feedback (message_id, user_id)",
        "CREATE UNIQUE INDEX {name} ON message_feedback (user_id)",
        "CREATE UNIQUE INDEX {name} ON message_feedback (user_id, message_id) WHERE user_id != ''",
        "CREATE UNIQUE INDEX {name} ON message_feedback (lower(user_id), message_id)",
        "CREATE UNIQUE INDEX {name} ON message_feedback (user_id COLLATE NOCASE, message_id)",
        "CREATE UNIQUE INDEX {name} ON message_feedback (user_id DESC, message_id)",
    ],
    ids=[
        "not-unique",
        "reversed",
        "other-columns",
        "partial",
        "expression",
        "collation",
        "descending",
    ],
)
async def test_incompatible_named_index_stops_without_ddl(tmp_path: Path, definition: str) -> None:
    url = await _legacy(
        tmp_path / "incompatible.sqlite",
        rows=[_row("feedback-a")],
        index_ddl=definition.format(name=migration.INDEX_NAME),
    )
    before = await _snapshot(url)
    for apply in (False, True):
        report = await migration.migrate(url, apply=apply)
        assert report.status == "blocked" and not report.index_verified
        assert await _snapshot(url) == before


@pytest.mark.anyio
@pytest.mark.parametrize("as_constraint", [False, True], ids=["index", "table-constraint"])
async def test_equivalent_uniqueness_under_another_name_is_not_duplicated(
    tmp_path: Path, as_constraint: bool
) -> None:
    ddl = _TABLE_DDL
    index_ddl = "CREATE UNIQUE INDEX legacy_unique_pair ON message_feedback (message_id, user_id)"
    if as_constraint:
        ddl = _TABLE_DDL[:-1] + ", CONSTRAINT legacy_unique_pair UNIQUE (user_id, message_id))"
        index_ddl = None
    url = await _legacy(
        tmp_path / "legacy-unique.sqlite",
        rows=[_row("feedback-a")],
        table_ddl=ddl,
        index_ddl=index_ddl,
    )
    before = await _snapshot(url)
    report = await migration.migrate(url, apply=True)
    assert report == migration.MigrationReport("blocked", 1, 0, False)
    assert await _snapshot(url) == before


@pytest.mark.anyio
async def test_reserved_index_name_occupied_by_a_table_blocks_preflight(tmp_path: Path) -> None:
    url = await _legacy(tmp_path / "occupied-name.sqlite", rows=[_row("feedback-a")])
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.exec_driver_sql(f"CREATE TABLE {migration.INDEX_NAME} (id INTEGER)")
    finally:
        await engine.dispose()
    before = await _snapshot(url)
    for apply in (False, True):
        report = await migration.migrate(url, apply=apply)
        assert report == migration.MigrationReport("blocked", 1, 0, False)
        assert await _snapshot(url) == before


@pytest.mark.anyio
async def test_named_table_constraint_is_not_mistaken_for_the_physical_named_index(
    tmp_path: Path,
) -> None:
    ddl = _TABLE_DDL[:-1] + f", CONSTRAINT {migration.INDEX_NAME} UNIQUE (user_id, message_id))"
    url = await _legacy(tmp_path / "constraint.sqlite", table_ddl=ddl, rows=[_row("feedback-a")])
    before = await _snapshot(url)
    assert await migration.migrate(url, apply=True) == migration.MigrationReport("blocked", 1, 0)
    assert await _snapshot(url) == before


@pytest.mark.anyio
@pytest.mark.parametrize(
    "ddl",
    [
        "CREATE TABLE other_table (id VARCHAR PRIMARY KEY)",
        "CREATE TABLE message_feedback (id VARCHAR NOT NULL PRIMARY KEY, user_id VARCHAR NOT NULL)",
        "CREATE TABLE message_feedback (id VARCHAR NOT NULL PRIMARY KEY, user_id VARCHAR, message_id VARCHAR NOT NULL)",
        "CREATE TABLE message_feedback (id VARCHAR NOT NULL PRIMARY KEY, user_id INTEGER NOT NULL, message_id VARCHAR NOT NULL)",
        "CREATE TABLE message_feedback (id VARCHAR NOT NULL, user_id VARCHAR NOT NULL, message_id VARCHAR NOT NULL)",
        "CREATE VIEW message_feedback AS SELECT 'id' AS id, 'user' AS user_id, 'msg' AS message_id",
    ],
    ids=["missing-table", "missing-column", "nullable-key", "wrong-type", "missing-pk", "view"],
)
async def test_incompatible_schema_stops_without_adding_index(tmp_path: Path, ddl: str) -> None:
    url = await _legacy(tmp_path / "schema.sqlite", table_ddl=ddl)
    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            before = list(
                await connection.execute(text("SELECT sql FROM sqlite_schema ORDER BY name"))
            )
        report = await migration.migrate(url, apply=True)
        assert report.status == "blocked"
        async with engine.connect() as connection:
            after = list(
                await connection.execute(text("SELECT sql FROM sqlite_schema ORDER BY name"))
            )
        assert after == before
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_failure_after_real_create_index_rolls_back_ddl_and_keeps_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = await _legacy(tmp_path / "rollback.sqlite", rows=[_row("feedback-a")])
    before = await _snapshot(url)
    original = migration._create_index

    def create_then_fail(connection: Connection) -> None:
        original(connection)
        assert (
            connection.execute(
                text("SELECT name FROM sqlite_schema WHERE type = 'index' AND name = :name"),
                {"name": migration.INDEX_NAME},
            ).scalar_one()
            == migration.INDEX_NAME
        )
        raise RuntimeError("synthetic failure after the DDL")

    with monkeypatch.context() as patch:
        patch.setattr(migration, "_create_index", create_then_fail)
        with pytest.raises(RuntimeError, match="after the DDL"):
            await migration.migrate(url, apply=True)
    assert await _snapshot(url) == before
    assert (await migration.migrate(url)).status == "ready"
    assert (await migration.migrate(url, apply=True)).status == "applied"


def test_cli_requires_explicit_environment_without_printing_credentials(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert migration.main([]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out)["status"] == "error"
    assert "DATABASE_URL" in captured.err


def test_cli_failure_does_not_print_url_credentials_or_exception_details(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    private_url = "postgresql+asyncpg://private-user:PRIVATE-PASSWORD@private-host/private-db"

    async def fail(_url: str, *, apply: bool):
        raise RuntimeError(private_url, "PRIVATE-SQL-OR-PARAMETER", apply)

    monkeypatch.setenv("DATABASE_URL", private_url)
    monkeypatch.setattr(migration, "migrate", fail)
    assert migration.main(["--apply"]) == 1
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "status": "error",
        "row_count": None,
        "duplicate_groups": None,
        "index_verified": False,
    }
    assert captured.err.strip() == "message_feedback_migration_failed error_type=RuntimeError"
    assert "PRIVATE" not in captured.out + captured.err
    assert "private-user" not in captured.out + captured.err


@pytest.mark.parametrize(
    "argv",
    [
        [
            "--database-url",
            "postgresql+asyncpg://private-user:PRIVATE-PASSWORD@private-host/private-db",
        ],
        ["--apply=PRIVATE-APPLY-VALUE"],
    ],
    ids=["unknown-dsn-option", "unexpected-apply-value"],
)
def test_cli_argument_errors_do_not_echo_sensitive_arguments(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], argv: list[str]
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(SystemExit) as error:
        migration.main(argv)
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == "message_feedback_migration_invalid_arguments"
    assert "PRIVATE" not in captured.err
    assert "private-user" not in captured.err
    assert "private-host" not in captured.err


@pytest.mark.anyio
@pytest.mark.parametrize(
    "value",
    [
        "sqlite+aiosqlite:///:memory:",
        "sqlite+aiosqlite:///absent.sqlite?mode=rwc",
        "sqlite+aiosqlite:///file:absent.sqlite",
        "sqlite:///absent.sqlite",
        "postgresql://synthetic:secret@host/db",
    ],
)
async def test_unsupported_or_ambiguous_destinations_are_rejected(value: str) -> None:
    with pytest.raises(ValueError):
        await migration.migrate(value)
