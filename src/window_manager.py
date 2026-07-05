"""Window Manager (PRD §8.2, F-4.1/F-4.3/F-4.4).

Mengoordinasikan jendela operator & jendela presentasi lewat Qt signal/slot
(bukan browser messaging seperti versi web). Tanggung jawab:
- deteksi monitor kedua & posisikan jendela presentasi (F-4.1),
- mendorong dokumen aktif ke proyektor SETELAH konfirmasi operator (F-4.3),
- sinkronisasi halaman/zoom real-time yang bisa di-toggle (F-4.4).
"""
from __future__ import annotations

from PySide6.QtCore import QObject, QTimer
from PySide6.QtGui import QGuiApplication, QScreen

from .render.document_renderer import RenderedDocument
from .ui.presentation_window import PresentationWindow
from .ui.widgets.preview_panel import PreviewPanel


class WindowManager(QObject):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.presentation: PresentationWindow | None = None
        self._sync_aktif = True
        self._operator_panel: PreviewPanel | None = None
        self._video_mirror_terpasang = False
        # Identitas file yang sedang dilihat operator vs yang tampil di proyektor.
        # Sinkronisasi hanya berlaku bila keduanya SAMA — supaya memilih file baru
        # di operator TIDAK menggeser proyektor sampai ditekan "Tampilkan ke Proyektor".
        self._id_operator: str | None = None
        self._id_proyektor: str | None = None

    # ---- deteksi monitor (F-4.1) --------------------------------------
    @staticmethod
    def monitor_sekunder() -> QScreen | None:
        """Monitor selain layar utama, bila ada (proyektor)."""
        primary = QGuiApplication.primaryScreen()
        for scr in QGuiApplication.screens():
            if scr is not primary:
                return scr
        return None

    @staticmethod
    def daftar_monitor() -> list[QScreen]:
        return list(QGuiApplication.screens())

    # ---- siklus hidup jendela presentasi ------------------------------
    def buka_presentasi(self, monitor_index: int = -1) -> PresentationWindow:
        """Buka (atau fokuskan) jendela presentasi di monitor tujuan.

        monitor_index = -1 → deteksi otomatis monitor sekunder.
        """
        if self.presentation is None:
            self.presentation = PresentationWindow()

        screens = self.daftar_monitor()
        target: QScreen | None = None
        if 0 <= monitor_index < len(screens):
            target = screens[monitor_index]
        else:
            target = self.monitor_sekunder()

        win = self.presentation
        if target is not None:
            geo = target.geometry()
            win.move(geo.topLeft())
            win.resize(geo.width(), geo.height())
        win.show()
        if target is not None:
            win.showFullScreen()
        return win

    def tutup_presentasi(self) -> None:
        if self.presentation is not None:
            self.presentation.close()
            self.presentation = None

    @property
    def presentasi_terbuka(self) -> bool:
        return self.presentation is not None and self.presentation.isVisible()

    # ---- sinkronisasi (F-4.3 / F-4.4) ---------------------------------
    def hubungkan_operator(self, panel: PreviewPanel) -> None:
        """Sambungkan panel operator agar perubahannya bisa disinkronkan."""
        self._operator_panel = panel
        panel.state_berubah.connect(self._on_operator_state_berubah)

    def set_sync(self, aktif: bool) -> None:
        self._sync_aktif = aktif

    @property
    def sync_aktif(self) -> bool:
        return self._sync_aktif

    def set_item_operator(self, item_id: str | None) -> None:
        """Catat file yang sedang dilihat operator (dipanggil saat pilih hasil)."""
        self._id_operator = item_id

    def _boleh_sinkron(self) -> bool:
        """Sync hanya bila proyektor terbuka & file operator == file proyektor."""
        return (
            self._sync_aktif
            and self.presentasi_terbuka
            and self._id_proyektor is not None
            and self._id_operator == self._id_proyektor
        )

    def tampilkan_paged_ke_proyektor(
        self,
        doc: RenderedDocument,
        judul: str,
        fraksi_v: float,
        fraksi_h: float,
        zoom_relatif: float,
        slideshow: bool = False,
        item_id: str | None = None,
    ) -> None:
        """Dorong dokumen halaman ke proyektor — HANYA setelah konfirmasi (F-4.3)."""
        self._id_proyektor = item_id  # mulai sekarang proyektor & operator sinkron
        if self.presentation is None:
            self.buka_presentasi()
        assert self.presentation is not None
        pv = self.presentation.preview.doc_viewer

        def _swap() -> None:
            self.presentation.set_judul(judul)
            self.presentation.preview.tampilkan_paged(doc, slideshow=slideshow)
            # Samakan posisi (scroll/slide) & zoom (relatif ke layar proyektor).
            QTimer.singleShot(0, lambda: pv.terapkan_state(fraksi_v, fraksi_h, zoom_relatif))

        self.presentation.transisi_ganti(_swap)  # fade-out → swap → fade-in

    def tampilkan_video_ke_proyektor(self, path: str, judul: str, item_id: str | None = None) -> None:
        """Dorong video ke proyektor dengan operator sebagai MASTER (F-4.3/F-4.4).

        - Operator (laptop) = pengendali: play/pause/seek-nya mengatur proyektor.
        - Proyektor = keluaran untuk asesor, sumber SUARA (agar tidak dobel, operator
          di-mute selama tampil).
        - Posisi proyektor mengejar posisi operator (koreksi drift) selama sync aktif.
        """
        self._id_proyektor = item_id
        if self.presentation is None:
            self.buka_presentasi()
        assert self.presentation is not None

        op = self._operator_panel.video_viewer if self._operator_panel else None
        proj = self.presentation.preview.video_viewer

        def _swap() -> None:
            self.presentation.set_judul(judul)
            self.presentation.preview.tampilkan_video(path, auto_play=False)
            proj.set_muted(False)          # suara dari proyektor
            if op is not None:
                op.set_muted(True)         # hindari suara dobel

            siap = (proj.player.MediaStatus.LoadedMedia, proj.player.MediaStatus.BufferedMedia)

            def _mulai_selaras(status) -> None:
                if status not in siap:
                    return
                try:
                    proj.player.mediaStatusChanged.disconnect(_mulai_selaras)
                except (TypeError, RuntimeError):
                    pass
                if op is not None:
                    proj.set_posisi(op.posisi())
                    if op.player.playbackState() == op.player.PlaybackState.PlayingState:
                        proj.play()
                    else:
                        proj.pause()
                else:
                    proj.play()

            proj.player.mediaStatusChanged.connect(_mulai_selaras)
            # Tangani kasus media sudah siap sebelum sinyal tersambung.
            if proj.player.mediaStatus() in siap:
                _mulai_selaras(proj.player.mediaStatus())

            self._pasang_mirror_video()

        self.presentation.transisi_ganti(_swap)  # fade-out → swap → fade-in

    def _pasang_mirror_video(self) -> None:
        """Sambungkan sinyal player operator → proyektor (sekali saja)."""
        if self._video_mirror_terpasang or self._operator_panel is None:
            return
        op = self._operator_panel.video_viewer.player
        op.playbackStateChanged.connect(self._mirror_video_state)
        op.positionChanged.connect(self._mirror_video_position)
        self._video_mirror_terpasang = True

    def _proj_video(self):
        if self.presentation is None:
            return None
        return self.presentation.preview.video_viewer

    def _video_sama(self) -> bool:
        """Video operator == video proyektor (jangan kendalikan proyektor saat
        operator sedang melihat/pratinjau video LAIN yang belum ditampilkan)."""
        return (
            self.presentasi_terbuka
            and self._id_proyektor is not None
            and self._id_operator == self._id_proyektor
        )

    def _mirror_video_state(self, state) -> None:
        proj = self._proj_video()
        if proj is None or not self._video_sama():
            return
        st = self._operator_panel.video_viewer.player.PlaybackState
        if state == st.PlayingState:
            proj.play()
        elif state == st.PausedState:
            proj.pause()
        else:
            proj.stop()

    def _mirror_video_position(self, pos: int) -> None:
        """Koreksi drift: samakan posisi proyektor bila selisih > 400 ms."""
        proj = self._proj_video()
        if proj is None or not self._sync_aktif or not self._video_sama():
            return
        if abs(proj.posisi() - pos) > 400:
            proj.set_posisi(pos)

    def _on_operator_state_berubah(self, fraksi_v: float, fraksi_h: float, zoom_relatif: float) -> None:
        """Sinkronkan posisi scroll + zoom ke proyektor — hanya bila file operator
        == file proyektor (F-4.4). Memilih file baru di operator TIDAK menggeser
        proyektor sampai ditekan "Tampilkan ke Proyektor".
        """
        if not self._boleh_sinkron():
            return
        assert self.presentation is not None
        self.presentation.preview.doc_viewer.terapkan_state(fraksi_v, fraksi_h, zoom_relatif)
