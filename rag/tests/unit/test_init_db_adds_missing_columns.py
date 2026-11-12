"""init_db debe actualizar bases ya desplegadas, no solo crear las nuevas.

``create_all`` no agrega columnas a tablas existentes: al sumar ``users.user_type``
al modelo, una base creada antes (la de AWS o la demo local) quedaba sin la
columna y cualquier lectura de usuario fallaba (login, /auth/me y todo endpoint
autenticado → 500 «no such column: users.user_type»).
"""

from __future__ import annotations

import asyncio
import sqlite3

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from rag.api import database
from rag.api.models import User


def test_init_db_adds_columns_missing_from_an_existing_users_table(tmp_path, monkeypatch):
    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE users (id VARCHAR PRIMARY KEY, email VARCHAR UNIQUE NOT NULL, "
        "password_hash VARCHAR NOT NULL, display_name VARCHAR, role VARCHAR NOT NULL, "
        "created_at DATETIME)"
    )
    con.execute("INSERT INTO users VALUES ('u1', 'a@b.co', 'x', 'Ana', 'user', NULL)")
    con.commit()
    con.close()

    async def scenario() -> User | None:
        engine = create_async_engine(f"sqlite+aiosqlite:///{db}")
        monkeypatch.setattr(database, "engine", engine)
        await database.init_db()
        await database.init_db()  # idempotente: la segunda vez no intenta re-agregarla
        async with async_sessionmaker(engine)() as session:
            found = await session.get(User, "u1")
        await engine.dispose()
        return found

    user = asyncio.run(scenario())

    assert user is not None
    assert user.email == "a@b.co"
    assert user.user_type is None
