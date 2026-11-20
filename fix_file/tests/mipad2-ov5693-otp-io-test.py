#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Fault the actual OV5693 OTP transaction and CCI accessors at the regmap."""

import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

kernel = Path(__file__).resolve().parents[2]
sensor_path = (Path(sys.argv[1]) if len(sys.argv) == 2
               else kernel / "drivers/media/i2c/ov5693.c")
sensor = sensor_path.read_text()
cci = (kernel / "drivers/media/v4l2-core/v4l2-cci.c").read_text()

prefix = r'''
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef uint8_t u8;
typedef uint32_t u32;
typedef uint64_t u64;
#define CCI_REG_LE (1U << 20)
#define CCI_REG_WIDTH_BYTES(x) (((x) >> 16) & 0xf)
#define CCI_REG_ADDR(x) ((x) & 0xffff)
#define CCI_REG8(x) ((1U << 16) | (x))
#define dev_err(...) do { } while (0)
#define dev_info(...) do { } while (0)
#define EXPORT_SYMBOL_GPL(name)
#define CHECK(expr) do { if (!(expr)) { \
	fprintf(stderr, "line %d: %s (main fault %d, cleanup %u)\n", \
		__LINE__, #expr, scenario, cleanup_fault); exit(1); } } while (0)

static int scenario;
static unsigned int cleanup_fault;

/* OV5693 OTP uses 8-bit CCI only; trip the fixture on another width. */
static u64 unused_read(const u8 *buf)
{
	(void)buf;
	abort();
}
static void unused_write(u64 val, u8 *buf)
{
	(void)val;
	(void)buf;
	abort();
}
'''
for order in ("le", "be"):
    for width in (16, 24, 32, 64):
        prefix += f"#define get_unaligned_{order}{width} unused_read\n"
        prefix += f"#define put_unaligned_{order}{width} unused_write\n"

prefix += r'''
enum { BANKS = 26, BANK_LEN = 16, BANK_OPS = BANK_LEN + 2, MAIN_OPS = 2 + BANKS * BANK_OPS };
enum { FRAME = 0x4202, STREAM = 0x0100, SELECT = 0x3d84, TRIGGER = 0x3d81, WINDOW = 0x3d00 };
struct regmap {
	unsigned int steps;
	u8 frame, stream, bank, otp_type;
};
struct ov5693_device {
	struct regmap *regmap;
	bool otp_cached, needs_reinit, streaming;
	u8 otp_data[BANKS * BANK_LEN];
};

static unsigned int main_expected(void)
{
	return scenario < 0 ? MAIN_OPS : (unsigned int)scenario + 1;
}

static int regmap_bulk_write(struct regmap *map, u32 reg, const u8 *data, size_t len)
{
	unsigned int i = map->steps++;

	CHECK(len == 1);
	if (i == main_expected()) {
		CHECK(reg == FRAME && *data == 0x0f);
		if (cleanup_fault & 1)
			return -EREMOTEIO;
	} else if (i == main_expected() + 1) {
		CHECK(reg == STREAM && *data == 0);
		if (cleanup_fault & 2)
			return -EIO;
	} else if (i == 0) {
		CHECK(reg == FRAME && *data == 0);
	} else if (i == 1) {
		CHECK(reg == STREAM && *data == 1);
	} else {
		CHECK(i < main_expected());
		if ((i - 2) % BANK_OPS == 0)
			CHECK(reg == SELECT && *data == (0xc0 | ((i - 2) / BANK_OPS)));
		else {
			CHECK((i - 2) % BANK_OPS == 1);
			CHECK(reg == TRIGGER && *data == 1);
		}
	}

	switch (reg) {
	case FRAME: map->frame = *data; break;
	case STREAM: map->stream = *data; break;
	case SELECT: map->bank = *data & 0x1f; break;
	case TRIGGER: CHECK(map->stream == 1 && map->frame == 0); break;
	default: abort();
	}
	/* Main-phase writes may have taken effect even when I2C reports an error. */
	return (int)i == scenario ? -ENXIO : 0;
}

static int regmap_bulk_read(struct regmap *map, u32 reg, u8 *data, size_t len)
{
	unsigned int i = map->steps++;
	unsigned int byte;

	CHECK(len == 1 && i >= 4 && i < main_expected());
	byte = (i - 2) % BANK_OPS;
	CHECK(byte >= 2 && reg == WINDOW + byte - 2);
	CHECK(map->stream == 1 && map->frame == 0);
	CHECK(map->bank == (i - 2) / BANK_OPS);
	if ((int)i == scenario)
		return -ENXIO;
	*data = i == 4 ? map->otp_type : map->bank ^ (byte - 2);
	return 0;
}

static void usleep_range(int lo, int hi)
{
	CHECK(lo > 0 && hi >= lo);
}
'''

