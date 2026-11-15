"""Comprueba el script de buckets sin credenciales ni llamadas a AWS."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

INGESTA = Path(__file__).resolve().parents[2]
BASH = shutil.which("bash")
pytestmark = pytest.mark.skipif(BASH is None, reason="Requiere Bash")

AWS_SIMULADO = r"""
aws() {
  printf '%s\t' "$@" >> "$REGISTRO"
  printf '\n' >> "$REGISTRO"
  case "$1:$2" in
    sts:get-caller-identity) echo "${CUENTA_PRUEBA:-679786170402}" ;;
    s3api:list-object-versions|s3api:delete-objects)
      "$PYTHON_PRUEBAS" -c 'import json, os, pathlib, sys
sys.stdout.reconfigure(newline="\n")
op = sys.argv[1]
args = sys.argv[2:]
def valor(opcion, defecto=None):
    return args[args.index(opcion) + 1] if opcion in args else defecto
ruta = pathlib.Path(os.environ["VERSIONES_PRUEBA"])
objetos = json.loads(ruta.read_text(encoding="utf-8"))
if op == "delete-objects":
    # Abrir exactamente la ruta recibida (como la AWS CLI nativa), sin reconstruirla.
    ruta_lote = pathlib.Path(valor("--delete").removeprefix("file://"))
    lote = json.loads(ruta_lote.read_text(encoding="utf-8"))["Objects"]
    assert 0 < len(lote) <= 1000
    assert all(set(o) == {"Key", "VersionId"} for o in lote)
    registro = pathlib.Path(os.environ["LOTES_PRUEBA"])
    lotes = json.loads(registro.read_text()) if registro.exists() else []
    registro.write_text(json.dumps([*lotes, lote]), encoding="utf-8")
    if os.environ["CASO"] == "error_borrado":
        print(1)
    else:
        pendientes = [o for o in objetos if {"Key": o["Key"], "VersionId": o["VersionId"]} not in lote]
        ruta.write_text(json.dumps(pendientes), encoding="utf-8")
        print(0)
else:
    assert "--no-paginate" in args
    limite = int(valor("--max-keys"))
    assert 0 < limite <= 1000
    marcador = (valor("--key-marker", ""), valor("--version-id-marker", ""))
    objetos = sorted((o for o in objetos if (o["Key"], o["VersionId"]) > marcador), key=lambda o: (o["Key"], o["VersionId"]))
    pagina = objetos[:limite]
    consulta = valor("--query")
    if consulta.startswith("[IsTruncated"):
        print("\t".join(map(str, [len(objetos) > limite, sum(o["Tipo"] == "Version" for o in pagina), sum(o["Tipo"] == "DeleteMarker" for o in pagina)])))
    elif consulta == "NextKeyMarker":
        print(pagina[-1]["Key"])
    elif consulta == "NextVersionIdMarker":
        print(pagina[-1]["VersionId"])
    elif consulta.startswith("{Objects:"):
        print(json.dumps({"Objects": [{"Key": o["Key"], "VersionId": o["VersionId"]} for o in pagina], "Quiet": True}))
    elif consulta == "length([Versions, DeleteMarkers][])":
        print(1 if os.environ["CASO"] == "restos" else len(pagina))
    else:
        raise AssertionError(consulta)
' "$2" "${@:3}" ;;
    s3api:head-bucket)
      if [[ "$CASO" == nuevo ]]; then echo '(404) Not Found' >&2; return 1; fi
      if [[ "$CASO" == inaccesible ]]; then echo '(403) Forbidden' >&2; return 1; fi ;;
    s3api:get-bucket-tagging)
      local a clave=""
      for a in "$@"; do [[ "$a" == "TagSet[?Key=="* ]] && clave="${a#*\'}" && clave="${clave%%\'*}"; done
      "$PYTHON_PRUEBAS" -c 'import json, os, sys
