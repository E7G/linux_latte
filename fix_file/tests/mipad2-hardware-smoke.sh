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

# BEGIN MIPAD2_WIRELESS_CHECKS
mipad2_wifi_pci_check() {
    mp2_pci=
    mp2_matches=0
    for mp2_path in "$1"/bus/pci/devices/*; do
        [ -r "$mp2_path/vendor" ] && [ -r "$mp2_path/device" ] || continue
        [ "$(cat "$mp2_path/vendor")" = 0x14e4 ] || continue
        [ "$(cat "$mp2_path/device")" = 0x43ec ] || continue
        mp2_pci=$mp2_path
        mp2_matches=$((mp2_matches + 1))
    done
    if [ "$mp2_matches" -ne 1 ]; then
        miss "expected one onboard BCM4356 PCI device (14e4:43ec; found $mp2_matches)"
        return
    fi

    mp2_driver=$(readlink "$mp2_pci/driver" 2>/dev/null || true)
    if [ "${mp2_driver##*/}" != brcmfmac ]; then
        miss "onboard BCM4356 bound to brcmfmac"
        return
    fi
    printf 'OK   onboard BCM4356 driver brcmfmac\n'

    mp2_wlan=
    for mp2_net in "$mp2_pci"/net/*; do
        [ -d "$mp2_net/wireless" ] || [ -e "$mp2_net/phy80211" ] || continue
        mp2_wlan=$mp2_net
        printf 'OK   onboard Wi-Fi interface %s (%s)\n' "${mp2_net##*/}" \
            "$(cat "$mp2_net/operstate" 2>/dev/null || echo unknown)"
    done
    [ -n "$mp2_wlan" ] || miss 'onboard BCM4356 Wi-Fi interface'
}

mipad2_fw_file_present() (
    mp2_lib=$1
    mp2_release=$2
    mp2_override=$3
    mp2_name=$4
    shift 4
    for mp2_suffix in "" "$@"; do
        for mp2_directory in "$mp2_override" "$mp2_lib/updates/$mp2_release" \
            "$mp2_lib/updates" "$mp2_lib/$mp2_release" "$mp2_lib"; do
            [ -n "$mp2_directory" ] || continue
            mp2_file=$mp2_directory/brcm/$mp2_name$mp2_suffix
            [ -f "$mp2_file" ] && [ -s "$mp2_file" ] && [ -r "$mp2_file" ] && exit 0
        done
    done
    exit 1
)

mipad2_fw_file_check() {
    mp2_fw_base=$1
    mp2_fw_release=$2
    mp2_fw_override=$3
    shift 3
    if mipad2_fw_file_present "$mp2_fw_base" "$mp2_fw_release" "$mp2_fw_override" \
        brcmfmac4356-pcie.bin "$@"; then
        printf 'OK   local BCM4356 Wi-Fi firmware file present\n'
    else
        miss 'local BCM4356 Wi-Fi firmware file (brcmfmac4356-pcie.bin)'
    fi
    if mipad2_fw_file_present "$mp2_fw_base" "$mp2_fw_release" "$mp2_fw_override" \
        'brcmfmac4356-pcie.Xiaomi Inc-Mipad2.txt' "$@"; then
        printf 'OK   local Mi Pad 2 board NVRAM file present\n'
    else
        miss 'local Mi Pad 2 board NVRAM file (brcmfmac4356-pcie.Xiaomi Inc-Mipad2.txt)'
    fi
    if mipad2_fw_file_present "$mp2_fw_base" "$mp2_fw_release" "$mp2_fw_override" \
        BCM4356A2.hcd "$@"; then
        printf 'OK   local BCM4356A2 Bluetooth firmware file present\n'
    else
        miss 'local BCM4356A2 Bluetooth firmware file (BCM4356A2.hcd)'
    fi
}
mipad2_bt_uart_check() {
    mp2_bt_matches=0
    mp2_bt_node=
    for mp2_bt_path in "$1"/class/bluetooth/hci*; do
        [ -d "$mp2_bt_path" ] || continue
        mp2_bt_name=${mp2_bt_path##*/}
        case "${mp2_bt_name#hci}" in
            ''|*[!0-9]*) continue ;;
        esac
        [ -r "$mp2_bt_path/device/uevent" ] || continue
        grep -q '^MODALIAS=acpi:BCM2E9C:' "$mp2_bt_path/device/uevent" || continue
        mp2_bt_node=$mp2_bt_path
        mp2_bt_matches=$((mp2_bt_matches + 1))
    done
    if [ "$mp2_bt_matches" -ne 1 ]; then
        miss "expected one onboard BCM4356A2 HCI device (ACPI BCM2E9C; found $mp2_bt_matches)"
        return
    fi

    mp2_bt_driver=$(readlink "$mp2_bt_node/device/driver" 2>/dev/null || true)
    if [ "${mp2_bt_driver##*/}" != hci_uart_bcm ]; then
        miss 'onboard BCM4356A2 bound to hci_uart_bcm'
        return
    fi
    printf 'OK   onboard BCM4356A2 Bluetooth %s (hci_uart_bcm)\n' "${mp2_bt_node##*/}"
}
# END MIPAD2_WIRELESS_CHECKS

