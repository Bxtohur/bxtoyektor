"""Uji parser terhadap file Excel nyata di docs/ (deteksi header otomatis)."""
from pathlib import Path

import pytest

from src.data.excel_reader import baca_excel

EXCEL = Path(__file__).resolve().parent.parent / "docs" / "LINK BUKTI FISIK C1-C9.xlsx"

pytestmark = pytest.mark.skipif(not EXCEL.exists(), reason="File Excel contoh tidak tersedia")


def test_baca_semua_sheet():
    hasil = baca_excel(EXCEL)
    per = hasil.jumlah_per_sheet
    # Kelima sheet harus terbaca dan menghasilkan data.
    assert set(per) == {"C1-C9", "C2", "C3", "C4", "C5"}
    assert all(v > 0 for v in per.values())
    assert len(hasil.items) > 900


def test_kategori_terisi_untuk_sheet_berkolom_judul():
    hasil = baca_excel(EXCEL)
    c2 = [it for it in hasil.items if it.sheet == "C2"]
    assert any(it.kategori for it in c2)  # kolom JUDUL terdeteksi & merambat


def test_file_tidak_ada_raise():
    with pytest.raises(FileNotFoundError):
        baca_excel("tidak_ada.xlsx")
