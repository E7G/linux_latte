#!/bin/sh
# Read-only Mi Pad 2 hardware smoke checks; safe to run after boot or resume.
set -eu

fail=0
check_path() {
    if [ -e "$1" ]; then printf 'OK   %s\n' "$1"; else printf 'MISS %s\n' "$1"; fail=1; fi
}

check_path /dev/media0
check_path /dev/video0
check_path /dev/v4l-subdev4
check_path /sys/class/power_supply/BAT0
check_path /sys/class/udc

if [ -d /sys/bus/i2c/devices/6-000c ]; then
    printf 'OK   DW9761 at i2c-6/0x0c\n'
else
    printf 'MISS DW9761 at i2c-6/0x0c\n'
    fail=1
fi

if command -v v4l2-ctl >/dev/null 2>&1; then
    v4l2-ctl -d /dev/v4l-subdev4 --list-ctrls >/dev/null
    printf 'OK   T4KA3 controls\n'
fi

exit "$fail"
