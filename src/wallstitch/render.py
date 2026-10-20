# SPDX-FileCopyrightText: 2026 Travis Estill <immyouany@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Cut a source image into one file per screen according to a Plan."""

from __future__ import annotations

import hashlib
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QImageReader, QPainter

from wallstitch import paths
from wallstitch.layout import Plan


def load_image(path: str | Path) -> QImage:
    # Panoramic wallpapers easily exceed Qt's default 256 MB decode limit.
    QImageReader.setAllocationLimit(0)
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)  # honour EXIF rotation
    image = reader.read()
    if image.isNull():
        raise ValueError(f"cannot read image {path}: {reader.errorString()}")
    return image


def render_slices(image_path: str | Path, image: QImage, plan: Plan) -> dict[str, Path]:
    """Write one PNG per screen into the cache dir and return name -> path.

    File names include a hash of the inputs: Plasma caches wallpapers by path,
    so reusing a name would leave the old picture on screen.
    """
    image_path = Path(image_path).resolve()
    key = hashlib.sha1(repr((str(image_path), image_path.stat().st_mtime_ns, plan)).encode()).hexdigest()[:12]

    out_dir = paths.cache_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs: dict[str, Path] = {}
    for sl in plan.slices:
        w, h = sl.screen.pixel_size
        out = QImage(w, h, QImage.Format.Format_RGB32)
        out.fill(Qt.GlobalColor.black)
        painter = QPainter(out)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        src = sl.source
        painter.drawImage(QRectF(0, 0, w, h), image, QRectF(src.x, src.y, src.width, src.height))
        painter.end()

        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in sl.screen.name)
        target = out_dir / f"{key}-{safe_name}.png"
        if not out.save(str(target)):
            raise OSError(f"failed to write {target}")
        outputs[sl.screen.name] = target

    # Drop slices from earlier runs so the cache doesn't grow forever.
    keep = set(outputs.values())
    for old in out_dir.glob("*.png"):
        if old not in keep:
            old.unlink(missing_ok=True)
    return outputs
