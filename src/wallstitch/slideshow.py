# SPDX-FileCopyrightText: 2026 Travis Estill <immyouany@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Spanning slideshow that stays in sync across every screen.

Plasma's own slideshow runs one timer per screen, so slices of the same
picture drift apart. Instead a systemd user timer runs ``wallstitch slideshow
next`` every interval, which stitches the next image onto all screens at
once, using whatever monitor layout is current at that moment.
"""

from __future__ import annotations

import json
import random
import shlex
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from wallstitch import paths

MAX_IMAGES = 50
UNIT = "wallstitch-slideshow"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


@dataclass
class Slideshow:
    images: list[str]
    interval_minutes: int = 10
    shuffle: bool = False
    bezel: float = 0.0
    # Playback state
    order: list[int] = field(default_factory=list)
    position: int = -1

    @staticmethod
    def _path() -> Path:
        return paths.config_dir() / "slideshow.json"

    def save(self) -> None:
        self._path().parent.mkdir(parents=True, exist_ok=True)
        self._path().write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls) -> Slideshow | None:
        try:
            return cls(**json.loads(cls._path().read_text()))
        except (FileNotFoundError, json.JSONDecodeError, TypeError):
            return None

    def advance(self) -> str | None:
        """Move to the next existing image and return its path."""
        for _ in range(len(self.images)):
            self.position += 1
            if not self.order or self.position >= len(self.order):
                self.order = list(range(len(self.images)))
                if self.shuffle:
                    random.shuffle(self.order)
                self.position = 0
            image = self.images[self.order[self.position]]
            if Path(image).is_file():
                return image
        return None


def images_in(folder: Path) -> list[str]:
    """Images in ``folder``, newest first, capped at MAX_IMAGES."""
    files = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [str(p.resolve()) for p in files[:MAX_IMAGES]]


# --- systemd user timer -------------------------------------------------------


def _unit_dir() -> Path:
    return Path.home() / ".config/systemd/user"


def _systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True)


def _install_units(interval_minutes: int) -> None:
    exec_start = shlex.join([sys.executable, "-m", "wallstitch", "slideshow", "next"])
    units = {
        f"{UNIT}.service": f"""[Unit]
Description=WallStitch: show the next slideshow wallpaper
PartOf=graphical-session.target
After=graphical-session.target

[Service]
Type=oneshot
ExecStart={exec_start}
""",
        f"{UNIT}.timer": f"""[Unit]
Description=WallStitch slideshow timer
PartOf=graphical-session.target
After=graphical-session.target

[Timer]
OnActiveSec={interval_minutes}min
OnUnitActiveSec={interval_minutes}min
AccuracySec=1s

[Install]
WantedBy=graphical-session.target
""",
    }
    _unit_dir().mkdir(parents=True, exist_ok=True)
    for name, text in units.items():
        (_unit_dir() / name).write_text(text)
    _systemctl("daemon-reload")


def start(images: list[str], interval_minutes: int, shuffle: bool, bezel: float) -> Slideshow:
    """Show the first image now and schedule the rest."""
    from wallstitch.backends import BackendError

    images = images[:MAX_IMAGES]
    if not images:
        raise BackendError("the slideshow needs at least one image")
    show = Slideshow(images, max(1, interval_minutes), shuffle, bezel)
    show.save()
    next_slide()

    _install_units(show.interval_minutes)
    result = _systemctl("enable", "--now", f"{UNIT}.timer")
    if result.returncode != 0:
        raise BackendError(f"could not start the slideshow timer: {result.stderr.strip()}")
    _systemctl("restart", f"{UNIT}.timer")  # pick up a changed interval
    return show


def stop() -> None:
    _systemctl("disable", "--now", f"{UNIT}.timer")


def is_running() -> bool:
    return _systemctl("is-active", "--quiet", f"{UNIT}.timer").returncode == 0


def next_slide() -> str:
    from wallstitch.backends import BackendError
    from wallstitch.core import Settings, stitch

    show = Slideshow.load()
    if show is None:
        raise BackendError("no slideshow configured; start one first")
    image = show.advance()
    if image is None:
        raise BackendError("none of the slideshow images exist any more")
    show.save()
    stitch(Settings(image=image, bezel=show.bezel), remember=False)
    return image
