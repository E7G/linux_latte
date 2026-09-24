#!/bin/sh
set -eu
repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
backup="$repo_root/packages/mipad2-recovery/src/mp2-backup"
recover="$repo_root/packages/mipad2-recovery/src/mp2-recover"
[ "$(id -u)" -eq 0 ] || { echo "Run tests as root (or with sudo)." >&2; exit 77; }
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
mkdir -p "$tmp/bin" "$tmp/recovery"
count="$tmp/list-count"
log="$tmp/timeshift.log"
tar_log="$tmp/tar.log"
export MIPAD2_RECOVERY_DIR="$tmp/recovery"
export MOCK_COUNT="$count" MOCK_LOG="$log" MOCK_TAR_LOG="$tar_log"
MOCK_ROOT_DEV=$(find /dev -type b -print -quit)
[ -n "$MOCK_ROOT_DEV" ] || { echo "No block device node available for mocked test." >&2; exit 77; }
export MOCK_ROOT_DEV

cat > "$tmp/bin/findmnt" <<'MOCK'
#!/bin/sh
case "$*" in
  "-n -o SOURCE /") echo "$MOCK_ROOT_DEV[/@]" ;;
  "-n -o FSTYPE /") echo "${MOCK_ROOT_FSTYPE:-btrfs}" ;;
  "-n -o FSTYPE /boot") echo "${MOCK_BOOT_FSTYPE:-vfat}" ;;
  "-n -o SOURCE /boot") echo "/dev/loop1" ;;
  *) echo "unexpected findmnt args: $*" >&2; exit 2 ;;
esac
MOCK
cat > "$tmp/bin/mountpoint" <<'MOCK'
#!/bin/sh
[ "${BOOT_MOUNTED:-1}" = 1 ]
MOCK
cat > "$tmp/bin/timeshift" <<'MOCK'
#!/bin/sh
printf '%s\n' "$*" >> "$MOCK_LOG"
case "$1" in
  --list)
    n=0
    [ ! -f "$MOCK_COUNT" ] || n=$(cat "$MOCK_COUNT")
    n=$((n + 1))
    printf '%s\n' "$n" > "$MOCK_COUNT"
    echo "Device: $MOCK_ROOT_DEV"
    echo "Num  Name                 Tags  Description"
    echo "0    > 2026-09-24_20-00-00 D     mipad2-manual-backup"
    if [ "$n" -ge 2 ]; then
      echo "1    > 2026-09-25_01-10-00 D     mipad2-manual-backup"
      # An unrelated automatic snapshot arrives after the manual one.
      echo "2    > 2026-09-25_01-11-00 H     hourly"
    fi
    ;;
  --create) exit 0 ;;
  --restore) exit 0 ;;
  *) echo "unexpected timeshift args: $*" >&2; exit 2 ;;
esac
MOCK
cat > "$tmp/bin/tar" <<'MOCK'
#!/bin/sh
printf '%s\n' "$*" >> "$MOCK_TAR_LOG"
[ "$1" = --zstd ] || exit 2
if [ "$2" = -cpf ]; then echo testdata > "$3"; fi
exit 0
MOCK
cat > "$tmp/bin/sync" <<'MOCK'
#!/bin/sh
exit 0
MOCK
cat > "$tmp/bin/flock" <<'MOCK'
#!/bin/sh
[ "${MOCK_FLOCK_FAIL:-0}" = 0 ]
MOCK
chmod +x "$tmp/bin/"*
export PATH="$tmp/bin:$PATH"

sh -n "$backup"
sh -n "$recover"
"$backup" >/dev/null
archive="$MIPAD2_RECOVERY_DIR/boot-2026-09-25_01-10-00.tar.zst"
[ -s "$archive" ] && [ -s "$archive.sha256" ]
grep -Fq -- "--snapshot-device $MOCK_ROOT_DEV" "$MOCK_LOG"
grep -Fq -- "--create --snapshot-device $MOCK_ROOT_DEV" "$MOCK_LOG"

# Valid restore must target the detected root device and extract the matching archive.
"$recover" --yes >/dev/null
grep -Fq -- "--restore --snapshot 2026-09-25_01-10-00 --snapshot-device $MOCK_ROOT_DEV --target $MOCK_ROOT_DEV" "$MOCK_LOG"
grep -q -- '--zstd -xpf .*boot-2026-09-25_01-10-00.tar.zst -C /boot' "$MOCK_TAR_LOG"

# Missing archive, bad checksum, and an unmounted /boot must fail before restore.
: > "$MOCK_LOG"
rm -f "$MOCK_TAR_LOG"
mv "$archive" "$archive.tmp"
if "$recover" --yes >/dev/null 2>&1; then echo "missing archive was accepted" >&2; exit 1; fi
if grep -q -- '--restore' "$MOCK_LOG"; then echo "restore ran despite a rejected precondition" >&2; exit 1; fi
: > "$MOCK_LOG"
mv "$archive.tmp" "$archive"
printf 'invalid  %s\n' "$archive" > "$archive.sha256"
if "$recover" --yes >/dev/null 2>&1; then echo "bad checksum was accepted" >&2; exit 1; fi
if grep -q -- '--restore' "$MOCK_LOG"; then echo "restore ran despite a rejected precondition" >&2; exit 1; fi
: > "$MOCK_LOG"
(cd "$MIPAD2_RECOVERY_DIR" && sha256sum "$(basename "$archive")" > "$(basename "$archive").sha256")
: > "$MOCK_LOG"
BOOT_MOUNTED=0
export BOOT_MOUNTED
if "$recover" --yes >/dev/null 2>&1; then echo "unmounted /boot was accepted" >&2; exit 1; fi
if grep -q -- '--restore' "$MOCK_LOG"; then echo "restore ran despite a rejected precondition" >&2; exit 1; fi

# Non-BTRFS roots and non-VFAT boot mounts must fail before invoking Timeshift.
: > "$MOCK_LOG"
MOCK_ROOT_FSTYPE=ext4
export MOCK_ROOT_FSTYPE
if "$recover" --yes >/dev/null 2>&1; then echo "non-BTRFS root was accepted" >&2; exit 1; fi
if [ -s "$MOCK_LOG" ]; then echo "Timeshift ran for a non-BTRFS root" >&2; exit 1; fi
unset MOCK_ROOT_FSTYPE
: > "$MOCK_LOG"
MOCK_BOOT_FSTYPE=ext4
export MOCK_BOOT_FSTYPE
if "$recover" --yes >/dev/null 2>&1; then echo "non-VFAT /boot was accepted" >&2; exit 1; fi
if [ -s "$MOCK_LOG" ]; then echo "Timeshift ran for non-VFAT /boot" >&2; exit 1; fi
unset MOCK_BOOT_FSTYPE

# A concurrent backup must fail before touching Timeshift or archives.
: > "$MOCK_LOG"
MOCK_FLOCK_FAIL=1
export MOCK_FLOCK_FAIL
if "$backup" >/dev/null 2>&1; then echo "concurrent backup lock was ignored" >&2; exit 1; fi
if [ -s "$MOCK_LOG" ]; then echo "Timeshift ran while backup lock was held" >&2; exit 1; fi
unset MOCK_FLOCK_FAIL
echo "PASS: recovery path detects root device, binds boot archive to snapshot, and fails closed."
