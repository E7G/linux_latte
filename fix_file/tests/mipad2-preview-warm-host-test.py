#!/usr/bin/env python3
"""Real negotiation/stream functions with sensor, PM and CCI stubs.

Not evidence of real sensor I/O, runtime PM, DMA or firmware selection.
"""
from pathlib import Path
import os,re,subprocess,tempfile
repo=Path(__file__).resolve().parents[2]
if not (repo/'drivers').is_dir():repo=Path('/root/linux_latte-6.14-integrated')
ov=(repo/'drivers/media/i2c/ov5693.c').read_text()
cmd=(repo/'drivers/staging/media/atomisp/pci/atomisp_cmd.c').read_text()
def function(src,name):
    matches=list(re.finditer(r'(?:static\s+)?int\s+'+name+r'\([^;{}]*\)\s*\{',src))
    assert len(matches)==1,(name,len(matches))
    start=matches[0].start()
    a=matches[0].end()-1;depth=1;b=a+1
    while depth:
        if src[b]=='{':depth+=1
        if src[b]=='}':depth-=1
        b+=1
    return src[start:b]+'\n'
base=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <linux/videodev2.h>
#include <linux/v4l2-mediabus.h>
#define CCI_REG8(x) (x)
#define CCI_REG16(x) (x)
#define BIT(n) (1U << (n))
'''
names=['OV5693_CROP_START_X_REG','OV5693_CROP_START_Y_REG','OV5693_CROP_END_X_REG','OV5693_CROP_END_Y_REG',
       'OV5693_OUTPUT_SIZE_X_REG','OV5693_OUTPUT_SIZE_Y_REG','OV5693_TIMING_HTS_REG','OV5693_FIXED_PPL',
       'OV5693_TIMING_VTS_REG','OV5693_OFFSET_START_X_REG','OV5693_OFFSET_START_Y_REG',
       'OV5693_SUB_INC_X_REG','OV5693_SUB_INC_Y_REG','OV5693_FORMAT1_REG','OV5693_FORMAT2_REG',
       'OV5693_FORMAT1_VBIN_EN','OV5693_FORMAT2_HBIN_EN','OV5693_SW_STREAM_REG','OV5693_START_STREAMING','OV5693_STOP_STREAMING']
macros='\n'.join(re.search(r'^#define '+n+r'\s+[^\n]+',ov,re.M).group(0) for n in names)+'\n'
stream=r'''
struct mutex { int held; };
static void mutex_lock(struct mutex *m) { assert(!m->held); m->held=1; }
static void mutex_unlock(struct mutex *m) { assert(m->held); m->held=0; }
struct ov5693_mode { struct v4l2_mbus_framefmt format; struct v4l2_rect crop;
 unsigned inc_x_odd,inc_y_odd; bool binning_x,binning_y; };
struct ov5693_device;
struct device { struct ov5693_device *sensor; int users; bool powered; };
struct regmap { struct ov5693_device *sensor; unsigned regs[0x4000],calls; };
struct handler { struct ov5693_device *sensor; unsigned calls; };
struct ov5693_device { struct device *dev; struct regmap *regmap; struct mutex lock;
 struct ov5693_mode mode; struct { struct handler handler; } ctrls; bool streaming;
 unsigned vts; int get_error,setup_error,fail_write; unsigned puts,noidle_puts; };
