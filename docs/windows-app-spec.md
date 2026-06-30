# 墨水桌面看板 · Windows 托盘 EXE 施工图

> ✅ **真机端到端跑通(2026-06-30,Windows 11 真机)**:把服务端移植到 Windows,打包成**一个托盘 EXE**——双击进系统托盘常驻、叉掉到托盘、托盘菜单退出才停服务;只要它开着,Kindle / 现代平板 / 老平板都能来本机取图。**v1 全功能对齐 Mac 版**。
>
> **真机验证结果(Windows 11 / Python 3.13 / 系统自带 Edge)**:`双击安装.bat` 一键装好 → 打包出 `MoshuiDesktop-1.0.exe`(21.4MB,PE32+ GUI)→ 托盘常驻 → 服务 `0.0.0.0:8585` 起 → **Edge 无头渲染出图正常**:局域网另一台机访问 `http://<win-ip>:8585/kindle/frame.png` 拿到 **600×800 8-bit 灰度 PNG**,中文字体清晰、排版正确(资讯页 AIHOT)。左键开设置页、切语言不掉线、退出三选一、开机自启全部就位。**核心结论:渲染管线(唯一难啃的跨平台块)在 Windows 用系统 Edge 完全正常,无需打包字体(系统字体渲染中文 OK)。**
>
> 本机(Linux)自检:309 测试绿(含 6 个跨平台分支测试)。落地详情见 §13「as-built / 已落地」,真机调试踩坑见 §14。
>
> 决策(2026-06-29 与浩轩确认):
> - **渲染引擎 = Chromium 内核检测优先、缺了才下载**:先探测系统里任一 Chromium 内核浏览器(Edge/Chrome/Brave…,Win10/11 自带 Edge 几乎必中)→ 有就直接用、**零下载**;一个都没有 → 从**国内可直连镜像(npmmirror)**下 `chrome-headless-shell-win64` 兜底。渲染本质是调内核的 `--headless --screenshot` 命令行,跟浏览器牌子无关。Windows 无头 Edge **不会**有 macOS 的 Dock 抖动问题(那是 macOS 专属)。
> - **打包 = PyInstaller `--onefile --windowed`**:产出单个 `MoshuiDesktop.exe`,无控制台窗、纯托盘形态(对位 Mac 菜单栏)。
> - **不签名**:首次运行走 SmartScreen「更多信息 → 仍要运行」放行一次(对位 Mac Gatekeeper)。
>
> **本文是给实现 AI 的自包含施工图。** 动手前先读项目根 `CLAUDE.md`(三条铁律 + 安全与健壮性防回归节)、`docs/mac-app-spec.md`(Mac 版对位实现,本文大量复用其思路)、`server/render/pipeline.py`(渲染管线,**唯一需要跨平台改造的核心文件**)、`server/menubar.py`(Mac 状态栏,Windows 托盘的对位范本)。
>
> ⚠️ **我(写代码的 AI)在 Linux 环境,无法实测 Windows。** 纯 Python 代码 + 模拟测试能在本机写完自检;**真正出包(PyInstaller)和真机验证必须在浩轩的 Windows 机上做**(如同 build-mac-app.sh 只能在 Mac 跑)。流程:我出代码+脚本+自检测试 → 浩轩跑构建/回截图日志 → 据此迭代。

---

## 0. 一句话目标

把"`git clone` + Python 起服务"的部署,在 Windows 上包装成**一个托盘 EXE**:双击 → 进系统托盘(无主窗口)→ 服务在后台跑、局域网设备来取图 → 托盘右键菜单开设置页 / 刷 Kindle / 检查更新 / 退出。**全程不碰命令行。**

**"只要开着就能取图、叉掉到托盘、托盘退出才停"** 的语义:这本来就是个**纯托盘程序、没有主窗口**(和 Mac 菜单栏同形态)。`--windowed` 打包后双击不弹任何窗口、直接进托盘;看板服务作为**子进程**跟随托盘进程生命周期——只有托盘菜单点「退出」才一起结束。

非目标(v1 不做):应用内静默自替换 exe(改成"提示去下载新版 .exe",运行中的 exe 无法直接覆盖);付费代码签名;把 Python/Chromium 全打进包(内核走系统探测,缺了才按需下)。

---

## 0.5 现状摸底结论(为什么这事可行)

