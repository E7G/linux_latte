#!/bin/sh
set -eu

test_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
audit=$test_dir/mipad2-thermal-audit.sh
root=$(mktemp -d)
trap 'rm -rf "$root"' EXIT HUP INT TERM

mkdir -p "$root/class/thermal/thermal_zone0" \
    "$root/class/thermal/thermal_zone1" \
    "$root/class/thermal/thermal_zone2" \
    "$root/class/thermal/cooling_device0" \
    "$root/bus/acpi/devices/INT3400:00"
printf 'Package\n' > "$root/class/thermal/thermal_zone0/type"
printf '42000\n' > "$root/class/thermal/thermal_zone0/temp"
printf '95000\n' > "$root/class/thermal/thermal_zone0/trip_point_0_temp"
printf 'x86_pkg_temp\n' > "$root/class/thermal/thermal_zone1/type"
printf '%s\n' '-5000' > "$root/class/thermal/thermal_zone1/temp"
printf 'STR0\n' > "$root/class/thermal/thermal_zone2/type"
printf '%s\n' '-273150' > "$root/class/thermal/thermal_zone2/temp"
printf 'Processor\n' > "$root/class/thermal/cooling_device0/type"
printf '2\n' > "$root/class/thermal/cooling_device0/cur_state"
printf '8\n' > "$root/class/thermal/cooling_device0/max_state"
printf 'enabled\n' > "$root/bus/acpi/devices/INT3400:00/status"

output=$(MIPAD2_SYSFS_ROOT="$root" sh "$audit")
printf '%s\n' "$output" | grep -Fq 'THERMAL zone=thermal_zone0 type=Package temp_mC=42000'
printf '%s\n' "$output" | grep -Fq 'THERMAL zone=thermal_zone1 type=x86_pkg_temp temp_mC=-5000'
printf '%s\n' "$output" | grep -Fq 'WARN thermal_zone=thermal_zone2 type=STR0 temp_mC=-273150 likely_unavailable_sentinel=true'
printf '%s\n' "$output" | grep -Fq 'TRIP zone=thermal_zone0 trip=0 temp_mC=95000'
printf '%s\n' "$output" | grep -Fq 'COOLING device=cooling_device0 type=Processor current=2 max=8'
printf '%s\n' "$output" | grep -Fq 'DPTF acpi=INT3400:00 status=enabled'

mkdir -p "$root/empty"
output=$(MIPAD2_SYSFS_ROOT="$root/empty" sh "$audit")
printf '%s\n' "$output" | grep -Fq 'INFO no readable thermal zones'
printf '%s\n' "$output" | grep -Fq 'INFO no INT340x ACPI devices'

echo 'PASS: thermal zones, trips, cooling devices and INT340x diagnostics.'
