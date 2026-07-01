"""Worker thread untuk operasi berat (AGENTS.md §6, PRD non-fungsional).

Baca Excel & render dokumen TIDAK boleh berjalan di UI thread. Modul ini
membungkusnya sebagai QRunnable + sinyal, dijalankan lewat QThreadPool.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Signal

from ..data.excel_reader import HasilImport, baca_excel
from ..data.folder_scanner import HasilScan, scan_folder
from ..data.models import DocumentItem
from ..render.document_renderer import DocumentRenderer, RenderedDocument


class _Sinyal(QObject):
    selesai = Signal(object)
    gagal = Signal(str)


class ImportExcelWorker(QRunnable):
    """Baca file Excel di background."""

    def __init__(self, path: str | Path) -> None:
        super().__init__()
        self._path = path
        self.sinyal = _Sinyal()

    def run(self) -> None:  # noqa: D401
        try:
            hasil: HasilImport = baca_excel(self._path)
            self.sinyal.selesai.emit(hasil)
        except Exception as exc:  # noqa: BLE001 — laporkan jelas ke UI
            self.sinyal.gagal.emit(str(exc))


class ScanFolderWorker(QRunnable):
    """Pindai folder rekursif di background (mode sumber folder besar)."""

    def __init__(self, path: str | Path) -> None:
        super().__init__()
        self._path = path
        self.sinyal = _Sinyal()

    def run(self) -> None:
        try:
            hasil: HasilScan = scan_folder(self._path)
            self.sinyal.selesai.emit(hasil)
        except Exception as exc:  # noqa: BLE001
            self.sinyal.gagal.emit(str(exc))


class RenderWorker(QRunnable):
    """Render satu dokumen di background."""

    def __init__(self, renderer: DocumentRenderer, item: DocumentItem) -> None:
        super().__init__()
        self._renderer = renderer
        self._item = item
        self.sinyal = _Sinyal()

    def run(self) -> None:
        try:
            doc: RenderedDocument = self._renderer.render(self._item)
            self.sinyal.selesai.emit(doc)
        except Exception as exc:  # noqa: BLE001
            self.sinyal.gagal.emit(str(exc))
