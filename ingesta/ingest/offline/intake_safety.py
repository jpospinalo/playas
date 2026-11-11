"""Destinos, identidad y clasificación determinista de entradas no confiables."""

from __future__ import annotations

import hashlib
import ipaddress
import os
import re
import tempfile
from collections import Counter
from pathlib import Path

from .extract import sha256_file
from .layers import key

DESTINOS = Path(__file__).resolve().parents[2] / "config" / "intake_destinos.yaml"
PROTEGIDAS = {"v1", "atlas_v1", "rag_playas", "rag_playas_magdalena"}


class ConfiguracionInvalida(ValueError):
    """La configuración no autoriza este destino o estos límites."""


def loopback(host):
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def cargar_destinos(ruta=None):
    import yaml

    datos = yaml.safe_load(Path(ruta or DESTINOS).read_text(encoding="utf-8"))
    if not isinstance(datos, dict):
        raise ConfiguracionInvalida("Configuración de destinos inválida")
    for campo in (
        "colecciones_protegidas",
        "prefijos_permitidos",
        "hosts_chroma_permitidos",
        "hosts_protegidos",
    ):
        valores = datos.get(campo)
        if not isinstance(valores, list) or any(not isinstance(v, str) or not v for v in valores):
            raise ConfiguracionInvalida(f"Lista inválida: {campo}")
    prefijos = datos["prefijos_permitidos"]
    if not prefijos or any(not p.startswith(("atlas_intake_", "bench_intake_")) for p in prefijos):
        raise ConfiguracionInvalida("Prefijos permitidos fuera del espacio de intake")
    if not datos["hosts_chroma_permitidos"] or not all(
        loopback(h) for h in datos["hosts_chroma_permitidos"]
    ):
        raise ConfiguracionInvalida("Chroma solo permite hosts loopback")
    for campo in (
        "tamano_maximo_bytes",
        "paginas_maximas",
        "tiempo_maximo_documento_segundos",
        "memoria_maxima_mb",
        "simhash_palabras_shingle",
    ):
        valor = datos.get(campo)
        if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
            raise ConfiguracionInvalida(f"Límite entero positivo requerido: {campo}")
    umbral = datos.get("simhash_umbral")
    if isinstance(umbral, bool) or not isinstance(umbral, int) or not 0 <= umbral <= 64:
        raise ConfiguracionInvalida("simhash_umbral debe estar entre 0 y 64")
    gancho = datos.get("gancho_notificacion")
    if gancho is not None and (not isinstance(gancho, str) or not gancho):
        raise ConfiguracionInvalida("gancho_notificacion debe ser una ruta de archivo")
    return datos


def validar_destino(coleccion, host, destinos, *, ficticios=False, port=8000):
    if not isinstance(coleccion, str) or not re.fullmatch(
        r"[a-zA-Z0-9_][a-zA-Z0-9_-]{1,490}", coleccion
    ):
        raise ConfiguracionInvalida("Nombre de colección inválido")
    for nombre in (coleccion, coleccion + "__staging"):
        if nombre in PROTEGIDAS | set(destinos["colecciones_protegidas"]) or not nombre.startswith(
            tuple(destinos["prefijos_permitidos"])
        ):
            raise ConfiguracionInvalida(f"Destino protegido: colección {nombre}")
    if (
        not loopback(host)
        or host not in destinos["hosts_chroma_permitidos"]
        or host in destinos["hosts_protegidos"]
        # El publicador usa siempre 127.0.0.1, incluidos los alias loopback.
        or "127.0.0.1" in destinos["hosts_protegidos"]
        or "127.0.0.1" not in destinos["hosts_chroma_permitidos"]
    ):
        raise ConfiguracionInvalida(
            f"Destino protegido: host Chroma {host}; solo loopback autorizado"
        )
    if ficticios and not coleccion.startswith("bench_"):
        raise ConfiguracionInvalida("--fake-embeddings requiere una colección bench_")
    if not 1 <= port <= 65535:
        raise ConfiguracionInvalida("Puerto Chroma inválido")


def nombre_seguro(doc_id):
    """El nombre recibido nunca participa en una ruta de salida."""
    if not re.fullmatch(r"[0-9a-f]{64}", doc_id):
        raise ValueError("Identidad SHA-256 inválida")
    return doc_id + ".pdf"


