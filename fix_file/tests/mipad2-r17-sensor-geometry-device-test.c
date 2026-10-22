/* r17-only destructive queue test: caller must ensure no active camera client.
 * Caller must snapshot/restore selected sensor controls around this test.
 * Does not change input. Restores the saved video format on exit.
 */
#include <errno.h>
#include <limits.h>
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
#include <stdint.h>
/* Buffer metadata layout is per file handle, selected before allocation. */
#define ATOMISP_BUFFER_METADATA_STANDARD	0
#define ATOMISP_BUFFER_METADATA_LEGACY	1
#define ATOMISP_BUFFER_METADATA_ANDROID	2

/*
 * Correlate metadata with the index, sequence and timeval timestamp returned
 * by DQBUF. timestamp_us is tv_sec * 1000000 + tv_usec, not a kernel pointer.
 * Query before requeueing the buffer; a stale or absent record is EAGAIN.
 * exp_id is unencoded in this interface; flags contains only V4L2_BUF_FLAG_ERROR.
 */
struct atomisp_frame_metadata {
	__u32 index;
	__u32 sequence;
	__aligned_u64 timestamp_us;
	__u32 exp_id;
	__u32 isp_config_id;
	__u32 flags;
	__u32 reserved;
};

/* Offsets 50/51 are unused in the original Mi Pad 2 Android ABI. */
#define ATOMISP_IOC_S_BUFFER_METADATA_MODE \
	_IOW('v', BASE_VIDIOC_PRIVATE + 50, __u32)
#define ATOMISP_IOC_G_FRAME_METADATA \
	_IOWR('v', BASE_VIDIOC_PRIVATE + 51, struct atomisp_frame_metadata)



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
static unsigned metadata_mode;
static const char *sensor_path;
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

/* Only execute on the new guarded R17 driver. No unsafe ACTIVE mutation is
 * sent to earlier kernels; the main release check precedes opening devices.
 */
