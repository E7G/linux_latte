#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Test T4KA3 OTP checksum and validation using the production C helpers."""

from pathlib import Path
import subprocess
import sys
import tempfile


kernel = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
src = (kernel / "drivers/media/i2c/t4ka3.c").read_text(encoding="utf-8")
start = src.index("static u8 t4ka3_mipad2_otp_checksum(")
end = src.index("static u16 t4ka3_mipad2_otp_crc16(", start)
helpers = src[start:end]

prefix = r'''#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;

#define T4KA3_MIPAD2_OTP_SIZE 578
#define T4KA3_MIPAD2_OTP_MODULE_END 15
#define T4KA3_MIPAD2_OTP_AF_START 16
#define T4KA3_MIPAD2_OTP_AF_END 31
#define T4KA3_MIPAD2_OTP_LS1_START 32
#define T4KA3_MIPAD2_OTP_LS1_END 303
#define T4KA3_MIPAD2_OTP_LS2_START 304
#define T4KA3_MIPAD2_OTP_LS2_END 577

struct t4ka3_data {
    u8 otp_data[T4KA3_MIPAD2_OTP_SIZE];
};
'''

test = r'''
static void fill_group(u8 *data, unsigned int start, unsigned int end)
{
    memset(data + start + 1, 0xff, end - start - 1);
    data[start] = 1;
    data[end] = 0;
}

int main(void)
{
    struct t4ka3_data sensor = { 0 };

    fill_group(sensor.otp_data, 0, T4KA3_MIPAD2_OTP_MODULE_END);
    fill_group(sensor.otp_data, T4KA3_MIPAD2_OTP_AF_START,
               T4KA3_MIPAD2_OTP_AF_END);
    fill_group(sensor.otp_data, T4KA3_MIPAD2_OTP_LS1_START,
               T4KA3_MIPAD2_OTP_LS1_END);
    fill_group(sensor.otp_data, T4KA3_MIPAD2_OTP_LS2_START,
               T4KA3_MIPAD2_OTP_LS2_END);

    if (t4ka3_mipad2_validate_otp(&sensor))
        return 1;

    sensor.otp_data[T4KA3_MIPAD2_OTP_LS2_START + 1]--;
    if (t4ka3_mipad2_validate_otp(&sensor) != -EBADMSG)
        return 2;

    sensor.otp_data[T4KA3_MIPAD2_OTP_LS2_END] = 254;
    if (t4ka3_mipad2_validate_otp(&sensor))
        return 3;

    puts("T4KA3 OTP checksum overflow and validation tests passed");
    return 0;
}
'''

with tempfile.TemporaryDirectory(prefix="t4ka3-otp-checksum-") as tmp:
    out = Path(tmp) / "t4ka3_otp_checksum_test.c"
    binary = Path(tmp) / "t4ka3_otp_checksum_test"
    out.write_text(prefix + helpers + test, encoding="utf-8")
    subprocess.run(
        ["cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror", str(out), "-o", str(binary)],
        check=True,
    )
    subprocess.run([str(binary)], check=True)
