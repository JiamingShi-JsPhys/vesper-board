# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 配置：只打应用代码和形象素材。

刻意不打进包里的东西：
  docs/   —— 里面是本机截图和使用记录
  tools/  —— 立绘生成脚本，会操作键鼠和剪贴板，不该跟着发行
  tests/  —— 测试
  assets/ref_*.jpg —— 个人/校方参考图
  任何 settings.json / *.bin / web-profile —— 运行时才生成，属于用户数据
"""

import os
import sys
from pathlib import Path


def _extra_binaries():
    """conda/mamba 版 Python 把若干运行库放在 Library\bin 里，不在默认搜索路径，
    必须手动带上；python.org 的版本不需要。ffi-8.dll 管 ctypes，sqlite3.dll 管
    _sqlite3（登录窗和 cookie 库都要用），其余几个是同类的运行库。"""
    import sys as _sys
    names = ("ffi-8.dll", "sqlite3.dll", "libssl-3-x64.dll", "libcrypto-3-x64.dll",
             "liblzma.dll", "libbz2.dll", "zlib.dll")
    roots = {Path(_sys.prefix), Path(_sys.base_prefix)}
    out = []
    for name in names:
        for base in roots:
            for cand in (base / "Library" / "bin" / name, base / "DLLs" / name,
                         base / name):
                if cand.exists():
                    out.append((str(cand), "."))
                    break
    return out


PROJECT = Path(SPECPATH).resolve().parent
ICON = PROJECT / "build" / "icon.ico"

a = Analysis(
    [str(PROJECT / "main.py")],
    pathex=[str(PROJECT)],
    binaries=_extra_binaries(),
    datas=[
        (str(PROJECT / "assets" / "pet"), "assets/pet"),
        (str(PROJECT / "assets" / "app_icon.png"), "assets"),
        # LGPL / Apache / PSF 要求随发行物附带许可证文本
        (str(PROJECT / "licenses"), "licenses"),
        (str(PROJECT / "LICENSE"), "."),
        (str(PROJECT / "THIRD_PARTY_LICENSES.txt"), "."),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "tests", "tools"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="VesperBoard",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=os.environ.get("WESTLAKE_CONSOLE") == "1",
    disable_windowed_traceback=False,
    icon=str(ICON) if ICON.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="VesperBoard",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Vesper Board.app",
        icon=str(PROJECT / "build" / "icon.icns") if (PROJECT / "build" / "icon.icns").exists() else None,
        bundle_identifier="com.vesperboard.app",
        info_plist={
            "CFBundleName": "Vesper Board",
            "CFBundleDisplayName": "晚星看板",
            "CFBundleShortVersionString": "1.0.0",
            "CFBundleVersion": "1.0.0",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )

# ---------------------------------------------------------------- 裁剪
# PyInstaller 会把 Qt 的全套 devtools 调试包和几十种语言的翻译都塞进来。
# 这里删掉用不到的部分：调试包两个（约 83 MB）、非中日英的翻译（约 50 MB）。
def _trim(root: Path) -> None:
    import shutil

    resources = root / "_internal" / "PySide6" / "resources" if (root / "_internal").is_dir() else root / "PySide6" / "resources"
    for name in ("qtwebengine_devtools_resources.pak",
                 "qtwebengine_devtools_resources.debug.pak"):
        target = resources / name
        if target.exists():
            target.unlink()

    # PyInstaller 6 把 datas 放进 _internal/，许可证应该摆在安装目录根下
    internal = root / "_internal"
    if internal.is_dir():
        for name in ("LICENSE", "THIRD_PARTY_LICENSES.txt"):
            src = internal / name
            if src.exists():
                shutil.copy2(src, root / name)
                src.unlink()
        lic = internal / "licenses"
        if lic.is_dir():
            dest = root / "licenses"
            if dest.exists():
                shutil.rmtree(dest)
            shutil.move(str(lic), str(dest))

    if (root / "_internal").is_dir():
        trans = root / "_internal" / "PySide6" / "translations"
    else:
        trans = root / "PySide6" / "translations"
    # 发行版默认只带「默认小西」；要连测试角色一起打，就设 WESPER_SHIP_ALL_SKINS=1
    import os as _os
    pet = root / "_internal" / "assets" / "pet"
    if not pet.is_dir():
        pet = root / "assets" / "pet"
    if pet.is_dir() and _os.environ.get("WESPER_SHIP_ALL_SKINS") != "1":
        for child in pet.iterdir():
            if child.is_dir() and child.name != "mascot":
                shutil.rmtree(child)

    keep = ("_zh_CN", "_zh_TW", "_en")
    if trans.is_dir():
        for qm in list(trans.glob("*.qm")) + list(trans.glob("*.pak")):
            if not any(k in qm.stem for k in keep):
                qm.unlink()
        # Chromium 自己的语言包（qtwebengine_locales/*.pak），一百多种，只留中英
        locales = trans / "qtwebengine_locales"
        if locales.is_dir():
            for pak in locales.iterdir():
                if pak.name not in ("en-US.pak", "zh-CN.pak", "zh-TW.pak"):
                    pak.unlink()


_dist = PROJECT / "dist"
_trim(_dist / "VesperBoard")
# macOS 的 .app 是 COLLECT 的副本，要单独裁一遍
for _app in _dist.glob("*.app"):
    _trim(_app / "Contents" / "Frameworks")
