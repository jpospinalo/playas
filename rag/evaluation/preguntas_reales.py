"""Corre el set de preguntas de gente real contra la API local de ATLAS.

Uso, desde ``rag/`` con la API y el modelo ya levantados:

    uv run python -m evaluation.preguntas_reales \
        --token-file ~/.local/share/atlas-demo/.token --tag local-gemma4

    # Repetir dos veces solo los casos dudosos (para medir varianza):
    uv run python -m evaluation.preguntas_reales \
        --token-file ~/.local/share/atlas-demo/.token \
        --repetir PR-23 PR-25 --repeticiones 2 --tag varianza

El set vive versionado en ``evaluation/data/preguntas-reales-v1.json``. Este
módulo solo lo ejecuta y guarda la transcripción; no juzga. El juicio se hace
después con los criterios de cada ítem (ver el informe de la corrida).

No forma parte de la ruta de servicio: no lo importa ``api/`` ni ``core/``.
Los resultados van a ``evaluation/results/`` (ignorado por git).
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DATASET = Path(__file__).resolve().parent / "data" / "preguntas-reales-v1.json"
RESULTS = Path(__file__).resolve().parent / "results"

_CITA_RE = re.compile(r"\[doc(\d+)\]")
_ETIQUETA_RE = re.compile(r"[a-z0-9][a-z0-9.-]*")


@dataclass
class Turno:
    """Un turno enviado y su respuesta."""

    pregunta: str
    esperado: str
    latencia_s: float
    http_status: int
    respuesta: str = ""
    ruta: str | None = None
    consulta_enriquecida: str | None = None
    fuentes: list[dict[str, Any]] = field(default_factory=list)
    citas: list[int] = field(default_factory=list)
    citas_invalidas: list[int] = field(default_factory=list)
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "pregunta": self.pregunta,
            "esperado": self.esperado,
            "latencia_s": round(self.latencia_s, 2),
            "http_status": self.http_status,
            "ruta": self.ruta,
            "consulta_enriquecida": self.consulta_enriquecida,
            "respuesta": self.respuesta,
            "fuentes": [
                {
                    "title": f.get("title"),
                    "doc_type": f.get("doc_type"),
                    "source": f.get("source"),
                }
                for f in self.fuentes
            ],
            "citas": self.citas,
            "citas_invalidas": self.citas_invalidas,
            "error": self.error,
        }


@dataclass
class Caso:
    """Un ítem del set: una pregunta simple o una conversación."""

    id: str
    categoria: str
    persona: str
    esperado: str
    turnos: list[Turno]

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "categoria": self.categoria,
            "persona": self.persona,
            "esperado": self.esperado,
            "turnos": [t.as_dict() for t in self.turnos],
            "latencia_total_s": round(sum(t.latencia_s for t in self.turnos), 2),
        }


def cargar_set(path: Path = DATASET) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items") or []
    ids = [i["id"] for i in items]
    if len(ids) != len(set(ids)):
        raise ValueError("Hay ids repetidos en el set")
    for item in items:
        if item["categoria"] not in data["categorias"]:
            raise ValueError(f"{item['id']}: categoría desconocida {item['categoria']!r}")
        if item["categoria"] == "conversacion" and not item.get("turnos"):
            raise ValueError(f"{item['id']}: conversación sin turnos")
        if item["categoria"] != "conversacion" and not item.get("pregunta"):
            raise ValueError(f"{item['id']}: falta la pregunta")
    return data


def _post(api: str, token: str, pregunta: str, thread_id: str, timeout: float) -> tuple[int, dict]:
    body = json.dumps({"question": pregunta, "thread_id": thread_id}).encode()
    req = urllib.request.Request(
        f"{api.rstrip('/')}/api/query",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:  # la API respondió con error
        crudo = exc.read().decode(errors="replace")[:500]
        try:
            detalle = json.loads(crudo)
        except json.JSONDecodeError:
            detalle = {"detail": crudo}
        return exc.code, detalle


def correr_turno(
    api: str, token: str, pregunta: str, esperado: str, thread_id: str, timeout: float
) -> Turno:
    t0 = time.perf_counter()
    try:
        status, data = _post(api, token, pregunta, thread_id, timeout)
        latencia = time.perf_counter() - t0
    except Exception as exc:  # red, timeout o JSON roto: se registra tal cual
        return Turno(
            pregunta=pregunta,
            esperado=esperado,
            latencia_s=time.perf_counter() - t0,
            http_status=0,
            error=f"{type(exc).__name__}: {exc}"[:300],
        )
    fuentes = data.get("sources") or []
    respuesta = data.get("answer") or ""
    citas = sorted({int(n) for n in _CITA_RE.findall(respuesta)})
    return Turno(
        pregunta=pregunta,
        esperado=esperado,
        latencia_s=latencia,
        http_status=status,
        respuesta=respuesta,
        ruta=data.get("query_route"),
        consulta_enriquecida=data.get("enriched_query"),
        fuentes=fuentes,
        citas=citas,
        citas_invalidas=[n for n in citas if n < 1 or n > len(fuentes)],
        error=None if status == 200 else str(data.get("detail") or data)[:300],
    )


def correr_caso(api: str, token: str, item: dict, timeout: float) -> Caso:
    thread_id = f"pr-{item['id'].lower()}-{uuid.uuid4().hex[:8]}"
    if item["categoria"] == "conversacion":
        turnos = [
            correr_turno(api, token, t["pregunta"], t["esperado"], thread_id, timeout)
            for t in item["turnos"]
        ]
        esperado = item["turnos"][0]["esperado"]
    else:
        turnos = [correr_turno(api, token, item["pregunta"], item["esperado"], thread_id, timeout)]
        esperado = item["esperado"]
    return Caso(
        id=item["id"],
        categoria=item["categoria"],
        persona=item["persona"],
        esperado=esperado,
        turnos=turnos,
    )


def _resumen_md(corrida: dict[str, Any]) -> str:
    casos: list[dict] = corrida["casos"]
    lineas = [
        "# Preguntas de gente real — transcripción de la corrida",
        "",
        f"- Fecha: {corrida['fecha']}",
        f"- Etiqueta: `{corrida['etiqueta']}`",
        f"- API: `{corrida['api']}`",
        f"- Casos: {len(casos)} · turnos: {sum(len(c['turnos']) for c in casos)}",
        "",
        "| Caso | Categoría | Persona | Turnos | Ruta(s) | Latencia (s) | Citas inválidas |",
        "|---|---|---|---:|---|---:|---:|",
    ]
    for c in casos:
        rutas = " → ".join(str(t["ruta"]) for t in c["turnos"])
        invalidas = sum(len(t["citas_invalidas"]) for t in c["turnos"])
        lineas.append(
            f"| {c['id']} | {c['categoria']} | {c['persona']} | {len(c['turnos'])} "
            f"| {rutas} | {c['latencia_total_s']:.1f} | {invalidas} |"
        )
    lineas += ["", "## Transcripción", ""]
    for c in casos:
        lineas.append(f"### {c['id']} — {c['categoria']} ({c['persona']})")
        lineas.append("")
        for i, t in enumerate(c["turnos"], 1):
            lineas.append(f"**Usuario (turno {i}):** {t['pregunta']}")
            lineas.append("")
            lineas.append(
                f"_ruta: {t['ruta']} · {t['latencia_s']:.1f} s · "
                f"fuentes: {len(t['fuentes'])} · esperado: {t['esperado']}_"
            )
            lineas.append("")
            lineas.append("**ATLAS:**")
            lineas.append("")
            lineas.append(t["respuesta"] or f"_(sin respuesta: {t['error']})_")
            lineas.append("")
        lineas.append("---")
        lineas.append("")
    return "\n".join(lineas)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--api", default="http://localhost:8080")
    ap.add_argument(
        "--token-file", required=True, help="Archivo con el JWT de una cuenta de prueba"
    )
    ap.add_argument("--set", type=Path, default=DATASET, help="Ruta del set JSON")
    ap.add_argument(
        "--tag", default="local", help="Etiqueta de la corrida (minúsculas, punto y guion)"
    )
    ap.add_argument("--solo", nargs="*", help="Ids concretos (por defecto, todos)")
    ap.add_argument("--repetir", nargs="*", help="Ids que se repiten además de la corrida completa")
    ap.add_argument("--repeticiones", type=int, default=1, help="Veces extra para --repetir")
    ap.add_argument("--timeout", type=float, default=400.0)
    args = ap.parse_args()

    if not _ETIQUETA_RE.fullmatch(args.tag):
        raise SystemExit(f"Etiqueta inválida: {args.tag!r}")

    data = cargar_set(args.set)
    token = Path(args.token_file).expanduser().read_text(encoding="utf-8").strip()
    if not token:
        raise SystemExit("El archivo de token está vacío")

    items = data["items"]
    if args.solo:
        pedidos = set(args.solo)
        items = [i for i in items if i["id"] in pedidos]
        faltan = pedidos - {i["id"] for i in items}
        if faltan:
            raise SystemExit(f"Ids inexistentes: {sorted(faltan)}")

    casos: list[Caso] = []
    for item in items:
        caso = correr_caso(args.api, token, item, args.timeout)
        casos.append(caso)
        for i, t in enumerate(caso.turnos, 1):
            print(
                f"{caso.id}.T{i} {str(t.ruta):19} {t.latencia_s:5.1f}s "
                f"fuentes={len(t.fuentes):2} citas={t.citas} | {t.pregunta[:48]}",
                flush=True,
            )

    corrida = {
        "fecha": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "etiqueta": args.tag,
        "api": args.api,
        "set": str(args.set),
        "version_set": data.get("version"),
        "casos": [c.as_dict() for c in casos],
    }

    repetidos: list[Caso] = []
    if args.repetir:
        if args.repeticiones < 1:
            raise SystemExit("--repeticiones debe ser >= 1")
        por_id = {i["id"]: i for i in data["items"]}
        faltan = set(args.repetir) - set(por_id)
        if faltan:
            raise SystemExit(f"Ids inexistentes: {sorted(faltan)}")
        for vuelta in range(1, args.repeticiones + 1):
            for pid in args.repetir:
                caso = correr_caso(args.api, token, por_id[pid], args.timeout)
                repetidos.append(caso)
                for i, t in enumerate(caso.turnos, 1):
                    print(
                        f"REP{vuelta} {caso.id}.T{i} {str(t.ruta):19} {t.latencia_s:5.1f}s "
                        f"fuentes={len(t.fuentes):2} | {t.pregunta[:44]}",
                        flush=True,
                    )
        corrida["repeticiones"] = [c.as_dict() for c in repetidos]

    RESULTS.mkdir(parents=True, exist_ok=True)
    destino = RESULTS / f"preguntas-reales-{args.tag}.json"
    destino.write_text(json.dumps(corrida, ensure_ascii=False, indent=2), encoding="utf-8")
    (RESULTS / f"preguntas-reales-{args.tag}.md").write_text(_resumen_md(corrida), encoding="utf-8")

    # Resumen de consola: latencias y rutas, sin juzgar.
    latencias = [t["latencia_s"] for c in corrida["casos"] for t in c["turnos"]]
    rutas = Counter(t["ruta"] for c in corrida["casos"] for t in c["turnos"])
    por_categoria: dict[str, list[float]] = defaultdict(list)
    for c in corrida["casos"]:
        por_categoria[c["categoria"]].extend(t["latencia_s"] for t in c["turnos"])
    print("\nRutas:", dict(rutas))
    print(
        f"Latencia: media {sum(latencias) / len(latencias):.1f}s · "
        f"mín {min(latencias):.1f}s · máx {max(latencias):.1f}s"
    )
    for categoria, vals in sorted(por_categoria.items()):
        print(f"  {categoria:16} n={len(vals):2} media={sum(vals) / len(vals):5.1f}s")
    if repetidos:
        print(f"Repeticiones extra: {len(repetidos)} casos")
    print(f"Guardado en {destino}")


if __name__ == "__main__":
    main()
