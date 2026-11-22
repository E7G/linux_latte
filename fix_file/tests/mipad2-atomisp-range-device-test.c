// SPDX-License-Identifier: GPL-2.0
/* Verify non-current values without changing the active sensor or its settings. */
#include <errno.h>
#include <fcntl.h>
#include <linux/videodev2.h>
#include <stdio.h>
#include <sys/ioctl.h>
#include <unistd.h>

#ifndef V4L2_CTRL_WHICH_MIN_VAL
#define V4L2_CTRL_WHICH_MIN_VAL 0x0f020000
#define V4L2_CTRL_WHICH_MAX_VAL 0x0f030000
#endif
#ifndef V4L2_CTRL_FLAG_HAS_WHICH_MIN_MAX
#define V4L2_CTRL_FLAG_HAS_WHICH_MIN_MAX 0x1000
#endif

static int test_limits(int capture, int sensor)
{
	const __u32 ids[] = { V4L2_CID_RED_BALANCE, V4L2_CID_BLUE_BALANCE,
			      V4L2_CID_EXPOSURE, V4L2_CID_ANALOGUE_GAIN };
	const __u32 modes[] = { V4L2_CTRL_WHICH_DEF_VAL, V4L2_CTRL_WHICH_MIN_VAL,
				V4L2_CTRL_WHICH_MAX_VAL };
	unsigned int i, j;

	for (i = 0; i < sizeof(ids) / sizeof(ids[0]); i++) {
		struct v4l2_query_ext_ctrl q = { .id = ids[i] };

		if (ioctl(sensor, VIDIOC_QUERY_EXT_CTRL, &q) < 0 ||
		    q.type != V4L2_CTRL_TYPE_INTEGER ||
		    !(q.flags & V4L2_CTRL_FLAG_HAS_WHICH_MIN_MAX))
			return 1;

		for (j = 0; j < sizeof(modes) / sizeof(modes[0]); j++) {
			struct v4l2_ext_control a = { .id = ids[i] }, b = a;
			struct v4l2_ext_controls x = {
				.count = 1, .which = modes[j], .controls = &a,
			};
			struct v4l2_ext_controls y = x;
			const long long expected[] = { q.default_value, q.minimum, q.maximum };

			y.controls = &b;
			if (ioctl(capture, VIDIOC_G_EXT_CTRLS, &x) < 0 ||
			    ioctl(sensor, VIDIOC_G_EXT_CTRLS, &y) < 0 ||
			    a.value != b.value || a.value != expected[j]) {
				fprintf(stderr, "%s which=%08x capture=%d sensor=%d expected=%lld\n",
					q.name, modes[j], a.value, b.value, expected[j]);
				return 1;
			}
		}
	}
	{
		struct v4l2_ext_control one = { .id = V4L2_CID_COLORFX };
		struct v4l2_ext_controls c = {
			.which = V4L2_CTRL_WHICH_MIN_VAL, .count = 1, .controls = &one,
		};

		if (ioctl(capture, VIDIOC_G_EXT_CTRLS, &c) >= 0 || errno != EINVAL)
			return 1;
	}
	puts("PASS: capture default, minimum and maximum match the active sensor");
	return 0;
}

int main(int argc, char **argv)
{
	int capture, sensor, rc;

	if (argc != 3) {
		fprintf(stderr, "Usage: %s /dev/videoN /dev/v4l-subdevN\n", argv[0]);
		return 2;
	}
	capture = open(argv[1], O_RDONLY | O_NONBLOCK);
	sensor = open(argv[2], O_RDONLY | O_NONBLOCK);
	if (capture < 0 || sensor < 0) {
		perror("open capture/sensor");
		return 1;
	}
	rc = test_limits(capture, sensor);
	close(sensor);
	close(capture);
	return rc;
}
