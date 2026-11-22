"""把 build/icon.png 展开成 macOS 的 .iconset 目录（配合 iconutil）。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "build" / "icon.png"
OUT = ROOT / "build" / "icon.iconset"
SIZES = (16, 32, 64, 128, 256, 512)


def main() -> None:
    img = Image.open(SRC).convert("RGBA")
    OUT.mkdir(parents=True, exist_ok=True)
    for s in SIZES:
        img.resize((s, s), Image.LANCZOS).save(OUT / f"icon_{s}x{s}.png")
        img.resize((s * 2, s * 2), Image.LANCZOS).save(OUT / f"icon_{s}x{s}@2x.png")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
