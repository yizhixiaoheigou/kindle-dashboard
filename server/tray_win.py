"""Windows 系统托盘 App:图标常驻 + 看板服务监工 + 控制菜单。

对位 macOS 的 server/menubar.py,但**进程模型不同**:
  - Mac:菜单栏 + launchd 服务(两个由系统托管的进程)。
  - Windows:托盘进程**自己拉起并守护**看板服务子进程(`exe --server`)。
    托盘菜单「退出」= 连服务子进程一起收;「开机自启」= 写注册表 Run 键拉起托盘 exe。

纯托盘、无主窗口(双击进托盘、叉掉到托盘、退出才停服务)。
弹窗用 tkinter(stdlib,免额外依赖);图标用 Pillow 现画(与 menubar 同款)。
"""
import os
import sys
import subprocess
import threading
import time
import webbrowser
import urllib.request

import pystray
from PIL import Image, ImageDraw

from server import updater

# 起子进程不弹黑色 cmd 窗(Windows 专用 flag)。
_CREATE_NO_WINDOW = 0x08000000

GH_OWNER, GH_REPO = "yizhixiaoheigou", "kindle-dashboard"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "MoshuiDesktop"

CONFIG_PATH = os.environ.get("KINDLE_CONFIG") or os.path.expanduser(
    "~/.config/kindle-dashboard/config.yaml")


def _resource_root():
    """打包后(PyInstaller onefile)资源在 _MEIPASS;开发时是仓库根。
    用于定位 installers/kindle/*.ps1 等随包资源。"""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return base
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


REPO = _resource_root()
KINDLE_DIR = os.path.join(REPO, "installers", "kindle")

# 菜单文案双语(zh/en),与 menubar.py 同口径(Windows 形态略有取舍)。
MENU = {
    "zh": {
        "status_running": "状态: 运行中",
        "status_stopped": "状态: 已停",
        "open_setup": "打开设置页",
        "restart": "重启服务",
        "autostart": "开机自启",
        "language": "语言 / Language",
        "lang_zh": "中文",
        "lang_en": "English",
        "check_update": "检查更新",
        "flash_kindle": "刷入 Kindle…",
        "unflash_kindle": "退出 Kindle…",
        "uninstall": "卸载(关闭自启并退出)",
        "quit": "退出",
        "quit_ask": "你想怎么退出?\n\n「是」= 退出看板服务和托盘图标(Kindle/平板将无法取图)\n「否」= 只退出托盘图标,看板服务继续在后台运行\n「取消」= 不退出",
        "title": "墨水桌面看板",
        "up_to_date": "已是最新版({v})。",
        "update_avail": "发现新版 {latest}(当前 {cur})。点「确定」打开下载页,下载新版 exe 覆盖运行即可。",
        "update_fail": "检查更新失败:{err}",
        "lang_switched": "语言已切换为 {lang}。无需重启,看板与设置页会在下一轮刷新后(最多约30秒)自动用新语言。",
        "flash_usb_or_wifi": "选择连接方式:\n\n「是」= USB(需以管理员运行,默认 192.168.15.244)\n「否」= WiFi(填 Kindle 的 WiFi IP)",
        "flash_ip_wifi": "请输入 Kindle 的 WiFi IP:",
        "flash_interval": "刷新间隔(秒):",
        "flash_confirm": "即将把看板刷入 Kindle({ip})。\n接下来可能要求输入 Kindle 的 SSH 密码(越狱默认 mario)。\n前提:Kindle 已越狱并开启 USBNetwork/SSH。继续?",
        "flash_running": "正在刷入 Kindle,请在弹出的 PowerShell 窗口里按提示操作…",
        "flash_done": "刷入流程已结束,请看 PowerShell 窗口的结果。",
        "unflash_ip": "请输入 Kindle 的 IP:",
        "unflash_confirm": "确定把 Kindle({ip})还原成正常界面?",
        "no_ssh": "没找到 Windows 自带的 ssh/scp。请到「设置 → 应用 → 可选功能 → 添加『OpenSSH 客户端』」后重试。",
        "uninstall_confirm": "将关闭开机自启、停止看板服务并退出托盘。\n(配置保留在 ~/.config;已刷过的 Kindle 不会自动还原)\n继续?",
    },
    "en": {
        "status_running": "Status: running",
        "status_stopped": "Status: stopped",
        "open_setup": "Open settings",
        "restart": "Restart service",
        "autostart": "Start at login",
        "language": "语言 / Language",
        "lang_zh": "中文",
        "lang_en": "English",
        "check_update": "Check for updates",
        "flash_kindle": "Flash Kindle…",
        "unflash_kindle": "Reset Kindle…",
        "uninstall": "Uninstall (disable autostart & quit)",
        "quit": "Quit",
        "quit_ask": "How do you want to quit?\n\nYes = Stop the service and the tray icon (devices can no longer fetch images)\nNo = Close the tray icon only; the dashboard service keeps running\nCancel = Don't quit",
        "title": "Moshui Dashboard",
        "up_to_date": "You're up to date ({v}).",
        "update_avail": "New version {latest} (current {cur}). Click OK to open the download page; download the new exe and run it.",
        "update_fail": "Update check failed: {err}",
        "lang_switched": "Language switched to {lang}. No restart needed; the dashboard and settings page apply it on the next refresh (up to ~30s).",
        "flash_usb_or_wifi": "Connection:\n\nYes = USB (run as admin, default 192.168.15.244)\nNo = WiFi (enter the Kindle WiFi IP)",
        "flash_ip_wifi": "Enter the Kindle WiFi IP:",
        "flash_interval": "Refresh interval (seconds):",
        "flash_confirm": "About to flash the dashboard to Kindle ({ip}).\nYou may be asked for the Kindle SSH password (jailbreak default: mario).\nContinue?",
        "flash_running": "Flashing Kindle; follow the prompts in the PowerShell window…",
        "flash_done": "Flash flow finished; see the PowerShell window for the result.",
        "unflash_ip": "Enter the Kindle IP:",
        "unflash_confirm": "Reset Kindle ({ip}) back to the normal UI?",
        "no_ssh": "Windows OpenSSH client (ssh/scp) not found. Add it via Settings → Apps → Optional features → OpenSSH Client, then retry.",
        "uninstall_confirm": "This disables autostart, stops the service, and quits.\n(Config kept in ~/.config; a flashed Kindle is not auto-reset)\nContinue?",
    },
}


