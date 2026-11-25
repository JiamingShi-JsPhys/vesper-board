"""这台机器上落盘的每一样用户数据，都用 AES-256-GCM 加密。

主密钥是 32 字节随机数，只以「操作系统能替我们解开」的形式保存：

  Windows   DPAPI —— 同一 Windows 账户、同一台机器才解得开，文件被拷走没用
  macOS     登录钥匙串（security add-generic-password）
  Linux     Secret Service（secret-tool）
  都没有     0600 的 key.plain —— 和旧令牌的降级路径一致，不假装安全

文件格式：``b"VBX1" + 12 字节 nonce + AESGCM 密文（含 16 字节 tag）``。
AAD 用逻辑名（settings / archived / reminders / log），把文件换名或对调都解不开。
GCM 的 tag 保证了篡改会被发现，而不是解出垃圾数据。

密钥丢了（换账户、重装系统、删了 key.bin）就等于这份数据丢了 —— 这是
「强加密」本身的代价，程序会退回默认设置，而不是解密出一堆乱码。
"""

from __future__ import annotations

import base64
import json
import logging
import os
import struct
import sys
from pathlib import Path
from typing import Any

from . import paths, security

MAGIC = b"VBX1"
NONCE = 12
KEY_BYTES = 32
KEY_NAME = "vault-key"        # 钥匙串里的条目名
KEY_FILE = "key.bin"
KEY_PLAIN = "key.plain"
_KC_MARKER = b"KC\n"

log = logging.getLogger("wsdock.vault")

_KEY: bytes | None = None


class VaultError(RuntimeError):
    """密钥不可用或密文被改过。"""


# ------------------------------------------------------------------ 主密钥
def _key_path() -> Path:
    return paths.data_dir() / KEY_FILE


def _plain_key_path() -> Path:
    return paths.data_dir() / KEY_PLAIN


def _store_key(key: bytes) -> None:
    path = _key_path()
    plain = _plain_key_path()
    try:
        if sys.platform.startswith("win"):
            blob = security.protect_bytes(key)
            _write_bytes_atomic(path, blob)
            plain.unlink(missing_ok=True)
            return
        if security.keychain_available() and security.keychain_put(
                KEY_NAME, base64.b64encode(key).decode("ascii")):
            _write_bytes_atomic(path, _KC_MARKER)
            plain.unlink(missing_ok=True)
            return
    except (OSError, VaultError):
        pass
    # 最后兜底：0600 的明文密钥。比不加密强，但要在文档里说清楚。
    _write_bytes_atomic(plain, base64.b64encode(key))
    path.unlink(missing_ok=True)


def _read_key() -> bytes | None:
    path = _key_path()
    if path.exists():
        try:
            data = path.read_bytes()
        except OSError:
            return None
        if data == _KC_MARKER:
            raw = security.keychain_get(KEY_NAME)
            try:
                key = base64.b64decode(raw)
            except (ValueError, TypeError):
                return None
            return key if len(key) == KEY_BYTES else None
        if sys.platform.startswith("win"):
            try:
                key = security.unprotect_bytes(data)
            except Exception:
                return None
            return key if len(key) == KEY_BYTES else None
        return None
    plain = _plain_key_path()
    if plain.exists():
        try:
            key = base64.b64decode(plain.read_bytes())
        except (OSError, ValueError):
            return None
        return key if len(key) == KEY_BYTES else None
    return None


def master_key() -> bytes:
    """取主密钥；没有就生成一把并存进系统凭据。"""
    global _KEY
    if _KEY is None:
        key = _read_key()
        if key is None:
            key = os.urandom(KEY_BYTES)
            _store_key(key)
            log.info("已生成新的数据加密主密钥")
        _KEY = key
    return _KEY


def reset_cache() -> None:
    """测试用：忘掉内存里的密钥。"""
    global _KEY
    _KEY = None


# ------------------------------------------------------------------ 加解密
def _aad(name: str) -> bytes:
    return ("VesperBoard/" + name).encode("utf-8")


