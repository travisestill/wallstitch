# SPDX-FileCopyrightText: 2026 Travis Estill <immyouany@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
"""XDG desktop portal calls used when running inside Flatpak."""

from __future__ import annotations

from PySide6.QtDBus import QDBusConnection, QDBusMessage

from wallstitch.screens import ensure_app


def request_background(autostart: bool, commandline: list[str], reason: str) -> None:
    """Ask to run in the background and (not) be started at login.

    The portal answers asynchronously and may show the user a prompt; the
    slideshow keeps working for this session either way, so we don't wait.
    """
    ensure_app()
    msg = QDBusMessage.createMethodCall(
        "org.freedesktop.portal.Desktop",
        "/org/freedesktop/portal/desktop",
        "org.freedesktop.portal.Background",
        "RequestBackground",
    )
    msg.setArguments(["", {"reason": reason, "autostart": autostart, "commandline": commandline}])
    QDBusConnection.sessionBus().call(msg)
