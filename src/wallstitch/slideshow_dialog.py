# SPDX-FileCopyrightText: 2026 Travis Estill <immyouany@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Dialog to import wallpapers and run a spanning slideshow."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from wallstitch import paths, slideshow
from wallstitch.backends import BackendError
from wallstitch.wallhaven import import_random


class _Cancelled(Exception):
    pass


class ImportWorker(QObject):
    progress = Signal(int, int)
    done = Signal(list)
    failed = Signal(str)

    def __init__(self, min_width: int, min_height: int, count: int):
        super().__init__()
        self.args = (min_width, min_height, count)
        self.cancelled = False

    def _report(self, done: int, total: int) -> None:
        if self.cancelled:
            raise _Cancelled
        self.progress.emit(done, total)

    def run(self) -> None:
        try:
            files = import_random(*self.args, paths.download_dir(), self._report)
        except _Cancelled:
            self.failed.emit("cancelled")
        except (OSError, ValueError) as e:
            self.failed.emit(str(e))
        else:
            self.done.emit([str(f) for f in files])


class SlideshowDialog(QDialog):
    def __init__(self, desktop_size: tuple[int, int], bezel: float, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Slideshow")
        self.desktop_size = desktop_size
        self.bezel = bezel
        self._thread: QThread | None = None

        # --- choose images ---
        self.count = QSpinBox()
        self.count.setRange(1, slideshow.MAX_IMAGES)
        self.count.setValue(20)
        self.import_btn = QPushButton("Import from Wallhaven")
        self.import_btn.setToolTip(
            f"Download random wallpapers that fit your {desktop_size[0]}×{desktop_size[1]} desktop"
        )
        self.import_btn.clicked.connect(self.import_random)
        folder_btn = QPushButton("Use Folder…")
        folder_btn.setToolTip(f"Use the newest {slideshow.MAX_IMAGES} images in a folder")
        folder_btn.clicked.connect(self.use_folder)

        import_row = QHBoxLayout()
        import_row.addWidget(QLabel("Get"))
        import_row.addWidget(self.count)
        import_row.addWidget(QLabel("random wallpapers"))
        import_row.addWidget(self.import_btn)
        import_row.addStretch()
        import_row.addWidget(folder_btn)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.list = QListWidget()
        self.list.setMinimumHeight(200)
        self.summary = QLabel()

        images_box = QGroupBox("Images")
        images_layout = QVBoxLayout(images_box)
        images_layout.addLayout(import_row)
        images_layout.addWidget(self.progress)
        images_layout.addWidget(self.list)
        images_layout.addWidget(self.summary)

        # --- playback ---
        self.interval = QSpinBox()
        self.interval.setRange(1, 24 * 60)
        self.interval.setValue(10)
        self.interval.setSuffix(" min")
        self.shuffle = QCheckBox("Random order")
        form = QFormLayout()
        form.addRow("Change every:", self.interval)
        form.addRow("", self.shuffle)

        self.status = QLabel()
        self.start_btn = QPushButton("Start Slideshow")
        self.start_btn.setDefault(True)
        self.start_btn.clicked.connect(self.start)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)

        bar = QHBoxLayout()
        bar.addWidget(self.status, 1)
        bar.addWidget(self.stop_btn)
        bar.addWidget(self.start_btn)
        bar.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(images_box)
        layout.addLayout(form)
        layout.addLayout(bar)
        self.resize(620, 480)

        existing = slideshow.Slideshow.load()
        if existing:
            self.set_images(existing.images)
            self.interval.setValue(existing.interval_minutes)
            self.shuffle.setChecked(existing.shuffle)
        else:
            self.set_images([])
        self.refresh_status()

    # --- images ---------------------------------------------------------------

    def set_images(self, images: list[str]) -> None:
        self.images = images[: slideshow.MAX_IMAGES]
        self.list.clear()
        for image in self.images:
            item = QListWidgetItem(Path(image).name)
            item.setToolTip(image)
            self.list.addItem(item)
        self.summary.setText(f"{len(self.images)} of max {slideshow.MAX_IMAGES} images")
        self.start_btn.setEnabled(bool(self.images))

    def use_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Slideshow folder", str(paths.download_dir()))
        if folder:
            self.set_images(slideshow.images_in(Path(folder)))

    def import_random(self) -> None:
        self.import_btn.setEnabled(False)
        self.start_btn.setEnabled(False)
        self.progress.setRange(0, 0)  # busy until we know how many were found
        self.progress.setVisible(True)
        self.status.setText("Searching wallhaven…")

        self._thread = QThread(self)
        self._worker = ImportWorker(*self.desktop_size, self.count.value())
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_imported)
        self._worker.failed.connect(self._on_import_failed)
        for signal in (self._worker.done, self._worker.failed):
            signal.connect(self._thread.quit)
        self._thread.start()

    def _on_progress(self, done: int, total: int) -> None:
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(done)
        self.status.setText(f"Downloading {min(done + 1, total)} of {total}…")

    def _import_finished(self) -> None:
        self.progress.setVisible(False)
        self.import_btn.setEnabled(True)
        self.start_btn.setEnabled(bool(self.images))

    def _on_imported(self, files: list[str]) -> None:
        self.set_images(files)
        self._import_finished()
        if files:
            self.status.setText(f"Imported {len(files)} wallpapers to {paths.download_dir()}")
        else:
            self.status.setText("No wallpapers found for this desktop size.")

    def _on_import_failed(self, message: str) -> None:
        self._import_finished()
        self.status.setText(f"Import failed: {message}")

    # --- playback -------------------------------------------------------------

    def refresh_status(self) -> None:
        running = slideshow.is_running()
        self.stop_btn.setEnabled(running)
        show = slideshow.Slideshow.load() if running else None
        if show:
            self.status.setText(
                f"Running: {len(show.images)} images, changing every {show.interval_minutes} min."
            )
        else:
            self.status.setText("Not running.")

    def start(self) -> None:
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            slideshow.start(self.images, self.interval.value(), self.shuffle.isChecked(), self.bezel)
        except (BackendError, ValueError, OSError) as e:
            self.status.setText(f"Could not start: {e}")
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.refresh_status()

    def stop(self) -> None:
        slideshow.stop()
        self.refresh_status()

    def done(self, result: int) -> None:
        if self._thread and self._thread.isRunning():
            # Stops before the next download; at most waits out the current one.
            self._worker.cancelled = True
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            self._thread.wait()
            QApplication.restoreOverrideCursor()
        super().done(result)