t = {x["Key"]: x["Value"] for x in json.loads(os.environ["ETIQUETAS_PRUEBA"])["TagSet"]}
print(t.get(sys.argv[1], "None"))' "$clave" ;;
    s3api:get-bucket-policy)
      if [[ "$CASO" == politica ]]; then echo '{"Policy":"ajena"}'; return 0; fi
      if [[ "$CASO" == politica_inaccesible ]]; then echo 'AccessDenied' >&2; return 1; fi
      echo 'NoSuchBucketPolicy' >&2; return 1 ;;
  esac
}
"""


def ejecutar_bucket(
    tmp_path,
    caso,
    bucket="atlas-demo-intake-prueba",
    etiquetas=None,
    *,
    script_nombre="crear_bucket.sh",
    argumentos=(),
    versiones=(),
    cuenta="679786170402",
):
    registro = tmp_path / "aws.log"
    estado_versiones = tmp_path / "versiones.json"
    estado_versiones.write_text(json.dumps(list(versiones)), encoding="utf-8")
    etiquetas = (
        etiquetas
        if etiquetas is not None
        else [
            {"Key": "Proyecto", "Value": "atlas-playas"},
            {"Key": "Uso", "Value": "intake-demo"},
            {"Key": "Conservar", "Value": "valor existente"},
        ]
    )
    entorno = {
        **os.environ,
        "CASO": caso,
        "REGISTRO": registro.as_posix(),
        "TMPDIR": tmp_path.as_posix(),
        "PYTHON_PRUEBAS": Path(sys.executable).as_posix(),
        "ETIQUETAS_PRUEBA": json.dumps({"TagSet": etiquetas}),
        "VERSIONES_PRUEBA": estado_versiones.as_posix(),
        "CUENTA_PRUEBA": cuenta,
        "LOTES_PRUEBA": (tmp_path / "lotes.json").as_posix(),
    }
    script = (INGESTA / "infrastructure/intake" / script_nombre).read_text(encoding="utf-8")
    resultado = subprocess.run(
        [BASH, "-s", "--", bucket, *argumentos],
        input=AWS_SIMULADO + script,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=entorno,
    )
    llamadas = (
        [linea.rstrip("\t").split("\t") for linea in registro.read_text().splitlines()]
        if registro.exists()
        else []
    )
    return resultado, llamadas


@pytest.mark.parametrize(
    "caso,bucket,etiquetas",
    [
        ("existente", "bucket-ajeno", None),
        ("existente", "atlas-demo-intake-prueba", []),
        (
            "existente",
            "atlas-demo-intake-prueba",
            [{"Key": "Proyecto", "Value": "otro"}, {"Key": "Uso", "Value": "intake-demo"}],
        ),
        ("politica", "atlas-demo-intake-prueba", None),
        ("politica_inaccesible", "atlas-demo-intake-prueba", None),
        ("inaccesible", "atlas-demo-intake-prueba", None),
    ],
)
def test_bucket_ajeno_o_sin_verificar_no_recibe_ningun_cambio(tmp_path, caso, bucket, etiquetas):
    resultado, llamadas = ejecutar_bucket(tmp_path, caso, bucket, etiquetas)
    assert resultado.returncode != 0
    assert not any(llamada[1].startswith(("put-", "create-", "delete-")) for llamada in llamadas)


@pytest.mark.parametrize("caso", ["existente", "nuevo"])
def test_bucket_configura_versionado_y_expiracion_y_conserva_etiquetas(tmp_path, caso):
    resultado, llamadas = ejecutar_bucket(tmp_path, caso)
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    operaciones = [llamada[1] for llamada in llamadas]
    if caso == "existente":
        assert operaciones.index("get-bucket-policy") < operaciones.index("put-public-access-block")
    else:
        assert operaciones.index("create-bucket") < operaciones.index("put-public-access-block")
    etiquetado = [llamada for llamada in llamadas if llamada[1] == "put-bucket-tagging"]
    if caso == "existente":
        # Un bucket existente ya verificado conserva sus etiquetas: no se reescriben.
        assert not etiquetado
    else:
        (tagging,) = etiquetado
        valor = tagging[tagging.index("--tagging") + 1]
        assert "{Key=Proyecto,Value=atlas-playas}" in valor
        assert "{Key=Uso,Value=intake-demo}" in valor
    versionado = next(llamada for llamada in llamadas if llamada[1] == "put-bucket-versioning")
    assert versionado[-1] == "Status=Enabled"
    ciclo = next(
        llamada for llamada in llamadas if llamada[1] == "put-bucket-lifecycle-configuration"
    )
    reglas = json.loads(ciclo[-1])["Rules"]
    assert reglas[0]["Status"] == "Enabled"
    assert reglas[0]["NoncurrentVersionExpiration"]["NoncurrentDays"] == 7


@pytest.mark.parametrize("cantidad", [0, 2003])
def test_destruir_bucket_borra_versiones_y_marcadores_paginados(tmp_path, cantidad):
    versiones = [
        {
            "Key": f'carpeta/objeto "con espacios" {i // 3:04}.pdf',
            "VersionId": f"v{i:04}",
            "Tipo": "DeleteMarker" if i % 3 == 0 else "Version",
        }
        for i in range(cantidad)
    ]
    resultado, llamadas = ejecutar_bucket(
        tmp_path,
        "versionado",
        script_nombre="destruir_bucket.sh",
        argumentos=("--confirmo-borrado",),
        versiones=versiones,
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    borrados = [c for c in llamadas if c[1] == "delete-objects"]
    lotes = json.loads((tmp_path / "lotes.json").read_text()) if cantidad else []
    assert len(borrados) == len(lotes)
    assert [len(lote) for lote in lotes] == ([1000, 1000, 3] if cantidad else [])
    assert [o for lote in lotes for o in lote] == [
        {"Key": o["Key"], "VersionId": o["VersionId"]} for o in versiones
    ]
    if cantidad:
        paginas = [c for c in llamadas if "--key-marker" in c]
        assert {c[c.index("--version-id-marker") + 1] for c in paginas} == {"v0999", "v1999"}
    assert llamadas[-2][1] == "list-object-versions"
    assert llamadas[-2][llamadas[-2].index("--max-keys") + 1] == "1"
    assert llamadas[-1][1] == "delete-bucket"
    assert json.loads((tmp_path / "versiones.json").read_text()) == []
    assert not any(c[:2] == ["s3", "rm"] for c in llamadas)


@pytest.mark.parametrize("caso", ["error_borrado", "restos"])
def test_destruir_bucket_no_borra_bucket_si_no_queda_vacio(tmp_path, caso):
    resultado, llamadas = ejecutar_bucket(
        tmp_path,
        caso,
        script_nombre="destruir_bucket.sh",
        argumentos=("--confirmo-borrado",),
        versiones=[{"Key": "archivo.pdf", "VersionId": "v1", "Tipo": "Version"}],
    )
    assert resultado.returncode != 0
    assert not any(c[1] == "delete-bucket" for c in llamadas)


@pytest.mark.parametrize(
    "argumentos,bucket,cuenta",
    [
        ((), "atlas-demo-intake-prueba", "679786170402"),
        (("--confirmo-borrado",), "bucket-ajeno", "679786170402"),
        (("--confirmo-borrado",), "atlas-demo-intake-prueba", "000000000000"),
    ],
)
def test_destruir_bucket_exige_confirmacion_prefijo_y_cuenta(tmp_path, argumentos, bucket, cuenta):
    resultado, llamadas = ejecutar_bucket(
        tmp_path,
        "versionado",
        bucket,
        script_nombre="destruir_bucket.sh",
        argumentos=argumentos,
        cuenta=cuenta,
    )
    assert resultado.returncode != 0
    assert all(c[0] == "sts" for c in llamadas)


@pytest.mark.parametrize("operacion", ["base", "reset"])
def test_operacion_toma_bloqueo_antes_de_parar_y_rearranca_aunque_falle(tmp_path, operacion):
    raiz = tmp_path / "repo"
    datos = tmp_path / "datos"
    (raiz / "ingesta").mkdir(parents=True)
    (datos / "locks").mkdir(parents=True)
    registro = tmp_path / "operacion.log"
    if operacion == "base":
        script = (INGESTA / "demo/worker/construir_base.sh").read_text(encoding="utf-8")
    else:
        operador = (INGESTA / "demo/reset_demo.sh").read_text(encoding="utf-8")
        script = operador.split("<<'EOF'\n", 1)[1].split("\nEOF", 1)[0]

    def ruta_bash(ruta):
        return (
            "/" + ruta.drive[0].lower() + ruta.as_posix()[2:]
            if os.name == "nt"
            else ruta.as_posix()
        )

    script = script.replace('"$RAIZ/ingesta/.venv/bin/python"', "python_simulado")
    script = script.replace("/opt/atlas/playas", ruta_bash(raiz)).replace(
        "/var/lib/atlas", ruta_bash(datos)
    )
    simulacion = r"""
source() { return 0; }
mkdir() { return 0; }
cd() { return 0; }
flock() { printf 'bloqueo %s\n' "$*" >> "$REGISTRO"; }
systemctl() { printf '%s\n' "$1" >> "$REGISTRO"; }
sudo() { printf 'operacion\n' >> "$REGISTRO"; return 37; }
chown() { return 0; }
rm() { return 0; }
python_simulado() { return 0; }
"""
    resultado = subprocess.run(
        [BASH, "-s", "--", "--frio"],
        input=simulacion + script,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={
            **os.environ,
            "REGISTRO": registro.as_posix(),
            "ATLAS_COLECCION": "atlas_demo_base",
            "ATLAS_OLLAMA": "http://localhost:11434",
        },
    )
    assert resultado.returncode == 37, resultado.stdout + resultado.stderr
    assert registro.read_text().splitlines() == ["bloqueo -x 9", "stop", "operacion", "start"]
    assert (datos / "locks/operacion.lock").exists()
    assert not (datos / "base_hashes.txt").exists()
