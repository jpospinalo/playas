"""Recuperación real del backend, pregunta cruda, métricas RAGAS sin LLM."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import os
import sys
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_DIGEST = "85462619ee721b466c5927d109d4cb765861907d5417b9109caebc4e614679f1"


def canonical(text):
    return " ".join(unicodedata.normalize("NFC", str(text)).split())


def key(source):
    return unicodedata.normalize("NFC", Path(str(source)).stem).casefold()


def ranks(docs, case, k):
    expected = {e["document_key"] for e in case["evidence"]}
    seen = []
    passage_rank = None
    for position, doc in enumerate(docs[:k], 1):
        source = key(doc.metadata.get("source", ""))
        if source not in seen:
            seen.append(source)
        if passage_rank is None and any(
            source == e["document_key"] and canonical(e["quote"]) in canonical(doc.page_content)
            for e in case["evidence"]
        ):
            passage_rank = position
    doc_rank = next((i for i, source in enumerate(seen, 1) if source in expected), None)
    return {
        "document_hit_at_k": float(doc_rank is not None),
        "document_mrr_at_k": 1 / doc_rank if doc_rank else 0.0,
        "passage_hit_at_k": float(passage_rank is not None),
        "passage_mrr_at_k": 1 / passage_rank if passage_rank else 0.0,
        "document_recall_at_k": len(set(seen) & expected) / len(expected),
    }


async def run(args):
    # El harness no construye el agente ni importa la fábrica de LLM.
    for name in ["OPENAI_API_KEY", "OPENROUTER_API_KEY", "GOOGLE_API_KEY", "GEMINI_API_KEY"]:
        os.environ[name] = ""
    os.environ.update(
        CHROMA_HOST="127.0.0.1",
        CHROMA_PORT=str(args.port),
        CHROMA_COLLECTION=args.collection,
        OLLAMA_BASE_URL=args.ollama,
        OLLAMA_EMBEDDING_MODEL="embeddinggemma:latest",
        AWS_EC2_METADATA_DISABLED="true",
        ANONYMIZED_TELEMETRY="False",
    )
    sys.path[:0] = [str(ROOT / "rag/backend"), str(ROOT / "rag")]
    import requests
    from ragas import SingleTurnSample
    from ragas.metrics import NonLLMContextPrecisionWithReference, NonLLMContextRecall

    from rag.core import retriever
    from rag.core.embeddings import OllamaEmbeddingClient

    assert importlib.metadata.version("ragas") == "0.4.3", "Se requiere RAGAS 0.4.3"
    models = requests.get(args.ollama.rstrip("/") + "/api/tags", timeout=10).json()["models"]
    assert any(
        m["name"] == "embeddinggemma:latest" and m["digest"] == EXPECTED_DIGEST for m in models
    ), "Digest de embeddings distinto"
    config = {
        "harness_version": "level0-2-source-constrained-passage",
        "k": 4,
        "k_candidates": 8,
        "query": "raw",
        "doc_types": None,
        "ragas": "0.4.3",
        "ragas_threshold": 0.5,
        "embedding_model": "embeddinggemma:latest",
        "embedding_digest": EXPECTED_DIGEST,
        "evidence_matching": "NFC + whitespace",
        "document_rank": "deduplicated source stem NFC casefold",
        "backend_sha256": hashlib.sha256(
            (ROOT / "rag/backend/rag/core/retriever.py").read_bytes()
        ).hexdigest(),
    }
    config_hash = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    dataset_hash = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    cache_dir = ROOT / "evaluation/ragas/.cache"
    cache_dir.mkdir(exist_ok=True)
    cache_path = cache_dir / "query_vectors.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    original = OllamaEmbeddingClient.embed_one

    def cached_embed(client, text):
        cache_key = hashlib.sha256((EXPECTED_DIGEST + "\0" + text).encode()).hexdigest()
        if cache_key not in cache:
            cache[cache_key] = original(client, text)
            cache_path.write_text(json.dumps(cache))
        return cache[cache_key]

    OllamaEmbeddingClient.embed_one = cached_embed
    metrics = {
        "nonllm_context_recall": NonLLMContextRecall(),
        "nonllm_context_precision": NonLLMContextPrecisionWithReference(),
    }
    cases = [
        json.loads(line) for line in args.dataset.read_text(encoding="utf-8").splitlines() if line
    ]
    previous = (
        [json.loads(line) for line in args.output.read_text().splitlines()]
        if args.output.exists()
        else []
    )
    if any(
        r["config_hash"] != config_hash
        or r["dataset_sha256"] != dataset_hash
        or r["collection"] != args.collection
        for r in previous
    ):
        raise ValueError("Checkpoint de otra configuración/dataset/colección")
    done = {r["id"] for r in previous}
    retriever.init_retrievers()
    engine = retriever.get_ensemble_retriever(k=4, k_candidates=8)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("a", encoding="utf-8") as stream:
        for case in cases:
            if case["id"] in done:
                continue
            started = time.monotonic()
            docs = engine.invoke(case["pregunta"])
            contexts = [d.page_content for d in docs]
            sample = SingleTurnSample(
                retrieved_contexts=contexts, reference_contexts=case["reference_contexts"]
            )
            scores = ranks(docs, case, 4)
            for name, metric in metrics.items():
                scores[name] = float(await metric.single_turn_ascore(sample))
            row = {
                "id": case["id"],
                "categoria": case["categoria"],
                "collection": args.collection,
                "config_hash": config_hash,
                "dataset_sha256": dataset_hash,
                "scores": scores,
                "retrieved": [
                    {
                        "source": d.metadata.get("source"),
                        "chunk_id": d.metadata.get("chunk_id", d.metadata.get("id")),
                        "characters": len(d.page_content),
                    }
                    for d in docs
                ],
                "seconds": round(time.monotonic() - started, 4),
                "llm_api_calls": 0,
                "validado_por_abogado": False,
            }
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.flush()
            print(case["id"], json.dumps(scores), flush=True)
    retriever.close_retrievers()
    (args.output.parent / (args.output.stem + ".config.json")).write_text(
        json.dumps(
            {
                "config": config,
                "config_hash": config_hash,
                "dataset_sha256": dataset_hash,
                "collection": args.collection,
                "validado_por_abogado": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--collection", required=True)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--ollama", required=True)
    parser.add_argument("--dataset", type=Path, default=ROOT / "evaluation/ragas/dataset_v1.jsonl")
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(run(parser.parse_args()))
