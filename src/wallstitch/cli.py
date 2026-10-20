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
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command in (None, "gui"):
        from wallstitch.gui import run

        return run()

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
                stitch(settings)
                print("Wallpaper applied.")
        elif args.command == "reapply":
            settings = Settings.load()
            if settings is None:
                print("wallstitch: nothing applied yet; use `wallstitch set IMAGE`", file=sys.stderr)
                return 1
            stitch(settings)
            print("Wallpaper re-applied.")
        elif args.command == "restore":
            restore()
            print("Previous wallpaper restored.")
    except (BackendError, ValueError, OSError) as e:
        print(f"wallstitch: {e}", file=sys.stderr)
        return 1
    return 0
