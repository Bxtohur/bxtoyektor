# PyInstaller spec — bxtoyektor (PRD §7 Instalasi).
# Build: pyinstaller --noconfirm build.spec   → dist/bxtoyektor/bxtoyektor.exe
# Catatan: LibreOffice TIDAK di-bundle (PRD §13) — dideteksi di runtime.

import os

from PyInstaller.utils.hooks import collect_all

# Sertakan plugin QtMultimedia (backend ffmpeg) agar preview video jalan di PC lain.
mm_datas, mm_binaries, mm_hidden = collect_all("PySide6.QtMultimedia")

block_cipher = None

a = Analysis(
    ["run.py"],
    pathex=["."],
    binaries=mm_binaries,
    datas=[("assets", "assets"), *mm_datas],
    hiddenimports=["PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", *mm_hidden],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "PySide6.QtQml", "PySide6.QtQuick"],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="bxtoyektor",
    console=False,           # aplikasi GUI, tanpa jendela konsol
    icon="assets/app.ico" if os.path.exists("assets/app.ico") else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="bxtoyektor",
)
