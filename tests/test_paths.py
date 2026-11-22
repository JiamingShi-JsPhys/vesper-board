"""数据目录迁移：复制成功后才删旧目录。"""

from __future__ import annotations

from wsdock.paths import APP_NAME, LEGACY_NAME, _migrate_legacy


def test_migration_copies_then_removes_legacy(tmp_path):
    legacy = tmp_path / LEGACY_NAME
    legacy.mkdir()
    (legacy / "settings.json").write_text("{}", encoding="utf-8")
    (legacy / "canvas_token.bin").write_bytes(b"secret")

    root = tmp_path / APP_NAME
    assert _migrate_legacy(root, legacy) is True

    assert (root / "settings.json").read_text(encoding="utf-8") == "{}"
    assert (root / "canvas_token.bin").read_bytes() == b"secret"
    assert not legacy.exists(), "复制成功后旧目录必须删掉，否则凭据会留第二份"


def test_migration_keeps_legacy_when_root_exists(tmp_path):
    legacy = tmp_path / LEGACY_NAME
    legacy.mkdir()
    (legacy / "settings.json").write_text("old", encoding="utf-8")

    root = tmp_path / APP_NAME
    root.mkdir()
    (root / "settings.json").write_text("new", encoding="utf-8")

    assert _migrate_legacy(root, legacy) is False
    assert (root / "settings.json").read_text(encoding="utf-8") == "new"
    # 没迁移就不动旧目录：那边可能有用户还没迁走的东西
    assert legacy.exists()


def test_migration_without_legacy_is_a_noop(tmp_path):
    root = tmp_path / APP_NAME
    assert _migrate_legacy(root, tmp_path / LEGACY_NAME) is False
    assert not root.exists()


def test_migration_is_idempotent(tmp_path):
    legacy = tmp_path / LEGACY_NAME
    legacy.mkdir()
    (legacy / "a.txt").write_text("1", encoding="utf-8")
    root = tmp_path / APP_NAME

    assert _migrate_legacy(root, legacy) is True
    (root / "a.txt").write_text("2", encoding="utf-8")
    assert _migrate_legacy(root, legacy) is False
    assert (root / "a.txt").read_text(encoding="utf-8") == "2"


def test_data_dir_falls_back_to_legacy_when_migration_fails(tmp_path, monkeypatch):
    """迁移失败时不能建空目录：否则下次启动会跳过迁移，旧令牌成孤儿。"""
    from wsdock import paths

    root = tmp_path / APP_NAME
    legacy = tmp_path / LEGACY_NAME
    legacy.mkdir()

    monkeypatch.setattr(paths, "root_dir", lambda: root)
    monkeypatch.setattr(paths, "_migrate_legacy", lambda r, l: False)

    assert paths.data_dir() == legacy
    assert not root.exists(), "失败的迁移不能留下一个空的 root"
