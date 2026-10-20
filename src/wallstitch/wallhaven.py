# SPDX-FileCopyrightText: 2026 Travis Estill <immyouany@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Find wallpapers that fit the desktop on wallhaven.cc (https://wallhaven.cc/help/api).

The single-pick dialog does its networking with Qt; bulk imports use the
blocking helpers at the bottom (run them off the GUI thread).
"""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

from wallstitch import __version__

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


def search_url(
    min_width: int, min_height: int, ratio: str | None = None, page: int = 1, seed: str | None = None
) -> str:
    """URL for a random page of safe-for-work wallpapers at least this large.

    Pass the ``seed`` from the first page's reply to get further pages of the
    same random order without repeats.
    """
    params = {
        "sorting": "random",
        "categories": "111",  # general, anime, people
        "purity": "100",  # SFW only; NSFW requires an API key anyway
        "atleast": f"{min_width}x{min_height}",
    }
    if ratio:
        params["ratios"] = ratio
    if page > 1:
        params["page"] = str(page)
    if seed:
        params["seed"] = seed
    return f"{SEARCH_API}?{urlencode(params)}"


def parse_search(body: bytes | str) -> list[Wallpaper]:
    return parse_search_page(body)[0]


def parse_search_page(body: bytes | str) -> tuple[list[Wallpaper], dict]:
    """Wallpapers plus the ``meta`` block (seed, last_page, ...)."""
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
    return results, data.get("meta") or {}


# --- blocking helpers for bulk import -----------------------------------------


def _fetch(url: str, timeout: float = 30) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": f"WallStitch/{__version__}"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def find_random(min_width: int, min_height: int, count: int) -> list[Wallpaper]:
    """Up to ``count`` distinct random wallpapers that fit the desktop."""
    for ratio in dict.fromkeys([best_ratio(min_width, min_height), None]):
        found: dict[str, Wallpaper] = {}
        seed, page, last_page = None, 1, 1
        while len(found) < count and page <= last_page:
            results, meta = parse_search_page(_fetch(search_url(min_width, min_height, ratio, page, seed)))
            seed = meta.get("seed") or seed
            last_page = int(meta.get("last_page") or 1)
            for wp in results:
                found.setdefault(wp.id, wp)
            page += 1
        if found:
            return list(found.values())[:count]
    return []


def download(wallpaper: Wallpaper, dest_dir: Path) -> Path:
    """Save the full image into ``dest_dir`` (skipped if already there)."""
    target = dest_dir / wallpaper.filename
    if target.is_file():
        return target
    dest_dir.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    partial.write_bytes(_fetch(wallpaper.image_url, timeout=120))
    partial.replace(target)
    return target


def import_random(
    min_width: int,
    min_height: int,
    count: int,
    dest_dir: Path,
    progress: Callable[[int, int], None] | None = None,
) -> list[Path]:
    """Find and download ``count`` random wallpapers; returns the saved files.

    Individual failed downloads are skipped rather than aborting the batch.
    """
    wallpapers = find_random(min_width, min_height, count)
    paths: list[Path] = []
    for i, wp in enumerate(wallpapers):
        if progress:
            progress(i, len(wallpapers))
        try:
            paths.append(download(wp, dest_dir))
        except OSError:
            continue
    if progress:
        progress(len(wallpapers), len(wallpapers))
    return paths
