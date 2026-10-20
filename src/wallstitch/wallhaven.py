# SPDX-FileCopyrightText: 2026 Travis Estill <immyouany@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Find wallpapers that fit the desktop on wallhaven.cc (https://wallhaven.cc/help/api).

Only builds URLs and parses replies; the GUI does the networking with Qt so
it never blocks.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlencode

SEARCH_API = "https://wallhaven.cc/api/v1/search"

# Aspect ratios wallhaven users tag images with, widest multi-monitor ones included.
RATIOS = {
    "4x3": 4 / 3,
    "16x10": 16 / 10,
    "16x9": 16 / 9,
    "21x9": 21 / 9,
    "32x9": 32 / 9,
    "48x9": 48 / 9,
    "9x16": 9 / 16,
    "10x16": 10 / 16,
}
RATIO_TOLERANCE = 0.08  # beyond this, cropping would lose too much of the image


@dataclass(frozen=True)
class Wallpaper:
    id: str
    page_url: str
    image_url: str
    thumb_url: str
    width: int
    height: int

    @property
    def filename(self) -> str:
        return self.image_url.rsplit("/", 1)[-1]


def best_ratio(width: float, height: float) -> str | None:
    """The wallhaven ratio tag closest to ``width/height``, if one is close enough."""
    target = width / height
    name, value = min(RATIOS.items(), key=lambda kv: abs(kv[1] - target))
    return name if abs(value - target) / target <= RATIO_TOLERANCE else None


def search_url(min_width: int, min_height: int, ratio: str | None = None) -> str:
    """URL for a random page of safe-for-work wallpapers at least this large."""
    params = {
        "sorting": "random",
        "categories": "111",  # general, anime, people
        "purity": "100",  # SFW only; NSFW requires an API key anyway
        "atleast": f"{min_width}x{min_height}",
    }
    if ratio:
        params["ratios"] = ratio
    return f"{SEARCH_API}?{urlencode(params)}"


def parse_search(body: bytes | str) -> list[Wallpaper]:
    data = json.loads(body)
    if "data" not in data:
        raise ValueError(data.get("error", "unexpected reply from wallhaven"))
    results = []
    for item in data["data"]:
        w, h = (int(v) for v in item["resolution"].split("x"))
        results.append(
            Wallpaper(
                id=item["id"],
                page_url=item["url"],
                image_url=item["path"],
                # "original" keeps the aspect ratio; the others are cropped to 3:2
                thumb_url=item["thumbs"]["original"],
                width=w,
                height=h,
            )
        )
    return results
