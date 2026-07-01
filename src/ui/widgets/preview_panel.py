"""Panel pratinjau terpadu (dokumen halaman ATAU video).

Menggabungkan DocumentViewer (pdf/docx/pptx/gambar) dan VideoViewer (video)
dalam satu QStackedWidget dengan API seragam. Dipakai baik di panel operator
maupun jendela proyektor, sehingga alur 2 langkah & sinkronisasi konsisten.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QStackedWidget, QVBoxLayout, QWidget

from ...data.models import MediaKind
from ...render.document_renderer import RenderedDocument
from .document_viewer import DocumentViewer
from .video_viewer import VideoViewer


class PreviewPanel(QWidget):
    # Diteruskan dari DocumentViewer untuk sinkronisasi PERSIS (F-4.4).
    state_berubah = Signal(float, float)   # (fraksi_scroll, zoom)
    halaman_berubah = Signal(int, int)     # (indeks_halaman_atas, total)

    def __init__(self, kontrol_video: bool = True, parent=None) -> None:
        super().__init__(parent)
        self.doc_viewer = DocumentViewer()
        self.video_viewer = VideoViewer(kontrol=kontrol_video)
        self._pesan = QLabel("Belum ada dokumen dipilih.")
        self._pesan.setWordWrap(True)
        self._pesan.setStyleSheet("padding:24px; color:#666;")

        self._stack = QStackedWidget()
        self._stack.addWidget(self.doc_viewer)    # index 0
        self._stack.addWidget(self.video_viewer)  # index 1
        self._stack.addWidget(self._pesan)         # index 2

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)

        self._kind: MediaKind = MediaKind.LAINNYA
        self.doc_viewer.state_berubah.connect(self.state_berubah)
        self.doc_viewer.halaman_berubah.connect(self.halaman_berubah)

    @property
    def kind(self) -> MediaKind:
        return self._kind

    def tampilkan_paged(self, doc: RenderedDocument, fraksi: float = 0.0, zoom: float | None = None) -> None:
        self.video_viewer.stop()
        self._kind = MediaKind.PAGED
        self.doc_viewer.tampilkan(doc, fraksi=fraksi, zoom=zoom)
        self._stack.setCurrentWidget(self.doc_viewer)

    def tampilkan_video(self, path: str | Path, auto_play: bool = True) -> None:
        self._kind = MediaKind.VIDEO
        self.doc_viewer.kosongkan()
        self.video_viewer.putar(path, auto_play=auto_play)
        self._stack.setCurrentWidget(self.video_viewer)

    def kosongkan(self, pesan: str = "Belum ada dokumen dipilih.") -> None:
        self.video_viewer.stop()
        self.doc_viewer.kosongkan()
        self._kind = MediaKind.LAINNYA
        self._pesan.setText(pesan)
        self._stack.setCurrentWidget(self._pesan)
