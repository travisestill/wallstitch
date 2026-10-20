# SPDX-FileCopyrightText: 2026 Travis Estill <immyouany@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

import json
import os

import pytest

from wallstitch import slideshow, wallhaven
from wallstitch.slideshow import MAX_IMAGES, Slideshow, images_in


@pytest.fixture
def images(tmp_path):
    files = []
    for i in range(3):
        f = tmp_path / f"img{i}.png"
        f.write_bytes(b"x")
        os.utime(f, (i, i))  # img2 is newest
        files.append(str(f))
    return files


def test_advance_cycles_in_order(images):
    show = Slideshow(images)
    assert [show.advance() for _ in range(4)] == [images[0], images[1], images[2], images[0]]


def test_advance_skips_missing_files(images):
    os.remove(images[1])
    show = Slideshow(images)
    assert [show.advance() for _ in range(3)] == [images[0], images[2], images[0]]


def test_advance_with_no_existing_files(tmp_path):
    assert Slideshow([str(tmp_path / "gone.png")]).advance() is None


def test_shuffle_shows_every_image_once_per_round(images):
    show = Slideshow(images, shuffle=True)
    assert sorted(show.advance() for _ in range(3)) == sorted(images)


def test_save_and_load_round_trip(images, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    show = Slideshow(images, interval_minutes=5, shuffle=True)
    show.advance()
    show.save()
    assert Slideshow.load() == show


def test_images_in_folder_newest_first_and_capped(tmp_path):
    for i in range(MAX_IMAGES + 5):
        f = tmp_path / f"{i:03}.jpg"
        f.write_bytes(b"x")
        os.utime(f, (i, i))
    (tmp_path / "notes.txt").write_text("not an image")
    found = images_in(tmp_path)
    assert len(found) == MAX_IMAGES
    assert found[0].endswith(f"{MAX_IMAGES + 4:03}.jpg")


def test_start_requires_images():
    with pytest.raises(Exception, match="at least one image"):
        slideshow.start([], 10, False, 0)


def _page(ids, last_page, seed="abc"):
    return json.dumps(
        {
            "data": [
                {
                    "id": i,
                    "url": f"https://wallhaven.cc/w/{i}",
                    "path": f"https://w.wallhaven.cc/full/xx/wallhaven-{i}.jpg",
                    "resolution": "5120x1440",
                    "thumbs": {"original": "t"},
                }
                for i in ids
            ],
            "meta": {"last_page": last_page, "seed": seed},
        }
    ).encode()


def test_find_random_pages_with_seed_and_dedupes(monkeypatch):
    urls = []
    pages = iter([_page([f"a{i}" for i in range(24)], 3), _page(["a0"] + [f"b{i}" for i in range(23)], 3)])

    def fake_fetch(url, timeout=30):
        urls.append(url)
        return next(pages)

    monkeypatch.setattr(wallhaven, "_fetch", fake_fetch)
    found = wallhaven.find_random(5120, 1440, 30)
    assert len(found) == 30
    assert len({w.id for w in found}) == 30
    assert "seed=abc" in urls[1] and "page=2" in urls[1]


def test_find_random_falls_back_to_any_ratio(monkeypatch):
    urls = []
    replies = iter([_page([], 1), _page(["x"], 1)])

    def fake_fetch(url, timeout=30):
        urls.append(url)
        return next(replies)

    monkeypatch.setattr(wallhaven, "_fetch", fake_fetch)
    assert [w.id for w in wallhaven.find_random(5120, 1440, 5)] == ["x"]
    assert "ratios=32x9" in urls[0] and "ratios" not in urls[1]
