#!/usr/bin/env python3
"""Extract production padding, TRY_FMT, range and VTS functions.

Sensor, DMI and format helpers are stubs. This is arithmetic/negotiation
coverage, not hardware, image-quality, DMA or firmware-selection proof.
"""
from pathlib import Path
import os, re, subprocess, tempfile

repo = Path(__file__).resolve().parents[2]
if not (repo / 'drivers').exists():
    repo = Path('/root/linux_latte-6.14-integrated')
cmd = (repo / 'drivers/staging/media/atomisp/pci/atomisp_cmd.c').read_text()
ov = (repo / 'drivers/media/i2c/ov5693.c').read_text()
internal = (repo / 'drivers/staging/media/atomisp/pci/atomisp_internal.h').read_text()
ioctl = (repo / 'drivers/staging/media/atomisp/pci/atomisp_ioctl.c').read_text()

def function(src, name):
    m = re.search(r'(?:static\s+)?(?:unsigned int|int|void)\s+' + name + r'\([^;{}]*\)\s*\{', src)
    assert m, name
    end, depth = m.end(), 1
    while depth:
        depth += (src[end] == '{') - (src[end] == '}')
        end += 1
    return src[m.start():end] + '\n'

def macros(src, names):
    return '\n'.join(re.search(r'^#define ' + n + r'\s+[^\n]+', src, re.M)[0] for n in names) + '\n'

defs = macros(internal, ['ATOM_ISP_MIN_WIDTH','ATOM_ISP_MIN_HEIGHT','ATOM_ISP_MAX_WIDTH',
    'ATOM_ISP_MAX_HEIGHT','ATOM_ISP_STEP_WIDTH','ATOM_ISP_STEP_HEIGHT'])
defs += macros(ov, ['OV5693_FIXED_PPL','OV5693_TIMING_MIN_VTS','OV5693_TIMING_MAX_VTS',
    'OV5693_MIPAD2_DEFAULT_FPS','OV5693_MIPAD2_VBLANK_BINNED','OV5693_MIPAD2_VBLANK_UNBINNED',
    'OV5693_INTEGRATION_TIME_MARGIN','OV5693_EXPOSURE_MIN','OV5693_PIXEL_RATE',
    'OV5693_MIPAD2_PIXEL_RATE','OV5693_NATIVE_HEIGHT'])
base = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <limits.h>
#include <linux/videodev2.h>
#include <linux/v4l2-mediabus.h>
typedef uint32_t u32;
typedef uint64_t u64;
#define min(a,b) ((a)<(b)?(a):(b))
#define max(a,b) ((a)>(b)?(a):(b))
#define min_t(t,a,b) min((t)(a),(t)(b))
#define max_t(t,a,b) max((t)(a),(t)(b))
#define clamp_t(t,x,l,h) min_t(t,max_t(t,x,l),h)
#define rounddown(x,n) ((x)-(x)%(n))
#define ALIGN(x,n) (((x)+(n)-1)&~((__typeof__(x))(n)-1))
#define ALIGN_DOWN(x,n) ((x)&~((__typeof__(x))(n)-1))
#define ISP2400_MIN_PAD_W 12
#define ISP2400_MIN_PAD_H 12
#define IA_CSS_BAYER_ORDER_RGGB 0
#define IA_CSS_BAYER_ORDER_GBRG 1
#define IA_CSS_BAYER_ORDER_BGGR 2
#define IA_CSS_BAYER_ORDER_GRBG 3
#define ATOMISP_RUN_MODE_PREVIEW 2
#define IA_CSS_FRAME_FORMAT_RAW 99
#define V4L2_SUBDEV_FORMAT_TRY 0
#define V4L2_SUBDEV_FORMAT_ACTIVE 1
#define V4L2_PIX_FMT_CUSTOM_M10MO_RAW 0x00abcdef
#define ATOMISP_SUBDEV_PAD_SINK 0
#define DMI_SYS_VENDOR 0
#define DMI_PRODUCT_NAME 1
#define dev_warn(...) ((void)0)
#define dev_err(...) ((void)0)
#define dev_dbg(...) ((void)0)
#define IS_ISP2401 (isp->isp2401)
static bool board_vendor=true, board_product=true;
static int pad_w=16, pad_h=16;
static bool __attribute__((unused)) dmi_match(int field, const char *s) {
 assert(!strcmp(s,field==DMI_SYS_VENDOR?"Xiaomi Inc":"Mipad2"));
 return field==DMI_SYS_VENDOR?board_vendor:board_product;
}
struct camera { char name[32]; };
struct control { int val; };
/* Unsigned geometry here matches the valid positive rectangles used below. */
struct rect { u32 width,height; };
struct atomisp_input_subdev { struct rect native_rect,active_rect;
 bool crop_support,binning_support; struct camera *camera; };