# ---------- 配置读写 ----------
def _read_config():
    try:
        import yaml
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _language():
    lang = (_read_config().get("server", {}) or {}).get("language", "zh")
    return lang if lang in MENU else "zh"


def _set_language(lang):
    import yaml
    cfg = _read_config()
    cfg.setdefault("server", {})["language"] = lang
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)


def _port():
    try:
        return int((_read_config().get("server", {}) or {}).get("port", 8585))
    except Exception:
        return 8585


def _token():
    try:
        return (_read_config().get("server", {}) or {}).get("access_token", "") or ""
    except Exception:
        return ""


def _get_kindle(key, default=""):
    return (_read_config().get("kindle", {}) or {}).get(key, default)


def _set_kindle(key, val):
    try:
        import yaml
        cfg = _read_config()
        cfg.setdefault("kindle", {})[key] = val
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
    except Exception:
        pass


# ---------- 开机自启(注册表 HKCU\...\Run,无需管理员) ----------
def _launch_command():
    """开机自启 / 重启服务用的"启动托盘"命令字符串。
    打包后 = exe 自身;开发时 = pythonw -m server.win_entry。"""
    if getattr(sys, "frozen", False):
        return '"%s"' % sys.executable
    pyw = sys.executable
    return '"%s" -m server.win_entry' % pyw


def _autostart_enabled():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            val, _ = winreg.QueryValueEx(k, RUN_VALUE)
            return bool(val)
    except Exception:
        return False


def _set_autostart(enabled):
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
        if enabled:
            winreg.SetValueEx(k, RUN_VALUE, 0, winreg.REG_SZ, _launch_command())
        else:
            try:
                winreg.DeleteValue(k, RUN_VALUE)
            except FileNotFoundError:
                pass


# ---------- 看板服务子进程监工 ----------
def _service_cmd():
    if getattr(sys, "frozen", False):
        return [sys.executable, "--server"]
    return [sys.executable, "-m", "server.win_entry", "--server"]


