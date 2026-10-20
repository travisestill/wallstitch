# SPDX-FileCopyrightText: 2026 Travis Estill <immyouany@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Visual editor: drag and zoom the image over a preview of your monitors."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen
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

from wallstitch import APP_ID, __version__, slideshow
from wallstitch.backends import BackendError
from wallstitch.core import Settings, restore, stitch
from wallstitch.layout import Plan, Screen, View, plan
from wallstitch.render import load_image
from wallstitch.screens import desktop_pixel_size, detect_screens
from wallstitch.slideshow_dialog import SlideshowDialog
from wallstitch.wallhaven_dialog import WallhavenDialog

PREVIEW_MAX_WIDTH = 2400  # downscale the preview copy so dragging stays smooth
MARGIN = 24


class Preview(QWidget):
    viewChanged = Signal()

    def __init__(self, screens: list[Screen]):
        super().__init__()
        self.screens = screens
        self.image: QImage | None = None
        self.image_size = (0, 0)  # full-resolution size, used for planning
        self.view = View()
        self.bezel = 0.0
        self._drag_from: QPointF | None = None
        self.setMinimumSize(640, 240)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def set_image(self, image: QImage) -> None:
        self.image_size = (image.width(), image.height())
        self.image = (
            image.scaledToWidth(PREVIEW_MAX_WIDTH, Qt.TransformationMode.SmoothTransformation)
            if image.width() > PREVIEW_MAX_WIDTH
            else image
        )
        self.view = View()
        self.update()

    def current_plan(self) -> Plan | None:
        if self.image is None:
            return None
        return plan(self.screens, self.image_size, self.view, self.bezel)

    def _fit(self, p: Plan) -> tuple[float, float, float]:
        """Scale and offset that map canvas coordinates into the widget."""
        avail_w = self.width() - 2 * MARGIN
        avail_h = self.height() - 2 * MARGIN
        k = min(avail_w / p.canvas_width, avail_h / p.canvas_height)
        ox = (self.width() - p.canvas_width * k) / 2
        oy = (self.height() - p.canvas_height * k) / 2
        return k, ox, oy

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), self.palette().window())

        p = self.current_plan()
        if p is None:
            # No image yet: just draw the monitor layout.
            p = plan(self.screens, (1, 1), View(), self.bezel)
        k, ox, oy = self._fit(p)

        def to_widget(r) -> QRectF:
            return QRectF(ox + r.x * k, oy + r.y * k, r.width * k, r.height * k)

        screen_area = QPainterPath()
        for sl in p.slices:
            screen_area.addRect(to_widget(sl.canvas))

        if self.image is not None:
            iw, ih = self.image_size
            target = QRectF(ox + p.image_left * k, oy + p.image_top * k, iw * p.scale * k, ih * p.scale * k)
            # Ghost of the whole image so you can see what's being cropped...
            painter.setOpacity(0.25)
            painter.drawImage(target, self.image)
            # ...and the parts that will actually be on your screens.
            painter.setOpacity(1.0)
            painter.save()
            painter.setClipPath(screen_area)
            painter.drawImage(target, self.image)
            painter.restore()

        pen = QPen(QColor("#3daee9"), 2)
        painter.setPen(pen)
        for sl in p.slices:
            rect = to_widget(sl.canvas)
            painter.drawRect(rect)
            label = f"{sl.screen.name}  {sl.screen.width}×{sl.screen.height}"
            painter.drawText(
                rect.adjusted(8, 6, -8, -6), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft, label
            )

        if self.image is None:
            painter.setPen(self.palette().text().color())
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Open an image to get started")

    # --- interaction -------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.image is not None:
            self._drag_from = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:
        p = self.current_plan()
        if self._drag_from is None or p is None:
            return
        k, _, _ = self._fit(p)
        delta = event.position() - self._drag_from
        self._drag_from = event.position()
        iw, ih = self.image_size
        # Dragging the picture right moves the visible window left over it.
        self.view = replace(
            p.view,
            center_x=p.view.center_x - delta.x() / k / (iw * p.scale),
            center_y=p.view.center_y - delta.y() / k / (ih * p.scale),
        )
        self.view = self.current_plan().view  # clamp
        self.update()
        self.viewChanged.emit()

    def mouseReleaseEvent(self, _event) -> None:
        self._drag_from = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def wheelEvent(self, event) -> None:
        if self.image is None:
            return
        steps = event.angleDelta().y() / 120
        self.view = replace(self.view, zoom=self.view.zoom * (1.1**steps))
        self.view = self.current_plan().view
        self.update()
        self.viewChanged.emit()


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
        layout.addWidget(hint)
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
        screens = self.preview.screens
        SlideshowDialog(desktop_pixel_size(screens), self.bezel.value(), self).exec()

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
    window = MainWindow()
    window.show()
    return app.exec()
