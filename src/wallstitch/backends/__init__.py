# SPDX-FileCopyrightText: 2026 Travis Estill <immyouany@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Desktop-environment backends that actually set the wallpaper."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

from wallstitch.layout import Screen


class BackendError(RuntimeError):
    pass


class Backend(Protocol):
    name: str

    def apply(self, slices: dict[Screen, Path]) -> None:
        """Show each file on the screen it was rendered for."""

    def snapshot(self) -> list[dict]:
        """Return the current wallpaper settings so they can be restored."""

    def restore(self, snapshot: list[dict]) -> None: ...


def get_backend() -> Backend:
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    if "KDE" in desktop:
        from wallstitch.backends.plasma import PlasmaBackend

        return PlasmaBackend()
    raise BackendError(
        f"desktop {desktop or 'unknown'!r} is not supported yet "
        "(currently: KDE Plasma). Contributions welcome!"
    )