# ---------- 图标(Pillow 现画,与 menubar 同款 Kindle 信息块) ----------
def _make_icon():
    size, scale = 32, 8
    img = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # 托盘背景常是浅色,用深墨色描边/填充保证可见。
    ink = (30, 30, 30, 255)

    def box(values):
        return tuple(int(round(v * scale)) for v in values)

    def px(value):
        return int(round(value * scale))

    d.rounded_rectangle(box((5, 3, 27, 29)), radius=px(4), outline=ink, width=px(2.4))
    d.rounded_rectangle(box((9, 8, 23, 13)), radius=px(1.5), fill=ink)
    d.rounded_rectangle(box((9, 16, 15, 21.5)), radius=px(1.2), fill=ink)
    d.rounded_rectangle(box((17, 16, 23, 21.5)), radius=px(1.2), fill=ink)
    d.rounded_rectangle(box((13, 25.5, 19, 27)), radius=px(0.8), fill=ink)
    resampling = getattr(Image, "Resampling", Image).LANCZOS
    return img.resize((size, size), resampling)


# ---------- 弹窗 ----------
def _dialog(kind, message, **kw):
    """info / yesno 用 Win32 原生 MessageBoxW(ctypes,无事件循环,绝不与托盘消息泵打架);
    askstring(要文本输入)用 tkinter。kind: 'info' | 'yesno' | 'askstring'。"""
    title = kw.get("title", MENU[_language()]["title"])
    if kind in ("info", "yesno"):
        import ctypes
        MB_TOPMOST = 0x00040000
        MB_SETFG = 0x00010000
        if kind == "info":
            ctypes.windll.user32.MessageBoxW(0, str(message), str(title),
                                             0x40 | MB_TOPMOST | MB_SETFG)   # OK + info 图标
            return True
        # YesNo + 问号图标;IDYES==6
        r = ctypes.windll.user32.MessageBoxW(0, str(message), str(title),
                                             0x24 | MB_TOPMOST | MB_SETFG)
        return r == 6
    if kind == "yesnocancel":
        import ctypes
        MB_TOPMOST = 0x00040000
        MB_SETFG = 0x00010000
        # MB_YESNOCANCEL(0x03) | MB_ICONQUESTION(0x20);IDYES=6 IDNO=7 IDCANCEL=2
        r = ctypes.windll.user32.MessageBoxW(0, str(message), str(title),
                                             0x23 | MB_TOPMOST | MB_SETFG)
        return {6: "yes", 7: "no", 2: "cancel"}.get(r, "cancel")
    if kind == "askstring":
        import tkinter as tk
        from tkinter import simpledialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            return simpledialog.askstring(title, message,
                                          initialvalue=kw.get("default", ""), parent=root)
        finally:
            try:
                root.destroy()
            except Exception:
                pass


