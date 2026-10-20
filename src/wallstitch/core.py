# SPDX-FileCopyrightText: 2026 Travis Estill <immyouany@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
"""High-level operations shared by the CLI and the GUI."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from wallstitch import paths
from wallstitch.backends import Backend, BackendError, get_backend
from wallstitch.layout import Plan, Screen, View, plan
from wallstitch.render import load_image, render_slices
from wallstitch.screens import detect_screens


@dataclass
class Settings:
    image: str
    bezel: float = 0.0
    view: View = field(default_factory=View)

    def save(self) -> None:
        path = paths.config_dir() / "config.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls) -> Settings | None:
        path = paths.config_dir() / "config.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return cls(image=data["image"], bezel=data.get("bezel", 0.0), view=View(**data.get("view", {})))


def _snapshot_path() -> Path:
    return paths.state_dir() / "previous-wallpaper.json"


def _save_snapshot_once(backend: Backend) -> None:
    """Remember the user's own wallpaper, but never one WallStitch set."""
    snapshot = backend.snapshot()
    cache_uri = paths.cache_dir().resolve().as_uri()
    if any(str(e.get("image", "")).startswith(cache_uri) for e in snapshot):
        return
    path = _snapshot_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2))


def stitch(settings: Settings, screens: list[Screen] | None = None) -> Plan:
    screens = screens or detect_screens()
    image = load_image(settings.image)
    result = plan(screens, (image.width(), image.height()), settings.view, settings.bezel)
    files = render_slices(settings.image, image, result)

    backend = get_backend()
    _save_snapshot_once(backend)
    backend.apply({sl.screen: files[sl.screen.name] for sl in result.slices})

    settings.view = result.view
    settings.save()
    return result


def restore() -> None:
    path = _snapshot_path()
    if not path.exists():
        raise BackendError("no previous wallpaper saved - nothing to restore")
    get_backend().restore(json.loads(path.read_text()))
    path.unlink()
