#!/bin/sh
# Mi Pad 2 hardware smoke checks; read-only unless
# MIPAD2_ACTIVE_CAMERA_TEST=1 is explicitly set.
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

release=$(uname -r 2>/dev/null || echo unknown)
printf 'Mi Pad 2 kernel health (%s)\n' "$release"

if [ -d "/usr/lib/modules/$release" ] &&
   [ -s "/usr/lib/modules/$release/modules.dep" ]; then
    printf 'OK   matching module tree and modules.dep\n'
else
    miss "matching /usr/lib/modules/$release tree"
fi

if [ -r /proc/config.gz ]; then
    printf 'OK   running kernel config /proc/config.gz\n'
else
    miss 'running kernel config /proc/config.gz'
fi

cpu_online=$(cat /sys/devices/system/cpu/online 2>/dev/null || true)
if [ -n "$cpu_online" ]; then printf 'OK   CPUs online %s\n' "$cpu_online"; else miss 'CPU online state'; fi
if [ -d /sys/devices/system/cpu/cpu0/cpufreq ] ||
   find /sys/devices/system/cpu/cpufreq -mindepth 1 -maxdepth 1 -type d -print -quit 2>/dev/null | grep -q .; then
    printf 'OK   CPU frequency scaling\n'
else
    miss 'CPU frequency scaling'
fi

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
    wifi_driver=$(basename "$(readlink "$wifi_node/device/driver" 2>/dev/null || true)")
    [ "$wifi_driver" = brcmfmac ] && printf 'OK   Wi-Fi driver brcmfmac\n' || miss 'Wi-Fi bound to brcmfmac'
else
    miss 'Wi-Fi interface'
fi

if find /usr/lib/firmware/brcm -maxdepth 1 \
    \( -name 'brcmfmac4356-pcie.bin*' -o -name 'brcmfmac4356-pcie.Xiaomi*' \) \
    -print -quit 2>/dev/null | grep -q .; then
    printf 'OK   BCM4356 Wi-Fi firmware/NVRAM\n'
else
    miss 'BCM4356 Wi-Fi firmware/NVRAM'
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

if find /usr/lib/firmware/brcm -maxdepth 1 -iname 'BCM4356A2.hcd*' \
    -print -quit 2>/dev/null | grep -q .; then
    printf 'OK   BCM4356A2 Bluetooth firmware\n'
else
    miss 'BCM4356A2 Bluetooth firmware'
fi

if [ -r /proc/asound/cards ] && grep -Eqi 'rt5659|cht.*5659' /proc/asound/cards; then
    printf 'OK   RT5659 ALSA sound card\n'
else
    miss 'RT5659 ALSA sound card'
fi

if [ -s /usr/share/alsa/ucm2/conf.d/cht-bsw-rt5659/HiFi.conf ]; then
    printf 'OK   RT5659 ALSA UCM profile\n'
else
    miss 'RT5659 ALSA UCM profile'
fi

tfa_count=0
for path in /sys/bus/i2c/devices/*/name; do
    [ -r "$path" ] || continue
    case "$(cat "$path" 2>/dev/null)" in
        tfa9890|tfa989x) tfa_count=$((tfa_count + 1)) ;;
    esac
done
if [ "$tfa_count" -ge 2 ]; then
    printf 'OK   dual TFA9890 speaker amplifiers (%s)\n' "$tfa_count"
else
    miss "dual TFA9890 speaker amplifiers (found $tfa_count)"
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
    device_path=$(readlink -f "${path%/name}" 2>/dev/null || true)
    case "$name $device_path" in
        *[Tt]ouch*|*Goodix*|*Silead*|*MSSL*|*FTSC1000*|*"hid-over-i2c 2808:509C"*)
            touch_name=$name
            break
            ;;
    esac
done
if [ -n "$touch_name" ]; then
    printf 'OK   touchscreen %s\n' "$touch_name"
else
    miss 'FTSC1000 touchscreen input device'
fi

button_name=
for path in /sys/class/input/event*/device/name; do
    [ -r "$path" ] || continue
    name=$(cat "$path" 2>/dev/null || true)
    case "$name" in
        *[Ss]oc*[Bb]utton*|*[Vv]irtual*[Bb]utton*|*gpio-keys*)
            button_name=$name
            break
            ;;
    esac
done
if [ -n "$button_name" ]; then
    printf 'OK   power/volume buttons %s\n' "$button_name"
else
    miss 'power/volume button input device'
fi

if [ -e /sys/class/drm/card0 ] && [ -e /sys/class/drm/renderD128 ]; then
    printf 'OK   i915 DRM card and render node\n'
