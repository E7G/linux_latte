// SPDX-License-Identifier: GPL-2.0
/* Standard V4L2 request validation smoke test, not a streaming test. */
#include <errno.h>
#include <fcntl.h>
#include <linux/videodev2.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

static int read_capture(int fd, int *value)
{
	struct v4l2_control c = { .id = V4L2_CID_RED_BALANCE };

	if (ioctl(fd, VIDIOC_G_CTRL, &c) < 0)
		return -1;
	*value = c.value;
	return 0;
}

static int read_sensor(int fd, int *value)
{
	struct v4l2_ext_control one = { .id = V4L2_CID_RED_BALANCE };
	struct v4l2_ext_controls c = {
		.which = V4L2_CTRL_WHICH_CUR_VAL, .count = 1, .controls = &one,
	};

	if (ioctl(fd, VIDIOC_G_EXT_CTRLS, &c) < 0)
		return -1;
	*value = one.value;
	return 0;
}

static int check_batch(int capture, int sensor, int baseline)
{
	struct v4l2_query_ext_ctrl q = { .id = V4L2_CID_RED_BALANCE };
	struct v4l2_query_ext_ctrl absent = { .id = V4L2_CID_AUTO_WHITE_BALANCE };
	struct v4l2_ext_control items[2] = {
		{ .id = V4L2_CID_RED_BALANCE },
		{ .id = V4L2_CID_AUTO_WHITE_BALANCE, .value = 1 },
	};
	struct v4l2_ext_controls group = {
		.which = V4L2_CTRL_WHICH_CUR_VAL, .count = 2, .controls = items,
	};
	struct v4l2_control undo = { .id = V4L2_CID_RED_BALANCE };
	int before, a, b, ret, err, actual;
	unsigned int failed_index;

	if (ioctl(capture, VIDIOC_QUERY_EXT_CTRL, &q) < 0 ||
	    q.type != V4L2_CTRL_TYPE_INTEGER || q.step != 1 || q.minimum != 256 ||
	    q.maximum != 4095 || read_capture(capture, &before) ||
	    read_sensor(sensor, &a) || a != before || before < q.minimum ||
	    before > q.maximum || ioctl(capture, VIDIOC_QUERY_EXT_CTRL, &absent) >= 0 ||
	    errno != EINVAL)
		return 1;

	items[0].value = before > q.minimum ? before - 1 : before + 1;
	if (!baseline) {
		struct v4l2_ext_controls try_one = group;

		try_one.count = 1;
		if (ioctl(capture, VIDIOC_TRY_EXT_CTRLS, &try_one) < 0 ||
		    read_sensor(sensor, &a) || a != before)
			return 1;
		if (ioctl(capture, VIDIOC_TRY_EXT_CTRLS, &group) >= 0 ||
		    errno != EINVAL || read_sensor(sensor, &a) || a != before)
			return 1;
	}
	ret = ioctl(capture, VIDIOC_S_EXT_CTRLS, &group);
	err = errno;
	failed_index = group.error_idx;
	actual = !read_capture(capture, &a) && !read_sensor(sensor, &b) && a == b;
	undo.value = before;
	if (ioctl(capture, VIDIOC_S_CTRL, &undo) < 0 || read_capture(capture, &b) ||
	    b != before || read_sensor(sensor, &b) || b != before) {
		fputs("Failed to restore original gain\n", stderr);
		return 1;
	}

	if (!actual || ret != -1 || err != EINVAL)
		return 1;
	printf("rejected batch: errno=%d error_idx=%u gain_before=%d gain_after=%d\n",
	       err, failed_index, before, a);
	printf("restored gain=%d\n", before);
	if (a == before) {
		puts("PASS: no partial sensor write");
		return 0;
	}
	puts("BASELINE: rejected batch partially changed the active sensor");
	return baseline && a == items[0].value ? 3 : 1;
}

int main(int argc, char **argv)
{
	int baseline = argc == 4 && !strcmp(argv[3], "--baseline");
	int capture, sensor, result;

	if (argc != 3 && !baseline)
		return 2;
	capture = open(argv[1], O_RDWR | O_NONBLOCK);
	sensor = open(argv[2], O_RDONLY | O_NONBLOCK);
	if (capture < 0 || sensor < 0)
		return 1;
	result = check_batch(capture, sensor, baseline);
	close(sensor);
	close(capture);
	return result;
}