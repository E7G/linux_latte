#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Exercise the actual AtomISP lookup code with a synthetic sensor handler."""

import os
from pathlib import Path
import shlex
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
driver = (root / "drivers/staging/media/atomisp/pci/atomisp_ioctl.c").read_text()
table = driver.split("static const struct v4l2_query_ext_ctrl ci_v4l2_controls[]", 1)[1]
table = table.split("static const u32 ctrls_num = ARRAY_SIZE(ci_v4l2_controls);", 1)[0]
query = driver.split("static int atomisp_query_control(", 1)[1]
query = query.split("static int atomisp_query_ext_ctrl(", 1)[0]
program = r"""
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <linux/videodev2.h>

typedef uint32_t u32;
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define V4L2_CID_ATOMISP_BAD_PIXEL_DETECTION (V4L2_CID_PRIVATE_BASE + 0)
#define V4L2_CID_ATOMISP_POSTPROCESS_GDC_CAC (V4L2_CID_PRIVATE_BASE + 1)
#define V4L2_CID_ATOMISP_VIDEO_STABLIZATION (V4L2_CID_PRIVATE_BASE + 2)
#define V4L2_CID_ATOMISP_FIXED_PATTERN_NR (V4L2_CID_PRIVATE_BASE + 3)
#define V4L2_CID_ATOMISP_FALSE_COLOR_CORRECTION (V4L2_CID_PRIVATE_BASE + 4)
#define V4L2_CID_ATOMISP_LOW_LIGHT (V4L2_CID_PRIVATE_BASE + 5)

struct sensor_controls {
	int red_default, blue_default;
	u32 red_flags, blue_flags, blue_type, blue_dims;
	int query_error;
};
struct sensor { const struct sensor_controls *ctrl_handler; };
struct atomisp_device { struct { struct sensor *sensor; } inputs[2]; };
struct atomisp_sub_device { struct atomisp_device *isp; unsigned input_curr; };

static int v4l2_query_ext_ctrl(const struct sensor_controls *sensor,
			       struct v4l2_query_ext_ctrl *q)
{
	int red = q->id == V4L2_CID_RED_BALANCE;

	if (!red && q->id != V4L2_CID_BLUE_BALANCE)
		return -EINVAL;
	if (sensor->query_error)
		return sensor->query_error;
	*q = (struct v4l2_query_ext_ctrl) {
		.id = q->id, .name = "Sensor gain", .minimum = 256, .maximum = 4095,
		.step = 1, .type = red ? V4L2_CTRL_TYPE_INTEGER : sensor->blue_type,
		.default_value = red ? sensor->red_default : sensor->blue_default,
		.flags = red ? sensor->red_flags : sensor->blue_flags,
		.elem_size = 4, .elems = 1, .nr_of_dims = red ? 0 : sensor->blue_dims,
	};
	return 0;
}
"""
program += "static const struct v4l2_query_ext_ctrl ci_v4l2_controls[]" + table
program += "static const u32 ctrls_num = ARRAY_SIZE(ci_v4l2_controls);\n"
program += "static int atomisp_query_control(" + query
program += r"""
static void next(struct atomisp_sub_device *asd, u32 id, u32 expected)
{
	struct v4l2_query_ext_ctrl q = { .id = id }, before = q, direct = { .id = expected };
	int rc = atomisp_query_next_control(asd, &q);

	if (!expected) {
		assert(rc == -EINVAL && !memcmp(&q, &before, sizeof(q)));
		return;
	}
	assert(!rc && q.id == expected);
	assert(!atomisp_query_control(asd, &direct));
	assert(!memcmp(&q, &direct, sizeof(q)));
}

int main(void)
{
	struct sensor_controls front = { 1650, 1633, 0, 0, V4L2_CTRL_TYPE_INTEGER, 0, 0 };
	struct sensor_controls rear = front;
	struct sensor s0 = { &front }, s1 = { &rear };
	struct atomisp_device isp = { .inputs = {{&s0}, {&s1}} };
	struct atomisp_sub_device asd = { .isp = &isp };
	const u32 scalar = V4L2_CTRL_FLAG_NEXT_CTRL;
	const u32 compound = V4L2_CTRL_FLAG_NEXT_COMPOUND;
	const u32 both = scalar | compound;
	const u32 red = V4L2_CID_RED_BALANCE, blue = V4L2_CID_BLUE_BALANCE;
	const u32 color = V4L2_CID_COLORFX;
	struct v4l2_query_ext_ctrl q = {};
	unsigned i;

	rear.red_default = 1270;
	for (i = 0; i < 2; i++) {
		u32 flags = i ? both : scalar;

		next(&asd, flags, red);
		next(&asd, red | flags, blue);
		next(&asd, blue | flags, color);
		next(&asd, color | flags, 0);
	}
	next(&asd, compound, 0);
	next(&asd, (red - 1) | scalar, red);
	next(&asd, (blue + 1) | scalar, color);
	next(&asd, V4L2_CID_PRIVATE_BASE | scalar, 0);

	asd.input_curr = 1;
	q.id = scalar;
	assert(!atomisp_query_next_control(&asd, &q) && q.default_value == 1270);
	assert(q.minimum == 256 && q.maximum == 4095 && q.step == 1);
	rear.red_flags = V4L2_CTRL_FLAG_DISABLED;
	next(&asd, both, blue);
	rear.blue_dims = 1;
	next(&asd, both, color);
	rear.blue_dims = 0;
	rear.blue_flags = V4L2_CTRL_FLAG_HAS_PAYLOAD;
	next(&asd, both, color);
	rear.blue_flags = 0;
	rear.blue_type = V4L2_CTRL_TYPE_INTEGER64;
	next(&asd, both, color);
	rear.blue_type = V4L2_CTRL_TYPE_U8;
	next(&asd, both, color);
	rear.query_error = -EIO;
	q.id = scalar;
	assert(atomisp_query_next_control(&asd, &q) == -EIO && q.id == scalar);
	s1.ctrl_handler = NULL;
	next(&asd, both, color);
	q.id = red;
	assert(atomisp_query_control(&asd, &q) == -ENODEV);
	isp.inputs[1].sensor = NULL;
	next(&asd, both, color);
	q.id = V4L2_CID_ATOMISP_BAD_PIXEL_DETECTION;
	assert(!atomisp_query_control(&asd, &q) && q.elems == 1 && q.elem_size == 4);
	q.id = 1;
	assert(atomisp_query_control(&asd, &q) == -EINVAL && q.flags == V4L2_CTRL_FLAG_DISABLED);
	puts("PASS: AtomISP control NEXT ordering, sensor metadata, filtering and legacy lookup");
}
"""

with tempfile.TemporaryDirectory(prefix="mipad2-control-") as tmp:
    source, binary = Path(tmp) / "test.c", Path(tmp) / "test"
    source.write_text(program, encoding="utf-8")
    subprocess.run(
        shlex.split(os.environ.get("CC", "cc"))
        + ["-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror", str(source), "-o", str(binary)],
        check=True,
    )
    subprocess.run([str(binary)], check=True)
