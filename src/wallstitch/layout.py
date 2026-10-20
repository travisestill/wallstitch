# SPDX-FileCopyrightText: 2026 Travis Estill <immyouany@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure geometry: map one image across a set of screens.

Nothing in this module depends on Qt, so it can be unit-tested and reused by
any desktop backend.

Coordinate spaces
-----------------
* **desktop**  - logical pixels as reported by the compositor (what Plasma's
  ``screenGeometry()`` and ``QScreen.geometry()`` return).
* **canvas**   - desktop space normalised to start at (0, 0), with optional
  bezel gaps inserted between neighbouring columns/rows of screens.
* **image**    - pixels of the source image.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Screen:
    name: str
    x: int
    y: int
    width: int
    height: int
    scale: float = 1.0

    @property
    def pixel_size(self) -> tuple[int, int]:
        """Size of the output image for this screen in device pixels."""
        return round(self.width * self.scale), round(self.height * self.scale)


@dataclass(frozen=True)
class View:
    """How the image is positioned on the canvas.

    ``zoom`` 1.0 means the image exactly covers the canvas (scaled to fill,
    cropping the overflowing axis). ``center_x``/``center_y`` are the point of
    the image (0..1) that sits in the middle of the canvas.
    """

    zoom: float = 1.0
    center_x: float = 0.5
    center_y: float = 0.5


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class Slice:
    screen: Screen
    canvas: Rect  # where the screen sits on the canvas
    source: Rect  # region of the source image shown on this screen


@dataclass(frozen=True)
class Plan:
    canvas_width: float
    canvas_height: float
    view: View  # the view after clamping, so callers can sync their UI
    scale: float  # canvas pixels per image pixel
    image_left: float  # canvas position of the image's top-left corner
    image_top: float
    slices: tuple[Slice, ...]


def canvas_rects(screens: list[Screen], bezel: float = 0.0) -> dict[str, Rect]:
    """Place screens on the canvas, inserting ``bezel`` px between columns/rows.

    Each distinct left edge after the first adds one bezel of horizontal
    offset (and likewise for top edges vertically), which keeps aligned
    screens aligned while opening a gap between neighbours.
    """
    if not screens:
        raise ValueError("no screens")
    min_x = min(s.x for s in screens)
    min_y = min(s.y for s in screens)
    xs = sorted({s.x for s in screens})
    ys = sorted({s.y for s in screens})
    return {
        s.name: Rect(
            s.x - min_x + xs.index(s.x) * bezel,
            s.y - min_y + ys.index(s.y) * bezel,
            s.width,
            s.height,
        )
        for s in screens
    }


def clamp_view(view: View, image_w: int, image_h: int, canvas_w: float, canvas_h: float) -> View:
    """Keep zoom >= 1 and the centre such that the canvas is always covered."""
    zoom = max(1.0, view.zoom)
    scale = max(canvas_w / image_w, canvas_h / image_h) * zoom
    half_w = canvas_w / scale / 2 / image_w  # half the visible width, in 0..1 units
    half_h = canvas_h / scale / 2 / image_h
    cx = min(max(view.center_x, half_w), 1 - half_w)
    cy = min(max(view.center_y, half_h), 1 - half_h)
    return replace(view, zoom=zoom, center_x=cx, center_y=cy)


def plan(
    screens: list[Screen],
    image_size: tuple[int, int],
    view: View | None = None,
    bezel: float = 0.0,
) -> Plan:
    image_w, image_h = image_size
    if image_w <= 0 or image_h <= 0:
        raise ValueError("image has no size")
    rects = canvas_rects(screens, bezel)
    view = view or View()
    canvas_w = max(r.x + r.width for r in rects.values())
    canvas_h = max(r.y + r.height for r in rects.values())

    view = clamp_view(view, image_w, image_h, canvas_w, canvas_h)
    scale = max(canvas_w / image_w, canvas_h / image_h) * view.zoom
    left = canvas_w / 2 - view.center_x * image_w * scale
    top = canvas_h / 2 - view.center_y * image_h * scale

    slices = tuple(
        Slice(
            screen=s,
            canvas=rects[s.name],
            source=Rect(
                (rects[s.name].x - left) / scale,
                (rects[s.name].y - top) / scale,
                s.width / scale,
                s.height / scale,
            ),
        )
        for s in screens
    )
    return Plan(canvas_w, canvas_h, view, scale, left, top, slices)