def validar_raw(raiz, inbox):
    """Valida la excepción de escritura en raw sin crear ni copiar archivos."""
    raiz, inbox = Path(raiz).resolve(), Path(inbox).resolve()
    if raiz.is_relative_to(inbox) or inbox.is_relative_to(raiz):
        raise ValueError("raw-root e inbox deben ser independientes")
    partes = [p.casefold() for p in raiz.parts]
    if partes[-2:] == ["data", "documents"]:
        raise ValueError("raw-root no puede ser la raíz de capas v1")
    if any(
        partes[i : i + 3]
        in (
            ["data", "documents", "bronze"],
            ["data", "documents", "silver"],
            ["data", "documents", "gold"],
        )
        for i in range(len(partes) - 2)
    ):
        raise ValueError("raw-root no puede apuntar a capas v1")
    if len(str(raiz / nombre_seguro("0" * 64))) >= 240:
        raise ValueError("Ruta raw demasiado larga (máximo 239 caracteres)")
    return raiz


def copiar_raw(origen, raiz, doc_id, inbox):
    """Excepción acotada al raw autorizado: copia inmutable con nombre SHA-256.

    No relaja guard_output para ningún otro escritor ni permite tocar capas v1.
    """
    raiz = validar_raw(raiz, inbox)
    destino = raiz / nombre_seguro(doc_id)
    if len(str(destino)) >= 240 or destino.is_symlink():
        raise ValueError("Ruta raw insegura o demasiado larga (máximo 239 caracteres)")
    if sha256_file(origen) != doc_id:
        raise ValueError("La entrada cambió durante el procesamiento")
    if destino.exists():
        if sha256_file(destino) != doc_id:
            raise ValueError("La copia raw existente no coincide con su identidad")
        return destino
    raiz.mkdir(parents=True, exist_ok=True)
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=raiz, prefix="intake-", suffix=".tmp", delete=False
        ) as salida:
            temporal = Path(salida.name)
            with Path(origen).open("rb") as entrada:
                for bloque in iter(lambda: entrada.read(1024 * 1024), b""):
                    salida.write(bloque)
            salida.flush()
            os.fsync(salida.fileno())
        if sha256_file(temporal) != doc_id:
            raise ValueError("La entrada cambi? durante la copia")
        os.replace(temporal, destino)
    finally:
        if temporal is not None:
            temporal.unlink(missing_ok=True)
    return destino


def clasificar(documento, manual=None):
    if manual:
        if manual not in {"normativa", "jurisprudencia"}:
            raise ValueError("Categoría manual inválida")
        return {"categoria": manual, "confianza": 1.0, "origen": "correccion_manual"}
    encabezado = key("\n".join(documento["raw_pages"][:2])[:12000])
    judicial = bool(
        re.search(
            r"consejo de estado|corte (?:constitucional|suprema)|tribunal (?:administrativo|superior)",
            encabezado,
        )
    )
    norma = bool(
        re.search(
            r"(?m)^\s*(?:ley|decreto|resolucion|acuerdo|ordenanza)\s+(?:numero\s+|no\.?\s*)?\d+",
            encabezado,
        )
    )
    norma = norma and bool(re.search(r"\b(?:decreta|resuelve|acuerda|articulo)\b", encabezado))
    clara = judicial != norma
    return {
        "categoria": "normativa" if norma and not judicial else "jurisprudencia",
        "confianza": 0.95 if clara else 0.0,
        "origen": "reglas_encabezado",
    }


def simhash_shingles(texto, palabras=3):
    tokens = re.findall(r"\w+", key(texto))
    shingles = [
        " ".join(tokens[i : i + palabras]) for i in range(max(1, len(tokens) - palabras + 1))
    ]
    pesos = [0] * 64
    for shingle, cuenta in Counter(shingles).items():
        valor = int.from_bytes(hashlib.blake2b(shingle.encode(), digest_size=8).digest(), "big")
        for bit in range(64):
            pesos[bit] += cuenta if valor & (1 << bit) else -cuenta
    return sum(1 << bit for bit, peso in enumerate(pesos) if peso > 0)
