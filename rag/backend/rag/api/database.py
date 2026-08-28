"""Motor SQLAlchemy async y helper de sesión para el backend RAG."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from rag.config import DATABASE_URL as _DATABASE_URL

_connect_args = {"check_same_thread": False} if "sqlite" in _DATABASE_URL else {}

engine = create_async_engine(_DATABASE_URL, echo=False, connect_args=_connect_args)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


async def init_db() -> None:
    from rag.api.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
