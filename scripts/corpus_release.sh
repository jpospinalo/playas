#!/usr/bin/env bash
# Defaults and local checks shared by the corpus deployment entrypoints.
# Sourcing this file does not connect to AWS, Chroma or Ollama.

CORPUS_RELEASE_BRANCH="corpus"
CORPUS_RELEASE_PACKAGE="gold-a-cc7bf44b54a9"
CORPUS_RELEASE_COLLECTION="rag_playas_gold_a_cc7bf44b54a9"
CORPUS_RELEASE_MODEL="embeddinggemma:latest"

corpus_release_python() {
  local repo="$1"
  if [[ -x "${repo}/rag/.venv/bin/python" ]]; then
    printf '%s\n' "${repo}/rag/.venv/bin/python"
  else
    command -v python3
  fi
}

corpus_release_check_local() {
  local repo="$1" python
  python="$(corpus_release_python "${repo}")" || return 1
  [[ -d "${repo}/data/chroma-releases/${CORPUS_RELEASE_PACKAGE}" ]] || {
    echo "Missing versioned Gold package: ${CORPUS_RELEASE_PACKAGE}" >&2
    return 1
  }
  "${python}" -I -S -B "${repo}/data/restore_gold_release.py" --check
}

# Only the selected value is returned to the caller; unsupported dotenv syntax
# is rejected locally before AWS rather than interpolated into remote HCL.
corpus_release_read_openai_key() {
  local path="$1"
  python3 -I -S -B - "${path}" <<'PY'
from pathlib import Path
import re
import sys

try:
    with Path(sys.argv[1]).open(encoding="utf-8") as stream:
        text = stream.read(65537)
except (OSError, UnicodeError):
    raise SystemExit("Unable to read the selected OpenAI credential") from None
if len(text) > 65536:
    raise SystemExit("Unsupported credential file size")
values = []
for line in text.splitlines():
    match = re.fullmatch(r"\s*(?:export\s+)?OPENAI_API_KEY\s*=(.*)", line)
    if match:
        values.append(match.group(1).strip())
if len(values) != 1:
    raise SystemExit("Exactly one OpenAI credential assignment is required")
value = values[0]
if value[:1] in ("'", '"'):
    if len(value) < 2 or value[-1] != value[0]:
        raise SystemExit("Unsupported OpenAI credential quoting")
    value = value[1:-1].strip()
if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
    raise SystemExit("Empty or unsupported OpenAI credential format")
print(value)
PY
}

corpus_release_published_head() {
  local repo="$1" remote="$2" branch commit published
  local selected=(scripts/corpus_release.sh data/restore_gold_release.py
    scripts/deploy_bastion_ec2.sh vector-infraestructura/scripts/deploy.sh
    vector-infraestructura/scripts/ec2_chroma_db.sh vector-infraestructura/scripts/ec2_ollama_embeddings.sh
    rag/infrastructure/scripts/deploy.sh rag/infrastructure/variables.tf rag/.env.example)
  local filename
  for filename in GOLD_A.jsonl.gz PROCEDENCIA_GOLD_A.json manifest.json README.md verificar_paquete.py; do
    selected+=("data/chroma-releases/${CORPUS_RELEASE_PACKAGE}/${filename}")
  done
  git -C "${repo}" ls-files --error-unmatch -- "${selected[@]}" >/dev/null || {
    echo "Commit all selected deployment inputs and the Gold package before deployment." >&2
    return 1
  }
  branch="$(git -C "${repo}" branch --show-current)" || return 1
  [[ "${branch}" == "${CORPUS_RELEASE_BRANCH}" ]] || {
    echo "Deployment must start from the corpus branch." >&2
    return 1
  }
  git -C "${repo}" diff --quiet -- || {
    echo "Commit tracked working-tree changes before deployment." >&2
    return 1
  }
  git -C "${repo}" diff --cached --quiet -- || {
    echo "Commit staged changes before deployment." >&2
    return 1
  }
  commit="$(git -C "${repo}" rev-parse HEAD)" || return 1
  [[ "${commit}" =~ ^[0-9a-f]{40}$ ]] || return 1
  published="$(git ls-remote --exit-code "${remote}" "refs/heads/${CORPUS_RELEASE_BRANCH}")" || return 1
  [[ "${published}" == "${commit}"$'\t'"refs/heads/${CORPUS_RELEASE_BRANCH}" ]] || {
    echo "Local HEAD must equal the published corpus HEAD before AWS changes." >&2
    return 1
  }
  printf '%s\n' "${commit}"
}

