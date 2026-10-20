# WallStitch

**Stitch one wallpaper seamlessly across all your monitors.**

[![CI](https://github.com/travisestill/wallstitch/actions/workflows/ci.yml/badge.svg)](https://github.com/travisestill/wallstitch/actions/workflows/ci.yml)
[![License: GPL v3+](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](LICENSE)
[![Support on Ko-fi](https://img.shields.io/badge/Ko--fi-support%20WallStitch-ff5e5b?logo=ko-fi&logoColor=white)](https://ko-fi.com/fizzy503)

![WallStitch spanning one landscape across two monitors](docs/screenshots/main.png)

Linux desktops (KDE Plasma included) can't stretch a single wallpaper across
several monitors. WallStitch reads your monitor layout, lets you position the
image visually, then cuts it into one perfectly aligned piece per screen and
sets them for you.

- **Any layout:** two 2560×1440 side by side, a 5120×1440 ultrawide, stacked
  or offset monitors, mixed resolutions, HiDPI scaling.
- **Visual editor:** drag to pan and scroll to zoom over a live preview of
  your monitors.
- **Bezel compensation:** hide a strip of the image behind the monitor frames
  so straight lines stay straight.
- **Random wallpapers:** browse 10 random images from
  [wallhaven.cc](https://wallhaven.cc) that match your desktop's shape and
  resolution (safe-for-work only); click one to download and edit it. Images
  are saved to `~/Pictures/WallStitch/`.
- **Spanning slideshow:** import up to 50 random wallpapers (or use a folder)
  and cycle through them in sync on every monitor. Plasma's own slideshow
  runs a separate timer per screen, so WallStitch uses a small background agent
  that stitches each image across all screens at once. The slideshow keeps
  running after you close the window, starts again at login, and re-fits the
  picture when you plug monitors in or out.
- **Restore:** one click puts back the wallpaper you had before.
- **CLI:** for scripts and dotfiles.

> Status: early alpha. KDE Plasma 6 is supported today; GNOME, Hyprland/Sway
> and X11 backends are planned. Contributions are welcome.

## Install

Download from the [latest release](https://github.com/travisestill/wallstitch/releases/latest):

**Flatpak (any distro):**
```bash
flatpak install --user WallStitch-*.flatpak
```
Its runtime comes from [Flathub](https://flathub.org/setup), so set that up first if you haven't.

**Ubuntu 25.10+ and other Debian-based distros that package PySide6:**
```bash
sudo apt install ./wallstitch_*_all.deb
```

Then launch **WallStitch** from your app menu. The command line works too:
`wallstitch --help` (`.deb`) or
`flatpak run io.github.travisestill.WallStitch --help` (Flatpak).

### From source

```bash
git clone https://github.com/travisestill/wallstitch.git
cd wallstitch
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/wallstitch
```

## Usage

Run `wallstitch` with no arguments to open the editor, or use the CLI:

```bash
wallstitch screens                        # show detected monitors
wallstitch set ~/Pictures/panorama.jpg    # span an image across all monitors
wallstitch set pano.jpg --bezel 40        # hide 40px behind each monitor gap
wallstitch set pano.jpg --zoom 1.3 --center 0.5,0.4 --dry-run
wallstitch reapply                        # re-apply after changing monitors
wallstitch restore                        # back to your previous wallpaper

wallstitch fetch 20                       # download 20 random wallpapers that fit
wallstitch slideshow start --fetch 30 --interval 15 --shuffle
wallstitch slideshow start --folder ~/Pictures/Panoramas
wallstitch slideshow next | stop | status
```

For best quality, use an image at least as large as your combined desktop,
for example 5120×1440 for two 1440p monitors side by side.

## How it works

1. Detects each screen's position, size and scale (via Qt, so it works on X11
   and Wayland).
2. Lays the image over the combined area, scaled to cover it, plus your pan,
   zoom and bezel settings ([`layout.py`](src/wallstitch/layout.py) is pure,
   unit-tested geometry).
3. Renders one PNG per screen into `~/.cache/wallstitch/`.
4. Hands each file to the desktop backend. On Plasma this goes through
   plasmashell's scripting API, which matches desktops to slices by screen
   position.

## Roadmap

- [x] Re-fit the slideshow automatically when monitors are plugged in or unplugged
- [ ] Do the same for a single (non-slideshow) wallpaper
- [ ] Physical-size correction for monitors with different pixel density
- [x] Synced spanning slideshows
- [ ] Layout profiles (docked / laptop only)
- [ ] Lock screen and SDDM login screen
- [ ] GNOME, Hyprland/Sway and X11 backends
- [x] Flatpak and .deb packages (on GitHub Releases)

## Packaging

- `scripts/build-deb.sh` builds the `.deb` in a clean Ubuntu container
  (podman or docker), exactly as CI does.
- `packaging/flatpak/` holds the Flatpak manifest:
  `flatpak run org.flatpak.Builder --user --install build-flatpak packaging/flatpak/io.github.travisestill.WallStitch.yml`
- Pushing a `v*` tag runs `.github/workflows/release.yml`, which builds both and
  publishes a GitHub Release with notes from `CHANGELOG.md`.

## Development

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
```

To add a desktop, implement the `Backend` protocol in
[`src/wallstitch/backends/`](src/wallstitch/backends/__init__.py)
(`apply`, `snapshot`, `restore`) and register it in `get_backend()`.

## Support

WallStitch is free and open source. If it brightens up your desk, you can
support development on [Ko-fi](https://ko-fi.com/fizzy503). ♥

## License

WallStitch is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version. See [LICENSE](LICENSE).
