"""Modelos SQLAlchemy para usuarios, conversaciones, mensajes y feedback."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _now() -> datetime:
    return datetime.now(UTC)


def _uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str | None] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, default="user", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    conversations: Mapped[list[Conversation]] = relationship(back_populates="user")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False, index=True)
    thread_id: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    message_count: Mapped[int] = mapped_column(Integer, default=0)

    user: Mapped[User] = relationship(back_populates="conversations")
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation", order_by="Message.created_at"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(
        String, ForeignKey("conversations.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    user_email: Mapped[str] = mapped_column(String, default="")
    ratings: Mapped[dict] = mapped_column(JSON, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    conversation_id: Mapped[str | None] = mapped_column(String)
    conversation_title: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MessageFeedback(Base):
    __tablename__ = "message_feedback"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    user_email: Mapped[str] = mapped_column(String, default="")
    conversation_id: Mapped[str] = mapped_column(String, nullable=False)
    message_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    ratings: Mapped[dict] = mapped_column(JSON, nullable=False)
    expected_answer: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


# ── Ejercicio de validación (tablas nuevas; no alteran las anteriores) ────────


class ExerciseProfile(Base):
    """Datos del ejercicio de validación para una cuenta.

    Participantes: número de participante (``codigo``) y tipo de usuario de
    playa (``tipo_playa``, uno de los 5 del ejercicio). Evaluadores
    (semilleristas): ``sede`` (Santa Marta o Barranquilla). El rol sigue en
    ``users.role`` (user, evaluador, comite, admin).
    """

    __tablename__ = "exercise_profile"

    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), primary_key=True)
    codigo: Mapped[str | None] = mapped_column(String, unique=True, index=True)
    tipo_playa: Mapped[int | None] = mapped_column(Integer)
    sede: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class QuestionEvaluation(Base):
    """Calificación de una pregunta (mensaje ``user``) con la planilla del
    ejercicio: forma F1-F3 (1 a 3), complejidad Ct (S/I/A) y valor Cv dentro
    del rango de Ct. Cada evaluador califica una vez cada pregunta; la
    calificación del comité lleva ``es_final`` (columna "Revisó")."""

    __tablename__ = "question_evaluation"
    __table_args__ = (UniqueConstraint("message_id", "evaluador_id", "es_final"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    message_id: Mapped[str] = mapped_column(
        String, ForeignKey("messages.id"), nullable=False, index=True
    )
    evaluador_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    sede: Mapped[str | None] = mapped_column(String)
    f1: Mapped[int] = mapped_column(Integer, nullable=False)
    f2: Mapped[int] = mapped_column(Integer, nullable=False)
    f3: Mapped[int] = mapped_column(Integer, nullable=False)
    ct: Mapped[str] = mapped_column(String(1), nullable=False)
    cv: Mapped[int] = mapped_column(Integer, nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False)
    valida: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    observaciones: Mapped[str | None] = mapped_column(Text)
    es_final: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
