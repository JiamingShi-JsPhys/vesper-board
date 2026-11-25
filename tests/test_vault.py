"""落盘加密：往返、防篡改、文件名绑定、明文迁移、日志帧。"""

from __future__ import annotations

import json
import struct

import pytest

from wsdock import paths, vault


@pytest.fixture()
def data(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "root_dir", lambda: tmp_path)
    vault.reset_cache()
    yield tmp_path
    vault.reset_cache()


def test_roundtrip(data):
    blob = vault.seal("settings", b'{"a": 1}')
    assert blob.startswith(vault.MAGIC)
    assert vault.unseal("settings", blob) == b'{"a": 1}'


def test_ciphertext_does_not_leak_plaintext(data):
    blob = vault.seal("settings", '姓名：张三'.encode())
    assert "张三".encode() not in blob


def test_tamper_is_detected(data):
    blob = bytearray(vault.seal("settings", b"secret"))
    blob[-1] ^= 0x01
    with pytest.raises(vault.VaultError):
        vault.unseal("settings", bytes(blob))


def test_file_name_is_bound_to_content(data):
    blob = vault.seal("settings", b"x")
    with pytest.raises(vault.VaultError):
        vault.unseal("archived", blob)


def test_truncated_blob_is_rejected(data):
    blob = vault.seal("settings", b"0123456789")
    with pytest.raises(vault.VaultError):
        vault.unseal("settings", blob[:10])


def test_key_is_persisted(data):
    first = vault.master_key()
    vault.reset_cache()
    assert vault.master_key() == first
    assert (data / vault.KEY_FILE).exists() or (data / vault.KEY_PLAIN).exists()


def test_json_roundtrip_and_file_is_sealed(data):
    path = data / "settings.json"
    vault.write_json("settings", path, {"user_name": "张三", "theme_mode": "dark"})
    raw = path.read_bytes()
    assert raw.startswith(vault.MAGIC)
    assert "张三".encode() not in raw
    assert vault.read_json("settings", path, {}) == {"user_name": "张三", "theme_mode": "dark"}


def test_legacy_plaintext_is_still_readable(data):
    path = data / "settings.json"
    path.write_text(json.dumps({"user_name": "old"}), encoding="utf-8")
    assert vault.read_json("settings", path, {}) == {"user_name": "old"}


def test_write_replaces_legacy_plaintext_file(data):
    path = data / "archived.json"
    legacy = path.with_suffix(".json.plain")
    legacy.write_text("{}", encoding="utf-8")
    vault.write_json("archived", path, {})
    assert not legacy.exists()


def test_wrong_type_falls_back_to_default(data):
    path = data / "settings.json"
    vault.write_json("settings", path, [1, 2, 3])
    assert vault.read_json("settings", path, {}) == {}


def test_log_sink_roundtrip(data):
    sink = vault.LogSink(data / "dock.log", max_bytes=10_000)
    sink.append("第一行\n")
    sink.append("第二行\n")
    assert sink.read() == "第一行\n第二行\n"
    assert "第一行".encode() not in (data / "dock.log").read_bytes()


def test_log_sink_rotates(data):
    sink = vault.LogSink(data / "dock.log", max_bytes=200, backups=2)
    for i in range(20):
        sink.append("行 %d\n" % i)
    assert (data / "dock.log.1").exists()
    current = sink.read()
    assert current.endswith("行 19\n"), current        # 最新一行在主的密文里
    assert current.startswith("行 ")                   # 从帧边界开始，不读半行
    rotated = vault.LogSink(data / "dock.log.1").read()
    assert rotated.startswith("行 ") and "行 19\n" not in rotated


def test_log_read_stops_at_corruption(data):
    sink = vault.LogSink(data / "dock.log")
    sink.append("ok\n")
    blob = (data / "dock.log").read_bytes()
    (data / "dock.log").write_bytes(blob + b"\x00\x00\x00\x05junk")
    assert sink.read() == "ok\n"

def test_migrate_mixed_log_keeps_both_parts(data):
    """旧日志是「明文 + 已经追加的密文帧」混在一起时，两边都不能丢。"""
    path = data / "dock.log"
    frame = vault.seal("log", "新的一行\n".encode())
    path.write_bytes("旧的一行\n".encode() + struct.pack(">I", len(frame)) + frame)
    assert vault.migrate_log(path) is True
    text = vault.LogSink(path).read()
    assert "旧的一行\n" in text and "新的一行\n" in text

def test_migrate_is_idempotent_for_sealed_log(data):
    """已经全是密文帧的日志不能再包一层（LogSink 的文件不以 MAGIC 开头）。"""
    sink = vault.LogSink(data / "dock.log")
    sink.append("一行\n")
    before = (data / "dock.log").read_bytes()
    assert vault.migrate_log(data / "dock.log") is False
    assert (data / "dock.log").read_bytes() == before
    assert vault.LogSink(data / "dock.log").read() == "一行\n"
