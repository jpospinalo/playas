"""Retriever wrappers keep callback parentage without changing documents or I/O."""

from __future__ import annotations

import asyncio
import json
import os
import re
import socket
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import httpx
import pytest
from langchain_core.callbacks import BaseCallbackHandler, CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from rag.core.chroma_query import ChromaQuery
from rag.core.retriever import HybridEnsembleRetriever, _AsyncChromaRetriever, _FilteredRetriever


class Recorder(BaseCallbackHandler):
    run_inline = True

    def __init__(self):
        self.events: list[dict[str, Any]] = []

    def on_retriever_start(self, serialized, query, *, run_id, parent_run_id=None, **kwargs):
        self.events.append(
            {
                "event": "start",
                "name": kwargs.get("name"),
                "run_id": str(run_id),
                "parent_run_id": str(parent_run_id) if parent_run_id else None,
                "tags": kwargs.get("tags", []),
                "marker": (kwargs.get("metadata") or {}).get("marker"),
            }
        )

    def on_retriever_end(self, documents, *, run_id, parent_run_id=None, **kwargs):
        self.events.append(
            {
                "event": "end",
                "run_id": str(run_id),
                "parent_run_id": str(parent_run_id) if parent_run_id else None,
                "documents": len(documents),
            }
        )

    def on_retriever_error(self, error, *, run_id, parent_run_id=None, **kwargs):
        self.events.append(
            {
                "event": "error",
                "run_id": str(run_id),
                "parent_run_id": str(parent_run_id) if parent_run_id else None,
                "error_class": type(error).__name__,
            }
        )


class StaticRetriever(BaseRetriever):
    docs: list[Document]
    fails: bool = False

    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun):
        if self.fails:
            raise ValueError("Synthetic retriever failure")
        return self.docs


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Retriever callback contracts must remain offline")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)


@pytest.fixture
def recorder(request):
    handler = Recorder()
    yield handler
    directory = os.environ.get("RETRIEVER_CALLBACK_TRACE_DIR")
    if directory:
        name = re.sub(r"[^a-zA-Z0-9_.-]", "_", request.node.name)
        path = Path(directory) / (name + ".json")
        with path.open("x") as stream:
            json.dump(handler.events, stream, indent=2)


def build(kind: str, *, fail: bool = False):
    a = Document(
        page_content="First legitimate passage", metadata={"chunk_id": "a", "doc_type": "normativa"}
    )
    b = Document(
        page_content="Second legitimate passage",
        metadata={"chunk_id": "b", "doc_type": "jurisprudencia"},
    )
    inner = StaticRetriever(name="inner", docs=[a, b], fails=fail)
    if kind == "filtered":
        return (
            _FilteredRetriever(name="filtered-root", inner=inner, doc_types=["normativa"]),
            [a],
            ["inner"],
        )
    if kind == "hybrid":
        vector = StaticRetriever(name="vector", docs=[b, a])
        return (
            HybridEnsembleRetriever(
                name="hybrid-root", retrievers=[inner, vector], weights=[0.3, 0.7], max_results=2
            ),
            # RRF pone b primero, pero la jerarquía normativa
            # (``normativa_primero``) adelanta la norma ``a`` a la sentencia.
            [a, b],
            ["inner", "vector"],
        )
    if kind == "chroma_sync":
        port = ChromaQuery(Mock(spec=httpx.AsyncClient), "/not-used", 1)
        return (
            _AsyncChromaRetriever(
                name="chroma-root", sync_retriever=inner, chroma_query=port, k=2, where=None
            ),
            [a, b],
            ["inner"],
        )
    raise AssertionError(kind)


def config(recorder):
    return {
        "callbacks": [recorder],
        "tags": ["fixture-trace"],
        "metadata": {"marker": "safe-fixture"},
    }


