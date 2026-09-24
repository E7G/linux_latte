#!/bin/sh
# Source-level regression checks for Mi Pad 2 HID-sensor axis orientation.
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
hub="$repo/drivers/hid/hid-sensor-hub.c"
accel="$repo/drivers/iio/accel/hid-sensor-accel-3d.c"
gyro="$repo/drivers/iio/gyro/hid-sensor-gyro-3d.c"
magn="$repo/drivers/iio/magnetometer/hid-sensor-magn-3d.c"
need() {
  grep -Fq -- "$2" "$1" || {
    echo "MISS: $2 in $1" >&2
    exit 1
  }
}
need "$hub" 'hdev->vendor == 0x8086 && hdev->product == 0x0002'
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
echo "PASS: Android Mi Pad 2 sensor axis corrections exported as HID-IIO mount matrices."
