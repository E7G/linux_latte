#!/bin/sh
# Read-only Mi Pad 2 hardware smoke checks; safe to run after boot or resume.
# Device numbers and I2C bus numbers are intentionally discovered at runtime.
set -u

fail=0
miss() {
    printf 'MISS %s\n' "$1"
    fail=1
}

media_node=
for node in /dev/media*; do
    if [ -c "$node" ]; then
        media_node=$node
        break
    fi
done
if [ -n "$media_node" ]; then printf 'OK   %s\n' "$media_node"; else miss '/dev/media*'; fi

video_node=
for node in /dev/video*; do
    if [ -c "$node" ]; then
        video_node=$node
        break
    fi
done
if [ -n "$video_node" ]; then printf 'OK   %s\n' "$video_node"; else miss '/dev/video*'; fi

battery_path=
for path in /sys/class/power_supply/*; do
    if [ -f "$path/type" ] && [ "$(cat "$path/type" 2>/dev/null)" = Battery ]; then
        battery_path=$path
        break
    fi
done
if [ -n "$battery_path" ]; then printf 'OK   %s\n' "$battery_path"; else miss '/sys/class/power_supply/BAT*'; fi

udc_path=$(find /sys/class/udc -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null || true)
if [ -n "$udc_path" ]; then printf 'OK   %s\n' "$udc_path"; else miss 'an actual UDC under /sys/class/udc'; fi

t4ka3_node=
for link in /sys/class/video4linux/v4l-subdev*; do
    [ -e "$link" ] || continue
    name=$(cat "$link/name" 2>/dev/null || true)
    case "$name" in
        *T4KA3*|*t4ka3*)
            t4ka3_node=/dev/${link##*/}
            break
            ;;
    esac
done
if [ -n "$t4ka3_node" ]; then
    printf 'OK   T4KA3 subdev %s\n' "$t4ka3_node"
else
    miss 'T4KA3 V4L2 subdev'
fi

vcm_path=
for path in /sys/bus/i2c/devices/*; do
    [ -e "$path" ] || continue
    name=$(cat "$path/name" 2>/dev/null || true)
    modalias=$(cat "$path/modalias" 2>/dev/null || true)
    driver=$(basename "$(readlink "$path/driver" 2>/dev/null || true)")
    case "$name $modalias $driver" in
        *dw9761*|*dw9719*)
            vcm_path=$path
            break
            ;;
    esac
done
if [ -n "$vcm_path" ]; then printf 'OK   VCM %s\n' "$vcm_path"; else miss 'DW9761/DW9719 at any I2C bus/0x0c'; fi

if [ -n "$media_node" ] && command -v media-ctl >/dev/null 2>&1; then
    graph=$(media-ctl -d "$media_node" -p 2>/dev/null || true)
    if printf '%s\n' "$graph" | grep -qi 't4ka3'; then
        printf 'OK   media graph contains T4KA3\n'
    else
        miss 'T4KA3 in media graph'
    fi
fi

if [ -n "$t4ka3_node" ] && command -v v4l2-ctl >/dev/null 2>&1; then
    if v4l2-ctl -d "$t4ka3_node" --list-ctrls >/dev/null 2>&1; then
        printf 'OK   T4KA3 controls\n'
    else
        miss "T4KA3 controls on $t4ka3_node"
    fi
fi

exit "$fail"
