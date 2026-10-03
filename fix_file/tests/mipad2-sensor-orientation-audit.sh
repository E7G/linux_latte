#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
# Source-level regression checks for Mi Pad 2 HID-sensor axis orientation.
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
hub="$repo/drivers/hid/hid-sensor-hub.c"
accel="$repo/drivers/iio/accel/hid-sensor-accel-3d.c"
gyro="$repo/drivers/iio/gyro/hid-sensor-gyro-3d.c"
magn="$repo/drivers/iio/magnetometer/hid-sensor-magn-3d.c"
attributes="$repo/drivers/iio/common/hid-sensors/hid-sensor-attributes.c"
need() {
  grep -Fq -- "$2" "$1" || {
    echo "MISS: $2 in $1" >&2
    exit 1
  }
}
need "$hub" '(hdev->product == 0x0001 || hdev->product == 0x0002)'
need "$hub" 'dmi_match(DMI_SYS_VENDOR, "Xiaomi Inc")'
need "$hub" 'dmi_match(DMI_PRODUCT_NAME, "Mipad2")'
need "$hub" 'PROPERTY_ENTRY_STRING_ARRAY("mount-matrix"'
need "$hub" '"-1", "0", "0"'
need "$hub" '"0", "1", "0"'
need "$hub" '"0", "0", "-1"'
need "$hub" 'HID_USAGE_SENSOR_ACCEL_3D'
need "$hub" 'HID_USAGE_SENSOR_GRAVITY_VECTOR'
need "$hub" 'HID_USAGE_SENSOR_GYRO_3D'
need "$hub" 'HID_USAGE_SENSOR_COMPASS_3D'
for driver in "$accel" "$gyro" "$magn"; do
  need "$driver" 'iio_read_mount_matrix(&pdev->dev'
  need "$driver" 'IIO_MOUNT_MATRIX('
done
need "$magn" 'channels[i].ext_info = magn_3d_ext_info'
for usage in \
  HID_USAGE_SENSOR_ORIENT_COMP_MAGN_NORTH \
  HID_USAGE_SENSOR_ORIENT_COMP_TRUE_NORTH \
  HID_USAGE_SENSOR_ORIENT_MAGN_NORTH \
  HID_USAGE_SENSOR_ORIENT_TRUE_NORTH; do
  need "$attributes" "${usage}, 0, 1, 0"
  grep -A1 -F "{${usage}," "$attributes" | grep -Fq 'HID_USAGE_SENSOR_UNITS_DEGREES, 1, 0}' || {
    echo "MISS: degree scale mapping for ${usage}" >&2
    exit 1
  }
done
echo "PASS: Mi Pad 2 HID-sensor mount matrices and compass angle scales."
