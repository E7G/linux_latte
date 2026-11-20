#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
set -euo pipefail

kernel=$(realpath -e -- "${1:?bzImage required}")
release=${2:?expected kernel release required}
ovmf_dir=${3:-/usr/share/OVMF}
tmp=$(mktemp -d -t mipad2-early-boot.XXXXXXXX)
trap 'rm -rf -- "$tmp"' EXIT

mkdir -p "$tmp/initrd"/{bin,dev,sys,mnt} "$tmp/filesystem"
install -m 0755 "$(command -v busybox)" "$tmp/initrd/bin/busybox"
printf 'mipad2\n' > "$tmp/filesystem/marker"
truncate -s 128M "$tmp/initrd/root.btrfs"
mkfs.btrfs -q -f -r "$tmp/filesystem" "$tmp/initrd/root.btrfs"
cat > "$tmp/initrd/init" <<'EOF'
#!/bin/busybox sh
set -eu
bb=/bin/busybox
$bb mount -t sysfs sysfs /sys
test -d /sys/firmware/efi
$bb mount -t devtmpfs devtmpfs /dev
$bb losetup /dev/loop0 /root.btrfs
$bb mount -t btrfs -o ro /dev/loop0 /mnt
read -r marker < /mnt/marker
test "$marker" = mipad2
printf 'MIPAD2_EFI_BTRFS_OK %s\n' "$($bb uname -r)"
$bb poweroff -f
EOF
chmod 0755 "$tmp/initrd/init"
(
    cd "$tmp/initrd"
    find . -print0 | cpio --quiet -0 -o -H newc | gzip -1
) > "$tmp/initrd.cpio.gz"
cp "$ovmf_dir/OVMF_VARS_4M.fd" "$tmp/vars.fd"

if ! timeout 120 qemu-system-x86_64 \
    -machine q35,accel=tcg -cpu Westmere,model=76,stepping=3,movbe=on,rdrand=on,bmi2=off \
    -smp 2 -m 2048 -nodefaults -display none -vga none -serial stdio -monitor none \
    -nic none -no-reboot \
    -drive if=pflash,format=raw,readonly=on,file="$ovmf_dir/OVMF_CODE_4M.fd" \
    -drive if=pflash,format=raw,file="$tmp/vars.fd" \
    -kernel "$kernel" -initrd "$tmp/initrd.cpio.gz" \
    -append 'console=ttyS0,115200 panic=1 loglevel=6' > "$tmp/serial.log" 2>&1 ||
   ! tr -d '\r' < "$tmp/serial.log" | grep -Fx "MIPAD2_EFI_BTRFS_OK $release"; then
    tail -80 "$tmp/serial.log" >&2
    exit 1
fi
