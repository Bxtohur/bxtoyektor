from src.data.models import DocumentItem, MediaKind, Sumber, TipeFile


def test_deteksi_tipe_dari_ekstensi():
    assert TipeFile.dari_lokasi("C:/x/a.PDF") == TipeFile.PDF
    assert TipeFile.dari_lokasi("a.jpeg") == TipeFile.JPG
    assert TipeFile.dari_lokasi("a.docx") == TipeFile.DOCX
    assert TipeFile.dari_lokasi("a.pptx") == TipeFile.PPTX
    assert TipeFile.dari_lokasi("clip.MP4") == TipeFile.MP4
    assert TipeFile.dari_lokasi("https://drive.google.com/file/d/abc/view") == TipeFile.LAINNYA


def test_kind_media():
    assert DocumentItem("s", "k", "n", "a.pptx").kind == MediaKind.PAGED
    assert DocumentItem("s", "k", "n", "a.xlsx").kind == MediaKind.PAGED  # Excel bisa dipreview
    assert DocumentItem("s", "k", "n", "a.mp4").kind == MediaKind.VIDEO
    assert DocumentItem("s", "k", "n", "a.zip").kind == MediaKind.LAINNYA


def test_deteksi_sumber():
    lokal = DocumentItem("C1", "kat", "a", r"C:\docs\a.pdf")
    drive = DocumentItem("C1", "kat", "a", "https://drive.google.com/file/d/x/view")
    assert lokal.sumber == Sumber.LOCAL
    assert drive.sumber == Sumber.DRIVE


def test_id_stabil_dan_unik():
    a = DocumentItem("C1", "k", "nama", "loc")
    b = DocumentItem("C1", "k", "nama", "loc")
    c = DocumentItem("C2", "k", "nama", "loc")
    assert a.id == b.id  # deterministik
    assert a.id != c.id  # sheet beda → id beda


def test_bisa_dipreview():
    assert DocumentItem("s", "k", "n", "a.pdf").bisa_dipreview
    assert not DocumentItem("s", "k", "n", "a.zip").bisa_dipreview