通读 `kindle-dash-oss` 后的判断:

- **服务端 95% 是跨平台 Python**(FastAPI + Jinja2 + PIL),Windows 直接能跑。真正卡平台的只有**一个文件** `server/render/pipeline.py`:用了 POSIX 专有的进程组杀进程(`os.killpg` / `start_new_session` / `signal.SIGKILL` / `pkill`)和写死的 Mac/Linux 浏览器路径。
- **渲染引擎在 Windows 几乎零成本**:Win10/11 自带 Edge(Chromium 内核),`msedge.exe --headless=new --screenshot` 出图与 Mac 一致。
- **Windows 的料已有一半**(已存在并真机测过,直接复用):
  - `server/sources/collectors/collect_windows.ps1`(本机设备监控)
  - `installers/kindle/install.ps1` + `uninstall.ps1`(Kindle 刷机/还原,含 USB/WiFi 两种连法,`.ps1` 已带 UTF-8 BOM)
  - `installers/push-agent/push_agent.ps1` + `install_agent.ps1`(设备 push agent)
- **配置/数据不丢机制天然兼容**:`app._resolve_config_path` 用 `expanduser("~/.config/kindle-dashboard/config.yaml")`,Windows 上落 `C:\Users\<用户>\.config\kindle-dashboard\`,升级/重装不丢配置的机制不变。
- **在线更新器已参数化**:`updater.check_release(asset_suffix=...)` 传 `.exe` 即可复用,与 `.dmg`/`.apk` 各发各的、互不误判(`_ver_from_asset` 按文件名取版本)。

**Mac 专属、需在 Windows 重写/对位的部分**:`menubar.py`(状态栏)、`bootstrap.sh`/`install.sh`(安装器)、launchd 自启、`build-mac-app.sh`(出包)。Windows 用**托盘 App + PyInstaller + 注册表自启**替换。

| 能力 | 现有文件(复用) | Windows 怎么用 |
|---|---|---|
| 渲染管线(截图/旋转/灰度/僵尸清理/部分失败保留旧页) | `server/render/pipeline.py` | **跨平台改造**(§1):杀进程分支 + Windows 浏览器候选 |
| 服务主体(采集/渲染/路由/鉴权/三档 UA 分流) | `server/app.py` 等 | 一字不改,直接跑 |
| 本机设备监控 | `collect_windows.ps1` | 直接用 |
| Kindle 刷机/还原 | `installers/kindle/install.ps1`/`uninstall.ps1` | 托盘菜单调起 |
| 在线更新逻辑 | `server/updater.py` | 传 `asset_suffix='.exe'` |
| 状态栏程序(状态/启停/设置页/语言/检查更新) | `server/menubar.py`(rumps) | **对位重写**为 `server/tray_win.py`(pystray) |

---

## 1. 渲染管线跨平台化 `server/render/pipeline.py`(核心,唯一硬骨头)

这是整个移植**唯一真正卡平台**的文件。改造点:

### 1.1 `find_chrome` 加 Windows 内核探测
只要找到任一 Chromium 内核就用,不挑牌子(浩轩定调)。Windows 候选(按优先级):
- `_headless_shell()` 命中的无头壳(§2 下载落地处)
- `where.exe` / `shutil.which` 查 PATH:`msedge`、`chrome`、`brave`
- 写死候选路径:
  - Edge:`%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe`(Win10/11 几乎必有)
  - Chrome:`%ProgramFiles%\Google\Chrome\Application\chrome.exe`、`%ProgramFiles(x86)%\...`、`%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe`
  - Brave / Vivaldi 等同理
- `CHROME_BIN` 环境变量覆盖(现状保留)

实现要点:用 `os.environ.get("ProgramFiles")` 等而非写死盘符,兼容非 C 盘安装。

### 1.2 进程起停按平台分支(防 POSIX 调用在 Windows 崩)
现状用 `start_new_session=True` + `os.killpg(os.getpgid(pid), SIGKILL)`——**Windows 没有进程组/setsid/SIGKILL,直接 AttributeError**。抽象成:

```
IS_WIN = sys.platform == "win32"
# 起子进程:
#   POSIX:  start_new_session=True
#   Windows: creationflags=CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
# 整组杀(_kill_group):
#   POSIX:  os.killpg(os.getpgid(pid), SIGKILL)
#   Windows: subprocess.run(["taskkill","/F","/T","/PID",str(pid)])   # /T 连子进程树
```

- `CREATE_NO_WINDOW`:防每次渲染弹黑色 cmd 窗口(Windows 起子进程默认会闪)。
- `_pkill(pattern)`(按 `kdash-render` 标记全局清僵尸 Chrome):Windows 没有 `pkill`。引入 **`psutil`**(跨平台、体积小),按 `proc.cmdline()` 含 `kdash-render` 精准杀;POSIX 维持 `pkill -9 -f`。psutil 同时让 `_kill_group` 更稳(可 `children(recursive=True)` 兜底)。

### 1.3 `_headless_shell` 加 Windows 缓存路径
- `%APPDATA%\墨水桌面看板\chrome-headless-shell\*\chrome-headless-shell.exe`(§2 下载落地处)
- puppeteer/playwright 的 Windows 缓存目录(`%LOCALAPPDATA%\...`)

### 1.4 渲染命令(无需大改)
`--headless=new --screenshot` 等参数 Windows 通用;`file://` URL 用 `pathlib.Path(html_path).as_uri()` 生成(Windows 路径含盘符/反斜杠,别手拼 `file://`)。`is_headless_shell` 判定逻辑不变(壳不加 `--headless`)。

