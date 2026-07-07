"""Jendela Operator / Laptop (PRD §9.1).

Header pencarian + filter + pemilih sumber (Excel / Folder), panel kiri hasil
(resizable), panel kanan preview terpadu (dokumen halaman / video) dengan kontrol
dan tombol "Tampilkan ke Proyektor" (konfirmasi 2 langkah, F-4.3).
"""
from __future__ import annotations

import webbrowser
from pathlib import Path

from PySide6.QtCore import QFileInfo, QSize, Qt, QThreadPool, QTimer
from PySide6.QtGui import QGuiApplication, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFileIconProvider,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..data.folder_scanner import list_dir
from ..data.models import DocumentItem, MediaKind, Sumber, TipeFile
from ..render.document_renderer import DocumentRenderer, RenderedDocument
from ..search.index import SearchIndex
from ..settings import Settings, cache_dir
from ..window_manager import WindowManager
from .excel_editor import ExcelEditorDialog
from .widgets.preview_panel import PreviewPanel
from .workers import ImportExcelWorker, RenderWorker, ScanFolderWorker

_ROLE_ITEM = Qt.ItemDataRole.UserRole      # DocumentItem (berkas)
_ROLE_FOLDER = Qt.ItemDataRole.UserRole + 1  # str path (folder, untuk jelajah)