else
    miss 'i915 DRM card/render node'
fi

display_connected=
for status in /sys/class/drm/card*-*/status; do
    [ -r "$status" ] || continue
    [ "$(cat "$status" 2>/dev/null)" = connected ] && display_connected=$status && break
done
if [ -n "$display_connected" ]; then
    printf 'OK   display connector %s\n' "${display_connected%/status}"
else
    miss 'connected DRM display connector'
fi

if [ -b /dev/mmcblk0 ]; then
    printf 'OK   eMMC /dev/mmcblk0\n'
else
    miss 'eMMC /dev/mmcblk0'
fi

if [ -e /sys/class/rtc/rtc0 ]; then printf 'OK   RTC rtc0\n'; else miss 'RTC rtc0'; fi

if [ -r /sys/power/mem_sleep ]; then
    mem_sleep=$(cat /sys/power/mem_sleep 2>/dev/null || true)
    printf 'INFO suspend modes %s\n' "$mem_sleep"
    case "$mem_sleep" in
        *deep*) printf 'OK   deep suspend advertised\n' ;;
        *) optional 'deep suspend is not advertised; system currently relies on s2idle' ;;
    esac
fi

if [ -r /sys/kernel/debug/pmc_atom/sleep_state ]; then
    printf 'INFO Cherry Trail PMC residency:\n'
    sed 's/^/     /' /sys/kernel/debug/pmc_atom/sleep_state
else
    optional 'PMC S0ix residency unavailable to this audit (debugfs may require root)'
fi

if find /sys/class/thermal -maxdepth 1 -name 'thermal_zone*' -print -quit 2>/dev/null | grep -q .; then
    printf 'OK   thermal zones\n'
else
    miss 'thermal zones'
fi

for led in mipad2:rgb:indicator mipad2:white:touch-buttons-backlight; do
    if [ -e "/sys/class/leds/$led" ]; then
        printf 'OK   LED %s\n' "$led"
    else
        miss "LED $led"
    fi
done

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

