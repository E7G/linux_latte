#!/usr/bin/env python3
"""Extract real OV crop/format/VTS/getters; no sensor, lock or I2C proof."""
from pathlib import Path
import os,re,subprocess,tempfile
r=Path(__file__).resolve().parents[2]
if not(r/'drivers').exists():r=Path('/root/linux_latte-6.14-integrated')
s=(r/'drivers/media/i2c/ov5693.c').read_text()
if os.environ.get('MIPAD2_CROP_NEGATIVE'):
    s=subprocess.check_output(['git','show','478556f8f6222f8a718cbb5cfe94709c53170ae3:drivers/media/i2c/ov5693.c'],cwd=r,text=True)

def function(name):
    m=re.search(r'(?:static\s+)?(?:unsigned int|int|struct v4l2_mbus_framefmt \*|struct v4l2_rect \*)\s*'+name+r'\([^;{}]*\)\s*\{',s);assert m,name
    n=m.end();depth=1
    while depth:depth+=(s[n]=='{')-(s[n]=='}');n+=1
    return s[m.start():n]+'\n'

names=['OV5693_NATIVE_START_LEFT','OV5693_NATIVE_START_TOP','OV5693_NATIVE_WIDTH','OV5693_NATIVE_HEIGHT',
    'OV5693_MIN_CROP_WIDTH','OV5693_MIN_CROP_HEIGHT','OV5693_FIXED_PPL','OV5693_TIMING_MIN_VTS',
    'OV5693_MIPAD2_DEFAULT_FPS','OV5693_MIPAD2_VBLANK_BINNED','OV5693_MIPAD2_VBLANK_UNBINNED',
    'OV5693_TIMING_MAX_VTS','OV5693_INTEGRATION_TIME_MARGIN','OV5693_EXPOSURE_MIN','OV5693_MIPAD2_PIXEL_RATE']
if os.environ.get('MIPAD2_CROP_NEGATIVE'):
    names=[n for n in names if n not in ['OV5693_MIPAD2_DEFAULT_FPS','OV5693_MIPAD2_VBLANK_BINNED','OV5693_MIPAD2_VBLANK_UNBINNED']]

macros='\n'.join(re.search(r'^#define '+n+r'\s+[^\n]+',s,re.M)[0] for n in names)+'\n'
base=r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <limits.h>
#include <string.h>
#include <linux/v4l2-subdev.h>
typedef uint32_t u32;
#define min_t(t,a,b) ((t)(a)<(t)(b)?(t)(a):(t)(b))
#define max_t(t,a,b) ((t)(a)>(t)(b)?(t)(a):(t)(b))
#define max(a,b) ((a)>(b)?(a):(b))
#define clamp_t(t,a,l,h) min_t(t,max_t(t,a,l),h)
#define clamp(a,l,h) clamp_t(__typeof__(a),a,l,h)
#define ALIGN(a,n) (((a)+(n)-1)&~((__typeof__(a))(n)-1))
#define ALIGN_DOWN(a,n) ((a)&~((__typeof__(a))(n)-1))
#define rounddown(a,n) ((a)-(a)%(n))
#define DIV_ROUND_CLOSEST(a,b) (((a)+(b)/2)/(b))
#define MEDIA_BUS_FMT_SBGGR10_1X10 0x3007
struct mutex { int held; };
static void mutex_lock(struct mutex *m) { assert(!m->held);m->held=1; }
static void mutex_unlock(struct mutex *m) { assert(m->held);m->held=0; }
struct control { int minimum,maximum,default_value,val; };
struct ov5693_device { unsigned pixel_rate; bool mipad2; struct mutex lock;
 struct { struct v4l2_rect crop; struct v4l2_mbus_framefmt format; bool binning_x,binning_y; unsigned inc_x_odd,inc_y_odd,vts; } mode;
 struct { struct control *vblank,*hblank; } ctrls; unsigned exposure_max; };
