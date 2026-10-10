param([switch]$WithBrowser)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $repoRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Create .venv and install requirements-dev.lock first.' }
Push-Location $repoRoot
try {
    & $pythonExe -m pytest backend/tests
    if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed.' }
    & $pythonExe -m ruff check backend
    if ($LASTEXITCODE -ne 0) { throw 'Backend lint failed.' }
    & $pythonExe -m backend.scripts.export_openapi --check
    if ($LASTEXITCODE -ne 0) { throw 'OpenAPI drift.' }
    foreach ($task in @('check:contracts', 'typecheck', 'build')) {
        & npm --prefix frontend run $task
        if ($LASTEXITCODE -ne 0) { throw "Frontend task failed: $task" }
    }
    & $pythonExe -m backend.scripts.validate_agents
    if ($LASTEXITCODE -ne 0) { throw 'Agent configuration check failed.' }
    if ($WithBrowser) {
        & $pythonExe -m backend.scripts.smoke_ui
        if ($LASTEXITCODE -ne 0) { throw 'Browser smoke failed; start API/UI and install Chromium first.' }
    }
} finally { Pop-Location }
