# SPDX-FileCopyrightText: 2026 Travis Estill <immyouany@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Dialog that shows random wallhaven.cc wallpapers sized for the desktop."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QImage, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QToolButton,
    QVBoxLayout,
)

from wallstitch import __version__
from wallstitch.paths import download_dir
from wallstitch.wallhaven import Wallpaper, best_ratio, parse_search, search_url

COUNT = 10
THUMB_WIDTH = 300


class WallhavenDialog(QDialog):
    """Pick one of 10 random wallpapers; ``chosen_path`` is set on accept."""

    def __init__(self, min_width: int, min_height: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Random Wallpapers from Wallhaven")
        self.min_width, self.min_height = min_width, min_height
        self.ratio = best_ratio(min_width, min_height)
        self.chosen_path: Path | None = None
        self._replies: list[QNetworkReply] = []
        self._tried_without_ratio = False

        self.net = QNetworkAccessManager(self)

        aspect = min_width / min_height
        self.icon_size = QSize(THUMB_WIDTH, max(80, round(THUMB_WIDTH / aspect)))
        columns = 2 if aspect >= 2 else 5

        self.buttons: list[QToolButton] = []
        grid = QGridLayout()
        for i in range(COUNT):
            btn = QToolButton()
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            btn.setIconSize(self.icon_size)
            btn.setAutoRaise(True)
            btn.setVisible(False)
            btn.clicked.connect(lambda _=False, i=i: self.choose(i))
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(
                lambda _pos, i=i: QDesktopServices.openUrl(QUrl(self.wallpapers[i].page_url))
            )
            grid.addWidget(btn, i // columns, i % columns)
            self.buttons.append(btn)
        self.wallpapers: list[Wallpaper] = []

        self.status = QLabel()
        self.progress = QProgressBar()
        self.progress.setVisible(False)

        self.shuffle_btn = QPushButton("Shuffle")
        self.shuffle_btn.setToolTip("Show 10 different wallpapers")
        self.shuffle_btn.clicked.connect(self.shuffle)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)

        bar = QHBoxLayout()
        bar.addWidget(self.status, 1)
        bar.addWidget(self.shuffle_btn)
        bar.addWidget(cancel)

        layout = QVBoxLayout(self)
        layout.addLayout(grid)
        layout.addWidget(self.progress)
        layout.addLayout(bar)

        self.shuffle()

    # --- networking --------------------------------------------------------

    def _get(self, url: str) -> QNetworkReply:
        request = QNetworkRequest(QUrl(url))
        request.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, f"WallStitch/{__version__}")
        reply = self.net.get(request)
        self._replies.append(reply)
        reply.finished.connect(lambda: self._replies.remove(reply) if reply in self._replies else None)
        return reply

    def _abort_all(self) -> None:
        for reply in list(self._replies):
            reply.abort()

    def shuffle(self) -> None:
        self._abort_all()
        self._tried_without_ratio = False
        self._search(self.ratio)

    def _search(self, ratio: str | None) -> None:
        for btn in self.buttons:
            btn.setVisible(False)
        self.shuffle_btn.setEnabled(False)
        shape = f"{ratio.replace('x', ':')} " if ratio else ""
        self.status.setText(f"Searching for {shape}wallpapers ≥ {self.min_width}×{self.min_height}…")
        reply = self._get(search_url(self.min_width, self.min_height, ratio))
        reply.finished.connect(lambda: self._on_search(reply))

    def _on_search(self, reply: QNetworkReply) -> None:
        self.shuffle_btn.setEnabled(True)
        if reply.error() == QNetworkReply.NetworkError.OperationCanceledError:
            return
        if reply.error() != QNetworkReply.NetworkError.NoError:
            self.status.setText(f"Couldn't reach wallhaven: {reply.errorString()}")
            return
        try:
            results = parse_search(bytes(reply.readAll()))
        except ValueError as e:
            self.status.setText(f"Wallhaven error: {e}")
            return

        if not results and self.ratio and not self._tried_without_ratio:
            # Rare layouts may have no exact-ratio images; accept any shape.
            self._tried_without_ratio = True
            self._search(None)
            return
        if not results:
            self.status.setText("No wallpapers found at this resolution.")
            return

        self.wallpapers = results[:COUNT]
        for btn, wp in zip(self.buttons, self.wallpapers, strict=False):
            btn.setIcon(QPixmap())
            btn.setText(f"{wp.width}×{wp.height}")
            btn.setToolTip(f"{wp.page_url}\nClick to use · right-click to open on wallhaven")
            btn.setVisible(True)
            thumb = self._get(wp.thumb_url)
            thumb.finished.connect(lambda thumb=thumb, btn=btn: self._on_thumb(thumb, btn))
        self.status.setText("Click a wallpaper to use it.")

    def _on_thumb(self, reply: QNetworkReply, btn: QToolButton) -> None:
        if reply.error() != QNetworkReply.NetworkError.NoError:
            return
        image = QImage.fromData(bytes(reply.readAll()))
        if image.isNull():
            return
        scaled = image.scaled(
            self.icon_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        btn.setIcon(QPixmap.fromImage(scaled))

    # --- choosing ----------------------------------------------------------

    def choose(self, index: int) -> None:
        wp = self.wallpapers[index]
        target = download_dir() / wp.filename
        if target.is_file():
            self.chosen_path = target
            self.accept()
            return

        self._abort_all()
        for btn in self.buttons:
            btn.setEnabled(False)
        self.shuffle_btn.setEnabled(False)
        self.status.setText(f"Downloading {wp.width}×{wp.height} wallpaper…")
        self.progress.setValue(0)
        self.progress.setVisible(True)

        reply = self._get(wp.image_url)
        reply.downloadProgress.connect(self._on_progress)
        reply.finished.connect(lambda: self._on_download(reply, target))

    def _on_progress(self, received: int, total: int) -> None:
        if total > 0:
            self.progress.setValue(round(received * 100 / total))

    def _on_download(self, reply: QNetworkReply, target: Path) -> None:
        self.progress.setVisible(False)
        for btn in self.buttons:
            btn.setEnabled(True)
        self.shuffle_btn.setEnabled(True)
        if reply.error() == QNetworkReply.NetworkError.OperationCanceledError:
            return
        if reply.error() != QNetworkReply.NetworkError.NoError:
            self.status.setText(f"Download failed: {reply.errorString()}")
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(target.suffix + ".part")
        partial.write_bytes(bytes(reply.readAll()))
        partial.replace(target)
        self.chosen_path = target
        self.accept()

    def reject(self) -> None:
        self._abort_all()
        super().reject()
