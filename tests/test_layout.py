# SPDX-FileCopyrightText: 2026 Travis Estill <immyouany@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

import pytest

from wallstitch.layout import Screen, View, canvas_rects, plan

LEFT = Screen("HDMI-A-1", 0, 0, 2560, 1440)
RIGHT = Screen("DP-1", 2560, 0, 2560, 1440)


def approx_rect(r):
    return pytest.approx((r.x, r.y, r.width, r.height))


def test_dual_1440p_exact_fit_splits_in_half():
    p = plan([LEFT, RIGHT], (5120, 1440))
    left, right = p.slices
    assert approx_rect(left.source) == (0, 0, 2560, 1440)
    assert approx_rect(right.source) == (2560, 0, 2560, 1440)


def test_single_ultrawide_uses_whole_image():
    uw = Screen("DP-1", 0, 0, 5120, 1440)
    (only,) = plan([uw], (5120, 1440)).slices
    assert approx_rect(only.source) == (0, 0, 5120, 1440)


def test_larger_image_is_scaled_to_cover():
    # 10240x2880 is exactly 2x: each screen gets a 5120x2880 region.
    left, right = plan([LEFT, RIGHT], (10240, 2880)).slices
    assert approx_rect(left.source) == (0, 0, 5120, 2880)
    assert approx_rect(right.source) == (5120, 0, 5120, 2880)


def test_too_tall_image_is_center_cropped():
    # 5120x2880 must be cropped vertically to 1440 rows, centred.
    left, _ = plan([LEFT, RIGHT], (5120, 2880)).slices
    assert approx_rect(left.source) == (0, 720, 2560, 1440)


def test_center_is_clamped_so_screens_stay_covered():
    p = plan([LEFT, RIGHT], (5120, 2880), View(center_y=0.0))
    left, _ = p.slices
    assert left.source.y == pytest.approx(0)
    assert p.view.center_y == pytest.approx(0.25)


def test_zoom_below_one_is_clamped():
    p = plan([LEFT, RIGHT], (5120, 1440), View(zoom=0.5))
    assert p.view.zoom == 1.0


def test_zoom_in_shows_smaller_region():
    left, right = plan([LEFT, RIGHT], (5120, 1440), View(zoom=2.0)).slices
    assert approx_rect(left.source) == (1280, 360, 1280, 720)
    assert approx_rect(right.source) == (2560, 360, 1280, 720)


def test_bezel_hides_image_between_screens():
    p = plan([LEFT, RIGHT], (5120 + 100, 1440), bezel=100)
    left, right = p.slices
    assert p.canvas_width == 5220
    assert approx_rect(left.source) == (0, 0, 2560, 1440)
    assert approx_rect(right.source) == (2660, 0, 2560, 1440)


def test_negative_and_stacked_layout_is_normalised():
    top = Screen("top", -1920, -1080, 1920, 1080)
    bottom = Screen("bottom", -1920, 0, 1920, 1080)
    rects = canvas_rects([top, bottom], bezel=10)
    assert approx_rect(rects["top"]) == (0, 0, 1920, 1080)
    assert approx_rect(rects["bottom"]) == (0, 1090, 1920, 1080)


def test_hidpi_screen_renders_more_pixels():
    assert Screen("x", 0, 0, 1280, 720, scale=2).pixel_size == (2560, 1440)


def test_no_screens_is_an_error():
    with pytest.raises(ValueError):
        plan([], (100, 100))