struct v4l2_subdev { struct ov5693_device *sensor; };
static struct ov5693_device *to_ov5693_sensor(struct v4l2_subdev *sd) { return sd->sensor; }
static int pm_runtime_resume_and_get(struct device *d) {
 if(d->sensor->get_error)return d->sensor->get_error;
 d->users++; d->powered=true;return 0;
}
static void pm_runtime_put(struct device *d) { assert(d->users>0);d->users--;d->sensor->puts++;if(!d->users)d->powered=false; }
static void __attribute__((unused)) pm_runtime_put_noidle(struct device *d) { assert(d->users>0);d->users--;d->sensor->noidle_puts++; }
static void cci_write(struct regmap *m,unsigned reg,unsigned val,int *err) {
 assert(m->sensor->lock.held && m->sensor->dev->powered); assert(reg<0x4000);
 if(*err)return;
 m->calls++;
 if(m->sensor->fail_write==(int)m->calls){*err=-EIO;return;}
 m->regs[reg]=val;
}
static void cci_update_bits(struct regmap *m,unsigned reg,unsigned mask,unsigned val,int *err) {
 cci_write(m,reg,(m->regs[reg]&~mask)|(val&mask),err);
}
static int __v4l2_ctrl_handler_setup(struct handler *h) {
 struct ov5693_device *s=h->sensor;assert(s->lock.held);h->calls++;
 if(s->setup_error)return s->setup_error;
 int err=0;cci_write(s->regmap,OV5693_TIMING_VTS_REG,s->vts,&err);return err;
}
'''
stream_functions=''.join(function(ov,n) for n in ['ov5693_mode_configure','ov5693_enable_streaming','ov5693_s_stream'])
stream_cases=r'''
int main(void) {
 unsigned cases=0;
 for(unsigned i=0;i<2048;i++)for(int failure=-2;failure<=15;failure++) {
  struct regmap map={0};struct device dev={0};struct ov5693_device s={0};struct v4l2_subdev sd={.sensor=&s};
  s.dev=&dev;s.regmap=&map;s.ctrls.handler.sensor=&s;map.sensor=&s;dev.sensor=&s;
  dev.users=i&1;dev.powered=true; // hold runtime power in half the cases
  s.mode.format.width=16+2*(i%1296);s.mode.format.height=16+2*(i%970);
  s.mode.crop=(struct v4l2_rect){.left=(int)(i%16)*2,.top=(int)(i%24)*2,.width=2600,.height=1940};
  s.mode.binning_x=i&1;s.mode.binning_y=i&2;s.mode.inc_x_odd=s.mode.binning_x?3:1;s.mode.inc_y_odd=s.mode.binning_y?3:1;s.vts=3000+i;
  map.regs[OV5693_OUTPUT_SIZE_X_REG]=2624;map.regs[OV5693_OUTPUT_SIZE_Y_REG]=1956;
  if(failure==-2)s.get_error=-EAGAIN;
  else if(failure==-1)s.setup_error=-EREMOTEIO;
  else s.fail_write=failure;
  int original_users=dev.users;
  int result=ov5693_s_stream(&sd,1);cases++;
  if(failure==0) {
   assert(result==0 && s.streaming && dev.users==original_users+1 && !s.lock.held);
   assert(map.regs[OV5693_OUTPUT_SIZE_X_REG]==s.mode.format.width && map.regs[OV5693_OUTPUT_SIZE_Y_REG]==s.mode.format.height);
   assert(map.regs[OV5693_CROP_START_X_REG]==(unsigned)s.mode.crop.left && map.regs[OV5693_CROP_START_Y_REG]==(unsigned)s.mode.crop.top);
   assert(map.regs[OV5693_TIMING_HTS_REG]==OV5693_FIXED_PPL && map.regs[OV5693_TIMING_VTS_REG]==s.vts);
   assert((map.regs[OV5693_FORMAT1_REG]&OV5693_FORMAT1_VBIN_EN)==(s.mode.binning_y?OV5693_FORMAT1_VBIN_EN:0));
   assert(s.ctrls.handler.calls==1 && map.regs[OV5693_SW_STREAM_REG]==OV5693_START_STREAMING);
   s.fail_write=0;assert(ov5693_s_stream(&sd,0)==0 && !s.streaming && dev.users==original_users && !s.lock.held);
  } else {
   assert(result==(failure==-2?-EAGAIN:failure==-1?-EREMOTEIO:-EIO));
   assert(!s.streaming && !s.lock.held && dev.users==original_users);
   assert(!s.noidle_puts && s.puts==(failure==-2?0U:1U));
   if(!original_users && failure!=-2)assert(!dev.powered);
  }
 }
 printf("PASS %u real OV5693 mode/control/stream/PM-reference cases; stubbed CCI and PM\n",cases);
}
'''
preview=r'''
typedef uint32_t u32;
#define min(a,b) ((a)<(b)?(a):(b))
#define min_t(t,a,b) min((t)(a),(t)(b))
#define clamp_t(t,x,l,h) ((t)(x)<(t)(l)?(t)(l):((t)(x)>(t)(h)?(t)(h):(t)(x)))
#define rounddown(x,n) ((x)-(x)%(n))
#define ATOMISP_RUN_MODE_PREVIEW 2
#define IA_CSS_FRAME_FORMAT_RAW 99
#define V4L2_SUBDEV_FORMAT_TRY 0
#define V4L2_PIX_FMT_CUSTOM_M10MO_RAW 0x00abcdef
#define dev_dbg(...) ((void)0)
#define dev_err(...) ((void)0)
struct control { int val; };
struct atomisp_sub_device { struct control *run_mode; unsigned input_curr; };
struct atomisp_input_subdev { struct v4l2_rect native_rect; };
struct atomisp_device { struct atomisp_sub_device asd; struct atomisp_input_subdev inputs[1]; unsigned native_w,native_h; int sensor_error; };
struct atomisp_format_bridge { unsigned pixelformat,sh_fmt,mbus_code; };
static const struct atomisp_format_bridge out={V4L2_PIX_FMT_YUV420,1,0x3007},raw={0xdeadbeef,IA_CSS_FRAME_FORMAT_RAW,0x3007};
static const struct atomisp_format_bridge *atomisp_get_format_bridge(unsigned f) { return f==out.pixelformat?&out:f==raw.pixelformat?&raw:NULL; }
static const struct atomisp_format_bridge *atomisp_get_format_bridge_from_mbus(unsigned f) { return f==out.mbus_code?&out:NULL; }
static void atomisp_get_padding(struct atomisp_device *d,unsigned w,unsigned h,u32 *pw,u32 *ph) { (void)d;(void)w;(void)h;*pw=*ph=16; }
static void v4l2_fill_mbus_format(struct v4l2_mbus_framefmt *mf,struct v4l2_pix_format *f,unsigned code) { mf->width=f->width;mf->height=f->height;mf->code=code; }
static int atomisp_set_sensor_crop_and_fmt(struct atomisp_device *d,struct v4l2_mbus_framefmt *mf,int which) {
 assert(which==V4L2_SUBDEV_FORMAT_TRY);
 if(d->asd.run_mode->val==ATOMISP_RUN_MODE_PREVIEW)assert(mf->width<=1936 && mf->height<=1456);
 if(d->sensor_error)return d->sensor_error;
 mf->width=min(mf->width,d->native_w);mf->height=min(mf->height,d->native_h);return 0;
}
static void atomisp_fill_pix_format(struct v4l2_pix_format *f,unsigned w,unsigned h,const struct atomisp_format_bridge *fmt) { f->width=w;f->height=h;f->pixelformat=fmt->pixelformat; }
'''
internal=(repo/'drivers/staging/media/atomisp/pci/atomisp_internal.h').read_text()
preview_macros='\n'.join(re.search(r'^#define '+n+r'\s+[^\n]+',internal,re.M).group(0) for n in ['ATOM_ISP_MIN_WIDTH','ATOM_ISP_MIN_HEIGHT','ATOM_ISP_MAX_WIDTH','ATOM_ISP_MAX_HEIGHT','ATOM_ISP_STEP_WIDTH','ATOM_ISP_STEP_HEIGHT'])+'\n'
preview_cases=r'''
int main(void) {
 struct control mode={.val=ATOMISP_RUN_MODE_PREVIEW};
 struct atomisp_device d={.asd={.run_mode=&mode},.native_w=2624,.native_h=1956};
 unsigned count=0;uint32_t seed=7;
 for(unsigned i=0;i<100000;i++) {
  seed=1664525*seed+1013904223;struct v4l2_pix_format f={.width=seed,.height=~seed,.pixelformat=i&1?out.pixelformat:raw.pixelformat};
  const struct atomisp_format_bridge *a=NULL,*b=NULL;
  assert(atomisp_try_fmt(&d,&f,&a,&b)==0);assert(a==&out && b==&out && f.pixelformat==out.pixelformat);
  assert(f.width>=4 && f.height>=4 && f.width<=1920 && f.height<=1440 && !(f.width&1) && !(f.height&1));count++;
 }
 for(unsigned modeval=0;modeval<4;modeval++) {
  mode.val=modeval;struct v4l2_pix_format f={.width=2400,.height=1800,.pixelformat=out.pixelformat};
  assert(atomisp_try_fmt(&d,&f,NULL,NULL)==0);
  assert(f.width==(modeval==ATOMISP_RUN_MODE_PREVIEW?1920U:2400U));
  assert(f.height==(modeval==ATOMISP_RUN_MODE_PREVIEW?1440U:1800U));count++;
 }
 mode.val=ATOMISP_RUN_MODE_PREVIEW;d.sensor_error=-EIO;
 struct v4l2_pix_format f={.width=4000,.height=4000,.pixelformat=out.pixelformat};
 assert(atomisp_try_fmt(&d,&f,NULL,NULL)==-EIO);count++;
 d.sensor_error=0;
 for(unsigned i=0;i<512;i++) {
  d.native_w=2000+i*2;d.native_h=1500+i*2;
  d.inputs[0].native_rect=(struct v4l2_rect){.width=(int)d.native_w,.height=(int)d.native_h};
  struct v4l2_frmsizeenum fs={.pixel_format=out.pixelformat};
  assert(atomisp_enum_framesizes_crop(&d,&fs)==0 && fs.type==V4L2_FRMSIZE_TYPE_STEPWISE);
  assert(fs.stepwise.min_width==4 && fs.stepwise.min_height==4 && fs.stepwise.max_width==1920 && fs.stepwise.max_height==1440);
  assert(fs.stepwise.step_width==2 && fs.stepwise.step_height==2);
  fs.index=1;assert(atomisp_enum_framesizes_crop(&d,&fs)==-EINVAL);
  fs.index=UINT32_MAX;assert(atomisp_enum_framesizes_crop(&d,&fs)==-EINVAL);
  fs.index=0;d.sensor_error=-ENOMEM;assert(atomisp_enum_framesizes_crop(&d,&fs)==-ENOMEM);d.sensor_error=0;
  count+=4;
 }
 d.inputs[0].native_rect.width=0;
 struct v4l2_frmsizeenum fs={.pixel_format=out.pixelformat};
 assert(atomisp_enum_framesizes_crop(&d,&fs)==-EINVAL);count++;
 printf("PASS %u real preview/range negotiation cases; sensor/format/padding stubs, not firmware proof\n",count);
}
'''
preview_function=function(cmd,'atomisp_try_fmt')
ioctl=(repo/'drivers/staging/media/atomisp/pci/atomisp_ioctl.c').read_text()
preview_function+=function(ioctl,'atomisp_enum_framesizes_crop')
with tempfile.TemporaryDirectory(prefix='mipad2-preview-warm-') as temp:
    p=Path(temp)
    fixtures=[('stream',base+macros+stream+stream_functions+stream_cases),
              ('preview',base+'#include <limits.h>\n'+preview_macros+preview+preview_function+preview_cases)]
    for name,src in fixtures:
        if os.environ.get('MIPAD2_OLD_NAME_NEGATIVE')==name:
            if name=='stream':
                src=src.replace('ret = ov5693_mode_configure(ov5693);\n\t\tif (!ret)\n\t\t\tret = __v4l2_ctrl_handler_setup','ret = __v4l2_ctrl_handler_setup')
                src=src.replace('static int ov5693_mode_configure(', 'static int __attribute__((unused)) ov5693_mode_configure(')
            else:src=src.replace('\t\tf->height = min(f->height, 1440U);','')
        c=p/(name+'.c');exe=p/name;c.write_text(src)
        subprocess.run(['gcc','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer','-no-pie',str(c),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True)
