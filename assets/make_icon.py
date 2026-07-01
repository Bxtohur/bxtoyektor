"""Hasilkan ikon aplikasi bertema PROYEKTOR → assets/app.ico + app.png.

Jalankan: python assets/make_icon.py
Butuh Pillow (dev dependency).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
UNGU = (79, 70, 229)      # indigo — warna latar
UNGU2 = (67, 56, 202)
PUTIH = (255, 255, 255)
KUNING = (250, 204, 21)   # cahaya lampu proyektor


def _bg(size: int) -> Image.Image:
    """Latar kotak membulat dengan gradien vertikal sederhana."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    grad = Image.new("RGBA", (size, size))
    for y in range(size):
        t = y / size
        r = int(UNGU[0] * (1 - t) + UNGU2[0] * t)
        g = int(UNGU[1] * (1 - t) + UNGU2[1] * t)
        b = int(UNGU[2] * (1 - t) + UNGU2[2] * t)
        for x in range(size):
            grad.putpixel((x, y), (r, g, b, 255))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=int(size * 0.22), fill=255
    )
    img.paste(grad, (0, 0), mask)
    return img


def _gambar_proyektor(img: Image.Image, size: int) -> None:
    d = ImageDraw.Draw(img)
    s = size / 256.0

    # Sinar cahaya (trapesium transparan) dari lensa ke kanan-atas.
    beam = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(beam).polygon(
        [(150 * s, 120 * s), (150 * s, 150 * s), (238 * s, 96 * s), (238 * s, 60 * s)],
        fill=(*KUNING, 110),
    )
    img.alpha_composite(beam)

    # Badan proyektor (kotak membulat).
    d.rounded_rectangle(
        [40 * s, 108 * s, 168 * s, 178 * s], radius=int(16 * s), fill=PUTIH
    )
    # Kaki.
    d.rectangle([60 * s, 178 * s, 76 * s, 192 * s], fill=PUTIH)
    d.rectangle([132 * s, 178 * s, 148 * s, 192 * s], fill=PUTIH)
    # Lensa besar (lingkaran) di depan.
    d.ellipse([120 * s, 118 * s, 168 * s, 166 * s], fill=UNGU2)
    d.ellipse([130 * s, 128 * s, 158 * s, 156 * s], fill=KUNING)
    # Tombol/indikator kecil di atas badan.
    d.ellipse([56 * s, 120 * s, 68 * s, 132 * s], fill=UNGU2)
    d.ellipse([76 * s, 120 * s, 88 * s, 132 * s], fill=UNGU2)


def main() -> None:
    base = 256
    img = _bg(base)
    _gambar_proyektor(img, base)
    png = ROOT / "app.png"
    ico = ROOT / "app.ico"
    img.save(png)
    img.save(ico, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("Tersimpan:", png)
    print("Tersimpan:", ico)


if __name__ == "__main__":
    main()
