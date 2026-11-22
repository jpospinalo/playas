"""Candidate selection preserves the retriever's ranking and ownership contracts.

Only the two ``pre_cut`` cases characterize the missing capability before the
implementation. The remaining contracts apply after the optional hook exists.
All lanes are local fixtures; no models, clients or corpus files are involved.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any

import pytest
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import Field

from rag.core.retriever import HybridEnsembleRetriever


class StaticLane(BaseRetriever):
    docs: list[Document]
    received_kwargs: list[dict[str, Any]] = Field(default_factory=list)

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun, **kwargs: Any
    ) -> list[Document]:
        self.received_kwargs.append(kwargs)
        return self.docs

    async def _aget_relevant_documents(
        self, query: str, *, run_manager: Any, **kwargs: Any
    ) -> list[Document]:
        self.received_kwargs.append(kwargs)
        await asyncio.sleep(0)
        return self.docs


@pytest.fixture
def anyio_backend():
    return "asyncio"


def passage(ident: str, text: str | None = None) -> Document:
    return Document(
        page_content=text or f"Retrieved public passage {ident}",
        metadata={"chunk_id": ident, "doc_type": "normativa"},
    )


def fixture_retriever(k: int = 4):
    common = [passage(letter) for letter in "abcde"]
    proof = passage("proof", "The required attribution is explicit in this passage.")
    structural = passage("structural", "--- | ---")
    left = StaticLane(docs=[*common, structural])
    right = StaticLane(docs=[proof, *common])
    ensemble = HybridEnsembleRetriever(
        retrievers=[left, right], weights=[0.3, 0.7], c=160, max_results=k
    )
    return ensemble, common, proof, structural


def assert_objects(actual, expected):
    assert len(actual) == len(expected)
    assert all(a is b for a, b in zip(actual, expected, strict=True))


def promoter(proof, calls):
    def choose(current, candidates):
        calls.append((current, candidates))
        assert isinstance(current, list)
        assert isinstance(candidates, tuple)
        assert any(doc is proof for doc in candidates)
        return [proof, *current[:3]]

    return choose


def test_sync_pre_cut_selector_can_retain_a_passage_ranked_below_four():
    retriever, common, proof, _ = fixture_retriever()
    calls = []
    result = retriever.invoke("fixed query", candidate_selector=promoter(proof, calls))

    assert calls, "The selector must see retrieved candidates before they are discarded"
    assert_objects(calls[0][0], common[:4])
    assert_objects(result, [proof, *common[:3]])


@pytest.mark.anyio
async def test_async_pre_cut_selector_can_retain_a_passage_ranked_below_four():
    retriever, common, proof, _ = fixture_retriever()
    calls = []
    result = await retriever.ainvoke("fixed query", candidate_selector=promoter(proof, calls))

    assert calls, "The selector must see retrieved candidates before they are discarded"
    assert_objects(calls[0][0], common[:4])
    assert_objects(result, [proof, *common[:3]])


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["fuse", "sync", "async"])
@pytest.mark.parametrize("k", [1, 4, 8])
async def test_default_preserves_rrf_order_budget_and_structural_filter(mode, k):
    retriever, common, proof, _ = fixture_retriever(k)
    expected = [*common, proof][:k]
    if mode == "fuse":
        result = retriever._fuse([lane.docs for lane in retriever.retrievers])
    elif mode == "sync":
        result = retriever.invoke("fixed query")
    else:
        result = await retriever.ainvoke("fixed query")
    assert_objects(result, expected)


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["sync", "async"])
@pytest.mark.parametrize("sparse_kind", ["absent", "explicit_none"])
async def test_default_keeps_existing_sparse_identity_and_first_object_preference(
    mode, sparse_kind
):
    metadata = {} if sparse_kind == "absent" else {"chunk_id": None}
    first = Document(page_content="First body", metadata=metadata)
    duplicate = Document(
        page_content="First body" if sparse_kind == "absent" else "Other body",
        metadata=metadata,
    )
    second = passage("second")
    retriever = HybridEnsembleRetriever(
        retrievers=[StaticLane(docs=[first, second]), StaticLane(docs=[duplicate, second])],
        weights=[0.3, 0.7],
        max_results=4,
    )
    if mode == "sync":
        result = retriever.invoke("fixed query", verbose=True)
    else:
        result = await retriever.ainvoke("fixed query", verbose=True)
    assert_objects(result, [first, second])
    assert all(not kwargs for lane in retriever.retrievers for kwargs in lane.received_kwargs)


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["sync", "async"])
async def test_selector_and_previously_ignored_kwargs_never_reach_child_lanes(mode):
    retriever, common, proof, _ = fixture_retriever()
    calls = []
    kwargs = {"candidate_selector": promoter(proof, calls), "verbose": True, "legacy_marker": 7}
    if mode == "sync":
        result = retriever.invoke("fixed query", **kwargs)
    else:
        result = await retriever.ainvoke("fixed query", **kwargs)
    assert_objects(result, [proof, *common[:3]])
    assert len(calls) == 1
    assert all(not kwargs for lane in retriever.retrievers for kwargs in lane.received_kwargs)


@pytest.mark.parametrize(
    "invalid", ["none", "empty", "foreign", "duplicate", "short", "long", "tuple", "structural"]
)
def test_invalid_selector_result_keeps_the_original_selection(invalid):
    retriever, common, _, structural = fixture_retriever()

    def choose(current, candidates):
        if invalid == "none":
            return None
        if invalid == "empty":
            return []
        if invalid == "foreign":
            return [deepcopy(current[0]), *current[1:]]
        if invalid == "duplicate":
            return [current[0]] * 4
        if invalid == "short":
            return current[:3]
        if invalid == "long":
            return list(candidates)[:5]
        if invalid == "tuple":
            return tuple(current)
        return [structural, *current[:3]]

    result = retriever.invoke("fixed query", candidate_selector=choose)
    assert_objects(result, common[:4])


def test_mutating_a_selector_list_then_failing_does_not_corrupt_baseline():
    retriever, common, _, _ = fixture_retriever()

    def choose(current, candidates):
        assert isinstance(candidates, tuple)
        current.clear()
        raise ValueError("synthetic selection failure")

    result = retriever.invoke("fixed query", candidate_selector=choose)
    assert_objects(result, common[:4])


def test_equal_sequence_is_normalized_to_baseline_without_mutating_documents():
    retriever, common, _, _ = fixture_retriever()
    snapshots = [(doc.page_content, deepcopy(doc.metadata), doc.id) for doc in common]
    received = []

    def choose(current, candidates):
        received.append(current)
        return current

    result = retriever.invoke("fixed query", candidate_selector=choose)
    assert len(received) == 1 and result is not received[0]
    assert_objects(result, common[:4])
    assert [(doc.page_content, doc.metadata, doc.id) for doc in common] == snapshots


def test_empty_baseline_does_not_invoke_selector_or_create_a_result():
    structural = passage("only-structural", "---")
    retriever = HybridEnsembleRetriever(
        retrievers=[StaticLane(docs=[structural]), StaticLane(docs=[])],
        weights=[0.3, 0.7],
        max_results=4,
    )

    def forbidden(current, candidates):
        pytest.fail("An empty baseline must not invoke the selector")

    assert retriever.invoke("fixed query", candidate_selector=forbidden) == []


class SelectionInterrupted(BaseException):
    pass


@pytest.mark.anyio
@pytest.mark.parametrize("interruption", [SelectionInterrupted, asyncio.CancelledError])
async def test_selector_baseexception_propagates_and_next_invocation_is_unchanged(interruption):
    retriever, common, _, _ = fixture_retriever()

    def interrupt(current, candidates):
        raise interruption()

    with pytest.raises(interruption):
        await retriever.ainvoke("interrupted query", candidate_selector=interrupt)
    assert_objects(await retriever.ainvoke("next query"), common[:4])


@pytest.mark.anyio
async def test_concurrent_invocations_do_not_share_selectors_or_next_call_state():
    retriever, common, proof, _ = fixture_retriever()
    first_calls, second_calls = [], []
    first, second = await asyncio.gather(
        retriever.ainvoke("first", candidate_selector=promoter(proof, first_calls)),
        retriever.ainvoke("second", candidate_selector=promoter(common[-1], second_calls)),
    )
    assert_objects(first, [proof, *common[:3]])
    assert_objects(second, [common[-1], *common[:3]])
    assert len(first_calls) == len(second_calls) == 1
    assert first_calls[0][0] is not second_calls[0][0]
    assert_objects(await retriever.ainvoke("default afterwards"), common[:4])
    assert all(not kwargs for lane in retriever.retrievers for kwargs in lane.received_kwargs)


class GatedLane(BaseRetriever):
    docs: list[Document]
    started: Any
    released: Any
    cancelled: Any
    finished: Any
    fail: bool = False

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        raise AssertionError("The lifecycle contract requires native asynchronous lanes")

    async def _aget_relevant_documents(self, query: str, *, run_manager: Any) -> list[Document]:
        self.started.set()
        try:
            await self.released.wait()
            if self.fail:
                raise RuntimeError("synthetic lane failure")
            return self.docs
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        finally:
            self.finished.set()


def gated_lane(ident, *, fail=False):
    return GatedLane(
        docs=[passage(ident)],
        started=asyncio.Event(),
        released=asyncio.Event(),
        cancelled=asyncio.Event(),
        finished=asyncio.Event(),
        fail=fail,
    )


@pytest.mark.anyio
@pytest.mark.parametrize("outcome", ["cancel", "lane_failure"])
async def test_incomplete_lanes_are_drained_without_calling_selector(outcome):
    left = gated_lane("left", fail=outcome == "lane_failure")
    right = gated_lane("right")
    retriever = HybridEnsembleRetriever(retrievers=[left, right], weights=[0.3, 0.7])
    calls = []

    def choose(current, candidates):
        calls.append(current)
        return current

    pending = asyncio.create_task(retriever.ainvoke("initial", candidate_selector=choose))
    await asyncio.wait_for(asyncio.gather(left.started.wait(), right.started.wait()), 1)
    if outcome == "cancel":
        pending.cancel()
        expected_error = asyncio.CancelledError
    else:
        left.released.set()
        expected_error = RuntimeError
    with pytest.raises(expected_error):
        await asyncio.wait_for(pending, 1)
    assert not calls
    assert left.finished.is_set() and right.finished.is_set()
    assert right.cancelled.is_set()
    if outcome == "cancel":
        assert left.cancelled.is_set()
    left.fail = False
    left.released.set()
    right.released.set()
    assert_objects(
        await asyncio.wait_for(retriever.ainvoke("next query"), 1),
        [*right.docs, *left.docs],
    )
