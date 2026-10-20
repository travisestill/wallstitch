# SPDX-FileCopyrightText: 2026 Travis Estill <immyouany@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Interactive preview of an image spread across the monitor layout."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QImage, QImageReader, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from wallstitch.layout import Plan, Screen, View, plan

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

    def set_image(self, image: QImage, full_size: tuple[int, int] | None = None) -> None:
        """Show ``image``; pass ``full_size`` if it is already a scaled-down copy."""
        self.image_size = full_size or (image.width(), image.height())
        self.image = (
            image.scaledToWidth(PREVIEW_MAX_WIDTH, Qt.TransformationMode.SmoothTransformation)
            if image.width() > PREVIEW_MAX_WIDTH
            else image
        )
        self.view = View()
        self.update()

    def clear_image(self) -> None:
        self.image = None
        self.image_size = (0, 0)
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


def load_preview(path: str | Path) -> tuple[QImage, tuple[int, int]]:
    """A preview-sized copy of the image plus its full size.

    Decoding at reduced size is much faster than loading a 10K panorama and
    scaling it, which keeps flipping through slideshow images snappy.
    """
    QImageReader.setAllocationLimit(0)
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    size = reader.size()
    full = (size.width(), size.height())
    if size.isValid() and size.width() > PREVIEW_MAX_WIDTH:
        reader.setScaledSize(
            QSize(PREVIEW_MAX_WIDTH, round(size.height() * PREVIEW_MAX_WIDTH / size.width()))
        )
    image = reader.read()
    if image.isNull():
        raise ValueError(f"cannot read image {path}: {reader.errorString()}")
    if not size.isValid():
        full = (image.width(), image.height())
    elif (image.width() > image.height()) != (full[0] > full[1]):
        full = (full[1], full[0])  # EXIF rotation swapped the axes
    return image, full
