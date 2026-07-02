"""Jendela Operator / Laptop (PRD §9.1).

Header pencarian + filter + pemilih sumber (Excel / Folder), panel kiri hasil
(resizable), panel kanan preview terpadu (dokumen halaman / video) dengan kontrol
dan tombol "Tampilkan ke Proyektor" (konfirmasi 2 langkah, F-4.3).
"""
from __future__ import annotations

import webbrowser
from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..data.models import DocumentItem, MediaKind, Sumber
from ..render.document_renderer import DocumentRenderer, RenderedDocument
from ..search.index import SearchIndex
from ..settings import Settings, cache_dir
from ..window_manager import WindowManager
from .widgets.preview_panel import PreviewPanel
from .workers import ImportExcelWorker, RenderWorker, ScanFolderWorker

_ROLE_ITEM = Qt.ItemDataRole.UserRole


class OperatorWindow(QMainWindow):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self.index = SearchIndex()
        self.renderer = DocumentRenderer(cache_dir())
        self.wm = WindowManager(self)
        self.pool = QThreadPool.globalInstance()
        self._item_aktif: DocumentItem | None = None
        # Simpan referensi worker yang sedang berjalan agar tidak di-GC sebelum
        # sinyalnya terkirim (kalau tidak, status "Memuat…" bisa nyangkut).
        self._workers: set = set()

        self.setWindowTitle("bxtoyektor — Pencarian & Preview Bukti Fisik")
        self.resize(1200, 760)
        self._bangun_ui()
        self._bangun_shortcut()

        # Debounce pencarian instan (~200 ms, F-2.1)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(200)
        self._debounce.timeout.connect(self._jalankan_pencarian)

        # Auto-load sumber terakhir (F-1.1)
        self._muat_sumber_terakhir()

    # ---- UI ------------------------------------------------------------
    def _bangun_ui(self) -> None:
        pusat = QWidget()
        self.setCentralWidget(pusat)
        root = QVBoxLayout(pusat)

        header = QHBoxLayout()
        self.btn_buka_folder = QPushButton("Buka Folder…")
        self.btn_buka_folder.clicked.connect(self._pilih_folder)
        self.btn_buka_excel = QPushButton("Buka Excel…")
        self.btn_buka_excel.clicked.connect(self._pilih_excel)
        self.btn_refresh = QPushButton("Refresh")  # F-1.4
        self.btn_refresh.clicked.connect(self._refresh_data)

        self.input_cari = QLineEdit()
        self.input_cari.setPlaceholderText("Ketik untuk mencari dokumen…  (Ctrl+F)")
        self.input_cari.textChanged.connect(lambda _: self._debounce.start())

        self.filter_sheet = QComboBox()  # F-2.2
        self.filter_sheet.addItem("Semua Kategori", None)
        self.filter_sheet.currentIndexChanged.connect(lambda _: self._jalankan_pencarian())

        self.btn_presentasi = QPushButton("Buka Jendela Presentasi")  # F-4.1
        self.btn_presentasi.clicked.connect(self._buka_presentasi)

        header.addWidget(self.btn_buka_folder)
        header.addWidget(self.btn_buka_excel)
        header.addWidget(self.btn_refresh)
        header.addWidget(self.input_cari, 1)
        header.addWidget(self.filter_sheet)
        header.addWidget(self.btn_presentasi)
        root.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.list_hasil = QListWidget()
        self.list_hasil.itemClicked.connect(self._pilih_hasil)
        splitter.addWidget(self.list_hasil)
        splitter.addWidget(self._bangun_panel_preview())
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([self.settings.lebar_panel_kiri, 820])
        self._splitter = splitter
        root.addWidget(splitter, 1)

        self.status = self.statusBar()
        self.status.showMessage("Buka folder atau file Excel untuk memulai.")

    def _bangun_panel_preview(self) -> QWidget:
        wrap = QWidget()
        v = QVBoxLayout(wrap)

        bar = QHBoxLayout()
        self.btn_prev = QPushButton("◀ Prev")
        self.btn_prev.clicked.connect(lambda: self.preview.doc_viewer.halaman_sebelumnya())
        self.spin_halaman = QSpinBox()
        self.spin_halaman.setMinimum(1)
        self.spin_halaman.valueChanged.connect(self._lompat_halaman)
        self.lbl_total = QLabel("/ 0")
        self.btn_next = QPushButton("Next ▶")
        self.btn_next.clicked.connect(lambda: self.preview.doc_viewer.halaman_berikutnya())
        self.btn_zoom_out = QPushButton("–")
        self.btn_zoom_out.clicked.connect(lambda: self.preview.doc_viewer.zoom_out())
        self.btn_zoom_in = QPushButton("+")
        self.btn_zoom_in.clicked.connect(lambda: self.preview.doc_viewer.zoom_in())
        self.btn_fit = QPushButton("Fit")
        self.btn_fit.clicked.connect(lambda: self.preview.doc_viewer.fit_to_window())
        self.btn_buka_asli = QPushButton("Buka Lokasi Asli")  # F-3.5
        self.btn_buka_asli.clicked.connect(self._buka_lokasi_asli)

        self._kontrol_paged = [
            self.btn_prev, self.spin_halaman, self.btn_next,
            self.btn_zoom_out, self.btn_zoom_in, self.btn_fit,
        ]
        for w in (self.btn_prev, self.spin_halaman, self.lbl_total, self.btn_next):
            bar.addWidget(w)
        bar.addStretch(1)
        for w in (self.btn_zoom_out, self.btn_zoom_in, self.btn_fit, self.btn_buka_asli):
            bar.addWidget(w)
        v.addLayout(bar)

        self.preview = PreviewPanel(kontrol_video=True)
        self.preview.halaman_berubah.connect(self._on_halaman_berubah)
        self.wm.hubungkan_operator(self.preview)
        v.addWidget(self.preview, 1)

        bawah = QHBoxLayout()
        self.chk_sync = QPushButton("Sync: ON")
        self.chk_sync.setCheckable(True)
        self.chk_sync.setChecked(self.settings.sync_scroll)
        self.chk_sync.toggled.connect(self._toggle_sync)
        self._toggle_sync(self.settings.sync_scroll)
        self.btn_tampilkan = QPushButton("▶ Tampilkan ke Proyektor")
        self.btn_tampilkan.setStyleSheet(
            "background:#1a7f37; color:white; font-weight:600; padding:6px 14px;"
        )
        self.btn_tampilkan.clicked.connect(self._tampilkan_ke_proyektor)
        bawah.addWidget(self.chk_sync)
        bawah.addStretch(1)
        bawah.addWidget(self.btn_tampilkan)
        v.addLayout(bawah)
        return wrap

    def _bangun_shortcut(self) -> None:  # F-5.4
        QShortcut(QKeySequence("Ctrl+F"), self, lambda: self.input_cari.setFocus())
        QShortcut(QKeySequence(Qt.Key.Key_Right), self, lambda: self.preview.doc_viewer.halaman_berikutnya())
        QShortcut(QKeySequence(Qt.Key.Key_Left), self, lambda: self.preview.doc_viewer.halaman_sebelumnya())
        QShortcut(QKeySequence(Qt.Key.Key_F11), self, self._buka_presentasi)
        # Zoom: Ctrl++ / Ctrl+- / Ctrl+0 (fit)
        QShortcut(QKeySequence.StandardKey.ZoomIn, self, lambda: self.preview.doc_viewer.zoom_in())
        QShortcut(QKeySequence("Ctrl+="), self, lambda: self.preview.doc_viewer.zoom_in())
        QShortcut(QKeySequence.StandardKey.ZoomOut, self, lambda: self.preview.doc_viewer.zoom_out())
        QShortcut(QKeySequence("Ctrl+0"), self, lambda: self.preview.doc_viewer.fit_to_window())

    def _set_kontrol_paged(self, aktif: bool) -> None:
        for w in self._kontrol_paged:
            w.setEnabled(aktif)

    # ---- Sumber data ---------------------------------------------------
    def _muat_sumber_terakhir(self) -> None:
        src = self.settings.sumber_terakhir
        if not src or not Path(src).exists():
            return
        if self.settings.sumber_tipe == "folder":
            self._scan_folder(src)
        else:
            self._import_excel(src)

    def _pilih_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Pilih folder dokumen")
        if folder:
            self._scan_folder(folder)

    def _pilih_excel(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Pilih file Excel", "", "Excel (*.xlsx *.xls)")
        if path:
            self._import_excel(path)

    def _refresh_data(self) -> None:  # F-1.4
        src = self.settings.sumber_terakhir
        if not src:
            self._pilih_folder()
        elif self.settings.sumber_tipe == "folder":
            self._scan_folder(src)
        else:
            self._import_excel(src)

    def _jalankan_worker(self, worker, on_ok, on_err) -> None:
        """Jalankan worker sambil menjaga referensinya tetap hidup."""
        self._workers.add(worker)

        def _lepas() -> None:
            self._workers.discard(worker)

        worker.sinyal.selesai.connect(on_ok)
        worker.sinyal.gagal.connect(on_err)
        worker.sinyal.selesai.connect(lambda *_: _lepas())
        worker.sinyal.gagal.connect(lambda *_: _lepas())
        self.pool.start(worker)

    def _scan_folder(self, path: str) -> None:
        self.status.showMessage(f"Memindai folder {Path(path).name}…")
        self._jalankan_worker(
            ScanFolderWorker(path),
            lambda hasil: self._muat_hasil(path, "folder", hasil, f"folder {Path(path).name}"),
            self._on_muat_gagal,
        )

    def _import_excel(self, path: str) -> None:
        self.status.showMessage(f"Memuat {Path(path).name}…")
        self._jalankan_worker(
            ImportExcelWorker(path),
            lambda hasil: self._muat_hasil(path, "excel", hasil, Path(path).name),
            self._on_muat_gagal,
        )

    def _muat_hasil(self, path: str, tipe: str, hasil, label: str) -> None:
        self.index.rebuild(hasil.items)
        self.settings.sumber_terakhir = path
        self.settings.sumber_tipe = tipe
        self.settings.save()
        self.filter_sheet.blockSignals(True)
        self.filter_sheet.clear()
        self.filter_sheet.addItem("Semua Kategori", None)
        for s in self.index.sheets:
            self.filter_sheet.addItem(s, s)
        self.filter_sheet.blockSignals(False)
        self._jalankan_pencarian()
        pesan = f"{len(hasil.items)} item dimuat dari {label}."
        if hasil.peringatan:
            pesan += f"  ({len(hasil.peringatan)} peringatan)"
        self.status.showMessage(pesan)

    def _on_muat_gagal(self, err: str) -> None:
        QMessageBox.critical(self, "Gagal memuat data", err)
        self.status.showMessage("Gagal memuat data.")

    # ---- Pencarian -----------------------------------------------------
    def _jalankan_pencarian(self) -> None:
        query = self.input_cari.text()
        sheet = self.filter_sheet.currentData()
        hasil = self.index.cari(query, sheet=sheet)
        self.list_hasil.clear()
        for h in hasil:
            it = h.item
            label_kind = {MediaKind.VIDEO: "🎬 ", MediaKind.PAGED: ""}.get(it.kind, "")
            teks = f"{label_kind}{it.nama_file}"
            teks += f"\n{it.kategori} · {it.sheet}" if it.kategori else f"\n{it.sheet}"
            lw = QListWidgetItem(teks)
            lw.setData(_ROLE_ITEM, it)
            self.list_hasil.addItem(lw)
        self.status.showMessage(
            f"{len(hasil)} hasil untuk '{query}'." if query else f"{len(hasil)} item."
        )
        if query:
            self.settings.tambah_riwayat(query)

    # ---- Preview -------------------------------------------------------
    def _pilih_hasil(self, lw: QListWidgetItem) -> None:
        item: DocumentItem = lw.data(_ROLE_ITEM)
        self._item_aktif = item
        self.lbl_total.setText("/ 0")

        if item.sumber == Sumber.DRIVE:
            self._set_kontrol_paged(False)
            self.preview.kosongkan(
                f"'{item.nama_file}'\n\nSumber: Google Drive.\n"
                "Klik 'Buka Lokasi Asli' untuk membuka di browser."
            )
            return
        if item.kind == MediaKind.LAINNYA:
            self._set_kontrol_paged(False)
            self.preview.kosongkan(
                f"'{item.nama_file}'\n\nTipe berkas ini belum didukung untuk preview.\n"
                "Klik 'Buka Lokasi Asli'."
            )
            return
        if item.kind == MediaKind.VIDEO:
            self._set_kontrol_paged(False)
            self.preview.tampilkan_video(item.lokasi)
            self.status.showMessage("Video siap. Cek sebelum tampil ke proyektor.")
            return

        # PAGED (pdf/docx/pptx/gambar) → render di worker
        self._set_kontrol_paged(True)
        self.status.showMessage(f"Merender {item.nama_file}…")
        self._jalankan_worker(
            RenderWorker(self.renderer, item),
            self._on_render_selesai,
            self._on_render_gagal,
        )

    def _on_render_selesai(self, doc: RenderedDocument) -> None:
        self.preview.tampilkan_paged(doc)
        n = self.preview.doc_viewer.jumlah_halaman
        self.spin_halaman.setMaximum(max(1, n))
        self.lbl_total.setText(f"/ {n}")
        self.status.showMessage("Siap. Cek dokumen sebelum tampil ke proyektor.")

    def _on_render_gagal(self, err: str) -> None:
        self.preview.kosongkan(f"Tidak bisa menampilkan dokumen:\n{err}")
        self.status.showMessage("Preview gagal.")

    def _lompat_halaman(self, nomor: int) -> None:
        self.preview.doc_viewer.set_halaman(nomor - 1)

    def _on_halaman_berubah(self, indeks: int, total: int) -> None:
        self.spin_halaman.blockSignals(True)
        self.spin_halaman.setValue(indeks + 1)
        self.spin_halaman.blockSignals(False)

    def _buka_lokasi_asli(self) -> None:  # F-3.5
        if not self._item_aktif:
            return
        item = self._item_aktif
        if item.sumber == Sumber.DRIVE:
            webbrowser.open(item.lokasi)
        else:
            p = Path(item.cache_path or item.lokasi)
            webbrowser.open(p.parent.as_uri() if p.exists() else item.lokasi)

    # ---- Presentasi / proyektor ---------------------------------------
    def _buka_presentasi(self) -> None:
        self.wm.buka_presentasi(self.settings.monitor_presentasi)
        if self.wm.monitor_sekunder() is None:
            self.status.showMessage(
                "Monitor kedua tidak terdeteksi — jendela presentasi dibuka di layar ini."
            )

    def _toggle_sync(self, aktif: bool) -> None:  # F-4.4
        self.wm.set_sync(aktif)
        self.chk_sync.setText(f"Sync: {'ON' if aktif else 'OFF'}")
        self.settings.sync_scroll = aktif

    def _tampilkan_ke_proyektor(self) -> None:  # F-4.3 (2-step)
        item = self._item_aktif
        if not item:
            QMessageBox.information(self, "Belum ada dokumen", "Pilih dokumen dulu.")
            return
        if item.sumber == Sumber.DRIVE or item.kind == MediaKind.LAINNYA:
            QMessageBox.information(
                self, "Belum bisa ditampilkan",
                "Item ini belum bisa dirender native. Gunakan 'Buka Lokasi Asli'.",
            )
            return
        if not self.wm.presentasi_terbuka:
            self._buka_presentasi()

        judul = item.nama_file
        if item.kind == MediaKind.VIDEO:
            self.wm.tampilkan_video_ke_proyektor(item.lokasi, judul)
            self.status.showMessage("Video tampil di proyektor.")
            return

        # PAGED: render dokumen TERPISAH untuk proyektor (jangan berbagi handle fitz).
        dv = self.preview.doc_viewer
        fraksi_v, fraksi_h, zrel = dv.fraksi_scroll, dv.fraksi_scroll_h, dv.zoom_relatif
        self._jalankan_worker(
            RenderWorker(self.renderer, item),
            lambda doc: self.wm.tampilkan_paged_ke_proyektor(doc, judul, fraksi_v, fraksi_h, zrel),
            self._on_render_gagal,
        )

    # ---- Tutup ---------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802
        self.settings.lebar_panel_kiri = self._splitter.sizes()[0]
        self.settings.save()
        self.wm.tutup_presentasi()
        super().closeEvent(event)
