"""Compile actual sensor flag assignments and core event dispatch, with helper stubs.

This verifies wiring, not real event queues, waiters, hardware or 3A.
"""
from pathlib import Path
import os,re,subprocess,tempfile
repo=Path(os.environ.get('MIPAD2_REPO','/root/linux_latte-6.14-integrated'))
core=(repo/'drivers/media/v4l2-core/v4l2-subdev.c').read_text()
dispatch=core[core.index('\tcase VIDIOC_DQEVENT:'):core.index('\n#ifdef CONFIG_VIDEO_ADV_DEBUG',core.index('\tcase VIDIOC_DQEVENT:'))]
assignments=[]
for name,var in [('ov5693','ov5693'),('t4ka3','sensor')]:
    source=(repo/f'drivers/media/i2c/{name}.c').read_text()
    match=re.findall(rf'\b{var}->sd\.flags\s*\|=\s*[^;]+;',source)
    assert len(match)==1,match
    ops=re.search(rf'static const struct v4l2_subdev_ops {name}_ops = \{{(.*?)\n\}};',source,re.S)
    assert ops and '.core' not in ops[1], 'New custom callbacks require an expanded test'
    statement=match[0]
    if os.environ.get('MIPAD2_SENSOR_EVENTS_NEGATIVE')==name:
        statement=re.sub(r'\|\s*V4L2_SUBDEV_FL_HAS_EVENTS','',statement)
    assignments.append('static unsigned flags_'+name+'(void) { struct sensor mock={0}; struct sensor *'+var+'=&mock; '+statement+' return mock.sd.flags; }')
prefix=r'''
#include <assert.h>
#include <stdbool.h>
#include <fcntl.h>
#include <linux/videodev2.h>
#include <stdio.h>
#define V4L2_SUBDEV_FL_HAS_DEVNODE (1U<<2)
#define V4L2_SUBDEV_FL_HAS_EVENTS (1U<<3)
#define ENOIOCTLCMD 515
struct sd { unsigned flags; };
struct sensor { struct sd sd; };
struct fh { void *ctrl_handler; };
struct file { int f_flags; };
static int deq_calls,sub_calls,unsub_calls;
static bool nonblock;
static int v4l2_event_dequeue(struct fh *f, void *a, bool nb) { assert(f&&a);deq_calls++;nonblock=nb;return 17; }
static int v4l2_ctrl_subdev_subscribe_event(struct sd *s,struct fh *f,void *a) { assert(s&&f&&f->ctrl_handler&&a);sub_calls++;return 19; }
static int v4l2_event_subdev_unsubscribe(struct sd *s,struct fh *f,void *a) { assert(s&&f&&a);unsub_calls++;return 13; }
#define v4l2_subdev_has_op(sd,group,op) false
#define v4l2_subdev_call(sd,group,op,fh,arg) (-99)
static int ioctl_events(struct sd *sd,struct fh *vfh,struct file *file,unsigned cmd,void *arg) {
 switch(cmd) {
'''
suffix=r'''
 default:return -1;
 }
}
int main(void) {
 unsigned flags[]={flags_ov5693(),flags_t4ka3()};
 unsigned cases=0;
 for(unsigned i=0;i<2;i++) {
   assert(flags[i]&V4L2_SUBDEV_FL_HAS_DEVNODE);
   struct sd s={.flags=flags[i]};struct fh f={.ctrl_handler=&s};struct file file={.f_flags=O_NONBLOCK};int arg=0;
   assert(ioctl_events(&s,&f,&file,VIDIOC_SUBSCRIBE_EVENT,&arg)==19);cases++;
   assert(ioctl_events(&s,&f,&file,VIDIOC_DQEVENT,&arg)==17&&nonblock);cases++;
   file.f_flags=0;
   assert(ioctl_events(&s,&f,&file,VIDIOC_DQEVENT,&arg)==17&&!nonblock);cases++;
   assert(ioctl_events(&s,&f,&file,VIDIOC_UNSUBSCRIBE_EVENT,&arg)==13);cases++;
   f.ctrl_handler=NULL;
   assert(ioctl_events(&s,&f,&file,VIDIOC_SUBSCRIBE_EVENT,&arg)==-ENOIOCTLCMD);cases++;
   s.flags&=~V4L2_SUBDEV_FL_HAS_EVENTS;
   int old_deq=deq_calls,old_sub=sub_calls,old_unsub=unsub_calls;
   assert(ioctl_events(&s,&f,&file,VIDIOC_DQEVENT,&arg)==-ENOIOCTLCMD);cases++;
   assert(ioctl_events(&s,&f,&file,VIDIOC_SUBSCRIBE_EVENT,&arg)==-ENOIOCTLCMD);cases++;
   assert(ioctl_events(&s,&f,&file,VIDIOC_UNSUBSCRIBE_EVENT,&arg)==-ENOIOCTLCMD);cases++;
   assert(deq_calls==old_deq&&sub_calls==old_sub&&unsub_calls==old_unsub);cases++;
 }
 assert(cases==18&&deq_calls==4&&sub_calls==2&&unsub_calls==2);
 puts("PASS 18 actual sensor-flag/core-event-dispatch wiring checks; helper stubs, no real event queue/I2C/3A proof");
}
'''
header=(repo/'include/media/v4l2-subdev.h').read_text()
for name in ['V4L2_SUBDEV_FL_HAS_DEVNODE','V4L2_SUBDEV_FL_HAS_EVENTS']:
    actual=re.search(r'^#define\s+'+name+r'\s+[^\n]+',header,re.M)
    assert actual
    prefix=re.sub(r'^#define\s+'+name+r'\s+[^\n]+',actual[0],prefix,flags=re.M)
source=prefix+dispatch+suffix
source=source.replace('static int ioctl_events(', '\n'.join(assignments)+'\nstatic int ioctl_events(',1)
with tempfile.TemporaryDirectory(prefix='mp2-events-host-') as tmp:
    c=Path(tmp)/'test.c';binary=Path(tmp)/'test';c.write_text(source)
    subprocess.run(['gcc','-O2','-Wall','-Wextra','-Werror',str(c),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
