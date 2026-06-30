"""渲染管线:HTML 字符串 → 无头 Chromium 截图 → PIL 旋转/灰度 → PNG bytes。

Kindle 558 物理屏是 600×800 竖屏。看板横放在显示器下方,所以模板按横屏 800×600 设计,
渲染后旋转 90° 成 600×800 写屏(用户把 Kindle 横过来摆)。Kindle 端照常拉 600×800 图。

尺寸/旋转/灰度全部参数化(从配置 server.render_* 读),不写死。
保留老代码踩过的坑:`--no-crashpad`(防 Chromium 僵尸)、超时杀进程、产物缺失杀僵尸。
ESP32 支线已按开源方案弃用,不再搬运。
"""
import io
import os
import sys
import glob
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from dataclasses import dataclass

from PIL import Image

# psutil 仅用于 Windows 上按命令行标记精准清僵尸渲染进程(POSIX 用 pkill,不依赖它)。
# 没装就降级:Windows 无 psutil 时全局清理走"按映像名兜底",可能略宽但不报错。
try:
    import psutil
except Exception:                # pragma: no cover - 仅在未装 psutil 的环境
    psutil = None

IS_WIN = sys.platform == "win32"

# 起渲染子进程的平台参数:
#   POSIX  —— 独立会话(start_new_session),便于按进程组一刀杀。
#   Windows —— 新进程组(便于 taskkill /T 杀整棵树)+ 不弹黑色 cmd 窗(CREATE_NO_WINDOW)。
_CREATE_NO_WINDOW = 0x08000000
_CREATE_NEW_PROCESS_GROUP = 0x00000200
if IS_WIN:
    _SPAWN_KW = {"creationflags": _CREATE_NO_WINDOW | _CREATE_NEW_PROCESS_GROUP}
else:
    _SPAWN_KW = {"start_new_session": True}

_ROT = {
    0: None,
    90: Image.ROTATE_90,     # 逆时针
    180: Image.ROTATE_180,
    270: Image.ROTATE_270,   # 顺时针(默认)
}

# 渲染用的浏览器:环境相关,由安装脚本设 CHROME_BIN;否则自动探测。
# 不进 config.yaml(用户业务配置)——用户不该关心二进制路径。
# 渲染走标准 Chromium 命令行(--headless=new --screenshot),所以任何 Chromium 内核的浏览器
# (Chrome / Chromium / Edge / Brave / Vivaldi 等)都能用,无需非装 Chrome。
_CANDIDATES = [
    "/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome",
    "/snap/bin/chromium",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    # 其它 Chromium 内核浏览器:同样支持 --headless=new --screenshot,渲染效果一致。
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Vivaldi.app/Contents/MacOS/Vivaldi",
    "/usr/bin/microsoft-edge", "/usr/bin/microsoft-edge-stable",
    "/usr/bin/brave-browser", "/usr/bin/vivaldi",
]


def _win_candidates() -> list:
    """Windows 上的 Chromium 内核浏览器候选路径(按盘符/安装位置从环境变量拼,兼容非 C 盘)。
    Win10/11 自带 Edge,几乎必中;渲染只需任一内核,不挑牌子。"""
    if not IS_WIN:
        return []
    bases = [
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        os.environ.get("LOCALAPPDATA", os.path.expanduser(r"~\AppData\Local")),
    ]
    rels = [
        r"Microsoft\Edge\Application\msedge.exe",
        r"Google\Chrome\Application\chrome.exe",
        r"BraveSoftware\Brave-Browser\Application\brave.exe",
        r"Vivaldi\Application\vivaldi.exe",
        r"Chromium\Application\chrome.exe",
    ]
    out = []
    for base in bases:
        if not base:
            continue
        for rel in rels:
            out.append(os.path.join(base, rel))
    return out


def _playwright_chrome() -> str:
    """探测 playwright 自动下载的 chromium(venv 内安装,不依赖系统 Chrome)。"""
    home = os.path.expanduser("~")
    patterns = [
        home + "/Library/Caches/ms-playwright/chromium-*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium",
        home + "/.cache/ms-playwright/chromium-*/chrome-linux*/chrome",
    ]
    if IS_WIN:
        local = os.environ.get("LOCALAPPDATA", os.path.expanduser(r"~\AppData\Local"))
        patterns.append(os.path.join(local, "ms-playwright", "chromium-*", "chrome-win", "chrome.exe"))
    for pat in patterns:
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]   # 取版本号最大的那份
    return ""


