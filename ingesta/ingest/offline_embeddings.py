"""Embeddings locales por lotes y digest; nunca importa un proveedor LLM."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

MODEL = "embeddinggemma:latest"
DIGEST = "85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1"
DIMENSION = 768


def validate_vector(vector, dimension=DIMENSION):
    if not isinstance(vector, list) or len(vector) != dimension:
        raise ValueError("Dimensión de embedding incorrecta")
    if any(
        isinstance(x, bool) or not isinstance(x, (float, int)) or not math.isfinite(x)
        for x in vector
    ):
        raise ValueError("Embedding contiene un valor no finito/no numérico")
    return vector


class OllamaBatchEmbeddings:
    def __init__(
        self, cache: Path, base_url="http://localhost:11434", allow_remote=False, batch_size=16
    ):
        parsed = urllib.parse.urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
            raise ValueError("URL Ollama inválida")
        if parsed.hostname not in {"localhost", "127.0.0.1", "::1"} and not allow_remote:
            raise ValueError("Ollama remoto requiere autorización explícita --allow-remote-ollama")
        if batch_size <= 0:
            raise ValueError("batch-size debe ser positivo")
        self.base_url = base_url.rstrip("/")
        self.model, self.digest, self.dimension = MODEL, DIGEST, DIMENSION
        self.batch_size = batch_size
        self.new_embeddings = 0
        self.http_embedding_calls = 0
        self.embedding_seconds = 0.0
        cache.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(cache)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS vectors (key TEXT PRIMARY KEY, vector TEXT NOT NULL)"
        )
        models = self._request("/api/tags")["models"]
        if not any(m["name"] == self.model and m["digest"] == self.digest for m in models):
            raise ValueError("El digest de embeddinggemma no coincide con el pin; no publicar")

    def _request(self, path, body=None):
        if path not in {"/api/tags", "/api/embed"}:
            raise ValueError("Endpoint no autorizado")
        payload = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            self.base_url + path, data=payload, headers={"Content-Type": "application/json"}
        )
        for attempt in range(2):
            try:
                with urllib.request.urlopen(request, timeout=180) as response:
                    return json.load(response)
            except (urllib.error.URLError, TimeoutError):
                if attempt == 1:
                    raise RuntimeError("Ollama no respondió tras dos intentos") from None
                time.sleep(0.5)

    def embed(self, texts):
        keys = [hashlib.sha256((self.digest + "\0" + text).encode()).hexdigest() for text in texts]
        existing = {}
        pending = {}
        for key, text in zip(keys, texts, strict=True):
            row = self.db.execute("SELECT vector FROM vectors WHERE key=?", (key,)).fetchone()
            if row:
                existing[key] = validate_vector(json.loads(row[0]), self.dimension)
            else:
                pending[key] = text
        pairs = list(pending.items())
        for offset in range(0, len(pairs), self.batch_size):
            batch = pairs[offset : offset + self.batch_size]
            started = time.monotonic()
            # truncate=False impide truncamiento silencioso del contenido legal.
            result = self._request(
                "/api/embed",
                {
                    "model": self.model,
                    "input": [text for _, text in batch],
                    "truncate": False,
                    "keep_alive": "10m",
                },
            )
            self.embedding_seconds += time.monotonic() - started
            self.http_embedding_calls += 1
            vectors = result.get("embeddings", [])
            if len(vectors) != len(batch):
                raise ValueError("Ollama devolvió un lote incompleto")
            for (key, _), vector in zip(batch, vectors, strict=True):
                validate_vector(vector, self.dimension)
                existing[key] = vector
                self.db.execute(
                    "INSERT OR REPLACE INTO vectors VALUES (?,?)",
                    (key, json.dumps(vector, allow_nan=False)),
                )
                self.new_embeddings += 1
            self.db.commit()
        return [existing[key] for key in keys]

    def manifest(self):
        checksum = hashlib.sha256()
        for key, vector in self.db.execute("SELECT key,vector FROM vectors ORDER BY key"):
            checksum.update((key + "\0" + vector + "\n").encode())
        return {
            "model": self.model,
            "digest": self.digest,
            "dimension": self.dimension,
            "cache_checksum": checksum.hexdigest(),
            "new_embeddings": self.new_embeddings,
            "embedding_batch_calls": self.http_embedding_calls,
            "embedding_seconds": self.embedding_seconds,
            "seconds_per_new_chunk": self.embedding_seconds / self.new_embeddings
            if self.new_embeddings
            else 0,
            "llm_api_calls": 0,
        }

    def close(self):
        self.db.close()
