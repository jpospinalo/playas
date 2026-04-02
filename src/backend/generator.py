# src/backend/generator.py

from __future__ import annotations

import os
import warnings
from functools import lru_cache

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_google_genai import ChatGoogleGenerativeAI

from .retriever import get_ensemble_retriever

warnings.filterwarnings("ignore", category=FutureWarning)

# ---------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------

load_dotenv()


@lru_cache(maxsize=1)
def _get_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        temperature=0.0,
    )


# ---------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------


def _build_context_block(docs: list[Document]) -> str:
    """
    Convierte la lista de documentos en un bloque de contexto legible,
    incluyendo metadatos básicos (source, chunk_id).
    """
    bloques: list[str] = []
    for i, d in enumerate(docs, start=1):
        meta = d.metadata or {}
        source = meta.get("source", "desconocido")
        chunk_id = meta.get("chunk_id", meta.get("id", f"doc_{i}"))
        bloque = f"[doc{i} | source={source} | chunk_id={chunk_id}]\n{d.page_content}"
        bloques.append(bloque)

    return "\n\n".join(bloques)


BASE_INSTRUCTIONS = (
    "Eres un asistente experto que responde en español.\n"
    "Debes contestar la pregunta del usuario usando EXCLUSIVAMENTE "
    "la información del contexto proporcionado.\n\n"
    "Si la respuesta no se puede obtener del contexto, indícalo de forma explícita "
    "y, si es útil, sugiere qué información adicional se requeriría."
)

PROMPT_WITH_SYSTEM = ChatPromptTemplate.from_messages(
    [
        ("system", BASE_INSTRUCTIONS),
        (
            "human",
            "CONTEXTO:\n{context}\n\nPREGUNTA:\n{question}\n\nResponde en español.",
        ),
    ]
)

PROMPT_NO_SYSTEM = ChatPromptTemplate.from_messages(
    [
        (
            "human",
            "INSTRUCCIONES:\n"
            "{instructions}\n\n"
            "CONTEXTO:\n{context}\n\n"
            "PREGUNTA:\n{question}\n\n"
            "Responde en español.",
        )
    ]
)


def _get_prompt_for_model(model_name: str) -> ChatPromptTemplate:
    model = (model_name or "").lower()
    if model.startswith("gemma-"):
        return PROMPT_NO_SYSTEM.partial(instructions=BASE_INSTRUCTIONS)
    return PROMPT_WITH_SYSTEM


# ---------------------------------------------------------------------
# Chain RAG
# ---------------------------------------------------------------------


def build_rag_chain(k_candidates: int = 8):
    """
    input (str) -> retriever -> docs -> contexto
                 -> PROMPT -> LLM -> texto
    """
    llm = _get_llm()
    prompt = _get_prompt_for_model(os.getenv("GEMINI_MODEL", "gemini-2.0-flash"))
    retriever = get_ensemble_retriever(k=k_candidates)

    rag_chain = (
        {
            "context": retriever | RunnableLambda(_build_context_block),
            "question": RunnablePassthrough(),
        }
        | prompt
        | llm
        | StrOutputParser()
    )
    return rag_chain, retriever


def generate_answer(
    question: str,
    k: int = 5,
    k_candidates: int = 8,
) -> tuple[str, list[Document]]:
    """
    1) Usa un chain RAG (retriever + prompt + LLM) para generar la respuesta.
    2) Recupera también los documentos usados (top-k del ensemble).

    Devuelve:
        (respuesta, documentos_utilizados)
    """
    rag_chain, retriever = build_rag_chain(k_candidates=k_candidates)

    # 1) Respuesta usando el chain completo (ya es str)
    answer = rag_chain.invoke(question)
    if isinstance(answer, str):
        answer = answer.strip()
    else:
        # Fallback defensivo por si el parser no se aplicara
        answer = str(getattr(answer, "content", answer)).strip()

    # 2) Documentos (los mismos candidatos que se usan para el contexto)
    candidates = retriever.invoke(question)
    docs = candidates[:k] if candidates else []

    if not docs and not answer:
        return "No se encontraron fragmentos relevantes en la base de conocimiento.", []

    return answer, docs


# ---------------------------------------------------------------------
# Ejemplo de uso desde terminal
# ---------------------------------------------------------------------


def demo(question: str = "¿quién era Leonora?") -> None:
    answer, docs = generate_answer(
        question=question,
        k=5,
        k_candidates=8,
    )

    print("\n=== PREGUNTA ===")
    print(question)

    print("\n=== RESPUESTA (Gemini) ===")
    print(answer)

    print("\n=== CONTEXTO UTILIZADO ===")
    for i, d in enumerate(docs, start=1):
        meta = d.metadata or {}
        src = meta.get("source", "desconocido")
        chunk_id = meta.get("chunk_id", meta.get("id", f"doc_{i}"))
        print(f"\n[doc{i}] source={src} | chunk_id={chunk_id}")
        print(d.page_content.replace("\n", " "))


if __name__ == "__main__":
    demo(question="¿Cómo murió la esposa del narrador del cuento del gato negro?")
