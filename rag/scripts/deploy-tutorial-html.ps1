#!/usr/bin/env pwsh
#
# Despliega en Vercel UNICAMENTE el tutorial HTML de ground truth.
#
# Como funciona:
#   Copia docs/ground-truth/ATLAS_Tutorial_Ground_Truth.html a una carpeta
#   temporal aislada como "index.html" y despliega SOLO esa carpeta. Asi el
#   sitio publicado contiene exclusivamente el HTML (nada del resto del repo).
#
# Requisitos (una sola vez):
#   - Vercel CLI instalado:   npm i -g vercel
#   - Sesion iniciada:        vercel login
#
# Uso:
#   pwsh scripts/deploy-tutorial-html.ps1                 # despliega a produccion
#   pwsh scripts/deploy-tutorial-html.ps1 -Preview        # despliega una preview
#
# Tras editar el HTML, simplemente vuelve a correr este script.

param(
    [switch]$Preview  # Si se pasa, crea un deployment de preview en vez de produccion.
)

$ErrorActionPreference = "Stop"

# --- Rutas ---
$RepoRoot = Split-Path -Parent $PSScriptRoot
$HtmlPath = Join-Path $RepoRoot "docs/ground-truth/ATLAS_Tutorial_Ground_Truth.html"
$Project  = "atlas-tutorial-groundtruth"

if (-not (Test-Path $HtmlPath)) {
    throw "No se encontro el HTML en: $HtmlPath"
}

# Verifica que el Vercel CLI este disponible.
if (-not (Get-Command vercel -ErrorAction SilentlyContinue)) {
    throw "Vercel CLI no encontrado. Instalalo con 'npm i -g vercel' e inicia sesion con 'vercel login'."
}

# --- Carpeta temporal aislada (solo contendra index.html) ---
$Tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("vercel-tutorial-" + [System.Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $Tmp | Out-Null

try {
    Copy-Item $HtmlPath (Join-Path $Tmp "index.html")

    Push-Location $Tmp
    try {
        # Vincula la carpeta temporal al proyecto existente en Vercel.
        vercel link --yes --project $Project
        if ($LASTEXITCODE -ne 0) { throw "Fallo 'vercel link' (codigo $LASTEXITCODE)." }

        # Despliega: produccion por defecto, o preview si se paso -Preview.
        if ($Preview) {
            Write-Host "`nDesplegando PREVIEW solo del HTML..." -ForegroundColor Cyan
            vercel deploy --yes
        } else {
            Write-Host "`nDesplegando a PRODUCCION solo del HTML..." -ForegroundColor Cyan
            vercel deploy --prod --yes
        }
        if ($LASTEXITCODE -ne 0) { throw "Fallo 'vercel deploy' (codigo $LASTEXITCODE)." }
    } finally {
        Pop-Location
    }

    Write-Host "`nListo. Produccion: https://atlas-tutorial-groundtruth.vercel.app" -ForegroundColor Green
} finally {
    # Limpia la carpeta temporal (incluye el .vercel que crea el link).
    Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue
}
