"""Pemindai folder rekursif sebagai sumber data (mode folder besar).

Menelusuri sebuah folder dan menormalisasi setiap berkas yang bisa dipreview
menjadi DocumentItem:
- `sheet`   = nama subfolder teratas (grup), atau "(root)" untuk berkas di akar.
- `kategori`= path folder relatif terhadap root (mis. "Materi/2024").
- `lokasi`  = path absolut berkas.

Murni logika (tanpa Qt) agar mudah diuji. Untuk folder besar, gunakan
`scan_folder_iter` yang memancarkan item bertahap (dipakai worker + progress).
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from .models import DocumentItem, MediaKind, TipeFile, kind_dari_tipe

# Ekstensi yang diindeks (yang bisa dipreview native).
_EKSTENSI_DIDUKUNG = {
    t.value for t in TipeFile if kind_dari_tipe(t) != MediaKind.LAINNYA
} | {"jpeg"}

# Folder yang dilewati agar pemindaian tetap cepat & bersih.
_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "$RECYCLE.BIN", "System Volume Information"}


@dataclass(slots=True)
class HasilScan:
    items: list[DocumentItem]
    peringatan: list[str]

    @property
    def jumlah_per_sheet(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for it in self.items:
            out[it.sheet] = out.get(it.sheet, 0) + 1
        return out


def _didukung(nama: str) -> bool:
    ext = Path(nama).suffix.lower().lstrip(".")
    return ext in _EKSTENSI_DIDUKUNG


def _buat_item(root: Path, berkas: Path) -> DocumentItem:
    rel = berkas.relative_to(root)
    bagian = rel.parts
    sheet = bagian[0] if len(bagian) > 1 else "(root)"
    kategori = str(rel.parent).replace("\\", "/")
    if kategori == ".":
        kategori = ""
    return DocumentItem(
        sheet=sheet,
        kategori=kategori,
        nama_file=berkas.name,
        lokasi=str(berkas),
    )


def scan_folder_iter(root: str | Path) -> Iterator[DocumentItem]:
    """Pancarkan DocumentItem bertahap sambil menelusuri folder.

    Raise NotADirectoryError bila root bukan folder.
    """
    root = Path(root)
    if not root.is_dir():
        raise NotADirectoryError(f"Bukan folder yang valid: {root}")

    for dirpath, dirnames, filenames in os.walk(root):
        # Lewati folder yang tidak relevan (ubah in-place agar os.walk patuh).
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith("~$")]
        for nama in filenames:
            if nama.startswith("~$"):  # berkas lock Office
                continue
            if _didukung(nama):
                yield _buat_item(root, Path(dirpath) / nama)


def scan_folder(root: str | Path) -> HasilScan:
    """Pindai seluruh folder sekaligus (untuk pemakaian sinkron/uji)."""
    peringatan: list[str] = []
    items = list(scan_folder_iter(root))
    if not items:
        peringatan.append("Tidak ada berkas yang bisa dipreview ditemukan di folder ini.")
    return HasilScan(items=items, peringatan=peringatan)
