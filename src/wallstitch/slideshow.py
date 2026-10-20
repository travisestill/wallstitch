# SPDX-FileCopyrightText: 2026 Travis Estill <immyouany@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Spanning slideshow that stays in sync across every screen.

Plasma's own slideshow runs one timer per screen, so slices of the same
picture drift apart. Instead a small background agent (``wallstitch
slideshow run``, see ``agent.py``) stitches each image across all screens at
once. It is started at login through XDG autostart, or through the
Background portal when running as a Flatpak.
"""

from __future__ import annotations

import json
import os
import random
import shlex
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from wallstitch import APP_ID, paths

MAX_IMAGES = 50
AGENT_BUS_NAME = f"{APP_ID}.Slideshow"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


@dataclass
class Slideshow:
    images: list[str]
    interval_minutes: int = 10
    shuffle: bool = False
    bezel: float = 0.0
    running: bool = False
    # Playback state
    order: list[int] = field(default_factory=list)
    position: int = -1

    @staticmethod
    def path() -> Path:
        return paths.config_dir() / "slideshow.json"

    def save(self) -> None:
        self.path().parent.mkdir(parents=True, exist_ok=True)
        self.path().write_text(json.dumps(asdict(self), indent=2))

    @classmethod
    def load(cls) -> Slideshow | None:
        try:
            return cls(**json.loads(cls.path().read_text()))
        except (FileNotFoundError, json.JSONDecodeError, TypeError):
            return None

    def current(self) -> str | None:
        if 0 <= self.position < len(self.order) and self.order[self.position] < len(self.images):
            return self.images[self.order[self.position]]
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


# --- starting the agent at login ---------------------------------------------


def in_flatpak() -> bool:
    return "FLATPAK_ID" in os.environ or Path("/.flatpak-info").exists()


def agent_command() -> list[str]:
    if in_flatpak():
        return ["wallstitch", "slideshow", "run"]  # the portal wraps this in `flatpak run`
    return [sys.executable, "-m", "wallstitch", "slideshow", "run"]


def autostart_file() -> Path:
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return config / "autostart" / f"{AGENT_BUS_NAME}.desktop"


def set_autostart(enabled: bool) -> None:
    if in_flatpak():
        from wallstitch.portal import request_background

        request_background(enabled, agent_command(), "Change the wallpaper slideshow on schedule")
        return
    path = autostart_file()
    if not enabled:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=WallStitch Slideshow\n"
        "Comment=Changes your spanning wallpaper on schedule\n"
        f"Exec={shlex.join(agent_command())}\n"
        f"Icon={APP_ID}\n"
        "NoDisplay=true\n"
        "X-KDE-autostart-phase=2\n"
    )


def is_running() -> bool:
    """Whether the background agent is alive (it owns a D-Bus name)."""
    from PySide6.QtDBus import QDBusConnection

    from wallstitch.screens import ensure_app

    ensure_app()
    reply = QDBusConnection.sessionBus().interface().isServiceRegistered(AGENT_BUS_NAME)
    return bool(reply.value()) if reply.isValid() else False


def _activate_agent() -> bool:
    """Ask D-Bus to start the agent from its installed .service file.

    This runs it as an independent process (a separate sandbox instance under
    Flatpak), so the command that started the slideshow can exit right away.
    """
    from PySide6.QtDBus import QDBusConnection

    from wallstitch.screens import ensure_app

    ensure_app()
    return QDBusConnection.sessionBus().interface().startService(AGENT_BUS_NAME).isValid()


def _launch_agent() -> None:
    if _activate_agent():
        return
    if in_flatpak():
        from wallstitch.backends import BackendError

        raise BackendError("could not start the slideshow agent through D-Bus")
    # Running from a source checkout, where no D-Bus service file is installed.
    log = paths.state_dir() / "slideshow.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "ab") as err:
        subprocess.Popen(
            [sys.executable, "-m", "wallstitch", "slideshow", "run"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=err,
            start_new_session=True,
        )


# --- control -----------------------------------------------------------------


def start(images: list[str], interval_minutes: int, shuffle: bool, bezel: float) -> Slideshow:
    """Show the first image now and keep changing it in the background."""
    from wallstitch.backends import BackendError

    images = images[:MAX_IMAGES]
    if not images:
        raise BackendError("the slideshow needs at least one image")
    show = Slideshow(images, max(1, interval_minutes), shuffle, bezel, running=True)
    show.save()
    next_slide()
    set_autostart(True)
    if not is_running():
        _launch_agent()  # a running agent picks up the new settings by itself
    return show


def stop() -> None:
    """Stop the slideshow; the agent notices the config change and exits."""
    show = Slideshow.load()
    if show and show.running:
        show.running = False
        show.save()
    if show is not None or autostart_file().exists():
        set_autostart(False)


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


def reapply_current() -> None:
    """Re-stitch the current image, e.g. after the monitor layout changed."""
    from wallstitch.core import Settings, stitch

    show = Slideshow.load()
    if show and (image := show.current()) and Path(image).is_file():
        stitch(Settings(image=image, bezel=show.bezel), remember=False)
