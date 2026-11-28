#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
set -euo pipefail

kernel=$(realpath -e -- "$1")
release=$2
evidence=$(realpath -e -- "$3")
ovmf_dir=${OVMF_DIR:-/usr/share/OVMF}
[[ "$release" =~ ^7\.2\.[0-9]+-mipad2-integrated-preavx-ci$ ]]
tmp=$(mktemp -d -t mipad2-72-preavx.XXXXXXXX)
trap 'rm -rf -- "$tmp"' EXIT

mkdir -p "$tmp/initrd"/{bin,dev,proc,sys,mnt} "$tmp/filesystem"
install -m 0755 "$(command -v busybox)" "$tmp/initrd/bin/busybox"
printf '%s\n' mipad2-preavx-btrfs > "$tmp/filesystem/marker"
truncate -s 128M "$tmp/initrd/root.btrfs"
mkfs.btrfs -q -f -r "$tmp/filesystem" "$tmp/initrd/root.btrfs"
cat > "$tmp/initrd/init" <<'GUEST'
#!/bin/busybox sh
set -eu
bb=/bin/busybox
trap 'rc=$?; echo "MIPAD2_PREAVX_FAILURE=$rc"; "$bb" poweroff -f' EXIT
"$bb" mount -t proc proc /proc
"$bb" mount -t sysfs sysfs /sys
test -d /sys/firmware/efi
"$bb" grep -Eq '^flags[[:space:]]*:' /proc/cpuinfo
if "$bb" grep -Eq '(^|[[:space:]])(avx|avx2|bmi1|bmi2)([[:space:]]|$)' /proc/cpuinfo; then
    echo "Guest unexpectedly exposes an AVX or BMI CPU feature"
    exit 1
fi
"$bb" mount -t devtmpfs devtmpfs /dev
"$bb" losetup /dev/loop0 /root.btrfs
"$bb" mount -t btrfs -o ro,nologreplay /dev/loop0 /mnt
read -r marker < /mnt/marker
test "$marker" = mipad2-preavx-btrfs
printf 'MIPAD2_PREAVX_EFI_BTRFS_OK %s\n' "$("$bb" uname -r)"
trap - EXIT
"$bb" poweroff -f
GUEST
chmod 0755 "$tmp/initrd/init"
(
    cd "$tmp/initrd"
    find . -print0 | cpio --quiet -0 -o -H newc | gzip -1
) > "$tmp/initrd.cpio.gz"
cp "$ovmf_dir/OVMF_VARS_4M.fd" "$tmp/vars.fd"

sha256sum "$kernel" > "$evidence/kernel.sha256"
printf '%s\n' "$release" > "$evidence/kernelrelease.txt"
ret=0
timeout 180 qemu-system-x86_64 \
    -machine q35,accel=tcg \
    -cpu Westmere,family=6,model=76,stepping=3,movbe=on,rdrand=on,avx=off,avx2=off,bmi1=off,bmi2=off \
    -smp 2 -m 2048 -nodefaults -display none -serial stdio -monitor none \
    -nic none -no-reboot \
    -drive if=pflash,format=raw,readonly=on,file="$ovmf_dir/OVMF_CODE_4M.fd" \
    -drive if=pflash,format=raw,file="$tmp/vars.fd" \
    -kernel "$kernel" -initrd "$tmp/initrd.cpio.gz" \
    -append 'console=ttyS0,115200 panic=1 loglevel=6' > "$evidence/qemu.log" 2>&1 || ret=$?
printf '%s\n' "$ret" > "$evidence/qemu-exit-status.txt"
tr -d '\r' < "$evidence/qemu.log" > "$evidence/guest.txt"
if [ "$ret" -ne 0 ] || ! grep -Fx "MIPAD2_PREAVX_EFI_BTRFS_OK $release" "$evidence/guest.txt"; then
    tail -n 100 "$evidence/guest.txt" >&2
    exit 1
fi
