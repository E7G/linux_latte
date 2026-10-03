#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
from pathlib import Path
import subprocess
import sys
import tempfile

kernel = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
src = (kernel / 'drivers/media/i2c/ov5693.c').read_text()
start = src.index('static bool ov5693_mipad2_otp_checksum(')
end = src.index('static int ov5693_mipad2_otp_cal_read(', start)
parser = src[start:end]

prefix = r'''#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint8_t u8;
typedef uint16_t u16;
#define OV5693_MIPAD2_OTP_BANK_SIZE 16
#define OV5693_MIPAD2_OTP_TYPE 0x3a
#define OV5693_MIPAD2_OTP_CAL_SIZE 320
#define OV5693_MIPAD2_OTP_DATA_OFFSET 48
#define OV5693_MIPAD2_OTP_DATA_SIZE 368
'''

test = r'''
static u8 checksum(const u8 *p, size_t n)
{
	u8 sum = 0;
	size_t i;
	for (i = 0; i < n; i++)
		sum = (sum + p[i]) % 255;
	return sum + 1;
}

static void set_group(u8 *data, unsigned int offset, unsigned int check,
		      u8 seed)
{
	unsigned int i;
	data[offset] = 0x40;
	for (i = 1; i <= 17; i++)
		data[offset + i] = seed + i;
	data[check] = checksum(data + offset + 1, 17);
}

static void set_meta(u8 *raw, unsigned int bank, u8 status, u8 module)
{
	u8 *p = raw + bank * 16;
	unsigned int i;
	p[0] = status;
	p[1] = module;
	for (i = 2; i < 15; i++)
		p[i] = i + bank;
	p[15] = checksum(p + 1, 14);
}

static void make_fixture(u8 *raw, u8 module, bool fallback)
{
	u8 *data;
	unsigned int i;

	memset(raw, 0, 416);
	raw[0] = 0x3a;
	set_meta(raw, 1, fallback ? 0x00 : 0x40,
		 fallback ? 0x00 : module);
	set_meta(raw, 2, 0x40, module);
	data = raw + 48;
	set_group(data, fallback ? 19 : 0, fallback ? 37 : 18, 0x10);
	set_group(data, fallback ? 57 : 38, fallback ? 75 : 56, 0x20);
	data[79] = 0x50;
	for (i = 80; i <= 220; i++)
		data[i] = i ^ 0x5a;
	data[221] = checksum(data + 80, 141);
	for (i = 224; i <= 364; i++)
		data[i] = i ^ 0xa5;
	data[365] = checksum(data + 224, 141);
}

int main(void)
{
	u8 raw[416], cal[320];
	u16 crc;
	int ret;
	FILE *fp;

	make_fixture(raw, 1, false);
	ret = ov5693_mipad2_parse_otp(raw, cal);
	if (ret || cal[2] != 1 ||
	    cal[0] != raw[48 + 1] || cal[1] != raw[48 + 2] ||
	    cal[13] != raw[48 + 3] || cal[14] != raw[48 + 4] ||
	    cal[16] != raw[48 + 5] || cal[18] != raw[48 + 6] ||
	    cal[19] != raw[48 + 7] ||
	    cal[302] != raw[48 + 8] || cal[303] != raw[48 + 9] ||
	    cal[306] != raw[48 + 10] || cal[307] != raw[48 + 11] ||
	    cal[310] != raw[48 + 12] || cal[311] != raw[48 + 13] ||
	    cal[314] != raw[48 + 14] || cal[315] != raw[48 + 15] ||
	    cal[15] != raw[48 + 42] || cal[17] != raw[48 + 43] ||
	    cal[304] != raw[48 + 46] || cal[305] != raw[48 + 47] ||
	    cal[308] != raw[48 + 48] || cal[309] != raw[48 + 49] ||
	    cal[312] != raw[48 + 50] || cal[313] != raw[48 + 51] ||
	    cal[316] != raw[48 + 52] || cal[317] != raw[48 + 53] ||
	    cal[20] != raw[48 + 80] ||
	    cal[161] != raw[48 + 224] ||
	    cal[21] != raw[48 + 80 + 35] ||
	    cal[55] != raw[48 + 81])
		return 1;
	fp = fopen("ov5693_raw_fixture.bin", "wb");
	if (!fp || fwrite(raw, 1, sizeof(raw), fp) != sizeof(raw) || fclose(fp))
		return 5;
	fp = fopen("ov5693_cal_fixture.bin", "wb");
	if (!fp || fwrite(cal, 1, sizeof(cal), fp) != sizeof(cal) || fclose(fp))
		return 6;
	crc = ov5693_mipad2_otp_crc16(cal, 318);
	if (cal[318] != (u8)crc || cal[319] != (u8)(crc >> 8))
		return 2;

	make_fixture(raw, 2, true);
	ret = ov5693_mipad2_parse_otp(raw, cal);
	if (ret ||
	    cal[0] != raw[48 + 23] || cal[1] != raw[48 + 24] ||
	    cal[13] != raw[48 + 25] || cal[14] != raw[48 + 26] ||
	    cal[16] != raw[48 + 27] || cal[18] != raw[48 + 28] ||
	    cal[19] != raw[48 + 29] ||
	    cal[302] != raw[48 + 30] || cal[303] != raw[48 + 31] ||
	    cal[306] != raw[48 + 32] || cal[307] != raw[48 + 33] ||
	    cal[310] != raw[48 + 34] || cal[311] != raw[48 + 35] ||
	    cal[314] != raw[48 + 36] || cal[315] != raw[48 + 37] ||
	    cal[15] != raw[48 + 64] || cal[17] != raw[48 + 65] ||
	    cal[304] != raw[48 + 68] || cal[305] != raw[48 + 69] ||
	    cal[308] != raw[48 + 70] || cal[309] != raw[48 + 71] ||
	    cal[312] != raw[48 + 72] || cal[313] != raw[48 + 73] ||
	    cal[316] != raw[48 + 74] || cal[317] != raw[48 + 75] ||
	    cal[21] != raw[48 + 87] || cal[27] != raw[48 + 81])
		return 3;

	raw[48 + 221] ^= 1;
	if (ov5693_mipad2_parse_otp(raw, cal) != -EBADMSG)
		return 4;

	puts("OV5693 parsed OTP fixture tests passed");
	return 0;
}
'''

