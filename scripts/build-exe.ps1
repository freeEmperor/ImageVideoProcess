[CmdletBinding()]
param([switch]$Dir, [switch]$Console)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$savedLocation = Get-Location
$names = @('UV_CACHE_DIR','UV_PYTHON_INSTALL_DIR','PYINSTALLER_CONFIG_DIR','IVP_BUILD_DIR','IVP_BUILD_CONSOLE','PATH','PYTHONPATH')
$saved = @{}
foreach ($name in $names) { $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
try {
    Set-Location $root
    . "$PSScriptRoot/activate-env.ps1"
    $env:PYTHONPATH = $null
    $env:PYINSTALLER_CONFIG_DIR = Join-Path $root 'build/pyinstaller-cache'
    $env:IVP_BUILD_DIR = [int]$Dir.IsPresent
    $env:IVP_BUILD_CONSOLE = [int]$Console.IsPresent
    $uv = (Get-Command uv -CommandType Application).Source
    & $uv sync --locked --group packaging
    if ($LASTEXITCODE -ne 0) { throw 'Dependency sync failed' }
    $env:PATH = "$env:SystemRoot/System32;$env:SystemRoot"
    & $uv run --locked --group packaging python -m PyInstaller --noconfirm --clean --distpath dist --workpath build/pyinstaller packaging/ImageVideoProcess.spec
    if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
} finally {
    foreach ($name in $names) { [Environment]::SetEnvironmentVariable($name, $saved[$name], 'Process') }
    Set-Location $savedLocation
}
