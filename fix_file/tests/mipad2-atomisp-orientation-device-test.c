// SPDX-License-Identifier: GPL-2.0
/* Compare position and mounting metadata without changing the selected input. */
#include <errno.h>
#include <fcntl.h>
#include <linux/videodev2.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

#define REQUIRE(cond, msg) do { \
	if (!(cond)) { \
		fprintf(stderr, "%s (errno=%d)\n", (msg), errno); \
		return 1; \
	} \
} while (0)

static int verify(int capture, int sensor, int rear, int baseline)
{
	const unsigned int ids[] = {
		V4L2_CID_CAMERA_ORIENTATION, V4L2_CID_CAMERA_SENSOR_ROTATION,
	};
	const int want[] = { rear ? V4L2_CAMERA_ORIENTATION_BACK :
			            V4L2_CAMERA_ORIENTATION_FRONT, rear ? 270 : 0 };
	struct v4l2_querymenu sm = { .id = ids[0], .index = want[0] }, cm = sm;
	unsigned int i;

	for (i = 0; i < 2; i++) {
		struct v4l2_query_ext_ctrl src = { .id = ids[i] }, dst = src;
		struct v4l2_ext_control v = { .id = ids[i] };
		struct v4l2_ext_controls sc = { .count = 1, .controls = &v };
		struct v4l2_control legacy = { .id = ids[i] };

		REQUIRE(!ioctl(sensor, VIDIOC_QUERY_EXT_CTRL, &src),
			"sensor does not expose location metadata");
		REQUIRE((src.flags & V4L2_CTRL_FLAG_READ_ONLY) &&
			src.type == (i ? V4L2_CTRL_TYPE_INTEGER : V4L2_CTRL_TYPE_MENU),
			"unexpected sensor control type or access");
		REQUIRE(!ioctl(sensor, VIDIOC_G_EXT_CTRLS, &sc) && v.value == want[i],
			"unexpected board metadata on supplied sensor");
		if (baseline) {
			REQUIRE(ioctl(capture, VIDIOC_QUERY_EXT_CTRL, &dst) < 0 &&
				errno == EINVAL, "baseline unexpectedly has capture metadata");
			continue;
		}
		REQUIRE(!ioctl(capture, VIDIOC_QUERY_EXT_CTRL, &dst) &&
			!memcmp(&src, &dst, sizeof(dst)), "capture metadata differs from sensor");
		REQUIRE(!ioctl(capture, VIDIOC_G_CTRL, &legacy) && legacy.value == want[i],
			"capture scalar read did not use the active sensor");
		v.value = -1;
		REQUIRE(!ioctl(capture, VIDIOC_G_EXT_CTRLS, &sc) && v.value == want[i],
			"capture extended read did not use the active sensor");
		dst.id = (ids[i] - 1) | V4L2_CTRL_FLAG_NEXT_CTRL;
		REQUIRE(!ioctl(capture, VIDIOC_QUERY_EXT_CTRL, &dst) && dst.id == ids[i],
			"location control missing from standard enumeration");
	}

	REQUIRE(!ioctl(sensor, VIDIOC_QUERYMENU, &sm), "sensor orientation menu missing");
	REQUIRE(!strcmp((const char *)sm.name, rear ? "Back" : "Front"),
		"unexpected orientation item");
	if (baseline) {
		REQUIRE(ioctl(capture, VIDIOC_QUERYMENU, &cm) < 0 && errno == ENOTTY,
			"baseline unexpectedly has a capture menu callback");
		puts("BASELINE: sensor metadata present but absent from capture");
	} else {
		REQUIRE(!ioctl(capture, VIDIOC_QUERYMENU, &cm) &&
			!memcmp(&sm, &cm, sizeof(cm)), "capture menu differs from active sensor");
		cm.index = 3;
		REQUIRE(ioctl(capture, VIDIOC_QUERYMENU, &cm) < 0 && errno == EINVAL,
			"invalid orientation menu index accepted");
		cm.id = ids[1];
		cm.index = 0;
		REQUIRE(ioctl(capture, VIDIOC_QUERYMENU, &cm) < 0 && errno == EINVAL,
			"rotation integer incorrectly exposed as a menu");
		printf("PASS: capture location %s, rotation %d degrees, read only\n",
		       sm.name, want[1]);
	}
	return 0;
}

int main(int argc, char *argv[])
{
	int capture, sensor, result;

	if ((argc != 4 && argc != 5) ||
	    (strcmp(argv[3], "front") && strcmp(argv[3], "back")) ||
	    (argc == 5 && strcmp(argv[4], "--baseline")))
		return 2;
	capture = open(argv[1], O_RDONLY | O_NONBLOCK);
	sensor = open(argv[2], O_RDONLY | O_NONBLOCK);
	REQUIRE(capture >= 0 && sensor >= 0, "open capture and sensor");
	result = verify(capture, sensor, !strcmp(argv[3], "back"), argc == 5);
	close(sensor);
	close(capture);
	return result;
}
