// SPDX-License-Identifier: GPL-2.0
/* Read-only V4L2 control ABI test. Does not switch inputs or stream.
 * cc -Wall -Wextra -Werror -O2 -o atomisp-control-test this-file.c
 * ./atomisp-control-test /dev/video0 [--baseline]
 */
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>
#include <linux/videodev2.h>

#define CHECK(cond, msg) do {						\
	if (!(cond)) {							\
		fprintf(stderr, "%s: %s\n", (msg), strerror(errno));	\
		return EXIT_FAILURE;					\
	}								\
} while (0)

static int call(int fd, unsigned long req, void *arg)
{
	int ret;

	do {
		ret = ioctl(fd, req, arg);
	} while (ret < 0 && errno == EINTR);
	return ret;
}

static int run(int fd, int baseline)
{
	const unsigned int gain_ids[] = { V4L2_CID_RED_BALANCE,
					  V4L2_CID_BLUE_BALANCE };
	const unsigned int modifiers[] = {
		V4L2_CTRL_FLAG_NEXT_CTRL,
		V4L2_CTRL_FLAG_NEXT_CTRL | V4L2_CTRL_FLAG_NEXT_COMPOUND,
	};
	struct v4l2_capability cap = {};
	struct v4l2_ext_control gains[2] = {};
	struct v4l2_ext_controls values = {
		.which = V4L2_CTRL_WHICH_CUR_VAL, .count = 2, .controls = gains,
	};
	struct v4l2_query_ext_ctrl compound = { .id = V4L2_CTRL_FLAG_NEXT_COMPOUND };
	struct v4l2_queryctrl legacy = { .id = V4L2_CTRL_FLAG_NEXT_CTRL };
	unsigned int input, i;

	CHECK(!call(fd, VIDIOC_QUERYCAP, &cap), "QUERYCAP");
	CHECK(!strcmp((const char *)cap.driver, "atomisp"), "not an AtomISP node");
	CHECK(!call(fd, VIDIOC_G_INPUT, &input), "G_INPUT");
	printf("driver=%s input=%u\n", cap.driver, input);

	for (i = 0; i < 2; i++) {
		struct v4l2_query_ext_ctrl q = { .id = gain_ids[i] };

		CHECK(!call(fd, VIDIOC_QUERY_EXT_CTRL, &q), "direct balance query");
		printf("direct 0x%08x %s range=%lld..%lld step=%llu default=%lld flags=0x%x\n",
		       q.id, q.name, (long long)q.minimum, (long long)q.maximum,
		       (unsigned long long)q.step, (long long)q.default_value, q.flags);
		CHECK(q.type == V4L2_CTRL_TYPE_INTEGER && q.minimum == 256 &&
		      q.maximum == 4095 && q.step == 1 &&
		      q.default_value >= q.minimum && q.default_value <= q.maximum &&
		      q.elems == 1 && !q.nr_of_dims &&
		      !(q.flags & (V4L2_CTRL_FLAG_DISABLED | V4L2_CTRL_FLAG_HAS_PAYLOAD)),
		      "wrong Q10 gain metadata");
		gains[i].id = gain_ids[i];
	}
	CHECK(!call(fd, VIDIOC_G_EXT_CTRLS, &values), "read current gains together");
	printf("current gains=%d,%d\n", gains[0].value, gains[1].value);

	for (i = 0; i < 2; i++) {
		unsigned int cursor = 0, seen = 0, count = 0;
		struct v4l2_query_ext_ctrl q = { .id = modifiers[i] };

		while (!call(fd, VIDIOC_QUERY_EXT_CTRL, &q)) {
			struct v4l2_query_ext_ctrl direct = { .id = q.id };
			struct v4l2_control control = { .id = q.id };

			CHECK(!baseline && q.id > cursor, "NEXT must advance once");
			CHECK(q.id < V4L2_CID_PRIVATE_BASE, "enumerated legacy private ID");
			CHECK(!(q.flags & V4L2_CTRL_FLAG_DISABLED), "enumerated disabled control");
			CHECK(!call(fd, VIDIOC_QUERY_EXT_CTRL, &direct), "direct after NEXT");
			CHECK(!memcmp(&q, &direct, sizeof(q)), "NEXT differs from direct query");
			CHECK(!call(fd, VIDIOC_G_CTRL, &control), "read enumerated scalar");
			if (q.id == gain_ids[0])
				seen |= 1;
			if (q.id == gain_ids[1])
				seen |= 2;
			printf("NEXT(0x%08x) 0x%08x %s\n", modifiers[i], q.id, q.name);
			count++;
			cursor = q.id;
			memset(&q, 0, sizeof(q));
			q.id = cursor | modifiers[i];
		}
		CHECK(errno == EINVAL, "NEXT should terminate with EINVAL");
		printf("NEXT(0x%08x) count=%u end=EINVAL\n", modifiers[i], count);
		CHECK(baseline ? count == 0 : seen == 3, "missing controls");
	}
	CHECK(call(fd, VIDIOC_QUERY_EXT_CTRL, &compound) < 0 && errno == EINVAL,
	      "unexpected compound control");
	if (baseline)
		CHECK(call(fd, VIDIOC_QUERYCTRL, &legacy) < 0 && errno == EINVAL,
		      "legacy baseline enumeration unexpectedly worked");
	else
		CHECK(!call(fd, VIDIOC_QUERYCTRL, &legacy) && legacy.id &&
		      !(legacy.id & V4L2_CTRL_FLAG_NEXT_CTRL), "legacy NEXT enumeration");
	return EXIT_SUCCESS;
}

int main(int argc, char **argv)
{
	int fd, status;

	if (argc < 2 || argc > 3 || (argc == 3 && strcmp(argv[2], "--baseline"))) {
		fprintf(stderr, "Usage: %s /dev/videoN [--baseline]\n", argv[0]);
		return EXIT_FAILURE;
	}
	fd = open(argv[1], O_RDONLY | O_NONBLOCK);
	CHECK(fd >= 0, "open video node");
	status = run(fd, argc == 3);
	close(fd);
	return status;
}
