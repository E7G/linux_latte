#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Check the exact AtomISP capture-format bridge and TRY_FMT format selection."""

import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile

pci = Path(__file__).resolve().parents[2] / "drivers/staging/media/atomisp/pci"
ioctl = Path(sys.argv[1]).read_text() if len(sys.argv) == 2 else (pci / "atomisp_ioctl.c").read_text()
cmd = (pci / "atomisp_cmd.c").read_text()
common = (pci / "atomisp_common.h").read_text()


def extract(source, pattern):
    match = re.search(pattern, source, re.M | re.S)
    if not match:
        raise SystemExit(f"AtomISP format source not found: {pattern}")
    return match[0]


table = extract(ioctl, r"^const struct atomisp_format_bridge atomisp_output_fmts\[\] = \{.*?^\};")
lookup = extract(ioctl, r"^const struct atomisp_format_bridge \*\natomisp_get_format_bridge\(.*?^\}")
bridge = extract(common, r"^struct atomisp_format_bridge \{.*?^\};")
custom_codes = re.findall(r"^#define V4L2_MBUS_FMT_CUSTOM_\w+[^\n]*",
                          (pci.parent / "include/linux/atomisp.h").read_text(), re.M)
try_fmt = extract(cmd, r"^int atomisp_try_fmt\(.*?^\}")
select_format = extract(try_fmt, r"^\tfmt = atomisp_get_format_bridge\(f->pixelformat\);.*?^\t\}")

code = r"""
#include <errno.h>
#include <linux/media-bus-format.h>
#include <linux/videodev2.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include "ia_css_frame_format.h"
typedef uint32_t u32;
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
""" + "\n".join((*custom_codes, bridge, table, lookup)) + r"""
static int select_capture_format(struct v4l2_pix_format *f)
{
    const struct atomisp_format_bridge *fmt;
""" + select_format + r"""
    return fmt->pixelformat == f->pixelformat ? 0 : -EINVAL;
}

int main(void)
{
    static const u32 expected[] = {
        V4L2_PIX_FMT_YUV420, V4L2_PIX_FMT_YVU420, V4L2_PIX_FMT_YUV422P,
        V4L2_PIX_FMT_NV12, V4L2_PIX_FMT_NV21, V4L2_PIX_FMT_NV16,
        V4L2_PIX_FMT_YUYV, V4L2_PIX_FMT_UYVY, V4L2_PIX_FMT_RGB565,
    };
    static const u32 fallback[] = {
        V4L2_PIX_FMT_YUV444, V4L2_PIX_FMT_YUV444M, V4L2_PIX_FMT_YUV24,
        V4L2_PIX_FMT_SBGGR10,
    };
    unsigned int i, capture = 0;

    if (atomisp_get_format_bridge(V4L2_PIX_FMT_YUV444)) {
        fputs("packed 16-bit Y444 is incorrectly exposed\n", stderr);
        return 1;
    }
    for (i = 0; i < ARRAY_SIZE(atomisp_output_fmts); i++) {
        struct v4l2_pix_format req = {.pixelformat=atomisp_output_fmts[i].pixelformat};
        if (atomisp_output_fmts[i].sh_fmt == IA_CSS_FRAME_FORMAT_RAW)
            continue; /* ENUM_FMT skips these sensor-only formats */
        if (capture >= ARRAY_SIZE(expected) || req.pixelformat != expected[capture] ||
            select_capture_format(&req) || req.pixelformat != expected[capture])
            return 2;
        capture++;
    }
    if (capture != ARRAY_SIZE(expected))
        return 3;
    for (i = 0; i < ARRAY_SIZE(fallback); i++) {
        struct v4l2_pix_format req = {.pixelformat=fallback[i]};
        if (select_capture_format(&req) || req.pixelformat != V4L2_PIX_FMT_YUV420)
            return 4;
    }
    puts("PASS: nine other capture formats unchanged; four unsupported requests use YU12");
    return 0;
}
"""

with tempfile.TemporaryDirectory(prefix="mipad2-atomisp-packed-format-") as temp:
    test, binary = Path(temp) / "probe.c", Path(temp) / "probe"
    test.write_text(code)
    cc = shlex.split(os.environ.get("CC", "cc"))
    subprocess.run([*cc, "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-I", str(pci),
                    str(test), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