def assert_children(recorder, names, *, error=False):
    starts = [e for e in recorder.events if e["event"] == "start"]
    roots = [e for e in starts if e["parent_run_id"] is None]
    assert len(roots) == 1
    root = roots[0]
    children = [e for e in starts if e["name"] in names]
    assert len(children) == len(names), recorder.events
    assert all(e["parent_run_id"] == root["run_id"] for e in children)
    assert all("fixture-trace" in e["tags"] and e["marker"] == "safe-fixture" for e in children)
    expected_event = "error" if error else "end"
    assert any(
        e["event"] == expected_event and e["run_id"] == root["run_id"] for e in recorder.events
    )
    assert any(
        e["event"] == expected_event and e["run_id"] == children[0]["run_id"]
        for e in recorder.events
    )


@pytest.mark.parametrize("kind", ["filtered", "hybrid", "chroma_sync"])
def test_sync_wrapper_keeps_child_parent_and_document_results(kind, recorder):
    retriever, expected, children = build(kind)
    result = retriever.invoke("Synthetic query", config=config(recorder))
    assert result == expected and all(a is b for a, b in zip(result, expected, strict=True))
    assert_children(recorder, children)


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["filtered", "hybrid"])
async def test_async_wrapper_keeps_child_parent_and_document_results(kind, recorder):
    retriever, expected, children = build(kind)
    result = await retriever.ainvoke("Synthetic query", config=config(recorder))
    assert result == expected and all(a is b for a, b in zip(result, expected, strict=True))
    assert_children(recorder, children)


@pytest.mark.parametrize("kind", ["filtered", "hybrid", "chroma_sync"])
def test_sync_child_failure_reaches_the_same_callback_tree(kind, recorder):
    retriever, _, _ = build(kind, fail=True)
    with pytest.raises(ValueError, match="Synthetic retriever failure"):
        retriever.invoke("Synthetic query", config=config(recorder))
    assert_children(recorder, ["inner"], error=True)


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["filtered", "hybrid"])
async def test_async_child_failure_reaches_the_same_callback_tree(kind, recorder):
    retriever, _, _ = build(kind, fail=True)
    with pytest.raises(ValueError, match="Synthetic retriever failure"):
        await retriever.ainvoke("Synthetic query", config=config(recorder))
    assert_children(recorder, ["inner"], error=True)


@pytest.mark.anyio
@pytest.mark.parametrize("transport", ["sync", "async"])
async def test_nested_filter_preserves_its_own_parent_not_the_ensemble_ancestor(
    transport, recorder
):
    retriever, expected, _ = build("hybrid")
    inner = retriever.retrievers[0]
    retriever.retrievers[0] = _FilteredRetriever(
        name="filtered-child", inner=inner, doc_types=["normativa"]
    )
    if transport == "sync":
        result = retriever.invoke("Synthetic query", config=config(recorder))
    else:
        result = await retriever.ainvoke("Synthetic query", config=config(recorder))
    # La norma ``a`` sigue primero por la jerarquía normativa.
    assert result == expected
    starts = {e["name"]: e for e in recorder.events if e["event"] == "start"}
    assert set(starts) == {"hybrid-root", "filtered-child", "inner", "vector"}
    assert starts["hybrid-root"]["parent_run_id"] is None
    assert starts["filtered-child"]["parent_run_id"] == starts["hybrid-root"]["run_id"]
    assert starts["vector"]["parent_run_id"] == starts["hybrid-root"]["run_id"]
    assert starts["inner"]["parent_run_id"] == starts["filtered-child"]["run_id"]
    assert len({e["run_id"] for e in starts.values()}) == 4
    assert len([e for e in recorder.events if e["event"] == "end"]) == 4


class GatedRetriever(BaseRetriever):
    docs: list[Document]
    started: Any
    cancelled: Any
    released: Any

    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun):
        raise AssertionError("This fixture must use native asynchronous retrieval")

    async def _aget_relevant_documents(self, query: str, *, run_manager):
        self.started.set()
        try:
            await self.released.wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        return self.docs