mipad2_wifi_pci_check /sys
firmware_override=$(cat /sys/module/firmware_class/parameters/path 2>/dev/null || true)
case "$firmware_override" in
    /*) ;;
    *) firmware_override= ;;
esac
# The running kernel determines which compressed file names are usable.
# These are availability checks, not proof of what was loaded at boot.
fw_config=$(zcat /proc/config.gz 2>/dev/null || true)
fw_zstd=
fw_xz=
printf '%s\n' "$fw_config" | grep -qx 'CONFIG_FW_LOADER_COMPRESS_ZSTD=y' && fw_zstd=.zst
printf '%s\n' "$fw_config" | grep -qx 'CONFIG_FW_LOADER_COMPRESS_XZ=y' && fw_xz=.xz
mipad2_fw_file_check /lib/firmware "$release" "$firmware_override" "$fw_zstd" "$fw_xz"

mipad2_bt_uart_check /sys

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

if modinfo -k "$release" intel_pmic_chtwc_thermal >/dev/null 2>&1; then
    if [ ! -L /sys/bus/platform/devices/cht_wcove_adc/driver ]; then
        miss 'Whiskey Cove ADC driver binding'
    fi
    for thermistor in chtwc-sys0 chtwc-sys1 chtwc-sys2; do
        zone_path=
        for type_file in /sys/class/thermal/thermal_zone*/type; do
            if [ -r "$type_file" ] && [ "$(cat "$type_file")" = "$thermistor" ]; then
                zone_path=${type_file%/type}
                break
            fi
        done
        if [ -z "$zone_path" ]; then
            miss "Whiskey Cove board thermal zone $thermistor"
            continue
        fi
        board_temp=$(cat "$zone_path/temp" 2>/dev/null || true)
        if [ "$board_temp" -ge -40000 ] 2>/dev/null && [ "$board_temp" -le 125000 ]; then
            printf 'OK   board thermal %s %s mC\n' "$thermistor" "$board_temp"
        else
            miss "Whiskey Cove board thermal reading $thermistor"
        fi
    done
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
    if [ "$charger_vreg" = 4400000 ]; then
        printf 'OK   BQ25890 Mi Pad 2 VREG 4.400 V\n'
    else
        miss "BQ25890 VREG 4.400 V (got ${charger_vreg:-unknown})"
    fi
    if [ "$charger_iterm" = 256000 ]; then
        printf 'OK   BQ25890 termination current 256 mA\n'
    else
        miss "BQ25890 termination current 256 mA (got ${charger_iterm:-unknown})"
    fi
else
    miss 'BQ25890 charger'
    charger_status=
fi

if [ -n "$battery_path" ]; then
    battery_capacity=$(cat "$battery_path/capacity" 2>/dev/null || true)
    battery_status=$(cat "$battery_path/status" 2>/dev/null || true)
    battery_voltage=$(cat "$battery_path/voltage_now" 2>/dev/null || true)
    battery_current=$(cat "$battery_path/current_now" 2>/dev/null || true)
    design_full=$(cat "$battery_path/charge_full_design" 2>/dev/null || true)
    printf 'INFO BQ27520 status=%s capacity=%s%% voltage=%s uV current=%s uA design=%s uAh\n' \
        "${battery_status:-unknown}" "${battery_capacity:-unknown}" \
        "${battery_voltage:-unknown}" "${battery_current:-unknown}" "${design_full:-unknown}"
    if [ "$design_full" = 6190000 ]; then
        printf 'OK   BQ27520 design capacity 6190 mAh\n'
    else
        optional "BQ27520 design capacity is ${design_full:-unknown}; expected Xiaomi profile 6190000 uAh"
    fi
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

for sensor in accel_3d gravity gyro_3d magn_3d; do
    case "$sensor" in
        accel_3d|gravity) expected_matrix='1,0,0;0,1,0;0,0,-1' ;;
        *) expected_matrix='-1,0,0;0,1,0;0,0,-1' ;;
    esac
    name_file=
    for path in /sys/bus/iio/devices/iio:device*/name; do
        [ -r "$path" ] || continue
        [ "$(cat "$path" 2>/dev/null)" = "$sensor" ] && name_file=$path && break
    done
    if [ -z "$name_file" ]; then
        # The enumeration loop above reports missing primary sensor devices.
        continue
    fi

    device_path=${name_file%/name}
    matrix_file=
    for path in "$device_path"/mount_matrix "$device_path"/*_mount_matrix; do
        [ -r "$path" ] || continue
        matrix_file=$path
        break
    done
    if [ -z "$matrix_file" ]; then
        miss "IIO $sensor mount matrix"
        continue
    fi

    actual_matrix=$(tr -d '[:space:]' < "$matrix_file" 2>/dev/null || true)
    if [ "$actual_matrix" = "$expected_matrix" ]; then
        printf 'OK   IIO %s mount matrix %s\n' "$sensor" "$actual_matrix"
    else
        miss "IIO $sensor mount matrix expected $expected_matrix, got ${actual_matrix:-unreadable}"
    fi
done

magn_name_file=
for path in /sys/bus/iio/devices/iio:device*/name; do
    [ -r "$path" ] || continue
    [ "$(cat "$path" 2>/dev/null)" = magn_3d ] && magn_name_file=$path && break
done
if [ -n "$magn_name_file" ]; then
    scale_file=${magn_name_file%/name}/in_rot_scale
    rotation_scale=$(cat "$scale_file" 2>/dev/null || true)
    if [ -n "$rotation_scale" ] &&
       awk -v value="$rotation_scale" 'BEGIN { exit !(value > 0 && value < 1) }'; then
        printf 'OK   compass rotation scale %s\n' "$rotation_scale"
    else
        miss "compass rotation unit scale (${rotation_scale:-unreadable})"
    fi
fi

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