def _headless_shell() -> str:
    """探测 chrome-headless-shell —— Chromium 的专用无头二进制。
    关键:macOS 上**完整 Chrome 的 `--headless=new` 会在 Dock 闪现图标**(它是真浏览器、会建平台窗口);
    chrome-headless-shell 是 //content 的轻量壳、不初始化窗口系统,**从不弹 Dock**。所以它优先级最高。
    探测:我们一键下载落地处(installers/macos/get-headless-shell.sh)+ puppeteer/playwright 缓存 + PATH。"""
    home = os.path.expanduser("~")
    patterns = [
        home + "/Library/Application Support/墨水桌面看板/chrome-headless-shell/*/chrome-headless-shell",
        home + "/.cache/puppeteer/chrome-headless-shell/*/chrome-headless-shell-*/chrome-headless-shell",
        home + "/Library/Caches/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-mac*/chrome-headless-shell",
        home + "/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux*/chrome-headless-shell",
    ]
    if IS_WIN:
        # Windows 兜底下载落地处(get-headless-shell.ps1)+ puppeteer/playwright 缓存。
        appdata = os.environ.get("APPDATA", os.path.expanduser(r"~\AppData\Roaming"))
        local = os.environ.get("LOCALAPPDATA", os.path.expanduser(r"~\AppData\Local"))
        patterns = [
            os.path.join(appdata, "墨水桌面看板", "chrome-headless-shell", "*", "chrome-headless-shell.exe"),
            os.path.join(local, "puppeteer", "chrome-headless-shell", "*", "chrome-headless-shell-*", "chrome-headless-shell.exe"),
            os.path.join(local, "ms-playwright", "chromium_headless_shell-*", "chrome-headless-shell-win*", "chrome-headless-shell.exe"),
        ]
    for pat in patterns:
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return shutil.which("chrome-headless-shell") or ""


def is_headless_shell(path: str) -> bool:
    """该二进制是不是 chrome-headless-shell(决定渲染要不要加 `--headless=new`:shell 本身就是无头,不能加)。"""
    return "headless-shell" in os.path.basename(path or "").lower()


def find_chrome() -> str:
    """定位渲染用浏览器。优先级:CHROME_BIN → **chrome-headless-shell(不弹 Dock)** →
    系统 Chrome/Chromium/Edge/Brave/Vivaldi → playwright 自带 chromium。找不到返回 ""。"""
    env = os.environ.get("CHROME_BIN")
    if env and os.path.exists(env):
        return env
    shell = _headless_shell()    # 优先无头壳:macOS 上它不弹 Dock
    if shell:
        return shell
    names = ["chromium", "chromium-browser", "google-chrome", "google-chrome-stable",
             "microsoft-edge", "microsoft-edge-stable", "brave-browser", "vivaldi"]
    if IS_WIN:
        # Windows 上浏览器一般不在 PATH,which 多半空;真正命中的是下面 _win_candidates 的固定路径。
        names = ["msedge", "chrome", "brave", "vivaldi", "chromium"]
    for name in names:
        p = shutil.which(name)
        if p:
            return p
    for p in (_win_candidates() + _CANDIDATES):
        if os.path.exists(p):
            return p
    return _playwright_chrome()


# 基准画布(横屏):所有风格只针对它设计,常量,不开放给用户改。
# 改它 = 所有风格要重画。多分辨率靠 device-scale-factor 等比放大,不动 CSS。
BASE_W, BASE_H = 800, 600


@dataclass
class RenderConfig:
    # width/height = 最终输出(用户 Kindle 横屏物理分辨率);base_* = 风格设计的逻辑画布
    width: int = BASE_W
    height: int = BASE_H
    base_width: int = BASE_W
    base_height: int = BASE_H
    rotate: int = 270
    grayscale: bool = True
    timeout: int = 30
    chrome_bin: str = ""

    @classmethod
    def from_config(cls, cfg: dict) -> "RenderConfig":
        s = (cfg or {}).get("server", {})
        # 机型预设→分辨率的映射是 schema 里的唯一数据源(局部导入避免包初始化耦合)
        from server.config.schema import resolve_render_size
        w, h = resolve_render_size(s)
        return cls(
            width=int(w),
            height=int(h),
            base_width=BASE_W,
            base_height=BASE_H,
            rotate=int(s.get("render_rotate", 270)),
            grayscale=bool(s.get("render_grayscale", True)),
            chrome_bin=find_chrome(),
        )


