# SPDX-FileCopyrightText: 2026 Travis Estill <immyouany@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Regenerate docs/screenshots/*.png for the README and app-store metadata.

Run with: QT_QPA_PLATFORM=offscreen python scripts/make_screenshots.py
Uses a generated landscape so the screenshots carry no third-party artwork.
"""

import os
import tempfile
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QRadialGradient
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"


def landscape(w: int = 5120, h: int = 1440) -> QImage:
    img = QImage(w, h, QImage.Format.Format_RGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    sky = QLinearGradient(0, 0, 0, h)
    for stop, color in [(0, "#0f1d3a"), (0.45, "#5b2a6e"), (0.75, "#d9705a"), (1, "#f6c177")]:
        sky.setColorAt(stop, QColor(color))
    p.fillRect(img.rect(), sky)
    glow = QRadialGradient(QPointF(w * 0.5, h * 0.4), h * 0.5)
    glow.setColorAt(0, QColor(255, 220, 140, 200))
    glow.setColorAt(1, QColor(255, 220, 140, 0))
    p.fillRect(img.rect(), glow)
    p.setBrush(QColor("#ffd27a"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QPointF(w * 0.5, h * 0.36), h * 0.08, h * 0.08)
    layers = [
        ("#3b2352", 0.55, [0.0, 0.18, 0.3, 0.45, 0.62, 0.8, 1.0], [0.75, 0.5, 0.62, 0.47, 0.58, 0.44, 0.7]),
        ("#24163a", 0.7, [0.0, 0.12, 0.33, 0.5, 0.7, 0.88, 1.0], [0.8, 0.66, 0.78, 0.6, 0.76, 0.64, 0.82]),
        ("#120c1f", 0.85, [0.0, 0.2, 0.4, 0.6, 0.8, 1.0], [0.9, 0.82, 0.92, 0.84, 0.9, 0.86]),
    ]
    for color, _, xs, ys in layers:
        path = QPainterPath(QPointF(0, h))
        for x, y in zip(xs, ys, strict=True):
            path.lineTo(x * w, y * h)
        path.lineTo(w, h)
        path.closeSubpath()
        p.fillPath(path, QColor(color))
    p.end()
    return img


def main() -> None:
    from wallstitch import paths
    from wallstitch.gui import MainWindow
    from wallstitch.layout import Screen
    from wallstitch.slideshow_dialog import SlideshowDialog

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["XDG_CONFIG_HOME"] = tmp  # don't load the developer's own settings
        image = Path(tmp) / "panorama.png"
        landscape().save(str(image))

        app = QApplication.instance() or QApplication([])
        app.setStyle("Fusion")
        win = MainWindow()
        win.preview.screens = [Screen("DP-1", 0, 0, 2560, 1440), Screen("DP-2", 2560, 0, 2560, 1440)]
        win.load(str(image))
        win.bezel.setValue(40)
        win.resize(1200, 560)
        win.show()
        app.processEvents()
        OUT.mkdir(parents=True, exist_ok=True)
        win.grab().save(str(OUT / "main.png"))

        dialog = SlideshowDialog((5120, 1440), 40)
        names = [f"wallhaven-{i:02}.jpg" for i in range(1, 21)]
        dialog.set_images([str(paths.download_dir() / n) for n in names])
        dialog.status.setText("Imported 20 wallpapers")
        dialog.show()
        app.processEvents()
        dialog.grab().save(str(OUT / "slideshow.png"))


if __name__ == "__main__":
    main()
