"""Widget penampil dokumen (PRD F-3.1, F-3.4, F-4.4).

Dua mode:
- **continuous** (PDF/DOCX): semua halaman ditumpuk vertikal, bisa di-scroll & zoom.
- **slideshow** (PPTX/PPT): satu slide penuh per layar (fit ke layar, letterbox),
  ganti slide dengan next/prev — seperti mode Show di PowerPoint. Tanpa scroll.

Halaman dirender LAZY (hanya yang terlihat) agar dokumen besar tetap responsif.

Meng-emit:
- `state_berubah(fraksi_v, fraksi_h, zoom)` — sinkronisasi PERSIS ke proyektor (F-4.4).
  Continuous: posisi scroll vertikal/horizontal (fraksi 0..1) + zoom relatif.
  Slideshow: `fraksi_v` membawa progres slide (indeks/(total-1)); fraksi_h & zoom
  diabaikan. Karena operator & proyektor memakai mode yang sama, maknanya konsisten.
- `halaman_berubah(indeks, total)` — halaman/slide aktif, untuk UI.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QPainter, QPixmap
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from ...render.document_renderer import RenderedDocument

_SPACING = 12          # jarak antar halaman (px) — mode continuous
_BUFFER_LAYAR = 1.0    # render halaman sejauh ±1 tinggi viewport dari area terlihat
_SOROT = QColor(255, 214, 0, 110)       # sorotan hasil cari
_SOROT_AKTIF = QColor(255, 140, 0, 150)  # sorotan hasil cari yang aktif


class _PageLabel(QLabel):
    """Label satu halaman yang tahu indeksnya & meneruskan event mouse (px lokal)."""

    diklik = Signal(int, float, float)   # (indeks, x_px, y_px)
    digerak = Signal(int, float, float)  # (indeks, x_px, y_px) untuk kursor link

    def __init__(self, indeks: int) -> None:
        super().__init__()
        self._indeks = indeks
        self.setMouseTracking(True)

    def mousePressEvent(self, e) -> None:  # noqa: N802
        p = e.position()
        self.diklik.emit(self._indeks, p.x(), p.y())

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        p = e.position()
        self.digerak.emit(self._indeks, p.x(), p.y())


class DocumentViewer(QScrollArea):
    state_berubah = Signal(float, float, float)  # (fraksi_v, fraksi_h, zoom_relatif)
    halaman_berubah = Signal(int, int)           # (indeks_aktif, total)
    buka_url = Signal(str)                        # link PDF diklik
    match_berubah = Signal(int, int)             # (indeks_hasil_cari+1, total)

    def __init__(self, sembunyikan_scrollbar: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._doc: RenderedDocument | None = None
        self._zoom = 1.0
        self._fit_lebar = True
        self._slideshow = False
        self._slide = 0
        self._labels: list[QLabel] = []
        self._rendered: set[int] = set()
        self._suppress = False  # cegah loop saat menerapkan state dari luar
        self._matches: list[tuple[int, tuple]] = []  # hasil cari: (page, rect PDF)
        self._match_idx = -1
        # Fraksi horizontal yang diinginkan, diterapkan saat range hbar sudah ada
        # (mengatasi race: range belum terhitung tepat setelah zoom/layout).
        self._target_h: float | None = None

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
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if sembunyikan_scrollbar:
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.horizontalScrollBar().valueChanged.connect(self._on_scroll)
        # Pusatkan horizontal begitu range-nya diketahui (mis. setelah zoom/layout).
        self.horizontalScrollBar().rangeChanged.connect(self._on_hrange)

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
        """Zoom relatif terhadap fit-lebar (1.0 = pas lebar layar)."""
        if self._slideshow:
            return 1.0
        fit = self._hitung_zoom_fit()
        return self._zoom / fit if fit > 0 else 1.0

    @property
    def fraksi_scroll(self) -> float:
        if self._slideshow:
            n = self.jumlah_halaman
            return self._slide / (n - 1) if n > 1 else 0.0
        bar = self.verticalScrollBar()
        return bar.value() / bar.maximum() if bar.maximum() > 0 else 0.0

    @property
    def fraksi_scroll_h(self) -> float:
        if self._slideshow:
            return 0.0
        bar = self.horizontalScrollBar()
        return bar.value() / bar.maximum() if bar.maximum() > 0 else 0.0

    @property
    def halaman_aktif(self) -> int:
        return self._slide if self._slideshow else self._halaman_teratas()

    # ---- API tampil ----------------------------------------------------
    def tampilkan(
        self,
        doc: RenderedDocument | None,
        fraksi: float = 0.0,
        zoom: float | None = None,
        slideshow: bool = False,
    ) -> None:
        if self._doc is not None:
            self._doc.close()
        self._doc = doc
        self._slideshow = slideshow
        self._slide = 0
        self._matches = []
        self._match_idx = -1
        self._bersihkan_labels()
        if doc is None or doc.jumlah_halaman == 0:
            self.kosongkan()
            return
        # Mode slideshow: satu slide fit-layar & tengah; mode continuous: fit-lebar & atas.
        if slideshow:
            self._vbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._fit_lebar = False
            # Pulihkan slide terakhir (fraksi = slide/(total-1)).
            n = doc.jumlah_halaman
            self._slide = round(fraksi * (n - 1)) if n > 1 else 0
        else:
            self._vbox.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            self._fit_lebar = zoom is None
            if zoom is not None:
                self._zoom = zoom
        self._bangun_halaman()
        # Continuous (PDF): target di tengah horizontal (0.5).
        self._target_h = None if slideshow else 0.5
        self._tata_ukuran()
        QTimer.singleShot(0, lambda: self._set_fraksi(fraksi))

    def kosongkan(self, pesan: str = "Belum ada dokumen dipilih.") -> None:
        if self._doc is not None:
            self._doc.close()
            self._doc = None
        self._bersihkan_labels()
        self._kosong.setText(pesan)
        self._kosong.show()

    # ---- navigasi ------------------------------------------------------
    def set_halaman(self, indeks: int) -> None:
        if not self._doc or not self._labels:
            return
        indeks = max(0, min(indeks, len(self._labels) - 1))
        if self._slideshow:
            if indeks != self._slide or indeks not in self._rendered:
                self._slide = indeks
                self._tata_ukuran()
                self._emit_state()
            return
        y = self._labels[indeks].pos().y() - 8
        self.verticalScrollBar().setValue(max(0, y))

    def halaman_berikutnya(self) -> None:
        self.set_halaman(self.halaman_aktif + 1)

    def halaman_sebelumnya(self) -> None:
        self.set_halaman(self.halaman_aktif - 1)

    def zoom_in(self) -> None:
        if not self._slideshow:
            self._set_zoom(self._zoom * 1.25)

    def zoom_out(self) -> None:
        if not self._slideshow:
            self._set_zoom(self._zoom / 1.25)

    def fit_to_window(self) -> None:
        if self._slideshow:
            self._tata_ukuran()
            return
        self._fit_lebar = True
        self._tata_ukuran()
        self._emit_state()

    def terapkan_state(self, fraksi_v: float, fraksi_h: float, zoom_relatif: float) -> None:
        """Diterapkan window_manager agar proyektor mengikuti operator (F-4.4)."""
        if not self._doc:
            return
        self._suppress = True
        try:
            self._target_h = fraksi_h  # posisi horizontal dari sinkronisasi
            if self._slideshow:
                n = self.jumlah_halaman
                target = round(fraksi_v * (n - 1)) if n > 1 else 0
                if target != self._slide:
                    self._slide = target
                    self._tata_ukuran()
                return
            fit = self._hitung_zoom_fit()
            if abs(zoom_relatif - 1.0) < 0.02:
                if not self._fit_lebar or abs(self._zoom - fit) > 1e-3:
                    self._fit_lebar = True
                    self._tata_ukuran()
            else:
                target_zoom = zoom_relatif * fit
                if abs(target_zoom - self._zoom) > 1e-3:
                    self._fit_lebar = False
                    self._zoom = target_zoom
                    self._tata_ukuran()
            self._set_fraksi(fraksi_v)
            self._terapkan_target_h()  # segera bila range sudah ada
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
        for i in range(self._doc.jumlah_halaman):
            lbl = _PageLabel(i)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("background:#fff;" if not self._slideshow else "background:transparent;")
            lbl.diklik.connect(self._klik_halaman)
            lbl.digerak.connect(self._hover_halaman)
            self._vbox.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignCenter)
            if self._slideshow and i != self._slide:
                lbl.hide()
            self._labels.append(lbl)

    def _hitung_zoom_fit(self) -> float:
        """Zoom agar LEBAR halaman pas viewport (mode continuous)."""
        assert self._doc is not None
        w, _ = self._doc.ukuran_halaman(0, zoom=1.0)
        if w <= 0:
            return 1.0
        lebar_vp = self.viewport().width() - 2 * _SPACING - 16
        return max(0.1, lebar_vp / w)

    def _hitung_zoom_fit_page(self, indeks: int) -> float:
        """Zoom agar SELURUH halaman pas viewport (mode slideshow, letterbox)."""
        assert self._doc is not None
        w, h = self._doc.ukuran_halaman(indeks, zoom=1.0)
        if w <= 0 or h <= 0:
            return 1.0
        vp_w = self.viewport().width() - 16
        vp_h = self.viewport().height() - 16
        return max(0.05, min(vp_w / w, vp_h / h))

    def _tata_ukuran(self) -> None:
        if not self._doc:
            return
        if self._slideshow:
            self._zoom = self._hitung_zoom_fit_page(self._slide)
            for i, lbl in enumerate(self._labels):
                if i == self._slide:
                    w, h = self._doc.ukuran_halaman(i, zoom=self._zoom)
                    lbl.setFixedSize(w, h)
                    lbl.show()
                else:
                    lbl.hide()
            self._rendered.discard(self._slide)  # paksa render ulang di ukuran baru
            self._render_terlihat()
            return
        if self._fit_lebar:
            self._zoom = self._hitung_zoom_fit()
        for i, lbl in enumerate(self._labels):
            w, h = self._doc.ukuran_halaman(i, zoom=self._zoom)
            lbl.setFixedSize(w, h)
            lbl.setPixmap(QPixmap())
        self._rendered.clear()
        self._render_terlihat()

    def _set_zoom(self, z: float) -> None:
        self._fit_lebar = False
        self._zoom = max(0.1, min(z, 8.0))
        fraksi_v = self.fraksi_scroll
        self._target_h = 0.5  # tetap di tengah horizontal setelah zoom
        self._tata_ukuran()
        QTimer.singleShot(0, lambda: self._set_fraksi(fraksi_v))
        self._emit_state()

    def _set_fraksi(self, fraksi_v: float) -> None:
        """Set posisi scroll VERTIKAL. Horizontal ditangani via `_target_h`."""
        if self._slideshow:
            self._render_terlihat()
            return
        vbar = self.verticalScrollBar()
        vbar.setValue(int(max(0.0, min(fraksi_v, 1.0)) * vbar.maximum()))
        self._terapkan_target_h()
        self._render_terlihat()

    def _terapkan_target_h(self) -> None:
        """Terapkan posisi horizontal yang diinginkan bila range sudah tersedia."""
        if self._target_h is None:
            return
        hbar = self.horizontalScrollBar()
        if hbar.maximum() > 0:
            hbar.setValue(int(max(0.0, min(self._target_h, 1.0)) * hbar.maximum()))
            self._target_h = None

    def _on_hrange(self, _min: int, _maks: int) -> None:
        """Range horizontal berubah (mis. setelah zoom/layout) → terapkan target."""
        self._terapkan_target_h()

    # ---- internal: scroll & render lazy -------------------------------
    def _on_scroll(self, _value: int) -> None:
        self._render_timer.start()
        self._emit_state()

    def _emit_state(self) -> None:
        if self._suppress or not self._doc:
            return
        self.state_berubah.emit(self.fraksi_scroll, self.fraksi_scroll_h, self.zoom_relatif)
        self.halaman_berubah.emit(self.halaman_aktif, self.jumlah_halaman)

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
        if self._slideshow:
            if self._slide not in self._rendered:
                self._render_ke_label(self._slide)
                self._rendered = {self._slide}  # cukup simpan slide aktif
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
                self._render_ke_label(i)
                self._rendered.add(i)
            elif not terlihat and i in self._rendered:
                lbl.setPixmap(QPixmap())
                self._rendered.discard(i)

    def _render_ke_label(self, i: int) -> None:
        """Render halaman i (dgn sorotan hasil cari bila ada) ke labelnya."""
        img = self._doc.halaman(i, zoom=self._zoom)
        sorot = [(idx, m) for idx, (p, m) in enumerate(self._matches) if p == i]
        if sorot:
            painter = QPainter(img)
            for idx, rect in sorot:
                x0, y0, x1, y1 = rect
                warna = _SOROT_AKTIF if idx == self._match_idx else _SOROT
                painter.fillRect(
                    int(x0 * self._zoom), int(y0 * self._zoom),
                    max(1, int((x1 - x0) * self._zoom)), max(1, int((y1 - y0) * self._zoom)),
                    warna,
                )
            painter.end()
        self._labels[i].setPixmap(QPixmap.fromImage(img))

    def resizeEvent(self, event) -> None:  # noqa: N802 (override Qt)
        super().resizeEvent(event)
        if not self._doc:
            return
        if self._slideshow or self._fit_lebar:
            self._tata_ukuran()
        else:
            self._render_terlihat()

    def wheelEvent(self, event) -> None:  # noqa: N802 (override Qt)
        # Slideshow: roda mouse = ganti slide. Continuous: Ctrl+roda = zoom.
        if self._doc and self._slideshow:
            if event.angleDelta().y() < 0:
                self.halaman_berikutnya()
            else:
                self.halaman_sebelumnya()
            event.accept()
            return
        if self._doc and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom_in() if event.angleDelta().y() > 0 else self.zoom_out()
            event.accept()
            return
        super().wheelEvent(event)

    # ---- Link PDF -----------------------------------------------------
    def _link_di(self, i: int, x_px: float, y_px: float) -> dict | None:
        if not self._doc:
            return None
        px, py = x_px / self._zoom, y_px / self._zoom  # px → titik PDF
        for lnk in self._doc.links(i):
            x0, y0, x1, y1 = lnk["rect"]
            if x0 <= px <= x1 and y0 <= py <= y1:
                return lnk
        return None

    def _klik_halaman(self, i: int, x: float, y: float) -> None:
        lnk = self._link_di(i, x, y)
        if lnk is None:
            return
        if lnk.get("uri"):
            self.buka_url.emit(lnk["uri"])
        elif lnk.get("page") is not None:
            self.set_halaman(int(lnk["page"]))

    def _hover_halaman(self, i: int, x: float, y: float) -> None:
        di_link = self._link_di(i, x, y) is not None
        self._labels[i].setCursor(
            QCursor(Qt.CursorShape.PointingHandCursor if di_link else Qt.CursorShape.ArrowCursor)
        )

    # ---- Cari di dalam dokumen ----------------------------------------
    def cari_dalam(self, teks: str) -> None:
        """Cari teks di dalam dokumen; sorot semua & lompat ke hasil pertama."""
        self._matches = self._doc.cari_teks(teks) if self._doc else []
        self._match_idx = 0 if self._matches else -1
        self._rendered.clear()
        self._render_terlihat()
        if self._matches:
            self._ke_match(0)
        self.match_berubah.emit(self._match_idx + 1, len(self._matches))

    def match_berikutnya(self) -> None:
        self._geser_match(1)

    def match_sebelumnya(self) -> None:
        self._geser_match(-1)

    def _geser_match(self, arah: int) -> None:
        if not self._matches:
            return
        self._match_idx = (self._match_idx + arah) % len(self._matches)
        self._ke_match(self._match_idx)
        self.match_berubah.emit(self._match_idx + 1, len(self._matches))

    def _ke_match(self, idx: int) -> None:
        page, (x0, y0, x1, y1) = self._matches[idx]
        self._rendered.discard(page)  # gambar ulang agar sorotan aktif terlihat
        if self._slideshow:
            self.set_halaman(page)
        else:
            self.set_halaman(page)
            target = self._labels[page].pos().y() + int(y0 * self._zoom) - 60
            self.verticalScrollBar().setValue(max(0, target))
        self._render_terlihat()
