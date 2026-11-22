"""生成打包用的图标：蓝色圆 + 白色 W（不依赖中文，三端都能渲染）。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path(__file__).resolve().parent.parent / "build"
SIZES = (256, 128, 64, 48, 32, 16)


def draw(size: int) -> Image.Image:
    scale = 4
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = int(s * 0.04)
    d.ellipse([pad, pad, s - pad, s - pad], fill=(58, 120, 235, 255))
    # 上高光
    d.ellipse([pad, pad, s - pad, int(s * 0.52)], fill=(96, 160, 255, 255))
    # 白色 W
    font = None
    for name in ("arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf"):
        try:
            font = ImageFont.truetype(name, int(s * 0.52))
            break
        except OSError:
            continue
    if font is None:
        font = ImageFont.load_default()
    text = "W"
    left, top, right, bottom = d.textbbox((0, 0), text, font=font)
    d.text(((s - (right - left)) / 2 - left, (s - (bottom - top)) / 2 - top - s * 0.02),
           text, font=font, fill=(255, 255, 255, 240))
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    images = [draw(n) for n in SIZES]
    images[0].save(OUT_DIR / "icon.ico", sizes=[(n, n) for n in SIZES])
    images[0].save(OUT_DIR / "icon.png")
    print("wrote", OUT_DIR / "icon.ico")


if __name__ == "__main__":
    main()
