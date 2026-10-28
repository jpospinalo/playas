"""Pydantic models for the RAG API request and response payloads."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

QueryRouteValue = Literal["in_scope", "out_of_scope", "conversation", "needs_clarification"]


class QueryRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Consulta jurídica en lenguaje natural",
    )
    k: int = Field(default=4, ge=1, le=8, description="Número de fragmentos para el contexto")
    k_candidates: int = Field(
        default=8, ge=4, le=20, description="Candidatos iniciales del retriever"
    )
    thread_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        description=(
            "Identificador de hilo de conversación. Si se proporciona, el agente mantiene "
            "el historial de mensajes entre requests (memoria multi-turno). "
            "Si es None, cada request es independiente. Si además se envía "
            "conversation_id, este último mantiene la precedencia actual (ver "
            "query_support._make_config: logical_id = conversation_id or thread_id "
            "or uuid4()); thread_id no está deprecado."
        ),
    )
    doc_types: list[Literal["jurisprudencia", "normativa"]] | None = Field(
        default=None,
        min_length=1,
        max_length=2,
        description=(
            "Filtro opcional por tipo de documento ('jurisprudencia', 'normativa'). "
            "Si es None (por defecto) se recuperan ambos tipos."
        ),
    )
    conversation_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description=(
            "ID de la conversación en la base de datos. "
            "Si el MemorySaver está vacío (reinicio del servidor) y se proporciona este campo, "
            "el backend hidrata el estado de LangGraph desde el historial persistido."
        ),
    )
    current_message_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        description=(
            "ID del mensaje de usuario ya persistido para el turno actual. Se excluye al "
            "hidratar el historial para evitar duplicar la pregunta."
        ),
    )

    @field_validator("doc_types")
    @classmethod
    def unique_doc_types(cls, value):
        if value is not None and len(value) != len(set(value)):
            raise ValueError("doc_types no puede contener valores duplicados")
        return value

    @model_validator(mode="after")
    def validate_related_fields(self) -> QueryRequest:
        if self.k_candidates < self.k:
            raise ValueError("k_candidates debe ser mayor o igual que k")
        if self.current_message_id and not self.conversation_id:
            raise ValueError("current_message_id requiere conversation_id")
        return self


class SourceFragment(BaseModel):
    index: int = Field(
        ..., description="Posición global 1-based del fragmento en la recuperación; mapea a [docN]"
    )
    content: str = Field(..., description="Contenido del fragmento (recortado a 500 caracteres)")
    metadata: dict = Field(
        default_factory=dict,
        description="Metadatos del fragmento (sección, summary, keywords, ...)",
    )


class SourceGroup(BaseModel):
    # A3.4 — `source`/`title`/`fragments` pasaron a ser requeridos (sin
    # default): `_docs_to_source_groups` (api/query_support.py), único
    # productor interno de este modelo, ya los provee siempre los tres
    # explícitamente, así que no cambia el contrato de `/api/query`. Lo que
    # sí habilita es que `AddMessageRequest.sources` (conversations.py)
    # rechace con 422 una estructura arbitraria como `{"foo": "bar"}` — antes
    # pasaba la validación completa porque los tres campos tenían default.
    # `source`/`title` siguen aceptando "" (un doc sin esos metadatos sigue
    # siendo válido); lo que ya no se acepta es la ausencia total de la
    # clave.
    source: str = Field(..., description="Nombre del archivo fuente; clave de agrupación")
    title: str = Field(..., description="Título legible del documento")
    doc_type: str | None = Field(
        default=None,
        description="Tipo de documento: 'jurisprudencia' o 'normativa'. Permite al frontend "
        "distinguir y etiquetar la fuente.",
    )
    metadata: dict = Field(
        default_factory=dict,
        description="Metadatos a nivel documento (Corporación, Radicado, Magistrado, Tema, Archivo, No)",
    )
    fragments: list[SourceFragment] = Field(
        ...,
        min_length=1,
        description="Fragmentos recuperados pertenecientes a este documento",
    )


# ── Conversation-level rating dimensions ───────────────────────────────────────


class RatingDimensions(BaseModel):
    """Calificación multidimensional de una conversación."""

    # Tono y largo solo los pide la encuesta del chat; la del flujo guiado
    # (ejercicio de validación) pide claridad, facilidad de uso y general.
    tone: int | None = Field(default=None, ge=1, le=5, description="Tono de las respuestas")
    length: int | None = Field(default=None, ge=1, le=5, description="Longitud de las respuestas")
    usability: int = Field(..., ge=1, le=5, description="Usabilidad del sistema")
    overall: int = Field(..., ge=1, le=5, description="Calificación general")
    # Encuesta de percepción del ejercicio de validación: claridad de las
    # respuestas. Opcional para no romper las encuestas guardadas antes.
    clarity: int | None = Field(default=None, ge=1, le=5, description="Claridad de las respuestas")


class RatingDimensionsFloat(BaseModel):
    """Promedios de calificación por dimensión (valores punto flotante)."""

    tone: float = 0.0
    length: float = 0.0
    usability: float = 0.0
    overall: float = 0.0


# ── Message-level rating dimensions ────────────────────────────────────────────


class MessageFeedbackRatings(BaseModel):
    """Calificación de un mensaje individual del agente."""

    pertinence: int = Field(..., ge=1, le=5, description="Pertinencia de la respuesta")
    accuracy: int = Field(..., ge=1, le=5, description="Precisión de la respuesta")


# ── Feedback request/response ─────────────────────────────────────────────────


class FeedbackRequest(BaseModel):
    """Calificación de conversación con dimensiones múltiples."""

    ratings: RatingDimensions = Field(
        ..., description="Calificación por dimensión (tono, longitud, usabilidad, general)"
    )
    comment: str | None = Field(
        default=None, max_length=500, description="Comentario opcional del usuario"
    )
    conversation_id: str | None = Field(default=None, description="ID de la conversación activa")


class FeedbackResponse(BaseModel):
    id: str = Field(..., description="ID del registro de feedback creado")


# ── Message feedback request/response ─────────────────────────────────────────


class MessageFeedbackRequest(BaseModel):
    """Calificación de un mensaje individual del agente."""

    conversation_id: str = Field(..., min_length=1, description="ID de la conversación")
    message_id: str = Field(..., min_length=1, description="ID del mensaje")
    ratings: MessageFeedbackRatings = Field(
        ..., description="Calificación por dimensión (pertinencia, precisión)"
    )
    expected_answer: str | None = Field(
        default=None, max_length=1000, description="Respuesta que el usuario consideraría adecuada"
    )


class MessageFeedbackResponse(BaseModel):
    id: str = Field(..., description="ID del registro de feedback de mensaje creado")


# ── Admin feedback schemas ────────────────────────────────────────────────────


class AdminFeedbackItem(BaseModel):
    id: str
    userId: str
    userEmail: str
    ratings: RatingDimensions
    comment: str | None
    conversationId: str | None
    conversationTitle: str | None
    createdAt: str = Field(..., description="ISO 8601 timestamp")


class AdminFeedbackResponse(BaseModel):
    items: list[AdminFeedbackItem]
    total: int
    avg_ratings: RatingDimensionsFloat = Field(
        ..., description="Promedio de calificaciones por dimensión"
    )
    distributions: dict[str, dict[str, int]] = Field(
        ...,
        description=(
            "Distribución de calificaciones por dimensión: "
            "{'tone': {'1': n, ...}, 'length': {...}, 'usability': {...}, 'overall': {...}}"
        ),
    )


class AdminMessageFeedbackItem(BaseModel):
    id: str
    userId: str
    userEmail: str
    conversationId: str
    messageId: str
    ratings: MessageFeedbackRatings
    expectedAnswer: str | None
    createdAt: str = Field(..., description="ISO 8601 timestamp")


class AdminMessageFeedbackResponse(BaseModel):
    items: list[AdminMessageFeedbackItem]
    total: int
    avg_ratings: dict[str, float] = Field(..., description="Promedio de pertinencia y precisión")
    distributions: dict[str, dict[str, int]] = Field(
        ...,
        description=(
            "Distribución de calificaciones por dimensión: "
            "{'pertinence': {'1': n, ...}, 'accuracy': {...}}"
        ),
    )


class AdminUserItem(BaseModel):
    uid: str
    email: str
    displayName: str | None
    role: str
    createdAt: str = Field(..., description="ISO 8601 timestamp")


class AdminUsersResponse(BaseModel):
    items: list[AdminUserItem]
    total: int


class CreateUserRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=320, description="Email del nuevo usuario")
    password: str = Field(
        ..., min_length=8, max_length=1024, description="Contraseña (mínimo 8 caracteres)"
    )
    displayName: str | None = Field(
        default=None, max_length=120, description="Nombre para mostrar (opcional)"
    )


class UpdatePasswordRequest(BaseModel):
    password: str = Field(
        ..., min_length=8, max_length=1024, description="Nueva contraseña (mínimo 8 caracteres)"
    )


class QueryResponse(BaseModel):
    answer: str = Field(..., description="Respuesta generada por el modelo")
    sources: list[SourceGroup] = Field(
        default_factory=list,
        description="Documentos fuente agrupados; cada grupo contiene los fragmentos recuperados de ese documento",
    )
    enriched_query: str | None = Field(
        default=None,
        description=(
            "Consulta expandida usada internamente para la recuperación de documentos. "
            "Útil para depuración y evaluación del enriquecimiento."
        ),
    )
    query_route: QueryRouteValue | None = Field(
        default=None,
        description="Ruta aplicada: in_scope, out_of_scope, conversation o needs_clarification.",
    )
    context_tokens: int = Field(
        default=0,
        description="Estimación de tokens acumulados en el historial de la conversación.",
    )
    context_limit: int = Field(
        default=200_000,
        description="Ventana de contexto máxima del modelo activo (tokens).",
    )


# ── Panel de administración (solo lectura) ─────────────────────────────────────


class PanelPeriodo(BaseModel):
    dias: int = Field(..., description="Días del periodo (0 = todo)")
    desde: str | None = Field(default=None, description="Inicio del periodo (ISO, UTC)")
    hasta: str = Field(..., description="Fin del periodo (ISO, UTC)")
    agrupacion: Literal["dia", "semana"]


class PanelCifras(BaseModel):
    preguntas: int
    personas: int
    personas_nuevas: int
    respuestas: int = Field(..., description="Respuestas sin contar saludos")
    con_fuente: int
    sin_respuesta_segura: int
    fuera_de_tema: int
    pide_aclarar: int
    saludos: int = Field(
        ..., description="Saludos o preguntas sobre ATLAS (no cuentan en respuestas)"
    )
    sin_respuesta_guardada: int
    calificaciones: int
    le_sirvio: int
    no_le_sirvio: int
    # PQ-132: de dónde salen las "no le sirvió" (fuera de tema o pidió aclarar
    # es donde ATLAS hizo lo correcto: no es contenido que falte).
    no_le_sirvio_con_fuente: int = 0
    no_le_sirvio_sin_respuesta: int = 0
    no_le_sirvio_fuera_de_tema: int = 0


class PanelPunto(BaseModel):
    fecha: str = Field(..., description="Día o lunes de la semana (YYYY-MM-DD, hora de Colombia)")
    desde: str = Field(..., description="Primer día del bloque dentro del periodo")
    hasta: str = Field(..., description="Último día del bloque dentro del periodo")
    parcial: bool = Field(..., description="Semana cortada por el inicio o el fin del periodo")
    preguntas: int
    sin_respuesta_segura: int


class PanelTema(BaseModel):
    id: str
    titulo: str
    preguntas: int
    calificaciones: int
    le_sirvio: int
    brechas: int


class PanelNorma(BaseModel):
    nombre: str
    doc_type: str | None
    respuestas: int


class PanelConteo(BaseModel):
    nombre: str
    preguntas: int


class PanelPersonas(BaseModel):
    activas: int
    nuevas: int
    recurrentes: int
    preguntas_por_persona: float
    # PQ-141: la media se sesga con quien pregunta mucho; va con la mediana.
    mediana_por_persona: float = 0


class PanelBrecha(BaseModel):
    pregunta: str
    veces: int
    tema: str
    tema_titulo: str
    motivo: Literal["sin_respuesta_segura", "no_le_sirvio"]
    # PQ-142: un grupo puede mezclar motivos; cuántas veces fue "no le sirvió".
    veces_no_le_sirvio: int = 0
    esperaba: str | None
    ultima: str
    conversation_id: str


class PanelResumenResponse(BaseModel):
    demo: bool = Field(..., description="La base tiene la semilla de demostración")
    periodo: PanelPeriodo
    cifras: PanelCifras
    anterior: PanelCifras | None = Field(
        default=None, description="Mismas cifras en el periodo anterior de igual duración"
    )
    serie: list[PanelPunto]
    temas: list[PanelTema]
    normas: list[PanelNorma]
    playas: list[PanelConteo]
    sin_playa: int
    personas: PanelPersonas
    brechas_total: int
    brechas: list[PanelBrecha]


class PanelPreguntaItem(BaseModel):
    id: str
    fecha: str
    pregunta: str
    tema: str
    tema_titulo: str
    playa: str | None
    resultado: str
    fuentes: int = Field(..., description="Documentos citados (normas + sentencias)")
    fuentes_sentencias: int = Field(..., description="Cuántos de ellos son sentencias")
    calificacion: str | None
    esperaba: str | None
    persona: str = Field(..., description="Nombre de registro (nunca el correo)")
    participante: str | None = Field(default=None, description="Número de participante")
    tipo_playa: int | None = Field(default=None, description="Tipo de usuario de playa (1-5)")
    conversation_id: str


class PanelPreguntasResponse(BaseModel):
    items: list[PanelPreguntaItem]
    total: int
    page: int
    page_size: int


class PanelFuente(BaseModel):
    nombre: str
    doc_type: str | None


class PanelMensaje(BaseModel):
    id: str
    role: str
    text: str
    fecha: str
    resultado: str | None
    fuentes: list[PanelFuente]
    calificacion: str | None
    esperaba: str | None


class PanelEncuestaItem(BaseModel):
    id: str
    fecha: str
    persona: str = Field(..., description="Nombre de registro (nunca el correo)")
    titulo: str | None
    conversation_id: str | None
    general: int
    claridad: int | None = Field(default=None, description="Solo en encuestas nuevas")
    tono: int | None = Field(default=None, description="Solo en la encuesta del chat")
    largo: int | None = Field(default=None, description="1 muy corta, 3 adecuada, 5 muy larga")
    facilidad: int
    comentario: str | None


class PanelEncuestasResponse(BaseModel):
    items: list[PanelEncuestaItem]
    total: int
    page: int
    page_size: int
    promedios: dict[str, float] = Field(
        ..., description="Promedio de 1 a 5 por dimensión (general, tono, largo, facilidad)"
    )


class PanelConversacionResponse(BaseModel):
    id: str
    titulo: str | None
    persona: str
    creada: str
    mensajes: list[PanelMensaje]
