// SPDX-License-Identifier: GPL-2.0
/* Read-only comparison between the AtomISP capture and active sensor nodes. */
#include <errno.h>
#include <fcntl.h>
#include <linux/videodev2.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

#define CHECK(cond, msg) do { \
	if (!(cond)) { \
		fprintf(stderr, "%s (errno=%d)\n", (msg), errno); \
		return EXIT_FAILURE; \
	} \
} while (0)

static int ioctl_retry(int fd, unsigned long request, void *arg)
{
	int rc;

	do {
		rc = ioctl(fd, request, arg);
	} while (rc < 0 && errno == EINTR);

	return rc;
}

static int test_controls(int capture, int sensor, bool baseline)
{
	const __u32 ids[] = { V4L2_CID_EXPOSURE, V4L2_CID_ANALOGUE_GAIN };
	struct v4l2_ext_control controls[2] = {
		{ .id = V4L2_CID_EXPOSURE }, { .id = V4L2_CID_ANALOGUE_GAIN },
	};
	struct v4l2_ext_controls batch = {
		.which = V4L2_CTRL_WHICH_CUR_VAL,
		.count = 2,
		.controls = controls,
	};
	int current[2];
	unsigned int i;

	for (i = 0; i < 2; i++) {
		struct v4l2_query_ext_ctrl src = { .id = ids[i] };
		struct v4l2_query_ext_ctrl dst = { .id = ids[i] };
		struct v4l2_queryctrl legacy = { .id = ids[i] };
		struct v4l2_control ctrl = { .id = ids[i] };
		struct v4l2_ext_control value = { .id = ids[i] };
		struct v4l2_ext_controls one = {
			.which = V4L2_CTRL_WHICH_CUR_VAL, .count = 1, .controls = &value,
		};

		CHECK(!ioctl_retry(sensor, VIDIOC_QUERY_EXT_CTRL, &src),
		      "sensor QUERY_EXT_CTRL");
		CHECK(src.type == V4L2_CTRL_TYPE_INTEGER && src.minimum <= src.default_value &&
		      src.default_value <= src.maximum && src.step && src.elems == 1,
		      "unexpected sensor metadata");
		CHECK(!ioctl_retry(sensor, VIDIOC_G_EXT_CTRLS, &one),
		      "sensor G_EXT_CTRLS");
		current[i] = value.value;
		printf("%s: min=%lld max=%lld default=%lld current=%d\n",
		       src.name, (long long)src.minimum, (long long)src.maximum,
		       (long long)src.default_value, current[i]);
		if (baseline) {
			CHECK(ioctl_retry(capture, VIDIOC_QUERY_EXT_CTRL, &dst) < 0 &&
			      errno == EINVAL, "baseline should lack capture control");
			CHECK(ioctl_retry(capture, VIDIOC_G_CTRL, &ctrl) < 0 &&
			      errno == EINVAL, "baseline should lack capture get");
			continue;
		}
		CHECK(!ioctl_retry(capture, VIDIOC_QUERY_EXT_CTRL, &dst) &&
		      !memcmp(&src, &dst, sizeof(src)), "capture and sensor metadata differ");
		CHECK(!ioctl_retry(capture, VIDIOC_QUERYCTRL, &legacy) &&
		      legacy.id == dst.id && legacy.type == dst.type &&
		      legacy.minimum == dst.minimum && legacy.maximum == dst.maximum &&
		      legacy.default_value == dst.default_value,
		      "legacy capture metadata differs");
		CHECK(!ioctl_retry(capture, VIDIOC_G_CTRL, &ctrl) && ctrl.value == current[i],
		      "capture and sensor current values differ");
	}

	if (!baseline) {
		CHECK(!ioctl_retry(capture, VIDIOC_G_EXT_CTRLS, &batch),
		      "mixed-class capture read failed");
		CHECK(controls[0].value == current[0] && controls[1].value == current[1],
		      "batch read differs from active sensor");
	}
	printf("%s\n", baseline ? "BASELINE: sensor controls are not exposed on capture" :
	       "PASS: capture exposure and analogue gain match active sensor");
	return EXIT_SUCCESS;
}

int main(int argc, char *argv[])
{
	bool baseline = argc == 4 && !strcmp(argv[3], "--baseline");
	int capture, sensor, result;

	if (argc != 3 && !baseline) {
		fprintf(stderr, "Usage: %s /dev/videoN /dev/v4l-subdevN [--baseline]\n", argv[0]);
		return EXIT_FAILURE;
	}
	capture = open(argv[1], O_RDONLY | O_NONBLOCK);
	CHECK(capture >= 0, "open capture node");
	sensor = open(argv[2], O_RDONLY | O_NONBLOCK);
	if (sensor < 0) {
		perror("open sensor node");
		close(capture);
		return EXIT_FAILURE;
	}
	result = test_controls(capture, sensor, baseline);
	close(sensor);
	close(capture);
	return result;
}
