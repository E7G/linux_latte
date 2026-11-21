#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Exercise the production AtomISP capture format readback helper."""
from pathlib import Path
import re
import shlex
import os
import subprocess
import tempfile


path = Path(__file__).resolve().parents[2] / "drivers/staging/media/atomisp/pci/atomisp_cmd.c"
source = path.read_text()
match = re.search(r"^static void atomisp_fill_pix_format\(.*?^\}", source, re.M | re.S)
if not match:
    raise SystemExit("AtomISP format helper not found")

code = r"""
#include <stdbool.h>
#include <stdint.h>
#include <linux/videodev2.h>
#include <stdio.h>

typedef uint32_t u32;
struct atomisp_format_bridge {
    u32 pixelformat, depth, sh_fmt;
    bool planar;
};
static u32 ia_css_frame_pad_width(u32 width, u32 format)
{
    (void)format;
    return (width + 63) & ~63U;
}
#define BITS_TO_BYTES(bits) (((bits) + 7) / 8)
#define PAGE_ALIGN(bytes) (((bytes) + 4095) & ~4095U)
""" + match[0] + r"""
int main(void)
{
    static const struct {
        struct atomisp_format_bridge fmt;
        u32 stride, capacity;
    } layouts[] = {
        {{.pixelformat=V4L2_PIX_FMT_NV12, .depth=12, .planar=true}, 1280, 1384448},
        {{.pixelformat=V4L2_PIX_FMT_YUV420, .depth=12, .planar=true}, 1280, 1384448},
        {{.pixelformat=V4L2_PIX_FMT_YUYV, .depth=16}, 2560, 1843200},
        {{.pixelformat=V4L2_PIX_FMT_RGB24, .depth=24}, 3840, 2764800},
    };
    const u32 fields[] = {V4L2_FIELD_ANY, V4L2_FIELD_NONE, V4L2_FIELD_INTERLACED,
                          V4L2_FIELD_ALTERNATE};
    const u32 quant[] = {V4L2_QUANTIZATION_DEFAULT, V4L2_QUANTIZATION_FULL_RANGE,
                         V4L2_QUANTIZATION_LIM_RANGE};
    unsigned cases = 0;
    for (unsigned l = 0; l < sizeof(layouts) / sizeof(layouts[0]); l++) {
        for (unsigned i = 0; i < sizeof(fields) / sizeof(fields[0]); i++) {
            for (unsigned j = 0; j < sizeof(quant) / sizeof(quant[0]); j++) {
                struct v4l2_pix_format pix = {
                    .field = fields[i],
                    .priv = V4L2_PIX_FMT_PRIV_MAGIC,
                    .flags = i ? V4L2_PIX_FMT_FLAG_SET_CSC |
                                 V4L2_PIX_FMT_FLAG_PREMUL_ALPHA : 0,
                    .colorspace = V4L2_COLORSPACE_SMPTE170M,
                    .ycbcr_enc = V4L2_YCBCR_ENC_601,
                    .quantization = quant[j],
                    .xfer_func = V4L2_XFER_FUNC_SRGB,
                };
                atomisp_fill_pix_format(&pix, 1278, 720, &layouts[l].fmt);
                if (pix.width != 1278 || pix.height != 720 ||
                    pix.pixelformat != layouts[l].fmt.pixelformat ||
                    pix.bytesperline != layouts[l].stride ||
                    pix.sizeimage != layouts[l].capacity ||
                    pix.priv != V4L2_PIX_FMT_PRIV_MAGIC ||
                    pix.field != V4L2_FIELD_NONE || pix.flags ||
                    pix.colorspace != V4L2_COLORSPACE_REC709 ||
                    pix.ycbcr_enc != V4L2_YCBCR_ENC_709 ||
                    pix.xfer_func != V4L2_XFER_FUNC_709 ||
                    pix.quantization != V4L2_QUANTIZATION_DEFAULT) {
                    fprintf(stderr, "layout=%u input=%u/%u output field=%u flags=%u q=%u\n",
                            l, fields[i], quant[j], pix.field, pix.flags, pix.quantization);
                    return 1;
                }
                cases++;
            }
        }
    }
    printf("PASS: %u progressive capture metadata cases\n", cases);
    return 0;
}
"""

with tempfile.TemporaryDirectory(prefix="mipad2-atomisp-format-") as temp:
    test, binary = Path(temp) / "probe.c", Path(temp) / "probe"
    test.write_text(code)
    cc = shlex.split(os.environ.get("CC", "cc"))
    subprocess.run([*cc, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                    str(test), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
