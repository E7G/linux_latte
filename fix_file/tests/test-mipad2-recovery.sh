#!/bin/sh
set -eu
repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
pkg="$repo_root/packages/mipad2-recovery/src"
backup="$pkg/mp2-backup"
recover="$pkg/mp2-recover"
helper="$pkg/mp2-restore-boot"
[ "$(id -u)" -eq 0 ] || { echo "Run tests as root (or with sudo)." >&2; exit 77; }
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
mkdir -p "$tmp/bin" "$tmp/recovery" "$tmp/state"
touch "$tmp/hook" "$tmp/service-link"
chmod +x "$tmp/hook"
count="$tmp/list-count"
log="$tmp/timeshift.log"
tar_log="$tmp/tar.log"
comment_file="$tmp/comment"
export MIPAD2_RECOVERY_DIR="$tmp/recovery"
export MIPAD2_RECOVERY_STATE_DIR="$tmp/state"
export MIPAD2_RESTORE_HOOK="$tmp/hook"
export MIPAD2_RESTORE_HELPER="$helper"
export MIPAD2_RESTORE_SERVICE_LINK="$tmp/service-link"
export MOCK_COUNT="$count" MOCK_LOG="$log" MOCK_TAR_LOG="$tar_log" MOCK_COMMENT="$comment_file"
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
    echo "Device: $MOCK_ROOT_DEV"
    echo "Num  Name                 Tags  Description"
    if [ -s "$MOCK_COMMENT" ]; then
      comment=$(cat "$MOCK_COMMENT")
      echo "0    > 2026-09-25_01-10-00 D     $comment"
      echo "1    > 2026-09-25_01-11-00 H     hourly"
    fi
    ;;
  --create)
    while [ "$#" -gt 0 ]; do
      if [ "$1" = --comments ]; then shift; printf '%s\n' "$1" > "$MOCK_COMMENT"; fi
      shift || true
    done
    exit 0
    ;;
  --restore)
    snap=
    while [ "$#" -gt 0 ]; do
      if [ "$1" = --snapshot ]; then shift; snap=$1; fi
      shift || true
    done
    [ -n "$snap" ] || exit 2
    cat "$MIPAD2_RECOVERY_DIR/boot-$snap.tar.zst.meta" > "$MIPAD2_RECOVERY_STATE_DIR/snapshot-token"
    "$MIPAD2_RESTORE_HELPER" hook
    ;;
  *) echo "unexpected timeshift args: $*" >&2; exit 2 ;;
esac
MOCK
cat > "$tmp/bin/tar" <<'MOCK'
#!/bin/sh
printf '%s\n' "$*" >> "$MOCK_TAR_LOG"
[ "$1" = --zstd ] || exit 2
while [ "$#" -gt 0 ]; do
  if [ "$1" = -cpf ]; then shift; echo testdata > "$1"; exit 0; fi
  if [ "$1" = -xpf ]; then exit 0; fi
  shift
done
exit 2
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
cat > "$tmp/bin/systemctl" <<'MOCK'
#!/bin/sh
echo "$*" >> "$MOCK_SYSTEMCTL_LOG"
MOCK
chmod +x "$tmp/bin/"*
export PATH="$tmp/bin:$PATH" MOCK_SYSTEMCTL_LOG="$tmp/systemctl.log"

for script in "$backup" "$recover" "$helper"; do sh -n "$script"; done
"$backup" >/dev/null
archive="$MIPAD2_RECOVERY_DIR/boot-2026-09-25_01-10-00.tar.zst"
[ -s "$archive" ] && [ -s "$archive.sha256" ] && [ -s "$archive.meta" ]
grep -Fq -- "--snapshot-device $MOCK_ROOT_DEV" "$MOCK_LOG"
grep -Fq -- "--create --snapshot-device $MOCK_ROOT_DEV" "$MOCK_LOG"
grep -q -- '--exclude=./.mipad2-recovery' "$MOCK_TAR_LOG"

