# Project-local interpreter and cache; managed-only policy is in pyproject.toml.
$projectRoot = Split-Path -Parent $PSScriptRoot
$env:UV_CACHE_DIR = Join-Path $projectRoot '.uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $projectRoot '.uv-python'
