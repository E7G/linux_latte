/* SPDX-License-Identifier: GPL-2.0-only */
/* Read-only capture format enumeration and negotiation; never starts a stream. */
#include <errno.h>
#include <fcntl.h>
#include <linux/videodev2.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

static int verify_format(int fd, bool report)
{
	struct v4l2_capability cap = {0};
	struct v4l2_format before = {.type = V4L2_BUF_TYPE_VIDEO_CAPTURE};
	struct v4l2_format trial = before, after = before;
	bool packed_y444 = false, nv12 = false, yu12 = false, yuyv = false;
	unsigned int i;

	if (ioctl(fd, VIDIOC_QUERYCAP, &cap) < 0 ||
	    ioctl(fd, VIDIOC_G_FMT, &before) < 0) {
		perror("query");
		return 1;
	}
	if (strcmp((const char *)cap.driver, "atomisp")) {
		fputs("expected AtomISP capture device\n", stderr);
		return 1;
	}

	for (i = 0; i < 32; i++) {
		struct v4l2_fmtdesc desc = {.index = i, .type = before.type};

		if (ioctl(fd, VIDIOC_ENUM_FMT, &desc) < 0) {
			if (errno == EINVAL)
				break;
			perror("enumeration");
			return 1;
		}
		printf("ENUM %.4s\n", (const char *)&desc.pixelformat);
		packed_y444 |= desc.pixelformat == V4L2_PIX_FMT_YUV444;
		nv12 |= desc.pixelformat == V4L2_PIX_FMT_NV12;
		yu12 |= desc.pixelformat == V4L2_PIX_FMT_YUV420;
		yuyv |= desc.pixelformat == V4L2_PIX_FMT_YUYV;
	}
	if (i == 32 || !nv12 || !yu12 || !yuyv) {
		fputs("expected complete enumeration with NV12/YU12/YUYV\n", stderr);
		return 1;
	}

	trial.fmt.pix.width = 1280;
	trial.fmt.pix.height = 720;
	trial.fmt.pix.pixelformat = V4L2_PIX_FMT_YUV444;
	if (ioctl(fd, VIDIOC_TRY_FMT, &trial) < 0) {
		perror("try format");
		return 1;
	}
	printf("TRY Y444 -> %.4s %ux%u stride=%u size=%u\n",
	       (const char *)&trial.fmt.pix.pixelformat,
	       trial.fmt.pix.width, trial.fmt.pix.height,
	       trial.fmt.pix.bytesperline, trial.fmt.pix.sizeimage);
	if (ioctl(fd, VIDIOC_G_FMT, &after) < 0) {
		perror("read active format");
		return 1;
	}
	if (memcmp(&before.fmt.pix, &after.fmt.pix, sizeof(before.fmt.pix))) {
		fputs("TRY_FMT changed the active format\n", stderr);
		return 1;
	}
	puts("Active capture format unchanged");

	if (!report && (packed_y444 || trial.fmt.pix.pixelformat != V4L2_PIX_FMT_YUV420)) {
		fputs("non-native packed Y444 was not replaced with YU12\n", stderr);
		return 1;
	}
	return 0;
}

int main(int argc, char **argv)
{
	bool report = argc == 2 && !strcmp(argv[1], "--report");
	int fd, ret;

	if (argc != 1 && !report) {
		fprintf(stderr, "Usage: %s [--report]\n", argv[0]);
		return 2;
	}
	fd = open("/dev/video0", O_RDONLY | O_CLOEXEC);
	if (fd < 0) {
		perror("/dev/video0");
		return 1;
	}
	ret = verify_format(fd, report);
	close(fd);
	return ret;
}
