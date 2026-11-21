"""P05: deterministic regressions for ownership of retriever initialization.

The tests call the real lifespan, asyncio.to_thread, initializer, getters and
cleanup. Only constructors, document input, SQL and graph/HTTP boundaries are
synthetic. The source map below fixes twelve cases before collection: ten
contract failures on the unrepaired source and two positive controls.

No test requires an artifact directory, an external runner or a desktop path.
P05_CONTRACT means an observed ownership violation. Any other exception stops
the session after safe draining; uncertain draining exits without restoration.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from collections import deque
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

WAIT_SECONDS = 5.0
BARRIER_SECONDS = 20.0
INVALIDATED_CLASS = "_RetrieverInitializationInvalidated"
INVALIDATED_MESSAGE = "Retriever initialization was invalidated"

_CALL_KEYS = (
    "sql_init",
    "sql_dispose",
    "sdk",
    "store",
    "documents",
    "embedding_close",
    "chroma_enter",
    "chroma_exit",
    "embedding_enter",
    "embedding_exit",
    "graph",
    "cancel_requests",
    "worker",
)


def _counts(**overrides):
    if not set(overrides) <= set(_CALL_KEYS):
        raise ValueError("P05_HARNESS unknown_counter_in_source_map")
    return dict.fromkeys(_CALL_KEYS, 0) | overrides


# Expectations describe the repaired behavior, including every zero boundary.
# They are source data, not counts inferred from a run or conditional xfails.
CASE_EXPECTATIONS = {
    "cancel-sdk": (
        "red",
        _counts(sql_init=1, sql_dispose=1, sdk=1, embedding_close=1, cancel_requests=1, worker=1),
    ),
    "cancel-store": (
        "red",
        _counts(
            sql_init=1,
            sql_dispose=1,
            sdk=1,
            store=1,
            embedding_close=1,
            cancel_requests=1,
            worker=1,
        ),
    ),
    "cancel-bm25-nonempty": (
        "red",
        _counts(
            sql_init=1,
            sql_dispose=1,
            sdk=1,
            store=1,
            documents=1,
            embedding_close=1,
            cancel_requests=1,
            worker=1,
        ),
    ),
    "cancel-bm25-empty": (
        "red",
        _counts(
            sql_init=1,
            sql_dispose=1,
            sdk=1,
            store=1,
            documents=1,
            embedding_close=1,
            cancel_requests=1,
            worker=1,
        ),
    ),
    "entry-after-close": (
        "red",
        _counts(sql_init=1, sql_dispose=1, embedding_close=1, cancel_requests=1, worker=1),
    ),
    "restart-blocked-bm25": (
        "red",
        _counts(
            sql_init=2,
            sql_dispose=2,
            sdk=2,
            store=2,
            documents=2,
            embedding_close=2,
            chroma_enter=1,
            chroma_exit=1,
            embedding_enter=1,
            embedding_exit=1,
            graph=1,
            cancel_requests=1,
            worker=2,
        ),
    ),
    "restart-cached-cycle": (
        "red",
        _counts(
            sql_init=2,
            sql_dispose=2,
            sdk=1,
            store=1,
            documents=1,
            embedding_close=2,
            chroma_enter=1,
            chroma_exit=1,
            embedding_enter=1,
            embedding_exit=1,
            graph=1,
            cancel_requests=1,
            worker=2,
        ),
    ),
    "waiting-blocked-bm25": (
        "red",
        _counts(
            sql_init=1, sql_dispose=1, sdk=1, store=1, documents=1, embedding_close=2, worker=1
        ),
    ),
    "waiting-after-real-return": (
        "red",
        _counts(
            sql_init=1, sql_dispose=1, sdk=1, store=1, documents=1, embedding_close=2, worker=1
        ),
    ),
    "embedding-close-error": (
        "red",
        _counts(
            sql_init=1,
            sql_dispose=1,
            sdk=1,
            store=1,
            documents=1,
            embedding_close=1,
            cancel_requests=1,
            worker=1,
        ),
    ),
    "context-success": (
        "green",
        _counts(
            sql_init=1,
            sql_dispose=1,
            sdk=2,
            store=2,
            documents=2,
            embedding_close=2,
            chroma_enter=1,
            chroma_exit=1,
            embedding_enter=1,
            embedding_exit=1,
            graph=1,
            worker=1,
        ),
    ),
    "context-real-error": (
        "green",
        _counts(
            sql_init=1,
            sql_dispose=1,
            sdk=2,
            store=2,
            documents=2,
            embedding_close=2,
            chroma_enter=1,
            chroma_exit=1,
            embedding_enter=1,
            embedding_exit=1,
            graph=1,
            worker=1,
        ),
    ),
}


class _ContractFailure(AssertionError):
    """An expected-red assertion, never an infrastructure classification."""


class _HarnessFailure(RuntimeError):
    """An inconclusive run which must not proceed to another case."""


class _SyntheticDependencyError(ValueError):
    """A unique real-error sentinel, deliberately different from invalidation."""


def _contract(condition, label):
    if not condition:
        raise _ContractFailure("P05_CONTRACT " + label)


def _require(condition, label):
    if not condition:
        raise _HarnessFailure("P05_HARNESS " + label)


class _Gate:
    def __init__(self, loop, label):
        self.loop = loop
        self.label = label
        self.entered = asyncio.Event()
        self.release = threading.Event()

    def block(self):
        self.loop.call_soon_threadsafe(self.entered.set)
        if not self.release.wait(BARRIER_SECONDS):
            raise _HarnessFailure("P05_HARNESS barrier_timeout_" + self.label)


class _Worker:
    def __init__(self):
        self.started = threading.Event()
        self.product_done = threading.Event()
        self.completed = asyncio.Event()
        self.real_entered = False
        self.real_returned = False
        self.different_thread = False
        self.error = None


class _Run:
    """One task owns both entry and exit of its synthetic application."""

    def __init__(self, harness):
        self.harness = harness
        self.app = SimpleNamespace(state=SimpleNamespace())
        self.worker = _Worker()
        self.resolved = asyncio.Event()
        self.stop = asyncio.Event()
        self.entered = False
        self.cancel_requested = False
        self.error = None
        self.task = None

    async def drive(self):
        try:
            async with self.harness.real["lifespan"](self.app):
                self.entered = True
                self.resolved.set()
                await self.stop.wait()
        except BaseException as exc:
            self.error = exc
            raise
        finally:
            self.resolved.set()


class _Harness:
    def __init__(self, case, *, boundary=None, empty=False):
        # Product imports happen only when a reviewed test body runs.
        from langchain_core.documents import Document

        import rag.api.database as database
        import rag.api.main as main
        import rag.core.agent as agent
        import rag.core.retriever as retriever

        self.case = case
        self.boundary = boundary
        self.loop = asyncio.get_running_loop()
        self.controller_ident = threading.get_ident()
        self.database = database
        self.main = main
        self.agent = agent
        self.retriever = retriever
        self.real = {
            "init": retriever.init_retrievers,
            "client": retriever._get_chroma_client,
            "store": retriever._get_chroma_vectorstore,
            "bm25": retriever._get_bm25_base,
            "close": retriever.close_retrievers,
            "lifespan": main.lifespan,
            "to_thread": asyncio.to_thread,
        }
        _require(main.init_retrievers is self.real["init"], "initializer_alias_mismatch")
        _require(main.close_retrievers is self.real["close"], "cleanup_alias_mismatch")
        self.documents = (
            []
            if empty
            else [
                Document(page_content="Playa sintética alfa", metadata={"source": "p05-alfa"}),
                Document(page_content="Costa sintética beta", metadata={"source": "p05-beta"}),
            ]
        )
        self.calls = _counts()
        self.counter_lock = threading.Lock()
        self.pending_workers = deque()
        self.runs = []
        self.originals = []
        self.clients = []
        self.stores = []
        self.graphs = []
        self.query = object()
        self.query_embedder = object()
        self.close_error = None
        self.document_error = None
        self.allowed_errors = []
        self.embeddings = SimpleNamespace(close=self.close_embeddings)
        self.gates = {
            name: _Gate(self.loop, name)
            for name in ("sdk", "store", "bm25", "before-init", "after-real-return")
        }

    def bump(self, key):
        with self.counter_lock:
            self.calls[key] += 1
            return self.calls[key]

    def patch(self, owner, name, value):
        original = getattr(owner, name)
        self.originals.append((owner, name, original))
        setattr(owner, name, value)

    def install(self):
        self.patch(self.database, "init_db", self.init_sql)
        self.patch(self.database, "engine", SimpleNamespace(dispose=self.dispose_sql))
        self.patch(self.retriever.chromadb, "HttpClient", self.make_client)
        self.patch(self.retriever, "Chroma", self.make_store)
        self.patch(self.retriever, "EMBEDDINGS", self.embeddings)
        self.patch(self.retriever, "load_all_docs_from_chroma", self.load_documents)
        for name in ("_chroma_client", "_chroma_vectorstore", "_bm25_base"):
            self.patch(self.retriever, name, None)
        self.patch(self.main, "_graph", None)
        self.patch(self.main, "init_retrievers", self.initialize)
        self.patch(self.main, "open_chroma_query", self.open_chroma)
        self.patch(self.main, "open_query_embeddings", self.open_embeddings)
        self.patch(self.agent, "build_graph", self.build_graph)
        self.require_real_functions()

    def require_real_functions(self):
        _require(
            all(
                (
                    self.retriever.init_retrievers is self.real["init"],
                    self.retriever._get_chroma_client is self.real["client"],
                    self.retriever._get_chroma_vectorstore is self.real["store"],
                    self.retriever._get_bm25_base is self.real["bm25"],
                    self.retriever.close_retrievers is self.real["close"],
                    self.main.close_retrievers is self.real["close"],
                    self.main.lifespan is self.real["lifespan"],
                    asyncio.to_thread is self.real["to_thread"],
                )
            ),
            "real_function_replaced",
        )

    async def init_sql(self):
        self.bump("sql_init")

    async def dispose_sql(self):
        self.bump("sql_dispose")

    def close_embeddings(self):
        self.bump("embedding_close")
        if self.close_error is not None:
            raise self.close_error

    def make_client(self, *args, **kwargs):
        del args, kwargs
        number = self.bump("sdk")
        client = object()
        self.clients.append(client)
        if self.boundary == "sdk" and number == 1:
            self.gates["sdk"].block()
        return client

    def make_store(self, *args, **kwargs):
        del args
        number = self.bump("store")
        _require(
            any(kwargs.get("client") is client for client in self.clients),
            "unknown_synthetic_client",
        )
        _require(kwargs.get("embedding_function") is self.embeddings, "wrong_embeddings")
        _require(
            kwargs.get("create_collection_if_not_exists") is False, "collection_creation_enabled"
        )
        store = object()
        self.stores.append(store)
        if self.boundary == "store" and number == 1:
            self.gates["store"].block()
        return store

    def load_documents(self):
        number = self.bump("documents")
        if self.boundary == "bm25" and number == 1:
            self.gates["bm25"].block()
        if self.document_error is not None:
            raise self.document_error
        return list(self.documents)

    @asynccontextmanager
    async def open_chroma(self):
        self.bump("chroma_enter")
        try:
            yield self.query
        finally:
            self.bump("chroma_exit")

    @asynccontextmanager
    async def open_embeddings(self):
        self.bump("embedding_enter")
        try:
            yield self.query_embedder
        finally:
            self.bump("embedding_exit")

    def build_graph(self, **kwargs):
        self.bump("graph")
        _require(kwargs.get("chroma_query") is self.query, "wrong_query_boundary")
        _require(kwargs.get("query_embedder") is self.query_embedder, "wrong_embedding_boundary")
        graph = object()
        self.graphs.append(graph)
        return graph

    def initialize(self):
        with self.counter_lock:
            _require(bool(self.pending_workers), "unowned_worker")
            worker = self.pending_workers.popleft()
        number = self.bump("worker")
        worker.started.set()
        worker.different_thread = threading.get_ident() != self.controller_ident
        try:
            if self.boundary == "before-init" and number == 1:
                self.gates["before-init"].block()
            worker.real_entered = True
            self.real["init"]()
            worker.real_returned = True
            if self.boundary == "after-real-return" and number == 1:
                self.gates["after-real-return"].block()
        except BaseException as exc:
            worker.error = exc
            raise
        finally:
            # No product state can change after this marker. The completion
            # notification is recovered before patches or the loop are restored.
            worker.product_done.set()
            self.loop.call_soon_threadsafe(worker.completed.set)

    def start(self):
        run = _Run(self)
        self.runs.append(run)
        with self.counter_lock:
            self.pending_workers.append(run.worker)
        run.task = asyncio.create_task(run.drive())
        return run

    def cancel_once(self, run):
        if run.task.done() or run.cancel_requested:
            return
        _require(self.calls["cancel_requests"] == 0, "second_cancellation_forbidden")
        self.bump("cancel_requests")
        run.cancel_requested = True
        run.task.cancel()

    async def wait_event(self, event, label):
        try:
            await asyncio.wait_for(event.wait(), WAIT_SECONDS)
        except TimeoutError as exc:
            raise _HarnessFailure("P05_HARNESS wait_timeout_" + label) from exc

    async def wait_done(self, run):
        done, _ = await asyncio.wait({run.task}, timeout=WAIT_SECONDS)
        _require(bool(done), "lifespan_completion_not_confirmed")
        if not run.task.cancelled():
            run.task.exception()  # Always retrieve the task's exception.

    async def wait_worker(self, run):
        await self.wait_event(run.worker.completed, "worker_completion")
        _require(run.worker.product_done.is_set(), "worker_final_marker_missing")
        _require(run.worker.different_thread, "initializer_not_in_worker_thread")
        if run.worker.error is not None:
            _require(
                self.is_allowed_error(run.worker.error),
                "unexpected_worker_exception_" + type(run.worker.error).__name__,
            )

    async def wait_startup(self, run):
        await self.wait_event(run.resolved, "startup_result")
        if not run.entered:
            await self.wait_done(run)

    def is_invalidated(self, error):
        # Absence on the old source is allowed. It never causes import/attribute
        # failure or substitutes a generic RuntimeError for the expected signal.
        expected = getattr(self.retriever, INVALIDATED_CLASS, None)
        return expected is not None and type(error) is expected

    def is_allowed_error(self, error):
        return self.is_invalidated(error) or any(
            error is allowed for allowed in self.allowed_errors
        )

    def require_invalidated(self, error, label):
        if error is not None and not self.is_invalidated(error):
            raise _HarnessFailure("P05_HARNESS unexpected_signal_" + type(error).__name__)
        _contract(error is not None, label + "_returned_without_invalidation")
        _contract(type(error).__name__ == INVALIDATED_CLASS, label + "_wrong_invalidation_class")
        _contract(str(error) == INVALIDATED_MESSAGE, label + "_wrong_invalidation_message")

    def state(self):
        return (
            self.retriever._chroma_client,
            self.retriever._chroma_vectorstore,
            self.retriever._bm25_base,
        )

    def require_empty(self, label):
        _contract(all(value is None for value in self.state()), label + "_singletons_repopulated")

    def require_no_graph(self, run, label):
        _contract(not run.entered, label + "_entered_lifespan_body")
        _contract(self.main._graph is None, label + "_global_graph_published")
        _contract(
            getattr(run.app.state, "graph", None) is None, label + "_application_graph_published"
        )
        _contract(
            getattr(run.app.state, "conversation_locks", None) is None,
            label + "_application_locks_published",
        )
        _contract(
            all(self.calls[key] == 0 for key in ("chroma_enter", "embedding_enter", "graph")),
            label + "_continued_to_http_or_graph",
        )

    def require_counts(self):
        expected = CASE_EXPECTATIONS[self.case][1]
        _contract(
            self.calls == expected,
            self.case
            + "_boundary_counts_"
            + json.dumps({"actual": self.calls, "expected": expected}, sort_keys=True),
        )

    def emergency(self, label):
        evidence = {
            "event": "P05_HARNESS_INCONCLUSIVE",
            "case": self.case,
            "reason": label,
            "restored": False,
            "calls": self.calls,
            "runs": [
                {
                    "task_done": run.task.done(),
                    "worker_started": run.worker.started.is_set(),
                    "product_done": run.worker.product_done.is_set(),
                }
                for run in self.runs
            ],
        }
        try:
            os.write(2, (json.dumps(evidence, sort_keys=True) + "\n").encode("utf-8"))
        finally:
            # Only unconfirmed owner completion reaches this branch. No fixture
            # can restore globals under a live worker or continue the session.
            os._exit(3)

    async def finish(self):
        for gate in self.gates.values():
            gate.release.set()
        for run in self.runs:
            run.stop.set()
            if not run.task.done() and not run.entered and not run.cancel_requested:
                if self.calls["cancel_requests"] == 0:
                    self.cancel_once(run)
        # Fail closed before restoration if either owner cannot be recovered.
        drain_errors = []
        for run in self.runs:
            try:
                await self.wait_done(run)
                await self.wait_worker(run)
            except BaseException as exc:
                if (
                    not run.task.done()
                    or not run.worker.product_done.is_set()
                    or not run.worker.completed.is_set()
                ):
                    self.emergency(type(exc).__name__)
                # Completion is certain, but classification may still be bad.
                # Restore only after checking *all* owners below.
                drain_errors.append(
                    str(exc) if isinstance(exc, _HarnessFailure) else type(exc).__name__
                )
        all_done = all(
            run.task.done() and run.worker.product_done.is_set() and run.worker.completed.is_set()
            for run in self.runs
        )
        if not all_done:
            self.emergency("owner_completion_not_confirmed")
        errors = drain_errors
        for run in self.runs:
            if run.worker.error is not None and not self.is_allowed_error(run.worker.error):
                errors.append("unexpected_worker_exception_" + type(run.worker.error).__name__)
            if run.error is not None and not isinstance(run.error, asyncio.CancelledError):
                if not self.is_allowed_error(run.error):
                    errors.append("unexpected_lifespan_exception_" + type(run.error).__name__)
            if isinstance(run.error, asyncio.CancelledError) and not run.cancel_requested:
                errors.append("unrequested_lifespan_cancellation")
        try:
            self.require_real_functions()
        except _HarnessFailure as exc:
            errors.append(str(exc))
        for owner, name, original in reversed(self.originals):
            setattr(owner, name, original)
        _require(
            all(getattr(owner, name) is original for owner, name, original in self.originals),
            "reference_restoration_failed",
        )
        _require(not errors, ";".join(errors))


def _run(case, scenario, **options):
    async def execute():
        harness = _Harness(case, **options)
        try:
            harness.install()
            await scenario(harness)
        finally:
            await harness.finish()

    try:
        asyncio.run(execute())
    except _ContractFailure:
        raise
    except BaseException as exc:
        # Every ordinary path has drained/restored above. A guard/environment
        # failure stops later tests instead of resembling an expected red.
        detail = str(exc) if isinstance(exc, _HarnessFailure) else type(exc).__name__
        pytest.exit("P05_HARNESS " + case + ": " + detail, returncode=3)


@pytest.mark.parametrize(
    ("boundary", "empty", "case"),
    [
        pytest.param("sdk", False, "cancel-sdk", id="sdk"),
        pytest.param("store", False, "cancel-store", id="store"),
        pytest.param("bm25", False, "cancel-bm25-nonempty", id="bm25-nonempty"),
        pytest.param("bm25", True, "cancel-bm25-empty", id="bm25-empty"),
    ],
)
def test_cancelled_startup_rejects_late_publication(boundary, empty, case):
    async def scenario(h):
        run = h.start()
        gate = h.gates[boundary]
        await h.wait_event(gate.entered, "constructor_entry")
        _require(not run.worker.product_done.is_set(), "worker_not_held_at_boundary")
        h.cancel_once(run)
        await h.wait_done(run)
        _contract(run.task.cancelled(), "caller_cancellation_not_preserved")
        h.require_empty("cancelled_cleanup")
        h.require_no_graph(run, "cancelled_cleanup")
        _require(
            not gate.release.is_set() and not run.worker.product_done.is_set(),
            "cleanup_not_observed_while_worker_held",
        )
        gate.release.set()
        await h.wait_worker(run)
        h.require_empty("late_" + boundary)
        h.require_invalidated(run.worker.error, "late_" + boundary)
        h.require_no_graph(run, "late_" + boundary)
        h.require_counts()

    _run(case, scenario, boundary=boundary, empty=empty)


def test_cancelled_worker_enters_real_initializer_after_close():
    async def scenario(h):
        run = h.start()
        gate = h.gates["before-init"]
        await h.wait_event(gate.entered, "before_real_initializer")
        _require(not run.worker.real_entered, "real_initializer_entered_too_early")
        h.cancel_once(run)
        await h.wait_done(run)
        _contract(run.task.cancelled(), "entry_caller_cancellation_not_preserved")
        h.require_empty("entry_cleanup")
        _require(not run.worker.product_done.is_set(), "entry_worker_not_held")
        gate.release.set()
        await h.wait_worker(run)
        h.require_empty("entry_after_close")
        h.require_invalidated(run.worker.error, "entry_after_close")
        h.require_no_graph(run, "entry_after_close")
        h.require_counts()

    _run("entry-after-close", scenario, boundary="before-init")


@pytest.mark.parametrize(
    ("boundary", "case"),
    [
        pytest.param("bm25", "restart-blocked-bm25", id="blocked-bm25"),
        pytest.param("before-init", "restart-cached-cycle", id="cached-cycle"),
    ],
)
def test_previous_worker_preserves_later_cycle(boundary, case):
    async def scenario(h):
        previous = h.start()
        gate = h.gates[boundary]
        await h.wait_event(gate.entered, "previous_worker_entry")
        previous_state = h.state()
        h.cancel_once(previous)
        await h.wait_done(previous)
        _contract(previous.task.cancelled(), "previous_caller_cancellation_not_preserved")
        h.require_empty("between_cycles")
        current = h.start()
        await h.wait_startup(current)
        _contract(current.entered and current.error is None, "later_cycle_failed_to_start")
        await h.wait_worker(current)
        current_state = h.state()
        _contract(all(value is not None for value in current_state), "later_cycle_missing_state")
        _contract(
            all(
                new is not old
                for new, old in zip(current_state, previous_state, strict=True)
                if old is not None
            ),
            "later_cycle_reused_old_reference",
        )
        _contract(h.real["client"]() is current_state[0], "later_cycle_client_cache_changed")
        _contract(h.real["store"]() is current_state[1], "later_cycle_store_cache_changed")
        _contract(h.real["bm25"]() is current_state[2], "later_cycle_bm25_cache_changed")
        graph = h.main._graph
        _contract(
            current.app.state.graph is graph and graph is h.graphs[-1],
            "later_cycle_graph_identity_changed",
        )
        gate.release.set()
        await h.wait_worker(previous)
        _contract(
            all(
                actual is expected
                for actual, expected in zip(h.state(), current_state, strict=True)
            ),
            "previous_worker_replaced_or_cleared_later_cycle",
        )
        h.require_invalidated(previous.worker.error, "previous_worker_cached_cycle")
        _contract(
            h.main._graph is graph and current.app.state.graph is graph,
            "previous_worker_cleared_later_graph",
        )
        current.stop.set()
        await h.wait_done(current)
        _contract(current.error is None, "later_cycle_shutdown_failed")
        h.require_empty("later_cycle_shutdown")
        h.require_counts()

    _run(case, scenario, boundary=boundary)


@pytest.mark.parametrize(
    ("boundary", "case"),
    [
        pytest.param("bm25", "waiting-blocked-bm25", id="blocked-bm25"),
        pytest.param("after-real-return", "waiting-after-real-return", id="after-real-return"),
    ],
)
def test_waiting_caller_rejects_invalidated_initialization(boundary, case):
    async def scenario(h):
        run = h.start()
        gate = h.gates[boundary]
        await h.wait_event(gate.entered, "waiting_caller_boundary")
        if boundary == "after-real-return":
            _require(run.worker.real_returned, "initializer_has_not_really_returned")
            _require(all(value is not None for value in h.state()), "initial_state_missing")
        _require(not run.task.done() and not run.cancel_requested, "caller_not_waiting")
        h.real["close"]()
        h.require_empty("external_invalidation")
        gate.release.set()
        await h.wait_worker(run)
        await h.wait_startup(run)
        h.require_no_graph(run, "waiting_caller_invalidation")
        h.require_empty("waiting_caller_invalidation")
        h.require_invalidated(run.error, "waiting_caller")
        if boundary == "after-real-return":
            _contract(
                run.worker.error is None and run.worker.real_returned,
                "outer_validation_replaced_worker_result",
            )
        else:
            h.require_invalidated(run.worker.error, "waiting_worker")
        _contract(h.calls["cancel_requests"] == 0, "waiting_caller_was_cancelled")
        h.require_counts()

    _run(case, scenario, boundary=boundary)


def test_failed_embedding_close_still_invalidates_worker():
    async def scenario(h):
        marker = _SyntheticDependencyError("synthetic embedding close failure")
        h.close_error = marker
        h.allowed_errors.append(marker)
        run = h.start()
        gate = h.gates["bm25"]
        await h.wait_event(gate.entered, "embedding_failure_boundary")
        h.cancel_once(run)
        await h.wait_done(run)
        _contract(run.error is marker, "embedding_close_error_not_preserved")
        _contract(h.calls["sql_dispose"] == 1, "embedding_failure_skipped_sql_dispose")
        clean_before_release = all(value is None for value in h.state())
        _require(not run.worker.product_done.is_set(), "embedding_failure_worker_not_held")
        gate.release.set()
        await h.wait_worker(run)
        _contract(clean_before_release, "embedding_failure_skipped_invalidation_and_discard")
        h.require_empty("embedding_failure_late_worker")
        h.require_invalidated(run.worker.error, "embedding_failure_worker")
        h.require_no_graph(run, "embedding_failure")
        h.require_counts()

    _run("embedding-close-error", scenario, boundary="bm25")


@pytest.mark.parametrize("first_error", [False, True], ids=["success", "real-error"])
def test_real_initialization_restores_context(first_error):
    async def scenario(h):
        # Direct real calls share this task's context and have no outer lifespan
        # scope. Closing between them reveals a leaked identity after success
        # or a genuine dependency exception without naming a future ContextVar.
        marker = _SyntheticDependencyError("synthetic document input failure")
        if first_error:
            h.document_error = marker
            try:
                h.real["init"]()
            except BaseException as exc:
                if exc is not marker and not h.is_invalidated(exc):
                    raise _HarnessFailure(
                        "P05_HARNESS unexpected_dependency_error_" + type(exc).__name__
                    ) from exc
                _contract(exc is marker, "real_error_replaced_by_invalidation")
            else:
                _contract(False, "real_dependency_error_was_suppressed")
            finally:
                h.document_error = None
        else:
            h.real["init"]()
        previous_state = h.state()
        h.real["close"]()
        h.require_empty("positive_direct_close")
        try:
            h.real["init"]()
        except BaseException as exc:
            if h.is_invalidated(exc):
                raise _ContractFailure("P05_CONTRACT initialization_context_not_restored") from exc
            raise
        current_state = h.state()
        _contract(
            all(value is not None for value in current_state), "positive_reinitialization_empty"
        )
        _contract(
            all(
                new is not old
                for new, old in zip(current_state, previous_state, strict=True)
                if old is not None
            ),
            "positive_reinitialization_reused_closed_reference",
        )
        run = h.start()
        await h.wait_startup(run)
        _contract(run.entered and run.error is None, "positive_real_startup_failed")
        await h.wait_worker(run)
        _contract(
            all(
                actual is expected
                for actual, expected in zip(h.state(), current_state, strict=True)
            ),
            "positive_cache_not_reused",
        )
        run.stop.set()
        await h.wait_done(run)
        _contract(run.error is None, "positive_real_shutdown_failed")
        h.require_empty("positive_real_shutdown")
        h.require_counts()

    case = "context-real-error" if first_error else "context-success"
    _run(case, scenario)
