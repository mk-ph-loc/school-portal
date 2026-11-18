#!/opt/school-portal/venv/bin/python
"""
make-demo-assets.py — Υλικό για τη σελίδα «Παράδειγμα Δυνατοτήτων MkDocs».

Δημιουργεί στο docs/paradeigma-dynatotiton/:
  * animation.gif — GIF animation δυαδικής μέτρησης (Pillow, ήδη στο requirements)

Επαναεκτελέσιμο (idempotent). Χρήση:
  /opt/school-portal/venv/bin/python scripts/make-demo-assets.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE = Path("/opt/school-portal/mkdocs-site/docs/paradeigma-dynatotiton")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_B if bold else FONT, size)


def binary_gif(path: Path) -> None:
    """16 καρέ: μετρητής 0–15 σε δυαδικό με 4 «λαμπάκια» (bits)."""
    W, H = 640, 300
    frames = []
    for n in range(16):
        im = Image.new("RGB", (W, H), "#1a237e")
        d = ImageDraw.Draw(im)
        d.text((W // 2, 40), "Δυαδικός μετρητής", font=font(30, True),
               fill="#ffffff", anchor="mm")
        bits = f"{n:04b}"
        x0 = 90
        for i, b in enumerate(bits):
            on = b == "1"
            cx = x0 + i * 130
            color = "#ffd54f" if on else "#3949ab"
            d.ellipse([cx, 90, cx + 100, 190], fill=color,
                      outline="#ffffff", width=3)
            d.text((cx + 50, 140), b, font=font(48, True),
                   fill="#1a237e" if on else "#c5cae9", anchor="mm")
            d.text((cx + 50, 215), str(2 ** (3 - i)), font=font(20),
                   fill="#9fa8da", anchor="mm")
        d.text((W // 2, 262), f"{bits}₂ = {n}₁₀", font=font(28, True),
               fill="#ffe082", anchor="mm")
        frames.append(im)
    frames[0].save(path, save_all=True, append_images=frames[1:],
                   duration=600, loop=0, optimize=True)


def main() -> None:
    BASE.mkdir(parents=True, exist_ok=True)
    binary_gif(BASE / "animation.gif")
    print(f"✅ animation.gif → {BASE}")


if __name__ == "__main__":
    main()