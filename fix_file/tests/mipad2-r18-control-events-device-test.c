/* R18-only idle sensor control-event test. No video stream or geometry edits.
 * Caller must keep camera clients closed and snapshot other controls.
 */
#include <errno.h>
#include <fcntl.h>
#include <linux/videodev2.h>
#include <poll.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/utsname.h>
#include <unistd.h>

static int call(int fd, unsigned long op, void *arg)
{
    int ret;
    do { ret = ioctl(fd, op, arg); } while (ret < 0 && errno == EINTR);
    return ret;
}

static int empty(int fd)
{
    struct v4l2_event ev = {0};
    /* Linux 6.14 v4l2_event_dequeue(nonblocking) uses ENOENT, not EAGAIN. */
    errno = 0;
    if (call(fd, VIDIOC_DQEVENT, &ev) != -1 || errno != ENOENT)
        return -1;
    struct pollfd p = {.fd=fd, .events=POLLPRI};
    if (poll(&p, 1, 0) != 0)
        return -1;
    return 0;
}

static int event(int fd, int expected, struct v4l2_event *last, bool first)
{
    struct pollfd p = {.fd=fd, .events=POLLPRI};
    int ret;
    do { ret = poll(&p, 1, 2000); } while (ret < 0 && errno == EINTR);
    if (ret != 1 || !(p.revents & POLLPRI))
        return -1;
    struct v4l2_event ev = {0};
    if (call(fd, VIDIOC_DQEVENT, &ev) < 0 ||
        ev.type != V4L2_EVENT_CTRL || ev.id != V4L2_CID_EXPOSURE ||
        ev.u.ctrl.type != V4L2_CTRL_TYPE_INTEGER || ev.u.ctrl.value != expected ||
        ev.timestamp.tv_nsec < 0 || ev.timestamp.tv_nsec >= 1000000000)
        return -1;
    for (unsigned i=0; i<sizeof(ev.reserved)/sizeof(ev.reserved[0]); ++i)
        if (ev.reserved[i])
            return -1;
    if (!first && (ev.sequence <= last->sequence ||
        ev.timestamp.tv_sec < last->timestamp.tv_sec ||
        (ev.timestamp.tv_sec == last->timestamp.tv_sec && ev.timestamp.tv_nsec < last->timestamp.tv_nsec)))
        return -1;
    *last=ev;
    printf("EVENT fd=%d sequence=%u exposure=%d timestamp=%lld.%09ld\n",
        fd,ev.sequence,ev.u.ctrl.value,(long long)ev.timestamp.tv_sec,ev.timestamp.tv_nsec);
    return empty(fd);
}

#define CHECK(expr) do { if (!(expr)) { fprintf(stderr,"FAIL line %d: %s (errno=%d)\n",__LINE__,#expr,errno); goto out; } } while (0)

int main(int argc, char **argv)
{
    struct utsname uts;
    if (argc != 2 || uname(&uts) || strcmp(uts.release,"6.14.0-mipad2-integrated-r18")) {
        fprintf(stderr,"R18-only idle control-event test; no device opened\n");
        return 2;
    }
    int w=-1,a=-1,b=-1,result=1;
    bool have_original=false;
    struct v4l2_control original={.id=V4L2_CID_EXPOSURE};
    struct v4l2_event_subscription sub={.type=V4L2_EVENT_CTRL,.id=V4L2_CID_EXPOSURE,
        .flags=V4L2_EVENT_SUB_FL_SEND_INITIAL};
    struct v4l2_queryctrl range={.id=V4L2_CID_EXPOSURE};
    struct v4l2_event ea={0},eb={0};
    w=open(argv[1],O_RDWR|O_NONBLOCK|O_CLOEXEC);
    a=open(argv[1],O_RDWR|O_NONBLOCK|O_CLOEXEC);
    b=open(argv[1],O_RDWR|O_NONBLOCK|O_CLOEXEC);
    CHECK(w>=0 && a>=0 && b>=0);
    CHECK(call(w,VIDIOC_G_CTRL,&original)==0);have_original=true;
    CHECK(call(w,VIDIOC_QUERYCTRL,&range)==0 && range.step>0);
    int alternate=original.value<=range.maximum-range.step ? original.value+range.step : original.value-range.step;
    CHECK(alternate>=range.minimum && alternate<=range.maximum && alternate!=original.value);
    CHECK(call(a,VIDIOC_SUBSCRIBE_EVENT,&sub)==0 && call(b,VIDIOC_SUBSCRIBE_EVENT,&sub)==0);
    CHECK(event(a,original.value,&ea,true)==0 && event(b,original.value,&eb,true)==0);
    struct v4l2_control changed={.id=V4L2_CID_EXPOSURE,.value=alternate};
    CHECK(call(w,VIDIOC_S_CTRL,&changed)==0 && changed.value==alternate);
    CHECK(event(a,alternate,&ea,false)==0 && event(b,alternate,&eb,false)==0);
    CHECK(call(w,VIDIOC_S_CTRL,&changed)==0);
    CHECK(empty(a)==0 && empty(b)==0); /* Unchanged value generates no new event. */
    CHECK(call(a,VIDIOC_UNSUBSCRIBE_EVENT,&sub)==0);
    CHECK(call(w,VIDIOC_S_CTRL,&original)==0);
    CHECK(empty(a)==0 && event(b,original.value,&eb,false)==0);
    CHECK(call(b,VIDIOC_UNSUBSCRIBE_EVENT,&sub)==0 && empty(b)==0);
    result=0;
out:
    if (have_original && w>=0) {
        struct v4l2_control restored={.id=V4L2_CID_EXPOSURE};
        if (call(w,VIDIOC_S_CTRL,&original)<0 || call(w,VIDIOC_G_CTRL,&restored)<0 || restored.value!=original.value) {
            fprintf(stderr,"Exposure restoration failed\n");result=1;
        }
    }
    if (a>=0) close(a);
    if (b>=0) close(b);
    if (w>=0) close(w);
    if (!result) puts("PASS per-fd initial/change events, poll wakeup, increasing sequence/time, unchanged-value silence, unsubscribe isolation and exposure restoration");
    return result;
}
