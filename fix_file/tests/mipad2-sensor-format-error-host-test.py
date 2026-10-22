#!/usr/bin/env python3
"""Extract actual Atomisp sensor/crop/CSI helper; fault-return/lock stubs only.

Does not prove real PM/I2C, streaming or complete ACTIVE-state rollback.
"""
from pathlib import Path
import os,re,subprocess,tempfile
r=Path(__file__).resolve().parents[2]
if not(r/'drivers').exists():r=Path('/root/linux_latte-6.14-integrated')
s=(r/'drivers/staging/media/atomisp/pci/atomisp_cmd.c').read_text()
m=re.search(r'static int atomisp_set_sensor_crop_and_fmt\([^;{}]*\)\s*\{',s);assert m
n=m.end();depth=1
while depth:depth+=(s[n]=='{')-(s[n]=='}');n+=1
function=s[m.start():n]
if os.environ.get('MIPAD2_SENSOR_FORMAT_NEGATIVE'):
    # Mutate only the extracted C: swallow the sensor set_fmt errno.
    # The real candidate file is not changed by this negative control.
    anchor='ret = v4l2_subdev_call(input->sensor, pad, set_fmt, sd_state, &format);'
    assert function.count(anchor)==1
    function=function.replace(anchor,anchor+'\n\t\tret = 0;')
