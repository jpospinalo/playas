#!/usr/bin/env bash
# Integra la próxima actualización de `corpus` en la rama de trabajo actual y
# reporta qué cambió: pruebas de rag, frontend e ingesta, y métricas sin LLM
# antes y después de la fusión (0 tokens).
#
# Uso (desde cualquier carpeta del repo, en la rama de integración):
#   scripts/integrar_corpus.sh                  # fetch + merge de origin/corpus + todo
#   scripts/integrar_corpus.sh --solo-verificar # sin fetch ni merge: pruebas y métricas
#   scripts/integrar_corpus.sh --sin-metricas   # sin ChromaDB/Ollama
#   ORIGEN=origin/otra-rama scripts/integrar_corpus.sh   # una rama local no se descarga
#
# Métricas: necesitan ChromaDB con la colección Gold y Ollama de embeddings.
# Se toman CHROMA_HOST, CHROMA_PORT, CHROMA_COLLECTION y OLLAMA_BASE_URL del
# entorno; si falta CHROMA_COLLECTION se usa la colección publicada en
# scripts/corpus_release.sh. La caché de generación (para las métricas de la
# ruta de producción y de respuesta) es CACHE_METRICAS o, si no se da, la más
# reciente de rag/evaluation/results/. Si ChromaDB no responde, se omiten.
#
# No hace push, no toca `main` ni `corpus`, no usa AWS ni LLM. Antes de fusionar
# guarda la rama actual en respaldo-local/integracion-antes-corpus-<fecha>.
# Si la fusión tiene conflictos se detiene y los lista (git merge --abort para
# deshacerla). Sale con 1 si alguna verificación falla.
set -uo pipefail

ORIGEN="${ORIGEN:-origin/corpus}"
FUSIONAR=1
METRICAS=1
for arg in "$@"; do
  case "$arg" in
    --solo-verificar) FUSIONAR=0 ;;
    --sin-metricas) METRICAS=0 ;;
    -h | --help) awk 'NR > 1 && !/^#/ { exit } NR > 1 { sub(/^# ?/, ""); print }' "$0"; exit 0 ;;
    *) echo "Opción desconocida: $arg" >&2; exit 2 ;;
  esac
done

REPO="$(git rev-parse --show-toplevel)" || exit 2
cd "$REPO" || exit 2
RAMA="$(git branch --show-current)"
case "$RAMA" in
  main | corpus | "") echo "Rama '$RAMA': cámbiate a la rama de integración." >&2; exit 2 ;;
esac
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Hay cambios sin commit; guárdalos antes de integrar." >&2
  exit 2
fi

ANTES="$(git rev-parse --short HEAD)"
FECHA="$(date +%F)"
LOGS="$REPO/rag/evaluation/results/integracion-$FECHA-$ANTES"
mkdir -p "$LOGS"
declare -a RESUMEN=()
FALLOS=0

paso() { # paso <nombre> <carpeta> <comando...>: corre, guarda log y anota el resultado
  local nombre="$1" dir="$2"
  shift 2
  local log="$LOGS/${nombre// /_}.log"
  printf '%-28s' "$nombre"
  if (cd "$REPO/$dir" && "$@") >"$log" 2>&1; then
    local estado="OK"
  else
    local estado="FALLO"
    FALLOS=$((FALLOS + 1))
  fi
  # Última línea de resumen de pytest o vitest, si la hay.
  local cifras
  cifras="$(sed 's/\x1b\[[0-9;]*m//g' "$log" | grep -E '[0-9]+ (passed|failed)' | tail -1 | tr -d '=' | tr -s ' ')"
  echo "$estado ${cifras}"
  RESUMEN+=("$(printf '%-28s %s %s' "$nombre" "$estado" "$cifras")")
}

coleccion_publicada() {
  (source "$REPO/scripts/corpus_release.sh" && printf '%s' "$CORPUS_RELEASE_COLLECTION")
}

