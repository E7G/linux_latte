#!/bin/sh
set -eu

provider=${1:-/sys/bus/nvmem/devices/mipad2-t4ka3-otp/nvmem}

if [ ! -r "$provider" ]; then
	echo "MISS Mi Pad 2 rear-camera OTP NVMEM: $provider" >&2
	exit 1
fi

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
cat "$provider" > "$tmp"

size=$(wc -c < "$tmp")
if [ "$size" -ne 578 ]; then
	echo "MISS rear-camera OTP size: $size (expected 578)" >&2
	exit 1
fi

od -An -v -tu1 "$tmp" | awk '
{
	for (i = 1; i <= NF; i++)
		b[n++] = $i
}
END {
	if (n != 578) {
		printf "MISS OTP byte count: %d\n", n > "/dev/stderr"
		exit 1
	}

	ok = 1
	if (b[0] != 1) ok = 0
	s = 0; for (i = 1; i <= 14; i++) s += b[i]
	m = s % 255
	printf "module: valid=%d checksum=%d stored=%d\n", b[0], m, b[15]
	if (m != b[15]) ok = 0

	if (b[16] != 1) ok = 0
	s = 0; for (i = 17; i <= 30; i++) s += b[i]
	a = s % 255
	printf "af: valid=%d checksum=%d stored=%d\n", b[16], a, b[31]
	if (a != b[31]) ok = 0

	if (b[32] != 1) ok = 0
	s = 0; for (i = 33; i <= 302; i++) s += b[i]
	l1 = s % 255
	printf "ls1: valid=%d checksum=%d stored=%d\n", b[32], l1, b[303]
	if (l1 != b[303]) ok = 0

	if (b[304] != 1) ok = 0
	s = 0; for (i = 305; i <= 576; i++) s += b[i]
	l2 = s % 255
	printf "ls2: valid=%d checksum=%d stored=%d\n", b[304], l2, b[577]
	if (l2 != b[577]) ok = 0

	inf = b[19] * 256 + b[20]
	macro = b[21] * 256 + b[22]
	printf "vendor=%d build=20%02d-%02d-%02d %02d:%02d:%02d AF=%d..%d span=%d grid=%dx%d\n",
	       b[1], b[5], b[6], b[7], b[8], b[9], b[10],
	       inf, macro, macro - inf, b[38], b[39]

	if (!ok) {
		print "MISS rear-camera OTP validation" > "/dev/stderr"
		exit 2
	}
	print "OK   rear-camera factory OTP"
}
'

sha256sum "$tmp"
