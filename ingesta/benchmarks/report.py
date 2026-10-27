"""Tablas de mediciones y proyecciones explícitas, sin consultar servicios ni precios."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from .common import finite_positive, output_dir, positive, sizes


def extrapolate(measurements, documents):
    """Ajuste lineal OLS: segundos = intercepto + pendiente * documentos."""
    positive(documents)
    if len(measurements) < 2:
        raise ValueError("Se requieren al menos dos escalas medidas")
    x = [finite_positive(row["documents"]) for row in measurements]
    y = [finite_positive(row["wall_seconds"]) for row in measurements]
    mx, my = sum(x) / len(x), sum(y) / len(y)
    denominator = sum((value - mx) ** 2 for value in x)
    if not denominator:
        raise ValueError("Se requieren escalas distintas")
    slope = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=True)) / denominator
    intercept = my - slope * mx
    prediction = intercept + slope * documents
    if slope <= 0 or prediction <= 0:
        raise ValueError("Las mediciones no permiten una proyección positiva creciente")
    return {
        "documents": documents,
        "wall_seconds": prediction,
        "docs_per_hour": documents * 3600 / prediction,
        "slope_seconds_per_doc": slope,
        "intercept_seconds": intercept,
        "measured_scales": sorted(set(x)),
        "extrapolated": True,
        "status": "EXTRAPOLADA",
        "method": "ajuste lineal OLS de tiempo frente a documentos",
    }


def extrapolate_embeddings(chunks, embeddings_per_second):
    positive(chunks)
    finite_positive(embeddings_per_second)
    return {
        "chunks": chunks,
        "embedding_seconds": chunks / embeddings_per_second,
        "embeddings_per_second": embeddings_per_second,
        "extrapolated": True,
        "status": "EXTRAPOLADA",
        "method": "chunks / embeddings por segundo medidos; supone todos nuevos",
    }


def cell(value):
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.4f}" if math.isfinite(value) else "—"
    return str(value).replace("|", "\\|").replace("\n", " ")


def table(title, headers, rows):
    if not rows:
        return []
    return [
        f"## {title}",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *("| " + " | ".join(cell(c) for c in row) + " |" for row in rows),
        "",
    ]


def load_results(root):
    results = []
    for path in sorted(Path(root).rglob("*.json")):
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(item, dict) and item.get("benchmark"):
            results.append((path.relative_to(root).as_posix(), item))
    return results


def render_report(results, extrapolate_sizes=(), chunks_per_doc=None):
    lines = [
        "# Escalabilidad: mediciones y proyecciones",
        "",
        "Los tiempos de etapas proceden del pipeline; el tiempo total incluye arranque y cierre del subproceso. CPU/RSS excluyen los servidores Ollama y Chroma. Embeddings ficticios: embeddings NO medidos.",
        "",
    ]
    pipeline_rows, stages, disks, extraction, embeddings, simhash, chroma, costs = (
        [] for _ in range(8)
    )
    groups = {}
    measured_embedding_rates = []
    for source, item in results:
        kind = item["benchmark"]
        if kind == "run_pipeline":
            for run in item["runs"]:
                report = run.get("pipeline") or {}
                resources = run["resources"]
                docs = report.get("documents")
                status = "MEDIDA" if run.get("success") else "FALLIDA"
                mode = "ficticios: NO medidos" if item["fake_embeddings"] else "reales"
                pipeline_rows.append(
                    [
                        source,
                        run["label"],
                        docs,
                        report.get("processed"),
                        mode,
                        status,
                        resources["wall_seconds"],
                        run.get("docs_per_hour"),
                        run.get("chunks_per_second"),
                        run.get("embeddings_per_second"),
                        run.get("embedding_cache_hits"),
                        run.get("new_embeddings"),
                        run.get("embedding_cache_hit_rate"),
                        run.get("embedding_pending_duplicates"),
                        resources.get("cpu_percent"),
                        resources.get("cpu_seconds"),
                        resources.get("max_rss_bytes"),
                    ]
                )
                for stage, timing in run.get("stage_timings", {}).items():
                    stages.append(
                        [
                            source,
                            run["label"],
                            docs,
                            stage,
                            timing["seconds"],
                            timing["calls"],
                            status,
                        ]
                    )
                for layer, count in run.get("disk_bytes", {}).items():
                    disks.append([source, run["label"], docs, layer, count])
                # Solo sync completo, exitoso, frío y con documentos nuevos entra al ajuste.
                if (
                    run["label"] == "sync"
                    and run.get("success")
                    and not item.get("preexisting_state")
                    and not item.get("preexisting_cache")
                    and not item.get("preexisting_layers")
                    and not item.get("from_stage")
                    and docs
                    and report.get("processed") == docs
                ):
                    key = (item["fake_embeddings"], item.get("chunker", "legacy"))
                    groups.setdefault(key, []).append(
                        {
                            "documents": docs,
                            "wall_seconds": resources["wall_seconds"],
                            "source": source,
                        }
                    )
        elif kind == "extract_parallel":
            for row in item["rows"]:
                extraction.append(
                    [
                        source,
                        row["workers"],
                        row.get("documents"),
                        row.get("successful_documents"),
                        row.get("wall_seconds"),
                        row.get("docs_per_hour"),
                        row.get("total_cpu_seconds"),
                        row.get("max_rss_bytes"),
                        "MEDIDA" if row["success"] else "FALLIDA",
                    ]
                )
        elif kind == "embed_throughput":
            embeddings.append(
                [
                    source,
                    item["embeddings"],
                    item["batch"],
                    item["num_thread"],
                    item["wall_seconds"],
                    item["embeddings_per_second"],
                    item["chars_per_second"],
                ]
            )
            measured_embedding_rates.append((source, item["embeddings_per_second"]))
        elif kind == "simhash_scaling":
            for row in item["rows"]:
                simhash.append(
                    [
                        source,
                        item.get("workload"),
                        row["size"],
                        row["fingerprint_seconds"],
                        row["detection_seconds"],
                        row["near_pairs"],
                        item.get("exponent"),
                        item.get("quadratic_observed"),
                    ]
                )
        elif kind == "chroma_query_latency":
            for row in item["rows"]:
                chroma.append(
                    [
                        source,
                        row["size"],
                        row["p50_ms"],
                        row["p95_ms"],
                        item.get("collection_deleted"),
                    ]
                )
        elif kind == "cost":
            costs.append(
                [
                    source,
                    item["docs_per_hour"],
                    item["price_per_hour"],
                    item["cost_per_1000_docs"],
                    item["price_source"],
                ]
            )
    lines += table(
        "Pipeline por escala",
        [
            "Fuente",
            "Operación",
            "Docs activos",
            "Procesados",
            "Embeddings",
            "Estado",
            "s total",
            "docs/h procesados",
            "chunks/s total",
            "emb/s API",
            "Hits",
            "Nuevos",
            "Hits/(hits+nuevos)",
            "Coalescidos",
            "CPU %",
            "CPU s",
            "RSS bytes",
        ],
        pipeline_rows,
    )
    lines += table(
        "Etapas", ["Fuente", "Operación", "Docs", "Etapa", "s", "Llamadas", "Estado"], stages
    )
    lines += table("Disco", ["Fuente", "Operación", "Docs", "Capa o almacén", "Bytes"], disks)
    lines += table(
        "Extracción y OCR",
        ["Fuente", "Workers", "Docs", "Correctos", "s", "docs/h", "CPU s", "RSS bytes", "Estado"],
        extraction,
    )
    lines += table(
        "Embeddings medidos",
        ["Fuente", "Embeddings", "Lote", "num_thread", "s", "emb/s", "caracteres/s"],
        embeddings,
    )
    lines += table(
        "SimHash",
        [
            "Fuente",
            "Distribución",
            "Textos",
            "s fingerprints",
            "s detección",
            "Pares",
            "Exponente",
            "Cuadrática observada",
        ],
        simhash,
    )
    lines += table(
        "Consultas Chroma",
        ["Fuente", "Vectores", "p50 ms", "p95 ms", "Colección eliminada"],
        chroma,
    )
    lines += table(
        "Costos en la moneda de la tarifa",
        ["Fuente", "docs/h", "Precio/h", "Costo/1000 docs", "Procedencia del precio"],
        costs,
    )
    projected, projected_embeddings = [], []
    for (fake, chunker), measurements in sorted(groups.items()):
        for count in extrapolate_sizes:
            try:
                row = extrapolate(measurements, count)
            except ValueError as exc:
                lines.extend([f"Proyección omitida ({chunker}, ficticios={fake}): {exc}.", ""])
                break
            projected.append(
                [
                    "**EXTRAPOLADA**",
                    count,
                    chunker,
                    fake,
                    row["wall_seconds"],
                    row["docs_per_hour"],
                    row["intercept_seconds"],
                    row["slope_seconds_per_doc"],
                    ", ".join(m["source"] for m in measurements),
                ]
            )
    if chunks_per_doc is not None:
        for source, speed in measured_embedding_rates:
            for count in extrapolate_sizes:
                chunks = math.ceil(count * chunks_per_doc)
                row = extrapolate_embeddings(chunks, speed)
                projected_embeddings.append(
                    ["**EXTRAPOLADA**", count, chunks, row["embedding_seconds"], speed, source]
                )
    lines += table(
        "Proyecciones lineales del pipeline",
        [
            "Estado",
            "Docs",
            "Chunker",
            "Embeddings ficticios",
            "s",
            "docs/h",
            "Intercepto s",
            "s/doc",
            "Fuentes medidas",
        ],
        projected,
    )
    lines += table(
        "Proyecciones de embeddings nuevos",
        ["Estado", "Docs", "Chunks supuestos", "s embeddings", "emb/s medidos", "Fuente"],
        projected_embeddings,
    )
    lines += [
        "## Interpretación",
        "",
        "Las proyecciones suponen hardware, cachés, distribución de tamaños y configuración comparables; no son mediciones. El ajuste lineal no modela saturación, créditos CPU ni crecimiento del costo de duplicados. No se mezclan embeddings ficticios y reales ni chunkers distintos.",
        "",
        "Una sal por página no garantiza chunks distintos después de OCR/limpieza. Revisar hits y textos coalescidos antes de extrapolar embeddings. Los CSV sintéticos conservan sus nombres originales y pueden perder coincidencias de metadatos.",
        "",
        "Las tasas del segundo sync reflejan reutilización de capas, validación, escaneo y hash, además de duplicados y calidad. Los segundos OCR están separados de extracción por los hooks existentes; no se debe volver a sumarlos dentro de extracción.",
        "",
    ]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--extrapolate-sizes", type=sizes, default=[])
    parser.add_argument("--chunks-per-doc", type=finite_positive)
    args = parser.parse_args(argv)
    if not args.results.is_dir():
        parser.error("--results debe ser un directorio existente")
    results = load_results(args.results)
    if not results:
        parser.error("No se encontraron resultados JSON del harness")
    # Este comando recibe un archivo explícito, en vez del directorio de los demás.
    out = output_dir(args.out.parent) / args.out.name
    if out.is_symlink():
        raise ValueError("El informe no admite enlaces")
    out.write_text(
        render_report(results, args.extrapolate_sizes, args.chunks_per_doc), encoding="utf-8"
    )
    print(
        json.dumps(
            {"benchmark": "report", "output": str(out), "sources": len(results)}, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()
