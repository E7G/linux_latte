#!/usr/bin/env python3
"""Verify T4KA3 NVMEM calibration packing against Xiaomi Android layout."""

import argparse
import hashlib
from pathlib import Path
import sys


RAW_DEFAULT = "/sys/bus/nvmem/devices/mipad2-t4ka3-otp/nvmem"
CAL_DEFAULT = "/sys/bus/nvmem/devices/mipad2-t4ka3-otp-calibrated/nvmem"
RAW_SIZE = 578
CAL_SIZE = 544


def checksum255(data):
    return sum(data) % 255


def crc16_ibm(data):
    crc = 0
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ (0xA001 if crc & 1 else 0)
    return crc


def parse_android_layout(raw):
    if len(raw) != RAW_SIZE:
        raise ValueError(f"raw size {len(raw)} != {RAW_SIZE}")

    groups = ((0, 16, 15), (16, 32, 31), (32, 304, 303), (304, 578, 577))
    for start, end, checksum_offset in groups:
        if raw[start] != 1:
            raise ValueError(f"OTP group at 0x{start:x} not valid")
        if checksum255(raw[start + 1:checksum_offset]) != raw[checksum_offset]:
            raise ValueError(f"OTP checksum mismatch at 0x{checksum_offset:x}")

    grid_x, grid_y = raw[38], raw[39]
    lsc_size = grid_x * grid_y * 4 + 1
    if not grid_x or not grid_y or lsc_size > 253:
        raise ValueError(f"unsupported LSC grid {grid_x}x{grid_y}")

    cal = bytearray(CAL_SIZE)
    cal[0:2] = raw[33:35]
    cal[2] = 1
    cal[3:5] = raw[17:19]
    cal[5] = raw[22]
    cal[6] = raw[21]
    cal[7] = raw[20]
    cal[8] = raw[19]
    cal[9:11] = cal[7:9]
    cal[11:13] = cal[5:7]
    cal[13] = raw[35]
    cal[14] = raw[36]
    cal[15] = raw[308]
    cal[16] = raw[37]
    cal[17] = raw[309]
    cal[18:20] = bytes((grid_x, grid_y))
    cal[20:20 + lsc_size] = raw[40:40 + lsc_size]
    cal[273:273 + lsc_size] = raw[312:312 + lsc_size]

    for output, source in ((526, 293), (528, 565)):
        cal[output:output + 2] = raw[source:source + 2]
        cal[output + 4:output + 6] = raw[source + 2:source + 4]
        cal[output + 8:output + 10] = raw[source + 4:source + 6]
        cal[output + 12:output + 14] = raw[source + 6:source + 8]

    crc = crc16_ibm(cal[:542])
    cal[542:544] = crc.to_bytes(2, "little")
    return bytes(cal)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("raw", nargs="?", default=RAW_DEFAULT)
    parser.add_argument("calibrated", nargs="?", default=CAL_DEFAULT)
    args = parser.parse_args()

    try:
        raw = Path(args.raw).read_bytes()
        actual = Path(args.calibrated).read_bytes()
        expected = parse_android_layout(raw)
    except (OSError, ValueError) as exc:
        print(f"MISS {exc}", file=sys.stderr)
        return 1

    if len(actual) != CAL_SIZE:
        print(f"MISS calibrated size {len(actual)} != {CAL_SIZE}", file=sys.stderr)
        return 1
    if actual != expected:
        mismatch = next(i for i, (a, b) in enumerate(zip(actual, expected)) if a != b)
        print(
            f"MISS Android OTP mapping differs at 0x{mismatch:03x}: "
            f"actual={actual[mismatch]:02x} expected={expected[mismatch]:02x}",
            file=sys.stderr,
        )
        return 1

    crc = int.from_bytes(actual[542:544], "little")
    focus_inf = int.from_bytes(raw[19:21], "big")
    focus_macro = int.from_bytes(raw[21:23], "big")
    print(
        f"OK   T4KA3 Android OTP layout bytes={len(actual)} "
        f"AF={focus_inf}..{focus_macro} grid={actual[18]}x{actual[19]} "
        f"CRC16/IBM={crc:04x} "
        f"SHA256={hashlib.sha256(actual).hexdigest()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
