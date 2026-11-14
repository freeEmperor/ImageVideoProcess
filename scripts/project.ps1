# All environment changes are scoped to this command and restored afterwards.
[CmdletBinding()]
param([ValidateSet('sync','run','check','diagnose')][string]$Action = 'run')
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$location = Get-Location
$names = @('UV_CACHE_DIR','UV_PYTHON_INSTALL_DIR','PYTHONPATH')
$saved = @{}
foreach ($name in $names) { $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
try {
    Set-Location $root
    . "$PSScriptRoot/activate-env.ps1"
    $env:PYTHONPATH = $null
    switch ($Action) {
        'sync' { uv sync --locked }
        'run' { uv run --locked imagevideoprocess }
        'diagnose' { uv run --locked python -m imagevideoprocess.runtime.envreport }
        'check' {
            uv run --locked pytest
            if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
            uv run --locked ruff check src tests scripts
            if ($LASTEXITCODE -ne 0) { throw 'Lint failed' }
            uv run --locked mypy
            if ($LASTEXITCODE -ne 0) { throw 'Type checks failed' }
            uv run --locked python scripts/smoke_test.py
        }
    }
    if ($LASTEXITCODE -ne 0) { throw "Command failed: $Action" }
} finally {
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process') }
    Set-Location $location
}
