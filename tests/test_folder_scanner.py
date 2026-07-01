from src.data.folder_scanner import scan_folder
from src.data.models import MediaKind


def _buat_pohon(base):
    (base / "Materi").mkdir()
    (base / "Materi" / "sesi1.pdf").write_bytes(b"%PDF-1.4")
    (base / "Materi" / "slide.pptx").write_bytes(b"PK\x03\x04")
    (base / "Video").mkdir()
    (base / "Video" / "intro.mp4").write_bytes(b"\x00\x00\x00\x18ftyp")
    (base / "foto.jpg").write_bytes(b"\xff\xd8\xff")
    (base / "catatan.txt").write_text("abaikan")  # tidak didukung
    skip = base / "__pycache__"
    skip.mkdir()
    (skip / "x.pdf").write_bytes(b"%PDF")  # harus dilewati


def test_scan_folder_rekursif(tmp_path):
    _buat_pohon(tmp_path)
    hasil = scan_folder(tmp_path)
    nama = {it.nama_file for it in hasil.items}
    assert nama == {"sesi1.pdf", "slide.pptx", "intro.mp4", "foto.jpg"}  # txt & pycache diabaikan


def test_sheet_dan_kategori_dari_struktur_folder(tmp_path):
    _buat_pohon(tmp_path)
    hasil = scan_folder(tmp_path)
    by = {it.nama_file: it for it in hasil.items}
    assert by["sesi1.pdf"].sheet == "Materi"
    assert by["sesi1.pdf"].kategori == "Materi"
    assert by["foto.jpg"].sheet == "(root)"  # berkas di akar


def test_kind_terdeteksi(tmp_path):
    _buat_pohon(tmp_path)
    by = {it.nama_file: it for it in scan_folder(tmp_path).items}
    assert by["intro.mp4"].kind == MediaKind.VIDEO
    assert by["slide.pptx"].kind == MediaKind.PAGED
    assert by["foto.jpg"].kind == MediaKind.PAGED


def test_folder_tidak_valid_raise():
    import pytest
    with pytest.raises(NotADirectoryError):
        scan_folder("folder_tidak_ada_xyz")
