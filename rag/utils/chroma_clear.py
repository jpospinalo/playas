"""Script para eliminar todos los documentos de una colección de Chroma.

Simulación (dry-run) por defecto: muestra host, colección y cantidad de
documentos sin eliminar nada. Requiere ``--collection`` explícito (sin
default) y la bandera ``--execute`` para intentar el borrado; aun con
``--execute`` exige escribir el nombre EXACTO de la colección como
confirmación. Se cancela si la confirmación no coincide o si la ejecución no
es interactiva (sin terminal disponible para confirmar con seguridad).

T2.4: host/puerto vienen de ``rag.config`` (resolución centralizada de
``.env``, T2.3) en vez de un ``load_dotenv()`` propio. ``--collection``
sigue sin tener default propio ni tomar ``CHROMA_COLLECTION`` del entorno:
un borrado siempre exige que quien lo ejecuta escriba el nombre exacto de la
colección de forma explícita, nunca uno resuelto implícitamente.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from typing import Any

import chromadb

from rag.config import CHROMA_HOST, CHROMA_PORT


def describe_collection(client: Any, collection_name: str) -> int:
    """Cantidad de documentos en ``collection_name``.

    Usa ``get_collection()`` — igual que ``chroma_count.py`` — así que nunca
    crea la colección solo para poder describirla.
    """
    collection = client.get_collection(name=collection_name)
    return int(collection.count())


def confirm(
    collection_name: str,
    *,
    interactive: bool,
    read_input: Callable[[str], str] = input,
) -> bool:
    """Confirmación exacta: escribir el nombre completo de la colección.

    Se cancela (devuelve ``False``) sin pedir nada si la ejecución no es
    interactiva — no hay forma de autorizar el borrado con seguridad sin una
    terminal — o si lo escrito no coincide carácter a carácter.
    """
    if not interactive:
        print(
            "Ejecución no interactiva: no es posible confirmar el borrado con "
            "seguridad. Operación cancelada."
        )
        return False

    respuesta = read_input(
        f"\nEsto eliminará TODOS los documentos de '{collection_name}'. "
        "Escribe el nombre exacto de la colección para confirmar: "
    ).strip()
    if respuesta != collection_name:
        print("La confirmación no coincide con el nombre de la colección. Operación cancelada.")
        return False
    return True


def clear_collection(client: Any, collection_name: str) -> None:
    """Elimina y recrea vacía ``collection_name``.

    Solo debe invocarse después de una confirmación exacta — ver ``confirm()``.
    """
    client.delete_collection(collection_name)
    client.create_collection(collection_name)


def run(
    client: Any,
    collection_name: str,
    *,
    execute: bool,
    interactive: bool,
    read_input: Callable[[str], str] = input,
) -> int:
    try:
        count = describe_collection(client, collection_name)
    except Exception as exc:
        print(
            f"No fue posible leer la colección '{collection_name}' en {CHROMA_HOST}:{CHROMA_PORT}: {exc}"
        )
        return 1

    print(f"Host: {CHROMA_HOST}:{CHROMA_PORT}")
    print(f"Colección: '{collection_name}'")
    print(f"Documentos actuales: {count}")

    if count == 0:
        print("La colección ya está vacía. No hay nada que eliminar.")
        return 0

    if not execute:
        print("\nSimulación: no se eliminó nada. Pasa --execute para ejecutar el borrado.")
        return 0

    if not confirm(collection_name, interactive=interactive, read_input=read_input):
        return 1

    clear_collection(client, collection_name)
    print(f"Colección '{collection_name}' vaciada. Documentos eliminados: {count}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--collection",
        required=True,
        help="Nombre EXACTO de la colección destino. Sin valor por defecto: debe indicarse.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Ejecuta el borrado. Sin esta bandera el script solo simula (dry-run, por defecto).",
    )
    args = parser.parse_args()

    client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    return run(
        client,
        args.collection,
        execute=args.execute,
        interactive=sys.stdin.isatty(),
    )


if __name__ == "__main__":
    sys.exit(main())