struct atomisp_sub_device { struct control *run_mode; unsigned input_curr; int subdev; };
struct atomisp_device { struct atomisp_sub_device asd; struct atomisp_input_subdev inputs[1];
 bool isp2401; unsigned calls,last_w,last_h; int sensor_error; };
struct atomisp_in_fmt_conv { unsigned bayer_order; };
struct atomisp_format_bridge { unsigned pixelformat,sh_fmt,mbus_code; };
static struct atomisp_in_fmt_conv conv={IA_CSS_BAYER_ORDER_GRBG};
static bool missing_sink,missing_conv;
static struct v4l2_mbus_framefmt sinkfmt={.code=0x3007};
static struct v4l2_mbus_framefmt *atomisp_subdev_get_ffmt(int *s,void *state,int which,int pad) {
 (void)s;assert(!state && which==V4L2_SUBDEV_FORMAT_ACTIVE && pad==0);
 return missing_sink?NULL:&sinkfmt;
}
static const struct atomisp_in_fmt_conv *atomisp_find_in_fmt_conv(unsigned c) {
 assert(c==sinkfmt.code);return missing_conv?NULL:&conv;
}
static const struct atomisp_format_bridge out={V4L2_PIX_FMT_YUV420,1,0x3007};
static const struct atomisp_format_bridge *atomisp_get_format_bridge(unsigned f) { return f==out.pixelformat?&out:NULL; }
static const struct atomisp_format_bridge *atomisp_get_format_bridge_from_mbus(unsigned f) { return f==out.mbus_code?&out:NULL; }
static void v4l2_fill_mbus_format(struct v4l2_mbus_framefmt *mf,struct v4l2_pix_format *f,unsigned code) { mf->width=f->width;mf->height=f->height;mf->code=code; }
static int atomisp_set_sensor_crop_and_fmt(struct atomisp_device *d,struct v4l2_mbus_framefmt *mf,int which) {
 assert(which==V4L2_SUBDEV_FORMAT_TRY);
 assert(mf->width<=2640 && mf->height<=1972); /* detect unchecked huge additions */
 d->calls++;d->last_w=mf->width;d->last_h=mf->height;
 if(d->sensor_error)return d->sensor_error;
 mf->width=min(mf->width,d->inputs[0].native_rect.width);
 mf->height=min(mf->height,d->inputs[0].native_rect.height);
 return 0;
}
static void atomisp_fill_pix_format(struct v4l2_pix_format *f,unsigned w,unsigned h,const struct atomisp_format_bridge *fmt) { f->width=w;f->height=h;f->pixelformat=fmt->pixelformat; }
struct ov5693_device { unsigned pixel_rate; bool mipad2; struct { bool binning_x,binning_y; } mode; };
'''
# Use the real v4l2_rect; signed kernel geometry is checked by real kernel build.
base = base.replace('struct rect { u32 width,height; };','')
base = base.replace('struct rect native_rect,active_rect;', 'struct v4l2_rect native_rect,active_rect;')
# min macros in old kernel source mix positive signed/unsigned geometry.
base = base.replace('#define min(a,b) ((a)<(b)?(a):(b))',
    '#define min(a,b) (((uint64_t)(a)<(uint64_t)(b))?(a):(b))')
base = base.replace('mf->width=min(mf->width,d->inputs[0].native_rect.width);',
    'mf->width=min_t(u32,mf->width,d->inputs[0].native_rect.width);')
base = base.replace('mf->height=min(mf->height,d->inputs[0].native_rect.height);',
    'mf->height=min_t(u32,mf->height,d->inputs[0].native_rect.height);')
cases = r'''
int main(void) {
 struct control mode={ATOMISP_RUN_MODE_PREVIEW};struct camera cam={"ov5693 6-0036"};
 struct atomisp_device d={.asd={.run_mode=&mode},.isp2401=true,
   .inputs={{.native_rect={.width=2624,.height=1956},.active_rect={.width=2592,.height=1944},
    .crop_support=true,.binning_support=true,.camera=&cam}}};
 unsigned count=0;
 unsigned heights[]={2,4,8,16,20,32,720,960,970,972,974,976,978,1440,1944,1956};
 for(unsigned w=2;w<=2624;w+=2)for(unsigned j=0;j<sizeof(heights)/sizeof(*heights);j++) {
  unsigned h=heights[j],pw,ph;
  atomisp_get_padding(&d,w,h,&pw,&ph);
  unsigned nw=(w<=1296 && h<=972)?1312U:2624U;
  assert(pw<=36 && ph<=16);
  if((uint64_t)w+16<=nw)assert(w+pw>=36 && !((w+pw)&3));
  count++;
 }
 struct { unsigned w,h,pad; } vectors[]={
  {4,4,32},{8,32,28},{16,32,20},{18,32,18},{20,32,16},
  {22,32,18},{24,32,16},{26,32,18},{30,32,18},{1282,32,18},
  {1294,32,18},{1298,32,18},{1302,32,18},{2594,1440,18},{2606,1440,18}};
 for(unsigned i=0;i<sizeof(vectors)/sizeof(*vectors);i++) {
  unsigned pw,ph;atomisp_get_padding(&d,vectors[i].w,vectors[i].h,&pw,&ph);
  assert(pw==vectors[i].pad && ph==16);count++;
 }
 /* Scope isolation: rear, other board, BYT, non-crop and absent camera. */
 for(unsigned scope=0;scope<6;scope++) {
  d.isp2401=true;d.inputs[0].crop_support=true;d.inputs[0].camera=&cam;
  strcpy(cam.name,"ov5693 6-0036");board_vendor=board_product=true;
  if(scope==0)strcpy(cam.name,"t4ka3 6-0037");
  if(scope==1)board_vendor=false;if(scope==2)board_product=false;
  if(scope==3)d.isp2401=false;
  if(scope==4)d.inputs[0].crop_support=false;
  if(scope==5)d.inputs[0].camera=NULL;
  unsigned pw,ph;atomisp_get_padding(&d,4,4,&pw,&ph);assert(pw==16 && ph==16);count++;
 }
 d.isp2401=true;d.inputs[0].crop_support=true;d.inputs[0].camera=&cam;
 strcpy(cam.name,"ov5693 6-0036");board_vendor=board_product=true;
 /* Retain the legacy BYT Bayer-padding behavior at the native edge. */
 d.isp2401=false;
 d.inputs[0].active_rect=d.inputs[0].native_rect;
 for(unsigned b=0;b<4;b++) {
  conv.bayer_order=b;unsigned pw,ph;atomisp_get_padding(&d,2624,1956,&pw,&ph);
  assert(pw==12U+(b==IA_CSS_BAYER_ORDER_RGGB || b==IA_CSS_BAYER_ORDER_GBRG?2U:0U));
  assert(ph==12U+(b==IA_CSS_BAYER_ORDER_BGGR || b==IA_CSS_BAYER_ORDER_GBRG?2U:0U));count++;
 }
 d.isp2401=true;
 d.inputs[0].active_rect=(struct v4l2_rect){.width=2592,.height=1944};
 unsigned requests[]={0,1,2,3,4,18,22,1282,1294,1298,1302,1920,2594,2606,2624,16384,UINT32_MAX-1,UINT32_MAX};
 for(unsigned m=0;m<4;m++)for(unsigned x=0;x<sizeof(requests)/sizeof(*requests);x++)
  for(unsigned y=0;y<sizeof(requests)/sizeof(*requests);y++) {
   mode.val=m;
   struct v4l2_pix_format f={.width=requests[x],.height=requests[y],.pixelformat=out.pixelformat};
   assert(!atomisp_try_fmt(&d,&f,NULL,NULL));
   assert(f.width>=4 && f.height>=4 && !(f.width&1) && !(f.height&1));
   assert(f.width<=2624 && f.height<=1956);
   if(m==ATOMISP_RUN_MODE_PREVIEW)assert(f.width<=1920 && f.height<=1440);
   if(requests[x]>=4 && requests[x]<=1920 && requests[y]>=4 && requests[y]<=1440)
    assert(f.width==requests[x] && f.height==requests[y]);
   count++;
  }
 mode.val=ATOMISP_RUN_MODE_PREVIEW;
 struct v4l2_frmsizeenum fs={.pixel_format=out.pixelformat};
 assert(!atomisp_enum_framesizes_crop(&d,&fs));
 assert(fs.type==V4L2_FRMSIZE_TYPE_STEPWISE && fs.stepwise.min_width==4 && fs.stepwise.min_height==4);
 assert(fs.stepwise.max_width==1920 && fs.stepwise.max_height==1440 && fs.stepwise.step_width==2 && fs.stepwise.step_height==2);count++;
 for(unsigned i=0;i<2;i++) {
  struct ov5693_device s={.pixel_rate=i?OV5693_PIXEL_RATE:OV5693_MIPAD2_PIXEL_RATE,.mipad2=!i};
  for(unsigned h=2;h<=OV5693_NATIVE_HEIGHT;h+=2) {
   unsigned vts=__ov5693_calc_vts(&s,h);
   assert(!(vts&1) && vts>=h+ov5693_min_vblank(&s) && vts<=OV5693_TIMING_MAX_VTS);
   assert(vts>=OV5693_INTEGRATION_TIME_MARGIN+OV5693_EXPOSURE_MIN);
   unsigned fps=rounddown(s.pixel_rate/OV5693_FIXED_PPL/h,30);
   unsigned old=ALIGN_DOWN(s.pixel_rate/OV5693_FIXED_PPL/max(fps,30U),2);
   if(i && old>=h+4 && old>=9)assert(vts==old);
   if(!i)assert(vts==1984);count++;
  }
 }
 printf("PASS %u extracted padding/TRY_FMT/range/VTS cases; stubs, not real capture proof\n",count);
}
'''
production = ''.join([function(cmd,'atomisp_get_padding'),function(cmd,'atomisp_try_fmt'),
    function(ioctl,'atomisp_enum_framesizes_crop'),function(ov,'ov5693_min_vblank'),function(ov,'__ov5693_calc_vts')])
negative = os.environ.get('MIPAD2_GEOMETRY_NEGATIVE')
if negative == 'padding':
    a = production.index('\tif (IS_ISP2401 && input->camera')
    b = production.index('\n\t/* The below minimum padding', a)
    production = production[:a] + '\t(void)requested_width; (void)input_width;\n' + production[b:]
elif negative == 'requested-width':
    production = production.replace('\t\tinput_width = (u64)requested_width', '\t\trequested_width = width;\n\t\tinput_width = (u64)requested_width')
elif negative == 'native-bound':
    a = production.index('\t/* Bound crop requests')
    b = production.index('\n\t/*\n\t * atomisp_set_fmt()', a)
    production = production[:a] + '\t(void)input;\n' + production[b:]
elif negative == 'vts':
    production = production.replace('return max(vts, ALIGN(min_vts, 2));', '(void)min_vts; return vts;')

with tempfile.TemporaryDirectory(prefix='mipad2-input-geometry-') as temp:
    p = Path(temp)
    c = p / 'geometry.c'
    c.write_text(base + defs + production + cases)
    subprocess.run(['gcc','-O1','-g','-Wall','-Wextra','-Werror','-Wno-sign-compare',
        '-Wno-sign-conversion','-Wno-misleading-indentation','-fsanitize=address,undefined',
        '-fno-omit-frame-pointer','-no-pie',str(c),'-o',str(p/'geometry')],check=True)
    subprocess.run([str(p/'geometry')],check=True)
