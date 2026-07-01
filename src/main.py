"""Entry point aplikasi Bukti Fisik C1-C9 (desktop PySide6).

Jalankan: `python -m src.main`
"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .settings import APP_NAME, Settings
from .ui.operator_window import OperatorWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)

    settings = Settings.load()
    win = OperatorWindow(settings)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