@pytest.mark.anyio
async def test_cancellation_drains_both_children_and_a_new_call_still_has_correct_parentage(
    recorder,
):
    left = GatedRetriever(
        name="left",
        docs=[Document(page_content="Left", metadata={"chunk_id": "a"})],
        started=asyncio.Event(),
        cancelled=asyncio.Event(),
        released=asyncio.Event(),
    )
    right = GatedRetriever(
        name="right",
        docs=[Document(page_content="Right", metadata={"chunk_id": "b"})],
        started=asyncio.Event(),
        cancelled=asyncio.Event(),
        released=asyncio.Event(),
    )
    retriever = HybridEnsembleRetriever(
        name="reusable-root", retrievers=[left, right], weights=[0.3, 0.7], max_results=2
    )
    task = asyncio.create_task(retriever.ainvoke("First fixture query", config=config(recorder)))
    await asyncio.wait_for(asyncio.gather(left.started.wait(), right.started.wait()), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert left.cancelled.is_set() and right.cancelled.is_set()
    left.released.set()
    right.released.set()
    result = await asyncio.wait_for(
        retriever.ainvoke("Second fixture query", config=config(recorder)), timeout=1
    )
    assert result == [*right.docs, *left.docs]
    roots = [e for e in recorder.events if e["event"] == "start" and e["parent_run_id"] is None]
    assert len(roots) == 2 and roots[0]["run_id"] != roots[1]["run_id"]
    second_children = [
        e
        for e in recorder.events
        if e["event"] == "start" and e["parent_run_id"] == roots[1]["run_id"]
    ]
    assert {e["name"] for e in second_children} == {"left", "right"}
    assert all(
        any(end["event"] == "end" and end["run_id"] == child["run_id"] for end in recorder.events)
        for child in second_children
    )


@pytest.mark.anyio
async def test_native_async_chroma_port_does_not_invoke_the_sync_fallback(monkeypatch, recorder):
    from unittest.mock import AsyncMock

    retriever, expected, _ = build("chroma_sync")
    calls = []

    async def search(port, embedding, *, k, where):
        calls.append((embedding, k, where))
        return expected

    monkeypatch.setattr(ChromaQuery, "search", search)
    retriever.query_embedder = AsyncMock(return_value=[0.25, 0.75])
    result = await retriever.ainvoke("Synthetic query", config=config(recorder))
    assert result == expected and calls == [([0.25, 0.75], 2, None)]
    starts = [e for e in recorder.events if e["event"] == "start"]
    assert len(starts) == 1 and starts[0]["name"] == "chroma-root"
    retriever.query_embedder.assert_awaited_once_with("Synthetic query")


@pytest.mark.anyio
async def test_multiquery_fusion_hangs_every_search_from_one_hybrid_run(recorder):
    retriever, expected, _ = build("hybrid")
    result = await retriever.afuse_queries(
        ["Synthetic query", "Reformulated query", "Synthetic query", " "],
        config=config(recorder),
    )
    assert result == expected and all(a is b for a, b in zip(result, expected, strict=True))
    starts = [e for e in recorder.events if e["event"] == "start"]
    roots = [e for e in starts if e["parent_run_id"] is None]
    assert len(roots) == 1 and roots[0]["name"] == "hybrid-root"
    children = [e for e in starts if e["parent_run_id"] == roots[0]["run_id"]]
    # Dos consultas distintas (el duplicado y la vacía se descartan) × dos
    # sub-recuperadores, todas colgadas de la misma ejecución raíz.
    assert sorted(e["name"] for e in children) == ["inner", "inner", "vector", "vector"]
    assert all("fixture-trace" in e["tags"] and e["marker"] == "safe-fixture" for e in children)
    ends = {e["run_id"]: e for e in recorder.events if e["event"] == "end"}
    assert ends[roots[0]["run_id"]]["documents"] == len(expected)
    assert all(e["run_id"] in ends for e in children)


@pytest.mark.anyio
async def test_multiquery_fusion_child_failure_reaches_the_same_callback_tree(recorder):
    retriever, _, _ = build("hybrid", fail=True)
    with pytest.raises(ValueError, match="Synthetic retriever failure"):
        await retriever.afuse_queries(["Synthetic query"], config=config(recorder))
    assert_children(recorder, ["inner"], error=True)


@pytest.mark.anyio
async def test_multiquery_fusion_without_queries_opens_no_run(recorder):
    retriever, _, _ = build("hybrid")
    assert await retriever.afuse_queries(["", "  "], config=config(recorder)) == []
    assert recorder.events == []
