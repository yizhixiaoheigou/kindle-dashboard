<#
墨水桌面看板 · Windows 出包(PyInstaller → 单 EXE)

产出一个 MoshuiDesktop.exe(--onefile --windowed,无控制台窗、纯托盘):
双击进系统托盘 → 后台起看板服务 → 局域网 Kindle/平板取图。

⚠ 只能在 Windows 上跑(Linux 出不了 Windows exe)。需要 Python 3.10+。
用法:powershell -ExecutionPolicy Bypass -File installers\windows\build-win-app.ps1 1.0
迭代本地直跑(不出包):powershell ... build-win-app.ps1 -DevRun
#>
param(
  [string]$Version = "1.0",
  [switch]$DevRun
)
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)   # 仓库根
Set-Location $Repo
Write-Host "==> 仓库根:$Repo"

# 1. 建/复用 venv,装依赖
$Venv = Join-Path $Repo ".venv-win"
if (-not (Test-Path $Venv)) {
  Write-Host "==> 建虚拟环境 $Venv"
  python -m venv $Venv
}
$Py = Join-Path $Venv "Scripts\python.exe"
# 国内装包走清华镜像(快很多);失败再退官方源。可设环境变量 PIP_INDEX 覆盖。
$PipIndex = if ($env:PIP_INDEX) { $env:PIP_INDEX } else { "https://pypi.tuna.tsinghua.edu.cn/simple" }
$PipArgs = @("-i", $PipIndex, "--trusted-host", "pypi.tuna.tsinghua.edu.cn")
& $Py -m pip install --upgrade pip @PipArgs | Out-Null
Write-Host "==> 装运行依赖 + 打包依赖(清华镜像)"
& $Py -m pip install @PipArgs -r (Join-Path $Repo "server\requirements.txt")
if ($LASTEXITCODE -ne 0) {
  Write-Host "!  清华镜像装依赖失败,退回 PyPI 官方源重试…"
  & $Py -m pip install -r (Join-Path $Repo "server\requirements.txt")
}
& $Py -m pip install @PipArgs pystray psutil pyinstaller
if ($LASTEXITCODE -ne 0) { & $Py -m pip install pystray psutil pyinstaller }

# 2. 开发直跑:不打包,直接起托盘(快速验证逻辑)
if ($DevRun) {
  Write-Host "==> DevRun:直接起托盘(Ctrl+C 退出)"
  & $Py -m server.win_entry
  exit $LASTEXITCODE
}

# 3. 生成 .ico(优先用 appicon-1024.png,退回现画图标)
$Ico = Join-Path $Repo "installers\windows\app.ico"
& $Py -c @"
from PIL import Image
import os
src = r'installers/macos/appicon-1024.png'
out = r'installers/windows/app.ico'
sizes = [(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)]
if os.path.exists(src):
    Image.open(src).convert('RGBA').save(out, sizes=sizes)
else:
    from server.tray_win import _make_icon
    _make_icon().save(out, sizes=sizes)
print('icon ->', out)
"@

# 4. 写版本文件(updater.installed_version 读它)
Set-Content -Path (Join-Path $Repo "APP_VERSION") -Value $Version -NoNewline -Encoding ascii

# 5. PyInstaller 打包,用 .spec 文件(onefile/windowed/icon/add-data/collect 全在 spec 里)。
#    走 spec 是为了彻底绕开命令行 --add-data 的 ';' 分隔在 PowerShell 5.1 下被搞坏的问题。
#    注意:用 spec 时命令行【不能】再带 --onefile/--add-data/--icon 等(PyInstaller 会报冲突)。
$Spec = Join-Path $Repo "installers\windows\MoshuiDesktop.spec"
$Log = Join-Path $Repo "build-pyinstaller.log"
Write-Host "==> PyInstaller 打包中(约 1-3 分钟,期间窗口没有输出是正常的,请勿关闭)…"
# 把【全部输出】(含 PyInstaller 写到 stderr 的进度)重定向到日志文件,不刷在窗口上——
# 否则 PowerShell 会把 PyInstaller 的每行进度都当"错误流"标成红字,满屏吓人(其实不是错误)。
# 失败时再从日志打印末尾 40 行。EAP 放宽,纯防御。
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $Py -m PyInstaller --noconfirm --clean $Spec *> $Log
$pyiCode = $LASTEXITCODE
$ErrorActionPreference = $prevEAP

$Exe = Join-Path $Repo "dist\MoshuiDesktop.exe"
if (Test-Path $Exe) {
  # 发 GitHub Release 用的资产名(ASCII,与 updater 的 .exe 后缀匹配)
  $Named = Join-Path $Repo ("dist\MoshuiDesktop-{0}.exe" -f $Version)
  Copy-Item $Exe $Named -Force
  Write-Host "==> 完成:$Named"
  Write-Host "    直接双击即可进托盘;发布时把它挂到 GitHub Release(资产名须 MoshuiDesktop-$Version.exe)。"
} else {
  Write-Host ""
  Write-Host "X 打包失败(PyInstaller 退出码 $pyiCode),dist\MoshuiDesktop.exe 不存在。" -ForegroundColor Red
  Write-Host "----- 完整日志:$Log -----" -ForegroundColor Yellow
  Write-Host "----- 末尾 40 行(把这段截图发我)-----" -ForegroundColor Yellow
  if (Test-Path $Log) { Get-Content $Log -Tail 40 | ForEach-Object { Write-Host $_ } }
  exit 1
}