base=r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <linux/v4l2-subdev.h>
#define min(a,b) ((a)<(b)?(a):(b))
struct v4l2_subdev_state { int locked; };
struct v4l2_subdev { int kind; struct v4l2_subdev_state *active_state; };
struct atomisp_input_subdev {
 struct v4l2_subdev *sensor,*sensor_isp,*csi_port; bool crop_support,binning_support;
 struct v4l2_rect native_rect; struct v4l2_subdev_state *try_sd_state;
};
struct atomisp_device { struct atomisp_input_subdev inputs[1]; struct { unsigned input_curr; } asd; void *dev; };
static int power_error,crop_error,format_error,csi_error;
static int isp_sink_error,isp_source_error,isp_sink_calls,isp_source_calls;
static struct v4l2_subdev_state isp_state;
#define SENSOR_ISP_PAD_SINK 0
#define SENSOR_ISP_PAD_SOURCE 1
#define CSI2_PAD_SINK 0
#define dev_dbg(...) ((void)0)
static int power_calls,crop_calls,format_calls,csi_calls,lock_calls,unlock_calls,log_calls;
static struct v4l2_subdev_state *expected_state;
static struct v4l2_rect expected_crop;
static void v4l2_subdev_lock_state(struct v4l2_subdev_state *s) {
 assert((s==expected_state || s==&isp_state) && !s->locked);s->locked=1;lock_calls++;
}
static void v4l2_subdev_unlock_state(struct v4l2_subdev_state *s) {
 assert((s==expected_state || s==&isp_state) && s->locked);s->locked=0;unlock_calls++;
}
static struct v4l2_subdev_state *v4l2_subdev_lock_and_get_active_state(struct v4l2_subdev *sd) {
 assert(sd->kind==3);v4l2_subdev_lock_state(&isp_state);return &isp_state;
}
static int atomisp_s_sensor_power(struct atomisp_device *isp,unsigned index,int on) {
 assert(isp->asd.input_curr==index && on==1);power_calls++;return power_error;
}
#define dev_err(...) ((void)log_calls++)
static int stub_set_selection(struct v4l2_subdev *sd,struct v4l2_subdev_state *state,struct v4l2_subdev_selection *sel) {
 assert(sd->kind==1 && state==expected_state);
 assert(!state || state->locked);
 assert(!memcmp(&sel->r,&expected_crop,sizeof(sel->r)));
 crop_calls++;return crop_error;
}
static int stub_set_fmt(struct v4l2_subdev *sd,struct v4l2_subdev_state *state,struct v4l2_subdev_format *fmt) {
 if(sd->kind==3) {
  assert(state==&isp_state && state->locked);
  if(fmt->pad==SENSOR_ISP_PAD_SINK){isp_sink_calls++;return isp_sink_error;}
  assert(fmt->pad==SENSOR_ISP_PAD_SOURCE);isp_source_calls++;return isp_source_error;
 }
 if(sd->kind==1) {
  assert(state==expected_state && (!state || state->locked));format_calls++;
  /* Mimic a callback modifying its argument even when returning an error. */
  fmt->format.width=602;fmt->format.height=402;
  return format_error;
 }
 assert(sd->kind==2 && !state && !expected_state->locked);
 csi_calls++;
 assert(fmt->format.width==602 && fmt->format.height==402);
 return csi_error;
}
#define v4l2_subdev_call(sd,group,op,state,arg) stub_##op(sd,state,arg)
'''
# CSI lock check also supports legacy/no-state callbacks.
base=base.replace('!expected_state->locked','(!expected_state || !expected_state->locked)')
cases=r'''
int main(void) {
 const int errors[]={0,-EIO,-EREMOTEIO,-ETIMEDOUT,-EINVAL};
 const unsigned geometry[][2]={{16,12},{1300,700},{3000,2500},{2592,1944}};
 unsigned cases=0;
 for(int isp_kind=0;isp_kind<4;isp_kind++)
 for(int active=0;active<2;active++)
 for(int crop=0;crop<2;crop++)
 for(int bin=0;bin<2;bin++)
 for(int has_state=0;has_state<2;has_state++)
 for(unsigned shape=0;shape<4;shape++)
 for(unsigned pe=0;pe<5;pe++)
 for(unsigned ce=0;ce<5;ce++)
 for(unsigned fe=0;fe<5;fe++)
 for(unsigned ie=0;ie<5;ie++) {
  power_error=errors[pe];crop_error=errors[ce];format_error=errors[fe];csi_error=errors[ie];
  power_calls=crop_calls=format_calls=csi_calls=lock_calls=unlock_calls=log_calls=0;
  isp_sink_error=isp_kind==2?-ENOSPC:0;isp_source_error=isp_kind==3?-EPIPE:0;
  isp_sink_calls=isp_source_calls=0;isp_state.locked=0;
  struct v4l2_subdev_state act={0},trial={0};
  expected_state=has_state?(active?&act:&trial):NULL;
  struct v4l2_subdev sensor={.kind=1,.active_state=has_state?&act:NULL},csi={.kind=2},sensor_isp={.kind=3};
  struct atomisp_device isp={.inputs={{.sensor=&sensor,.sensor_isp=isp_kind?&sensor_isp:NULL,.csi_port=&csi,
   .crop_support=crop,.binning_support=bin,.native_rect={.width=2624,.height=1956},.try_sd_state=has_state?&trial:NULL}}};
  struct v4l2_mbus_framefmt before={.width=geometry[shape][0],.height=geometry[shape][1],.code=0x3007},actual=before;
  unsigned w=before.width,h=before.height;
  if(bin && w<=1312 && h<=978) {w*=2;h*=2;}
  w=min(w,2624u);h=min(h,1956u);
  expected_crop=(struct v4l2_rect){.left=((2624-w)/2)&~1u,.top=((1956-h)/2)&~1u,.width=w,.height=h};
  int expected_error=active?power_error:0;
  if(!expected_error && crop)expected_error=crop_error;
  if(!expected_error)expected_error=format_error;
  int sensor_error=expected_error;
  bool isp_reached=active && isp_kind && !sensor_error;
  if(isp_reached)expected_error=isp_sink_error?isp_sink_error:isp_source_error;
  if(!expected_error && active)expected_error=csi_error;
  int ret=atomisp_set_sensor_crop_and_fmt(&isp,&actual,active?V4L2_SUBDEV_FORMAT_ACTIVE:V4L2_SUBDEV_FORMAT_TRY);
  assert(ret==expected_error);
  assert(power_calls==active);
  bool reached=!(active && power_error);
  assert(lock_calls==(reached && has_state)+isp_reached);assert(unlock_calls==lock_calls);
  assert(!act.locked && !trial.locked && !isp_state.locked);
  assert(isp_sink_calls==isp_reached);assert(isp_source_calls==(isp_reached && !isp_sink_error));
  assert(crop_calls==(reached && crop));
  assert(format_calls==(reached && (!crop || !crop_error)));
  assert(csi_calls==(active && !sensor_error && (!isp_reached || (!isp_sink_error && !isp_source_error))));
  assert(log_calls==(reached && crop && crop_error!=0));
  if(ret)assert(!memcmp(&actual,&before,sizeof(before)));
  else assert(actual.width==602 && actual.height==402);
  cases++;
 }
 struct atomisp_device absent={0};struct v4l2_mbus_framefmt fmt={.width=640,.height=480};
 assert(atomisp_set_sensor_crop_and_fmt(&absent,&fmt,V4L2_SUBDEV_FORMAT_ACTIVE)==-EINVAL);
 printf("PASS %u actual sensor/crop/CSI helper fault-return cases; sensor errno retained, locks balanced, CSI suppressed after sensor error; stubs not hardware/rollback proof\n",cases);
}
'''
with tempfile.TemporaryDirectory(prefix='mipad2-sensor-format-') as temp:
 p=Path(temp);(p/'test.c').write_text(base+function+cases)
 subprocess.run(['gcc','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-Wno-sign-compare',
  '-fsanitize=address,undefined','-fno-omit-frame-pointer','-no-pie',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
