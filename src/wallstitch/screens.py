# SPDX-FileCopyrightText: 2026 Travis Estill <immyouany@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Detect the monitor layout through Qt, which works on X11 and Wayland."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QGuiApplication

from wallstitch.layout import Screen


def ensure_app() -> QCoreApplication:
    app = QCoreApplication.instance()
    if app is None:
        app = QGuiApplication(["wallstitch"])
    return app


def detect_screens() -> list[Screen]:
    ensure_app()
    screens = []
    for qs in QGuiApplication.screens():
        g = qs.geometry()
        screens.append(Screen(qs.name(), g.x(), g.y(), g.width(), g.height(), qs.devicePixelRatio()))
    if not screens:
        raise RuntimeError("no screens detected")
    return sorted(screens, key=lambda s: (s.y, s.x))


def desktop_pixel_size(screens: list[Screen]) -> tuple[int, int]:
    """Combined desktop size in device pixels, used to pick sharp-enough images."""
    from wallstitch.layout import plan

    p = plan(screens, (1, 1))
    scale = max(s.scale for s in screens)
    return round(p.canvas_width * scale), round(p.canvas_height * scale)
