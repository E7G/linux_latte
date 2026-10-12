/* r14-only destructive queue test: caller must ensure no active camera client.
 * Caller must snapshot/restore selected sensor controls around this test.
 * Does not change input. Restores the saved video format on exit.
 */
#include <errno.h>
#include <fcntl.h>
#include <linux/videodev2.h>
#include <linux/v4l2-subdev.h>
#include <poll.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/utsname.h>
#include <unistd.h>

struct mapping { void *address; size_t length; };
struct capture { int fd; bool streaming; unsigned int count; struct mapping maps[32]; };
static int call(int fd, unsigned long op, void *arg)
{
    int ret;
    do { ret = ioctl(fd, op, arg); } while (ret < 0 && errno == EINTR);
    return ret;
}
static void unmap_all(struct capture *c)
{
    for (unsigned int i = 0; i < c->count; ++i) {
        if (c->maps[i].address && c->maps[i].address != MAP_FAILED) {
            munmap(c->maps[i].address, c->maps[i].length);
            c->maps[i].address = NULL;
        }
    }
}
static int sensor_fd = -1;
static void period_stage(int fd,const char *stage)
{
    struct v4l2_streamparm p={.type=V4L2_BUF_TYPE_VIDEO_CAPTURE};
    if (call(fd,VIDIOC_G_PARM,&p)<0) perror("period stage");
    else printf("PERIOD %s %u/%u\n",stage,p.parm.capture.timeperframe.numerator,p.parm.capture.timeperframe.denominator);
}
static int start(struct capture *c)
{
    struct v4l2_requestbuffers req = {.type = V4L2_BUF_TYPE_VIDEO_CAPTURE,
        .memory = V4L2_MEMORY_MMAP, .count = 8};
    struct v4l2_format fmt_before={.type=V4L2_BUF_TYPE_VIDEO_CAPTURE},fmt_after=fmt_before;
    struct v4l2_control exp_before={.id=V4L2_CID_EXPOSURE},exp_after=exp_before;
    if (call(c->fd,VIDIOC_G_FMT,&fmt_before)<0 || call(sensor_fd,VIDIOC_G_CTRL,&exp_before)<0) return -1;
    period_stage(c->fd,"before-REQBUFS");
    if (call(c->fd, VIDIOC_REQBUFS, &req) < 0) return -1;
    period_stage(c->fd,"after-REQBUFS");
    if (call(c->fd,VIDIOC_G_FMT,&fmt_after)<0 || call(sensor_fd,VIDIOC_G_CTRL,&exp_after)<0) return -1;
    printf("PRESERVE exposure %d -> %d format %ux%u -> %ux%u\n",exp_before.value,exp_after.value,
           fmt_before.fmt.pix.width,fmt_before.fmt.pix.height,fmt_after.fmt.pix.width,fmt_after.fmt.pix.height);
    if (exp_before.value!=exp_after.value || fmt_before.fmt.pix.width!=fmt_after.fmt.pix.width ||
        fmt_before.fmt.pix.height!=fmt_after.fmt.pix.height || fmt_before.fmt.pix.pixelformat!=fmt_after.fmt.pix.pixelformat ||
        fmt_before.fmt.pix.sizeimage!=fmt_after.fmt.pix.sizeimage || fmt_before.fmt.pix.bytesperline!=fmt_after.fmt.pix.bytesperline) {
        errno=EIO;return -1;
    }
    if (req.count < 8 || req.count > 32) { errno = EINVAL; return -1; }
    c->count = req.count;
    for (unsigned int i = 0; i < c->count; ++i) {
        struct v4l2_buffer b = {.type = req.type, .memory = req.memory, .index = i};
        if (call(c->fd, VIDIOC_QUERYBUF, &b) < 0) return -1;
        c->maps[i].length = b.length;
        c->maps[i].address = mmap(NULL, b.length, PROT_READ | PROT_WRITE,
                                 MAP_SHARED, c->fd, b.m.offset);
        if (c->maps[i].address == MAP_FAILED) return -1;
        if (call(c->fd, VIDIOC_QBUF, &b) < 0) return -1;
    }
    enum v4l2_buf_type type = req.type;
    if (call(c->fd, VIDIOC_STREAMON, &type) < 0) return -1;
    period_stage(c->fd,"after-STREAMON");
    c->streaming = true;
    return 0;
}