static int verify_sensor_geometry_guard(void)
{
    struct v4l2_subdev_format before={.which=V4L2_SUBDEV_FORMAT_ACTIVE,.pad=0},after=before;
    struct v4l2_subdev_selection crop={.which=V4L2_SUBDEV_FORMAT_ACTIVE,.pad=0,.target=V4L2_SEL_TGT_CROP},crop_after=crop;
    if(call(sensor_fd,VIDIOC_SUBDEV_G_FMT,&before)<0 || call(sensor_fd,VIDIOC_SUBDEV_G_SELECTION,&crop)<0)return -1;
    for(int changed=0;changed<2;changed++) {
        struct v4l2_subdev_format attempt=before,saved;
        struct v4l2_subdev_selection selection=crop,selection_saved;
        if(changed){attempt.format.width=4;attempt.format.height=4;selection.r=(struct v4l2_rect){.left=0,.top=0,.width=32,.height=32};}
        saved=attempt;selection_saved=selection;errno=0;
        if(call(sensor_fd,VIDIOC_SUBDEV_S_FMT,&attempt)!=-1 || errno!=EBUSY || memcmp(&attempt,&saved,sizeof(saved))){errno=EIO;return -1;}
        errno=0;
        if(call(sensor_fd,VIDIOC_SUBDEV_S_SELECTION,&selection)!=-1 || errno!=EBUSY || memcmp(&selection,&selection_saved,sizeof(selection))){errno=EIO;return -1;}
    }
    int observer=open(sensor_path,O_RDWR|O_CLOEXEC);
    if(observer<0)return -1;
    int result=-1;
    struct v4l2_subdev_format own_try={.which=V4L2_SUBDEV_FORMAT_TRY,.pad=0},other_try=own_try,other_after=own_try;
    if(call(sensor_fd,VIDIOC_SUBDEV_G_FMT,&own_try)<0 || call(observer,VIDIOC_SUBDEV_G_FMT,&other_try)<0)goto out;
    own_try.format.width=UINT_MAX;own_try.format.height=UINT_MAX;
    if(call(sensor_fd,VIDIOC_SUBDEV_S_FMT,&own_try)<0)goto out;
    struct v4l2_subdev_format read_try={.which=V4L2_SUBDEV_FORMAT_TRY,.pad=0};
    if(call(sensor_fd,VIDIOC_SUBDEV_G_FMT,&read_try)<0 || memcmp(&read_try.format,&own_try.format,sizeof(own_try.format)))goto out;
    if(call(observer,VIDIOC_SUBDEV_G_FMT,&other_after)<0 || memcmp(&other_after.format,&other_try.format,sizeof(other_try.format)))goto out;
    struct v4l2_subdev_selection trial={.which=V4L2_SUBDEV_FORMAT_TRY,.pad=0,.target=V4L2_SEL_TGT_CROP,.r={.left=0,.top=0,.width=32,.height=32}};
    struct v4l2_subdev_selection other_crop={.which=V4L2_SUBDEV_FORMAT_TRY,.pad=0,.target=V4L2_SEL_TGT_CROP},other_crop_after=other_crop;
    if(call(observer,VIDIOC_SUBDEV_G_SELECTION,&other_crop)<0)goto out;
    if(call(sensor_fd,VIDIOC_SUBDEV_S_SELECTION,&trial)<0)goto out;
    struct v4l2_subdev_selection own_crop_after={.which=V4L2_SUBDEV_FORMAT_TRY,.pad=0,.target=V4L2_SEL_TGT_CROP};
    if(call(sensor_fd,VIDIOC_SUBDEV_G_SELECTION,&own_crop_after)<0 || memcmp(&own_crop_after.r,&trial.r,sizeof(trial.r)))goto out;
    if(call(sensor_fd,VIDIOC_SUBDEV_G_FMT,&read_try)<0 || read_try.format.width!=trial.r.width || read_try.format.height!=trial.r.height)goto out;
    if(call(observer,VIDIOC_SUBDEV_G_FMT,&other_after)<0 || memcmp(&other_after.format,&other_try.format,sizeof(other_try.format)))goto out;
    if(call(observer,VIDIOC_SUBDEV_G_SELECTION,&other_crop_after)<0 || memcmp(&other_crop_after.r,&other_crop.r,sizeof(other_crop.r)))goto out;
    if(call(sensor_fd,VIDIOC_SUBDEV_G_FMT,&after)<0 || call(sensor_fd,VIDIOC_SUBDEV_G_SELECTION,&crop_after)<0)goto out;
    if(memcmp(&before.format,&after.format,sizeof(before.format)) || memcmp(&crop.r,&crop_after.r,sizeof(crop.r)))goto out;
    puts("SENSOR_GEOMETRY_GUARD ACTIVE fmt/crop EBUSY unchanged, TRY independent while streaming PASS");
    result=0;
out:
    close(observer);
    if(result)errno=EIO;
    return result;
}

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

