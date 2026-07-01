"""Widget penampil dokumen scroll-menerus (PRD F-3.1, F-3.4, F-4.4).

Menampilkan seluruh halaman dokumen ditumpuk vertikal seperti PDF viewer biasa:
bisa di-scroll bebas, zoom, dan lompat halaman. Halaman dirender LAZY (hanya yang
terlihat) agar dokumen besar tetap responsif.

Meng-emit:
- `state_berubah(fraksi_scroll, zoom)` — untuk sinkronisasi PERSIS ke jendela
  proyektor (F-4.4): posisi scroll dinyatakan sebagai fraksi 0..1 dari total tinggi
  dokumen sehingga tetap sinkron walau ukuran layar berbeda.
- `halaman_berubah(indeks_atas, total)` — halaman teratas yang terlihat, untuk UI.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from ...render.document_renderer import RenderedDocument

_SPACING = 12          # jarak antar halaman (px)
_BUFFER_LAYAR = 1.0    # render halaman sejauh ±1 tinggi viewport dari area terlihat


class DocumentViewer(QScrollArea):
    state_berubah = Signal(float, float)   # (fraksi_scroll 0..1, zoom)
    halaman_berubah = Signal(int, int)     # (indeks_halaman_atas, total)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._doc: RenderedDocument | None = None
        self._zoom = 1.0
        self._fit_lebar = True
        self._labels: list[QLabel] = []
        self._rendered: set[int] = set()
        self._suppress = False  # cegah loop saat menerapkan state dari luar

        self._container = QWidget()
        self._vbox = QVBoxLayout(self._container)
        self._vbox.setSpacing(_SPACING)
        self._vbox.setContentsMargins(8, 8, 8, 8)
        self._vbox.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self._kosong = QLabel("Belum ada dokumen dipilih.")
        self._kosong.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._vbox.addWidget(self._kosong)

        self.setWidget(self._container)
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

        # Debounce render saat scroll cepat.
        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(30)
        self._render_timer.timeout.connect(self._render_terlihat)

    # ---- properti publik ----------------------------------------------
    @property
    def jumlah_halaman(self) -> int:
        return self._doc.jumlah_halaman if self._doc else 0

    @property
    def zoom(self) -> float:
        return self._zoom

    @property
    def zoom_relatif(self) -> float:
        """Zoom relatif terhadap fit-lebar (1.0 = pas lebar layar).

        Dipakai untuk sync ke proyektor agar 'fit' tetap 'fit' & kelipatan zoom
        sama, meski lebar layar operator ≠ proyektor.
        """
        fit = self._hitung_zoom_fit()
        return self._zoom / fit if fit > 0 else 1.0

    @property
    def fraksi_scroll(self) -> float:
        bar = self.verticalScrollBar()
        return bar.value() / bar.maximum() if bar.maximum() > 0 else 0.0

    @property
    def halaman_aktif(self) -> int:
        return self._halaman_teratas()

    # ---- API tampil ----------------------------------------------------
    def tampilkan(self, doc: RenderedDocument | None, fraksi: float = 0.0, zoom: float | None = None) -> None:
        if self._doc is not None:
            self._doc.close()
        self._doc = doc
        self._bersihkan_labels()
        if doc is None or doc.jumlah_halaman == 0:
            self.kosongkan()
            return
        self._fit_lebar = zoom is None
        if zoom is not None:
            self._zoom = zoom
        self._bangun_halaman()
        self._tata_ukuran()
        # Setelah layout siap, terapkan posisi scroll awal.
        QTimer.singleShot(0, lambda: self._set_fraksi(fraksi))

    def kosongkan(self, pesan: str = "Belum ada dokumen dipilih.") -> None:
        if self._doc is not None:
            self._doc.close()
            self._doc = None
        self._bersihkan_labels()
        # _kosong tetap berada di layout sejak __init__; cukup tampilkan lagi.
        self._kosong.setText(pesan)
        self._kosong.show()

    # ---- navigasi ------------------------------------------------------
    def set_halaman(self, indeks: int) -> None:
        if not self._doc or not self._labels:
            return
        indeks = max(0, min(indeks, len(self._labels) - 1))
        y = self._labels[indeks].pos().y() - 8
        self.verticalScrollBar().setValue(max(0, y))

    def halaman_berikutnya(self) -> None:
        self.set_halaman(self._halaman_teratas() + 1)

    def halaman_sebelumnya(self) -> None:
        self.set_halaman(self._halaman_teratas() - 1)

    def zoom_in(self) -> None:
        self._set_zoom(self._zoom * 1.25)

    def zoom_out(self) -> None:
        self._set_zoom(self._zoom / 1.25)

    def fit_to_window(self) -> None:
        self._fit_lebar = True
        self._tata_ukuran()
        self._emit_state()

    def terapkan_state(self, fraksi: float, zoom_relatif: float) -> None:
        """Diterapkan oleh window_manager agar proyektor mengikuti operator (F-4.4).

        `zoom_relatif` ditafsirkan relatif terhadap fit-lebar LAYAR INI, sehingga
        posisi & tingkat zoom sama persis walau ukuran layar berbeda. Tidak
        meng-emit sinyal agar tidak terjadi loop sinkronisasi.
        """
        if not self._doc:
            return
        self._suppress = True
        try:
            fit = self._hitung_zoom_fit()
            if abs(zoom_relatif - 1.0) < 0.02:
                if not self._fit_lebar or abs(self._zoom - fit) > 1e-3:
                    self._fit_lebar = True
                    self._tata_ukuran()
            else:
                target = zoom_relatif * fit
                if abs(target - self._zoom) > 1e-3:
                    self._fit_lebar = False
                    self._zoom = target
                    self._tata_ukuran()
            self._set_fraksi(fraksi)
        finally:
            self._suppress = False

    # ---- internal: bangun & tata --------------------------------------
    def _bersihkan_labels(self) -> None:
        self._kosong.hide()
        for lbl in self._labels:
            self._vbox.removeWidget(lbl)
            lbl.deleteLater()
        self._labels.clear()
        self._rendered.clear()

    def _bangun_halaman(self) -> None:
        assert self._doc is not None
        for _ in range(self._doc.jumlah_halaman):
            lbl = QLabel()
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("background:#fff;")
            self._vbox.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignHCenter)
            self._labels.append(lbl)

    def _hitung_zoom_fit(self) -> float:
        assert self._doc is not None
        w, _ = self._doc.ukuran_halaman(0, zoom=1.0)
        if w <= 0:
            return 1.0
        lebar_vp = self.viewport().width() - 2 * _SPACING - 16
        return max(0.1, lebar_vp / w)

    def _tata_ukuran(self) -> None:
        if not self._doc:
            return
        if self._fit_lebar:
            self._zoom = self._hitung_zoom_fit()
        for i, lbl in enumerate(self._labels):
            w, h = self._doc.ukuran_halaman(i, zoom=self._zoom)
            lbl.setFixedSize(w, h)
            lbl.setPixmap(QPixmap())  # placeholder; akan dirender lazy
        self._rendered.clear()
        self._render_terlihat()

    def _set_zoom(self, z: float) -> None:
        self._fit_lebar = False
        self._zoom = max(0.1, min(z, 8.0))
        fraksi = self.fraksi_scroll
        self._tata_ukuran()
        QTimer.singleShot(0, lambda: self._set_fraksi(fraksi))
        self._emit_state()  # penting: agar zoom ikut tersinkron ke proyektor

    def _set_fraksi(self, fraksi: float) -> None:
        bar = self.verticalScrollBar()
        bar.setValue(int(max(0.0, min(fraksi, 1.0)) * bar.maximum()))
        self._render_terlihat()

    # ---- internal: scroll & render lazy -------------------------------
    def _on_scroll(self, _value: int) -> None:
        self._render_timer.start()
        self._emit_state()

    def _emit_state(self) -> None:
        if self._suppress or not self._doc:
            return
        self.state_berubah.emit(self.fraksi_scroll, self.zoom_relatif)
        self.halaman_berubah.emit(self._halaman_teratas(), self.jumlah_halaman)

    def _halaman_teratas(self) -> int:
        if not self._labels:
            return 0
        y = self.verticalScrollBar().value()
        for i, lbl in enumerate(self._labels):
            if lbl.pos().y() + lbl.height() >= y:
                return i
        return len(self._labels) - 1

    def _render_terlihat(self) -> None:
        if not self._doc or not self._labels:
            return
        vp = self.viewport().height()
        atas = self.verticalScrollBar().value()
        buffer = int(vp * _BUFFER_LAYAR)
        y0, y1 = atas - buffer, atas + vp + buffer
        for i, lbl in enumerate(self._labels):
            top = lbl.pos().y()
            bawah = top + lbl.height()
            terlihat = bawah >= y0 and top <= y1
            if terlihat and i not in self._rendered:
                img = self._doc.halaman(i, zoom=self._zoom)
                lbl.setPixmap(QPixmap.fromImage(img))
                self._rendered.add(i)
            elif not terlihat and i in self._rendered:
                lbl.setPixmap(QPixmap())  # bebaskan memori halaman jauh
                self._rendered.discard(i)

    def resizeEvent(self, event) -> None:  # noqa: N802 (override Qt)
        super().resizeEvent(event)
        if self._fit_lebar and self._doc:
            self._tata_ukuran()
        else:
            self._render_terlihat()

    def wheelEvent(self, event) -> None:  # noqa: N802 (override Qt)
        """Ctrl + roda mouse = zoom (seperti PDF viewer umumnya)."""
        if self._doc and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
            event.accept()
            return
        super().wheelEvent(event)
