#!/bin/sh
# Read-only Mi Pad 2 hardware smoke checks; safe to run after boot or resume.
# Device numbers and I2C bus numbers are intentionally discovered at runtime.
set -u

fail=0
miss() {
    printf 'MISS %s\n' "$1"
    fail=1
}

optional() {
    printf 'INFO %s\n' "$1"
}

printf 'Mi Pad 2 kernel health (%s)\n' "$(uname -r 2>/dev/null || echo unknown)"

if mountpoint -q /boot 2>/dev/null; then
    printf 'OK   /boot mounted\n'
else
    miss '/boot mounted'
fi

wifi_node=
for path in /sys/class/net/*/wireless; do
    [ -d "$path" ] || continue
    wifi_node=${path%/wireless}
    break
done
if [ -n "$wifi_node" ]; then
    printf 'OK   Wi-Fi %s (%s)\n' "${wifi_node##*/}" \
        "$(cat "$wifi_node/operstate" 2>/dev/null || echo unknown)"
else
    miss 'Wi-Fi interface'
fi

bt_node=
for path in /sys/class/bluetooth/hci*; do
    [ -d "$path" ] || continue
    bt_node=$path
    break
done
if [ -n "$bt_node" ]; then
    printf 'OK   Bluetooth %s\n' "${bt_node##*/}"
else
    miss 'Bluetooth HCI device'
fi

if [ -r /proc/asound/cards ] && grep -q '^[[:space:]]*[0-9]' /proc/asound/cards; then
    printf 'OK   ALSA sound card\n'
else
    miss 'ALSA sound card'
fi

backlight_path=
for path in /sys/class/backlight/*; do
    [ -f "$path/max_brightness" ] || continue
    backlight_path=$path
    break
done
if [ -n "$backlight_path" ]; then
    printf 'OK   backlight %s\n' "${backlight_path##*/}"
else
    miss 'LCD backlight'
fi

touch_name=
for path in /sys/class/input/event*/device/name; do
    [ -r "$path" ] || continue
    name=$(cat "$path" 2>/dev/null || true)
    case "$name" in
        *[Tt]ouch*|*Goodix*|*Silead*|*MSSL*)
            touch_name=$name
            break
            ;;
    esac
done
if [ -n "$touch_name" ]; then
    printf 'OK   touchscreen %s\n' "$touch_name"
else
    optional 'touchscreen name not recognized (check manually)'
fi

if [ -e /dev/ttyGS0 ]; then
    printf 'OK   USB serial /dev/ttyGS0\n'
else
    optional 'USB serial gadget is not currently attached'
fi

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
