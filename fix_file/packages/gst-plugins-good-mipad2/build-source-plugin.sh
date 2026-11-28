#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
# Build an unqualified AtomISP plugin without the historical local SDK.
set -euo pipefail

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
[[ $# == 1 ]] || die "usage: $0 NEW_OUTPUT_DIRECTORY"
[[ $EUID != 0 ]] || die 'run the source build as a regular user'
[[ $(uname -m) == x86_64 ]] || die 'the pinned SDK is x86_64 only'

export LC_ALL=C TZ=UTC SOURCE_DATE_EPOCH=1788739200
unset PKG_CONFIG_PATH PKG_CONFIG_LIBDIR PKG_CONFIG_SYSROOT_DIR
unset CC CXX CFLAGS CXXFLAGS CPPFLAGS LDFLAGS
unset GST_PLUGIN_PATH GST_PLUGIN_SYSTEM_PATH GST_PLUGIN_SCANNER GST_PLUGIN_SCANNER_1_0
unset GST_REGISTRY GST_REGISTRY_1_0 GST_REGISTRY_UPDATE GST_REGISTRY_FORK
fix=$(realpath -- "$(dirname -- "$0")/../..")
version=1.28.7
archive=gst-plugins-good-$version.tar.xz
archive_sha=87256969c82cf3bc8574301f3e7044a90de0ac500a5a27d8ba38c4dde894dd8b

for name in gstreamer gst-plugins-base-libs; do
    [[ $(pacman -Q "$name") == "$name $version-1" ]] ||
        die "$name must be the Arch $version-1 package"
done

mkdir -- "$1"
out=$(realpath -- "$1")
work=$(mktemp -d)
trap 'rm -rf -- "$work"' EXIT
cd -- "$work"
mkdir src

curl --disable --fail --show-error --silent --location --proto '=https' \
    --proto-redir '=https' --connect-timeout 15 --max-time 180 --retry 3 \
    -o "$archive" "https://gstreamer.freedesktop.org/src/gst-plugins-good/$archive"
printf '%s  %s\n' "$archive_sha" "$archive" | sha256sum --check
tar -xf "$archive" --strip-components=1 -C src
for patch in gstreamer-v4l2src-early-latency.patch gstreamer-v4l2-atomisp-stepwise.patch; do
    patch --batch --forward --fuzz=0 -d src -p1 < "$fix/$patch"
done

export CC=gcc CXX=g++
export CFLAGS="-ffile-prefix-map=$work=/mipad2-gst-build"
export CXXFLAGS="$CFLAGS"
meson setup obj src --wrap-mode=nodownload --buildtype=release \
    -Dauto_features=disabled -Dv4l2=enabled -Dv4l2-libv4l2=enabled \
    -Dv4l2-gudev=enabled -Dexamples=disabled -Dtests=disabled \
    -Ddoc=disabled -Dnls=disabled
ninja -C obj sys/v4l2/libgstvideo4linux2.so

plugin=libgstvideo4linux2.so
install -m755 "obj/sys/v4l2/$plugin" "$out/$plugin"
readelf -d "$out/$plugin" > "$out/elf-dynamic.txt"
grep -F '[libv4l2.so.0]' "$out/elf-dynamic.txt"
grep -F '[libgudev-1.0.so.0]' "$out/elf-dynamic.txt"

python3 -B "$fix/tests/mipad2-gst-atomisp-stepwise-test.py" src/sys/v4l2/gstv4l2object.c > caps-test.c
# pkg-config emits separate arguments for the exact SDK installed above.
# shellcheck disable=SC2046
gcc -O2 -Wall -Wextra -Werror caps-test.c -o caps-test $(pkg-config --cflags --libs gstreamer-1.0)
./caps-test | tee "$out/caps-test.txt"

export GST_PLUGIN_SYSTEM_PATH_1_0= GST_PLUGIN_PATH_1_0="$out" GST_REGISTRY_1_0="$work/registry.bin"
gst-inspect-1.0 v4l2src > "$out/gst-inspect-v4l2src.txt"
awk -v file="$out/$plugin" '
    $1 == "Filename" { found_file = substr($0, index($0, $2)) == file }
    $1 == "Version"  { found_version = $2 == "1.28.7" }
    END { exit !(found_file && found_version) }
' "$out/gst-inspect-v4l2src.txt" || die 'gst-inspect did not load the rebuilt 1.28.7 plugin'

(
    printf 'status=host-validated-candidate-not-for-deployment\n'
    printf 'source_sha256=%s\n' "$archive_sha"
    sha256sum "$fix/gstreamer-v4l2src-early-latency.patch" "$fix/gstreamer-v4l2-atomisp-stepwise.patch" |
        sed "s#  .*/#  #"
    pacman -Q
) > "$out/build-inputs.txt"
(cd -- "$out" && sha256sum "$plugin" > SHA256SUMS)
