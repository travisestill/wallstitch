# SPDX-FileCopyrightText: 2026 Travis Estill <immyouany@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
"""Command-line interface. Running ``wallstitch`` with no arguments opens the GUI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from wallstitch import __version__


def _parse_center(value: str) -> tuple[float, float]:
    try:
        x, y = (float(v) for v in value.split(","))
    except ValueError:
        raise argparse.ArgumentTypeError("expected X,Y between 0 and 1, e.g. 0.5,0.4") from None
    return x, y


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="wallstitch", description="Stitch one wallpaper seamlessly across all your monitors."
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command")

    sub.add_parser("gui", help="open the visual editor (default)")
    sub.add_parser("screens", help="list detected monitors")

    s = sub.add_parser("set", help="span an image across all monitors")
    s.add_argument("image", type=Path)
    s.add_argument(
        "--bezel",
        type=float,
        default=0.0,
        metavar="PX",
        help="hide PX pixels of image between neighbouring monitors (bezel compensation)",
    )
    s.add_argument("--zoom", type=float, default=1.0, help="1.0 = just cover all screens (default)")
    s.add_argument(
        "--center",
        type=_parse_center,
        default=(0.5, 0.5),
        metavar="X,Y",
        help="point of the image (0-1) to centre on, default 0.5,0.5",
    )
    s.add_argument("--dry-run", action="store_true", help="print the plan without changing anything")

    sub.add_parser("reapply", help="re-apply the last wallpaper (e.g. after a layout change)")
    sub.add_parser("restore", help="put back the wallpaper you had before WallStitch")

    f = sub.add_parser("fetch", help="download N random wallpapers from wallhaven.cc that fit your monitors")
    f.add_argument("count", type=_count)
    f.add_argument("--dir", type=Path, help="where to save them (default ~/Pictures/WallStitch)")

    show = sub.add_parser("slideshow", help="cycle through up to 50 wallpapers in sync on all monitors")
    show_sub = show.add_subparsers(dest="action", required=True, metavar="{start,stop,next,status}")
    start = show_sub.add_parser("start", help="start a slideshow")
    source = start.add_mutually_exclusive_group(required=True)
    source.add_argument("--folder", type=Path, help="use the newest 50 images in this folder")
    source.add_argument("--fetch", type=_count, metavar="N", help="download N random wallpapers and use them")
    source.add_argument("--images", type=Path, nargs="+", metavar="IMAGE", help="use these images")
    start.add_argument(
        "--interval", type=int, default=10, metavar="MIN", help="minutes per image (default 10)"
    )
    start.add_argument("--shuffle", action="store_true", help="random order")
    start.add_argument("--bezel", type=float, default=0.0, metavar="PX", help="bezel compensation")
    show_sub.add_parser("stop", help="stop the slideshow (keeps the current image)")
    show_sub.add_parser("next", help="skip to the next image")
    show_sub.add_parser("status", help="show whether a slideshow is running")
    show_sub.add_parser("run", help=argparse.SUPPRESS)  # the background agent itself
    return p


def _count(value: str) -> int:
    from wallstitch.slideshow import MAX_IMAGES

    n = int(value)
    if not 1 <= n <= MAX_IMAGES:
        raise argparse.ArgumentTypeError(f"must be between 1 and {MAX_IMAGES}")
    return n


def _fetch(count: int, dest: Path) -> list[Path]:
    from wallstitch.screens import desktop_pixel_size, detect_screens
    from wallstitch.wallhaven import import_random

    def progress(done: int, total: int) -> None:
        print(f"\rDownloading {done}/{total}…", end="", flush=True)

    files = import_random(*desktop_pixel_size(detect_screens()), count, dest, progress)
    print()
    return files


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command in (None, "gui"):
        from wallstitch.gui import run

        return run()

    from wallstitch import paths, slideshow
    from wallstitch.backends import BackendError
    from wallstitch.core import Settings, restore, stitch
    from wallstitch.layout import View, plan
    from wallstitch.screens import detect_screens

    try:
        if args.command == "screens":
            for s in detect_screens():
                print(f"{s.name:<12} {s.width}x{s.height} at {s.x},{s.y}  scale {s.scale:g}")
        elif args.command == "set":
            if not args.image.is_file():
                print(f"wallstitch: no such file: {args.image}", file=sys.stderr)
                return 2
            settings = Settings(
                image=str(args.image.resolve()),
                bezel=args.bezel,
                view=View(args.zoom, *args.center),
            )
            if args.dry_run:
                from wallstitch.render import load_image

                img = load_image(settings.image)
                result = plan(detect_screens(), (img.width(), img.height()), settings.view, settings.bezel)
                canvas = f"{result.canvas_width:g}x{result.canvas_height:g}"
                print(f"image {img.width()}x{img.height()}, canvas {canvas}")
                for sl in result.slices:
                    r = sl.source
                    region = f"{r.width:.0f}x{r.height:.0f} at {r.x:.0f},{r.y:.0f}"
                    print(f"{sl.screen.name:<12} <- image region {region}")
            else:
                slideshow.stop()
                stitch(settings)
                print("Wallpaper applied.")
        elif args.command == "reapply":
            settings = Settings.load()
            if settings is None:
                print("wallstitch: nothing applied yet; use `wallstitch set IMAGE`", file=sys.stderr)
                return 1
            slideshow.stop()
            stitch(settings)
            print("Wallpaper re-applied.")
        elif args.command == "restore":
            restore()
            print("Previous wallpaper restored.")
        elif args.command == "fetch":
            dest = args.dir or paths.download_dir()
            files = _fetch(args.count, dest)
            print(f"Saved {len(files)} wallpapers to {dest}")
        elif args.command == "slideshow":
            return _slideshow(args)
    except (BackendError, ValueError, OSError) as e:
        print(f"wallstitch: {e}", file=sys.stderr)
        return 1
    return 0


def _slideshow(args: argparse.Namespace) -> int:
    from wallstitch import paths, slideshow

    if args.action == "start":
        if args.fetch:
            images = [str(p) for p in _fetch(args.fetch, paths.download_dir())]
        elif args.folder:
            images = slideshow.images_in(args.folder)
        else:
            images = [str(p.resolve()) for p in args.images if p.is_file()]
        show = slideshow.start(images, args.interval, args.shuffle, args.bezel)
        print(f"Slideshow started: {len(show.images)} images, every {show.interval_minutes} min.")
    elif args.action == "stop":
        slideshow.stop()
        print("Slideshow stopped.")
    elif args.action == "run":
        from wallstitch.agent import run

        return run()
    elif args.action == "next":
        print(f"Now showing {slideshow.next_slide()}")
    elif args.action == "status":
        show = slideshow.Slideshow.load()
        if show and slideshow.is_running():
            n = show.position + 1
            print(f"Running: image {n} of {len(show.images)}, every {show.interval_minutes} min.")
        else:
            print("Not running.")
    return 0