### 1.5 测试 `tests/test_pipeline_win.py`
monkeypatch `sys.platform == 'win32'`,验证:① 候选路径含 Edge ② 杀进程拼成 `taskkill /F /T` 而非 `killpg` ③ `file://` URI 生成正确。**在 Linux 上也能跑**(纯字符串/分支断言,不真起 Chrome)。现有测试保持全绿。

---

## 2. 渲染引擎"检测优先、缺了才下载"(两步方案)

### 第一步:检测(绝大多数机器到此为止)
首启 / 安装时跑 `find_chrome()`:命中任一内核 → 直接用,**零下载**。Win10/11 自带 Edge,这步通常就够。

### 第二步:兜底下载(没装任何 Chromium 内核的极端机器)
从**国内可直连镜像**下 `chrome-headless-shell-win64`,**不用梯子**:
- 镜像源:**npmmirror(淘宝)的 chrome-for-testing 镜像** `https://registry.npmmirror.com/-/binary/chrome-for-testing/`(国内直连稳定)。
- 落地:解压到 `%APPDATA%\墨水桌面看板\chrome-headless-shell\<版本>\chrome-headless-shell.exe`。
- 脚本:`installers/windows/get-headless-shell.ps1`(对位 Mac 的 `get-headless-shell.sh`)。
- 触发:安装/首启探测到一个内核都没有时才下;有就跳过。

---

## 3. Windows 托盘 App `server/tray_win.py`(对位 `menubar.py`)

- **技术栈**:`pystray` + `Pillow`(画托盘图标,复用 `installers/macos/appicon-1024.png` 转 `.ico`)。**不引 rumps**(Mac 专属)。
- **形态**:纯托盘、无主窗口(对位 Mac 菜单栏)。
- **菜单**(逐项对位 Mac 版,i18n 复用现有 `I18N` 中英字典思路):
  - 状态行(服务运行中 / 已停)
  - 打开设置页(`webbrowser.open` 带令牌的 `/setup?token=`)
  - 重启服务
  - 开机自启 ✓(§4)
  - 语言 ▸ 中文 / English(写 `config.server.language` 后重载)
  - 检查更新(§6)
  - 刷入 Kindle / 退出 Kindle(§5)
  - 卸载墨水桌面看板…
  - 退出(连子进程一起收)
- **监工逻辑**:
  - 启动即拉起看板服务**子进程**:`subprocess.Popen([sys.executable, "--server"], creationflags=CREATE_NO_WINDOW)`(onefile 下 `sys.executable` 指向 exe 自身,靠 `--server` 参数分流到角色 B)。
  - 后台线程轮询 `http://127.0.0.1:<port>/health` 更新状态行。
  - 「退出」/「重启」:`taskkill /F /T /PID <子进程>` 收干净再(重)起。

### 3.1 入口参数分流(onefile 单 exe 双角色)
`server/win_entry.py`(PyInstaller 入口):
```
if "--server" in sys.argv:   # 角色B:看板服务
    from server.run import main; main()
else:                         # 角色A:托盘监工(默认)
    from server.tray_win import main; main()
```

