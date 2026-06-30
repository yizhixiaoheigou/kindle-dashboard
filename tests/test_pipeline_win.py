"""渲染管线跨平台分支(Windows)。在 Linux 上用 monkeypatch 模拟 win32 验证分支正确,
不真起 Chrome/进程。配套 docs/windows-app-spec.md §1。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from server.render import pipeline   # noqa: E402


def test_win_candidates_built_from_env(monkeypatch):
    """Windows 候选按环境变量(ProgramFiles 等)拼,含 Edge,兼容非 C 盘。"""
    monkeypatch.setattr(pipeline, "IS_WIN", True)
    monkeypatch.setenv("ProgramFiles", r"D:\PF")
    monkeypatch.setenv("ProgramFiles(x86)", r"D:\PF86")
    monkeypatch.setenv("LOCALAPPDATA", r"D:\Users\x\AppData\Local")
    cands = pipeline._win_candidates()
    assert any(c.endswith(r"Microsoft\Edge\Application\msedge.exe") for c in cands)
    assert any(c.startswith(r"D:\PF") for c in cands)
    # 非 win 时返回空
    monkeypatch.setattr(pipeline, "IS_WIN", False)
    assert pipeline._win_candidates() == []


def test_find_chrome_uses_win_candidates(monkeypatch):
    """模拟 Windows:PATH 里 which 全空,find_chrome 退到固定候选路径并命中存在的那个。"""
    monkeypatch.setattr(pipeline, "IS_WIN", True)
    monkeypatch.delenv("CHROME_BIN", raising=False)
    monkeypatch.setattr(pipeline, "_headless_shell", lambda: "")
    monkeypatch.setattr(pipeline.shutil, "which", lambda *_a, **_k: None)
    monkeypatch.setattr(pipeline, "_playwright_chrome", lambda: "")
    fake_edge = r"D:\PF\Microsoft\Edge\Application\msedge.exe"
    monkeypatch.setattr(pipeline, "_win_candidates", lambda: [fake_edge])
    monkeypatch.setattr(pipeline.os.path, "exists", lambda p: p == fake_edge)
    assert pipeline.find_chrome() == fake_edge


def test_kill_group_windows_uses_taskkill(monkeypatch):
    """Windows 上 _kill_group 用 taskkill /F /T,绝不调 os.killpg(POSIX 专有,Windows 会崩)。"""
    monkeypatch.setattr(pipeline, "IS_WIN", True)
    monkeypatch.setattr(pipeline, "psutil", None)        # 没 psutil 也要能跑

    calls = []
    monkeypatch.setattr(pipeline.subprocess, "run",
                        lambda cmd, **kw: calls.append(cmd))

    def _boom(*_a, **_k):
        raise AssertionError("Windows 不该调 os.killpg")
    monkeypatch.setattr(pipeline.os, "killpg", _boom, raising=False)

    class FakeProc:
        pid = 4321
        def wait(self, timeout=None):
            return 0
    pipeline._kill_group(FakeProc())
    assert calls and calls[0][:3] == ["taskkill", "/F", "/T"]
    assert str(4321) in calls[0]


def test_pkill_windows_without_psutil_is_noop(monkeypatch):
    """Windows 无 psutil 时 _pkill 安静返回(不调 pkill,那是 POSIX 命令)。"""
    monkeypatch.setattr(pipeline, "IS_WIN", True)
    monkeypatch.setattr(pipeline, "psutil", None)

    def _no_run(*_a, **_k):
        raise AssertionError("Windows 不该调 subprocess pkill")
    monkeypatch.setattr(pipeline.subprocess, "run", _no_run)
    pipeline._pkill("kdash-render")          # 不抛即通过


def test_pkill_windows_with_psutil_matches_marker(monkeypatch):
    """Windows 有 psutil 时,_pkill 只杀 cmdline 含标记的进程。"""
    monkeypatch.setattr(pipeline, "IS_WIN", True)
    killed = []

    class FakeProc:
        def __init__(self, pid, cmdline):
            self.info = {"pid": pid, "cmdline": cmdline}
            self._cmd = cmdline
            self._pid = pid
        def kill(self):
            killed.append(self._pid)

    procs = [
        FakeProc(1, ["msedge.exe", r"--user-data-dir=C:\t\kdash-render-abc\ud"]),
        FakeProc(2, ["chrome.exe", "--some-other"]),
    ]

    class FakePsutil:
        @staticmethod
        def process_iter(_attrs):
            return procs
    monkeypatch.setattr(pipeline, "psutil", FakePsutil)
    pipeline._pkill("kdash-render")
    assert killed == [1]


def test_spawn_kwargs_platform():
    """POSIX 用 start_new_session;Windows 用 creationflags(进程组+无窗口)。两者互斥,别同时出现。"""
    if pipeline.IS_WIN:
        assert "creationflags" in pipeline._SPAWN_KW
        assert "start_new_session" not in pipeline._SPAWN_KW
    else:
        assert pipeline._SPAWN_KW.get("start_new_session") is True
        assert "creationflags" not in pipeline._SPAWN_KW
