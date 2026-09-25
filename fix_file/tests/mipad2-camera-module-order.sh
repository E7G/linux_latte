#!/bin/sh
# Keep Mi Pad 2 AtomISP module initialization behind its sensor graph.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
package="$root/fix_file/packages/mipad2-camera-support"
load_conf="$package/src/mipad2-camera.conf"
modprobe_conf="$package/src/mipad2-atomisp.conf"
pkgbuild="$package/PKGBUILD"

grep -qx 'atomisp_gmin_platform' "$load_conf"
grep -qx 'softdep atomisp pre: atomisp_gmin_platform ov5693 t4ka3 dw9719' "$modprobe_conf"
grep -q 'mipad2-atomisp.conf' "$pkgbuild"
grep -q '/etc/modprobe.d/mipad2-atomisp.conf' "$pkgbuild"
grep -q 'mipad2-camera.conf' "$pkgbuild"
grep -q '/etc/modules-load.d/mipad2-camera.conf' "$pkgbuild"
need_config() {
	tr -d '\r' < "$root/arch/x86/configs/xiaomipad2_defconfig" | grep -qx "$1"
}
need_config 'CONFIG_VIDEO_ATOMISP=m'
need_config 'CONFIG_VIDEO_OV5693=m'
need_config 'CONFIG_VIDEO_T4KA3=m'
need_config 'CONFIG_VIDEO_DW9719=m'

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
bash -c 'srcdir="$1"; pkgdir="$2"; source "$3"; package' _ "$package/src" "$tmp" "$pkgbuild"
cmp "$modprobe_conf" "$tmp/etc/modprobe.d/mipad2-atomisp.conf"
cmp "$load_conf" "$tmp/etc/modules-load.d/mipad2-camera.conf"

echo "PASS: platform helper loads early; sensor/VCM softdeps precede AtomISP."