def is_sealed(blob: bytes) -> bool:
    return blob[:len(MAGIC)] == MAGIC


def seal(name: str, data: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(NONCE)
    ct = AESGCM(master_key()).encrypt(nonce, data, _aad(name))
    return MAGIC + nonce + ct


def unseal(name: str, blob: bytes) -> bytes:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if not is_sealed(blob) or len(blob) < len(MAGIC) + NONCE + 16:
        raise VaultError("不是本程序的密文")
    nonce = blob[len(MAGIC):len(MAGIC) + NONCE]
    ct = blob[len(MAGIC) + NONCE:]
    try:
        return AESGCM(master_key()).decrypt(nonce, ct, _aad(name))
    except InvalidTag as exc:
        raise VaultError("密文校验失败（被改过，或密钥不是这一把）") from exc


# ------------------------------------------------------------------ 文件读写
def _write_bytes_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name("%s.%d.tmp" % (path.name, os.getpid()))
    try:
        tmp.unlink()
    except OSError:
        pass
    with open(tmp, "xb") as fh:
        fh.write(data)
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def _scrub(path: Path) -> None:
    """覆盖一遍再删：旧明文不要以「已删除」的名义留在簇里。"""
    try:
        size = path.stat().st_size
        with open(path, "r+b") as fh:
            fh.write(b"\0" * size)
            fh.flush()
            os.fsync(fh.fileno())
    except OSError:
        pass
    try:
        path.unlink()
    except OSError:
        pass


def read_bytes(name: str, path: Path) -> bytes | None:
    """读密文；碰到旧版本的明文文件就原样返回（调用方下次写入时会转成密文）。"""
    try:
        blob = path.read_bytes()
    except OSError:
        return None
    if not is_sealed(blob):
        return blob
    try:
        return unseal(name, blob)
    except VaultError:
        log.warning("%s 解不开，按空文件处理", path.name)
        return None


def write_bytes(name: str, path: Path, data: bytes) -> None:
    _write_bytes_atomic(path, seal(name, data))


def read_json(name: str, path: Path, default: Any) -> Any:
    raw = read_bytes(name, path)
    if raw is None:
        return default
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return default
    return value if isinstance(value, type(default)) else default


def write_json(name: str, path: Path, value: Any) -> None:
    payload = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
    write_bytes(name, path, payload)
    # 老版本留下的明文同名文件要清掉，免得成了第二份
    swap = path.with_suffix(path.suffix + ".plain")
    if swap.exists():
        _scrub(swap)


# ------------------------------------------------------------------ 日志
class LogSink:
    """把日志一行一条地封成密文；按大小轮转，读的时候再解开。"""

    def __init__(self, path: Path, max_bytes: int = 1_000_000, backups: int = 2) -> None:
        self.path = path
        self.max_bytes = max_bytes
        self.backups = backups

    def append(self, text: str) -> None:
        frame = seal("log", text.encode("utf-8", "replace"))
        record = struct.pack(">I", len(frame)) + frame
        try:
            size = self.path.stat().st_size
        except OSError:
            size = 0
        if size and size + len(record) > self.max_bytes:
            self._rotate()
        with open(self.path, "ab") as fh:
            fh.write(record)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def _rotate(self) -> None:
        for i in range(self.backups, 0, -1):
            src = self.path if i == 1 else self.path.with_name("%s.%d" % (self.path.name, i - 1))
            dst = self.path.with_name("%s.%d" % (self.path.name, i))
            try:
                if i == self.backups and dst.exists():
                    dst.unlink()
                if src.exists():
                    os.replace(src, dst)
            except OSError:
                pass

    def read(self) -> str:
        """把主文件按顺序解开；解不动的地方就停下，返回已经读出来的部分。"""
        try:
            blob = self.path.read_bytes()
        except OSError:
            return ""
        out: list[str] = []
        pos = 0
        while pos + 4 <= len(blob):
            (length,) = struct.unpack(">I", blob[pos:pos + 4])
            pos += 4
            if length <= 0 or pos + length > len(blob):
                break
            try:
                out.append(unseal("log", blob[pos:pos + length]).decode("utf-8", "replace"))
            except VaultError:
                break
            pos += length
        return "".join(out)


def migrate_plaintext(name: str, path: Path) -> bool:
    """旧版本留在盘上的明文 JSON：原地转成密文。"""
    if not path.is_file():
        return False
    try:
        blob = path.read_bytes()
    except OSError:
        return False
    if not blob or is_sealed(blob):
        return False
    tmp = path.with_name(path.name + ".migrating")
    try:
        tmp.unlink()
    except OSError:
        pass
    try:
        with open(tmp, "xb") as fh:
            fh.write(seal(name, blob))
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        _scrub(path)          # 先把旧明文覆盖掉，再换上新密文
        os.replace(tmp, path)
    except OSError:
        return False
    return True


def _split_frames(blob: bytes) -> tuple[list[str], bool]:
    """把「明文 + 密文帧」混排的旧日志拆开。

    帧的开头是 4 字节长度 + MAGIC；明文里也可能碰巧出现 MAGIC，所以必须
    真的解一次，解得开才认定为帧。返回（按顺序的文本片段，是否含明文）。
    """
    marks: list[tuple[int, int, str]] = []
    start = 0
    while True:
        i = blob.find(MAGIC, start)
        if i < 0:
            break
        start = i + 1
        if i < 4:
            continue
        (length,) = struct.unpack(">I", blob[i - 4:i])
        body = blob[i:i + length]
        if length <= 0 or i + length > len(blob):
            continue
        try:
            text = unseal("log", body).decode("utf-8", "replace")
        except VaultError:
            continue
        marks.append((i - 4, i + length, text))
    chunks: list[str] = []
    pos = 0
    has_plain = False
    for begin, finish, text in marks:
        if begin > pos:
            chunks.append(blob[pos:begin].decode("utf-8", "replace"))
            has_plain = True
        chunks.append(text)
        pos = finish
    if pos < len(blob):
        chunks.append(blob[pos:].decode("utf-8", "replace"))
        has_plain = True
    return chunks, has_plain


def migrate_log(path: Path, backups: int = 2) -> bool:
    """旧版本写的是明文日志：把明文部分重新封成帧，再覆盖清零旧文件。"""
    files = [path.with_name("%s.%d" % (path.name, i)) for i in range(backups, 0, -1)]
    files.append(path)
    chunks: list[str] = []
    stale = False
    for f in files:
        if not f.is_file():
            continue
        try:
            blob = f.read_bytes()
        except OSError:
            continue
        if not blob:
            continue
        parts, has_plain = _split_frames(blob)
        chunks.extend(parts)
        stale = stale or has_plain
    if not stale:
        return False
    tmp = path.with_name("%s.%d.migrating" % (path.name, os.getpid()))
    try:
        tmp.unlink()
    except OSError:
        pass
    sink = LogSink(tmp, max_bytes=1 << 40)      # 迁移途中绝不轮转
    for text in chunks:
        if text:
            sink.append(text)
    for f in files:
        if f.is_file():
            _scrub(f)
    os.replace(tmp, path)
    return True


def log_sink() -> LogSink:
    return LogSink(paths.log_file())


def append_log(text: str) -> None:
    """给不走 logging 的几处（登录窗诊断）用的直写入口。"""
    try:
        log_sink().append(text if text.endswith("\n") else text + "\n")
    except Exception:
        pass


class VaultLogHandler(logging.Handler):
    """替换 RotatingFileHandler：同样的格式，落盘换成密文。"""

    def __init__(self, sink: LogSink | None = None) -> None:
        super().__init__()
        self.sink = sink or log_sink()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.sink.append(self.format(record) + "\n")
        except Exception:
            self.handleError(record)
