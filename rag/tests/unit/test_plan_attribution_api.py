"""Portable graph/JSON/SSE contracts with synthetic providers, never live answers.

The history seed is explicit test input, not a reconstructed SQL conversation.
The real hybrid retriever must expose its already obtained candidates before k4.
"""

from __future__ import annotations

import copy
import json
import re
import socket
from types import SimpleNamespace

import pytest
from langchain_core.documents import Document
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import RunnableLambda

from rag.api.schemas import QueryRequest
from rag.core.domain_scope import EnrichedQuery

PLAN = "Plan de Manejo Integral de la Zona Costera Bahía Clara"
QUESTION = "¿Y quién debe formularlo?"
STANDALONE = f"¿Quién debe formular el {PLAN}?"
ADOPTION = f"¿Qué autoridad debe adoptar el {PLAN}?"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("The portable API contract must not connect to a service")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)


class FixedLane(BaseRetriever):
    documents: list[Document]

    def _get_relevant_documents(self, query, *, run_manager):
        return self.documents

    async def _aget_relevant_documents(self, query, *, run_manager):
        return self.documents


def packet():
    bodies = {
        "guide": "La guía organiza los aspectos metodológicos del PBC.",
        "identity": f"Se establece el {PLAN} -PBC- para la jurisdicción indicada.",
        "stages": "Las fases del PBC incluyen diagnóstico y seguimiento ambiental.",
        "coordination": "Corresponde a la Secretaría Local coordinar la ejecución del PBC.",
        "proof": (
            "ARTÍCULO 2. Formulación y adopción del PBC.\n"
            "La formulación del PBC, estará a cargo de la Dirección Técnica de Bahía Clara "
            "y su adopción estará en cabeza del Consejo Local."
        ),
    }
    documents = {}
    for number, (ident, body) in enumerate(bodies.items(), 1):
        documents[ident] = Document(
            id=None if ident != "proof" else ident,
            page_content=body,
            metadata={
                "chunk_id": ident,
                "source": "norma_sintetica.md",
                "norma": "Decreto 123 de 2025",
                "doc_type": "normativa",
                "articulo": "2" if ident == "proof" else str(number + 2),
                "articulo_titulo": "Formulación y adopción del PBC" if ident == "proof" else "",
                "section_index": number,
                "chunk_index": 0,
                "total_chunks_in_section": 1,
                "summary": "Descripción auxiliar que no sustituye al cuerpo.",
                "keywords": ["plan", "costero"],
            },
        )
    return documents


async def public_result(main_module, request, channel):
    user = {"sub": "plan-attribution-contract-user"}
    if channel == "JSON":
        result = await main_module.query(request, user)
        return result.answer, [group.model_dump() for group in result.sources]
    response = await main_module.query_stream(request, user)
    events = []
    done = False
    try:
        async for block in response.body_iterator:
            text = block.decode() if isinstance(block, bytes) else block
            for line in text.splitlines():
                if not line.startswith("data: "):
                    continue
                payload = line[6:].strip()
                if payload == "[DONE]":
                    assert not done
                    done = True
                else:
                    assert not done
                    events.append(json.loads(payload))
    finally:
        await response.body_iterator.aclose()
    assert done
    assert not any(event.get("type") == "error" for event in events)
    source_events = [event for event in events if event.get("type") == "sources"]
    assert len(source_events) == 1
    answer = "".join(event["content"] for event in events if event.get("type") == "token")
    return answer, source_events[0]["sources"]


