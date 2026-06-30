<#
墨水桌面看板 · Windows 一键跑(给浩轩用)

干三件事:① 检测 Python(有就用、没有才从 npmmirror 国内直连装)
         ② 把项目从 NAS 拷到本地盘(打包不在网络盘上跑,快且不污染同步盘)
         ③ 起托盘验证(默认)或出 EXE(-Build)

用法(在 PowerShell 里,从 NAS 上这个目录直接跑即可):
  默认 = 拷到本地 + 起托盘测试:
    powershell -ExecutionPolicy Bypass -File installers\windows\run-on-windows.ps1
  出正式 EXE(版本号每次递增):
    powershell -ExecutionPolicy Bypass -File installers\windows\run-on-windows.ps1 -Build 1.0
  换本地目标盘:加 -Dest D:\kindle-dash
#>
param(
  [string]$Build  = "",                # 传版本号(如 1.0)= 出 EXE;不传 = 起托盘测试(DevRun)
  [string]$Dest   = "C:\kindle-dash",  # 本地工作目录
  [switch]$Launch                      # 出 EXE 后直接启动它(双击 .bat 走这条:一步到位)
)
$ErrorActionPreference = "Stop"
# 防御:清掉传入路径可能粘上的引号/空白(%~dp0 结尾反斜杠把闭合引号转义时会留下杂质)。
$Dest = ([string]$Dest).Trim().Trim('"').TrimEnd('\')

# ---------- 1. 确保有 Python(>=3.10),返回 python.exe 全路径 ----------
function Get-PyVersion($exe, $launcherArgs) {
  # 函数内放宽:native 命令往 stderr 写东西时,Stop 模式 + 2>$null 会抛终止错误;
  # 这里只看退出码判断成败,别让一句无害的 stderr 警告误杀一个能用的 Python。
  $ErrorActionPreference = "SilentlyContinue"
  try {
    $out = & $exe @launcherArgs "-c" "import sys;print('%d.%d'%sys.version_info[:2]);print(sys.executable)" 2>$null
    if ($LASTEXITCODE -eq 0 -and $out) {
      $lines = @($out)
      $ver = [version]$lines[0]
      return @{ ok = ($ver -ge [version]"3.10"); ver = $lines[0]; path = $lines[1] }
    }
  } catch {}
  return $null
}

function Ensure-Python {
  # 依次试:py -3 启动器 / python / python3。任一 >=3.10 就用它,不重复下载。
  foreach ($cand in @(@{e="py";a=@("-3")}, @{e="python";a=@()}, @{e="python3";a=@()})) {
    if (Get-Command $cand.e -ErrorAction SilentlyContinue) {
      $r = Get-PyVersion $cand.e $cand.a
      if ($r -and $r.ok) {
        Write-Host "==> 已检测到 Python $($r.ver):$($r.path)(直接用,不重新下载)"
        return $r.path
      } elseif ($r) {
        Write-Host "!  检测到 Python $($r.ver),但低于 3.10,准备装一个新的。"
      }
    }
  }

  # 没有可用的 → 从 npmmirror(淘宝)镜像下官方安装器,国内直连不用梯子。
  $pyver = "3.12.7"
  $url = "https://registry.npmmirror.com/-/binary/python/$pyver/python-$pyver-amd64.exe"
  $installer = Join-Path $env:TEMP "python-$pyver-amd64.exe"
  Write-Host "==> 没有可用 Python,从 npmmirror 下载 $pyver(国内直连)…"
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
  Invoke-WebRequest -Uri $url -OutFile $installer -UseBasicParsing -TimeoutSec 300
  Write-Host "==> 静默安装(当前用户,自动加 PATH + pip)…"
  Start-Process -FilePath $installer -Wait -ArgumentList `
    "/quiet","InstallAllUsers=0","PrependPath=1","Include_pip=1","Include_test=0"
  # 装完当前会话 PATH 还没刷新,直接按已知的每用户安装位置找 python.exe。
  $maj = ($pyver -split '\.')[0..1] -join ''
  $guess = Join-Path $env:LOCALAPPDATA "Programs\Python\Python$maj\python.exe"
  if (Test-Path $guess) {
    Write-Host "==> 安装完成:$guess"
    return $guess
  }
  # 兜底:py 启动器现在应能找到
  $r = Get-PyVersion "py" @("-3")
  if ($r -and $r.ok) { return $r.path }
  throw "Python 装好了但没定位到 python.exe,请重开 PowerShell 后再跑一次本脚本。"
}

$PyExe = Ensure-Python
# 把这个 python 的目录放到本会话 PATH 最前,后面 build 脚本里的裸 `python` 就能命中它。
$env:Path = (Split-Path $PyExe) + ";" + (Split-Path $PyExe) + "\Scripts;" + $env:Path

# ---------- 2. 拷到本地盘(已经在本地就跳过) ----------
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)   # installers\windows → 仓库根
$DestFull = (New-Item -ItemType Directory -Force -Path $Dest).FullName
if ($RepoRoot.TrimEnd('\') -ieq $DestFull.TrimEnd('\')) {
  Write-Host "==> 已在本地工作目录运行,跳过拷贝:$DestFull"
} else {
  Write-Host "==> 从 NAS 拷到本地盘:`n    $RepoRoot`n  → $DestFull(排除 .git/venv/构建产物,首次稍慢)"
  robocopy $RepoRoot $DestFull /E /NFL /NDL /NJH /NJS /NP `
    /XD ".git" ".venv-win" "build" "dist" "__pycache__" ".pytest_cache" | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "robocopy 拷贝失败(退出码 $LASTEXITCODE)。检查源/目标路径与磁盘空间。" }
}

# ---------- 3. 起托盘 / 出包(调本地副本的 build 脚本) ----------
$BuildPs1 = Join-Path $DestFull "installers\windows\build-win-app.ps1"
Set-Location $DestFull
if ($Build) {
  # 若已有一个在跑,先收掉(否则 PyInstaller 覆盖不了正在运行的 exe)。
  # 用 cmd /c 让 taskkill 自己吞掉 stderr —— 否则 "没找到进程" 这句会在 Stop 模式下被当成终止错误抛出。
  cmd /c "taskkill /IM MoshuiDesktop.exe /F /T >nul 2>&1"
  Write-Host "==> 出 EXE,版本 $Build(首次装依赖+打包要几分钟,别关窗口)…"
  & powershell -ExecutionPolicy Bypass -File $BuildPs1 $Build
  if ($LASTEXITCODE -ne 0) { throw "打包失败,见上面的报错。" }
  $Exe = Join-Path $DestFull ("dist\MoshuiDesktop-{0}.exe" -f $Build)
  if ($Launch -and (Test-Path $Exe)) {
    Write-Host "==> 启动看板:$Exe(进系统托盘;首次运行自动设好开机自启)"
    Start-Process -FilePath $Exe
    Write-Host "`n  全部完成!右下角托盘应出现图标。第一次起服务会弹防火墙 → 点『允许』。"
  } else {
    Write-Host "`n  完成:$Exe(双击它即可进托盘)。"
  }
} else {
  Write-Host "==> 起托盘测试(DevRun):托盘出现图标后,右键点菜单、防火墙弹窗点『允许』。Ctrl+C 退出。"
  & powershell -ExecutionPolicy Bypass -File $BuildPs1 -DevRun
}
