#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Test the actual sensor timing and bridge enumeration code with TRY stubs."""

import os
import re
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OV = (ROOT / "drivers/media/i2c/ov5693.c").read_text()
T4 = (ROOT / "drivers/media/i2c/t4ka3.c").read_text()
ISP = (ROOT / "drivers/staging/media/atomisp/pci/atomisp_ioctl.c").read_text()


def function(source, name):
    start = re.search(rf"^static (?:bool|int|void|unsigned int) {name}\(", source, re.M)
    return source[start.start():source.index("\n}", start.end()) + 2]


def definitions(source, *names):
    return "\n".join(re.search(rf"^#define {name}[ \t]+(?:[^\n]*\\\n)*[^\n]+",
                               source, re.M)[0] for name in names)


PRELUDE = r"""
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <linux/videodev2.h>
#include <linux/v4l2-mediabus.h>
#include <linux/v4l2-subdev.h>
typedef uint32_t u32;
#define max(a, b) ((a) > (b) ? (a) : (b))
struct v4l2_subdev_state {
	struct v4l2_mbus_framefmt fmt;
	struct v4l2_rect crop;
	int locked;
};
struct ov5693_device { bool mipad2; u32 pixel_rate; };
struct v4l2_subdev {
	struct ov5693_device *ov;
	int (*get_frame_interval_range)(struct v4l2_subdev *, struct v4l2_subdev_state *,
					u32, u32, struct v4l2_frmival_stepwise *);
	int (*enum_frame_interval)(struct v4l2_subdev *, struct v4l2_subdev_state *,
				   struct v4l2_subdev_frame_interval_enum *);
};
struct atomisp_input_subdev {
	struct v4l2_subdev_state *try_sd_state;
	struct v4l2_subdev *sensor;
};
struct atomisp_device { struct atomisp_input_subdev *inputs; };
struct atomisp_sub_device { int input_curr; };
struct atomisp_pipe { struct atomisp_sub_device *asd; };
struct video_device { struct atomisp_device *isp; struct atomisp_pipe *pipe; };
struct file { struct video_device *vdev; };
static struct v4l2_subdev_state *active_state;
static const struct { u32 code; } atomisp_in_fmt_conv[] = {{0x3007}};
static int param_locked;
#define THIS_MODULE (&param_locked)
static void kernel_param_lock(int *p) { assert(!*p); *p = 1; }
static void kernel_param_unlock(int *p) { assert(*p); *p = 0; }
#define video_devdata(f) ((f)->vdev)
#define video_get_drvdata(v) ((v)->isp)
#define atomisp_to_video_pipe(v) ((v)->pipe)
static int tries, try_error;
static void v4l2_subdev_lock_state(struct v4l2_subdev_state *s)
{
	assert(!s->locked);
	s->locked = 1;
}
static void v4l2_subdev_unlock_state(struct v4l2_subdev_state *s)
{
	assert(s->locked);
	s->locked = 0;
}
static struct v4l2_subdev_state *
v4l2_subdev_lock_and_get_active_state(struct v4l2_subdev *sd)
{
	v4l2_subdev_lock_state(active_state);
	return active_state;
}
static struct ov5693_device *to_ov5693_sensor(struct v4l2_subdev *sd)
{
	return sd->ov;
}
static struct v4l2_mbus_framefmt *
v4l2_subdev_state_get_format(struct v4l2_subdev_state *s, u32 pad)
{
	assert(s->locked && !pad);
	return &s->fmt;
}
static struct v4l2_rect *
v4l2_subdev_state_get_crop(struct v4l2_subdev_state *s, u32 pad)
{
	assert(s->locked && !pad);
	return &s->crop;
}
static int atomisp_try_fmt(struct atomisp_device *isp, struct v4l2_pix_format *pix,
			   void *f, void *s)
{
	struct v4l2_subdev_state *state = isp->inputs[0].try_sd_state;

	assert(!f && !s && !state->locked);
	tries++;
	if (try_error)
		return try_error;
	if (pix->pixelformat != V4L2_PIX_FMT_NV12)
		pix->pixelformat = V4L2_PIX_FMT_NV12;
	pix->width &= ~1u;
	pix->height &= ~1u;
	state->fmt.width = pix->width + 16;
	state->fmt.height = pix->height + 16;
	state->crop.width = state->fmt.width;
	state->crop.height = state->fmt.height;
	return 0;
}
#define v4l2_subdev_call(sd, op, fn, ...) (sd)->fn(sd, __VA_ARGS__)
#define v4l2_subdev_has_op(sd, op, fn) ((sd)->fn != NULL)
"""

