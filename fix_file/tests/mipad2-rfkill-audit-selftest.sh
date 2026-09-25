#!/bin/sh
set -eu

test_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
audit=$test_dir/mipad2-rfkill-audit.sh
root=$(mktemp -d)
trap 'rm -rf "$root"' EXIT HUP INT TERM
mkdir -p "$root/class/rfkill/rfkill0"
printf 'bluetooth\n' > "$root/class/rfkill/rfkill0/type"
printf 'hci0\n' > "$root/class/rfkill/rfkill0/name"
printf '1\n' > "$root/class/rfkill/rfkill0/soft"
printf '0\n' > "$root/class/rfkill/rfkill0/hard"
output=$(MIPAD2_SYSFS_ROOT="$root" sh "$audit")
printf '%s\n' "$output" | grep -Fq 'INFO Bluetooth hci0 soft-blocked (HCI enumerated; radio function untested)'

printf '0\n' > "$root/class/rfkill/rfkill0/soft"
output=$(MIPAD2_SYSFS_ROOT="$root" sh "$audit")
printf '%s\n' "$output" | grep -Fq 'OK   Bluetooth hci0 rfkill unblocked (pairing/function still untested)'

printf '%s\n' 'PASS: Bluetooth rfkill blocked/unblocked status is distinguished from HCI enumeration.'
