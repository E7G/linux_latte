#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
set -eu

repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
script="$repo/fix_file/packages/gst-plugins-good-mipad2/mipad2-atomisp-frameintervals"
root=$(mktemp -d)
trap 'rm -f "$root/functions" "$root/product" "$root/param" "$root/manifest" "$root/plugin" "$root/versions" "$root/state/lock" "$root/state/inhibit"; rmdir "$root/state" "$root" 2>/dev/null || :' EXIT
sed '/^main "\$@"$/d' "$script" > "$root/functions"
. "$root/functions"

product=$root/product
parameter=$root/param
manifest=$root/manifest
plugin=$root/plugin
state=$root/state
expected_versions='gstreamer 1.28.7-1
gst-plugins-base-libs 1.28.7-1
gst-plugins-good 1.28.7-1.1'
runtime_versions() { cat "$root/versions"; }

check() { test "$(cat "$parameter")" = "$1"; }
printf '%s\n' "$expected_versions" > "$root/versions"
printf 'Mipad2\n' > "$product"
printf 'N\n' > "$parameter"
printf 'paired version\n' > "$plugin"
sha256sum "$plugin" | cut -d ' ' -f 1 > "$manifest"

run_gate enable
check Y
run_gate disable
check N

printf 'another board\n' > "$product"
run_gate enable
check N
printf 'Mipad2\n' > "$product"
printf 'Y\n' > "$parameter"
printf 'gst-plugins-good 1.28.7-1\n' > "$root/versions"
run_gate enable
check N
printf '%s\n' "$expected_versions" > "$root/versions"
printf 'other binary\n' > "$plugin"
run_gate enable
check N
sha256sum "$plugin" | cut -d ' ' -f 1 > "$manifest"
run_gate enable
check Y

# The transaction hook must still disarm when product detection fails.
rm -f "$product"
run_gate inhibit
check N
test -f "$state/inhibit"
printf 'Mipad2\n' > "$product"
run_gate enable
check N

# Fresh boot: marker gone, kernel initially N. A valid pair can arm again.
rm -f "$state/inhibit"
run_gate enable
check Y
rm -f "$parameter"
run_gate inhibit
test -f "$state/inhibit"
printf 'N\n' > "$parameter"
run_gate enable
check N

rc=0
run_gate invalid || rc=$?
test "$rc" -eq 2
printf 'PASS: qualified enable, disable, board/version/hash checks, update inhibitor, reload and fresh boot\n'
