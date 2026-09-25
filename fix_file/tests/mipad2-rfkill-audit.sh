#!/bin/sh
# Read-only report of Bluetooth rfkill state. HCI enumeration does not imply
# that the radio is unblocked or that pairing works.
set -u

sysfs_root=${MIPAD2_SYSFS_ROOT:-/sys}
found=0
for path in "$sysfs_root"/class/rfkill/rfkill*; do
    [ -r "$path/type" ] && [ -r "$path/name" ] &&
        [ -r "$path/soft" ] && [ -r "$path/hard" ] || continue
    [ "$(cat "$path/type" 2>/dev/null || true)" = bluetooth ] || continue
    found=1
    name=$(cat "$path/name" 2>/dev/null || echo unknown)
    soft=$(cat "$path/soft" 2>/dev/null || echo unknown)
    hard=$(cat "$path/hard" 2>/dev/null || echo unknown)
    if [ "$hard" = 1 ] && [ "$soft" = 1 ]; then
        printf 'INFO Bluetooth %s hard+soft blocked (radio function unavailable)\n' "$name"
    elif [ "$hard" = 1 ]; then
        printf 'INFO Bluetooth %s hard-blocked (radio function unavailable)\n' "$name"
    elif [ "$soft" = 1 ]; then
        printf 'INFO Bluetooth %s soft-blocked (HCI enumerated; radio function untested)\n' "$name"
    elif [ "$soft" = 0 ] && [ "$hard" = 0 ]; then
        printf 'OK   Bluetooth %s rfkill unblocked (pairing/function still untested)\n' "$name"
    else
        printf 'INFO Bluetooth %s rfkill state unknown (soft=%s hard=%s)\n' "$name" "$soft" "$hard"
    fi
done
[ "$found" -eq 1 ] || printf 'INFO Bluetooth rfkill state unavailable\n'
