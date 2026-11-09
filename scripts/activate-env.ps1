# 把本项目的 uv 环境变量加载到当前 PowerShell 会话。
#
# 用法（在项目根目录）：
#     .\scripts\activate-env.ps1
#
# 为什么需要它：uv 0.12.2 **不会**自动读取项目根目录的 .env，
# 而本项目故意把 uv 的缓存和 Python 副本都放在项目目录内
# （见 .env 里的说明），所以每个新终端都要先把这几个变量设上。
#
# 不激活也能用，只是 uv 会退回全局默认位置
# （%LOCALAPPDATA%\uv\cache 与 %APPDATA%\uv\python）。

$projectRoot = Split-Path -Parent $PSScriptRoot
$cacheDir = Join-Path $projectRoot '.uv-cache'
$pythonDir = Join-Path $projectRoot '.uv-python'
$nuitkaDir = Join-Path $projectRoot '.nuitka-cache'

$env:UV_CACHE_DIR = $cacheDir
$env:UV_PYTHON_INSTALL_DIR = $pythonDir
$env:NUITKA_CACHE_DIR = $nuitkaDir
# 大小写两种都设：不同程序读的写法不一样。
# 作用是让 uv 等工具**跳过代理、直连**——它会覆盖你 $PROFILE 里
# 设的 HTTP_PROXY / HTTPS_PROXY。若你想走代理，把下面两行删掉即可，
# 或改成只保留本地地址例外：$env:NO_PROXY = 'localhost,127.0.0.1'
$env:NO_PROXY = '*'
$env:no_proxy = '*'

Write-Host 'ImageVideoProcess 环境变量已加载:' -ForegroundColor Green
Write-Host ('  {0,-22} = {1}' -f 'UV_CACHE_DIR', $cacheDir)
Write-Host ('  {0,-22} = {1}' -f 'UV_PYTHON_INSTALL_DIR', $pythonDir)
Write-Host ('  {0,-22} = {1}' -f 'NUITKA_CACHE_DIR', $nuitkaDir)
Write-Host ('  {0,-22} = {1}' -f 'NO_PROXY', '*')
Write-Host ''
Write-Host '提示: NO_PROXY=* 会让 uv 直连不走代理。' -ForegroundColor Yellow
Write-Host '      若你需要走代理才能上网，请把这两行删掉或改成你的代理设置。' -ForegroundColor Yellow