@pytest.mark.anyio
@pytest.mark.parametrize("channel", ["JSON", "SSE"])
@pytest.mark.parametrize(
    "scenario",
    ["followup", "followup_parenthetical", "first_adoption", "off", "unverified", "juris_filter"],
)
async def test_bound_plan_evidence_reaches_public_citations(monkeypatch, channel, scenario):
    import rag.api.main as main_module
    import rag.core.agent as agent_module
    from rag.core.retriever import HybridEnsembleRetriever

    docs = packet()
    before = {key: doc.model_dump() for key, doc in docs.items()}
    verified = tuple(Document(**copy.deepcopy(doc.model_dump())) for doc in docs.values())
    question = ADOPTION if scenario == "first_adoption" else QUESTION
    factory_calls = []
    generation_prompts = []
    history_calls = []

    async def analyze(incoming, history):
        assert incoming == question
        history_calls.append(history)
        standalone = (
            STANDALONE.replace("?", " (PBC)?")
            if scenario == "followup_parenthetical"
            else STANDALONE
        )
        return EnrichedQuery(
            route="in_scope",
            standalone_question=question if scenario == "first_adoption" else standalone,
            expanded_query=question if scenario == "first_adoption" else standalone,
            doc_types=["jurisprudencia", "normativa"]
            if scenario == "followup_parenthetical"
            else ["normativa"],
        )

    async def initial_messages(
        graph, config, conversation_id, incoming, user_id, current_message_id
    ):
        assert conversation_id is None and current_message_id is None
        if scenario == "first_adoption":
            return [HumanMessage(content=incoming)]
        # This is a portable, mixed-role seed. It does not claim to exercise SQL hydration.
        return [
            HumanMessage(
                content=ADOPTION
                if scenario == "followup_parenthetical"
                else f"Me refiero al {PLAN}."
            ),
            AIMessage(content="La adopción corresponde al Consejo Local [doc2]."),
            HumanMessage(content=incoming),
        ]

    def factory(**kwargs):
        factory_calls.append(kwargs)
        allowed = kwargs.get("doc_types")

        def lane(identifiers):
            return FixedLane(
                documents=[
                    docs[ident]
                    for ident in identifiers
                    if allowed is None or docs[ident].metadata["doc_type"] in allowed
                ]
            )

        # Four documents occur in both lanes; proof is vector-first but absent lexically.
        # Ordinary RRF therefore loses proof unless the optional pre-cut selector runs.
        return HybridEnsembleRetriever(
            retrievers=[
                lane(["guide", "identity", "stages", "coordination"]),
                lane(["proof", "guide", "identity", "stages", "coordination"]),
            ],
            weights=[0.3, 0.7],
            c=160,
            id_key="chunk_id",
            max_results=kwargs["k"],
        )

    async def generate(prompt):
        text = "\n".join(str(message.content) for message in prompt.to_messages())
        generation_prompts.append(text)
        proof_marker = re.search(r"\[doc(\d+) \|[^\]]*chunk_id=proof\]", text)
        if proof_marker:
            assert docs["proof"].page_content in text
            actor = (
                "Consejo Local"
                if scenario == "first_adoption"
                else "Dirección Técnica de Bahía Clara"
            )
            return f"{actor} [doc{proof_marker.group(1)}]."
        return "Solo consta una descripción metodológica [doc1]."

    monkeypatch.setattr(agent_module, "enrich_query_async", analyze)
    monkeypatch.setattr(
        agent_module,
        "get_active_provider",
        lambda: SimpleNamespace(supports_system_role=True),
    )
    monkeypatch.setattr(agent_module, "get_generation_llm", lambda: RunnableLambda(generate))
    monkeypatch.setattr(agent_module, "get_ensemble_retriever", factory)
    monkeypatch.setattr(
        agent_module,
        "LEGAL_RESOLUTION_PROVENANCE_PATH",
        None if scenario == "off" else "synthetic-proof",
    )
    monkeypatch.setattr(agent_module, "load_provenance", lambda *args: {})
    monkeypatch.setattr(agent_module, "bm25_documents", lambda: list(verified))
    monkeypatch.setattr(
        agent_module,
        "ResolutionIndex",
        lambda *args: SimpleNamespace(snapshot_verified=scenario != "unverified"),
    )
    monkeypatch.setattr(main_module, "_get_initial_messages", initial_messages)
    monkeypatch.setattr(main_module, "_graph", agent_module.build_graph())
    request = QueryRequest(
        question=question,
        doc_types=["jurisprudencia"] if scenario == "juris_filter" else None,
        k=4,
        k_candidates=8,
    )
    answer, groups = await public_result(main_module, request, channel)
    fragments = [fragment for group in groups for fragment in group["fragments"]]
    public_metadata = {
        fragment["index"]: {**group["metadata"], **fragment["metadata"], "source": group["source"]}
        for group in groups
        for fragment in group["fragments"]
    }
    ids = [fragment["metadata"]["chunk_id"] for fragment in fragments]
    if scenario in ("followup", "followup_parenthetical"):
        assert ids == ["proof", "guide", "identity", "stages"]
        assert "Dirección Técnica de Bahía Clara" in answer and "[doc1]" in answer
        assert factory_calls and factory_calls[0]["k"] == 4
        if scenario == "followup_parenthetical":
            assert factory_calls[0]["doc_types"] == ["jurisprudencia", "normativa"]
    elif scenario == "first_adoption":
        assert ids == ["identity", "proof"]
        assert "Consejo Local" in answer and "[doc2]" in answer
        assert not factory_calls
    elif scenario == "juris_filter":
        assert not fragments and not generation_prompts
        assert factory_calls[0]["doc_types"] == ["jurisprudencia"]
        assert "[doc" not in answer
    else:
        assert ids == ["guide", "identity", "stages", "coordination"]
        assert "proof" not in ids and "Dirección Técnica" not in answer
    for index, fragment in enumerate(fragments, 1):
        original = docs[fragment["metadata"]["chunk_id"]]
        assert fragment["index"] == index
        assert fragment["content"] == original.page_content.strip().replace("\n", " ")
        assert public_metadata[index] == original.metadata
        assert fragment["metadata"]["summary"] == original.metadata["summary"]
        assert fragment["metadata"]["keywords"] == original.metadata["keywords"]
    cited = [int(value) for value in re.findall(r"\[doc(\d+)\]", answer)]
    assert all(1 <= index <= len(fragments) for index in cited)
    assert history_calls
    assert {key: doc.model_dump() for key, doc in docs.items()} == before
