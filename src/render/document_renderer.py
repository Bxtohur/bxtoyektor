"""Document Renderer (PRD F-3.x, §8.2).

Menghasilkan output SERAGAM: gambar per-halaman (QImage) untuk ditampilkan
di kanvas Qt — baik dokumen PDF, DOCX (via konversi LibreOffice), maupun gambar.

Catatan penting sesuai data nyata:
- Hampir semua sumber berupa link Google Drive (butuh internet / login).
- Renderer native HANYA bekerja untuk berkas LOKAL (path di disk) atau berkas
  yang sudah di-cache. Untuk link Drive, UI menampilkan opsi "Buka di Browser"
  (F-3.5) dan — di fase berikutnya — mengunduh ke cache lalu merender (F-1.3).

Semua operasi berat di modul ini dipanggil dari worker thread (lihat AGENTS.md §6),
bukan dari UI thread.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF
from PySide6.QtGui import QImage

from ..data.models import DocumentItem, Sumber, TipeFile

_TIPE_GAMBAR = {TipeFile.PNG, TipeFile.JPG, TipeFile.GIF, TipeFile.BMP, TipeFile.WEBP}
_TIPE_OFFICE = {TipeFile.DOCX, TipeFile.DOC, TipeFile.PPTX, TipeFile.PPT}


class RenderError(Exception):
    """Kesalahan saat merender dokumen (ditampilkan jelas ke pengguna)."""


@dataclass(slots=True)
class LokasiSoffice:
    """Hasil pencarian executable LibreOffice."""

    path: str | None

    @property
    def tersedia(self) -> bool:
        return self.path is not None


def cari_soffice() -> LokasiSoffice:
    """Cari LibreOffice (soffice) di PATH atau lokasi instalasi umum Windows.

    Sesuai PRD §13: JANGAN bundle LibreOffice — deteksi yang sudah terpasang.
    """
    for nama in ("soffice", "soffice.exe"):
        found = shutil.which(nama)
        if found:
            return LokasiSoffice(found)
    kandidat = [
        Path(r"C:/Program Files/LibreOffice/program/soffice.exe"),
        Path(r"C:/Program Files (x86)/LibreOffice/program/soffice.exe"),
    ]
    for p in kandidat:
        if p.exists():
            return LokasiSoffice(str(p))
    return LokasiSoffice(None)


class RenderedDocument:
    """Dokumen yang siap ditampilkan sebagai halaman-halaman gambar.

    Untuk PDF, halaman dirender lazy (on-demand) agar hemat memori pada file
    besar (target: PDF hingga 50 MB tetap responsif).
    """

    def __init__(self, pdf_path: Path | None = None, gambar: QImage | None = None) -> None:
        self._doc: fitz.Document | None = None
        self._gambar = gambar
        if pdf_path is not None:
            self._doc = fitz.open(pdf_path)

    @property
    def jumlah_halaman(self) -> int:
        if self._gambar is not None:
            return 1
        return self._doc.page_count if self._doc else 0

    def ukuran_halaman(self, indeks: int, zoom: float = 1.0) -> tuple[int, int]:
        """Ukuran (lebar, tinggi) halaman pada zoom tertentu TANPA merender.

        Dipakai viewer scroll-menerus untuk menata placeholder halaman lebih dulu.
        """
        if self._gambar is not None:
            return int(self._gambar.width() * zoom), int(self._gambar.height() * zoom)
        if self._doc is None or not (0 <= indeks < self._doc.page_count):
            return (0, 0)
        r = self._doc.load_page(indeks).rect
        return max(1, int(r.width * zoom)), max(1, int(r.height * zoom))

    def halaman(self, indeks: int, zoom: float = 1.0) -> QImage:
        """Render satu halaman ke QImage pada level zoom tertentu."""
        if self._gambar is not None:
            return self._gambar
        if self._doc is None or not (0 <= indeks < self._doc.page_count):
            raise RenderError(f"Halaman {indeks + 1} di luar jangkauan.")
        page = self._doc.load_page(indeks)
        matrix = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        # Salin bytes agar QImage tidak mengacu buffer yang bisa dibebaskan.
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
        return img.copy()

    def close(self) -> None:
        if self._doc is not None:
            self._doc.close()
            self._doc = None


class DocumentRenderer:
    """Fasad renderer: pilih strategi berdasarkan tipe file & sumber."""

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._soffice = cari_soffice()

    def bisa_render_native(self, item: DocumentItem) -> bool:
        """True bila item bisa dirender di aplikasi (berkas lokal terdukung)."""
        if item.sumber == Sumber.DRIVE:
            return False
        return item.bisa_dipreview

    def render(self, item: DocumentItem) -> RenderedDocument:
        """Render item lokal menjadi RenderedDocument.

        Raise RenderError dengan pesan jelas bila tidak bisa dirender native
        (mis. link Drive → arahkan UI untuk 'Buka di Browser').
        """
        if item.sumber == Sumber.DRIVE:
            raise RenderError(
                "Dokumen ini berupa link Google Drive. Gunakan 'Buka di Browser' "
                "atau aktifkan sinkronisasi/cache (fase berikutnya)."
            )

        path = Path(item.cache_path or item.lokasi)
        if not path.exists():
            raise RenderError(f"Berkas tidak ditemukan: {path}")

        tipe = item.tipe_file
        if tipe == TipeFile.PDF:
            return RenderedDocument(pdf_path=path)
        if tipe in _TIPE_GAMBAR:
            img = QImage(str(path))
            if img.isNull():
                raise RenderError(f"Gagal memuat gambar: {path.name}")
            return RenderedDocument(gambar=img)
        if tipe in _TIPE_OFFICE:
            pdf = self._konversi_ke_pdf(path)
            return RenderedDocument(pdf_path=pdf)
        raise RenderError(f"Tipe file belum didukung untuk preview: {tipe.value}")

    def _konversi_ke_pdf(self, path: Path) -> Path:
        """Konversi dokumen Office (DOCX/DOC/PPTX/PPT) → PDF via LibreOffice
        headless (F-3.2). Hasil di-cache; konversi ulang dilewati bila masih baru.
        """
        if not self._soffice.tersedia:
            raise RenderError(
                "LibreOffice tidak ditemukan. Instal LibreOffice untuk preview "
                "DOCX/PPTX, atau buka dokumen di aplikasi aslinya."
            )
        target = self.cache_dir / (path.stem + ".pdf")
        if target.exists() and target.stat().st_mtime >= path.stat().st_mtime:
            return target  # cache masih valid

        cmd = [
            self._soffice.path,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(self.cache_dir),
            str(path),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=180)
        except subprocess.TimeoutExpired as exc:
            raise RenderError("Konversi dokumen terlalu lama (timeout).") from exc
        except subprocess.CalledProcessError as exc:
            raise RenderError(
                f"Gagal mengonversi dokumen: {exc.stderr.decode('utf-8', 'ignore')}"
            ) from exc
        if not target.exists():
            raise RenderError("Konversi selesai tetapi berkas PDF tidak ditemukan.")
        return target
