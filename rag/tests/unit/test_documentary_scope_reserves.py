"""Offline contracts for G04 and the twelve unresolved Antioquia identities.

Question literals come from the frozen historical captures. Their expected
outcome remains abstention; a scope rescue must not invent identity or instance.
The snapshot is the repository release, never a running Chroma collection.
"""

from __future__ import annotations

import gzip
import json
from hashlib import sha256
from pathlib import Path
from typing import NoReturn

import pytest
from langchain_core.documents import Document

from rag.core.domain_scope import EnrichedQuery, QueryRoute, _fallback
from rag.core.legal_resolution import ResolutionIndex, load_provenance

GOLD = Path(__file__).resolve().parents[3] / "data/chroma-releases/gold-a-cc7bf44b54a9"
ARCHIVE_SHA = "cc7bf44b54a9309d67e52d77cf7e41fd5e4cd7063168dfc70ffd57785ba7657d"
PROOF_SHA = "390dc2a8c1f267e908027f0efb348be3139ca9a222f162d7dd5439309aa8b117"
QUESTIONS: tuple[tuple[str, str], ...] = (
    (
        "Antioquia-01",
        "¿Qué resolvió en segunda instancia sobre la sentencia del 12 de diciembre de 2018 en el radicado 05837-33-33-001-2015-00281-01?",
    ),
    (
        "Antioquia-02",
        "¿Qué resolvió en primera instancia sobre la sentencia del 12 de diciembre de 2018 en el radicado 05837-33-33-001-2015-00281-01?",
    ),
    (
        "Antioquia-03",
        "¿Qué resolvió en única instancia sobre la sentencia del 12 de diciembre de 2018 en el radicado 05837-33-33-001-2015-00281-01?",
    ),
    (
        "Antioquia-04",
        "¿Qué resolvió en segunda instancia sobre la sentencia del 12 de diciembre de 2018 en el radicado 05837333300120150028101?",
    ),
    (
        "Antioquia-05",
        "¿Qué resolvió en primera instancia sobre la sentencia del 12 de diciembre de 2018 en el radicado 05837333300120150028101?",
    ),
    (
        "Antioquia-06",
        "¿Qué resolvió en única instancia sobre la sentencia del 12 de diciembre de 2018 en el radicado 05837333300120150028101?",
    ),
    (
        "Antioquia-07",
        "¿Qué resolvió en segunda instancia sobre la sentencia del 12 de diciembre de 2018 en el radicado 05001-33-33-001-2015-00281-01?",
    ),
    (
        "Antioquia-08",
        "¿Qué resolvió en primera instancia sobre la sentencia del 12 de diciembre de 2018 en el radicado 05001-33-33-001-2015-00281-01?",
    ),
    (
        "Antioquia-09",
        "¿Qué resolvió en única instancia sobre la sentencia del 12 de diciembre de 2018 en el radicado 05001-33-33-001-2015-00281-01?",
    ),
    (
        "Antioquia-10",
        "¿Qué resolvió en segunda instancia sobre la sentencia del 12 de diciembre de 2018 en el radicado 05001333300120150028101?",
    ),
    (
        "Antioquia-11",
        "¿Qué resolvió en primera instancia sobre la sentencia del 12 de diciembre de 2018 en el radicado 05001333300120150028101?",
    ),
    (
        "Antioquia-12",
        "¿Qué resolvió en única instancia sobre la sentencia del 12 de diciembre de 2018 en el radicado 05001333300120150028101?",
    ),
    (
        "G04",
        "¿Qué ordenó en primera instancia sobre el apoyo técnico, documental y logístico en el radicado 47001233300020180036800?",
    ),
)
QUESTION_SHA256 = {
    "Antioquia-01": "775438048a70ede9c866b973083babdc34a7a462bffa1b236d0d290c422acfc8",
    "Antioquia-02": "9669d886b2d7661da5741c2bb0f07e68faf44b7eb9047d459a7772c429292629",
    "Antioquia-03": "d2643a21612c91f187f6076124b8ae881d3b1cf887de08dfa8a239aea9cd8fa8",
    "Antioquia-04": "e98558f95b262d322e5a152b605eec94a03fa9c8237d0b6ce177971c1bb57f5a",
    "Antioquia-05": "39eb1a9b0177e2dd6aef2abb5708e858f00be8ec8af3ad915d2a3bd566a8b8c9",
    "Antioquia-06": "a7b87d15ae0f4ee92d5c686afff6e7931cdb7bda25438c447df5964918227486",
    "Antioquia-07": "3efaa5ca370061e03b6095f7ba7bde1fd8e5ce96a8f5e1d228d75c5661dd7a0f",
    "Antioquia-08": "c3cdfb1d28efa1f8673f8582071fe8f5f95eba3aba64ae4b6c6e6ca10ccf6945",
    "Antioquia-09": "65ba0919db20f51c73c31fa88b9bde2e9a5b780f2ee13bd44f93f9e71b51800b",
    "Antioquia-10": "937f29f856101e4b7e2a2d5eb278176b4496be09d46142658f8b955e4bed39f9",
    "Antioquia-11": "3b9e5fe7cee0d07c18832938d225e896db754dc51e335fa85d16264b5e63def8",
    "Antioquia-12": "271000d6c53633cf699b1575953138945fc2715d70e423f5ed07613fa789a423",
    "G04": "d0ea9e2542280523945a050b8959b0bb47cc8e0c15edc0af6a8ea89c3248ff2e",
}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="module")
def reserve_snapshot() -> tuple[list[Document], ResolutionIndex]:
    assert len(QUESTIONS) == len({question for _, question in QUESTIONS}) == 13
    assert {label for label, _ in QUESTIONS} == set(QUESTION_SHA256)
    assert all(
        sha256(question.encode()).hexdigest() == QUESTION_SHA256[label]
        for label, question in QUESTIONS
    )
    assert sha256((GOLD / "GOLD_A.jsonl.gz").read_bytes()).hexdigest() == ARCHIVE_SHA
    documents = []
    with gzip.open(GOLD / "GOLD_A.jsonl.gz", "rt", encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if "__manifest__" not in row:
                documents.append(
                    Document(id=row["id"], page_content=row["document"], metadata=row["metadata"])
                )
    proof = load_provenance(GOLD / "PROCEDENCIA_GOLD_A.json", PROOF_SHA)
    index = ResolutionIndex(documents, proof)
    assert index.snapshot_verified and len(documents) == 5862
    return documents, index


@pytest.mark.parametrize(("label", "question"), QUESTIONS, ids=[label for label, _ in QUESTIONS])
def test_snapshot_reserves_do_not_admit_unverified_identity(
    reserve_snapshot: tuple[list[Document], ResolutionIndex], label: str, question: str
) -> None:
    _, index = reserve_snapshot
    assert _fallback(question).route == "out_of_scope", label
    assert index.resolve(question) is None, label
    assert index.docket_evidence(question) is None, label


def _unexpected_retrieval_or_generation(*args: object, **kwargs: object) -> NoReturn:
    pytest.fail("An unverified identity must not trigger retrieval or generation")


@pytest.mark.anyio
@pytest.mark.parametrize("channel", ["JSON", "SSE"])
@pytest.mark.parametrize("forced_route", ["out_of_scope", "in_scope"])
async def test_reserves_in_public_handlers_even_if_scope_admits(
    monkeypatch: pytest.MonkeyPatch,
    reserve_snapshot: tuple[list[Document], ResolutionIndex],
    channel: str,
    forced_route: QueryRoute,
) -> None:
    import rag.api.main as main
    import rag.core.agent as agent
    from rag.api.schemas import QueryRequest

    documents, _ = reserve_snapshot
    monkeypatch.setattr(agent, "bm25_documents", lambda: documents)
    monkeypatch.setattr(
        agent, "LEGAL_RESOLUTION_PROVENANCE_PATH", str(GOLD / "PROCEDENCIA_GOLD_A.json")
    )
    monkeypatch.setattr(agent, "LEGAL_RESOLUTION_PROVENANCE_SHA256", PROOF_SHA)

    async def analyze(question: str, history: str) -> EnrichedQuery:
        return EnrichedQuery(
            route=forced_route,
            standalone_question=question,
            expanded_query=question,
            doc_types=["jurisprudencia"] if forced_route == "in_scope" else [],
        )

    monkeypatch.setattr(agent, "enrich_query_async", analyze)
    monkeypatch.setattr(agent, "get_ensemble_retriever", _unexpected_retrieval_or_generation)
    monkeypatch.setattr(agent, "get_generation_llm", _unexpected_retrieval_or_generation)
    monkeypatch.setattr(main, "_graph", agent.build_graph())
    for label, question in QUESTIONS:
        request = QueryRequest(question=question)
        if channel == "JSON":
            response = await main.query(request, {"sub": "reserve-user"})
            answer, sources = response.answer, response.sources
        else:
            response = await main.query_stream(request, {"sub": "reserve-user"})
            events = []
            done = False
            async for block in response.body_iterator:
                text = block.decode() if isinstance(block, bytes) else block
                for line in text.splitlines():
                    if not line.startswith("data: "):
                        continue
                    payload = line[6:].strip()
                    if payload == "[DONE]":
                        done = True
                    else:
                        events.append(json.loads(payload))
            assert done and not any(event.get("type") == "error" for event in events), label
            answer = "".join(event["content"] for event in events if event.get("type") == "token")
            source_events = [event for event in events if event.get("type") == "sources"]
            assert len(source_events) == 1, label
            sources = source_events[0]["sources"]
        assert not sources and "[doc" not in answer and answer.strip(), label
