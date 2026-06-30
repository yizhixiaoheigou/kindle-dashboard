# 安装指南(详细)

> 总览见 [README](../README.md)。本文补充各数据源配置、Kindle 前置、故障排查、验证状态。

## 一、装服务(三选一:Mac / Windows / NAS)

> 看板服务跑在哪台常开机器都行,Kindle/平板取图完全一致。下面是 **Mac**;**Windows** 见 [README「Windows 桌面部署」](../README.md#windows-桌面部署托盘-exe) + 施工图 [windows-app-spec.md](windows-app-spec.md)(双击 `双击安装.bat` 一键装);**NAS Docker** 见 [README「NAS Docker 部署」](../README.md#nas-docker-部署)。

### Mac 服务

**推荐:图形安装(.dmg)。** 到 [Releases](https://github.com/yizhixiaoheigou/kindle-dashboard/releases) 下载 `MoshuiDesktop-x.x.dmg` → 拖进「应用程序」→ 双击。首启自动建环境(复制源码到 `~/Library/Application Support/墨水桌面看板/repo` 建 venv)、起服务、状态栏出图标;首次联网下载**无头渲染引擎 chrome-headless-shell ~100MB**(渲染不弹 Dock、已有则跳过)+ **Python 依赖 ~40MB**(测速自动选官方/清华源)。**装/设置/刷退 Kindle/检查更新/卸载全在状态栏菜单**。未签名,首开右键「打开」或系统设置放行一次。

**命令行安装(开发者 / 进阶):**

```bash
git clone https://github.com/yizhixiaoheigou/kindle-dashboard.git kindle-dashboard && cd kindle-dashboard
bash installers/macos/install.sh
```

手动起服务(调试用):

```bash
.venv/bin/python -m server.run     # 读 config.yaml 的端口,绑 0.0.0.0
```

自己出 .dmg 分发:在 Mac 上 `bash installers/macos/build-mac-app.sh <版本>`(只能 Mac 跑;Linux 不能 hdiutil)。

- 配置文件:**仓库外** `~/.config/kindle-dashboard/config.yaml`(首次从 `config.example.yaml` 生成,详见下「配置文件位置」)
- 日志:`data/*.log`(service / menubar / codex-quota / reminders);**服务自动轮转**——超 5MB 截断只留最近 1MB,长期跑不爆盘,无需手动清。
- 改端口需重启服务;其余配置网页保存即热重载
- **访问令牌**(防同 WiFi 他人访问设置页):首次启动自动生成,存 `config.yaml` 的 `server.access_token`;`install.sh` 装完会打印 `http://<IP>:端口/setup?token=...`,**用这个带令牌的链接打开设置页**(或点菜单栏「打开设置页」)。`/api/*` 与预览需令牌;**Kindle 拉图(`/kindle/frame.png`)、设备上报、`/health` 豁免**,不受影响。令牌留空=不鉴权(不推荐)。

安装脚本会自动处理依赖,中途会问你两件事:
- **渲染引擎**:没检测到 Chrome 时,问是否自动下载内置 chromium(playwright,约 150MB,装进 venv、不动系统)。选 Y 即可,无需自己装 Chrome。
- **AI 用量统计**:问是否启用(见下「AI 用量」);选启用会自动检测 Node + ccusage,缺了再安装,不用你手动装。

**菜单栏程序**:装完后 Mac 顶部状态栏只显示 Kindle 小图标,不显示「看板」文字。点开可看运行状态、当前版本、打开设置页、重启/启停服务、**检查更新**,也可用「开机自启」勾选项控制主服务下次登录是否自动启动。安装脚本会生成一个本地 `LSUIElement` app bundle,只显示在顶部状态栏,不会在 Dock 里显示 Python 图标。依赖 `rumps`,install.sh 会自动装(老环境的 venv 若缺它,重跑 install.sh 即补上)。

**配置文件位置**:真实配置在**仓库外** `~/.config/kindle-dashboard/config.yaml`(`KINDLE_CONFIG` 环境变量可覆盖)。这样升级 / 重装 / 删库重拉**都不丢设置**;若老版本把 `config.yaml` 放在仓库内,首次启动会自动迁移过去。

### 更新已部署的服务(代码有新版时)
配置改动网页保存即热重载;但 **Python 代码更新必须重启进程**才生效。两种方式:
- **菜单栏一键(推荐)**:点顶部菜单栏图标 → **检查更新** → 有新版会提示,点「升级」自动 `git pull --ff-only` + 重启(配置在仓库外,升级不动你的设置)。
- **命令行**:`cd ~/kindle-dashboard && git pull` 后跑 `bash installers/macos/restart.sh`(主服务+菜单栏一并重启),或重跑 `bash installers/macos/install.sh`(更新依赖+重启+自检)。
- 验证:浏览器开 `http://<本机IP>:端口/health`。
> ⚠️ 不要直接在网络共享盘(SMB/NFS,Mac 上的 `/Volumes/...`)里跑服务:venv 在网络盘建不干净。务必先把项目拷到本地盘(如 `~/kindle-dashboard`)再装/更新。
> 在线升级要求看板是用 `git clone` 装的(非 git 目录菜单栏会提示无法在线升级,改用命令行覆盖)。

## 二、各数据源配置

### 天气(QWeather)
1. 注册 [和风天气](https://dev.qweather.com/) 免费开发者
2. 拿到 **API Key** 和**专属 API Host**(形如 `xxx.re.qweatherapi.com`)
3. 查城市 **LocationID**(如北京 `101010100`)
4. 设置页「天气」填入 → 首页出现天气

### Home Assistant(打印机/更多设备)
1. HA 用户资料页 → 创建**长期访问令牌**(Long-Lived Access Token)
2. 设置页「Home Assistant」填地址 + 令牌
3. 「3D 打印机」点「扫描」选择打印机 → 保存后打印机页出现

### AI 用量(ccusage)
- **本机直采,零配置,无中间服务**:安装时回答"启用 AI 用量"→ 自动装 Node + [ccusage](https://github.com/ryoppippi/ccusage) 并把 `ai_usage.enabled` 置 true,服务端每轮跑 `ccusage claude/codex daily --json` 读本机日志(见 `server/sources/ccusage_cli.py`)。看板服务跑在哪台机器就读那台的用量。
- 「额度」(5h/周窗口)是另一回事(ccusage 不提供),见下「AI 额度」小节;不启用时 AI 页额度显示 0%(诚实降级)。

### AI 额度(Claude 5h/周 + Codex 5h/周,仅 macOS)
在 AI 页显示 Claude / Codex 的额度用量%。**push 模式**:在跑 Claude Code / Codex CLI 的机器上采集,POST 到看板 `/api/rate-limits`(看板服务本身拿不到这些数据,只能被设备送上门)。

- **Claude**(官方机制,稳):走 Claude Code 的 **statusLine** —— Claude Code 把含 `rate_limits` 的 JSON 从 stdin 喂给你配的状态栏命令。`enable_quota.sh` 检测 `~/.claude/settings.json`:**没配过 statusLine 就备份后写入**指向 `installers/macos/quota/claude_statusline.py`;**已自定义则不覆盖**,打印「把那段 POST 抄进你自己的 statusline」的指引(脚本里 `# >>> 上报额度` 到 `# <<<` 那段)。
- **Codex**(⚠️ 非公开接口,可能失效):`codex_quota.py` 读 `~/.codex/auth.json` 调 `chatgpt.com/backend-api/wham/usage`,launchd 定时上报。`wham/usage` 是 OpenAI 内部接口、无文档,**官方一改即失效**(不影响 Claude)。国内访问 chatgpt.com 多半要代理:设置页「AI 用量」填 **Codex 代理**(或 config 设 `ai_usage.codex_proxy: http://127.0.0.1:7897`)。

启用方式(在装看板的 Mac 上、项目目录执行):
- **装看板时**:`install.sh` 会问「是否启用 AI 额度?」+「Codex 多久上报一次(秒)」,选 `y` 即自动装好。
- **事后想加**:`bash installers/macos/enable_quota.sh`。脚本会同步把 `ai_usage.enabled` 置 true,避免装了额度采集但 AI 页仍被隐藏。
- **停用**:`bash installers/macos/disable_quota.sh`(卸 Codex launchd;Claude 的 statusLine 按提示自行撤)
- **间隔**:`ai_usage.codex_quota_interval`(秒,launchd)/ `ai_usage.claude_quota_interval`(秒,statusLine 节流);改后重跑 `enable_quota.sh` 生效。

### 设备监控(Win/Linux/Mac)
**看板所在机(这台 Mac)**:安装时回答"启用本机性能监控"即可(自动加一台 `local` 设备),或事后在设置页「设备监控」加一台『本机直读』。

**另一台机器(NAS / Linux / Mac)三选一:**
- **本机直读(local)**:仅服务所在机,零额外安装。
- **推(agent,推荐,不交密码)**:在设置页「设备监控」底部复制那行命令,到目标机上跑一次即可:
  ```sh
  curl -fsSL http://<看板IP>:<端口>/agent/install.sh | sh -s -- http://<看板IP>:<端口> 30
  ```
  装好后每 30 秒(改末尾数字调间隔)推一次,目标机自动出现在设置页「发现设备」里,点一下加进来改名。
  设置页生成这行命令时,**看板地址下拉里有个 `Xxx.local:端口` 选项**——目标机支持 mDNS(多数 Mac/Linux)的话选它,可绕开 Mac IP 漂移(IP 变了名字不变);不支持 mDNS 的设备用 IP 地址即可。
  自启:Linux 用 `@reboot` cron、macOS 用 launchd。卸载:`... | sh -s -- uninstall`。
  **Windows**:设置页同时给出 PowerShell 命令(`iwr .../agent/install.ps1 ... | ...`),自启用『计划任务』(登录启动);卸载把末尾换成 `uninstall`。
  **间隔由目标机 agent 自己定(装时设),看板设置页改不了**(与本机直读的服务端间隔不同)。
- `platform` 选对(auto/linux/macos/windows);可重命名、勾选只显示部分指标。

采集脚本:`server/sources/collectors/`(linux.sh / macos.sh / windows.ps1),本机直读 / 推 agent 两处复用。
推送 agent:`installers/push-agent/`(`install_agent.sh` 由看板 `/agent/install.sh` 下发;`push_agent.sh` 循环采集+POST)。

### 提醒事项(苹果,仅 macOS)
把本机「提醒事项」App(含 iPhone 经 iCloud 同步过来的)显示到看板。原理:一个后台 agent 每 5 分钟用 JXA 读 Reminders.app,POST 到 `/api/apple-sync`。

启用方式(任选其一,两种都需在你装看板的 Mac 终端、项目目录下执行):
- **装看板时**:`install.sh` 会问「是否启用提醒事项同步?」,选 `y` 即自动装好。
- **事后想加**:在设置页「提醒事项」卡片复制那行命令运行:
  ```bash
  bash installers/macos/enable_reminders.sh
  ```
- **停用**:`bash installers/macos/disable_reminders.sh`

首次运行会弹「允许访问提醒事项」,**必须点【允许】**,否则读不到。误点拒绝:系统设置 → 隐私与安全性 → 提醒事项,勾选 终端/osascript 后重跑命令。

> 为什么不在网页上放个开关?因为它要装本机后台 agent + 一次系统授权,只有终端前台运行才弹得出授权框;网页点开关会变成「显示开着、其实没数据」。所以用一行命令一键搞定,装/卸状态以 agent 是否在为准(设置页徽章)。

## 三、Kindle 前置

1. **越狱**:按你的固件版本找对应方法(本项目不含越狱工具)
2. **开 USBNetwork**:让 Kindle 通过 USB 提供 SSH(默认 IP 常为 `192.168.15.244`)
3. **装 fbink**:刷屏必需,通常随 KUAL/越狱工具包提供
4. 数据线用支持**数据传输**的(非纯充电线)
5. **SSH root 密码**:安装时会要求输入。越狱包(KUAL/USBNetwork 等)**常见默认密码是 `mario`**;若你越狱时改过,用你设的。`install.sh` 运行时也会提示这条。

然后主机端:

```bash
sh installers/kindle/detect.sh [KINDLE_IP]      # 识别:USB 接入 + SSH 可达
sh installers/kindle/install.sh [KINDLE_IP] [SERVER_URL] [INTERVAL]
sh installers/kindle/uninstall.sh [KINDLE_IP]   # 一键还原
```

**Windows 主机**(Kindle 插 Windows 电脑刷图):用 PowerShell 版,**右键 PowerShell『以管理员身份运行』**(配 USB 网卡需管理员;Windows 10+ 自带的 OpenSSH 客户端要装上):
```powershell
powershell -ExecutionPolicy Bypass -File installers\kindle\install.ps1     # 一键刷图(可加 -KindleIp / -ServerUrl / -Interval)
powershell -ExecutionPolicy Bypass -File installers\kindle\uninstall.ps1   # 一键还原成正常电子书
```
> 逻辑与 .sh 一致(用 `netsh` 配 USB 网卡、Windows 自带 `ssh`/`scp`)。`.gitattributes` 强制 `*.sh`=LF、`*.ps1`=BOM+CRLF,防 Windows clone 破坏脚本(`.ps1` 无 BOM 会被 PS5 按 GBK 读、中文乱码)。
>
> **两种连法(设置页「服务」卡的刷机框有 Kindle IP 输入框,填好自动拼好完整命令)**:
> - **方式一 USB**(默认 `192.168.15.244`):Kindle 插电脑。⚠️ 前提两关——① Kindle 上**先开 USBNetwork**(KUAL;**它一重启就关、默认是 U 盘存储模式**,Windows 会把它认成磁盘而非网卡)② Windows 把 Kindle 认成『网络适配器/RNDIS』(认成未知设备就到设备管理器装『远程 NDIS 兼容设备』驱动)。这两关是越狱 Kindle 插 Windows 的固有门槛。
> - **方式二 WiFi(推荐,免装驱动)**:Kindle 连 WiFi → 路由器后台查到它的 IP → 填进刷机框(或 `-KindleIp <IP>`)。脚本检测到非 `.244` 就**跳过 USB 配置、直接走 WiFi SSH**,Win/Mac/Linux 完全一样,不碰 RNDIS 驱动。
> - **SSH 前提 / 自启**:**首次**刷机时 Kindle 需先开着 SSH(USBNetwork 的 dropbear,WiFi/USB 都听)。装上看板后 `start.sh` 会**自启 dropbear**——以后看板跑着 SSH 就常开,远程刷一条命令直连,不用每次重开。
> - **抢开机窗口刷**:看板占屏会把系统界面连同 SSH 一起杀掉(见故障排查),但 Kindle **重启的开机瞬间** SSH 是通的。`install.sh --wait <KindleIP> <URL> [间隔]` 会每 5 秒探一次、SSH 就绪即自动刷——先跑上它,再去重启 Kindle 即可抓住窗口。
> - ✅ 真机验证状态(2026-06-09):USB/WiFi 刷机、`--wait` 抓窗口、SSH 自启均真机通过。

`install.sh` 会推送 `start.sh`/`stop.sh`、写服务地址到 `/mnt/us/dashboard.conf`、加 `@reboot` 自启(带 `# kindle-dashboard` 标记便于卸载精确移除)、启动显示。

**刷新间隔**:`install.sh` 运行时会问「Kindle 多久拉一次新图(秒)」,常用 10/20/30/60、回车默认 20,写进 `dashboard.conf` 的 `INTERVAL`(也可作第三参数传入,如 `... [SERVER_URL] 30`;非交互默认 20,<5s 自动回退 20)。注意区分两个间隔:
- **`INTERVAL`(Kindle 拉图间隔)**:刷机时定,Kindle 端多久拉一张新图。改它要重跑 `install.sh`,网页改不了。
- **`page_interval`(服务端轮播间隔)**:看板多少秒翻一页,设置网页里随时可配。

**服务器 IP 别变(关键)**:Kindle 按固定地址拉图,**看板服务所在那台机器的 IP 一旦变,Kindle 就拉不到图、看板停更**。按服务在哪台机器分两种处理:

- **服务在 NAS / 常开主机**(NAS 部署):NAS 一般走有线、MAC 不变,**去路由器给它的 MAC 绑定一个固定 IP(DHCP 保留地址),或在 NAS 上设静态 IP**。绑一次就稳,最省心。
- **服务在 Mac**:Mac 的 IP 老变,**主因是 Apple『私有 Wi-Fi 地址』(MAC 随机化)**——默认「轮替」,Mac 每隔一阵换个随机 MAC,路由器按 MAC 记租约,MAC 一变 IP 跟着变。**根治:系统设置 → Wi-Fi → 当前网络「详细信息…」→「私有 Wi-Fi 地址」从「轮替」改成「固定」**(想更稳再去路由器绑 IP,或在 TCP/IP 里设手动 IP)。
  - ❌ 别只靠路由器绑 MAC:只要「私有 Wi-Fi 地址」还是「轮替」,MAC 一直变,绑了也没用——必须先改「固定」。
- **IP 真的变了**:重跑 `install.sh`(或设置页那条 Kindle 刷机命令),`SERVER_URL` 换成新地址即可。
- 注:旧版那个 `.local`(mDNS)备用地址已移除——它只对"服务跑在本机"成立(服务在 NAS 时算的是本机名,是错的),且主流越狱 Kindle(busybox)根本解析不了 `.local`。

**屏幕分辨率(机型)**:设置网页「服务」里有 **Kindle 机型** 下拉,选你的型号(基础版 6″/Paperwhite 3-4/PW5/PW12·Oasis/Scribe),服务端就按该机型原生分辨率出清晰图——高 PPI 机型不再被放大糊字。
- 原理:风格只按基准画布 **横屏 800×600** 设计,渲染时用 Chrome `--force-device-scale-factor` 把同一份布局**矢量放大**到目标分辨率(字体/线条放大依旧锐利,CSS 零改动)。详见 `docs/multi-resolution-spec.md`。
- 6″ 基础版选第一个即可(=现状,行为不变)。不确定型号:机器背面或「设置→设备信息」。
- 列表没有你的机型 → 选「自定义」,手填**横屏分辨率**(= 竖屏宽高对调,如竖屏 1236×1648 的 PW5 填宽 1648、高 1236)。
- 极少数非 4:3 机型:等比缩放 + 白底居中(letterbox),不裁切不变形;要像素级铺满需风格层单独出变体(P2)。
- Kindle 端 `fbink` 按图实际尺寸贴屏,服务端出原生分辨率即严丝合缝,**无需改 Kindle 端**。

## 四、故障排查

| 现象 | 排查 |
|---|---|
| 渲染失败/白屏 | 确认装了 Chrome/Chromium;或设 `CHROME_BIN` 指向可执行文件 |
| 中文显示成方块 | 装中文字体(Linux:`fonts-noto-cjk`;Mac 自带苹方,一般无需) |
| 连不上 Kindle | 跑 `detect.sh`;确认越狱+USBNetwork+数据线;默认 IP `192.168.15.244`。Windows 上把 Kindle 认成磁盘=USBNetwork 没开(在 Kindle 上开)或缺 RNDIS 驱动;也可改走 WiFi(填 Kindle 的 WiFi IP) |
| **看板运行中连不上(SSH refused / 插 USB 不进 U 盘 / `detect.sh` 看不到设备)** | 看板占屏会把系统界面连同 USB gadget、SSH 一起关掉,所以**运行中**连不上属正常(不是线/Mac 的问题)。装了新版(`start.sh` 自启 dropbear)后看板跑着 SSH 仍常开;若 Kindle 还是旧版,用 `install.sh --wait` 抓**重启开机窗口**刷上新版,或走逃生舱 |
| Kindle/路由器重启后看板停在旧画面 | 新版 `start.sh` 有 WiFi 自愈(`ensure_wifi` 关开无线、强制重新 DHCP 拿 IP),通常自动恢复;没恢复就**长按电源重启 Kindle**(系统重连 WiFi 即恢复)。旧版无自愈,装新版根治 |
| **看板占屏又连不上 Kindle(像变砖)** | 🛟 逃生舱:把 Kindle 插任意电脑(默认 U 盘模式,**不需要 USBNetwork/WiFi**),在盘根目录新建空文件 `dashboard.off`,重启 Kindle 即回正常界面;删掉该文件恢复看板。`start.sh` 开机先查这个文件 |
| Kindle 不刷屏 | 缺 `fbink`,通过 KUAL/越狱工具安装 |
| Kindle 时间冻结(Docker) | compose 加 `init: true`(已内建);本机直跑无此问题 |
| 设备页空 | 确认机器已配置且采集成功;push 设备需 agent 已上报 |
| Mac 存储比"关于本机→储存"略小几 G | 正常。macOS 是 APFS、一块盘多卷共享空间,看板取数据卷的实际 Used(与系统口径一致);系统还会额外扣掉「可清除空间」(TimeMachine 本地快照/缓存等),那个精确值 `df` 命令拿不到,所以可能差几 G。(若显示成 ~12G 那是读错卷的老 bug,升级到最新即修) |

## 五、验证状态(诚实清单)

**已自动化测试(42 项,`python3 -m pytest tests/ -q`)**:
- 配置 schema/加载/校验/脱敏保存、数据契约、数据整合
- 渲染管线真实出图(降级 + 真实数据)、风格调度
- Linux 本机采集端到端、主服务全部 API、设置页与实时预览(真机 chrome 截图验证)

**待真机验证**:
- macOS / Windows 采集脚本(`collect_macos.sh` / `collect_windows.ps1`)
- Mac launchd 安装(`installers/macos/`)
- Kindle 识别/安装/卸载全流程(`installers/kindle/`,需真机 Kindle)
