# SPDX-FileCopyrightText: 2026 Travis Estill <immyouany@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Visual editor: drag and zoom the image over a preview of your monitors."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from wallstitch import APP_ID, DONATE_URL, __version__, slideshow
from wallstitch.backends import BackendError
from wallstitch.core import Settings, restore, stitch
from wallstitch.layout import View
from wallstitch.preview import Preview
from wallstitch.render import load_image
from wallstitch.screens import desktop_pixel_size, detect_screens
from wallstitch.slideshow_dialog import SlideshowDialog
from wallstitch.wallhaven_dialog import WallhavenDialog


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WallStitch")
        self.image_path: str | None = None
        self.preview = Preview(detect_screens())

        open_btn = QPushButton("Open Image…")
        open_btn.clicked.connect(self.open_image)
        random_btn = QPushButton("Random Wallpapers…")
        random_btn.setToolTip("Browse 10 random wallpapers from wallhaven.cc that fit your monitors")
        random_btn.clicked.connect(self.random_wallpapers)
        slideshow_btn = QPushButton("Slideshow…")
        slideshow_btn.setToolTip("Import up to 50 wallpapers and cycle through them on all monitors")
        slideshow_btn.clicked.connect(self.open_slideshow)

        self.bezel = QDoubleSpinBox()
        self.bezel.setRange(0, 2000)
        self.bezel.setDecimals(0)
        self.bezel.setSuffix(" px")
        self.bezel.setToolTip(
            "Hide this many pixels of the image between monitors\n"
            "so lines continue straight across the bezels"
        )
        self.bezel.valueChanged.connect(self.bezel_changed)

        reset_btn = QPushButton("Reset View")
        reset_btn.clicked.connect(self.reset_view)
        restore_btn = QPushButton("Restore Original")
        restore_btn.clicked.connect(self.restore)
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setDefault(True)
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self.apply)

        bar = QHBoxLayout()
        bar.addWidget(open_btn)
        bar.addWidget(random_btn)
        bar.addWidget(slideshow_btn)
        bar.addSpacing(16)
        bar.addWidget(QLabel("Bezel gap:"))
        bar.addWidget(self.bezel)
        bar.addWidget(reset_btn)
        bar.addStretch()
        bar.addWidget(restore_btn)
        bar.addWidget(self.apply_btn)

        hint = QLabel("Drag to move the image · scroll to zoom")
        hint.setEnabled(False)

        layout = QVBoxLayout()
        layout.addWidget(self.preview, 1)
        support = QLabel(f'<a href="{DONATE_URL}">♥ Support WallStitch on Ko-fi</a>')
        support.setOpenExternalLinks(True)
        hint_row = QHBoxLayout()
        hint_row.addWidget(hint)
        hint_row.addStretch()
        hint_row.addWidget(support)
        layout.addLayout(hint_row)
        layout.addLayout(bar)
        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)
        self.resize(1100, 520)

        if (last := Settings.load()) and Path(last.image).is_file():
            self.load(last.image)
            self.bezel.setValue(last.bezel)
            self.preview.view = last.view
            self.preview.update()

    def load(self, path: str) -> None:
        try:
            image = load_image(path)
        except ValueError as e:
            QMessageBox.warning(self, "WallStitch", str(e))
            return
        self.image_path = path
        self.preview.set_image(image)
        self.apply_btn.setEnabled(True)
        w, h = image.width(), image.height()
        self.statusBar().showMessage(f"{Path(path).name} — {w}×{h}")

    def random_wallpapers(self) -> None:
        dialog = WallhavenDialog(*desktop_pixel_size(self.preview.screens), self)
        if dialog.exec() and dialog.chosen_path:
            self.load(str(dialog.chosen_path))

    def open_slideshow(self) -> None:
        SlideshowDialog(self.preview.screens, self.bezel.value(), self).exec()

    def open_image(self) -> None:
        start = str(Path(self.image_path).parent) if self.image_path else str(Path.home() / "Pictures")
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose a wallpaper", start, "Images (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)"
        )
        if path:
            self.load(path)

    def bezel_changed(self, value: float) -> None:
        self.preview.bezel = value
        if self.preview.image is not None:
            self.preview.view = self.preview.current_plan().view
        self.preview.update()

    def reset_view(self) -> None:
        self.preview.view = View()
        self.preview.update()

    def apply(self) -> None:
        if not self.image_path:
            return
        settings = Settings(self.image_path, self.bezel.value(), self.preview.view)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            slideshow.stop()
            stitch(settings, self.preview.screens)
        except (BackendError, ValueError, OSError) as e:
            QMessageBox.warning(self, "WallStitch", f"Could not apply wallpaper:\n{e}")
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.statusBar().showMessage("Wallpaper applied.", 5000)

    def restore(self) -> None:
        try:
            restore()
        except BackendError as e:
            QMessageBox.information(self, "WallStitch", str(e))
            return
        self.statusBar().showMessage("Previous wallpaper restored.", 5000)


def run() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("WallStitch")
    app.setApplicationVersion(__version__)
    app.setDesktopFileName(APP_ID)
    bundled_icon = Path(__file__).parent / "resources" / f"{APP_ID}.svg"
    app.setWindowIcon(QIcon.fromTheme(APP_ID, QIcon(str(bundled_icon))))
    window = MainWindow()
    window.show()
    return app.exec()