class TrayApp:
    def __init__(self):
        self.lang = _language()
        self.proc = None                 # 看板服务子进程
        self.icon = pystray.Icon("MoshuiDesktop", _make_icon(),
                                 MENU[self.lang]["title"], menu=self._build_menu())

    # ----- 服务监工 -----
    def _alive(self):
        try:
            with urllib.request.urlopen(
                    "http://127.0.0.1:%d/health" % _port(), timeout=2) as r:
                return b'"status":"ok"' in r.read()
        except Exception:
            return False

    def _start_service(self):
        if self.proc and self.proc.poll() is None:
            return
        # 端口已有服务在答(比如上次选了"只退托盘"、服务还在后台跑)→ 别再起一个抢 8585。
        if self._alive():
            return
        self.proc = subprocess.Popen(_service_cmd(), creationflags=_CREATE_NO_WINDOW,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _stop_service(self):
        if not self.proc:
            return
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)],
                           capture_output=True, timeout=10, creationflags=_CREATE_NO_WINDOW)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        self.proc = None

    def _restart_service(self, icon=None, item=None):
        self._stop_service()
        time.sleep(0.5)
        self._start_service()
        self._refresh_menu()

    def _supervise_loop(self):
        """守护线程:服务子进程意外退出就自动拉起;5 秒刷新一次菜单状态行。"""
        while True:
            try:
                if (self.proc is None or self.proc.poll() is not None) and not self._alive():
                    self._start_service()
            except Exception:
                pass
            self._refresh_menu()
            time.sleep(5)

    def _refresh_menu(self):
        try:
            self.icon.update_menu()
        except Exception:
            pass

    # ----- 菜单 -----
    def _t(self):
        return MENU[self.lang]

    def _status_text(self, _item):
        return self._t()["status_running"] if self._alive() else self._t()["status_stopped"]

    def _build_menu(self):
        def item(key, cb, **kw):
            return pystray.MenuItem(lambda i: self._t()[key], cb, **kw)
        lang_sub = pystray.Menu(
            pystray.MenuItem(lambda i: self._t()["lang_zh"], lambda icon=None, item=None: self._set_lang("zh"),
                             checked=lambda i: self.lang == "zh", radio=True),
            pystray.MenuItem(lambda i: self._t()["lang_en"], lambda icon=None, item=None: self._set_lang("en"),
                             checked=lambda i: self.lang == "en", radio=True),
        )
        return pystray.Menu(
            pystray.MenuItem(self._status_text, None, enabled=False),
            pystray.Menu.SEPARATOR,
            # default=True:左键单击托盘图标触发它(pystray 默认只有右键出菜单,
            # 左键调"默认项";没默认项时左键无反应)。左键 = 打开设置页,最常用。
            item("open_setup", self._open_setup, default=True),
            item("restart", self._restart_service),
            pystray.MenuItem(lambda i: self._t()["autostart"], self._toggle_autostart,
                             checked=lambda i: _autostart_enabled()),
            pystray.MenuItem(lambda i: self._t()["language"], lang_sub),
            pystray.Menu.SEPARATOR,
            item("flash_kindle", self._flash_kindle),
            item("unflash_kindle", self._unflash_kindle),
            pystray.Menu.SEPARATOR,
            item("check_update", self._check_update),
            item("uninstall", self._uninstall),
            item("quit", self._quit),
        )

    # ----- 回调 -----
    def _open_setup(self, icon=None, item=None):
        tok = _token()
        q = ("?token=" + tok) if tok else ""
        webbrowser.open("http://127.0.0.1:%d/setup%s" % (_port(), q))

    def _toggle_autostart(self, icon=None, item=None):
        try:
            _set_autostart(not _autostart_enabled())
        except Exception as e:
            _dialog("info", str(e))
        self._refresh_menu()

    def _set_lang(self, lang):
        try:
            _set_language(lang)
        except Exception as e:
            _dialog("info", str(e))
            return
        self.lang = lang
        # 不重启服务!配置按文件 mtime 热重载(loader.maybe_reload),看板/设置页下一轮渲染
        # 自动用新语言。重启会让服务有几秒离线窗口(设置页打不开)——那才是 bug。
        # 托盘自己的菜单语言靠 self.lang + 下面 refresh 更新。
        _dialog("info", self._t()["lang_switched"].format(lang=self._t()["lang_%s" % lang]))
        self._refresh_menu()

    def _check_update(self, icon=None, item=None):
        t = self._t()
        cur = updater.installed_version(REPO)
        try:
            info = updater.check_release(GH_OWNER, GH_REPO, current=cur, asset_suffix=".exe")
        except Exception as e:
            _dialog("info", t["update_fail"].format(err=str(e)))
            return
        if not info.get("ok"):
            _dialog("info", t["update_fail"].format(err=info.get("error", "")))
            return
        if not info.get("newer"):
            _dialog("info", t["up_to_date"].format(v=cur))
            return
        if _dialog("yesno", t["update_avail"].format(latest=info.get("latest", "?"), cur=cur)):
            webbrowser.open(info.get("url") or info.get("asset_url") or "")

    def _have_ssh(self):
        import shutil
        return bool(shutil.which("ssh") and shutil.which("scp"))

    def _run_ps1(self, script, args):
        """在新的 PowerShell 窗口里跑 Kindle 脚本(刷机要交互输 SSH 密码,给用户可见窗口最稳)。"""
        path = os.path.join(KINDLE_DIR, script)
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", path] + args
        subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)

    def _flash_kindle(self, icon=None, item=None):
        t = self._t()
        if not self._have_ssh():
            _dialog("info", t["no_ssh"])
            return
        usb = _dialog("yesno", t["flash_usb_or_wifi"])
        if usb:
            ip = "192.168.15.244"
        else:
            ip = _dialog("askstring", t["flash_ip_wifi"], default=_get_kindle("last_ip", "192.168."))
            if not ip:
                return
        interval = _dialog("askstring", t["flash_interval"],
                           default=str(_get_kindle("last_interval", "20")))
        if not interval:
            return
        if not _dialog("yesno", t["flash_confirm"].format(ip=ip)):
            return
        _set_kindle("last_ip", ip)
        _set_kindle("last_interval", interval)
        args = ["-KindleIp", ip, "-Interval", str(interval)]
        self._run_ps1("install.ps1", args)
        _dialog("info", t["flash_running"])

    def _unflash_kindle(self, icon=None, item=None):
        t = self._t()
        if not self._have_ssh():
            _dialog("info", t["no_ssh"])
            return
        ip = _dialog("askstring", t["unflash_ip"], default=_get_kindle("last_ip", "192.168.15.244"))
        if not ip:
            return
        if not _dialog("yesno", t["unflash_confirm"].format(ip=ip)):
            return
        self._run_ps1("uninstall.ps1", ["-KindleIp", ip])
        _dialog("info", t["flash_done"])

    def _uninstall(self, icon=None, item=None):
        if not _dialog("yesno", self._t()["uninstall_confirm"]):
            return
        try:
            _set_autostart(False)
        except Exception:
            pass
        self._shutdown(stop_service=True)   # 卸载=连服务一起收,不再二次确认

    def _shutdown(self, stop_service):
        """收尾退出。stop_service=True 连看板服务子进程一起杀;False 只撤托盘、服务后台继续。
        (Windows 子进程默认不随父进程退出,所以"只退托盘"时服务能独立活着。)"""
        if stop_service:
            self._stop_service()
        try:
            self.icon.stop()
        except Exception:
            pass

    def _quit(self, icon=None, item=None):
        choice = _dialog("yesnocancel", self._t()["quit_ask"])
        if choice == "yes":
            self._shutdown(stop_service=True)    # 服务 + 托盘都退
        elif choice == "no":
            self._shutdown(stop_service=False)   # 只退托盘,服务继续后台跑
        # cancel:什么都不做

    # ----- 启动 -----
    def _maybe_first_run_autostart(self):
        """首次启动自动打开开机自启(看板本就是常开服务,装一次=开机即跑)。
        只做一次:写个 marker,之后尊重用户在菜单里的开/关,不再强制回写。
        仅对打包后的 exe 生效(开发时 -m 启动的自启命令脆弱,不自动设)。"""
        if not getattr(sys, "frozen", False):
            return
        appdata = os.environ.get("APPDATA") or os.path.expanduser(r"~\AppData\Roaming")
        marker = os.path.join(appdata, "墨水桌面看板", ".autostart_initialized")
        if os.path.exists(marker):
            return
        try:
            _set_autostart(True)
        except Exception:
            pass
        try:
            os.makedirs(os.path.dirname(marker), exist_ok=True)
            with open(marker, "w", encoding="utf-8") as f:
                f.write("1")
        except Exception:
            pass

    def run(self):
        self._maybe_first_run_autostart()
        self._start_service()
        threading.Thread(target=self._supervise_loop, daemon=True).start()
        self.icon.run()                  # 阻塞:托盘事件循环


_SINGLETON_HANDLE = None    # 命名互斥句柄,全程持有(别被 GC 关掉,否则单例失效)


def _acquire_singleton():
    """单实例保护:开机自启 + 用户又双击 → 两个托盘 + 两个服务抢 8585 端口。
    用命名互斥量,已存在则返回 False(本进程应退出)。"""
    global _SINGLETON_HANDLE
    try:
        import ctypes
        _SINGLETON_HANDLE = ctypes.windll.kernel32.CreateMutexW(None, False, "MoshuiDesktopTraySingleton")
        return ctypes.windll.kernel32.GetLastError() != 183   # ERROR_ALREADY_EXISTS
    except Exception:
        return True     # 拿不到就别拦着启动


def main():
    if not _acquire_singleton():
        return          # 已有一个托盘在跑,本次安静退出
    TrayApp().run()


if __name__ == "__main__":
    main()
