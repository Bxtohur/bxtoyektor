"""Jendela Presentasi / Proyektor (PRD F-4.2, §9.2).

Tampilan bersih & besar untuk asesor: hanya dokumen/video aktif, tanpa kontrol
pencarian. Header tipis (nama dokumen) bisa disembunyikan untuk mode benar-benar
bersih. Bisa fullscreen (F11) dan mode kiosk (F-4.5).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from .widgets.preview_panel import PreviewPanel


class PresentationWindow(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Presentasi — Bukti Fisik")
        self.setStyleSheet("background:#111; color:#eee;")

        self._header = QLabel("")
        self._header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._header.setStyleSheet(
            "padding:8px; font-size:18px; font-weight:600; background:#000; color:#fff;"
        )
        # Proyektor: tanpa kontrol video & TANPA scrollbar (tampilan benar-benar
        # bersih/fullscreen). Posisi scroll tetap mengikuti operator secara programatik.
        self.preview = PreviewPanel(kontrol_video=False, scrollbar=False)
        self.preview.setStyleSheet("background:#111; border:none;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._header)
        layout.addWidget(self.preview, 1)

        # Header ditampilkan saat mode jendela (untuk pengecekan operator),
        # tetapi otomatis DISEMBUNYIKAN saat fullscreen agar proyektor bersih total.
        self._header_diminta = True

        # Pintasan: F11 fullscreen, Esc keluar fullscreen, H toggle header (mode jendela).
        QShortcut(QKeySequence(Qt.Key.Key_F11), self, self.toggle_fullscreen)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self.keluar_fullscreen)
        QShortcut(QKeySequence(Qt.Key.Key_H), self, self.toggle_header)

    def set_judul(self, teks: str) -> None:
        self._header.setText(teks)

    def toggle_header(self) -> None:
        self._header_diminta = not self._header_diminta
        self._perbarui_header()

    def _perbarui_header(self) -> None:
        # Saat fullscreen: selalu tersembunyi (tampilan bersih untuk asesor).
        self._header.setVisible(self._header_diminta and not self.isFullScreen())

    def changeEvent(self, event) -> None:  # noqa: N802 (override Qt)
        super().changeEvent(event)
        if event.type() == event.Type.WindowStateChange:
            self._perbarui_header()

    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def keluar_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()

    def set_kiosk(self, aktif: bool) -> None:
        """Mode kiosk (F-4.5): sembunyikan title bar untuk tampilan bersih."""
        flags = self.windowFlags()
        if aktif:
            flags |= Qt.WindowType.FramelessWindowHint
        else:
            flags &= ~Qt.WindowType.FramelessWindowHint
        self.setWindowFlags(flags)
        self.show()