TEST = r"""
static int legacy_enum(struct v4l2_subdev *sd, struct v4l2_subdev_state *state,
		       struct v4l2_subdev_frame_interval_enum *fie)
{
	assert(state == active_state && state->locked);
	assert(fie->code == 0x3007 && fie->which == V4L2_SUBDEV_FORMAT_ACTIVE);
	fie->interval = (struct v4l2_fract) {1, 15};
	return 0;
}

static void verify(const struct v4l2_frmival_stepwise *ival,
		   u32 ppl, u32 rate, u32 min, u32 max)
{
	assert(ival->min.numerator == ppl * min && ival->min.denominator == rate);
	assert(ival->max.numerator == ppl * max && ival->max.denominator == rate);
	assert(ival->step.numerator == ppl && ival->step.denominator == rate);
}

int main(void)
{
	struct ov5693_device ov = {.mipad2 = true, .pixel_rate = 160000000};
	struct v4l2_subdev front = {
		.ov = &ov, .get_frame_interval_range = ov5693_get_frame_interval_range,
	};
	struct v4l2_subdev rear = {
		.get_frame_interval_range = t4ka3_get_frame_interval_range,
	};
	struct v4l2_subdev legacy = {.enum_frame_interval = legacy_enum};
	struct v4l2_subdev_state state = {0};
	struct v4l2_frmival_stepwise range = {0};
	struct atomisp_input_subdev input = {&state, &front};
	struct atomisp_device isp = {&input};
	struct atomisp_sub_device asd = {0};
	struct atomisp_pipe pipe = {&asd};
	struct video_device vdev = {&isp, &pipe};
	struct file file = {&vdev};
	struct v4l2_frmivalenum fival = {
		.pixel_format = V4L2_PIX_FMT_NV12, .width = 1920, .height = 1080,
	};
	unsigned int checked = 0;

	v4l2_subdev_lock_state(&state);
	assert(front.get_frame_interval_range(&front, &state, 0, 0, &range) == -EINVAL);
	assert(rear.get_frame_interval_range(&rear, &state, 1, 0, &range) == -EINVAL);
	assert(rear.get_frame_interval_range(&rear, &state, 0, 1, &range) == -EINVAL);
	assert(front.get_frame_interval_range(&front, NULL, 0, 0, &range) == -EINVAL);
	for (u32 h = 2; h <= 2460; h += 2)
	for (u32 mask = 0; mask < 4; mask++) {
		bool both = (mask == 3);
		struct v4l2_subdev_state saved;
		u32 rear_min = both ? h * 2 + 4 : h + 4;

		state.fmt = (struct v4l2_mbus_framefmt) {.width = 640, .height = h};
		state.crop = (struct v4l2_rect) {
			.width = 640 * ((mask & 1) ? 2 : 1),
			.height = h * ((mask & 2) ? 2 : 1),
		};
		saved = state;
		assert(!front.get_frame_interval_range(&front, &state, 0, 0, &range));
		verify(&range, 2688, 160000000, h + (both ? 16 : 24), 65535);
		ov.mipad2 = false;
		ov.pixel_rate = 167680000;
		assert(!front.get_frame_interval_range(&front, &state, 0, 0, &range));
		verify(&range, 2688, 167680000, h + 4, 65535);
		ov.mipad2 = true;
		ov.pixel_rate = 160000000;
		assert(!rear.get_frame_interval_range(&rear, &state, 0, 0, &range));
		verify(&range, 3440, 257174400, max(rear_min, 7u), 65535);
		assert(!memcmp(&saved, &state, sizeof(state)));
		checked += 3;
	}
	v4l2_subdev_unlock_state(&state);

	assert(!atomisp_enum_stepwise_frameintervals(&isp, &input, &fival));
	assert(fival.type == V4L2_FRMIVAL_TYPE_STEPWISE);
	verify(&fival.stepwise, 2688, 160000000, 1120, 65535);
	input.sensor = &rear;
	assert(!atomisp_enum_stepwise_frameintervals(&isp, &input, &fival));
	verify(&fival.stepwise, 3440, 257174400, 1100, 65535);
	assert(tries == 2 && !state.locked);
	fival.index = 1;
	assert(atomisp_enum_stepwise_frameintervals(&isp, &input, &fival) == -EINVAL);
	fival.index = 0;
	fival.height = 0;
	assert(atomisp_enum_stepwise_frameintervals(&isp, &input, &fival) == -EINVAL);
	assert(tries == 2);
	fival.height = 1079;
	assert(atomisp_enum_stepwise_frameintervals(&isp, &input, &fival) == -EINVAL);
	fival.height = 1080;
	fival.pixel_format = V4L2_PIX_FMT_SBGGR10;
	assert(atomisp_enum_stepwise_frameintervals(&isp, &input, &fival) == -EINVAL);
	fival.pixel_format = V4L2_PIX_FMT_NV12;
	try_error = -EIO;
	assert(atomisp_enum_stepwise_frameintervals(&isp, &input, &fival) == -EIO);
	assert(tries == 5 && !state.locked);
	try_error = 0;
	assert(atomisp_enum_frameintervals(&file, NULL, &fival) == -ENOTTY);
	assert(tries == 5 && !param_locked);
	stepwise_frame_intervals = true;
	assert(!atomisp_enum_frameintervals(&file, NULL, &fival));
	verify(&fival.stepwise, 3440, 257174400, 1100, 65535);
	stepwise_frame_intervals = false;
	assert(atomisp_enum_frameintervals(&file, NULL, &fival) == -ENOTTY);
	assert(tries == 6 && !state.locked && !param_locked);
	input.sensor = &legacy;
	active_state = &state;
	assert(!atomisp_enum_frameintervals(&file, NULL, &fival));
	assert(fival.type == V4L2_FRMIVAL_TYPE_DISCRETE && fival.discrete.numerator == 1 &&
	       fival.discrete.denominator == 15 && !state.locked);
	printf("PASS: %u geometry/timing cases, exact endpoints, gate and legacy dispatch\n", checked);
}
"""

