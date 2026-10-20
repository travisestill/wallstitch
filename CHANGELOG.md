# Changelog

All notable changes to WallStitch are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-10-20

First release.

### Added
- Span one wallpaper across any monitor layout on KDE Plasma 6 (multi-monitor,
  ultrawide, stacked/offset, mixed resolutions, HiDPI).
- Visual editor with drag-to-pan, scroll-to-zoom and bezel compensation.
- Random wallpapers from wallhaven.cc sized for your desktop.
- Synced spanning slideshow of up to 50 images, run by a background agent that
  starts at login and re-fits the image when monitors change.
- Preview and frame each slideshow image individually; framing is saved per
  image.
- Restore the wallpaper you had before WallStitch.
- Packages: Flatpak (any distro) and .deb (Ubuntu 25.10+).
- Command-line interface: `screens`, `set`, `reapply`, `restore`, `fetch`,
  `slideshow start|stop|next|status`.

[0.1.0]: https://github.com/travisestill/wallstitch/releases/tag/v0.1.0
