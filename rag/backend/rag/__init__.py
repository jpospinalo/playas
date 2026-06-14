"""RAG Playas package.

Configures a StreamHandler on the ``rag`` logger so INFO-level messages
(e.g. LLM token-usage lines) are visible in the terminal regardless of the
entry point (uvicorn, CLI scripts, tests).

Uvicorn's default ``dictConfig`` only attaches handlers to ``uvicorn.*``
loggers and leaves the root logger without handlers, so propagation alone is
not enough; we need an explicit handler here.
"""

import logging

_handler = logging.StreamHandler()
_handler.setFormatter(logging.Formatter("%(levelname)-8s %(name)s: %(message)s"))

_logger = logging.getLogger("rag")
_logger.setLevel(logging.INFO)
# Guard against duplicate handlers on hot-reload cycles (uvicorn --reload).
if not _logger.handlers:
    _logger.addHandler(_handler)
# Disable propagation: we own our handler; don't double-print if root ever
# gains a handler (e.g. logging.basicConfig called elsewhere).
_logger.propagate = False
