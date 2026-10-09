"""Host test actual AtomISP G/S_PARM functions, with sensor/control stubs."""
import pathlib
import re
import subprocess
import tempfile

repo = pathlib.Path(__file__).resolve().parents[2]
if not (repo / 'drivers').exists():
    repo = pathlib.Path('/root/linux_latte-6.14-integrated')
source = (repo / 'drivers/staging/media/atomisp/pci/atomisp_ioctl.c').read_text()
start = source.index('static int atomisp_g_parm(')
end = source.index('\nstatic long atomisp_vidioc_default', start)
functions = source[start:end]
prelude = r'''
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <linux/videodev2.h>
#include <linux/v4l2-subdev.h>
typedef uint64_t u64;
#define ENOIOCTLCMD 515
struct v4l2_ctrl { int val; };
struct v4l2_subdev { bool get_frame_interval, set_frame_interval; };
struct video_device { unsigned int device_caps; };
struct file { int unused; };
struct atomisp_sub_device { unsigned int input_curr; struct v4l2_ctrl *run_mode; bool high_speed_mode; };
struct atomisp_device { struct { struct v4l2_subdev *camera; } inputs[2]; };
struct pipe { struct atomisp_sub_device *asd; };
static struct video_device video;
static struct atomisp_device isp;
static struct atomisp_sub_device asd;
static struct pipe pipe_;
static int mode_error, sensor_error, set_calls;
static struct v4l2_fract actual = {1,30};
static struct video_device *video_devdata(struct file *file) { (void)file; return &video; }
static struct pipe *atomisp_to_video_pipe(struct video_device *vdev) { (void)vdev; return &pipe_; }
static struct atomisp_device *video_get_drvdata(struct video_device *vdev) { (void)vdev; return &isp; }
static int v4l2_ctrl_s_ctrl(struct v4l2_ctrl *ctrl, int mode) { if (mode_error) return mode_error; ctrl->val=mode; return 0; }
#define v4l2_subdev_has_op(sensor,pad,op) ((sensor)->op)
static int sensor_call(struct v4l2_subdev *sensor, bool set, struct v4l2_subdev_frame_interval *fi) {
    (void)sensor;
    assert(fi->which == V4L2_SUBDEV_FORMAT_ACTIVE && !fi->pad);
    if (sensor_error) return sensor_error;
    if (set) {
        set_calls++;
        if (!fi->interval.numerator || !fi->interval.denominator) actual=(struct v4l2_fract){1,30};
        else actual=fi->interval;
    }
    fi->interval=actual;
    return 0;
}
#define v4l2_subdev_call_state_active(sensor,pad,op,fi) sensor_call(sensor, #op[0]=='s', fi)
'''
header = (repo / 'drivers/staging/media/atomisp/include/linux/atomisp.h').read_text()
for name in ['CI_MODE_VIDEO', 'CI_MODE_STILL_CAPTURE', 'CI_MODE_PREVIEW',
             'ATOMISP_RUN_MODE_VIDEO', 'ATOMISP_RUN_MODE_STILL_CAPTURE', 'ATOMISP_RUN_MODE_PREVIEW']:
    prelude += re.search(r'^#define ' + name + r'[ \t]+[^\n]+', header, re.M).group(0) + '\n'
