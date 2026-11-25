"""Einstieg der GUI: `uv run rc-505-panel` (ohne Argumente) oder `uv run rc-505-panel-gui`."""
from __future__ import annotations

import sys


def run() -> int:
    from PySide6.QtWidgets import QApplication

    from .main_window import MainWindow
    from .style import QSS

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("RC-505 Panel")
    app.setStyleSheet(QSS)
    win = MainWindow()
    win.show()
    return app.exec()
