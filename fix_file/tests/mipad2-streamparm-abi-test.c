// SPDX-License-Identifier: GPL-2.0
/* Run only with the candidate kernel and no active video stream.
 * Tests one selected input; caller discovers/passes its matching subdev.
 * Saves/restores frame period, run mode, VBLANK and exposure.
 */
#include <errno.h>
#include <fcntl.h>
#include <linux/videodev2.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

#define RUN_MODE_ID (V4L2_CID_CAMERA_CLASS_BASE + 1024 + 20)
static int control(int fd, unsigned int id, int *value, int set)
{
	struct v4l2_control c = { .id = id, .value = *value };
	if (ioctl(fd, set ? VIDIOC_S_CTRL : VIDIOC_G_CTRL, &c) < 0)
		return -1;
	*value = c.value;
	return 0;
}

static int valid(const struct v4l2_streamparm *p)
{
	if (p->type != V4L2_BUF_TYPE_VIDEO_CAPTURE ||
	    p->parm.capture.capability != V4L2_CAP_TIMEPERFRAME ||
	    p->parm.capture.capturemode || p->parm.capture.extendedmode ||
	    p->parm.capture.readbuffers ||
	    !p->parm.capture.timeperframe.numerator ||
	    !p->parm.capture.timeperframe.denominator)
		return 0;
	for (unsigned int i = 0; i < 4; i++)
		if (p->parm.capture.reserved[i])
			return 0;
	return 1;
}

int main(int argc, char **argv)
{
	struct v4l2_streamparm original, p;
	struct v4l2_format before = { .type = V4L2_BUF_TYPE_VIDEO_CAPTURE }, after;
	unsigned int modes[] = { 0x4000, 0x2000, 0x8000 };
	int internal_modes[] = { 1, 2, 3 };
	unsigned int rates[][2] = { {1, 30}, {1, 15}, {0, 0}, {0, 1}, {1, 0} };
	int fd = -1, sensor = -1, mode = 0, exposure = 0, vblank = 0;
	int failed = 0, saved = 0;
	if (argc != 3) {
		fprintf(stderr, "usage: %s /dev/video0 /dev/v4l-subdevN\n", argv[0]);
		return 2;
	}
	fd = open(argv[1], O_RDWR | O_CLOEXEC);
	sensor = open(argv[2], O_RDWR | O_CLOEXEC);
	if (fd < 0 || sensor < 0)
		goto error;
	unsigned int input;
	struct v4l2_input input_info = {0};
	if (ioctl(fd, VIDIOC_G_INPUT, &input) < 0)
		goto error;
	input_info.index = input;
	if (ioctl(fd, VIDIOC_ENUMINPUT, &input_info) < 0)
		goto error;
	const char *basename = strrchr(argv[2], '/');
	char path[256], sensor_name[64];
	if (!basename || strncmp(basename + 1, "v4l-subdev", 10)) {
		errno = EINVAL; goto error;
	}
	snprintf(path, sizeof(path), "/sys/class/video4linux/%s/name", basename + 1);
	FILE *name_file = fopen(path, "r");
	if (!name_file)
		goto error;
	int name_read = fgets(sensor_name, sizeof(sensor_name), name_file) != NULL;
	fclose(name_file);
	if (!name_read)
		goto error;
	sensor_name[strcspn(sensor_name, "\r\n")] = 0;
	if (strcmp(sensor_name, (const char *)input_info.name)) {
		fprintf(stderr, "Selected video input does not match sensor subdev\n");
		errno = EINVAL; goto error;
	}
	memset(&original, 0xff, sizeof(original));
	original.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
	if (ioctl(fd, VIDIOC_G_PARM, &original) < 0 || !valid(&original) ||
	    ioctl(fd, VIDIOC_G_FMT, &before) < 0 ||
	    control(fd, RUN_MODE_ID, &mode, 0) ||
	    control(sensor, V4L2_CID_VBLANK, &vblank, 0) ||
	    control(sensor, V4L2_CID_EXPOSURE, &exposure, 0))
		goto error;
	saved = 1;
	for (unsigned int i = 0; i < sizeof(rates)/sizeof(rates[0]); i++) {
		memset(&p, 0xff, sizeof(p));
		p.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
		p.parm.capture.capturemode = i == 1 ? UINT32_MAX : 0;
		p.parm.capture.timeperframe.numerator = rates[i][0];
		p.parm.capture.timeperframe.denominator = rates[i][1];
		if (ioctl(fd, VIDIOC_S_PARM, &p) < 0 || !valid(&p))
			goto error;
		printf("requested %u/%u returned %u/%u\n", rates[i][0], rates[i][1],
		       p.parm.capture.timeperframe.numerator, p.parm.capture.timeperframe.denominator);
		memset(&after, 0, sizeof(after)); after.type = before.type;
		if (ioctl(fd, VIDIOC_G_FMT, &after) < 0 ||
		    memcmp(&before.fmt.pix, &after.fmt.pix, sizeof(before.fmt.pix)))
			goto error;
		struct v4l2_streamparm queried;
		memset(&queried, 0xff, sizeof(queried)); queried.type = p.type;
		if (ioctl(fd, VIDIOC_G_PARM, &queried) < 0 || !valid(&queried) ||
		    memcmp(&p.parm.capture, &queried.parm.capture, sizeof(p.parm.capture)))
			goto error;
	}
	for (unsigned int i = 0; i < 3; i++) {
		int observed = 0;
		memset(&p, 0xff, sizeof(p)); p.type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
		p.parm.capture.capturemode = modes[i];
		if (ioctl(fd, VIDIOC_S_PARM, &p) < 0 || !valid(&p) ||
		    control(fd, RUN_MODE_ID, &observed, 0) || observed != internal_modes[i])
			goto error;
	}
	p.type = V4L2_BUF_TYPE_VIDEO_OUTPUT;
	if (ioctl(fd, VIDIOC_G_PARM, &p) == 0 || errno != EINVAL ||
	    ioctl(fd, VIDIOC_S_PARM, &p) == 0 || errno != EINVAL)
		goto error;
	goto restore;
error:
	fprintf(stderr, "FAIL streamparm ABI check: errno=%d (%s)\n", errno, strerror(errno));
	failed = 1;
restore:
	if (saved) {
		int restore_failed = control(fd, RUN_MODE_ID, &mode, 1) != 0;
		restore_failed |= ioctl(fd, VIDIOC_S_PARM, &original) < 0;
		restore_failed |= control(sensor, V4L2_CID_VBLANK, &vblank, 1) != 0;
		restore_failed |= control(sensor, V4L2_CID_EXPOSURE, &exposure, 1) != 0;
		int observed = 0;
		restore_failed |= control(fd, RUN_MODE_ID, &observed, 0) != 0 || observed != mode;
		restore_failed |= control(sensor, V4L2_CID_VBLANK, &observed, 0) != 0 || observed != vblank;
		restore_failed |= control(sensor, V4L2_CID_EXPOSURE, &observed, 0) != 0 || observed != exposure;
		if (restore_failed) {
			fprintf(stderr, "FAIL restoring original controls\n"); failed = 1;
		}
	}
	if (sensor >= 0) close(sensor);
	if (fd >= 0) close(fd);
	if (!failed) puts("PASS streamparm ABI, legacy CI modes, unchanged format; controls restored");
	return failed;
}
