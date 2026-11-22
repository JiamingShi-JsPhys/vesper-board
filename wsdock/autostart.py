"""开机自启：Windows 用 Run 注册表，macOS 用 LaunchAgent，Linux 用 .desktop。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_ID = "com.vesperboard.app"
APP_LABEL = "Vesper Board"


def _argv() -> list[str]:
    """打包后就是 exe 自己；从源码跑就是 python(w) + main.py。"""
    exe = Path(sys.executable)
    if not getattr(sys, "frozen", False):
        pythonw = exe.with_name("pythonw.exe")
        if pythonw.exists():
            exe = pythonw
        main_py = Path(__file__).resolve().parent.parent / "main.py"
        return [str(exe), str(main_py)]
    return [str(exe)]


# ------------------------------------------------------------------ Windows
def _win_key():
    import winreg
    return winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                          r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                          winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE)


def _win_is_enabled() -> bool:
    import winreg
    try:
        with _win_key() as key:
            value, _ = winreg.QueryValueEx(key, "VesperBoard")
            return bool(value)
    except OSError:
        return False


def _win_set(enabled: bool) -> None:
    import winreg
    with _win_key() as key:
        if enabled:
            cmd = " ".join('"%s"' % a for a in _argv())
            winreg.SetValueEx(key, "VesperBoard", 0, winreg.REG_SZ, cmd)
        else:
            try:
                winreg.DeleteValue(key, "VesperBoard")
            except FileNotFoundError:
                pass


# -------------------------------------------------------------------- macOS
def _mac_plist() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / ("%s.plist" % APP_ID)


PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{label}</string>
  <key>ProgramArguments</key>
  <array>{args}</array>
  <key>RunAtLoad</key><true/>
  <key>ProcessType</key><string>Interactive</string>
</dict>
</plist>
"""


def _mac_is_enabled() -> bool:
    return _mac_plist().exists()


def _mac_set(enabled: bool) -> None:
    path = _mac_plist()
    if not enabled:
        try:
            path.unlink()
        except OSError:
            pass
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    args = "".join("<string>%s</string>" % a for a in _argv())
    path.write_text(PLIST.format(label=APP_ID, args=args), encoding="utf-8")


# -------------------------------------------------------------------- Linux
def _linux_desktop() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "autostart" / "vesper-board.desktop"


def _linux_is_enabled() -> bool:
    return _linux_desktop().exists()


def _linux_set(enabled: bool) -> None:
    path = _linux_desktop()
    if not enabled:
        try:
            path.unlink()
        except OSError:
            pass
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    exec_line = " ".join('"%s"' % a for a in _argv())
    path.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=%s\n"
        "Exec=%s\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n" % (APP_LABEL, exec_line),
        encoding="utf-8",
    )


# ---------------------------------------------------------------- dispatch
def is_enabled() -> bool:
    try:
        if sys.platform.startswith("win"):
            return _win_is_enabled()
        if sys.platform == "darwin":
            return _mac_is_enabled()
        return _linux_is_enabled()
    except OSError:
        return False


def set_enabled(enabled: bool) -> None:
    if sys.platform.startswith("win"):
        _win_set(enabled)
    elif sys.platform == "darwin":
        _mac_set(enabled)
    else:
        _linux_set(enabled)