# 渲染串行化:同一时刻只允许一个 Chrome 在跑。
# 关键修复 —— 预览(网页随手点)和主循环(每 render_interval 一轮 5 页)原先各自并发起 Chrome,
# 在低核机器(如 MacBook Air)上几个 Chrome 抢 CPU → 每个都卡过 30s 超时 → 触发清理 → 误杀彼此 → 雪崩。
# 串行化后每次渲染独占资源(基准画布 1~2s 出图),既消除竞态也根除"全部失败"雪崩。
_RENDER_MUTEX = threading.Lock()


def _pkill(pattern: str) -> None:
    """按命令行标记杀进程(只动带该标记的渲染 Chrome,绝不碰本服务/他人进程或用户自己的浏览器)。
    POSIX 走 pkill -f;Windows 没有 pkill,用 psutil 按 cmdline 含标记精准杀(只杀我们这次渲染的那棵)。"""
    if IS_WIN:
        if psutil is None:
            return                  # 没 psutil 就不做全局清理(单次渲染已由 _kill_group 的 taskkill /T 收干净)
        for p in psutil.process_iter(["pid", "cmdline"]):
            try:
                cmd = p.info.get("cmdline") or []
                if any(pattern in (arg or "") for arg in cmd):
                    p.kill()
            except Exception:
                pass
        return
    try:
        subprocess.run(["pkill", "-9", "-f", pattern], capture_output=True, timeout=5)
    except Exception:
        pass


def _kill_group(proc) -> None:
    """整组杀掉一次渲染:主进程 + 它派生的全部 Chrome 子进程一起清。
    超时时一刀清干净,既释放渲染锁,又不留继承管道的子进程把后续渲染拖死。
    POSIX:Popen 用 start_new_session → 按进程组 killpg。
    Windows:Popen 用 CREATE_NEW_PROCESS_GROUP → taskkill /T 连子进程树整棵杀(psutil 兜底子进程)。"""
    if IS_WIN:
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True, timeout=5,
                           creationflags=_CREATE_NO_WINDOW)
        except Exception:
            pass
        if psutil is not None:       # 兜底:taskkill 没覆盖到的子进程再扫一遍
            try:
                parent = psutil.Process(proc.pid)
                for child in parent.children(recursive=True):
                    try:
                        child.kill()
                    except Exception:
                        pass
            except Exception:
                pass
    else:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            pass
    try:
        proc.wait(timeout=5)        # 回收僵尸,别留 defunct
    except Exception:
        pass


def kill_stale_chrome() -> None:
    """全局清理本服务**所有**渲染 Chrome(命令行带 kdash-render 标记)。
    仅用于:服务启动时清上一轮残留、以及主循环整轮全失败的兜底扫除。
    单次渲染超时只杀自己那次(见 _shot_to_image 的 _pkill(td)),不走这里,避免误伤。"""
    _pkill("kdash-render")