with tempfile.TemporaryDirectory(prefix="ov5693-otp-fixture-") as tmp:
    tmpdir = Path(tmp)
    out = tmpdir / "ov5693_parsed_calibration_test.c"
    binary = tmpdir / "ov5693_parsed_calibration_test"
    raw_fixture = tmpdir / "ov5693_raw_fixture.bin"
    cal_fixture = tmpdir / "ov5693_cal_fixture.bin"
    bad_cal = tmpdir / "ov5693_cal_fixture_bad.bin"

    out.write_text(prefix + parser + test)
    subprocess.run([
        "cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
        str(out), "-o", str(binary),
    ], check=True)
    subprocess.run([str(binary)], cwd=tmpdir, check=True)
    smoke = kernel / "fix_file/tests/mipad2-ov5693-otp-test.sh"
    subprocess.run([
        "/bin/sh", str(smoke), str(raw_fixture), str(cal_fixture),
    ], check=True)

    corrupted = bytearray(cal_fixture.read_bytes())
    corrupted[318] ^= 1
    bad_cal.write_bytes(corrupted)
    bad = subprocess.run([
        "/bin/sh", str(smoke), str(raw_fixture), str(bad_cal),
    ], capture_output=True, text=True)
    if bad.returncode == 0:
        raise SystemExit("host smoke test accepted a corrupted parsed OTP CRC")
    print("front OTP smoke test rejects corrupted CRC")

    unreadable_raw = tmpdir / "raw_read_error"
    unreadable_raw.mkdir()
    raw_error = subprocess.run([
        "/bin/sh", str(smoke), str(unreadable_raw), str(cal_fixture),
    ], capture_output=True, text=True)
    if raw_error.returncode == 0 or "MISS front-camera raw OTP read:" not in raw_error.stderr:
        raise SystemExit("host smoke test did not report a raw OTP read error")
    print("front OTP smoke test reports raw-provider read errors")

    unreadable_cal = tmpdir / "cal_read_error"
    unreadable_cal.mkdir()
    cal_error = subprocess.run([
        "/bin/sh", str(smoke), str(raw_fixture), str(unreadable_cal),
    ], capture_output=True, text=True)
    if cal_error.returncode == 0 or "MISS front-camera parsed OTP read:" not in cal_error.stderr:
        raise SystemExit("host smoke test did not report a parsed OTP read error")
    print("front OTP smoke test reports parsed-provider read errors")
