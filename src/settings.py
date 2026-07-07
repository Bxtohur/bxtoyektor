"""Preferensi pengguna & path data aplikasi (PRD §8.2, F-5.2).

Disimpan di folder data lokal lintas-OS (mis. %APPDATA%/BuktiFisikC1C9 di Windows)
via QStandardPaths — tidak ada path yang di-hardcode (AGENTS.md §6).
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from PySide6.QtCore import QStandardPaths

APP_NAME = "bxtoyektor"


def app_data_dir() -> Path:
    """Folder data aplikasi (dibuat bila belum ada)."""
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    d = Path(base) if base else Path.home() / f".{APP_NAME}"
    d = d / APP_NAME if APP_NAME not in d.name else d
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_dir() -> Path:
    d = app_data_dir() / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


@dataclass
class Settings:
    """Preferensi yang dipersist ke settings.json."""

    sumber_terakhir: str = ""       # path sumber terakhir (F-1.1: auto-load)
    sumber_tipe: str = "excel"      # "excel" | "folder"
    tema: str = "terang"            # "terang" | "gelap" (F-5.2)
    ukuran_font: int = 12
    lebar_panel_kiri: int = 380     # F-5.3
    sync_scroll: bool = True        # F-4.4 (default aktif)
    monitor_presentasi: int = -1    # -1 = deteksi otomatis (F-4.1)
    riwayat_cari: list[str] = None  # type: ignore[assignment]
    pinned: list[str] = None        # lokasi file yang di-pin (selalu di atas)
    posisi_terakhir: dict = None    # lokasi -> fraksi posisi terakhir (0..1)

    def __post_init__(self) -> None:
        if self.riwayat_cari is None:
            self.riwayat_cari = []
        if self.pinned is None:
            self.pinned = []
        if self.posisi_terakhir is None:
            self.posisi_terakhir = {}

    @classmethod
    def path(cls) -> Path:
        return app_data_dir() / "settings.json"

    @classmethod
    def load(cls) -> Settings:
        p = cls.path()
        if not p.exists():
            return cls()
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            valid = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
            return cls(**valid)
        except (json.JSONDecodeError, OSError, TypeError):
            return cls()  # settings korup → kembali ke default (jangan crash)

    def save(self) -> None:
        self.path().write_text(
            json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def tambah_riwayat(self, query: str, maks: int = 15) -> None:
        q = query.strip()
        if not q:
            return
        if q in self.riwayat_cari:
            self.riwayat_cari.remove(q)
        self.riwayat_cari.insert(0, q)
        del self.riwayat_cari[maks:]
