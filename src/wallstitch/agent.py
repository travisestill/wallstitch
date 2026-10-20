# SPDX-FileCopyrightText: 2026 Travis Estill <immyouany@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Background agent behind ``wallstitch slideshow run``.

Windowless. It changes the wallpaper every interval, re-fits the current one
when monitors are plugged in or rearranged, and exits as soon as the
slideshow is stopped (it watches the config file, so the GUI and CLI control
it just by saving settings).
"""

from __future__ import annotations

import sys
import traceback

from PySide6.QtCore import QFileSystemWatcher, QTimer
from PySide6.QtDBus import QDBusConnection
from PySide6.QtGui import QGuiApplication

from wallstitch import slideshow

LAYOUT_SETTLE_MS = 2000  # monitors report several changes while (re)connecting


def _log_errors(fn):
    def wrapper(*args):
        try:
            fn(*args)
        except Exception:  # keep the agent alive; a bad image shouldn't end the slideshow
            traceback.print_exc(file=sys.stderr)

    return wrapper


def run() -> int:
    app = QGuiApplication(["wallstitch"])
    app.setQuitOnLastWindowClosed(False)

    bus = QDBusConnection.sessionBus()
    if not bus.registerService(slideshow.AGENT_BUS_NAME):
        print("wallstitch: slideshow agent already running", file=sys.stderr)
        return 0

    timer = QTimer(app)
    timer.timeout.connect(_log_errors(slideshow.next_slide))

    relayout = QTimer(app)
    relayout.setSingleShot(True)
    relayout.setInterval(LAYOUT_SETTLE_MS)
    relayout.timeout.connect(_log_errors(slideshow.reapply_current))

    def watch_screen(screen) -> None:
        screen.geometryChanged.connect(relayout.start)

    for screen in app.screens():
        watch_screen(screen)
    app.screenAdded.connect(lambda s: (watch_screen(s), relayout.start()))
    app.screenRemoved.connect(lambda _s: relayout.start())

    config = str(slideshow.Slideshow.path())
    watcher = QFileSystemWatcher([config], app)

    def reload(_path: str = "") -> None:
        if config not in watcher.files():
            watcher.addPath(config)  # editors and atomic writes replace the file
        show = slideshow.Slideshow.load()
        if show is None or not show.running:
            app.quit()
            return
        # Restarting also gives a full interval after a manual "next".
        timer.start(show.interval_minutes * 60_000)

    watcher.fileChanged.connect(reload)
    reload()
    return app.exec()
