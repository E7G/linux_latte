#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Report local Mi Pad 2 EFI crash records without printing or deleting logs."""

import errno
import hashlib
import json
import os
import re
import stat
from pathlib import Path

LIVE = Path("/sys/fs/pstore")
ARCHIVE = Path("/var/lib/systemd/pstore")
RECORD = re.compile(r"dmesg-efi(?:_pstore)?-([0-9]{1,20})(\.enc\.z)?")
ARCHIVE_DIR = (re.compile(r"[0-9]{1,15}"), re.compile(r"[0-9]{3}"))
HEADER = re.compile(rb"(Panic|Oops|Emergency|Shutdown)#[0-9]+ Part[0-9]+")
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
FILE_FLAGS = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
MAX_ENTRIES = 4096  # Whole tree, including unrelated entries.
MAX_BYTES = 64 * 1024  # EFI chunks are normally much smaller.


def read_record(parent, name):
    if not stat.S_ISREG(os.stat(name, dir_fd=parent, follow_symlinks=False).st_mode):
        raise OSError(errno.EINVAL, "not a regular file")
    fd = os.open(name, FILE_FLAGS, dir_fd=parent)
    with os.fdopen(fd, "rb") as record:
        if not stat.S_ISREG(os.fstat(record.fileno()).st_mode):
            raise OSError(errno.EINVAL, "not a regular file")
        data = record.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise OSError(errno.EFBIG, "oversize record")
    return data


def collect(source, archived):
    records = set()
    errors = 0
    scanned = 0
    limited = False

    def walk(fd, depth=0):
        nonlocal errors, scanned, limited
        with os.scandir(fd) as entries:
            for entry in entries:
                if scanned == MAX_ENTRIES:
                    limited = True
                    return
                scanned += 1
                name = entry.name
                match = RECORD.fullmatch(name)
                try:
                    if match:
                        record_id = int(match[1])
                        if record_id >= 2**64:
                            continue
                        data = read_record(fd, name)
                        if match[2]:
                            kind = "compressed"
                        else:
                            header = HEADER.fullmatch(data.partition(b"\n")[0])
                            kind = header[1].decode("ascii").lower() if header else "unknown"
                        records.add((record_id, hashlib.sha256(data).digest(), kind))
                    elif (archived and depth < len(ARCHIVE_DIR)
                          and ARCHIVE_DIR[depth].fullmatch(name)):
                        child = os.open(name, DIR_FLAGS, dir_fd=fd)
                        try:
                            walk(child, depth + 1)
                        finally:
                            os.close(child)
                        if limited:
                            return
                except OSError:
                    errors += 1

    try:
        fd = os.open(source, DIR_FLAGS)
    except FileNotFoundError:
        return {"state": "missing", "records": 0, "errors": 0}, records
    except OSError:
        return {"state": "unreadable", "records": 0, "errors": 1}, records
    try:
        walk(fd)
    except OSError:
        errors += 1
    finally:
        os.close(fd)
    state = "partial" if errors or limited else "records" if records else "empty"
    return {"state": state, "records": len(records), "errors": errors,
            "scan_limit_hit": limited}, records


def pstore_mounted(mountinfo):
    for line in mountinfo.splitlines():
        mount, sep, fs = line.partition(" - ")
        fields = mount.split()
        if sep and len(fields) > 4 and fields[4] == str(LIVE) and fs.startswith("pstore "):
            return True
    return False


def report(live, archive, mounted):
    live_status, live_records = (collect(live, False) if mounted else
                                 ({"state": "not-mounted", "records": 0, "errors": 0}, set()))
    archive_status, archive_records = collect(archive, True)
    groups = {}
    for record_id, _digest, kind in live_records | archive_records:
        # EFI's id packs wall-clock seconds, part (2 digits), count (3 digits).
        group = groups.setdefault((record_id // 100000, record_id % 1000), {})
        group[kind] = group.get(kind, 0) + 1
    return {
        "live": live_status,
        "archive": archive_status,
        "efi_groups": [{"record_epoch_seconds": seconds, "dump_count": count,
                        "chunks_by_header": kinds}
                       for (seconds, count), kinds in sorted(groups.items())],
    }


def main():
    try:
        boot_id = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
        mountinfo = Path("/proc/self/mountinfo").read_text(encoding="utf-8", errors="replace")
    except OSError:
        print(json.dumps({"state": "observer-unavailable"}))
        return 2
    result = report(LIVE, ARCHIVE, pstore_mounted(mountinfo))
    result["observer_boot_id"] = boot_id
    result["observer_kernel_release"] = os.uname().release
    print(json.dumps(result, sort_keys=True))
    return 2 if any(result[k]["errors"] or result[k].get("scan_limit_hit")
                    for k in ("live", "archive")) else 0


if __name__ == "__main__":
    raise SystemExit(main())
