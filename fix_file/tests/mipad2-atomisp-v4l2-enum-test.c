// SPDX-License-Identifier: GPL-2.0
/* Read-only V4L2 ABI regression: enumeration and unknown ioctl. */
#include <errno.h>
#include <fcntl.h>
#include <linux/videodev2.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

int main(int argc, char **argv)
{
	struct v4l2_frmsizeenum size = {
		.index = 0,
		.pixel_format = v4l2_fourcc('B', 'A', 'D', '!'),
	};
	int fd, i, j, failures = 0;

	if (argc != 2) {
		fprintf(stderr, "usage: %s /dev/video0\n", argv[0]);
		return 2;
	}
	fd = open(argv[1], O_RDWR | O_CLOEXEC);
	if (fd < 0) {
		perror("open");
		return 2;
	}
	for (i = 0; i < 2; i++) {
		struct v4l2_input input = { .index = i };

		if (ioctl(fd, VIDIOC_ENUMINPUT, &input) < 0) {
			perror("VIDIOC_ENUMINPUT");
			return 1;
		}
		for (j = 0; j < 3; j++) {
			if (input.reserved[j]) {
				fprintf(stderr, "FAIL input %d reserved[%d]=%u\n",
					i, j, input.reserved[j]);
				failures++;
			}
		}
	}
	if (ioctl(fd, VIDIOC_ENUM_FRAMESIZES, &size) == 0 || errno != EINVAL) {
		fprintf(stderr, "FAIL invalid pixel format was not rejected with EINVAL\n");
		failures++;
	}
	memset(&size, 0, sizeof(size));
	size.pixel_format = V4L2_PIX_FMT_YUV420;
	if (ioctl(fd, VIDIOC_ENUM_FRAMESIZES, &size) < 0 ||
	    size.type != V4L2_FRMSIZE_TYPE_DISCRETE ||
	    !size.discrete.width || !size.discrete.height) {
		perror("VIDIOC_ENUM_FRAMESIZES YUV420");
		return 1;
	}
	errno = 0;
	if (ioctl(fd, _IO('V', 250), NULL) == 0 || errno != ENOTTY) {
		fprintf(stderr, "FAIL unknown ioctl was not rejected with ENOTTY\n");
		failures++;
	}
	if (!failures)
		printf("PASS: reserved zero; invalid format EINVAL; "
		       "unknown ioctl ENOTTY; YUV420 %ux%u\n",
		       size.discrete.width, size.discrete.height);
	close(fd);
	return failures ? 1 : 0;
}
