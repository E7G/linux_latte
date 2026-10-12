"""Actual HBLANK registration, core call_op macro and T4 s_ctrl; PM/CCI stubs.

Not a real powered sensor, complete control framework or rollback proof.
"""
import os,re,subprocess,tempfile
from pathlib import Path
r=Path(os.environ.get('MIPAD2_REPO','/root/linux_latte-6.14-integrated'))
s=(r/'drivers/media/i2c/t4ka3.c').read_text()
start=s.index('static int t4ka3_s_ctrl('); brace=s.index('{',start);depth=1;end=brace+1
while depth:
    depth+=(s[end]=='{')-(s[end]=='}');end+=1
callback=s[start:end]
registration=re.search(r'ctrls->hblank\s*=\s*v4l2_ctrl_new_std\(hdl,\s*(\w+),\s*V4L2_CID_HBLANK,',s)
assert registration and registration[1] in ['ops','NULL']
assert 'ctrls->hblank->flags |= V4L2_CTRL_FLAG_READ_ONLY;' in s
arg=registration[1]
if os.environ.get('MIPAD2_METADATA_CONTROL_NEGATIVE'):arg='ops'
header=(r/'drivers/media/v4l2-core/v4l2-ctrls-priv.h').read_text()
macros=header[header.index('#define has_op('):header.index('\n\nstatic inline',header.index('#define has_op('))]
c=r'''
#include <assert.h>
#include <errno.h>
#include <linux/videodev2.h>
#include <stdbool.h>
#include <stdio.h>
struct v4l2_ctrl;
struct v4l2_ctrl_ops { int (*s_ctrl)(struct v4l2_ctrl *); };
struct v4l2_ctrl { unsigned id; int val; const struct v4l2_ctrl_ops *ops; };
struct v4l2_subdev { void *dev; };
struct v4l2_subdev_state { int dummy; };
struct v4l2_mbus_framefmt { unsigned width,height; };
struct t4ka3_data { struct v4l2_subdev sd; void *regmap; };
static struct t4ka3_data sensor;
static struct v4l2_subdev_state state;
static struct v4l2_mbus_framefmt fmt={1936,1456};
static int powered,usage,cci_calls,cci_errno;
static struct t4ka3_data *ctrl_to_t4ka3(struct v4l2_ctrl *c) { assert(c);return &sensor; }
static struct v4l2_subdev_state *v4l2_subdev_get_locked_active_state(struct v4l2_subdev *s) { assert(s==&sensor.sd);return &state; }
static struct v4l2_mbus_framefmt *v4l2_subdev_state_get_format(struct v4l2_subdev_state *s,unsigned pad) { assert(s==&state&&!pad);return &fmt; }
static int t4ka3_update_exposure_range(struct t4ka3_data *s,struct v4l2_mbus_framefmt *f) { assert(s==&sensor&&f==&fmt);return 0; }
static int pm_runtime_get_if_in_use(void *d) { (void)d;if(powered)usage++;return powered; }
static void pm_runtime_put(void *d) { (void)d;assert(usage>0);usage--; }
static int t4ka3_test_pattern(struct t4ka3_data *s,int v) { (void)s;(void)v;return 0; }
static int t4ka3_update_flip(struct v4l2_subdev *s,struct v4l2_mbus_framefmt *f,int v,unsigned bit) { (void)s;(void)f;(void)v;(void)bit;return 0; }
static int t4ka3_color_gain_configure(struct t4ka3_data *s) { (void)s;return 0; }
#define T4KA3_REG_FRAME_LENGTH_LINES 1
#define T4KA3_REG_COARSE_INTEGRATION_TIME 2
#define T4KA3_REG_GLOBAL_GAIN 3
#define T4KA3_VFLIP_BIT 1
#define T4KA3_HFLIP_BIT 2
static int cci_write(void *map,unsigned reg,unsigned val,void *err) { (void)map;(void)reg;(void)val;(void)err;cci_calls++;return cci_errno; }
'''+macros+'\n'+callback+r'''
static const struct v4l2_ctrl_ops ctrl_ops={.s_ctrl=t4ka3_s_ctrl};
static struct v4l2_ctrl make_metadata(void) {
 const struct v4l2_ctrl_ops *ops=&ctrl_ops;
 (void)ops;
 return (struct v4l2_ctrl){.id=V4L2_CID_HBLANK,.val=1504,.ops=REGISTRATION_OPS};
}
int main(void) {
 unsigned cases=0;
 for(powered=0;powered<2;powered++) {
  for(int width=2;width<=3280;width+=2) {
   struct v4l2_ctrl hblank=make_metadata();hblank.val=3440-width;
   cci_errno=-EIO;int old=cci_calls;
   assert(call_op(&hblank,s_ctrl)==0);
   assert(cci_calls==old&&usage==0);cases++;
  }
 }
 powered=1;
 for(int err=-5;err<=0;err++) {
  struct v4l2_ctrl exposure={.id=V4L2_CID_EXPOSURE,.val=800,.ops=&ctrl_ops};
  cci_errno=err;int old=cci_calls;
  assert(call_op(&exposure,s_ctrl)==err&&cci_calls==old+1&&usage==0);cases++;
 }
 assert(cases==3286);
 puts("PASS 3286 actual HBLANK-registration/core-call_op/T4-callback cases; PM/CCI stubs, genuine exposure errors retained, no hardware/full rollback proof");
}
'''
c=c.replace('REGISTRATION_OPS',arg)
with tempfile.TemporaryDirectory(prefix='mp2-t4-metadata-host-') as t:
    src=Path(t)/'test.c';binary=Path(t)/'test';src.write_text(c)
    subprocess.run(['gcc','-O2','-Wall','-Wextra','-Werror',str(src),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