/* Enumerating sizes while buffers are streaming must not modify ACTIVE state. */
static int verify_enum_unchanged(int fd)
{
    struct v4l2_format before={.type=V4L2_BUF_TYPE_VIDEO_CAPTURE},after=before;
    struct v4l2_subdev_format sensor_before={.which=V4L2_SUBDEV_FORMAT_ACTIVE,.pad=0},sensor_after=sensor_before;
    struct v4l2_subdev_selection crop_before={.which=V4L2_SUBDEV_FORMAT_ACTIVE,.pad=0,.target=V4L2_SEL_TGT_CROP},crop_after=crop_before;
    const unsigned ids[]={V4L2_CID_EXPOSURE,V4L2_CID_VBLANK,V4L2_CID_ANALOGUE_GAIN,V4L2_CID_RED_BALANCE,V4L2_CID_BLUE_BALANCE};
    int values[sizeof(ids)/sizeof(ids[0])];
    if(call(fd,VIDIOC_G_FMT,&before)<0 || call(sensor_fd,VIDIOC_SUBDEV_G_FMT,&sensor_before)<0)return -1;
    if(call(sensor_fd,VIDIOC_SUBDEV_G_SELECTION,&crop_before)<0)return -1;
    for(unsigned i=0;i<sizeof(ids)/sizeof(ids[0]);i++) {
        struct v4l2_control ctrl={.id=ids[i]};
        if(call(sensor_fd,VIDIOC_G_CTRL,&ctrl)<0)return -1;
        values[i]=ctrl.value;
    }
    struct v4l2_frmsizeenum fs={.pixel_format=before.fmt.pix.pixelformat};
    if(call(fd,VIDIOC_ENUM_FRAMESIZES,&fs)<0)return -1;
    if(fs.type!=V4L2_FRMSIZE_TYPE_STEPWISE || fs.stepwise.min_width!=4 || fs.stepwise.min_height!=4 ||
       fs.stepwise.max_width>1920 || fs.stepwise.max_height>1440 ||
       fs.stepwise.step_width!=2 || fs.stepwise.step_height!=2 || fs.reserved[0] || fs.reserved[1]) {
        errno=EIO;return -1;
    }
    struct v4l2_frmsizeenum invalid=fs;invalid.index=1;errno=0;
    if(call(fd,VIDIOC_ENUM_FRAMESIZES,&invalid)!=-1 || errno!=EINVAL){errno=EIO;return -1;}
    invalid.index=0;invalid.pixel_format=0xffffffff;errno=0;
    if(call(fd,VIDIOC_ENUM_FRAMESIZES,&invalid)!=-1 || errno!=EINVAL){errno=EIO;return -1;}
    if(call(fd,VIDIOC_G_FMT,&after)<0 || call(sensor_fd,VIDIOC_SUBDEV_G_FMT,&sensor_after)<0)return -1;
    if(call(sensor_fd,VIDIOC_SUBDEV_G_SELECTION,&crop_after)<0)return -1;
    if(crop_before.r.left!=crop_after.r.left || crop_before.r.top!=crop_after.r.top ||
       crop_before.r.width!=crop_after.r.width || crop_before.r.height!=crop_after.r.height) {
        errno=EIO;return -1;
    }
    printf("ENUM_CROP left=%d top=%d width=%u height=%u unchanged PASS\n",
           crop_before.r.left,crop_before.r.top,crop_before.r.width,crop_before.r.height);
    if(before.fmt.pix.width!=after.fmt.pix.width || before.fmt.pix.height!=after.fmt.pix.height ||
       before.fmt.pix.pixelformat!=after.fmt.pix.pixelformat || before.fmt.pix.sizeimage!=after.fmt.pix.sizeimage ||
       before.fmt.pix.bytesperline!=after.fmt.pix.bytesperline ||
       sensor_before.format.width!=sensor_after.format.width || sensor_before.format.height!=sensor_after.format.height ||
       sensor_before.format.code!=sensor_after.format.code){errno=EIO;return -1;}
    for(unsigned i=0;i<sizeof(ids)/sizeof(ids[0]);i++) {
        struct v4l2_control ctrl={.id=ids[i]};
        if(call(sensor_fd,VIDIOC_G_CTRL,&ctrl)<0 || ctrl.value!=values[i]){errno=EIO;return -1;}
    }
    printf("ENUM_STEPWISE %u..%u/%u x %u..%u/%u ACTIVE/control preservation PASS\n",
           fs.stepwise.min_width,fs.stepwise.max_width,fs.stepwise.step_width,
           fs.stepwise.min_height,fs.stepwise.max_height,fs.stepwise.step_height);
    return 0;
}
static int frames(struct capture *c, const char *phase)
{
    if(verify_enum_unchanged(c->fd)<0)return -1;
    struct v4l2_format payload_fmt={.type=V4L2_BUF_TYPE_VIDEO_CAPTURE};
    if(call(c->fd,VIDIOC_G_FMT,&payload_fmt)<0)return -1;
    unsigned int sequence = 0;
    for (int n = 0; n < 60; ++n) {
        struct pollfd p = {.fd = c->fd, .events = POLLIN};
        int ret;
        do { ret = poll(&p, 1, 5000); } while (ret < 0 && errno == EINTR);
        if (ret <= 0) { if (!ret) errno = ETIMEDOUT; return -1; }
        struct v4l2_buffer b = {.type = V4L2_BUF_TYPE_VIDEO_CAPTURE, .memory = V4L2_MEMORY_MMAP};
        if (call(c->fd, VIDIOC_DQBUF, &b) < 0) return -1;
        if (b.flags & V4L2_BUF_FLAG_ERROR || !b.bytesused || b.index>=c->count ||
            b.bytesused!=payload_fmt.fmt.pix.sizeimage || b.bytesused>c->maps[b.index].length) {
            errno = EIO; return -1;
        }
        if (n && b.sequence <= sequence) {
            fprintf(stderr, "FAIL duplicate sequence %u\n", b.sequence);
            errno = EIO; return -1;
        }
        sequence = b.sequence;
        printf("%s frame=%u bytes=%u timestamp=%ld.%06ld\n", phase, b.sequence,
               b.bytesused, (long)b.timestamp.tv_sec, (long)b.timestamp.tv_usec);
        if (call(c->fd, VIDIOC_QBUF, &b) < 0) return -1;
    }
    return 0;
}
static int busy(int fd, unsigned long op, void *arg, const char *name)
{
    errno = 0;
    if (call(fd, op, arg) != -1 || errno != EBUSY) {
        fprintf(stderr, "%s: nonowner did not receive EBUSY (errno=%d)\n", name, errno);
        errno = EIO; return -1;
    }
    return 0;
}
int main(int argc, char **argv)
{
    struct utsname uts;
    if (argc != 4 || uname(&uts) || strcmp(uts.release, "6.14.0-mipad2-integrated-r14")) {
        fprintf(stderr, "Usage: on r14 with camera idle, %s /dev/videoN fps /dev/sensor-subdevN\n", argv[0]);
        return 2;
    }
    sensor_fd=open(argv[3],O_RDWR|O_CLOEXEC);
    if(sensor_fd<0) { perror("sensor open");return 1; }
    struct capture a = {.fd = -1}, b = {.fd = -1};
    int observer = -1, result = 1;
    bool have_format = false;
    struct v4l2_format saved = {.type = V4L2_BUF_TYPE_VIDEO_CAPTURE};
    a.fd = open(argv[1], O_RDWR | O_NONBLOCK | O_CLOEXEC);
    if (a.fd < 0) goto out;
    struct v4l2_capability cap;
    if (call(a.fd, VIDIOC_QUERYCAP, &cap) < 0) goto out;
    if (strcmp((const char *)cap.driver, "atomisp")) { errno = ENODEV; goto out; }
    if (call(a.fd, VIDIOC_G_FMT, &saved) < 0) goto out;
    have_format = true;
    struct v4l2_format selected = saved;
    if (!selected.fmt.pix.width || !selected.fmt.pix.height) {
        selected.fmt.pix.width = 640; selected.fmt.pix.height = 480;
        selected.fmt.pix.pixelformat = V4L2_PIX_FMT_YUV420;
    }
    /* Deliberately reuse cached video configuration without S_FMT. */
    if (!saved.fmt.pix.width || !saved.fmt.pix.height) { errno=EINVAL;goto out; }
    unsigned int rate=(unsigned int)atoi(argv[2]);
    if (rate!=30 && rate!=15) { errno=EINVAL; goto out; }
    struct v4l2_streamparm period={.type=V4L2_BUF_TYPE_VIDEO_CAPTURE};
    period.parm.capture.timeperframe.numerator=1;
    period.parm.capture.timeperframe.denominator=rate;
    if (call(a.fd, VIDIOC_S_PARM, &period)<0) goto out;
    printf("WITHOUT S_FMT requested rate %u actual period %u/%u\n",rate,
           period.parm.capture.timeperframe.numerator,period.parm.capture.timeperframe.denominator);
    struct v4l2_queryctrl exp_info={.id=V4L2_CID_EXPOSURE};
    if(call(sensor_fd,VIDIOC_QUERYCTRL,&exp_info)<0) goto out;
    struct v4l2_control high_exp={.id=V4L2_CID_EXPOSURE,.value=exp_info.minimum+(exp_info.maximum-exp_info.minimum)*3/4};
    if(call(sensor_fd,VIDIOC_S_CTRL,&high_exp)<0) goto out;
    printf("HIGH_EXPOSURE %d range %d..%d\n",high_exp.value,exp_info.minimum,exp_info.maximum);
    b.fd = open(argv[1], O_RDWR | O_NONBLOCK | O_CLOEXEC);
    observer = open(argv[1], O_RDWR | O_NONBLOCK | O_CLOEXEC);
    if (b.fd < 0 || observer < 0 || start(&a) < 0) goto out;
    struct v4l2_requestbuffers req = {.type = V4L2_BUF_TYPE_VIDEO_CAPTURE,
        .memory = V4L2_MEMORY_MMAP, .count = 8};
    enum v4l2_buf_type type = req.type;
    struct v4l2_buffer q = {.type = req.type, .memory = req.memory, .index = 0};
    if (busy(b.fd, VIDIOC_REQBUFS, &req, "REQBUFS") < 0 ||
        busy(b.fd, VIDIOC_QBUF, &q, "QBUF") < 0 ||
        busy(b.fd, VIDIOC_STREAMON, &type, "STREAMON") < 0 ||
        busy(b.fd, VIDIOC_STREAMOFF, &type, "STREAMOFF") < 0) goto out;
    if (frames(&a, "before-observer-close") < 0) goto out;
    close(observer); observer = -1;
    if (frames(&a, "after-observer-close") < 0) goto out;
    struct v4l2_control restart_exp={.id=V4L2_CID_EXPOSURE};
    if (call(sensor_fd,VIDIOC_G_CTRL,&restart_exp)<0) goto out;
    int expected_exposure=restart_exp.value;
    if (call(a.fd, VIDIOC_STREAMOFF, &type) < 0) goto out;
    a.streaming=false;
    for (unsigned int i=0;i<a.count;++i) {
        struct v4l2_buffer queued={.type=type,.memory=V4L2_MEMORY_MMAP,.index=i};
        if (call(a.fd,VIDIOC_QBUF,&queued)<0) goto out;
    }
    if (call(a.fd,VIDIOC_STREAMON,&type)<0) goto out;
    a.streaming=true;
    if (call(sensor_fd,VIDIOC_G_CTRL,&restart_exp)<0 || restart_exp.value!=expected_exposure) {
        errno=EIO;goto out;
    }
    printf("RESTART_PRESERVE exposure %d -> %d\n",expected_exposure,restart_exp.value);
    if (frames(&a,"ordinary-restart")<0) goto out;
    /* mmap holds file references: unmap before close to actually invoke release. */
    unmap_all(&a);
    close(a.fd); a.fd = -1; a.streaming = false;
    if (start(&b) < 0 || frames(&b, "remaining-fd-takeover") < 0) goto out;
    result = 0;
out:
    if (result) perror("multiopen regression");
    struct capture *captures[] = {&a, &b};
    for (unsigned int i = 0; i < 2; ++i) {
        struct capture *c = captures[i];
        if (c->fd < 0) continue;
        enum v4l2_buf_type type = V4L2_BUF_TYPE_VIDEO_CAPTURE;
        if (c->streaming && call(c->fd, VIDIOC_STREAMOFF, &type) < 0) result = 1;
        unmap_all(c);
        struct v4l2_requestbuffers req = {.type = type, .memory = V4L2_MEMORY_MMAP};
        if (c->count && call(c->fd, VIDIOC_REQBUFS, &req) < 0) result = 1;
    }
    int restore_fd = a.fd >= 0 ? a.fd : b.fd;
    if (have_format && restore_fd >= 0 && call(restore_fd, VIDIOC_S_FMT, &saved) < 0) {
        perror("restore video format"); result = 1;
    }
    if (have_format && restore_fd >= 0) {
        struct v4l2_format restored = {.type = V4L2_BUF_TYPE_VIDEO_CAPTURE};
        if (call(restore_fd, VIDIOC_G_FMT, &restored) < 0 ||
            restored.fmt.pix.width != saved.fmt.pix.width ||
            restored.fmt.pix.height != saved.fmt.pix.height ||
            restored.fmt.pix.pixelformat != saved.fmt.pix.pixelformat ||
            restored.fmt.pix.field != saved.fmt.pix.field) {
            fprintf(stderr, "Restored video format readback mismatch\n"); result = 1;
        }
    }
    if (observer >= 0) close(observer);
    if (a.fd >= 0) close(a.fd);
    if (b.fd >= 0) close(b.fd);
    if (!result) puts("PASS owner isolation/takeover with increasing frame sequence");
    close(sensor_fd);
    return result;
}