struct v4l2_subdev { struct ov5693_device *sensor; };
struct v4l2_subdev_state { struct v4l2_rect crop; struct v4l2_mbus_framefmt format; };
static struct ov5693_device *to_ov5693_sensor(struct v4l2_subdev *s) { return s->sensor; }
static struct v4l2_rect *v4l2_subdev_state_get_crop(struct v4l2_subdev_state *s,unsigned pad) { assert(!pad);return &s->crop; }
static struct v4l2_mbus_framefmt *v4l2_subdev_state_get_format(struct v4l2_subdev_state *s,unsigned pad) { assert(!pad);return &s->format; }
static int __v4l2_ctrl_modify_range(struct control *c,int lo,int hi,int step,int def) {
 assert(lo>=0 && hi>=lo && step==1 && def>=lo && def<=hi);
 c->minimum=lo;c->maximum=hi;c->default_value=def;return 0;
}
static int __v4l2_ctrl_s_ctrl(struct control *c,int val) { assert(val>=c->minimum && val<=c->maximum);c->val=val;return 0; }
static void ov5693_update_exposure_range(struct ov5693_device *s,unsigned max) { assert(s->lock.held && max>=1);s->exposure_max=max; }
'''
cases=r'''
int main(void) {
 unsigned count=0;
 int positions[]={INT_MIN,-3,-1,0,1,16,1953,1954,1955,1956,2621,2622,2623,2624,INT_MAX};
 unsigned sizes[]={0,1,2,3,4,17,1955,1956,2623,2624,65535,UINT_MAX-1,UINT_MAX};
 for(unsigned board=0;board<2;board++)
 for(unsigned which=0;which<2;which++)
  for(unsigned x=0;x<sizeof(positions)/sizeof(*positions);x++)
   for(unsigned y=0;y<sizeof(positions)/sizeof(*positions);y++)
    for(unsigned z=0;z<sizeof(sizes)/sizeof(*sizes);z++) {
     struct control vb={0},hb={0};struct ov5693_device d={.pixel_rate=OV5693_MIPAD2_PIXEL_RATE,.mipad2=board,.ctrls={&vb,&hb}};
     d.mode.crop=(struct v4l2_rect){.width=OV5693_NATIVE_WIDTH,.height=OV5693_NATIVE_HEIGHT};
     d.mode.format=(struct v4l2_mbus_framefmt){.width=OV5693_NATIVE_WIDTH,.height=OV5693_NATIVE_HEIGHT};
     struct v4l2_subdev sd={&d};struct v4l2_subdev_state state={.crop=d.mode.crop,.format=d.mode.format};
     struct v4l2_subdev_selection sel={.which=which,.target=V4L2_SEL_TGT_CROP,
      .r={.left=positions[x],.top=positions[y],.width=sizes[z],.height=sizes[12-z]}};
     assert(!ov5693_set_selection(&sd,&state,&sel));
     assert(sel.r.left>=0 && sel.r.top>=0 && !(sel.r.left&1) && !(sel.r.top&1));
     assert(sel.r.width>=2 && sel.r.height>=2 && !(sel.r.width&1) && !(sel.r.height&1));
     assert((uint64_t)sel.r.left+sel.r.width<=OV5693_NATIVE_WIDTH && (uint64_t)sel.r.top+sel.r.height<=OV5693_NATIVE_HEIGHT);
     struct v4l2_rect *crop=which==V4L2_SUBDEV_FORMAT_TRY?&state.crop:&d.mode.crop;
     assert(!memcmp(crop,&sel.r,sizeof(sel.r)));
     struct v4l2_subdev_format fmt={.which=which,.format={.width=UINT_MAX,.height=UINT_MAX}};
     assert(!ov5693_set_fmt(&sd,&state,&fmt));
     assert(fmt.format.width==crop->width && fmt.format.height==crop->height); // huge requests stay at max, not wrapped to min/binning
     assert(fmt.format.width>=2 && fmt.format.height>=2);
     if(which==V4L2_SUBDEV_FORMAT_ACTIVE)assert(!d.lock.held && d.exposure_max>=1 && vb.val>=4);
     struct v4l2_rect saved=*crop;sel.target=V4L2_SEL_TGT_NATIVE_SIZE;
     assert(ov5693_set_selection(&sd,&state,&sel)==-EINVAL && !memcmp(crop,&saved,sizeof(saved)));
     count++;
    }
 printf("PASS %u actual OV crop/format/VTS edge cases, bounded before ALIGN and non-empty; control/state stubs\n",count);
}
'''
function_names=['__ov5693_calc_vts','__ov5693_get_pad_format','__ov5693_get_pad_crop','ov5693_set_fmt','ov5693_set_selection']
if not os.environ.get('MIPAD2_CROP_NEGATIVE'):function_names.insert(0,'ov5693_min_vblank')
functions=''.join(function(n) for n in function_names)
with tempfile.TemporaryDirectory(prefix='mipad2-crop-') as temp:
    p=Path(temp);c=p/'test.c';c.write_text(base+macros+functions+cases)
    subprocess.run(['gcc','-O1','-g','-Wall','-Wextra','-Werror','-Wno-sign-compare','-fsanitize=address,undefined',
        '-fno-omit-frame-pointer','-no-pie',str(c),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
