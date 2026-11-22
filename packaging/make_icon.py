"""生成打包用的图标：直接用 assets/app_icon.png，不再自己画。

三端共用一张方形图标：Windows 生成多尺寸 .ico，macOS 的 .icns 由
`make_iconset.py` 读取同一张 `build/icon.png` 生成。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "assets" / "app_icon.png"
OUT_DIR = ROOT / "build"
SIZES = (256, 128, 64, 48, 32, 16)


def square(image: Image.Image) -> Image.Image:
    """居中裁成正方形，避免不同来源的图被拉变形。"""
    side = min(image.size)
    left = (image.width - side) // 2
    top = (image.height - side) // 2
    return image.crop((left, top, left + side, top + side))


def main() -> None:
    if not SRC.exists():
        raise SystemExit(f"找不到图标源文件：{SRC}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    base = square(Image.open(SRC).convert("RGBA"))
    base.save(OUT_DIR / "icon.ico", format="ICO",
              sizes=[(n, n) for n in SIZES])
    base.resize((256, 256), Image.Resampling.LANCZOS).save(OUT_DIR / "icon.png")
    print("wrote", OUT_DIR / "icon.ico", "from", SRC.name)


if __name__ == "__main__":
    main()