parts = [
    PRELUDE,
    definitions(OV, "OV5693_FIXED_PPL", "OV5693_TIMING_MIN_VTS",
                "OV5693_TIMING_MAX_VTS", "OV5693_MIPAD2_VBLANK_BINNED",
                "OV5693_MIPAD2_VBLANK_UNBINNED"),
    definitions(T4, "T4KA3_PIXELS_PER_LINE", "T4KA3_LINES_PER_FRAME_30FPS",
                "T4KA3_FPS", "T4KA3_PIXEL_RATE", "T4KA3_MIN_VBLANK",
                "T4KA3_MAX_VBLANK", "T4KA3_COARSE_INTEGRATION_TIME_MARGIN",
                "T4KA3_COARSE_INTEGRATION_TIME_MIN"),
    function(OV, "ov5693_min_vblank_for_mode"),
    function(OV, "ov5693_get_frame_interval_range"),
    function(T4, "t4ka3_binning"),
    function(T4, "t4ka3_get_vblank_limits"),
    function(T4, "t4ka3_get_frame_interval_range"),
    function(ISP, "atomisp_enum_stepwise_frameintervals"),
    re.search(r"^static bool stepwise_frame_intervals.*;$", ISP, re.M)[0],
    function(ISP, "atomisp_stepwise_frame_intervals_enabled"),
    function(ISP, "atomisp_enum_frameintervals"),
    TEST,
]
with tempfile.TemporaryDirectory(prefix="mipad2-v4l2-intervals-") as temp:
    source, exe = Path(temp) / "test.c", Path(temp) / "test"
    source.write_text("\n".join(parts))
    subprocess.run([os.environ.get("CC", "gcc"), "-std=gnu11", "-Wall", "-Wextra",
                    "-Werror", "-Wno-unused-parameter", "-fsanitize=undefined",
                    "-fno-sanitize-recover=all", str(source), "-o", str(exe)],
                   check=True)
    subprocess.run([str(exe)], check=True)