cache_metricas() {
  if [[ -n "${CACHE_METRICAS:-}" ]]; then
    printf '%s' "$CACHE_METRICAS"
  else
    ls -t "$REPO"/rag/evaluation/results/generation-cache-v0.2*.jsonl 2>/dev/null | head -1
  fi
}

chroma_listo() { # chroma_listo <colección>
  (cd "$REPO/rag" && CHROMA_COLLECTION="$1" uv run --frozen python - <<'PY'
import chromadb
from rag.config import CHROMA_COLLECTION, CHROMA_HOST, CHROMA_PORT
chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT).get_collection(CHROMA_COLLECTION)
PY
  ) >/dev/null 2>&1
}

metricas() { # metricas <etiqueta> <colección> [args de metricas_sin_llm...]
  local tag="$1" col="$2"
  shift 2
  local cache
  cache="$(cache_metricas)"
  local args=(--tag "$tag")
  [[ -n "$cache" ]] && args+=(--cache "$cache")
  (cd "$REPO/rag" && CHROMA_COLLECTION="$col" uv run --frozen python -m evaluation.metricas_sin_llm "${args[@]}" "$@") \
    >"$LOGS/metricas-$tag.log" 2>&1
}

COLECCION="${CHROMA_COLLECTION:-$(coleccion_publicada)}"
if [[ "$METRICAS" == 1 ]] && ! chroma_listo "$COLECCION"; then
  echo "ChromaDB no responde o no tiene '$COLECCION': se omiten las métricas."
  METRICAS=0
fi

echo "Rama: $RAMA @ $ANTES · registros en ${LOGS#"$REPO"/}"

