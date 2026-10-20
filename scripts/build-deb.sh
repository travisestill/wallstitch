#!/bin/sh
# SPDX-FileCopyrightText: 2026 Travis Estill <immyouany@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Build the .deb inside a clean Ubuntu container (podman or docker), the same
# way CI does. Output: dist/wallstitch_<version>_all.deb
set -eu
cd "$(dirname "$0")/.."
ENGINE=${ENGINE:-$(command -v podman || command -v docker)}
IMAGE=${IMAGE:-docker.io/library/ubuntu:26.04}
mkdir -p dist
"$ENGINE" run --rm -v "$PWD:/src:ro" -v "$PWD/dist:/out" "$IMAGE" sh -euc '
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq --no-install-recommends build-essential devscripts equivs >/dev/null
  mkdir /build
  tar -C /src --exclude=./.venv --exclude=./dist --exclude=./.git -cf - . | tar -C /build -xf -
  cd /build
  mk-build-deps -i -r -t "apt-get -y -qq --no-install-recommends" debian/control >/dev/null
  dpkg-buildpackage -b -us -uc
  cp ../wallstitch_*_all.deb /out/
'
ls -l dist/*.deb