definitions = sensor[sensor.index("#define OV5693_MIPAD2_OTP_START_REG"):
                     sensor.index("#define OV5693_MIPAD2_OTP_CAL_SIZE")]
stream_defs = sensor[sensor.index("#define OV5693_SW_STREAM_REG"):
                     sensor.index("#define OV5693_SW_RESET\t")]
stream_start = sensor.index("static int ov5693_enable_streaming(struct ov5693_device *ov5693, bool enable)\n{")
stream_end = sensor.index("\n}", stream_start) + 2
accessors = cci[cci.index("int cci_read("):cci.index("int cci_update_bits(")]
transaction = sensor[sensor.index("static int ov5693_mipad2_read_otp_bank("):
                     sensor.index("/*\n * Repack the Mi Pad 2 factory OTP")]

harness = r'''
static void run_case(int primary, unsigned int cleanup, bool valid_type)
{
	struct regmap map = { .frame = 0x0f, .otp_type = valid_type ? 0x3a : 0x00 };
	struct ov5693_device dev = { .regmap = &map };
	unsigned int steps, bank, i;
	int expected, ret;

	scenario = primary;
	cleanup_fault = cleanup;
	expected = primary >= 0 ? -ENXIO : cleanup & 1 ? -EREMOTEIO :
		   cleanup & 2 ? -EIO : !valid_type ? -EBADMSG : 0;
	ret = ov5693_mipad2_fetch_otp(&dev);
	CHECK(ret == expected);
	CHECK(map.steps == main_expected() + 2);
	CHECK(dev.needs_reinit == !!cleanup);
	CHECK(!dev.streaming);
	CHECK(dev.otp_cached == !expected);
	if (!(cleanup & 1))
		CHECK(map.frame == 0x0f);
	if (!(cleanup & 2))
		CHECK(map.stream == 0);
	if (!expected) {
		CHECK(dev.otp_data[0] == 0x3a);
		for (bank = 0; bank < BANKS; bank++)
			for (i = (bank == 0); i < BANK_LEN; i++)
				CHECK(dev.otp_data[bank * BANK_LEN + i] == (bank ^ i));
	}
	if (!expected || cleanup) {
		steps = map.steps;
		CHECK(ov5693_mipad2_fetch_otp(&dev) == (cleanup ? -EBUSY : 0));
		CHECK(map.steps == steps);
	}
}

int main(void)
{
	struct regmap map = { .frame = 0x0f };
	struct ov5693_device active = { .regmap = &map, .streaming = true };
	unsigned int cleanup;
	int fault;

	CHECK(ov5693_mipad2_fetch_otp(&active) == -EBUSY && !map.steps);
	for (fault = -1; fault < MAIN_OPS; fault++)
		for (cleanup = 0; cleanup < 4; cleanup++)
			run_case(fault, cleanup, true);
	run_case(-1, 0, false);
	printf("OV5693: %u scripted I2C/cleanup cases, active-stream exclusion and OTP contents pass\n",
	       (MAIN_OPS + 1U) * 4U);
	return 0;
}
'''

with tempfile.TemporaryDirectory(prefix="mipad2-ov5693-otp-io.") as tmp:
    root = Path(tmp)
    src = root / "otp.c"
    src.write_text(prefix + definitions + stream_defs + accessors +
                   sensor[stream_start:stream_end] + "\n" + transaction + harness)
    cc = shlex.split(os.environ.get("CC", "cc"))
    for opt in ("-O0", "-O2"):
        binary = root / "otp"
        subprocess.run(cc + ["-std=gnu11", "-Wall", "-Wextra", opt,
                             "-ftrivial-auto-var-init=pattern",
                             "-fsanitize=undefined", "-fno-sanitize-recover=all",
                             str(src), "-o", str(binary)], check=True)
        subprocess.run([binary], check=True)