if [[ "$FUSIONAR" == 1 ]]; then
  if [[ "$ORIGEN" == origin/* ]]; then
    git fetch origin "${ORIGEN#origin/}" || exit 2
  fi
  NUEVOS="$(git log --oneline "HEAD..$ORIGEN")"
  if [[ -z "$NUEVOS" ]]; then
    echo "$ORIGEN no trae commits nuevos; se verifica el estado actual."
    FUSIONAR=0
  else
    echo "Commits nuevos de $ORIGEN:"
    echo "$NUEVOS" | sed 's/^/  /'
    BASE="$(git merge-base HEAD "$ORIGEN")"
    CHOQUE="$(comm -12 <(git diff --name-only "$BASE" "$ORIGEN" | sort) \
      <(git diff --name-only "$BASE" HEAD | sort))"
    if [[ -n "$CHOQUE" ]]; then
      echo "Archivos que cambian ambos lados (revisar la fusión aquí):"
      echo "$CHOQUE" | sed 's/^/  /'
    fi
    RESPALDO="respaldo-local/integracion-antes-corpus-$FECHA"
    git show-ref --quiet "refs/heads/$RESPALDO" && RESPALDO="$RESPALDO-$ANTES"
    git branch "$RESPALDO" HEAD && echo "Respaldo: $RESPALDO"
    if [[ "$METRICAS" == 1 ]]; then
      printf '%-28s' "métricas antes ($ANTES)"
      metricas "antes-$ANTES" "$COLECCION" && echo OK || echo "FALLO (ver log)"
    fi
    DESTINO="$(git rev-parse --short "$ORIGEN")"
    if ! git merge --no-ff --no-edit -m "merge: corpus hasta $DESTINO" "$ORIGEN"; then
      echo "Conflictos de fusión:" >&2
      git diff --name-only --diff-filter=U | sed 's/^/  /' >&2
      echo "Resuélvelos y vuelve a correr con --solo-verificar, o deshaz con: git merge --abort" >&2
      exit 2
    fi
  fi
fi

DESPUES="$(git rev-parse --short HEAD)"
NUEVA_COLECCION="${CHROMA_COLLECTION:-$(coleccion_publicada)}"
if [[ "$NUEVA_COLECCION" != "$COLECCION" ]]; then
  echo "AVISO: la colección publicada cambió ($COLECCION → $NUEVA_COLECCION)."
  echo "  Restaurar el Gold nuevo en el ChromaDB local antes de comparar (ver data/chroma-releases/README.md)."
  if [[ "$METRICAS" == 1 ]] && ! chroma_listo "$NUEVA_COLECCION"; then
    echo "  ChromaDB no tiene '$NUEVA_COLECCION': se omiten las métricas de después."
    METRICAS=0
  fi
fi

echo
echo "Verificación de $DESPUES:"
paso "rag uv sync" rag uv sync --frozen --all-packages --group dev --python 3.12
paso "rag ruff check" rag uv run --frozen ruff check backend/rag/ tests/ evaluation/ scripts/ utils/
paso "rag ruff format" rag uv run --frozen ruff format --check backend/rag/ tests/ evaluation/ scripts/ utils/
paso "rag mypy" rag uv run --frozen mypy backend/rag/
paso "rag pytest" rag uv run --frozen pytest tests/unit/ -q -o addopts= -p no:cacheprovider
paso "frontend install" rag bun install --frozen-lockfile
paso "frontend lint" rag/frontend bun run lint
paso "frontend typecheck" rag/frontend bun run typecheck
paso "frontend test" rag/frontend bun run test
paso "frontend build" rag/frontend bun run build
paso "ingesta uv sync" ingesta uv sync --frozen --group dev --python 3.12
paso "ingesta ruff check" ingesta uv run --frozen ruff check ingest/ tests/ utils/
paso "ingesta ruff format" ingesta uv run --frozen ruff format --check ingest/ tests/ utils/
paso "ingesta pytest" ingesta uv run --frozen pytest tests/unit/ -q -p no:cacheprovider
paso "ingesta contratos" ingesta uv run --frozen pytest tests/integration/ -m integration -q -p no:cacheprovider

if [[ "$METRICAS" == 1 ]]; then
  echo
  REF="rag/evaluation/results/metricas-sin-llm-v0.2-antes-$ANTES.json"
  if [[ "$DESPUES" != "$ANTES" && -f "$REPO/$REF" ]]; then
    echo "Métricas sin LLM de $DESPUES frente a $ANTES (misma sesión de ChromaDB):"
    metricas "despues-$DESPUES" "$NUEVA_COLECCION" --linea-base "../$REF"
    LOG_M="$LOGS/metricas-despues-$DESPUES.log"
    # Antes y después difieren solo en el código fusionado: una regresión es real.
    grep -q 'REGRESIÓN' "$LOG_M" && FALLOS=$((FALLOS + 1))
  else
    # Sin fusión no hay «antes»: se compara con la línea base versionada, que
    # puede ser de otra caché o de otro corpus; se informa, no se cuenta como fallo.
    echo "Métricas sin LLM de $DESPUES frente a la línea base versionada (informativo):"
    metricas "verificacion-$DESPUES" "$NUEVA_COLECCION"
    LOG_M="$LOGS/metricas-verificacion-$DESPUES.log"
  fi
  grep -E '^(recuperacion|respuesta) |REGRESIÓN|Empeora|AVISO|Reporte:' "$LOG_M" | sed 's/^/  /'
  CAMBIOS="$(grep -E '^(REGRESIÓN|Empeora)' "$LOG_M" | sed 's/ (revisar casos)//; s/ frente a la línea base//' | paste -sd ';' -)"
  RESUMEN+=("$(printf '%-28s %s' "métricas sin LLM" "${CAMBIOS:-sin regresiones ni empeoras}")")
fi

echo
echo "Resumen ($RAMA @ $DESPUES):"
printf '  %s\n' "${RESUMEN[@]}"
if [[ "$FALLOS" -gt 0 ]]; then
  echo "$FALLOS verificaciones con fallo o regresión; ver ${LOGS#"$REPO"/}." >&2
  exit 1
fi
echo "Todo en verde."
