"""Penampil berbagi layar / window (live screen share).

Menampilkan tangkapan LANGSUNG dari seluruh layar (QScreenCapture) atau satu
window tertentu (QWindowCapture) melalui QMediaCaptureSession → QVideoWidget.
Dipakai di panel operator (pratinjau) maupun jendela proyektor. Masing-masing
memakai sesi tangkapan sendiri agar bisa tampil di dua jendela sekaligus.

Catatan: berbagi "seluruh layar" yang sama dengan layar tempat jendela ini berada
akan menimbulkan efek cermin tak hingga — pilih layar operator, tampilkan di layar
proyektor.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QScreen
from PySide6.QtMultimedia import (
    QCapturableWindow,
    QMediaCaptureSession,
    QScreenCapture,
    QWindowCapture,
)
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QVBoxLayout, QWidget


class ScreenShareViewer(QWidget):
    error = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background:#000;")
        self._session = QMediaCaptureSession(self)
        self._screen_cap = QScreenCapture(self)
        self._window_cap = QWindowCapture(self)
        self._video = QVideoWidget(self)
        self._session.setVideoOutput(self._video)

        self._screen_cap.errorOccurred.connect(
            lambda _e, s: self.error.emit(s or "Gagal berbagi layar.")
        )
        self._window_cap.errorOccurred.connect(
            lambda _e, s: self.error.emit(s or "Gagal berbagi window.")
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._video)

    # ---- API publik ----------------------------------------------------
    def share_screen(self, screen: QScreen) -> None:
        self._window_cap.setActive(False)
        self._session.setWindowCapture(None)
        self._screen_cap.setScreen(screen)
        self._session.setScreenCapture(self._screen_cap)
        self._screen_cap.setActive(True)

    def share_window(self, window: QCapturableWindow) -> None:
        self._screen_cap.setActive(False)
        self._session.setScreenCapture(None)
        self._window_cap.setWindow(window)
        self._session.setWindowCapture(self._window_cap)
        self._window_cap.setActive(True)

    def stop(self) -> None:
        self._screen_cap.setActive(False)
        self._window_cap.setActive(False)

    @staticmethod
    def daftar_window() -> list[QCapturableWindow]:
        """Window yang bisa ditangkap (punya .description())."""
        return list(QWindowCapture.capturableWindows())
