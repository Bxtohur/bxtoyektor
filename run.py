"""Titik masuk untuk build (PyInstaller) & menjalankan langsung.

Entry frozen app dijalankan sebagai __main__ sehingga import relatif di dalam
paket `src` tidak boleh dipakai di titik masuk. File ini mengimpor paket secara
absolut lalu memanggil main(); import relatif di dalam `src` tetap valid karena
`src.main` diimpor sebagai bagian dari paket.

Jalankan: python run.py   (setara dengan: python -m src.main)
"""
from __future__ import annotations

import sys

from src.main import main

if __name__ == "__main__":
    sys.exit(main())
