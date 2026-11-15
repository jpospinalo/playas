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
    sts:get-caller-identity) echo 679786170402 ;;
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


def ejecutar_bucket(tmp_path, caso, bucket="atlas-demo-intake-prueba", etiquetas=None):
    registro = tmp_path / "aws.log"
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
    }
    script = (INGESTA / "infrastructure/intake/crear_bucket.sh").read_text(encoding="utf-8")
    resultado = subprocess.run(
        [BASH, "-s", "--", bucket],
        input=AWS_SIMULADO + script,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=entorno,
    )
    llamadas = [linea.rstrip("\t").split("\t") for linea in registro.read_text().splitlines()]
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
