"""Selección y registro verificable de los documentos solicitados para la base."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from ingest.offline.storage import atomic_bytes


def preparar_base(raiz, buzon, sufijos):
    mapa = json.loads(
        (raiz / "ingesta/benchmarks/demo_aws/sufijos_raw.json").read_text(encoding="utf-8")
    )
    solicitados = set(sufijos)
    if not solicitados:
        raise ValueError("Indica los sufijos de los documentos de la base")
    encontrados = {}
    for ruta in sorted((raiz / "data/documents/raw").rglob("*.pdf")):
        huella = hashlib.sha256(ruta.read_bytes()).hexdigest()
        if mapa.get(huella) in solicitados:
            encontrados[huella] = ruta
    faltan = solicitados - {mapa[h] for h in encontrados}
    if faltan:
        raise ValueError(f"Faltan documentos solicitados: {sorted(faltan)}")
    buzon.mkdir(parents=True, exist_ok=True)
    usados = set()
    for huella, ruta in encontrados.items():
        # El nombre del archivo da el title de los chunks: conservar el original y
        # desambiguar solo si dos categorías traen el mismo nombre.
        nombre = ruta.name if ruta.name not in usados else f"{ruta.stem} ({huella[:8]}).pdf"
        usados.add(nombre)
        shutil.copy2(ruta, buzon / nombre)
        (buzon / f"{nombre}.meta.json").write_text(
            json.dumps({"categoria": ruta.parent.name}), encoding="utf-8"
        )
    return sorted(encontrados)


def registrar_base(estado, solicitados, destino):
    hashes = sorted(set(solicitados))
    if not hashes:
        raise ValueError("La base solicitada está vacía")
    for huella in hashes:
        ruta = Path(estado) / "intake" / f"{huella}.json"
        if not ruta.exists():
            raise ValueError(f"Falta la ficha del documento solicitado {huella}")
        ficha = json.loads(ruta.read_text(encoding="utf-8"))
        if ficha.get("estado") not in {"publicado", "revision_humana", "rechazado"}:
            raise ValueError(f"Documento solicitado sin resolver: {huella}")
    atomic_bytes(destino, ("\n".join(hashes) + "\n").encode("utf-8"))