---

## 4. 开机自启

- 用**注册表 `HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run`** 写一条值(`winreg` 标准库,**无需管理员权限**,最干净)。
- 托盘菜单「开机自启」开关 = 写入 / 删除这条键;值 = `"<exe 全路径>"`。
- 备选:Startup 文件夹放快捷方式(若注册表方案遇杀软拦截再降级)。

---

## 5. Kindle 刷机 / 还原(复用现成 .ps1)

- 直接复用 `installers/kindle/install.ps1` / `uninstall.ps1`(已带 USB/WiFi 两种连法、已带 UTF-8 BOM、真机测过)。
- 托盘菜单调:`powershell -ExecutionPolicy Bypass -File installers\kindle\install.ps1 <看板URL> [-KindleIp <IP>]`。
- **依赖 Windows 自带 OpenSSH 客户端**(Win10 1809+ 默认含 `ssh`/`scp`):检测缺失则提示一键开启(设置→应用→可选功能,或 `Add-WindowsCapability`)。
- ⚠️ Kindle 插 Windows 的固有门槛(见 CLAUDE.md「已知坑」):USBNetwork 一重启就回 U 盘模式、需手装 RNDIS 驱动 → 文档主推 **WiFi 连法**(填 Kindle 的 WiFi IP)绕开。

---

## 6. 在线更新(对齐 Mac,只提示不自替换)

- `updater.check_release(owner, repo, asset_suffix=".exe")`,资产名 `MoshuiDesktop-X.Y.exe`(ASCII 命名,`_ver_from_asset` 正则已兼容)。
- 与 `.dmg`/`.apk` 同发一个 Release 互不误判(遍历 releases 按后缀过滤,现状逻辑已具备)。
- 策略同 Mac:查到新版 → 弹提示 → **打开下载页 / 下载新 exe 让用户手动运行**(运行中的 exe 无法直接覆盖自己;v1 不做静默自替换,避免引入"自替换 + 重启"的坑)。
- 托盘启动 8s + 每 6h 后台静默查,有新版把「检查更新」标记/加红点(对位 Mac)。

---

## 7. 打包出 EXE `installers/windows/build-win-app.ps1`

- **PyInstaller `--onefile --windowed`** → 单个 `MoshuiDesktop.exe`。
- 打进:`server/`、`web/`、`styles/`、`fonts/`、`.ico` 图标(`--add-data`;注意 Windows `--add-data` 分隔符是 `;`)。
- 依赖:`fastapi uvicorn httpx Pillow Jinja2 PyYAML lunardate zeroconf pystray psutil pyinstaller`(**去 rumps**)。
- onefile 自调子进程:`sys.executable + ["--server"]` 成立(`sys.executable` = exe 自身)。
- 资源路径:打包后用 `sys._MEIPASS` 解析 `web/`、`styles/`、`fonts/`(PyInstaller 临时解压目录);代码里 `REPO_ROOT`/`WEB_DIR` 等要兼容 frozen(加 `getattr(sys,'_MEIPASS',...)` 分支)。**数据/配置绝不能写进 `_MEIPASS`**(每次解压目录都变)——配置走 `~/.config`、数据走 `%APPDATA%`(§8)。
- 版本号每次递增(触发更新提示)。
- **必须在 Windows 上跑**(Linux 不能出 Windows exe)。迭代可加开关跳过装包、本地直跑。

---

## 8. 配置 / 数据路径(小调整)

