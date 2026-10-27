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
    # Organización, institución o asociación (opcional; listado de tipos de usuario).
    organizacion: Mapped[str | None] = mapped_column(String)
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


class AwardDecision(Base):
    """Ganadora de "mejor pregunta" elegida por el comité cuando hay empate en
    Cv dentro de un nivel (el documento: decide el comité por pertinencia
    jurídica; la app no desempata sola)."""

    __tablename__ = "award_decision"

    nivel: Mapped[str] = mapped_column(String(1), primary_key=True)
    message_id: Mapped[str] = mapped_column(String, ForeignKey("messages.id"), nullable=False)
    decidido_por: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class QuestionNumber(Base):
    """ "ID pregunta" de la planilla: número fijo por pregunta, asignado en
    orden de llegada la primera vez que se ve. No cambia aunque después se
    agreguen o quiten participantes (PQ-56)."""

    __tablename__ = "question_number"

    message_id: Mapped[str] = mapped_column(String, ForeignKey("messages.id"), primary_key=True)
    numero: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AccountStatus(Base):
    """Cuenta desactivada sin borrar su historial (CHECKLIST-FINAL c2). Sin
    fila = cuenta activa."""

    __tablename__ = "account_status"

    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), primary_key=True)
    activa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    cambiada_por: Mapped[str | None] = mapped_column(String)
    cambiada_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AdminAudit(Base):
    """Auditoría de acciones de administración y del comité (c7)."""

    __tablename__ = "admin_audit"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    actor_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    accion: Mapped[str] = mapped_column(String, nullable=False)
    objetivo_id: Mapped[str | None] = mapped_column(String)
    detalle: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class PrivacyConsent(Base):
    """Autorización de tratamiento de datos (Ley 1581 / Decreto 1377, c8):
    fecha y versión del aviso aceptado, como prueba."""

    __tablename__ = "privacy_consent"

    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), primary_key=True)
    version: Mapped[str] = mapped_column(String, nullable=False)
    aceptada_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class QuestionAssignment(Base):
    """Reunión del 20-oct (T1): cada pregunta se asigna sola a un semillerista
    de cada sede, repartiendo por igual. Una fila por pregunta y sede."""

    __tablename__ = "question_assignment"

    message_id: Mapped[str] = mapped_column(String, ForeignKey("messages.id"), primary_key=True)
    sede: Mapped[str] = mapped_column(String, primary_key=True)
    evaluador_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    # Si se reasignó (evaluador desactivado o reasignación del admin), de quién venía.
    reasignada_de: Mapped[str | None] = mapped_column(String)


class ValidatorProfile(Base):
    """Reunión del 20-oct (T3): tipo de validación de una cuenta del comité.
    "juridico" (Ana María, Sandra) valida las evaluaciones de su sede
    (exercise_profile.sede); "costero" (Camilo) revisa si cada pregunta es del
    tema."""

    __tablename__ = "validator_profile"

    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), primary_key=True)
    tipo: Mapped[str] = mapped_column(String, nullable=False)


class EvaluationReview(Base):
    """Validación jurídica de una evaluación (T2-T4): de acuerdo o no. Se
    guardan todas; vale la última, y solo si es posterior a la última
    corrección del semillerista."""

    __tablename__ = "evaluation_review"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    evaluation_id: Mapped[str] = mapped_column(
        String, ForeignKey("question_evaluation.id"), nullable=False, index=True
    )
    validador_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    de_acuerdo: Mapped[bool] = mapped_column(Boolean, nullable=False)
    comentario: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class EvaluationComment(Base):
    """Conversación entre validador y semillerista sobre una evaluación (T4).
    tipo: "comentario", "desacuerdo", "acuerdo" o "correccion" (antes → después)."""

    __tablename__ = "evaluation_comment"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    evaluation_id: Mapped[str] = mapped_column(
        String, ForeignKey("question_evaluation.id"), nullable=False, index=True
    )
    autor_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    tipo: Mapped[str] = mapped_column(String, default="comentario", nullable=False)
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PertinenceReview(Base):
    """Revisión de gestión costera (T3, E7): ¿la pregunta es del tema de
    playas? "No pertinente" la saca de premios y gratificación."""

    __tablename__ = "pertinence_review"

    message_id: Mapped[str] = mapped_column(String, ForeignKey("messages.id"), primary_key=True)
    validador_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), nullable=False)
    pertinente: Mapped[bool] = mapped_column(Boolean, nullable=False)
    comentario: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PracticeAccount(Base):
    """Reunión del 20-oct (T7): cuenta de práctica (participante o semillerista
    de prueba para la semana antes del 2 nov). Sus preguntas se evalúan para
    practicar pero no cuentan para nada; un semillerista de práctica no recibe
    preguntas reales (E5)."""

    __tablename__ = "practice_account"

    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ExerciseSetting(Base):
    """Ajustes del ejercicio que cambia el admin (práctica archivada, fechas del
    calendario, días de la ventana del participante)."""

    __tablename__ = "exercise_setting"

    clave: Mapped[str] = mapped_column(String, primary_key=True)
    valor: Mapped[str] = mapped_column(String, nullable=False)
    updated_by: Mapped[str | None] = mapped_column(String)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