# Timeshift restore invokes the pre-reboot hook, which verifies token/checksum and repairs /boot.
"$recover" --yes
grep -Fq -- "--restore --snapshot 2026-09-25_01-10-00 --snapshot-device $MOCK_ROOT_DEV --target $MOCK_ROOT_DEV" "$MOCK_LOG"
grep -q -- '--zstd -xpf .*boot-2026-09-25_01-10-00.tar.zst -C /boot' "$MOCK_TAR_LOG"
[ ! -e "$MIPAD2_RECOVERY_DIR/pending-restore" ]

# A root-token mismatch must fail closed and preserve pending work for recovery.
printf '%s\n%s\n' "$(basename "$archive")" "/dev/loop1" > "$MIPAD2_RECOVERY_DIR/pending-restore"
printf '%s\n' "00000000-0000-0000-0000-000000000000" > "$MIPAD2_RECOVERY_STATE_DIR/snapshot-token"
if "$helper" hook >/dev/null 2>&1; then echo "mismatched root token was accepted" >&2; exit 1; fi
[ -e "$MIPAD2_RECOVERY_DIR/pending-restore" ]
cat "$archive.meta" > "$MIPAD2_RECOVERY_STATE_DIR/snapshot-token"
"$helper" service >/dev/null
[ ! -e "$MIPAD2_RECOVERY_DIR/pending-restore" ]
grep -q '^reboot$' "$MOCK_SYSTEMCTL_LOG"

# Missing archive, bad checksum, and an unmounted /boot must fail before restore.
: > "$MOCK_LOG"
mv "$archive" "$archive.tmp"
if "$recover" --yes 2>&1; then echo "missing archive was accepted" >&2; exit 1; fi
if grep -q -- '--restore' "$MOCK_LOG"; then echo "restore ran despite a rejected precondition" >&2; exit 1; fi
: > "$MOCK_LOG"
mv "$archive.tmp" "$archive"
printf 'invalid  %s\n' "$archive" > "$archive.sha256"
if "$recover" --yes 2>&1; then echo "bad checksum was accepted" >&2; exit 1; fi
if grep -q -- '--restore' "$MOCK_LOG"; then echo "restore ran despite a rejected precondition" >&2; exit 1; fi
(cd "$MIPAD2_RECOVERY_DIR" && sha256sum "$(basename "$archive")" > "$(basename "$archive").sha256")
: > "$MOCK_LOG"
BOOT_MOUNTED=0
export BOOT_MOUNTED
if "$recover" --yes 2>&1; then echo "unmounted /boot was accepted" >&2; exit 1; fi
if grep -q -- '--restore' "$MOCK_LOG"; then echo "restore ran despite a rejected precondition" >&2; exit 1; fi

# Non-BTRFS roots and non-VFAT boot mounts fail before invoking Timeshift.
: > "$MOCK_LOG"
MOCK_ROOT_FSTYPE=ext4
export MOCK_ROOT_FSTYPE
if "$recover" --yes 2>&1; then echo "non-BTRFS root was accepted" >&2; exit 1; fi
[ ! -s "$MOCK_LOG" ]
unset MOCK_ROOT_FSTYPE
: > "$MOCK_LOG"
MOCK_BOOT_FSTYPE=ext4
export MOCK_BOOT_FSTYPE
if "$recover" --yes 2>&1; then echo "non-VFAT /boot was accepted" >&2; exit 1; fi
[ ! -s "$MOCK_LOG" ]
unset MOCK_BOOT_FSTYPE

# Concurrent backup and missing restore hooks are rejected before snapshot creation.
: > "$MOCK_LOG"
MOCK_FLOCK_FAIL=1
export MOCK_FLOCK_FAIL
if "$backup" >/dev/null 2>&1; then echo "concurrent backup lock was ignored" >&2; exit 1; fi
[ ! -s "$MOCK_LOG" ]
unset MOCK_FLOCK_FAIL
MIPAD2_RESTORE_HOOK="$tmp/missing-hook"
export MIPAD2_RESTORE_HOOK
if "$backup" >/dev/null 2>&1; then echo "backup without restore integration was accepted" >&2; exit 1; fi
[ ! -s "$MOCK_LOG" ]
echo "PASS: restore archives are bound to snapshots, restored by pre-reboot hook, and safely retried at boot."
