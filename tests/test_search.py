from src.data.models import DocumentItem
from src.search.index import SearchIndex


def _index():
    items = [
        DocumentItem("C1", "Visi", "Renstra 2021-2025 UNIKU", "a.pdf"),
        DocumentItem("C1", "Visi", "Pedoman Penyusunan Visi Misi", "b.pdf"),
        DocumentItem("C2", "Kerjasama", "Bukti Kerjasama SMPN 4", "c.pdf"),
    ]
    return SearchIndex(items)


def test_query_kosong_kembalikan_semua():
    assert len(_index().cari("")) == 3


def test_substring_match():
    hasil = _index().cari("renstra")
    assert hasil and hasil[0].item.nama_file.startswith("Renstra")


def test_filter_sheet():
    hasil = _index().cari("", sheet="C2")
    assert len(hasil) == 1 and hasil[0].item.sheet == "C2"


def test_fuzzy_typo_tolerant():
    # "kerjsama" (typo) tetap menemukan "Kerjasama"
    hasil = _index().cari("kerjsama", fuzzy=True)
    assert any("Kerjasama" in h.item.nama_file for h in hasil)


def test_sheets_unik_urut():
    assert _index().sheets == ["C1", "C2"]
