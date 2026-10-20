# SPDX-FileCopyrightText: 2026 Travis Estill <immyouany@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
"""KDE Plasma backend, driven through plasmashell's desktop scripting API.

Desktops are matched to slices by screen position, because Plasma's screen
numbers don't map reliably to connector names.
"""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtDBus import QDBusConnection, QDBusMessage

from wallstitch.backends import BackendError
from wallstitch.layout import Screen
from wallstitch.screens import ensure_app

# FillMode 2 = "Scaled and Cropped". Slices are already the exact screen size.
_APPLY_JS = """
var slices = %s;
var ds = desktops();
var applied = 0;
for (var i = 0; i < ds.length; i++) {
    var d = ds[i];
    if (d.screen < 0) continue;
    var g = screenGeometry(d.screen);
    for (var j = 0; j < slices.length; j++) {
        var s = slices[j];
        if (s.x == g.x && s.y == g.y) {
            d.wallpaperPlugin = "org.kde.image";
            d.currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
            d.writeConfig("Image", s.uri);
            d.writeConfig("FillMode", 2);
            applied++;
        }
    }
}
print(applied);
"""

_SNAPSHOT_JS = """
var out = [];
var ds = desktops();
for (var i = 0; i < ds.length; i++) {
    var d = ds[i];
    if (d.screen < 0) continue;
    var g = screenGeometry(d.screen);
    var entry = {x: g.x, y: g.y, plugin: d.wallpaperPlugin};
    if (d.wallpaperPlugin == "org.kde.image") {
        d.currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
        entry.image = d.readConfig("Image");
        entry.fillMode = d.readConfig("FillMode");
    }
    out.push(entry);
}
print(JSON.stringify(out));
"""

_RESTORE_JS = """
var saved = %s;
var ds = desktops();
for (var i = 0; i < ds.length; i++) {
    var d = ds[i];
    if (d.screen < 0) continue;
    var g = screenGeometry(d.screen);
    for (var j = 0; j < saved.length; j++) {
        var s = saved[j];
        if (s.x != g.x || s.y != g.y) continue;
        d.wallpaperPlugin = s.plugin;
        if (s.plugin == "org.kde.image" && s.image) {
            d.currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
            d.writeConfig("Image", s.image);
            if (s.fillMode !== undefined && s.fillMode !== "") d.writeConfig("FillMode", s.fillMode);
        }
    }
}
"""


def _evaluate(script: str) -> str:
    ensure_app()
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        raise BackendError("cannot connect to the D-Bus session bus")
    msg = QDBusMessage.createMethodCall(
        "org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell", "evaluateScript"
    )
    msg.setArguments([script])
    reply = bus.call(msg)
    if reply.type() == QDBusMessage.MessageType.ErrorMessage:
        raise BackendError(f"plasmashell refused the script: {reply.errorMessage()}")
    args = reply.arguments()
    return str(args[0]).strip() if args else ""


class PlasmaBackend:
    name = "plasma"

    def apply(self, slices: dict[Screen, Path]) -> None:
        payload = [{"x": s.x, "y": s.y, "uri": Path(p).resolve().as_uri()} for s, p in slices.items()]
        applied = _evaluate(_APPLY_JS % json.dumps(payload))
        if applied in ("", "0"):
            raise BackendError("no Plasma desktop matched the detected screen layout")

    def snapshot(self) -> list[dict]:
        out = _evaluate(_SNAPSHOT_JS)
        try:
            return json.loads(out)
        except json.JSONDecodeError as e:
            raise BackendError(f"unexpected reply from plasmashell: {out!r}") from e

    def restore(self, snapshot: list[dict]) -> None:
        _evaluate(_RESTORE_JS % json.dumps(snapshot))