ov5693_node=
for link in /sys/class/video4linux/v4l-subdev*; do
    [ -e "$link" ] || continue
    name=$(cat "$link/name" 2>/dev/null || true)
    case "$name" in
        *OV5693*|*ov5693*) ov5693_node=/dev/${link##*/}; break ;;
    esac
done
if [ -n "$ov5693_node" ]; then
    printf 'OK   OV5693 subdev %s\n' "$ov5693_node"
else
    miss 'OV5693 V4L2 subdev'
fi

battery_path=
for path in /sys/class/power_supply/*; do
    if [ -f "$path/type" ] && [ "$(cat "$path/type" 2>/dev/null)" = Battery ]; then
        battery_path=$path
        break
    fi
done
if [ -n "$battery_path" ]; then printf 'OK   %s\n' "$battery_path"; else miss '/sys/class/power_supply/BAT*'; fi

charger_path=
for path in /sys/class/power_supply/*; do
    [ -f "$path/type" ] || continue
    case "$(cat "$path/type" 2>/dev/null)" in
        USB|Mains)
            charger_path=$path
            break
            ;;
    esac
done
if [ -n "$charger_path" ]; then
    printf 'OK   charger %s\n' "$charger_path"
    charger_status=$(cat "$charger_path/status" 2>/dev/null || true)
    charger_online=$(cat "$charger_path/online" 2>/dev/null || true)
    charger_vreg=$(cat "$charger_path/constant_charge_voltage_max" 2>/dev/null || true)
    charger_iterm=$(cat "$charger_path/charge_term_current" 2>/dev/null || true)
    printf 'INFO BQ25890 status=%s online=%s VREG=%s uV ITERM=%s uA\n' \
        "${charger_status:-unknown}" "${charger_online:-unknown}" \
        "${charger_vreg:-unknown}" "${charger_iterm:-unknown}"
else
    miss 'BQ25890 charger'
    charger_status=
fi

if [ -n "$battery_path" ]; then
    battery_capacity=$(cat "$battery_path/capacity" 2>/dev/null || true)
    battery_status=$(cat "$battery_path/status" 2>/dev/null || true)
    battery_voltage=$(cat "$battery_path/voltage_now" 2>/dev/null || true)
    battery_current=$(cat "$battery_path/current_now" 2>/dev/null || true)
    printf 'INFO BQ27520 status=%s capacity=%s%% voltage=%s uV current=%s uA\n' \
        "${battery_status:-unknown}" "${battery_capacity:-unknown}" \
        "${battery_voltage:-unknown}" "${battery_current:-unknown}"
    if [ "$charger_status" = Full ] && [ -n "$battery_capacity" ] &&
       [ "$battery_capacity" -lt 95 ] 2>/dev/null; then
        optional "charger reports Full while fuel gauge reports ${battery_capacity}% (${battery_status:-unknown}); inspect BQ25890 termination and BQ27520 gauge calibration"
    fi
fi

for sensor in als accel_3d gyro_3d magn_3d incli_3d dev_rotation; do
    found=
    for name_file in /sys/bus/iio/devices/iio:device*/name; do
        [ -r "$name_file" ] || continue
        [ "$(cat "$name_file" 2>/dev/null)" = "$sensor" ] && found=$name_file && break
    done
    if [ -n "$found" ]; then
        printf 'OK   IIO %s\n' "$sensor"
    else
        miss "IIO $sensor"
    fi
done

udc_path=$(find /sys/class/udc -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null || true)
if [ -n "$udc_path" ]; then printf 'OK   %s\n' "$udc_path"; else miss 'an actual UDC under /sys/class/udc'; fi

xhci_bound=$(find /sys/bus/pci/drivers/xhci_hcd -maxdepth 1 -type l -print -quit 2>/dev/null || true)
if [ -n "$xhci_bound" ]; then printf 'OK   USB host xHCI\n'; else miss 'USB host xHCI binding'; fi

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

vcm_node=
for link in /sys/class/video4linux/v4l-subdev*; do
    [ -e "$link" ] || continue
    name=$(cat "$link/name" 2>/dev/null || true)
    case "$name" in
        *dw9761*|*dw9719*)
            vcm_node=/dev/${link##*/}
            break
            ;;
    esac
done
if [ -n "$vcm_node" ] && command -v v4l2-ctl >/dev/null 2>&1 &&
   v4l2-ctl -d "$vcm_node" --list-ctrls 2>/dev/null | grep -q focus_absolute; then
    printf 'OK   DW9761 focus control %s\n' "$vcm_node"
else
    miss 'DW9761 V4L2_CID_FOCUS_ABSOLUTE'
fi

if [ -n "$media_node" ] && command -v media-ctl >/dev/null 2>&1; then
    graph=$(media-ctl -d "$media_node" -p 2>/dev/null || true)
    if printf '%s\n' "$graph" | grep -qi 't4ka3'; then
        printf 'OK   media graph contains T4KA3\n'
    else
        miss 'T4KA3 in media graph'
    fi
fi

if [ -n "$t4ka3_node" ] && command -v v4l2-ctl >/dev/null 2>&1; then
    controls=$(v4l2-ctl -d "$t4ka3_node" --list-ctrls 2>/dev/null || true)
    if [ -n "$controls" ]; then
        printf 'OK   T4KA3 controls\n'
    else
        miss "T4KA3 controls on $t4ka3_node"
    fi
    if printf '%s\n' "$controls" | grep -q 'camera_sensor_rotation.*value=270'; then
        printf 'OK   T4KA3 rotation metadata 270 degrees\n'
    else
        miss 'T4KA3 rotation metadata'
    fi
fi

if [ "${MIPAD2_ACTIVE_CAMERA_TEST:-0}" = 1 ] && [ -n "$video_node" ] &&
   command -v v4l2-ctl >/dev/null 2>&1; then
    for input in 0 1; do
        output="/tmp/mipad2-camera-input-$input.raw"
        rm -f "$output"
        if v4l2-ctl -d "$video_node" --set-input="$input" >/dev/null 2>&1 &&
           timeout 20 v4l2-ctl -d "$video_node" --stream-mmap=4 \
               --stream-count=3 --stream-to="$output" >/dev/null 2>&1 &&
           [ -s "$output" ]; then
            printf 'OK   camera input %s streams without prior S_FMT\n' "$input"
        else
            miss "camera input $input stream"
        fi
        rm -f "$output"
    done
fi

if dmesg >/dev/null 2>&1; then
    bad_log=$(dmesg | grep -Ei \
        'Unknown symbol|disagrees about version of symbol|brcmf_fw_crashed|Firmware has halted or crashed|GPU HANG|GPU.*wedged|i2c_hid.*probe.*failed|FTSC1000.*failed' \
        | tail -n 20 || true)
    if [ -n "$bad_log" ]; then
        miss 'fatal driver errors in dmesg'
        printf '%s\n' "$bad_log"
    else
        printf 'OK   no known fatal driver errors in dmesg\n'
    fi
else
    optional 'dmesg unavailable (run this audit as root)'
fi

exit "$fail"
