"""All on-disk locations the app uses, in one place.

Windows: %LOCALAPPDATA%\\VesperBoard
macOS:   ~/Library/Application Support/VesperBoard
Linux:   $XDG_DATA_HOME/VesperBoard（默认 ~/.local/share/VesperBoard）
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

APP_NAME = "VesperBoard"
LEGACY_NAME = "WestlakeDock"      # 改名前的数据目录，首次启动时整目录搬过来


def is_windows() -> bool:
    return sys.platform.startswith("win")


def is_macos() -> bool:
    return sys.platform == "darwin"


def _migrate_legacy(root: Path, legacy: Path) -> bool:
    """把改名前的数据目录搬过来，成功后再删掉旧的。

    先复制到临时目录再改名，复制到一半失败时不会留下半份 ``root``；
    只有完整复制成功才删除旧目录——否则旧令牌和会话会以第二份的形式
    留在磁盘上，卸载程序也管不到。
    """
    if root.exists() or not legacy.is_dir():
        return False
    staging = root.with_name(root.name + ".migrating")
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    try:
        shutil.copytree(legacy, staging)
        staging.rename(root)
    except OSError:
        shutil.rmtree(staging, ignore_errors=True)
        return False
    shutil.rmtree(legacy, ignore_errors=True)
    return True


def root_dir() -> Path:
    """数据目录的路径——只计算，不迁移、不创建。

    给单实例锁这类「还没决定能不能动磁盘」的场合用。
    """
    if is_windows():
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        return Path(base) / APP_NAME if base else Path.home() / APP_NAME
    if is_macos():
        return Path.home() / "Library" / "Application Support" / APP_NAME
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_NAME


def _harden_dir(path: Path) -> None:
    """POSIX 上把数据目录收紧到 0700。

    umask 022 建出来的目录是 0755，同机其他用户能读 archived.json / dock.log
    （课程名、作业标题）。
    """
    if os.name == "nt":
        return
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def data_dir() -> Path:
    root = root_dir()
    if root.exists():
        _harden_dir(root)
        return root

    legacy = root.parent / LEGACY_NAME
    if legacy.is_dir():
        if _migrate_legacy(root, legacy):
            _harden_dir(root)
            return root
        # 迁移失败（磁盘满、杀软锁文件……）：本次继续用旧目录，下次启动再试。
        # 这里绝不能建一个空的 root——否则下次 root.exists() 成立，迁移被永久跳过，
        # 旧目录里的令牌就成了没人用的孤儿。
        _harden_dir(legacy)
        return legacy

    root.mkdir(parents=True, exist_ok=True)
    _harden_dir(root)
    return root


def settings_file() -> Path:
    return data_dir() / "settings.json"


def canvas_token_file() -> Path:
    return data_dir() / "canvas_token.bin"


def ams_token_file() -> Path:
    return data_dir() / "ams_token.bin"


def canvas_session_file() -> Path:
    return data_dir() / "canvas_session.bin"


def ams_session_file() -> Path:
    return data_dir() / "ams_session.bin"


def cookie_map_file() -> Path:
    return data_dir() / "cookies.bin"


def pet_user_dir() -> Path:
    """用户自己导入的形象，放在这里；升级/重装不会丢。"""
    d = data_dir() / "pet"
    d.mkdir(parents=True, exist_ok=True)
    return d


def web_profile_dir() -> Path:
    d = data_dir() / "web-profile"
    d.mkdir(parents=True, exist_ok=True)
    return d


def web_cache_dir() -> Path:
    d = data_dir() / "web-cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_file() -> Path:
    return data_dir() / "dock.log"


def write_text_atomic(path: Path, text: str) -> None:
    """先写同目录临时文件再 os.replace：写到一半被杀也不会留下半个 JSON。

    临时名带 pid，并用 `"x"`（O_EXCL）打开——别人预先放好的同名符号链接
    不会被跟随，避免覆写到同用户可写的其它文件。
    """
    tmp = path.with_name("%s.%d.tmp" % (path.name, os.getpid()))
    try:
        tmp.unlink()
    except OSError:
        pass
    with open(tmp, "x", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def debug_dir() -> Path:
    d = data_dir() / "debug"
    d.mkdir(parents=True, exist_ok=True)
    return d


def bundle_dir() -> Path:
    """Where read-only assets live.

    Running from source: the repo root. Frozen: PyInstaller 6 puts data under
    `_internal/`, but `sys._MEIPASS` has pointed at either the bundle root or
    that folder depending on version — so probe for the one that actually has
    `assets/` instead of assuming.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    exe_dir = Path(sys.executable).resolve().parent
    candidates = []
    if meipass:
        candidates += [Path(meipass), Path(meipass) / "_internal"]
    candidates += [exe_dir, exe_dir / "_internal", Path(__file__).resolve().parent.parent]
    for cand in candidates:
        if (cand / "assets").is_dir():
            return cand
    return Path(meipass) if meipass else Path(__file__).resolve().parent.parent

def purge_web_dirs() -> list[Path]:
    """登录窗的 Chromium 目录里会留 favicon、页面缓存、GPU 缓存。

    cookie 本来就不落盘（NoPersistentCookies），但这些缓存里可能有页面内容，
    所以在启动和退出时都整目录删掉，下次用再建。
    """
    removed: list[Path] = []
    for name in ("web-profile", "web-cache"):
        path = data_dir() / name
        if not path.is_dir():
            continue
        try:
            shutil.rmtree(path)
            removed.append(path)
        except OSError:
            pass
    return removed


def purge_legacy_dir() -> Path | None:
    """改名前的数据目录：新目录已经存在时，旧目录里只是第二份凭据与旧日志。

    迁移只在「新目录不存在」时发生；新目录已经在了，旧目录就一定是残留，
    继续放着等于把 DPAPI 凭据和明文日志多留一份。
    """
    root = root_dir()
    legacy = root.parent / LEGACY_NAME
    if not (root.is_dir() and legacy.is_dir()):
        return None
    try:
        shutil.rmtree(legacy)
        return legacy
    except OSError:
        return None


def purge_plain_cookies() -> list[Path]:
    """旧版本把登录窗的 cookie 明文留在 web-profile 里。

    现在这个 profile 只放内存（NoPersistentCookies），但升级上来的机器上
    还留着旧的 Cookies 库——启动时清掉，避免继续摊在磁盘上。
    """
    removed: list[Path] = []
    profile = web_profile_dir()
    for rel in ("Cookies", "Cookies-journal", "Network/Cookies", "Network/Cookies-journal"):
        path = profile / rel
        if path.exists():
            try:
                path.unlink()
                removed.append(path)
            except OSError:
                pass
    return removed
