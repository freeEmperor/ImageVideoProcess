# ImageVideoProcess —— 一键打包脚本
#
# 用法（在项目根目录执行）：
#     .\scripts\build-exe.ps1              # 单文件 exe（默认，产物 dist\ImageVideoProcess.exe）
#     .\scripts\build-exe.ps1 -Dir         # 文件夹版（排查问题用，产物 dist\ImageVideoProcess\）
#     .\scripts\build-exe.ps1 -Console     # 保留控制台窗口（能看到报错，调试打包用）
#
# 三个关键参数（缺一个都会出问题，详见 README 10.2）：
#   --paths src    src 布局 + uv 可编辑安装，PyInstaller 静态分析跟不进去，
#                  漏掉它打出的 exe 会一运行就退出（退出码 -1）且看不到任何报错
#   --icon         exe 文件本身的图标
#   --add-data     让窗口图标在运行时也能读到（代码里用 sys._MEIPASS 定位）
#
# 注意：单文件模式启动时要把内容解压到临时目录，若被杀软/策略拦住会报
#      "Failed to extract ...: fopen: Permission denied"，此时改用 -Dir。

[CmdletBinding()]
param(
    [switch]$Dir,       # 打成文件夹而不是单文件
    [switch]$Console    # 保留控制台窗口，便于看报错
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "== 1/4 检查 uv ==" -ForegroundColor Cyan
uv --version

Write-Host "== 2/4 准备图标 ==" -ForegroundColor Cyan
if (-not (Test-Path "assets\app.ico")) {
    Write-Host "assets\app.ico 不存在，自动生成"
    uv run python scripts\make_icon.py
} else {
    Write-Host "已存在 assets\app.ico"
}

Write-Host "== 3/4 打包（首次约 2~5 分钟）==" -ForegroundColor Cyan
$mode = if ($Dir) { "--onedir" } else { "--onefile" }
$win = if ($Console) { "--console" } else { "--windowed" }
uv run pyinstaller --noconfirm --clean `
    --name ImageVideoProcess `
    $mode $win `
    --paths src `
    --icon assets\app.ico `
    --add-data "assets\app.ico;assets" `
    src\imagevideoprocess\__main__.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 打包失败，退出码 $LASTEXITCODE" }

Write-Host "== 4/4 结果 ==" -ForegroundColor Cyan
$exe = if ($Dir) { "dist\ImageVideoProcess\ImageVideoProcess.exe" } else { "dist\ImageVideoProcess.exe" }
if (-not (Test-Path $exe)) { throw "没有找到产物 $exe" }
$item = Get-Item $exe
Write-Host ("产物: {0}" -f $item.FullName)
Write-Host ("体积: {0:N1} MB" -f ($item.Length / 1MB))
Write-Host ""
Write-Host "运行后，处理结果会写到 exe 同级的 processed 文件夹。" -ForegroundColor Green
Write-Host "若双击没反应，请用 -Console 重新打包看报错，或先看 README 10.2。" -ForegroundColor Yellow