tests = r'''
static void clean(struct v4l2_streamparm *p, bool timed) {
    assert(p->type==V4L2_BUF_TYPE_VIDEO_CAPTURE);
    assert(!p->parm.capture.capturemode && !p->parm.capture.extendedmode);
    assert(p->parm.capture.readbuffers == ((video.device_caps & V4L2_CAP_READWRITE) ? 2u : 0u));
    assert(p->parm.capture.capability == (timed ? V4L2_CAP_TIMEPERFRAME : 0u));
    for (unsigned int i=0;i<4;i++) assert(!p->parm.capture.reserved[i]);
    for (unsigned int i=sizeof(p->parm.capture);i<sizeof(p->parm);i++) assert(!p->parm.raw_data[i]);
}
int main(void) {
    struct file file={0};
    struct v4l2_ctrl mode={ATOMISP_RUN_MODE_PREVIEW};
    struct v4l2_subdev sensor={true,true};
    isp.inputs[0].camera=&sensor; isp.inputs[1].camera=&sensor;
    asd.run_mode=&mode; pipe_.asd=&asd;
    unsigned int count=0;
    for (unsigned int input=0;input<2;input++) {
        asd.input_curr=input;
        for (unsigned int rw=0;rw<2;rw++) {
            video.device_caps=rw ? V4L2_CAP_READWRITE : 0;
            struct v4l2_streamparm p;
            memset(&p,0xff,sizeof(p)); p.type=V4L2_BUF_TYPE_VIDEO_CAPTURE;
            assert(!atomisp_g_parm(&file,NULL,&p)); clean(&p,true);
            assert(p.parm.capture.timeperframe.numerator==actual.numerator);
            assert(p.parm.capture.timeperframe.denominator==actual.denominator);
            count++;
            for (unsigned int flags=0;flags<3;flags++) {
                memset(&p,0xff,sizeof(p)); p.type=V4L2_BUF_TYPE_VIDEO_CAPTURE;
                p.parm.capture.capturemode=flags==0 ? 0 : flags==1 ? V4L2_MODE_HIGHQUALITY : UINT32_MAX;
                p.parm.capture.timeperframe=(struct v4l2_fract){1,60};
                int saved=mode.val;
                assert(!atomisp_s_parm(&file,NULL,&p)); clean(&p,true);
                assert(mode.val==saved && asd.high_speed_mode);
                assert(p.parm.capture.timeperframe.denominator==60);
                count++;
                p.parm.capture.timeperframe=(struct v4l2_fract){0,1};
                assert(!atomisp_s_parm(&file,NULL,&p)); clean(&p,true);
                assert(!asd.high_speed_mode && p.parm.capture.timeperframe.denominator==30);
                count++;
            }
            unsigned int ci[]={CI_MODE_VIDEO,CI_MODE_STILL_CAPTURE,CI_MODE_PREVIEW};
            int modes[]={ATOMISP_RUN_MODE_VIDEO,ATOMISP_RUN_MODE_STILL_CAPTURE,ATOMISP_RUN_MODE_PREVIEW};
            for (unsigned int i=0;i<3;i++) {
                memset(&p,0xff,sizeof(p)); p.type=V4L2_BUF_TYPE_VIDEO_CAPTURE;
                p.parm.capture.capturemode=ci[i];
                int calls=set_calls;
                assert(!atomisp_s_parm(&file,NULL,&p)); clean(&p,true);
                assert(mode.val==modes[i] && set_calls==calls && !asd.high_speed_mode);
                count++;
            }
        }
    }
    struct v4l2_streamparm p={.type=V4L2_BUF_TYPE_VIDEO_OUTPUT};
    assert(atomisp_g_parm(&file,NULL,&p)==-EINVAL);
    assert(atomisp_s_parm(&file,NULL,&p)==-EINVAL); count+=2;
    p.type=V4L2_BUF_TYPE_VIDEO_CAPTURE; p.parm.capture.capturemode=0;
    sensor_error=-EIO;
    assert(atomisp_g_parm(&file,NULL,&p)==-EIO);
    assert(atomisp_s_parm(&file,NULL,&p)==-EIO); count+=2;
    sensor_error=0; mode_error=-EBUSY; p.parm.capture.capturemode=CI_MODE_VIDEO;
    assert(atomisp_s_parm(&file,NULL,&p)==-EBUSY); count++;
    mode_error=0; sensor.set_frame_interval=false;
    p.parm.capture.capturemode=0;
    assert(!atomisp_s_parm(&file,NULL,&p)); clean(&p,false); count++;
    sensor.get_frame_interval=false;
    assert(!atomisp_g_parm(&file,NULL,&p)); clean(&p,false);
    assert(!p.parm.capture.timeperframe.numerator && !p.parm.capture.timeperframe.denominator); count++;
    printf("PASS %u stream-parameter cases; actual AtomISP functions, stubbed subdevices/controls\n",count);
}
'''
with tempfile.TemporaryDirectory(prefix='mipad2-atomisp-parm-test-') as temp:
    path = pathlib.Path(temp)
    (path / 'test.c').write_text(prelude + functions + tests)
    subprocess.run(['gcc', '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-fsanitize=undefined,address', '-fno-sanitize-recover=all', str(path / 'test.c'), '-o', str(path / 'test')], check=True)
    subprocess.run([str(path / 'test')], check=True)
