#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT HUP INT TERM
mock="$tmp/mock"
mkdir -p "$mock"
archive="$tmp/boot-known-good.tar.zst"
script="$tmp/mp2-recover"
log="$tmp/calls.log"

# Use a temporary copy so the test never writes under /var/lib.
sed "s|boot=/var/lib/mipad2-recovery/boot-known-good.tar.zst|boot=$archive|" \
  "$root/fix_file/packages/mipad2-recovery/src/mp2-recover" > "$script"
chmod +x "$script"
printf 'fixture archive bytes
' > "$archive"
sha256sum "$archive" > "$archive.sha256"

cat > "$mock/id" <<'EOF'
#!/bin/sh
echo 0
EOF
cat > "$mock/findmnt" <<'EOF'
#!/bin/sh
case "$*" in
  *"-o SOURCE"*) echo "${MOCK_ROOT_SOURCE:-/dev/mmcblk0p3[/@]}" ;;
  *"-o TARGET"*)
    case "$*" in *"/boot"*) echo "${MOCK_BOOT_TARGET:-/boot}" ;; *) echo / ;; esac ;;
  *"-o FSTYPE"*)
    case "$*" in *"/boot"*) echo "${MOCK_BOOT_FSTYPE:-vfat}" ;; *) echo "${MOCK_ROOT_FSTYPE:-btrfs}" ;; esac ;;
  *) exit 2 ;;
esac
EOF
cat > "$mock/timeshift" <<'EOF'
#!/bin/sh
printf 'timeshift %s\n' "$*" >> "$MP2_TEST_LOG"
if [ "${1:-}" = --list ]; then
  echo "0 2026-09-25_00-10-10 BTRFS"
fi
EOF
cat > "$mock/cp" <<'EOF'
#!/bin/sh
printf 'cp %s\n' "$*" >> "$MP2_TEST_LOG"
EOF
cat > "$mock/tar" <<'EOF'
#!/bin/sh
printf 'tar %s\n' "$*" >> "$MP2_TEST_LOG"
EOF
cat > "$mock/rm" <<'EOF'
#!/bin/sh
printf 'rm %s\n' "$*" >> "$MP2_TEST_LOG"
EOF
cat > "$mock/sync" <<'EOF'
#!/bin/sh
:
EOF
chmod +x "$mock"/*

PATH="$mock:$PATH" MP2_TEST_LOG="$log" "$script" --status > "$tmp/status"
grep -Fq -- 'timeshift --list --btrfs --scripted' "$log"

: > "$log"
if PATH="$mock:$PATH" MP2_TEST_LOG="$log" MOCK_BOOT_TARGET=/ "$script" --yes   > "$tmp/unmounted.out" 2>&1; then
  echo "FAIL: recovery accepted an unmounted /boot" >&2
  exit 1
fi
! grep -Fq -- '--restore ' "$log"

printf 'corruption\n' >> "$archive"
: > "$log"
if PATH="$mock:$PATH" MP2_TEST_LOG="$log" "$script" --yes > "$tmp/corrupt.out" 2>&1; then
  echo "FAIL: recovery accepted a checksum-mismatched boot archive" >&2
  exit 1
fi
! grep -Fq -- '--restore ' "$log"
printf 'fixture archive bytes\n' > "$archive"
sha256sum "$archive" > "$archive.sha256"

: > "$log"
if PATH="$mock:$PATH" MP2_TEST_LOG="$log" MOCK_ROOT_FSTYPE=ext4 "$script" --yes \
  > "$tmp/non-btrfs.out" 2>&1; then
  echo "FAIL: recovery accepted a non-Btrfs root" >&2
  exit 1
fi
! grep -Fq -- '--restore ' "$log"

: > "$log"
PATH="$mock:$PATH" MP2_TEST_LOG="$log" "$script" --yes > "$tmp/restore.out"
grep -Fq -- '--target /dev/mmcblk0p3' "$log"
grep -Fq -- '--restore --snapshot 2026-09-25_00-10-10' "$log"
grep -Fq -- '--snapshot-device' "$log" && {
  echo "FAIL: helper overrode Timeshift's configured snapshot device" >&2
  exit 1
} || :
grep -Fq 'cp ' "$log"
grep -Fq 'tar --zstd -xpf /boot/.mp2-recovery-boot-2026-09-25_00-10-10.tar.zst -C /boot' "$log"

echo "PASS: recovery uses the configured Timeshift location, targets the discovered root, and fails closed for an unmounted /boot."