class OperatorWindow(QMainWindow):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self.index = SearchIndex()
        self.renderer = DocumentRenderer(cache_dir())
        self.wm = WindowManager(self)
        self.pool = QThreadPool.globalInstance()
        self._item_aktif: DocumentItem | None = None
        # Berbagi layar aktif: None | ("screen", QScreen) | ("window", QCapturableWindow)
        self._share_aktif: tuple | None = None
        # Jelajah folder (mode Explorer): akar + folder yang sedang dibuka.
        self._root_dir: Path | None = None
        self._current_dir: Path | None = None
        self._icon_provider = QFileIconProvider()
        self._semua_items: list[DocumentItem] = []  # untuk resolve item pinned
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
        self.btn_edit_excel = QPushButton("Edit Excel…")
        self.btn_edit_excel.clicked.connect(self._edit_excel)
        self.btn_refresh = QPushButton("Refresh")  # F-1.4
        self.btn_refresh.clicked.connect(self._refresh_data)

        self.input_cari = QLineEdit()
        self.input_cari.setPlaceholderText("Ketik untuk mencari dokumen…  (Ctrl+F)")
        self.input_cari.textChanged.connect(lambda _: self._debounce.start())

        self.filter_sheet = QComboBox()  # F-2.2
        self.filter_sheet.addItem("Semua Kategori", None)
        self.filter_sheet.currentIndexChanged.connect(lambda _: self._jalankan_pencarian())

        self.btn_share = QPushButton("Share Layar ▾")  # live screen/window share
        self.btn_share.clicked.connect(self._buka_menu_share)

        self.btn_presentasi = QPushButton("Buka Jendela Presentasi")  # F-4.1
        self.btn_presentasi.clicked.connect(self._buka_presentasi)

        header.addWidget(self.btn_buka_folder)
        header.addWidget(self.btn_buka_excel)
        header.addWidget(self.btn_edit_excel)
        header.addWidget(self.btn_refresh)
        header.addWidget(self.input_cari, 1)
        header.addWidget(self.filter_sheet)
        header.addWidget(self.btn_share)
        header.addWidget(self.btn_presentasi)
        root.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._bangun_panel_kiri())
        splitter.addWidget(self._bangun_panel_preview())
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([self.settings.lebar_panel_kiri, 820])
        self._splitter = splitter
        root.addWidget(splitter, 1)

        self.status = self.statusBar()
        self.status.showMessage("Buka folder atau file Excel untuk memulai.")

    def _bangun_panel_kiri(self) -> QWidget:
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 0)

        # Bar navigasi: Naik + breadcrumb + toggle List/Icon.
        nav = QHBoxLayout()
        self.btn_naik = QPushButton("⬆")
        self.btn_naik.setToolTip("Naik ke folder induk")
        self.btn_naik.setFixedWidth(32)
        self.btn_naik.clicked.connect(self._naik_folder)
        self.lbl_path = QLabel("—")
        self.lbl_path.setStyleSheet("color:#666;")
        self.btn_view = QPushButton("▦ Icon")
        self.btn_view.setToolTip("Ganti tampilan List / Icon")
        self.btn_view.setCheckable(True)
        self.btn_view.setFixedWidth(72)
        self.btn_view.toggled.connect(self._toggle_view)
        nav.addWidget(self.btn_naik)
        nav.addWidget(self.lbl_path, 1)
        nav.addWidget(self.btn_view)
        v.addLayout(nav)

        self.list_hasil = QListWidget()
        self.list_hasil.itemClicked.connect(self._pilih_hasil)
        self.list_hasil.itemDoubleClicked.connect(self._double_click_hasil)
        self.list_hasil.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_hasil.customContextMenuRequested.connect(self._menu_konteks)
        self.list_hasil.setWordWrap(True)
        self.list_hasil.setUniformItemSizes(False)
        self.list_hasil.setResizeMode(QListView.ResizeMode.Adjust)
        v.addWidget(self.list_hasil, 1)
        self._set_view_mode(icon=False)
        return wrap

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
        self.preview.screen_viewer.error.connect(self._on_share_error)
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

    def _edit_excel(self) -> None:
        awal = self.settings.sumber_terakhir if self.settings.sumber_tipe == "excel" else ""
        path, _ = QFileDialog.getOpenFileName(self, "Pilih Excel untuk diedit", awal, "Excel (*.xlsx)")
        if not path:
            return
        try:
            dlg = ExcelEditorDialog(path, self)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Gagal membuka Excel", str(exc))
            return
        dlg.tersimpan.connect(self._on_excel_tersimpan)
        self._excel_editor = dlg  # simpan referensi agar tidak di-GC
        dlg.show()

    def _on_excel_tersimpan(self, path: str) -> None:
        # Bila yang diedit adalah sumber data aktif → muat ulang daftarnya.
        if self.settings.sumber_tipe == "excel" and self.settings.sumber_terakhir:
            if Path(path) == Path(self.settings.sumber_terakhir):
                self._import_excel(path)
                self.status.showMessage(f"Excel disimpan & daftar diperbarui: {Path(path).name}")
                return
        self.status.showMessage(f"Excel disimpan: {Path(path).name}")

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
        self._semua_items = list(hasil.items)
        self.settings.sumber_terakhir = path
        self.settings.sumber_tipe = tipe
        self.settings.save()
        # Mode jelajah folder hanya untuk sumber folder.
        if tipe == "folder":
            self._root_dir = Path(path)
            self._current_dir = Path(path)
        else:
            self._root_dir = None
            self._current_dir = None
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

    # ---- Pencarian & Jelajah -------------------------------------------
    def _jalankan_pencarian(self) -> None:
        query = self.input_cari.text().strip()
        # Kotak cari kosong + sumber folder → tampilkan isi folder (mode jelajah).
        if not query and self._root_dir is not None:
            self._tampilkan_browse()
            return
        sheet = self.filter_sheet.currentData()
        hasil = self.index.cari(query, sheet=sheet)
        self.list_hasil.clear()
        pinned_lok = self._isi_pinned_di_atas()
        for h in hasil:
            if h.item.lokasi in pinned_lok:
                continue  # sudah tampil di bagian pinned (paling atas)
            self.list_hasil.addItem(self._buat_item_file(h.item, lokasi=True))
        self.status.showMessage(
            f"{len(hasil)} hasil untuk '{query}'." if query else f"{len(hasil)} item."
        )
        if query:
            self.settings.tambah_riwayat(query)
        self._perbarui_nav(browse=False)

    def _tampilkan_browse(self) -> None:
        """Tampilkan isi 1 folder (subfolder + berkas) — mode Explorer."""
        self.list_hasil.clear()
        pinned_lok = self._isi_pinned_di_atas()
        subs, files = list_dir(self._root_dir, self._current_dir)
        for d in subs:
            self.list_hasil.addItem(self._buat_item_folder(d))
        for it in files:
            if it.lokasi in pinned_lok:
                continue
            self.list_hasil.addItem(self._buat_item_file(it, lokasi=False))
        self._perbarui_nav(browse=True)
        self.status.showMessage(f"{len(subs)} folder · {len(files)} berkas · {len(pinned_lok)} pin")

    def _isi_pinned_di_atas(self) -> set[str]:
        """Tambahkan semua file yang di-pin di paling atas. Return set lokasi pinned."""
        pinned = [lok for lok in self.settings.pinned]
        if not pinned:
            return set()
        by_lok = {it.lokasi: it for it in self._semua_items}
        tampil: set[str] = set()
        for lok in pinned:
            it = by_lok.get(lok)
            if it is not None:
                self.list_hasil.addItem(self._buat_item_file(it, lokasi=True, pinned=True))
                tampil.add(lok)
        return tampil

    def _buat_item_folder(self, path: Path) -> QListWidgetItem:
        lw = QListWidgetItem(self._icon_provider.icon(QFileIconProvider.IconType.Folder), path.name)
        lw.setData(_ROLE_FOLDER, str(path))
        lw.setToolTip(str(path))
        return lw

    def _buat_item_file(self, it: DocumentItem, lokasi: bool, pinned: bool = False) -> QListWidgetItem:
        if it.sumber == Sumber.LOCAL:
            icon = self._icon_provider.icon(QFileInfo(it.lokasi))
        else:
            icon = self._icon_provider.icon(QFileIconProvider.IconType.File)
        teks = ("📌 " if pinned else "") + it.nama_file
        lw = QListWidgetItem(icon, teks)
        lw.setData(_ROLE_ITEM, it)
        detail = f"{it.kategori} · {it.sheet}" if it.kategori else it.sheet
        lw.setToolTip(detail if not lokasi else f"{it.nama_file}\n{detail}")
        return lw

    # ---- Pin ----------------------------------------------------------
    def _menu_konteks(self, pos) -> None:
        lw = self.list_hasil.itemAt(pos)
        if lw is None:
            return
        item: DocumentItem | None = lw.data(_ROLE_ITEM)
        if item is None:  # folder tidak bisa di-pin
            return
        menu = QMenu(self)
        if item.lokasi in self.settings.pinned:
            menu.addAction("📌 Lepas Pin", lambda: self._set_pin(item, False))
        else:
            menu.addAction("📌 Pin (selalu di atas)", lambda: self._set_pin(item, True))
        menu.exec(self.list_hasil.mapToGlobal(pos))

    def _set_pin(self, item: DocumentItem, pin: bool) -> None:
        lok = item.lokasi
        if pin and lok not in self.settings.pinned:
            self.settings.pinned.insert(0, lok)
        elif not pin and lok in self.settings.pinned:
            self.settings.pinned.remove(lok)
            self.settings.posisi_terakhir.pop(lok, None)  # lupakan posisi tersimpan
        self.settings.save()
        self._jalankan_pencarian()  # render ulang daftar

    def _perbarui_nav(self, browse: bool) -> None:
        folder_mode = self._root_dir is not None
        self.btn_naik.setVisible(folder_mode)
        self.lbl_path.setVisible(folder_mode)
        if not folder_mode:
            return
        if browse and self._current_dir is not None:
            rel = self._current_dir.relative_to(self._root_dir)
            crumbs = self._root_dir.name + ("/" + str(rel) if str(rel) != "." else "")
            self.lbl_path.setText("📁 " + crumbs.replace("\\", "/"))
            self.btn_naik.setEnabled(self._current_dir != self._root_dir)
        else:
            self.lbl_path.setText("🔎 Hasil pencarian")
            self.btn_naik.setEnabled(False)

    def _masuk_folder(self, path: str) -> None:
        self._current_dir = Path(path)
        self.input_cari.blockSignals(True)
        self.input_cari.clear()
        self.input_cari.blockSignals(False)
        self._tampilkan_browse()

    def _naik_folder(self) -> None:
        if self._current_dir and self._root_dir and self._current_dir != self._root_dir:
            self._current_dir = self._current_dir.parent
            self._tampilkan_browse()

    def _double_click_hasil(self, lw: QListWidgetItem) -> None:
        folder = lw.data(_ROLE_FOLDER)
        if folder:
            self._masuk_folder(folder)

    # ---- Tampilan List / Icon -----------------------------------------
    def _set_view_mode(self, icon: bool) -> None:
        if icon:
            self.list_hasil.setViewMode(QListView.ViewMode.IconMode)
            self.list_hasil.setIconSize(QSize(56, 56))
            self.list_hasil.setGridSize(QSize(112, 92))
            self.list_hasil.setFlow(QListView.Flow.LeftToRight)
            self.list_hasil.setWrapping(True)
            self.btn_view.setText("☰ List")
        else:
            self.list_hasil.setViewMode(QListView.ViewMode.ListMode)
            self.list_hasil.setIconSize(QSize(22, 22))
            self.list_hasil.setGridSize(QSize())
            self.list_hasil.setFlow(QListView.Flow.TopToBottom)
            self.list_hasil.setWrapping(False)
            self.btn_view.setText("▦ Icon")
        self.list_hasil.setMovement(QListView.Movement.Static)

    def _toggle_view(self, icon: bool) -> None:
        self._set_view_mode(icon)

    # ---- Preview -------------------------------------------------------
    def _pilih_hasil(self, lw: QListWidgetItem) -> None:
        item: DocumentItem | None = lw.data(_ROLE_ITEM)
        if item is None:  # folder → dibuka lewat double-click, bukan preview
            return
        self.settings.save()  # persist posisi terakhir file sebelumnya
        self._item_aktif = item
        self._share_aktif = None  # memilih file menghentikan berbagi layar
        # Catat file yang sedang dilihat operator; proyektor tidak ikut bergeser
        # sampai file ini benar-benar "Ditampilkan ke Proyektor".
        self.wm.set_item_operator(item.id)
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

    @staticmethod
    def _pakai_slideshow(item: DocumentItem | None) -> bool:
        """PPTX/PPT ditampilkan sebagai slide show (satu slide penuh per layar)."""
        return item is not None and item.tipe_file in {TipeFile.PPTX, TipeFile.PPT}

    def _on_render_selesai(self, doc: RenderedDocument) -> None:
        item = self._item_aktif
        slideshow = self._pakai_slideshow(item)
        # Pulihkan posisi terakhir untuk file yang di-pin.
        fraksi = 0.0
        if item is not None and item.lokasi in self.settings.pinned:
            fraksi = float(self.settings.posisi_terakhir.get(item.lokasi, 0.0))
        self.preview.tampilkan_paged(doc, fraksi=fraksi, slideshow=slideshow)
        n = self.preview.doc_viewer.jumlah_halaman
        self.spin_halaman.setMaximum(max(1, n))
        self.lbl_total.setText(f"/ {n}")
        if slideshow:
            self.status.showMessage(f"Slide {self.preview.doc_viewer.halaman_aktif + 1}/{n} — ◀/▶ ganti slide, lalu tampilkan ke proyektor.")
        else:
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
        # Ingat posisi terakhir untuk file yang di-pin (disimpan di memori,
        # dipersist saat ganti file / tutup aplikasi).
        item = self._item_aktif
        if item is not None and item.lokasi in self.settings.pinned:
            self.settings.posisi_terakhir[item.lokasi] = self.preview.doc_viewer.fraksi_scroll

    def _buka_lokasi_asli(self) -> None:  # F-3.5
        if not self._item_aktif:
            return
        item = self._item_aktif
        if item.sumber == Sumber.DRIVE:
            webbrowser.open(item.lokasi)
        else:
            p = Path(item.cache_path or item.lokasi)
            webbrowser.open(p.parent.as_uri() if p.exists() else item.lokasi)

    # ---- Berbagi layar / window ---------------------------------------
    def _buka_menu_share(self) -> None:
        menu = QMenu(self)
        layar_menu = menu.addMenu("Seluruh Layar")
        for i, scr in enumerate(QGuiApplication.screens()):
            g = scr.geometry()
            label = f"Layar {i + 1} — {g.width()}×{g.height()}"
            if scr is QGuiApplication.primaryScreen():
                label += " (utama)"
            layar_menu.addAction(label, lambda s=scr: self._mulai_share_screen(s))

        win_menu = menu.addMenu("Window")
        windows = self.preview.screen_viewer.daftar_window()
        if not windows:
            win_menu.addAction("(tidak ada window)").setEnabled(False)
        for w in windows:
            desk = w.description() or "(tanpa judul)"
            win_menu.addAction(desk[:60], lambda win=w: self._mulai_share_window(win))

        menu.exec(self.btn_share.mapToGlobal(self.btn_share.rect().bottomLeft()))

    def _mulai_share_screen(self, screen) -> None:
        self._item_aktif = None
        self._share_aktif = ("screen", screen)
        self.wm.set_item_operator("__screen__")
        self._set_kontrol_paged(False)
        self.preview.tampilkan_share_screen(screen)
        self.status.showMessage("Pratinjau berbagi layar. Tekan 'Tampilkan ke Proyektor' untuk mulai.")

    def _mulai_share_window(self, window) -> None:
        self._item_aktif = None
        self._share_aktif = ("window", window)
        self.wm.set_item_operator("__screen__")
        self._set_kontrol_paged(False)
        self.preview.tampilkan_share_window(window)
        self.status.showMessage("Pratinjau berbagi window. Tekan 'Tampilkan ke Proyektor' untuk mulai.")

    def _on_share_error(self, pesan: str) -> None:
        """Tampilkan pesan jelas bila berbagi layar tidak didukung sistem."""
        if "0x887a0004" in pesan or "not supported" in pesan.lower():
            pesan = (
                "Berbagi layar tidak didukung di sistem ini. Ini biasa terjadi pada "
                "Remote Desktop, mesin virtual, atau driver GPU tertentu. Coba di "
                "komputer/monitor fisik."
            )
        self.status.showMessage(f"Berbagi layar: {pesan}")

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
        # Berbagi layar/window aktif → tampilkan capture live ke proyektor.
        if self._share_aktif is not None:
            if not self.wm.presentasi_terbuka:
                self._buka_presentasi()
            mode, sumber = self._share_aktif
            if mode == "screen":
                self.wm.tampilkan_share_screen_ke_proyektor(sumber, "Berbagi Layar")
            else:
                self.wm.tampilkan_share_window_ke_proyektor(
                    sumber, sumber.description() or "Berbagi Window"
                )
            self.status.showMessage("Berbagi layar tampil di proyektor.")
            return

        item = self._item_aktif
        if not item:
            QMessageBox.information(self, "Belum ada dokumen", "Pilih dokumen atau mulai berbagi layar dulu.")
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
            self.wm.tampilkan_video_ke_proyektor(item.lokasi, judul, item_id=item.id)
            self.status.showMessage("Video tampil di proyektor.")
            return

        # PAGED: render dokumen TERPISAH untuk proyektor (jangan berbagi handle fitz).
        dv = self.preview.doc_viewer
        fraksi_v, fraksi_h, zrel = dv.fraksi_scroll, dv.fraksi_scroll_h, dv.zoom_relatif
        slideshow = self._pakai_slideshow(item)
        item_id = item.id
        self._jalankan_worker(
            RenderWorker(self.renderer, item),
            lambda doc: self.wm.tampilkan_paged_ke_proyektor(
                doc, judul, fraksi_v, fraksi_h, zrel, slideshow, item_id
            ),
            self._on_render_gagal,
        )

    # ---- Tutup ---------------------------------------------------------
    def closeEvent(self, event) -> None:  # noqa: N802
        self.settings.lebar_panel_kiri = self._splitter.sizes()[0]
        self.settings.save()
        self.wm.tutup_presentasi()
        super().closeEvent(event)
