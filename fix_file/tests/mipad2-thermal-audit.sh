#!/bin/sh
# Read-only thermal/DPTF diagnostics for Mi Pad 2. Missing ACPI objects are
# reported as INFO: the Windows INF contains generic model IDs, not a runtime
# ACPI inventory. MIPAD2_SYSFS_ROOT is for isolated test fixtures.
set -u

sysfs_root=${MIPAD2_SYSFS_ROOT:-/sys}
thermal_root=$sysfs_root/class/thermal
acpi_root=$sysfs_root/bus/acpi/devices
zone_count=0
cooler_count=0
dptf_count=0

for zone in "$thermal_root"/thermal_zone*; do
    [ -d "$zone" ] || continue
    [ -r "$zone/type" ] && [ -r "$zone/temp" ] || continue
    name=$(cat "$zone/type" 2>/dev/null || true)
    temp=$(cat "$zone/temp" 2>/dev/null || true)
    digits=$temp
    case "$digits" in -*) digits=${digits#-} ;; esac
    case "$digits" in ''|*[!0-9]*)
        printf 'WARN thermal_zone=%s invalid_temp=%s\n' "${zone##*/}" "$temp"
        continue
        ;;
    esac
    zone_count=$((zone_count + 1))
    printf 'THERMAL zone=%s type=%s temp_mC=%s\n' "${zone##*/}" "$name" "$temp"
    for trip in "$zone"/trip_point_*_temp; do
        [ -r "$trip" ] || continue
        trip_name=${trip##*/trip_point_}
        trip_name=${trip_name%_temp}
        printf 'TRIP zone=%s trip=%s temp_mC=%s\n' "${zone##*/}" "$trip_name" "$(cat "$trip" 2>/dev/null || echo unknown)"
    done
done

for cooler in "$thermal_root"/cooling_device*; do
    [ -d "$cooler" ] || continue
    [ -r "$cooler/type" ] || continue
    cooler_count=$((cooler_count + 1))
    printf 'COOLING device=%s type=%s current=%s max=%s\n' \
        "${cooler##*/}" "$(cat "$cooler/type" 2>/dev/null || echo unknown)" \
        "$(cat "$cooler/cur_state" 2>/dev/null || echo unknown)" \
        "$(cat "$cooler/max_state" 2>/dev/null || echo unknown)"
done

for device in "$acpi_root"/INT340[0-9]*; do
    [ -d "$device" ] || continue
    dptf_count=$((dptf_count + 1))
    printf 'DPTF acpi=%s status=%s\n' "${device##*/}" \
        "$(cat "$device/status" 2>/dev/null || echo unknown)"
done

[ "$zone_count" -gt 0 ] || printf 'INFO no readable thermal zones under %s\n' "$thermal_root"
[ "$cooler_count" -gt 0 ] || printf 'INFO no cooling devices under %s\n' "$thermal_root"
[ "$dptf_count" -gt 0 ] || printf 'INFO no INT340x ACPI devices under %s\n' "$acpi_root"
exit 0