# Read only a concrete quoted string or positive integer for one deployment key.
# HCL expressions and duplicate assignments require an explicit operator choice.
corpus_release_tfvar() {
  local file="$1" key="$2" fallback="${3:-}"
  python3 -I -S -B - "${file}" "${key}" "${fallback}" <<'PY'
from pathlib import Path
import re
import sys

path, key, fallback = sys.argv[1:]
if not re.fullmatch(r"[a-z][a-z0-9_]*", key):
    raise SystemExit("Invalid deployment variable name")
matches = []
for line in Path(path).read_text().splitlines():
    if re.match(r"^\s*" + re.escape(key) + r"\s*=", line):
        match = re.fullmatch(r'\s*' + re.escape(key) + r'\s*=\s*(?:"([^"\\]*)"|([0-9]+))\s*(?:#.*)?', line)
        if match is None:
            raise SystemExit("Deployment variable must be a concrete string/integer: " + key)
        value = match.group(1) if match.group(1) is not None else match.group(2)
        if "${" in value or "%{" in value:
            raise SystemExit("Deployment variable must not interpolate HCL: " + key)
        matches.append(value)
if len(matches) > 1:
    raise SystemExit("Duplicate deployment variable: " + key)
value = matches[0] if matches else fallback
if not value:
    raise SystemExit("Missing concrete deployment variable: " + key)
print(value)
PY
}

corpus_release_receipt_directory() {
  local operation="$1" root="${HOME}/.local/state/playas-corpus"
  [[ "${operation}" == "restore" || "${operation}" == "verify" ]] || return 1
  mkdir -p -m 700 "${root}" || return 1
  mktemp -d "${root}/${CORPUS_RELEASE_PACKAGE}-${operation}.XXXXXX"
}

corpus_release_restore() {
  local repo="$1" host="$2" port="$3" ollama="$4" receipt="$5" mode="${6:-}" python
  local arguments=(--execute --host "${host}" --port "${port}" --ollama-base-url "${ollama}" --receipt "${receipt}")
  [[ -z "${mode}" || "${mode}" == "--verify-only" ]] || return 1
  [[ -z "${mode}" ]] || arguments+=("${mode}")
  python="$(corpus_release_python "${repo}")" || return 1
  "${python}" -I -S -B "${repo}/data/restore_gold_release.py" "${arguments[@]}"
}

corpus_release_wait_ollama() {
  local repo="$1" url="$2" python deadline
  python="$(corpus_release_python "${repo}")" || return 1
  deadline=$((SECONDS + 900))
  while (( SECONDS < deadline )); do
    if "${python}" -I -S -B - "${url}" "${CORPUS_RELEASE_MODEL}" <<'PY'
import http.client
import json
import signal
import sys
from urllib.parse import urlsplit

url = urlsplit(sys.argv[1])
if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password or url.path not in ("", "/") or url.query or url.fragment:
    raise SystemExit(1)
connection_type = http.client.HTTPSConnection if url.scheme == "https" else http.client.HTTPConnection
connection = connection_type(url.hostname, url.port, timeout=5)
def expired(_signum, _frame):
    raise TimeoutError("Model tags deadline")
signal.signal(signal.SIGALRM, expired)
signal.setitimer(signal.ITIMER_REAL, 5)
try:
    connection.request("GET", "/api/tags", headers={"Connection": "close"})
    response = connection.getresponse()
    raw = response.read(1024 * 1024 + 1)
    if response.status != 200 or len(raw) > 1024 * 1024:
        raise SystemExit(1)
    models = json.loads(raw).get("models", [])
    raise SystemExit(0 if any(row.get("model") == sys.argv[2] for row in models) else 1)
except (OSError, ValueError, TypeError, AttributeError, http.client.HTTPException):
    raise SystemExit(1)
finally:
    signal.setitimer(signal.ITIMER_REAL, 0)
    connection.close()
PY
    then
      return 0
    fi
    sleep 5
  done
  echo "Ollama model tags did not become available within 900 seconds; no inference was requested." >&2
  return 1
}