- **配置**:沿用 `~/.config/kindle-dashboard/config.yaml`(Windows 自动落 `C:\Users\<用户>\.config\`),不丢配置机制不变。
- **数据目录**:`KINDLE_DATA_DIR` 指到 `%APPDATA%\墨水桌面看板\data`(`os.environ["APPDATA"]`)——更符合 Windows 习惯,且 onefile 临时解压目录每次变、**绝不能把数据/缓存写那里**。在 `win_entry.py` 启动时,若没设 `KINDLE_DATA_DIR` 就默认指 `%APPDATA%`。
- 所有现有走 `KINDLE_DATA_DIR` 的持久化(ccusage / 提醒 / music / mstodo token / artwork)自动跟随,无需逐个改。

---

## 9. 已知风险 / 必须内建处理

1. **无法在本机(Linux)实测 Windows**:出包 + 真机验证在浩轩的 Windows 机上做。我出代码/脚本/自检测试,浩轩回截图+日志,迭代。
2. **防火墙**:首次起服务,Windows Defender 防火墙弹"是否允许网络访问"——不放行则局域网 Kindle/平板取不到图。安装/首启用 `netsh advfirewall firewall add rule`(入站、TCP、端口 8585)自动加规则,免用户漏点。
3. **SmartScreen**:未签名 exe 首次运行拦"Windows 已保护你的电脑" → "更多信息 → 仍要运行"放行一次(对位 Gatekeeper),文档明示。
4. **子进程黑窗**:Windows 起任何子进程(Chrome 渲染 / ps1 脚本)默认闪黑色 cmd 窗 → 一律 `CREATE_NO_WINDOW`。
5. **uvicorn 子进程信号**:作为独立子进程跑无问题。若日后改单进程内线程跑服务,要 `uvicorn.Server(config, install_signal_handlers=False)`(已知解法,先记着)。
6. **路径分隔符 / `file://`**:Windows 路径反斜杠 + 盘符,凡拼 URL 用 `Path.as_uri()`;`--add-data` 用 `;` 分隔。

---

## 10. 落地顺序(每步可独立验证)

1. **渲染管线跨平台化 + Edge 探测**(改 `pipeline.py`,补 `test_pipeline_win.py`)→ 通了之后 Windows 上 `python -m server.run` 就能出图、Kindle/平板已能取图(**主线打通**)。【纯 Python,本机能写完自检】
2. **托盘 App + 注册表自启 + 设置页入口**(`tray_win.py`、`win_entry.py`)→ "叉掉到托盘、退出才停"成立。
3. **PyInstaller 出包**(`build-win-app.ps1`)→ 真正的单 EXE。【Windows 上跑】
4. **Kindle 刷机 / 在线更新 / 卸载接进托盘** → 全功能对齐 Mac。
5. **引擎缺失时的国内镜像下载兜底**(`get-headless-shell.ps1`)→ 覆盖没装任何浏览器的极端机器。
6. **文档 + 真机联调收尾**:本文转为"真机落地实录"(对位 mac-app-spec §10),README / install.md 补 Windows 段。

---

## 11. 落地文件清单(预计)

- **改**:`server/render/pipeline.py`(跨平台杀进程 + Windows 浏览器候选)、`server/app.py`(frozen 资源路径兼容,若需要)、`server/requirements-win.txt`(或在 requirements 加 `pystray; sys_platform=='win32'` 等环境标记)。
- **新增**:
  - `server/tray_win.py`(托盘 App)
  - `server/win_entry.py`(入口参数分流)
  - `installers/windows/build-win-app.ps1`(PyInstaller 出包)
  - `installers/windows/get-headless-shell.ps1`(引擎兜底下载)
  - `installers/windows/MoshuiDesktop.spec`(PyInstaller 配置,可选)
  - `tests/test_pipeline_win.py`(跨平台分支自检)
  - 图标 `.ico`(由 appicon-1024.png 转)
- **复用不改**:`installers/kindle/install.ps1`/`uninstall.ps1`、`collect_windows.ps1`、`installers/push-agent/*.ps1`、`server/updater.py`。

---

## 12. 真机验证清单(Windows 机上,2026-06-30 大部分已验)

- [x] Edge headless 截图正常、无黑窗(真机:`/kindle/frame.png` 出 600×800 灰度 PNG,中文清晰)
- [x] 托盘:双击进托盘、叉掉到托盘、退出(三选一)、重启服务
- [x] 注册表开机自启**首启自动写入**(`.autostart_initialized` marker;reboot 后自动起待用户最终确认)
- [x] PyInstaller onefile 出包(21.4MB)+ 子进程 `--server` 拉起正常 + 资源路径(web/styles)正常
- [x] 局域网另一台设备能取到图(防火墙允许后,`http://<win-ip>:8585` 可达)
- [x] SmartScreen 放行流程走通
- [x] 左键开设置页 / 切语言不掉线 / 单实例互斥
- [ ] 渲染超时 / 僵尸清理在 Windows 用 `taskkill /T` 杀干净(正常路径已验,超时分支未专门压测)
- [ ] Kindle 刷机(WiFi 连法)从托盘跑通(未测——手边无越狱 Kindle 接 Windows)
- [ ] 引擎兜底:卸载所有浏览器后 npmmirror 下载 chrome-headless-shell(未触发——真机自带 Edge)

---

## 13. as-built / 已落地(2026-06-29,本机部分完成)

> 以下为**实际写进仓库**的内容,与 §1–§9 设计一致,落地时的细节以本节为准。代码部分在 Linux 本机写完并自检(308 测试绿);PyInstaller 出包与真机行为仍待 §12 验证。

### 13.1 渲染管线跨平台化 `server/render/pipeline.py`(已改)
- 顶部加 `IS_WIN = sys.platform == "win32"` + `_SPAWN_KW`(POSIX=`start_new_session=True`;Windows=`creationflags=CREATE_NEW_PROCESS_GROUP|CREATE_NO_WINDOW`,常量 `0x0200|0x08000000`)。
- `psutil` 顶部 **try-import 可选**:没装也不崩(POSIX 不需要;Windows 没装则 `_pkill` 降级为不做全局清理,单次渲染仍由 `_kill_group` 的 `taskkill /T` 收干净)。
- 新增 `_win_candidates()`:按 `ProgramFiles`/`ProgramFiles(x86)`/`LOCALAPPDATA` 环境变量拼 Edge/Chrome/Brave/Vivaldi/Chromium 路径(兼容非 C 盘)。
- `_playwright_chrome` / `_headless_shell` 加 Windows 缓存路径(`%LOCALAPPDATA%\ms-playwright\…`、`%APPDATA%\墨水桌面看板\chrome-headless-shell\*\chrome-headless-shell.exe`)。
- `find_chrome`:Windows 上 which 查 `msedge/chrome/brave/vivaldi/chromium`(多半空),再退到 `_win_candidates()+_CANDIDATES` 命中存在的固定路径。
- `_pkill`:Windows 走 psutil 按 `cmdline` 含 `kdash-render` 标记精准杀;POSIX 维持 `pkill -9 -f`。
- `_kill_group`:Windows 走 `taskkill /F /T /PID`(+ psutil children 兜底);POSIX 维持 `os.killpg`。**两边末尾都 `proc.wait` 收僵尸。**
- `_shot_to_image`:`file://` 改 `Path(html_path).as_uri()`(Windows 盘符+反斜杠手拼会失败);`--user-data-dir` 用 `os.path.join`;Popen 用 `**_SPAWN_KW`。
- **POSIX 行为零变化**(IS_WIN=False 分支与改动前等价);串行锁 `_RENDER_MUTEX`、超时一刀杀、不用 `subprocess.run(timeout)` 跑 Chrome 等**所有防回归红线原样保留**。

### 13.2 新增文件
| 文件 | 作用 |
|---|---|
| `server/win_entry.py` | 单 exe 双角色入口:`--server`→服务、默认→托盘;Windows 默认把 `KINDLE_DATA_DIR` 指到 `%APPDATA%\墨水桌面看板\data`(onefile 解压目录每次变,不能写那) |
| `server/tray_win.py` | 托盘 App(pystray + PIL 图标 + tkinter 弹窗);**进程监工模型**:自己拉起/守护服务子进程(`exe --server`),崩了自动拉起;菜单=状态/打开设置/重启/开机自启(注册表 Run)/语言/刷·退 Kindle(调 powershell ps1,新控制台窗交互输密码)/检查更新(`asset_suffix='.exe'`)/卸载/退出 |
| `installers/windows/get-headless-shell.ps1` | 引擎兜底:一个内核都没有时从 **npmmirror** 取版本列表→下 `chrome-headless-shell-win64`→拍平解压到 `%APPDATA%\墨水桌面看板\chrome-headless-shell\<ver>\`(已带 UTF-8 BOM) |
| `双击安装.bat`(仓库根) | **最终用户入口**:双击即跑(ASCII 内容+CRLF+无 BOM,免 cmd GBK 乱码)→ 调 run-on-windows.ps1 `-Dest <自身目录> -Build 1.0 -Launch`,就地装好并启动。用户只需把整个文件夹拷到本地、双击它 |
| `installers/windows/run-on-windows.ps1` | 一键编排:检测 Python(`py -3`/`python`/`python3`,有 ≥3.10 就用、不重下;没有才从 **npmmirror** 国内直连装 3.12.7 静默安装)→ robocopy 项目到本地盘(网络盘不打包)→ 默认起托盘 DevRun、`-Build <ver>` 出 EXE(已带 UTF-8 BOM) |
| `installers/windows/build-win-app.ps1` | PyInstaller `--onefile --windowed` 出包:建 `.venv-win`、装依赖+pystray/psutil/pyinstaller、`appicon-1024.png`→`.ico`、`--add-data` 按仓库布局塞 web/styles/fonts/installers/collectors、`--collect-all uvicorn`、`--exclude-module rumps`、写 `APP_VERSION`、产出 `dist\MoshuiDesktop-<ver>.exe`;`-DevRun` 跳过打包直跑托盘(已带 UTF-8 BOM) |
| `tests/test_pipeline_win.py` | 6 个跨平台分支测试(monkeypatch 模拟 win32):候选路径、find_chrome 退候选、taskkill 不调 killpg、psutil 按标记杀、`_SPAWN_KW` 互斥。**Linux 上即可跑全绿** |

- `server/requirements.txt` 加 `pystray>=0.19; sys_platform=='win32'` + `psutil>=5.9; sys_platform=='win32'`(marker 控制,Mac/Linux 不装)。

### 13.3 落地时确认/微调的点(与设计一致,记录细节)
- **资源根**:`app.py` 的 `REPO_ROOT = dirname(dirname(__file__))`,PyInstaller onefile 下 `__file__` 在 `_MEIPASS/server/app.py` → `REPO_ROOT=_MEIPASS`,所以 `--add-data` 按 `web;web`/`styles;styles`/`installers;installers` 等原样布局即对,**代码不用改 REPO_ROOT**。`tray_win` 读 ps1 用独立的 `_resource_root()`(优先 `_MEIPASS`)。
- **psutil 设为可选**而非硬依赖:让 `pipeline.py` 在没装 psutil 的任何环境都能 import(测试/精简部署),只有 Windows 全局清僵尸才真正用它。
- **语言切换**:Windows 改完 `config.language` 后**自动重启服务子进程**(监工模型下最干净),不像 Mac 那样提示"重开菜单栏"。
- **Kindle 刷机**走 `CREATE_NEW_CONSOLE` 开可见 PowerShell 窗(刷机要交互输 SSH 密码,可见窗比后台捕获稳),复用已有 `install.ps1 -KindleIp -Interval` / `uninstall.ps1 -KindleIp`。
- **更新策略**与 Mac 一致:只提示+开下载页,不自替换运行中的 exe(v1)。

### 13.5 上机前复检(2026-06-29,发现并修复)
- **🔴 关键 bug:pystray 动作回调参数个数**。核对 pystray 源码 `MenuItem.__call__` = `self._action(icon, self)`(动作回调收 **2 个参数**;而 `text`/`checked`/`enabled` 回调收 1 个)。原稿所有菜单动作回调只收 1 个(`def _x(self, _=None)`)/lambda 收 0 个 → **每次点菜单都会 TypeError 崩**。已全部改成 `(self, icon=None, item=None)`、语言 lambda 改 `lambda icon=None, item=None:`。(text/checked 的 `lambda i:` 本就对,不动。)
- **弹窗改 Win32 原生**:info/yesno 用 `ctypes.windll.user32.MessageBoxW`(无事件循环,绝不与托盘消息泵打架);仅文本输入(WiFi IP/间隔)还用 tkinter `askstring`。
- **单实例保护**:命名互斥量 `MoshuiDesktopTraySingleton`——开机自启 + 用户又双击不会起两个托盘 + 两个服务抢 8585。
- **开机自启首启自动开**:打包 exe **首次运行**自动写注册表 Run 键(marker `%APPDATA%\墨水桌面看板\.autostart_initialized` 只做一次),之后尊重菜单开关;开发 `-m` 启动不自动设(自启命令脆弱)。
- **freeze_support**:`win_entry.main()` 头部加 `multiprocessing.freeze_support()`(onefile 防子进程重跑整个 exe)。
- **出包补 `--collect-all zeroconf`**(mDNS 自发现的已知 PyInstaller 盲区;缺了非致命但顺手兜上)。

### 13.4 ⏳ 仍需 Windows 真机做的(本机无法完成)
PyInstaller 出包、§12 全部真机验证项、以及出包后可能要补的 `--hidden-import`(uvicorn/zeroconf 动态导入若漏)。出包脚本已尽量用 `--collect-all uvicorn` / `--collect-submodules server` 兜底,真机若报缺模块按报错补 hidden-import 即可。

---

## 14. 真机调试踩坑实录(2026-06-30,Windows 11,as-built 以此为准)

打包+真机过程踩的坑,**全部已修进代码**;按出现顺序排,给后来人避雷:

1. **`双击安装.bat` 路径非法字符**:`-Dest "%~dp0"` 里 `%~dp0` 结尾带 `\`,`\"` 被当转义引号 → PowerShell 收到的路径末尾混进 `"` → 「路径中有非法字符」。修:`.bat` 先剥掉结尾反斜杠(`set HERE` + 判尾);run-on-windows.ps1 对 `$Dest` 再 `Trim('"')/TrimEnd('\')` 兜底。
2. **`taskkill` 在 Stop 模式抛终止错误**:首次打包前杀旧 exe,`taskkill ... 2>$null` 在「没找到进程」时把那句 stderr 升级成终止错误(`2>$null` 重定向 + `$ErrorActionPreference=Stop` 的著名组合)。修:`taskkill` 改走 `cmd /c "... >nul 2>&1"` 自吞。同类:`Get-PyVersion` 函数内放宽 EAP、只按退出码判。
3. **`--add-data` 在 PowerShell 5.1 下被 `;` 搞坏**:`pyinstaller: error: argument --add-data: Wrong syntax`。PyInstaller 6.x 命令行 `--add-data SOURCE;DEST` 的 `;` 分隔经 PS5.1 传原生参数时坏掉。修:**改用 `installers/windows/MoshuiDesktop.spec`**(datas/binaries/hiddenimports 全 Python 元组,源路径用 `SPECPATH` 推 `REPO` 取绝对路径),build 脚本 `pyinstaller --noconfirm --clean MoshuiDesktop.spec`(spec 模式不能再带 `--onefile/--add-data/--icon`)。
4. **spec 误带不存在的 `fonts/`**:`ERROR: Unable to find '...\fonts'`。本仓库根本没有 `fonts/`(从旧仓库误带);渲染用系统字体(Chromium 自取),无需打包字体。修:去掉 fonts,且 datas 改成「只收 `os.path.exists` 为真的路径」。
5. **`--collect-submodules server` 拉崩 rumps**(分析阶段):它枚举时会 import `server.menubar`(Mac 专属、`import rumps`),Windows 没装 rumps → ModuleNotFoundError。修:**去掉 `--collect-submodules server`**(win_entry 静态 import 已带全需要的模块),改在 spec 用 `excludes=['rumps','server.menubar']`。
6. **满屏红字其实是成功的进度**:`2>&1 | Tee-Object` 把 PyInstaller 写到 stderr 的 INFO 逐行标红,看着像失败。修:打包输出 `*> $Log` 全量重定向到日志文件,窗口只显示「打包中,请稍候…」,失败才打印日志末尾 40 行。
7. **pystray 回调参数个数**:动作回调按 `action(icon, item)`(2 参)调用,原稿写成 1 参/lambda 0 参 → 每点必崩。修:所有动作回调 `(self, icon=None, item=None)`,lambda `(icon=None, item=None)`。(text/checked 回调是 1 参 `lambda i:`,本就对。)
8. **左键无反应**:pystray 只把菜单绑右键,左键调「默认项」。修:给「打开设置页」加 `default=True` → 左键单击开设置页。
9. **切语言后服务短暂离线**:`_set_lang` 误调 `_restart_service`,杀服务→新 uvicorn 要几秒启动→这期间设置页打不开。根因:语言根本不需重启(配置按 mtime 热重载,`render_loop` 每轮 `maybe_reload`)。修:去掉重启;托盘菜单语言靠 `self.lang`+refresh 即时更新。**与 Mac 一致(它也从不为切语言重启服务)。**
10. **`\d` SyntaxWarning**:win_entry 模块 docstring 含 `…\墨水桌面看板\data` 的 `\d`。修:docstring 改 `r"""`。

**真机已确认 OK 的能力**:Edge 无头出图(600×800 灰度,中文清晰)、托盘常驻、左键设置页、右键菜单、切语言不掉线、退出三选一、开机自启首启自动设、局域网供图、单实例互斥。
