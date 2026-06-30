r"""Windows 单 EXE 入口:一个 exe 两个角色,靠参数分流。

  MoshuiDesktop.exe            → 角色A:托盘监工(默认,server.tray_win)
  MoshuiDesktop.exe --server   → 角色B:看板服务(server.run,uvicorn)

PyInstaller onefile 打包后 sys.executable = exe 自身,托盘监工用
`[sys.executable, "--server"]` 拉起服务子进程(见 tray_win._service_cmd)。

数据目录默认落 %APPDATA%\墨水桌面看板\data(onefile 临时解压目录每次都变,
绝不能把数据/缓存写那里);配置仍沿用 ~/.config/kindle-dashboard(跨平台不丢)。
"""
import os
import sys


def _default_data_dir():
    appdata = os.environ.get("APPDATA") or os.path.expanduser(r"~\AppData\Roaming")
    return os.path.join(appdata, "墨水桌面看板", "data")


def _bootstrap_env():
    # 没显式设 KINDLE_DATA_DIR 时,Windows 默认指向 %APPDATA%(可写、固定、随用户),
    # 而不是 onefile 解压出的 _MEIPASS 临时目录。
    if sys.platform == "win32" and not os.environ.get("KINDLE_DATA_DIR"):
        d = _default_data_dir()
        try:
            os.makedirs(d, exist_ok=True)
        except Exception:
            pass
        os.environ["KINDLE_DATA_DIR"] = d


def main():
    # PyInstaller onefile 防护:任一依赖若用了 multiprocessing,没有这行会让子进程重新跑整个 exe
    # (无限拉起托盘/服务)。当前不用 mp,但留作保险,无副作用。
    import multiprocessing
    multiprocessing.freeze_support()
    _bootstrap_env()
    if "--server" in sys.argv[1:]:
        from server.run import main as run_main
        run_main()
    else:
        from server.tray_win import main as tray_main
        tray_main()


if __name__ == "__main__":
    main()
