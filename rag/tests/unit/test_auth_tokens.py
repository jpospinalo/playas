"""Controles del contrato JWT."""

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import rag.api.database as database_module
from rag.api.auth import _decode, create_access_token, get_current_user
from rag.api.models import Base, User


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_token_requires_configured_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        create_access_token("user-1", "u1@example.com", "user")


def test_token_contains_required_identity_claims(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret-with-enough-entropy-for-unit-tests")
    token = create_access_token("user-1", "u1@example.com", "admin")
    payload = _decode(token)
    assert payload["sub"] == "user-1"
    assert payload["email"] == "u1@example.com"
    assert payload["role"] == "admin"
    assert "iat" in payload
    assert "exp" in payload


@pytest.mark.anyio
async def test_current_user_refreshes_profile_from_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        session.add(
            User(
                id="user-1",
                email="actual@example.com",
                display_name="Usuario actual",
                password_hash="hash",
                role="admin",
            )
        )
        await session.commit()

    monkeypatch.setattr(database_module, "async_session_factory", session_factory)
    result = await get_current_user({"sub": "user-1", "email": "old@example.com", "role": "user"})

    assert result["email"] == "actual@example.com"
    assert result["display_name"] == "Usuario actual"
    assert result["role"] == "admin"
    await engine.dispose()
