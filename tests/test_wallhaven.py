# SPDX-FileCopyrightText: 2026 Travis Estill <immyouany@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

import json
from urllib.parse import parse_qs, urlparse

import pytest

from wallstitch.wallhaven import best_ratio, parse_search, search_url


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        ((5120, 1440), "32x9"),  # two 1440p side by side, or a super-ultrawide
        ((2560, 1440), "16x9"),
        ((3440, 1440), "21x9"),
        ((7680, 1440), "48x9"),  # three 1440p
        ((1920, 1200), "16x10"),
        ((1440, 2560), "9x16"),
        ((2560, 2880), None),  # two stacked 1440p: nothing close enough
    ],
)
def test_best_ratio(size, expected):
    assert best_ratio(*size) == expected


def test_search_url():
    q = parse_qs(urlparse(search_url(5120, 1440, "32x9")).query)
    assert q["sorting"] == ["random"]
    assert q["purity"] == ["100"]
    assert q["atleast"] == ["5120x1440"]
    assert q["ratios"] == ["32x9"]


def test_search_url_without_ratio():
    assert "ratios" not in search_url(2560, 2880)


def test_parse_search():
    body = json.dumps(
        {
            "data": [
                {
                    "id": "r76wvj",
                    "url": "https://wallhaven.cc/w/r76wvj",
                    "path": "https://w.wallhaven.cc/full/r7/wallhaven-r76wvj.jpg",
                    "resolution": "7680x2160",
                    "thumbs": {"original": "https://th.wallhaven.cc/orig/r7/r76wvj.jpg"},
                }
            ],
            "meta": {},
        }
    )
    (wp,) = parse_search(body)
    assert (wp.width, wp.height) == (7680, 2160)
    assert wp.filename == "wallhaven-r76wvj.jpg"
    assert wp.thumb_url.endswith("/orig/r7/r76wvj.jpg")


def test_parse_search_error():
    with pytest.raises(ValueError, match="Too Many"):
        parse_search('{"error": "Too Many Requests"}')
