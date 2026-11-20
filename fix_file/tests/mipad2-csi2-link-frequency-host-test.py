#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Exercise the AtomISP CSI-2 frequency and timing code without hardware."""

import os
import pathlib
import re
import subprocess
import tempfile


ROOT = pathlib.Path(__file__).resolve().parents[2]
PCI = ROOT / "drivers/staging/media/atomisp/pci"
csi = (PCI / "atomisp_csi2.c").read_text()
css = (PCI / "atomisp_compat_css20.c").read_text()
cmd = (PCI / "atomisp_cmd.c").read_text()
port = (PCI / "ia_css_input_port.h").read_text()
csi_helpers = csi[csi.index("int atomisp_csi2_get_link_freq("):
                  csi.index("static void atomisp_csi2_configure_isp2401(")]
css_helper = css[css.index("static unsigned int atomisp_css_rxcount("):
                 css.index("int atomisp_css_input_configure_port(")]
default = re.search(r"^#define IA_CSS_DEFAULT_PORT_RXCOUNT .*", port, re.M)[0]
assert "mipi_freq = atomisp_csi2_get_link_freq(input);" in cmd
assert "mipi_freq = atomisp_csi2_get_link_freq(input);" in csi
assert "source.port.rxcount = rxcount;" in css
assert "if (mipi_freq)" not in css[css.index("int atomisp_css_input_configure_port("):
                                  css.index("static void atomisp_css_stop_internal(")]
for source in (cmd, csi):
    assert ".id = V4L2_CID_LINK_FREQ;" not in source

PRELUDE = r"""
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
typedef int64_t s64;
#define SENSOR_ISP_PAD_SOURCE 1
#define V4L2_CID_LINK_FREQ 0x009f0901
#define V4L2_CTRL_TYPE_INTEGER 1
#define V4L2_CTRL_TYPE_INTEGER_MENU 9
#define min(a, b) ((a) < (b) ? (a) : (b))
#define max(a, b) ((a) > (b) ? (a) : (b))
struct media_pad { s64 freq; };
struct v4l2_ctrl { unsigned int type; int val; };
struct v4l2_subdev {
	struct { struct media_pad *pads; unsigned int num_pads; } entity;
	struct v4l2_ctrl *ctrl_handler;
};
struct atomisp_input_subdev {
	struct v4l2_subdev *csi_remote_source, *sensor_isp;
};
static int lookups;
static s64 v4l2_get_link_freq(const struct media_pad *pad, unsigned int mul,
			     unsigned int div)
{
	assert(mul == 0 && div == 0); /* no pixel-array rate fallback */
	lookups++;
	return pad->freq;
}
static struct v4l2_ctrl *v4l2_ctrl_find(struct v4l2_ctrl *handler, unsigned int id)
{
	assert(id == V4L2_CID_LINK_FREQ);
	return handler;
}
static int v4l2_ctrl_g_ctrl(struct v4l2_ctrl *ctrl)
{
	assert(ctrl->type == V4L2_CTRL_TYPE_INTEGER);
	return ctrl->val;
}
"""

TEST = r"""
int main(void)
{
	struct media_pad pads[] = {{419200000}, {321468000}};
	struct v4l2_subdev transmitter = {.entity = {pads, 2}};
	struct atomisp_input_subdev input = {.csi_remote_source = &transmitter};
	const short int clock[] = {95, -8}, data[] = {85, -2};
	static const struct {
		s64 reported;
		int frequency, clk_settle, dat_settle;
		unsigned int rxcount;
	} cases[] = {
		{419200000, 419200000, 1368, 1322, 0x07070707},
		{321468000, 321468000, 1321, 1311, 0x05050505},
		{-ENOENT, 0, 0x480, 0x480, 0x04040404},
		{-EIO, 0, 0x480, 0x480, 0x04040404},
		{0, 0, 0x480, 0x480, 0x04040404},
		{1, 1, 0x480, 0x480, 0},
		{64, 64, 0, 0, 0},
		{1000000, 1000000, 0, 0, 0},
		{58879999, 58879999, 434, 1089, 0},
		{105984000, 105984000, 917, 1210, 0x01010101},
		{INT_MAX, INT_MAX, 1491, 1353, 0x2c2c2c2c},
		{(s64)INT_MAX + 1, 0, 0x480, 0x480, 0x04040404},
	};
	assert(atomisp_csi2_get_link_freq(&input) == 419200000);
	input.sensor_isp = &transmitter;
	assert(atomisp_csi2_get_link_freq(&input) == 321468000);
	transmitter.entity.num_pads = 1;
	assert(atomisp_csi2_get_link_freq(&input) == 0);
	input.csi_remote_source = NULL;
	assert(atomisp_csi2_get_link_freq(&input) == 0 && lookups == 2);
	input.sensor_isp = NULL;
	input.csi_remote_source = &transmitter;
	struct v4l2_ctrl legacy = {.type = V4L2_CTRL_TYPE_INTEGER, .val = 360000000};
	transmitter.ctrl_handler = &legacy;
	pads[0].freq = -ENOENT;
	assert(atomisp_csi2_get_link_freq(&input) == legacy.val);
	pads[0].freq = -EIO;
	assert(atomisp_csi2_get_link_freq(&input) == 0);
	pads[0].freq = 419200000;
	assert(atomisp_csi2_get_link_freq(&input) == 419200000);
	pads[0].freq = -ENOENT;
	legacy.type = V4L2_CTRL_TYPE_INTEGER_MENU;
	assert(atomisp_csi2_get_link_freq(&input) == 0);
	for (unsigned int i = 0; i < sizeof(cases) / sizeof(*cases); i++) {
		pads[0].freq = cases[i].reported;
		int freq = atomisp_csi2_get_link_freq(&input);
		assert(freq == cases[i].frequency);
		assert(atomisp_csi2_configure_calc(clock, freq, 0x480) ==
		       cases[i].clk_settle);
		assert(atomisp_csi2_configure_calc(data, freq, 0x480) ==
		       cases[i].dat_settle);
		assert(atomisp_css_rxcount(freq) == cases[i].rxcount);
	}
	puts("PASS: transmitter pad, menu values, both Mi Pad 2 timing profiles, fallback and bounds");
}
"""

with tempfile.TemporaryDirectory(prefix="mipad2-csi2-timing-") as tmp:
    path = pathlib.Path(tmp)
    source = path / "test.c"
    exe = path / "test"
    source.write_text("\n".join((PRELUDE, default, csi_helpers, css_helper, TEST)))
    subprocess.run(
        [os.environ.get("CC", "cc"), "-std=gnu11", "-Wall", "-Wextra", "-Werror",
         "-fsanitize=undefined", "-fno-sanitize-recover=all", str(source), "-o",
         str(exe)],
        check=True,
    )
    subprocess.run([exe], check=True)
