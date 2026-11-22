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
sensor_ids = driver.split("static const u32 atomisp_sensor_ctrl_ids[]", 1)[1]
sensor_ids = sensor_ids.split("static const struct v4l2_query_ext_ctrl", 1)[0]
routing = driver.split("static bool atomisp_is_sensor_ctrl(", 1)[1]
routing = routing.split("static int atomisp_query_control(", 1)[0]
query = driver.split("static int atomisp_query_control(", 1)[1]
query = query.split("static int atomisp_query_ext_ctrl(", 1)[0]
limits = driver.split("static int atomisp_g_ext_limits(", 1)[1]
limits = limits.split("/* This ioctl allows the application to get multiple controls", 1)[0]
program = r"""
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <linux/videodev2.h>

typedef uint32_t u32;
typedef int32_t s32;
#ifndef V4L2_CTRL_WHICH_MIN_VAL
#define V4L2_CTRL_WHICH_MIN_VAL 0x0f020000
#define V4L2_CTRL_WHICH_MAX_VAL 0x0f030000
#endif
#ifndef V4L2_CTRL_FLAG_HAS_WHICH_MIN_MAX
#define V4L2_CTRL_FLAG_HAS_WHICH_MIN_MAX 0x1000
#endif
#define GFP_KERNEL 0
static bool fail_alloc;
#define kcalloc(n, size, flags) (fail_alloc ? NULL : calloc((n), (size)))
#define kfree(p) free(p)
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define V4L2_CID_ATOMISP_BAD_PIXEL_DETECTION (V4L2_CID_PRIVATE_BASE + 0)
#define V4L2_CID_ATOMISP_POSTPROCESS_GDC_CAC (V4L2_CID_PRIVATE_BASE + 1)
#define V4L2_CID_ATOMISP_VIDEO_STABLIZATION (V4L2_CID_PRIVATE_BASE + 2)
#define V4L2_CID_ATOMISP_FIXED_PATTERN_NR (V4L2_CID_PRIVATE_BASE + 3)
#define V4L2_CID_ATOMISP_FALSE_COLOR_CORRECTION (V4L2_CID_PRIVATE_BASE + 4)
#define V4L2_CID_ATOMISP_LOW_LIGHT (V4L2_CID_PRIVATE_BASE + 5)

struct v4l2_ctrl_handler {
	int red_default, blue_default;
	u32 red_flags, blue_flags, blue_type, blue_dims;
	int query_error;
	bool manual;
	int exposure, analogue_gain;
	int get_error, set_error;
};
struct v4l2_subdev { struct v4l2_ctrl_handler *ctrl_handler; };
struct atomisp_device { struct { struct v4l2_subdev *sensor; } inputs[2]; };
struct atomisp_sub_device { struct atomisp_device *isp; unsigned input_curr; };
struct video_device { struct atomisp_sub_device *asd; };
struct file { struct video_device *vdev; };
#define video_devdata(file) ((file)->vdev)
#define atomisp_to_video_pipe(vdev) (vdev)

#define FAKE_ISP_CTRL(name) \
	static int atomisp_##name(struct atomisp_sub_device *asd, int set, __s32 *value) \
	{ return -ENOSYS; }
FAKE_ISP_CTRL(color_effect)
FAKE_ISP_CTRL(bad_pixel)
FAKE_ISP_CTRL(gdc_cac)
FAKE_ISP_CTRL(video_stable)
FAKE_ISP_CTRL(fixed_pattern)
FAKE_ISP_CTRL(false_color)
FAKE_ISP_CTRL(low_light)

static int v4l2_g_ctrl(struct v4l2_ctrl_handler *hdl, struct v4l2_control *c)
{
	if (hdl->get_error)
		return hdl->get_error;
	switch (c->id) {
	case V4L2_CID_EXPOSURE:
		c->value = hdl->exposure;
		return 0;
	case V4L2_CID_ANALOGUE_GAIN:
		c->value = hdl->analogue_gain;
		return 0;
	default:
		return -EINVAL;
	}
}

static int v4l2_s_ctrl(void *fh, struct v4l2_ctrl_handler *hdl,
		       struct v4l2_control *c)
{
	if (hdl->set_error)
		return hdl->set_error;
	switch (c->id) {
	case V4L2_CID_EXPOSURE:
		hdl->exposure = c->value;
		return 0;
	case V4L2_CID_ANALOGUE_GAIN:
		hdl->analogue_gain = c->value;
		return 0;
	default:
		return -EINVAL;
	}
}

static int v4l2_query_ext_ctrl(const struct v4l2_ctrl_handler *sensor,
			       struct v4l2_query_ext_ctrl *q)
{
	int red = q->id == V4L2_CID_RED_BALANCE;

	if (sensor->manual && (q->id == V4L2_CID_EXPOSURE ||
			      q->id == V4L2_CID_ANALOGUE_GAIN)) {
		bool exposure = q->id == V4L2_CID_EXPOSURE;

		*q = (struct v4l2_query_ext_ctrl) {
			.id = q->id, .name = "Manual sensor control",
			.minimum = exposure ? 1 : sensor->analogue_gain,
			.maximum = exposure ? sensor->exposure : 2047,
			.step = 1, .default_value = exposure ? sensor->exposure : sensor->analogue_gain,
			.type = V4L2_CTRL_TYPE_INTEGER, .elem_size = 4, .elems = 1,
		};
		return 0;
	}
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
program += "static const u32 atomisp_sensor_ctrl_ids[]" + sensor_ids
program += "static const struct v4l2_query_ext_ctrl ci_v4l2_controls[]" + table
program += "static const u32 ctrls_num = ARRAY_SIZE(ci_v4l2_controls);\n"
program += "static bool atomisp_is_sensor_ctrl(" + routing
program += "static int atomisp_query_control(" + query
program += "static int atomisp_g_ext_limits(" + limits
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
	struct v4l2_ctrl_handler front = {
		.red_default = 1650, .blue_default = 1633,
		.blue_type = V4L2_CTRL_TYPE_INTEGER,
	};
	struct v4l2_ctrl_handler rear = front;
	struct v4l2_subdev s0 = { &front }, s1 = { &rear };
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
	/* Now both real device shapes expose manual exposure and gain. */
	isp.inputs[1].sensor = &s1;
	s1.ctrl_handler = &rear;
	rear.query_error = 0;
	front.manual = rear.manual = true;
	front.exposure = 1976;
	rear.exposure = 2486;
	front.analogue_gain = 8;
	rear.analogue_gain = 128;
	for (i = 0; i < 2; i++) {
		struct video_device vdev = { .asd = &asd };
		struct file file = { .vdev = &vdev };
		struct v4l2_ctrl_handler *current = i ? &rear : &front;
		struct v4l2_ctrl_handler *other = i ? &front : &rear;
		int prior = other->exposure;
		struct v4l2_control ctrl = { .id = V4L2_CID_EXPOSURE };

		asd.input_curr = i;
		next(&asd, (V4L2_CID_EXPOSURE - 1) | both, V4L2_CID_EXPOSURE);
		next(&asd, color | scalar, V4L2_CID_ANALOGUE_GAIN);
		next(&asd, V4L2_CID_ANALOGUE_GAIN | both, 0);
		q.id = ctrl.id;
		assert(!atomisp_query_control(&asd, &q) && q.maximum == current->exposure);
		assert(!atomisp_g_ctrl(&file, NULL, &ctrl) && ctrl.value == current->exposure);
		ctrl.value--;
		assert(!atomisp_s_ctrl(&file, NULL, &ctrl) && current->exposure == ctrl.value);
		assert(other->exposure == prior);

		ctrl.id = V4L2_CID_ANALOGUE_GAIN;
		q.id = ctrl.id;
		assert(!atomisp_query_control(&asd, &q) && q.default_value == current->analogue_gain);
		assert(!atomisp_g_ctrl(&file, NULL, &ctrl) && ctrl.value == current->analogue_gain);
		current->get_error = -ENODATA;
		assert(atomisp_g_ctrl(&file, NULL, &ctrl) == -ENODATA);
		current->set_error = -ERANGE;
		assert(atomisp_s_ctrl(&file, NULL, &ctrl) == -ERANGE);
		ctrl.id = V4L2_CID_DIGITAL_GAIN;
		assert(atomisp_g_ctrl(&file, NULL, &ctrl) == -EINVAL);
	}
	{
		struct v4l2_ext_control v[2] = {
			{.id = red, .value = 17}, {.id = color, .value = 19},
		};
		struct v4l2_ext_controls c = {
			.controls = v, .count = 2, .which = V4L2_CTRL_WHICH_MIN_VAL,
		};

		asd.input_curr = 0;
		front.red_flags = V4L2_CTRL_FLAG_HAS_WHICH_MIN_MAX;
		assert(atomisp_g_ext_limits(&asd, &c) == -EINVAL && c.error_idx == 1);
		assert(v[0].value == 17 && v[1].value == 19);
		c.which = V4L2_CTRL_WHICH_DEF_VAL;
		assert(!atomisp_g_ext_limits(&asd, &c) && c.error_idx == 2);
		assert(v[0].value == front.red_default && v[1].value == 0);
		asd.input_curr = 1;
		rear.red_flags = V4L2_CTRL_FLAG_HAS_WHICH_MIN_MAX;
		assert(!atomisp_g_ext_limits(&asd, &c) && v[0].value == rear.red_default);
		c.count = 1;
		c.which = V4L2_CTRL_WHICH_MIN_VAL;
		assert(!atomisp_g_ext_limits(&asd, &c) && v[0].value == 256);
		c.which = V4L2_CTRL_WHICH_MAX_VAL;
		assert(!atomisp_g_ext_limits(&asd, &c) && v[0].value == 4095);
		rear.red_flags |= V4L2_CTRL_FLAG_WRITE_ONLY;
		assert(atomisp_g_ext_limits(&asd, &c) == -EACCES && c.error_idx == 0);
		rear.red_flags = V4L2_CTRL_FLAG_HAS_WHICH_MIN_MAX | V4L2_CTRL_FLAG_DISABLED;
		assert(atomisp_g_ext_limits(&asd, &c) == -EINVAL && c.error_idx == 0);
		fail_alloc = true;
		assert(atomisp_g_ext_limits(&asd, &c) == -ENOMEM && c.error_idx == 1);
		c.count = 0;
		assert(!atomisp_g_ext_limits(&asd, &c) && c.error_idx == 0);
		fail_alloc = false;
	}
	puts("PASS: AtomISP NEXT, active-sensor get/set, and atomic scalar limits queries");
}
"""

with tempfile.TemporaryDirectory(prefix="mipad2-control-") as tmp:
    source, binary = Path(tmp) / "test.c", Path(tmp) / "test"
    source.write_text(program, encoding="utf-8")
    subprocess.run(
        shlex.split(os.environ.get("CC", "cc"))
        + ["-std=gnu11", "-O2", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter", str(source), "-o", str(binary)],
        check=True,
    )
    subprocess.run([str(binary)], check=True)
