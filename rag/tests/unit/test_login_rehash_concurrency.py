"""Rehash must preserve concurrent credential writes, using real SQLite sessions.

Only verification/hash computation is held at barriers. The routes, SQL writes,
commits and rollbacks are real in races; this is not PostgreSQL certification.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import bcrypt
import pytest
from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import rag.api.routes.admin as admin_module
import rag.api.routes.auth as auth_module
from rag.api.auth import _decode
from rag.api.models import Base, User
from rag.api.passwords import verify_password
from rag.api.routes.auth import LoginRequest, TokenResponse
from rag.api.schemas import UpdatePasswordRequest

_USER = "synthetic-rehash-user"
_EMAIL = "rehash@example.invalid"
_OLD_PASSWORD = "synthetic-old-password"
_NEW_PASSWORD = "synthetic-admin-password"
_ADMIN = {"sub": "synthetic-admin", "role": "admin"}
_WAIT = 3.0


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _test_hash(password: str, *, current: bool) -> str:
    """Cheap synthetic hashes in the supported formats; never change product cost."""
    raw = hashlib.sha256(password.encode()).digest() if current else password.encode()
    value = bcrypt.hashpw(raw, bcrypt.gensalt(rounds=4)).decode()
    return f"v2:{value}" if current else value


@dataclass
class _Database:
    sessions: async_sessionmaker[AsyncSession]
    original: str
    administrative: str
    replacement: str

    async def stored_hash(self) -> str:
        async with self.sessions() as session:
            user = await session.get(User, _USER)
            assert user is not None
            return user.password_hash


@pytest.fixture
async def rehash_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[_Database]:
    monkeypatch.setenv("JWT_SECRET_KEY", "synthetic-rehash-secret-with-sufficient-entropy")
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'rehash.sqlite'}", connect_args={"timeout": 1}
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    database = _Database(
        sessions,
        _test_hash(_OLD_PASSWORD, current=False),
        _test_hash(_NEW_PASSWORD, current=True),
        _test_hash(_OLD_PASSWORD, current=True),
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with sessions() as session:
            session.add(
                User(
                    id=_USER,
                    email=_EMAIL,
                    password_hash=database.original,
                    display_name="Synthetic user",
                    role="user",
                )
            )
            await session.commit()
        yield database
    finally:
        await engine.dispose()


class _Gate:
    def __init__(self) -> None:
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def hold(self) -> None:
        self.entered.set()
        await asyncio.wait_for(self.release.wait(), timeout=_WAIT)

    async def wait(self) -> None:
        await asyncio.wait_for(self.entered.wait(), timeout=_WAIT)


async def _finish(task: asyncio.Task):
    return await asyncio.wait_for(asyncio.shield(task), timeout=_WAIT)


async def _collect(*tasks: asyncio.Task) -> None:
    for task in tasks:
        if not task.done():
            task.cancel()
    await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=_WAIT)


async def _login(database: _Database) -> TokenResponse:
    async with database.sessions() as session:
        return await auth_module.login(
            LoginRequest(email=_EMAIL, password=_OLD_PASSWORD),
            Request(scope={"type": "http", "client": ("127.0.0.1", 12345), "headers": []}),
            session=session,
        )


async def _reset(database: _Database) -> None:
    async with database.sessions() as session:
        await admin_module.update_user_password(
            _USER,
            UpdatePasswordRequest(password=_NEW_PASSWORD),
            _admin=_ADMIN,
            session=session,
        )


def _assert_login(response: TokenResponse) -> None:
    assert response.user_id == _USER
    assert response.email == _EMAIL
    assert response.display_name == "Synthetic user"
    assert response.role == "user"
    assert response.token_type == "bearer"
    assert _decode(response.access_token)["sub"] == _USER


@pytest.mark.anyio
@pytest.mark.parametrize("stage", ["verify", "rehash"])
async def test_confirmed_admin_password_is_not_overwritten_by_a_stale_login(
    rehash_database: _Database, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    database = rehash_database
    gate = _Gate()
    verified_hashes: list[str] = []

    async def verify(password: str, hashed: str) -> bool:
        verified_hashes.append(hashed)
        valid = verify_password(password, hashed)
        if stage == "verify":
            await gate.hold()
        return valid

    async def rehash(password: str) -> str:
        assert password == _OLD_PASSWORD
        if stage == "rehash":
            await gate.hold()
        return database.replacement

    monkeypatch.setattr(auth_module, "verify_password_async", verify)
    monkeypatch.setattr(auth_module, "hash_password_async", rehash)
    monkeypatch.setattr(
        admin_module, "hash_password_async", AsyncMock(return_value=database.administrative)
    )
    login_task = asyncio.create_task(_login(database))
    reset_task: asyncio.Task | None = None
    try:
        await gate.wait()
        reset_task = asyncio.create_task(_reset(database))
        await _finish(reset_task)
        assert await database.stored_hash() == database.administrative
        gate.release.set()
        _assert_login(await _finish(login_task))
        assert verified_hashes == [database.original]
        stored = await database.stored_hash()
        assert stored == database.administrative
        assert verify_password(_NEW_PASSWORD, stored)
        assert not verify_password(_OLD_PASSWORD, stored)
    finally:
        gate.release.set()
        await _collect(login_task, *([reset_task] if reset_task is not None else []))


@pytest.mark.anyio
async def test_admin_reset_finishing_after_rehash_remains_the_final_credential(
    rehash_database: _Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = rehash_database
    gate = _Gate()

    async def administrative_hash(password: str) -> str:
        assert password == _NEW_PASSWORD
        await gate.hold()
        return database.administrative

    monkeypatch.setattr(admin_module, "hash_password_async", administrative_hash)
    monkeypatch.setattr(
        auth_module, "hash_password_async", AsyncMock(return_value=database.replacement)
    )
    reset_task = asyncio.create_task(_reset(database))
    login_task: asyncio.Task | None = None
    try:
        await gate.wait()
        login_task = asyncio.create_task(_login(database))
        _assert_login(await _finish(login_task))
        assert await database.stored_hash() == database.replacement
        gate.release.set()
        await _finish(reset_task)
        stored = await database.stored_hash()
        assert stored == database.administrative
        assert verify_password(_NEW_PASSWORD, stored)
        assert not verify_password(_OLD_PASSWORD, stored)
    finally:
        gate.release.set()
        await _collect(reset_task, *([login_task] if login_task is not None else []))


@pytest.mark.anyio
async def test_second_rehash_does_not_overwrite_the_first_confirmed_replacement(
    rehash_database: _Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = rehash_database
    gates = [_Gate(), _Gate()]
    replacements = [database.replacement, _test_hash(_OLD_PASSWORD, current=True)]
    calls = 0

    async def rehash(password: str) -> str:
        nonlocal calls
        assert password == _OLD_PASSWORD
        position = calls
        calls += 1
        await gates[position].hold()
        return replacements[position]

    monkeypatch.setattr(auth_module, "hash_password_async", rehash)
    first = asyncio.create_task(_login(database))
    second: asyncio.Task | None = None
    try:
        await gates[0].wait()
        second = asyncio.create_task(_login(database))
        await gates[1].wait()
        gates[0].release.set()
        _assert_login(await _finish(first))
        assert await database.stored_hash() == replacements[0]
        gates[1].release.set()
        _assert_login(await _finish(second))
        assert await database.stored_hash() == replacements[0]
        assert calls == 2
    finally:
        for gate in gates:
            gate.release.set()
        await _collect(first, *([second] if second is not None else []))


@pytest.mark.anyio
async def test_sql_update_failure_rolls_back_without_rejecting_a_valid_login(
    rehash_database: _Database, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    database = rehash_database
    private_error = "SYNTHETIC_PRIVATE_SQL_REHASH_FAILURE"
    async with database.sessions() as setup:
        await setup.execute(
            text(
                "CREATE TRIGGER reject_rehash BEFORE UPDATE OF password_hash ON users "
                f"BEGIN SELECT RAISE(ABORT, '{private_error}'); END"
            )
        )
        await setup.commit()
    monkeypatch.setattr(
        auth_module, "hash_password_async", AsyncMock(return_value=database.replacement)
    )
    async with database.sessions() as session:
        rollback = AsyncMock(wraps=session.rollback)
        monkeypatch.setattr(session, "rollback", rollback)
        with caplog.at_level(logging.WARNING, logger=auth_module.__name__):
            response = await auth_module.login(
                LoginRequest(email=_EMAIL, password=_OLD_PASSWORD),
                Request(scope={"type": "http", "client": ("127.0.0.1", 12345), "headers": []}),
                session=session,
            )
        rollback.assert_awaited_once()
        assert not session.in_transaction()
    _assert_login(response)
    assert await database.stored_hash() == database.original
    assert "opportunistic_password_rehash_failed" in caplog.text
    assert private_error not in caplog.text
    assert database.original not in caplog.text
    assert database.replacement not in caplog.text
    assert _OLD_PASSWORD not in caplog.text
    records = [record for record in caplog.records if record.name == auth_module.__name__]
    assert records
    assert all(record.exc_info is None for record in records)


@pytest.mark.anyio
async def test_cancelling_rehash_does_not_issue_a_token_or_write_later(
    rehash_database: _Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = rehash_database
    gate = _Gate()
    hash_exited = asyncio.Event()

    async def rehash(password: str) -> str:
        assert password == _OLD_PASSWORD
        try:
            await gate.hold()
            return database.replacement
        finally:
            hash_exited.set()

    token = Mock(return_value="unexpected-synthetic-token")
    monkeypatch.setattr(auth_module, "hash_password_async", rehash)
    monkeypatch.setattr(auth_module, "create_access_token", token)
    login_task = asyncio.create_task(_login(database))
    try:
        await gate.wait()
        login_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await _finish(login_task)
        await asyncio.wait_for(hash_exited.wait(), timeout=_WAIT)
        gate.release.set()
        assert login_task.done()
        token.assert_not_called()
        assert await database.stored_hash() == database.original
    finally:
        gate.release.set()
        await _collect(login_task)


@pytest.mark.anyio
async def test_rollback_failure_propagates_instead_of_inventing_a_successful_login(
    rehash_database: _Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    database = rehash_database
    failure = RuntimeError("synthetic-rollback-failure")
    monkeypatch.setattr(
        auth_module,
        "hash_password_async",
        AsyncMock(side_effect=ValueError("synthetic-hash-error")),
    )
    token = Mock(return_value="unexpected-synthetic-token")
    monkeypatch.setattr(auth_module, "create_access_token", token)
    async with database.sessions() as session:
        rollback = AsyncMock(side_effect=failure)
        monkeypatch.setattr(session, "rollback", rollback)
        with pytest.raises(RuntimeError) as raised:
            await auth_module.login(
                LoginRequest(email=_EMAIL, password=_OLD_PASSWORD),
                Request(scope={"type": "http", "client": ("127.0.0.1", 12345), "headers": []}),
                session=session,
            )
        assert raised.value is failure
        rollback.assert_awaited_once()
    token.assert_not_called()
    assert await database.stored_hash() == database.original