def _shot_to_image(html: str, rc: RenderConfig) -> Image.Image:
    chrome = rc.chrome_bin or find_chrome()
    if not chrome:
        raise RuntimeError("未找到 Chrome/Chromium,请装 chromium 或设置 CHROME_BIN")
    # 临时目录带 kdash-render 前缀:chrome 命令行会含此路径,kill_stale_chrome 据此只杀自己的渲染进程。
    with tempfile.TemporaryDirectory(prefix="kdash-render-") as td:
        html_path = os.path.join(td, "page.html")
        png_path = os.path.join(td, "out.png")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        # 窗口永远是基准画布(CSS 像素),用 device-scale-factor 把同一份布局矢量放大到
        # 目标物理分辨率 —— 字体/斜线矢量放大依旧锐利,模板 CSS 零改动。
        # scale 取宽/高比的较小值:4:3 机型两者相等;非 4:3 取小值=等比不裁切,短边留白(letterbox)。
        bw = rc.base_width or BASE_W
        bh = rc.base_height or BASE_H
        scale = min(rc.width / bw, rc.height / bh)
        if scale <= 0:
            scale = 1.0
        # macOS Dock 抖动根因(2026-06-24 纠正):**完整 Chrome 的 `--headless=new` 是真浏览器、会建平台窗口
        # → 在 Dock 闪一下图标**(此前 CLAUDE.md 记反了)。chrome-headless-shell 本身就是无头壳、不弹 Dock,
        # 且**不接受 `--headless` flag**(它默认无头)。所以:用 shell 时不加 --headless;用完整 Chrome 才加。
        cmd = [chrome]
        if not is_headless_shell(chrome):
            cmd.append("--headless=new")
        cmd += [
            "--no-sandbox", "--disable-gpu",
            "--no-crashpad", "--disable-crash-reporter",
            "--disable-dev-shm-usage", "--hide-scrollbars",
            # 防首启卡顿/后台网络等待(全新 user-data-dir 否则会触发首启流程,在弱机上可拖到超时)
            "--no-first-run", "--no-default-browser-check",
            "--disable-background-networking", "--disable-sync",
            "--disable-default-apps", "--disable-component-update",
            "--disable-extensions", "--disable-features=Translate,OptimizationHints",
            "--mute-audio", "--metrics-recording-only",
            f"--force-device-scale-factor={scale:.4f}",
            f"--window-size={bw},{bh}",
            "--default-background-color=FFFFFFFF",
            f"--user-data-dir={os.path.join(td, 'ud')}",
            # file:// URL 必须用 as_uri():Windows 路径含盘符+反斜杠,手拼 file://C:\... 会失败。
            f"--screenshot={png_path}", Path(html_path).as_uri(),
        ]
        # 串行化:同一时刻只跑一个 Chrome(预览与主循环互不抢资源)。
        # ⚠️ 绝不能用 subprocess.run(capture_output=True, timeout=) —— Chrome 派生的渲染子进程会继承
        # stdout/stderr 管道,run() 超时后的二次 communicate() 会【永久卡在等管道关闭】,既不返回也不超时;
        # 在串行锁下这一卡就把锁占死 → 预览/主循环全堵死、看板冻屏(2026-06-08 真机踩中)。
        # 改用 Popen + 独立进程组(start_new_session)+ 丢弃输出(DEVNULL,无管道可卡);
        # 超时按整个进程组一刀杀(os.killpg),保证锁一定释放、子进程一定清。
        with _RENDER_MUTEX:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, **_SPAWN_KW)
            # ⚠️ 截图一写好就立刻收工,绝不等 Chrome 自己退出(2026-06-08 真机定位):
            # 国内/弱网下,全新 profile 的 Chrome 截完图后会被 GoogleUpdater(--wake-all)+ GCM 注册
            # 的后台联网拖住 —— 连 Google 被 GFW 拦截,SSL 握手反复失败重试,要 ~30s 才肯退出。
            # 而 --screenshot 秒级就把 png 写好了。所以轮询到 png 出现就整组杀掉,渲染 30s→~1s。
            deadline = time.time() + rc.timeout
            try:
                while time.time() < deadline:
                    if proc.poll() is not None:
                        break                                        # Chrome 自己退了
                    if os.path.exists(png_path) and os.path.getsize(png_path) > 0:
                        time.sleep(0.15)                             # 让它把 png 写完整再收
                        break
                    time.sleep(0.1)
            finally:
                _kill_group(proc)       # 无论截到没截到都整组清干净(含拖后腿的 updater 子进程)
                _pkill(td)              # 兜底:按 td 标记再扫一遍
        if not os.path.exists(png_path) or os.path.getsize(png_path) == 0:
            raise FileNotFoundError("Chromium 未产出截图(已清理本次进程,下轮自动恢复)")
        mode = "L" if rc.grayscale else "RGB"
        shot = Image.open(png_path).convert(mode)
        # 落到精确的输出尺寸:白底居中贴图。兜住两件事——非 4:3 的 letterbox 留白,
        # 以及非整数 scale 取整带来的 1~2px 误差。绝不报错(诚实降级)。
        bg = 255 if mode == "L" else (255, 255, 255)
        canvas = Image.new(mode, (rc.width, rc.height), bg)
        ox = (rc.width - shot.width) // 2
        oy = (rc.height - shot.height) // 2
        canvas.paste(shot, (ox, oy))
        return canvas


def render_html_to_png(html: str, rc: RenderConfig) -> bytes:
    """横屏 HTML → 旋转后的设备 PNG bytes(诚实失败:抛异常,由上层保留旧页)。
    失败自动重试一次 —— headless Chrome 偶发漏图/瞬时超时,重试即自愈,
    避免单次抖动让预览裂图、让该页这一轮空缺。"""
    img = None
    for attempt in range(2):
        try:
            img = _shot_to_image(html, rc)
            break
        except Exception:
            if attempt == 1:
                raise
            time.sleep(0.4)
    rot = _ROT.get(rc.rotate)
    if rot is not None:
        img = img.transpose(rot)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