static int verify_frame_metadata(int fd, const struct v4l2_buffer *b)
{
    struct atomisp_frame_metadata m={.index=b->index,.sequence=b->sequence,
        .timestamp_us=(uint64_t)b->timestamp.tv_sec*1000000ULL+b->timestamp.tv_usec};
    struct atomisp_frame_metadata key=m;
    if(call(fd,ATOMISP_IOC_G_FRAME_METADATA,&m)<0)return -1;
    if(m.index!=key.index || m.sequence!=key.sequence || m.timestamp_us!=key.timestamp_us ||
       m.flags!=(b->flags&V4L2_BUF_FLAG_ERROR) || m.reserved || m.exp_id>250) {errno=EIO;return -1;}
    if(metadata_mode==ATOMISP_BUFFER_METADATA_STANDARD) {
        if(b->request_fd || b->reserved2 || (b->flags&V4L2_BUF_FLAG_REQUEST_FD)) {errno=EIO;return -1;}
    } else {
        unsigned wire=metadata_mode==ATOMISP_BUFFER_METADATA_ANDROID?m.exp_id<<16:m.exp_id;
        if(b->reserved!=wire || b->reserved2!=m.isp_config_id) {errno=EIO;return -1;}
    }
    struct atomisp_frame_metadata stale=key;stale.timestamp_us++;errno=0;
    if(call(fd,ATOMISP_IOC_G_FRAME_METADATA,&stale)!=-1 || errno!=EAGAIN){errno=EIO;return -1;}
    stale=key;stale.sequence++;errno=0;
    if(call(fd,ATOMISP_IOC_G_FRAME_METADATA,&stale)!=-1 || errno!=EAGAIN){errno=EIO;return -1;}
    if(b->sequence==0)printf("FRAME_METADATA mode=%u exp_id=%u config_id=%u timestamp_us=%llu PASS\n",
        metadata_mode,m.exp_id,m.isp_config_id,(unsigned long long)m.timestamp_us);
    return 0;
}

static int frames(struct capture *c, const char *phase)
{
    if(verify_sensor_geometry_guard()<0)return -1;
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
        if(verify_frame_metadata(c->fd,&b)<0)return -1;
        sequence = b.sequence;
        printf("%s frame=%u bytes=%u timestamp=%ld.%06ld\n", phase, b.sequence,
               b.bytesused, (long)b.timestamp.tv_sec, (long)b.timestamp.tv_usec);
        if (call(c->fd, VIDIOC_QBUF, &b) < 0) return -1;
        struct atomisp_frame_metadata invalid={.index=b.index,.sequence=b.sequence,
            .timestamp_us=(uint64_t)b.timestamp.tv_sec*1000000ULL+b.timestamp.tv_usec};
        errno=0;
        if(call(c->fd,ATOMISP_IOC_G_FRAME_METADATA,&invalid)!=-1 || errno!=EAGAIN){errno=EIO;return -1;}

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
    if ((argc != 4 && argc != 5) || uname(&uts) || strcmp(uts.release, "6.14.0-mipad2-integrated-r17")) {
        fprintf(stderr, "Usage: on r17 with camera idle, %s /dev/videoN fps /dev/sensor-subdevN\n", argv[0]);
        return 2;
    }
    metadata_mode=argc==5?(unsigned)atoi(argv[4]):0;
    if(metadata_mode>2)return 2;
    sensor_path=argv[3];
    sensor_fd=open(argv[3],O_RDWR|O_CLOEXEC);
    if(sensor_fd<0) { perror("sensor open");return 1; }
    struct capture a = {.fd = -1}, b = {.fd = -1};
    int observer = -1, result = 1;
    bool have_format = false;
    struct v4l2_format saved = {.type = V4L2_BUF_TYPE_VIDEO_CAPTURE};
    a.fd = open(argv[1], O_RDWR | O_NONBLOCK | O_CLOEXEC);
    if (a.fd < 0) goto out;
    if(call(a.fd,ATOMISP_IOC_S_BUFFER_METADATA_MODE,&metadata_mode)<0)goto out;
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
    if (b.fd < 0 || observer < 0) goto out;
    if(call(b.fd,ATOMISP_IOC_S_BUFFER_METADATA_MODE,&metadata_mode)<0 || start(&a)<0)goto out;
    unsigned switch_mode=metadata_mode==2?0:2;errno=0;
    if(call(a.fd,ATOMISP_IOC_S_BUFFER_METADATA_MODE,&switch_mode)!=-1 || errno!=EBUSY) {errno=EIO;goto out;}
    struct atomisp_frame_metadata missing={0};errno=0;
    if(call(observer,ATOMISP_IOC_G_FRAME_METADATA,&missing)!=-1 || errno!=EAGAIN) {errno=EIO;goto out;}

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
