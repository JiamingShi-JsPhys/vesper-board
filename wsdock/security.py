"""Token storage that uses whatever the OS gives us.

Windows: DPAPI (`CryptProtectData`) — only the same Windows user on the same
machine can decrypt it, so a copied file is useless elsewhere.
macOS:   login keychain through `security`; a tiny marker file records that the
         secret lives there.
Linux:   Secret Service through `secret-tool` when installed; otherwise a
1006 file in the app data dir (documented, not hidden).
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import os
import shutil
import subprocess
import sys
from pathlib import Path

_CRYPTPROTECT_UI_FORBIDDEN = 0x1
_ENTROPY = b"WestlakeDock.v1"   # 改名后也不能动：动了旧令牌就解不开
_MARKER = b"KC\n"


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> _DATA_BLOB:
    buf = ctypes.create_string_buffer(data, len(data))
    blob = _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))
    # 必须把 buffer 挂住：struct 里只是个裸指针，buf 一出作用域就被回收。
    blob._keepalive = buf  # type: ignore[attr-defined]
    return blob


def _blob_bytes(blob: _DATA_BLOB) -> bytes:
    return ctypes.string_at(blob.pbData, blob.cbData)


def _protect(data: bytes) -> bytes:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    src = _blob(data)
    entropy = _blob(_ENTROPY)
    out = _DATA_BLOB()
    ok = crypt32.CryptProtectData(
        ctypes.byref(src), None, ctypes.byref(entropy), None, None,
        _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out),
    )
    if not ok:
        raise OSError("CryptProtectData failed")
    try:
        return _blob_bytes(out)
    finally:
        kernel32.LocalFree(out.pbData)


def _unprotect(data: bytes) -> bytes:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    src = _blob(data)
    entropy = _blob(_ENTROPY)
    out = _DATA_BLOB()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(src), None, ctypes.byref(entropy), None, None,
        _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out),
    )
    if not ok:
        raise OSError("CryptUnprotectData failed")
    try:
        return _blob_bytes(out)
    finally:
        kernel32.LocalFree(out.pbData)


# --------------------------------------------------------------- keychain
def _kc_available() -> bool:
    if sys.platform == "darwin":
        return shutil.which("security") is not None
    return shutil.which("secret-tool") is not None


def _kc_set(name: str, value: str) -> bool:
    try:
        if sys.platform == "darwin":
            subprocess.run(
                ["security", "add-generic-password", "-U", "-a", "VesperBoard",
                 "-s", name, "-w", value],
                check=True, capture_output=True, timeout=15,
            )
        else:
            subprocess.run(
                ["secret-tool", "store", "--label", "VesperBoard", "app", name],
                input=value.encode("utf-8"), check=True, capture_output=True, timeout=15,
            )
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def _kc_get(name: str) -> str:
    try:
        if sys.platform == "darwin":
            out = subprocess.run(
                ["security", "find-generic-password", "-s", name, "-w"],
                check=True, capture_output=True, timeout=15,
            ).stdout
        else:
            out = subprocess.run(
                ["secret-tool", "lookup", "app", name],
                check=True, capture_output=True, timeout=15,
            ).stdout
        return out.decode("utf-8").strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _kc_delete(name: str) -> None:
    try:
        if sys.platform == "darwin":
            subprocess.run(["security", "delete-generic-password", "-s", name],
                           check=False, capture_output=True, timeout=10)
        else:
            subprocess.run(["secret-tool", "clear", "app", name],
                           check=False, capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass


# ------------------------------------------------------------------ files
def _plain_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".plain")


def save_secret(path: Path, value: str) -> None:
    if not value:
        for p in (path, _plain_path(path)):
            try:
                p.unlink()
            except OSError:
                pass
        _kc_delete(path.name)
        return

    if sys.platform.startswith("win"):
        path.write_bytes(_protect(value.encode("utf-8")))
    elif _kc_available() and _kc_set(path.name, value):
        path.write_bytes(_MARKER)
    else:
        plain = _plain_path(path)
        plain.write_text(value, encoding="utf-8")
        try:
            os.chmod(plain, 0o600)
        except OSError:
            pass
        path.unlink(missing_ok=True)
        return

    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def load_secret(path: Path) -> str:
    if path.exists():
        try:
            data = path.read_bytes()
        except OSError:
            return ""
        if data == _MARKER:
            return _kc_get(path.name)
        if not sys.platform.startswith("win"):
            return ""
        try:
            return _unprotect(data).decode("utf-8")
        except Exception:
            return ""
    plain = _plain_path(path)
    if plain.exists():
        try:
            return plain.read_text(encoding="utf-8")
        except OSError:
            return ""
    return ""


# ------------------------------------------------------------- 任意字节 / 钥匙串
def protect_bytes(data: bytes) -> bytes:
    """Windows：用 DPAPI 封装任意长度的字节。其它平台抛 OSError，调用方自行降级。"""
    if not sys.platform.startswith("win"):
        raise OSError("DPAPI 只在 Windows 上可用")
    return _protect(data)


def unprotect_bytes(blob: bytes) -> bytes:
    if not sys.platform.startswith("win"):
        raise OSError("DPAPI 只在 Windows 上可用")
    return _unprotect(blob)


def keychain_available() -> bool:
    """macOS 的 security 命令 / Linux 的 secret-tool 是否可用。"""
    return _kc_available()


def keychain_put(name: str, value: str) -> bool:
    return _kc_available() and _kc_set(name, value)


def keychain_get(name: str) -> str:
    return _kc_get(name) if _kc_available() else ""
