"""Motor SQLAlchemy async y helper de sesión para el backend RAG."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import Connection, MetaData, inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from rag.config import DATABASE_URL as _DATABASE_URL

_connect_args = {"check_same_thread": False} if "sqlite" in _DATABASE_URL else {}

engine = create_async_engine(_DATABASE_URL, echo=False, connect_args=_connect_args)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


def _add_missing_nullable_columns(conn: Connection, metadata: MetaData) -> None:
    """Agrega a tablas ya existentes las columnas opcionales nuevas del modelo.

    ``create_all`` solo crea tablas que faltan; no altera las existentes. Sin
    esto, sumar una columna al modelo (p. ej. ``users.user_type``) rompe toda
    lectura de esa tabla en una base desplegada antes del cambio. Solo agrega
    columnas *nullable* (seguro en SQLite y PostgreSQL, sin reescribir datos);
    una columna obligatoria nueva sigue necesitando una migración explícita.
    """
    inspector = inspect(conn)
    for table in metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing or not column.nullable:
                continue
            col_type = column.type.compile(dialect=conn.dialect)
            conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'))


async def init_db() -> None:
    from rag.api.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_nullable_columns, Base.metadata)
