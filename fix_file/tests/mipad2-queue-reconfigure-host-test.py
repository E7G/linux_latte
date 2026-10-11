#!/usr/bin/env python3
"""Extract actual queue fallback/setup; CSS/sensor/control/locks are stubs.

Tests format/timing/exposure preservation and every restoration-error path.
Does not establish hardware cadence or real firmware/DMA/locking behavior.
"""
from pathlib import Path
import subprocess,tempfile
repo=Path(__file__).resolve().parents[2]
if not (repo/'drivers').exists():repo=Path('/root/linux_latte-6.14-integrated')
s=(repo/'drivers/staging/media/atomisp/pci/atomisp_fops.c').read_text()
s=s[s.index('static int atomisp_queue_reconfigure('):s.index('\nstatic int atomisp_buf_init(')]
common=(repo/'drivers/staging/media/atomisp/pci/atomisp_common.h').read_text()
import re
defines='\n'.join(re.search(r'^#define '+n+r'\s+[^\n]+',common,re.M).group(0) for n in ['ATOMISP_DEFAULT_WIDTH','ATOMISP_DEFAULT_HEIGHT'])+'\n'
prelude=r'''
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <linux/videodev2.h>
#include <linux/v4l2-subdev.h>
#define ENOIOCTLCMD 515
#define ATOMISP_INPUT_STREAM_GENERAL 0
#define PAGE_ALIGN(x) (((x)+4095u)&~4095u)
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
struct mutex { unsigned int depth; };
static void mutex_lock(struct mutex *m) { assert(!m->depth);m->depth++; }
static void mutex_unlock(struct mutex *m) { assert(m->depth==1);m->depth--; }
#define lockdep_assert_held(m) assert((m)->depth==1)
struct v4l2_ctrl { int val; };
struct v4l2_ctrl_handler { struct v4l2_ctrl *exposure; };
struct v4l2_subdev { struct v4l2_ctrl_handler *ctrl_handler; bool get_frame_interval,set_frame_interval; };
struct atomisp_device { struct mutex mutex; struct {struct v4l2_subdev *camera;} inputs[2]; };
struct atomisp_sub_device { struct atomisp_device *isp; unsigned int input_curr; };
struct vb2_queue { int dummy; };
struct video_device { int dummy; };
struct ia_css_frame_info { int dummy; };
struct device { int dummy; };
struct atomisp_video_pipe { struct atomisp_sub_device *asd; struct v4l2_pix_format pix;
    struct vb2_queue vb_queue; struct video_device vdev; struct ia_css_frame_info frame_info; };
static struct atomisp_device isp;
static struct atomisp_sub_device asd;
static struct atomisp_video_pipe pipe_;
static struct v4l2_ctrl exposure;
static struct v4l2_ctrl_handler handler;
static struct v4l2_subdev sensor;
static struct v4l2_fract actual;
static struct v4l2_pix_format requested;
static int getter_error,setter_error,format_error,exposure_error,css_retry_error;
static unsigned int get_calls,set_calls,format_calls,exposure_calls,css_calls,stats_calls;
static bool css_ready;
static char events[100];
static void event(char x) { assert(isp.mutex.depth==1);size_t n=strlen(events);assert(n+1<sizeof(events));events[n]=x; }
#define v4l2_subdev_has_op(sd,pad,op) ((sd)->op)
static int sensor_call(struct v4l2_subdev *sd, bool set, struct v4l2_subdev_frame_interval *fi) {
    assert(sd==&sensor && fi->which==V4L2_SUBDEV_FORMAT_ACTIVE && !fi->pad);
    if (set) { event('s');set_calls++;if(setter_error)return setter_error;actual=fi->interval; }
    else { event('g');get_calls++;if(getter_error)return getter_error; }
    fi->interval=actual;return 0;
}
#define v4l2_subdev_call_state_active(sd,pad,op,fi) sensor_call(sd,#op[0]=='s',fi)
static struct v4l2_ctrl *v4l2_ctrl_find(struct v4l2_ctrl_handler *h, unsigned int id) {
    assert(id==V4L2_CID_EXPOSURE);return h->exposure;
}
static int v4l2_ctrl_g_ctrl(struct v4l2_ctrl *c) { event('e');return c->val; }
static int v4l2_ctrl_s_ctrl(struct v4l2_ctrl *c,int value) {
    event('E');exposure_calls++;assert(actual.numerator==1 && actual.denominator==15);
    if(exposure_error)return exposure_error;
    c->val=value;return 0;
}
static int atomisp_set_fmt(struct video_device *v,struct v4l2_format *f) {
    assert(v==&pipe_.vdev && f->type==V4L2_BUF_TYPE_VIDEO_CAPTURE);
    event('f');format_calls++;requested=f->fmt.pix;pipe_.pix=f->fmt.pix;
    actual=(struct v4l2_fract){1,60};exposure.val=20;css_ready=true;
    return format_error;
}
static int atomisp_get_css_frame_info(struct atomisp_sub_device *a,struct ia_css_frame_info *f) {
    assert(a==&asd && f==&pipe_.frame_info);event('c');css_calls++;
    return css_ready ? css_retry_error : -EINVAL;
}
static void atomisp_alloc_css_stat_bufs(struct atomisp_sub_device *a,unsigned int stream) {
    assert(a==&asd && stream==ATOMISP_INPUT_STREAM_GENERAL);event('a');stats_calls++;
}
'''
tests=r'''
static void reset(void) {
    memset(events,0,sizeof(events));memset(&isp,0,sizeof(isp));memset(&pipe_,0,sizeof(pipe_));
    asd=(struct atomisp_sub_device){.isp=&isp,.input_curr=1};pipe_.asd=&asd;
    exposure.val=300;handler.exposure=&exposure;
    sensor=(struct v4l2_subdev){.ctrl_handler=&handler,.get_frame_interval=true,.set_frame_interval=true};
    isp.inputs[1].camera=&sensor;actual=(struct v4l2_fract){1,15};
    pipe_.pix=(struct v4l2_pix_format){.width=1280,.height=720,.pixelformat=V4L2_PIX_FMT_YUV420,.sizeimage=1280*720*3/2};
    get_calls=set_calls=format_calls=exposure_calls=css_calls=stats_calls=0;css_ready=false;
    getter_error=setter_error=format_error=exposure_error=css_retry_error=0;
}
static int setup(void) {
    unsigned int count=8,planes=0,size=0;
    int ret=atomisp_queue_setup(&pipe_.vb_queue,&count,&planes,&size,NULL);
    assert(!isp.mutex.depth);
    if(!ret) {assert(count==8 && planes==1);assert(size==PAGE_ALIGN(pipe_.pix.sizeimage));}
    return ret;
}
int main(void) {
    unsigned int count=0;
    for(unsigned int cycle=0;cycle<10000;cycle++) {
        reset();assert(!setup());
        assert(!strcmp(events,"cgefsEca"));assert(format_calls==1 && get_calls==1 && set_calls==1 && exposure_calls==1);
        assert(requested.width==1280 && requested.height==720 && exposure.val==300 && actual.denominator==15);count++;
        reset();css_ready=true;assert(!setup());assert(!strcmp(events,"ca") && !format_calls);count++;
        reset();memset(&pipe_.pix,0,sizeof(pipe_.pix));assert(!setup());
        assert(requested.width==ATOMISP_DEFAULT_WIDTH && requested.height==ATOMISP_DEFAULT_HEIGHT && requested.pixelformat==V4L2_PIX_FMT_YUV420);count++;
        reset();sensor.get_frame_interval=false;assert(!setup());assert(!get_calls && !set_calls && !exposure_calls);count++;
        reset();sensor.set_frame_interval=false;assert(!setup());assert(!get_calls && !set_calls && !exposure_calls);count++;
        reset();getter_error=-ENOIOCTLCMD;assert(!setup());assert(!set_calls && !exposure_calls);count++;
        reset();getter_error=-EOPNOTSUPP;assert(!setup());assert(!set_calls && !exposure_calls);count++;
        reset();getter_error=-EIO;assert(setup()==-EIO);assert(!format_calls && !stats_calls);count++;
        reset();setter_error=-EIO;assert(setup()==-EIO);assert(!exposure_calls && !stats_calls);count++;
        reset();format_error=-EPIPE;assert(setup()==-EPIPE);assert(set_calls==1 && exposure.val==300 && !stats_calls);count++;
        reset();format_error=-EPIPE;setter_error=-EIO;assert(setup()==-EPIPE);assert(!exposure_calls && !stats_calls);count++;
        reset();exposure_error=-ERANGE;assert(setup()==-ERANGE);assert(!stats_calls && actual.denominator==15);count++;
        reset();css_retry_error=-EINVAL;assert(setup()==-EINVAL);assert(exposure.val==300 && actual.denominator==15 && !stats_calls);count++;
        reset();sensor.ctrl_handler=NULL;assert(!setup());assert(!exposure_calls && actual.denominator==15);count++;
        reset();handler.exposure=NULL;assert(!setup());assert(!exposure_calls && actual.denominator==15);count++;
    }
    printf("PASS %u queue-reconfiguration cases; real source, CSS/sensor/control/lock stubs\n",count);
}
'''
with tempfile.TemporaryDirectory(prefix='mipad2-queue-reconfigure-') as d:
    p=Path(d);(p/'test.c').write_text(defines+prelude+s+tests)
    subprocess.run(['gcc','-O1','-g','-Wall','-Wextra','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(p/'test.c'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
