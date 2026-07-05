"""Model data internal seragam (lihat PRD §10 & AGENTS.md §5).

Semua lapisan lain bergantung pada struktur ini. Data Layer bertugas
menormalisasi sumber (folder lokal / Excel / Google Sheet) menjadi
list[DocumentItem].
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class Sumber(StrEnum):
    """Asal dokumen."""

    LOCAL = "local"   # path file di komputer
    DRIVE = "drive"   # link Google Drive / URL


class MediaKind(StrEnum):
    """Cara sebuah item dipratinjau (menentukan komponen viewer)."""

    PAGED = "paged"   # dirender jadi halaman gambar (pdf/docx/pptx/gambar)
    VIDEO = "video"   # diputar dengan media player
    SCREEN = "screen"  # berbagi layar/window langsung (bukan dari file)
    LAINNYA = "lainnya"  # tidak bisa dipreview native


class TipeFile(StrEnum):
    """Tipe file, dideteksi dari ekstensi."""

    PDF = "pdf"
    DOCX = "docx"
    DOC = "doc"
    PPTX = "pptx"
    PPT = "ppt"
    XLSX = "xlsx"
    PNG = "png"
    JPG = "jpg"
    GIF = "gif"
    BMP = "bmp"
    WEBP = "webp"
    MP4 = "mp4"
    MKV = "mkv"
    MOV = "mov"
    AVI = "avi"
    WEBM = "webm"
    M4V = "m4v"
    LAINNYA = "lainnya"

    @classmethod
    def dari_lokasi(cls, lokasi: str) -> TipeFile:
        """Deteksi tipe dari ekstensi path/URL."""
        ext = Path(lokasi.split("?")[0].split("#")[0]).suffix.lower().lstrip(".")
        alias = {"jpeg": "jpg", "xls": "xlsx"}
        ext = alias.get(ext, ext)
        try:
            return cls(ext)
        except ValueError:
            return cls.LAINNYA


# Kelompok tipe → cara preview.
_DOKUMEN_PAGED = {TipeFile.PDF, TipeFile.DOCX, TipeFile.DOC, TipeFile.PPTX, TipeFile.PPT}
_GAMBAR = {TipeFile.PNG, TipeFile.JPG, TipeFile.GIF, TipeFile.BMP, TipeFile.WEBP}
_VIDEO = {TipeFile.MP4, TipeFile.MKV, TipeFile.MOV, TipeFile.AVI, TipeFile.WEBM, TipeFile.M4V}


def kind_dari_tipe(tipe: TipeFile) -> MediaKind:
    if tipe in _DOKUMEN_PAGED or tipe in _GAMBAR:
        return MediaKind.PAGED
    if tipe in _VIDEO:
        return MediaKind.VIDEO
    return MediaKind.LAINNYA


def _deteksi_sumber(lokasi: str) -> Sumber:
    """Link http(s) atau google drive dianggap 'drive'; selebihnya 'local'."""
    low = lokasi.strip().lower()
    if low.startswith(("http://", "https://")) or "drive.google" in low or "docs.google" in low:
        return Sumber.DRIVE
    return Sumber.LOCAL


@dataclass(slots=True)
class DocumentItem:
    """Satu berkas/bukti setelah normalisasi."""

    sheet: str            # grup/sumber (nama sheet Excel atau folder teratas)
    kategori: str         # sub-kategori (judul Excel atau path folder relatif)
    nama_file: str        # nama dokumen yang dicari pengguna
    lokasi: str           # path lokal absolut atau URL
    sumber: Sumber = field(init=False)
    tipe_file: TipeFile = field(init=False)
    kind: MediaKind = field(init=False)
    id: str = field(init=False)
    cache_path: str | None = None

    def __post_init__(self) -> None:
        self.sumber = _deteksi_sumber(self.lokasi)
        self.tipe_file = TipeFile.dari_lokasi(self.lokasi)
        self.kind = kind_dari_tipe(self.tipe_file)
        raw = f"{self.sheet}|{self.nama_file}|{self.lokasi}"
        self.id = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]

    @property
    def teks_cari(self) -> str:
        """Gabungan field untuk indexing/pencarian."""
        return f"{self.nama_file} {self.kategori} {self.sheet}".strip()

    @property
    def bisa_dipreview(self) -> bool:
        """True bila item bisa dipratinjau native (bukan link Drive)."""
        return self.sumber == Sumber.LOCAL and self.kind != MediaKind.LAINNYA
