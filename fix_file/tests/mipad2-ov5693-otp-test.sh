#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-only
set -eu

raw_provider=${1:-/sys/bus/nvmem/devices/mipad2-ov5693-otp-raw/nvmem}
cal_provider=${2:-/sys/bus/nvmem/devices/mipad2-ov5693-otp-calibrated/nvmem}

if [ ! -r "$raw_provider" ]; then
	echo "MISS Mi Pad 2 front-camera raw OTP NVMEM: $raw_provider" >&2
	exit 1
fi
if [ ! -r "$cal_provider" ]; then
	echo "MISS Mi Pad 2 front-camera parsed OTP NVMEM: $cal_provider" >&2
	exit 1
fi

raw_size=$(wc -c < "$raw_provider")
raw_type=$(od -An -v -tu1 -N1 "$raw_provider" | tr -d '[:space:]')
if [ "$raw_size" -ne 416 ] || [ "$raw_type" -ne 58 ]; then
	echo "MISS front-camera raw OTP: size=$raw_size type=$raw_type (expected 416/58)" >&2
	exit 1
fi

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT HUP INT TERM
cat "$cal_provider" > "$tmp"
cal_size=$(wc -c < "$tmp")
if [ "$cal_size" -ne 320 ]; then
	echo "MISS front-camera parsed OTP size: $cal_size (expected 320)" >&2
	exit 1
fi

od -An -v -tu1 "$tmp" | awk '
function xor16(a, b, result, place) {
	result = 0
	place = 1
	while (a || b) {
		if (a % 2 != b % 2)
			result += place
		a = int(a / 2)
		b = int(b / 2)
		place *= 2
	}
	return result
}
{
	for (i = 1; i <= NF; i++)
		b[n++] = $i
}
END {
	if (n != 320) {
		printf "MISS parsed OTP byte count: %d\n", n > "/dev/stderr"
		exit 1
	}

	crc = 0
	for (i = 0; i < 318; i++) {
		crc = xor16(crc, b[i])
		for (bit = 0; bit < 8; bit++) {
			if (crc % 2)
				crc = xor16(int(crc / 2), 40961)
			else
				crc = int(crc / 2)
		}
	}
	stored = b[318] + 256 * b[319]
	printf "parsed OTP: bytes=%d crc=%04x stored=%04x\n", n, crc, stored
	if (crc != stored) {
		print "MISS parsed OTP CRC16/IBM" > "/dev/stderr"
		exit 2
	}

	# This module has no AF OTP; Android exports its fixed focus block.
	if (b[2] != 1 || b[3] != 0 || b[4] != 10 || b[5] != 138 ||
	    b[6] != 2 || b[7] != 44 || b[8] != 1 || b[9] != 100 ||
	    b[10] != 0 || b[11] != 132 || b[12] != 3) {
		print "MISS parsed OTP fixed AF block" > "/dev/stderr"
		exit 3
	}
	print "OK   front-camera parsed factory OTP"
}
'

sha256sum "$tmp"
