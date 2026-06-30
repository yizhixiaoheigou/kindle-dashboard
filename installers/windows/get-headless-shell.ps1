<#
墨水桌面看板 · Windows 渲染引擎兜底下载

仅当机器上一个 Chromium 内核浏览器都没有(连系统自带 Edge 都被卸了)时才需要它。
从国内可直连镜像 npmmirror(淘宝)下 chrome-headless-shell-win64,**不用梯子**,
解压到 %APPDATA%\墨水桌面看板\chrome-headless-shell\<版本>\,供 pipeline._headless_shell 探测。

用法:powershell -ExecutionPolicy Bypass -File installers\windows\get-headless-shell.ps1
#>
$ErrorActionPreference = "Stop"
$Root = Join-Path $env:APPDATA "墨水桌面看板\chrome-headless-shell"
$Mirror = "https://registry.npmmirror.com/-/binary/chrome-for-testing"

function Has-Shell {
  if (-not (Test-Path $Root)) { return $false }
  return [bool](Get-ChildItem -Path $Root -Recurse -Filter "chrome-headless-shell.exe" -ErrorAction SilentlyContinue | Select-Object -First 1)
}

if (Has-Shell) { Write-Host "==> 已有 chrome-headless-shell,跳过下载。"; exit 0 }

Write-Host "==> 本机没有可用的 Chromium 内核,从 npmmirror 镜像下载 chrome-headless-shell(国内直连)…"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# 1. 取版本列表,从新到旧挑一个 win64 有 chrome-headless-shell 的。
$versions = @()
try {
  $list = Invoke-RestMethod -Uri "$Mirror/" -UseBasicParsing -TimeoutSec 30
  $versions = $list |
    ForEach-Object { ($_.name).TrimEnd('/') } |
    Where-Object { $_ -match '^\d+\.\d+\.\d+\.\d+$' } |
    Sort-Object { [version]$_ } -Descending
} catch {
  Write-Host "! 取版本列表失败:$($_.Exception.Message)"
}
if (-not $versions -or $versions.Count -eq 0) {
  Write-Host "X 无法从镜像取到版本列表。请改用任一 Chromium 内核浏览器(装 Edge/Chrome)后重试。"
  exit 1
}

New-Item -ItemType Directory -Force -Path $Root | Out-Null
$tmp = Join-Path $env:TEMP ("chs-" + [System.Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $tmp | Out-Null

$ok = $false
foreach ($ver in ($versions | Select-Object -First 8)) {
  $url = "$Mirror/$ver/win64/chrome-headless-shell-win64.zip"
  $zip = Join-Path $tmp "$ver.zip"
  try {
    Write-Host "  尝试 $ver …"
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing -TimeoutSec 120
  } catch { continue }
  if (-not (Test-Path $zip) -or (Get-Item $zip).Length -lt 1000000) { continue }
  $dest = Join-Path $Root $ver
  if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
  $unzip = Join-Path $tmp $ver
  Expand-Archive -Path $zip -DestinationPath $unzip -Force
  # zip 内层目录是 chrome-headless-shell-win64\ —— 把含 exe 的那层内容拍平到 $dest\。
  $exe = Get-ChildItem -Path $unzip -Recurse -Filter "chrome-headless-shell.exe" | Select-Object -First 1
  if (-not $exe) { continue }
  New-Item -ItemType Directory -Force -Path $dest | Out-Null
  Copy-Item -Path (Join-Path $exe.Directory.FullName "*") -Destination $dest -Recurse -Force
  if (Test-Path (Join-Path $dest "chrome-headless-shell.exe")) { $ok = $true; break }
}

Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue

if ($ok) {
  Write-Host "==> 完成。渲染引擎已就绪:$Root"
  exit 0
} else {
  Write-Host "X 下载/解压均失败。请改装任一 Chromium 内核浏览器(Edge/Chrome)后重试。"
  exit 1
}
