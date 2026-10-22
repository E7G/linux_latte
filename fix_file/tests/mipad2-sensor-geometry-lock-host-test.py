#!/usr/bin/env python3
"""Real geometry callbacks with pthread/control/state stubs, not DMA/I2C proof."""
from pathlib import Path
import os,re,subprocess,tempfile
r=Path(__file__).resolve().parents[2]
if not(r/'drivers').exists():r=Path('/root/linux_latte-6.14-integrated')
ov=(r/'drivers/media/i2c/ov5693.c').read_text();t4=(r/'drivers/media/i2c/t4ka3.c').read_text()
assert 'sensor->sd.state_lock = sensor->ctrls.handler.lock;' in t4
assert 'ov5693->sd.internal_ops = &ov5693_internal_ops;' in ov
def function(s,name):
 m=re.search(r'(?:static\s+)?(?:unsigned int|int|void|struct v4l2_mbus_framefmt \*|struct v4l2_rect \*)\s*'+name+r'\([^;{}]*\)\s*\{',s);assert m,name
 n=m.end();depth=1
 while depth:depth+=(s[n]=='{')-(s[n]=='}');n+=1
 return s[m.start():n]+'\n'
ovnames=['ov5693_min_vblank','__ov5693_calc_vts','__ov5693_get_pad_format','__ov5693_get_pad_crop',
 'ov5693_get_fmt','ov5693_set_fmt','ov5693_get_selection','ov5693_set_selection','ov5693_enum_frame_size','ov5693_init_state']
t4names=['t4ka3_calc_mode','t4ka3_fill_format','t4ka3_get_vblank_limits','t4ka3_set_pad_format','t4ka3_set_selection']
parts={n:function(ov,n) for n in ovnames};parts.update({n:function(t4,n) for n in t4names})
negative=os.environ.get('MIPAD2_SENSOR_GEOMETRY_NEGATIVE')
if negative=='ov_busy':
 for name,field in [('ov5693_set_fmt','format'),('ov5693_set_selection','sel')]:
  block=f'\tif ({field}->which == V4L2_SUBDEV_FORMAT_ACTIVE && ov5693->streaming) {{\n\t\tmutex_unlock(&ov5693->lock);\n\t\treturn -EBUSY;\n\t}}\n'
  assert parts[name].count(block)==1;parts[name]=parts[name].replace(block,'')
elif negative=='t4_busy':
 block='\tif (sel->which == V4L2_SUBDEV_FORMAT_ACTIVE && sensor->streaming)\n\t\treturn -EBUSY;\n'
 assert parts['t4ka3_set_selection'].count(block)==1;parts['t4ka3_set_selection']=parts['t4ka3_set_selection'].replace(block,'')
elif negative=='try_getter':
 name='ov5693_get_fmt';a=parts[name].index('\tformat->format =');b=parts[name].index('\n\tmutex_unlock',a)
 parts[name]=parts[name][:a]+'\tformat->format = ov5693->mode.format;'+parts[name][b:]
elif negative=='t4_bounds':
 old=subprocess.check_output(['git','show','9fa44d532d98e052633f7a26afc27d7418501b62:drivers/media/i2c/t4ka3.c'],cwd=r,text=True)
 parts['t4ka3_set_selection']=function(old,'t4ka3_set_selection')
elif negative=='t4_window':
 name='t4ka3_set_selection';old='\t*crop = rect;\n';assert parts[name].count(old)==1
 parts[name]=parts[name].replace(old,'').replace('\tsel->r = rect;','\t*crop = rect;\n\tsel->r = rect;')
elif negative=='ov_lock':
 name='ov5693_set_fmt';assert parts[name].count('\tmutex_lock(&ov5693->lock);')==1
 parts[name]=parts[name].replace('\tmutex_lock(&ov5693->lock);','')
elif negative=='t4_doublelock':
 name='t4ka3_set_pad_format';needle='\tlockdep_assert_held(sensor->sd.state_lock);';assert parts[name].count(needle)==1
 parts[name]=parts[name].replace(needle,needle+'\n\tmutex_lock(sensor->sd.state_lock);')
else:assert not negative
# Instrument private ACTIVE accessor returns to catch omitted serialization
# before the first read/write, not merely a lock somewhere later in callback.
for name in ['__ov5693_get_pad_format','__ov5693_get_pad_crop']:
 needle='\tcase V4L2_SUBDEV_FORMAT_ACTIVE:\n';assert parts[name].count(needle)==1
 parts[name]=parts[name].replace(needle,needle+'\t\tlockdep_assert_held(&ov5693->lock);\n')
names=['NATIVE_START_LEFT','NATIVE_START_TOP','NATIVE_WIDTH','NATIVE_HEIGHT','MIN_CROP_WIDTH','MIN_CROP_HEIGHT']
defs=[]
for prefix,s,extras in [('OV5693',ov,['FIXED_PPL','TIMING_MIN_VTS','TIMING_MAX_VTS','INTEGRATION_TIME_MARGIN','EXPOSURE_MIN','MIPAD2_DEFAULT_FPS','MIPAD2_VBLANK_BINNED','MIPAD2_VBLANK_UNBINNED','ACTIVE_START_LEFT','ACTIVE_START_TOP','ACTIVE_WIDTH','ACTIVE_HEIGHT']),
                        ('T4KA3',t4,['PIXELS_PER_LINE','MIN_VBLANK','MAX_VBLANK','LINES_PER_FRAME_30FPS','COARSE_INTEGRATION_TIME_MARGIN','COARSE_INTEGRATION_TIME_MIN'])]:
 for name in names+extras:defs.append(re.search(r'^#define '+prefix+'_'+name+r'\s+[^\n]+',s,re.M)[0])
base=r'''
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <linux/v4l2-subdev.h>
typedef uint32_t u32;
#define min_t(t,a,b) ((t)(a)<(t)(b)?(t)(a):(t)(b))
#define max_t(t,a,b) ((t)(a)>(t)(b)?(t)(a):(t)(b))
#define max(a,b) ((a)>(b)?(a):(b))
#define clamp_t(t,a,l,h) min_t(t,max_t(t,a,l),h)
#define clamp(a,l,h) clamp_t(__typeof__(a),a,l,h)
#define clamp_val(a,l,h) clamp(a,l,h)
#define ALIGN(a,n) (((a)+(n)-1)&~((__typeof__(a))(n)-1))
#define ALIGN_DOWN(a,n) ((a)&~((__typeof__(a))(n)-1))
#define rounddown(a,n) ((a)-(a)%(n))
#define DIV_ROUND_CLOSEST(a,b) (((a)+(b)/2)/(b))
#define DIV_ROUND_UP(a,b) (((a)+(b)-1)/(b))
#define MEDIA_BUS_FMT_SBGGR10_1X10 0x3007
struct mutex { pthread_mutex_t raw; pthread_t owner; bool held; };
static void mutex_init(struct mutex *m) {
 pthread_mutexattr_t attr;assert(!pthread_mutexattr_init(&attr));
 assert(!pthread_mutexattr_settype(&attr,PTHREAD_MUTEX_ERRORCHECK));
 assert(!pthread_mutex_init(&m->raw,&attr));assert(!pthread_mutexattr_destroy(&attr));m->held=false;
}
static void mutex_lock(struct mutex *m) {assert(!pthread_mutex_lock(&m->raw));m->owner=pthread_self();m->held=true;}
static void lockdep_assert_held(struct mutex *m) {assert(m && m->held && pthread_equal(m->owner,pthread_self()));}
static void mutex_unlock(struct mutex *m) {lockdep_assert_held(m);m->held=false;assert(!pthread_mutex_unlock(&m->raw));}
struct control { int minimum,maximum,default_value,val; struct mutex *lock; };
static unsigned ctrl_calls;
static int __v4l2_ctrl_modify_range(struct control *c,int lo,int hi,int step,int def) {
 lockdep_assert_held(c->lock);assert(lo>=0 && hi>=lo && step==1 && def>=lo && def<=hi);
 c->minimum=lo;c->maximum=hi;c->default_value=def;ctrl_calls++;return 0;
}
static int __v4l2_ctrl_s_ctrl(struct control *c,int val) {lockdep_assert_held(c->lock);assert(val>=c->minimum && val<=c->maximum);c->val=val;ctrl_calls++;return 0;}
struct v4l2_subdev { void *sensor; struct mutex *state_lock; };
struct v4l2_subdev_state { struct v4l2_rect crop; struct v4l2_mbus_framefmt format; };
struct ov5693_device { unsigned pixel_rate; bool mipad2,streaming; struct mutex lock;
 struct { struct v4l2_rect crop; struct v4l2_mbus_framefmt format; bool binning_x,binning_y; unsigned inc_x_odd,inc_y_odd,vts; } mode;
 struct {struct control *vblank,*hblank;} ctrls; unsigned exposure_max; };
struct t4ka3_data { struct v4l2_subdev sd; int streaming;
 struct {int binning; uint16_t win_x,win_y;} mode;
 struct {struct control *vblank,*hblank;} ctrls; };
static struct ov5693_device *to_ov5693_sensor(struct v4l2_subdev *sd) {return sd->sensor;}
static struct t4ka3_data *to_t4ka3_sensor(struct v4l2_subdev *sd) {return sd->sensor;}
static struct v4l2_rect *v4l2_subdev_state_get_crop(struct v4l2_subdev_state *s,unsigned pad) {assert(s && !pad);return &s->crop;}
static struct v4l2_mbus_framefmt *v4l2_subdev_state_get_format(struct v4l2_subdev_state *s,unsigned pad) {assert(s && !pad);return &s->format;}
static void ov5693_update_exposure_range(struct ov5693_device *s,unsigned value) {lockdep_assert_held(&s->lock);s->exposure_max=value;}
static void t4ka3_set_bayer_order(struct t4ka3_data *s,struct v4l2_mbus_framefmt *fmt) {(void)s;fmt->code=0x300a;}
'''
cases=r'''
static unsigned count;
static void ov_checks(struct ov5693_device *d,struct v4l2_subdev *sd) {
 struct v4l2_subdev_state a={0},b={0};assert(!ov5693_init_state(sd,&a));assert(!ov5693_init_state(sd,&b));
 assert(!memcmp(&a.crop,&d->mode.crop,sizeof(a.crop)) && !memcmp(&a.format,&d->mode.format,sizeof(a.format)));
 struct v4l2_subdev_format f={.which=V4L2_SUBDEV_FORMAT_TRY,.format={.width=648,.height=486}};
 __typeof__(d->mode) saved=d->mode;unsigned calls=ctrl_calls;
 assert(!ov5693_set_fmt(sd,&a,&f));assert(f.format.width==648 && f.format.height==486);
 f.format.width=0;f.format.height=0;assert(!ov5693_get_fmt(sd,&a,&f));assert(f.format.width==648 && f.format.height==486);
 assert(!ov5693_get_fmt(sd,&b,&f));assert(f.format.width==1296 && f.format.height==972);
 assert(!memcmp(&saved,&d->mode,sizeof(saved)) && ctrl_calls==calls);count+=4;
 struct v4l2_subdev_selection got={.which=V4L2_SUBDEV_FORMAT_TRY,.target=V4L2_SEL_TGT_CROP};
 assert(!ov5693_get_selection(sd,&a,&got) && !memcmp(&got.r,&a.crop,sizeof(got.r)));
 got.which=V4L2_SUBDEV_FORMAT_ACTIVE;
 assert(!ov5693_get_selection(sd,NULL,&got) && !memcmp(&got.r,&d->mode.crop,sizeof(got.r)));count+=2;
 for(int busy=0;busy<2;busy++)for(unsigned which=0;which<2;which++) {
  d->streaming=busy;saved=d->mode;calls=ctrl_calls;
  struct v4l2_subdev_format req={.which=which,.format={.width=UINT_MAX,.height=UINT_MAX}},before=req;
  struct v4l2_subdev_selection sel={.which=which,.target=V4L2_SEL_TGT_CROP,.r={.left=40,.top=80,.width=200,.height=100}},sel_before=sel;
  int expected=busy && which==V4L2_SUBDEV_FORMAT_ACTIVE?-EBUSY:0;
  assert(ov5693_set_fmt(sd,&a,&req)==expected);
  if(expected)assert(!memcmp(&before,&req,sizeof(req)) && !memcmp(&saved,&d->mode,sizeof(saved)) && ctrl_calls==calls);
  assert(ov5693_set_selection(sd,&a,&sel)==expected);
  if(expected)assert(!memcmp(&sel,&sel_before,sizeof(sel)) && !memcmp(&saved,&d->mode,sizeof(saved)) && ctrl_calls==calls);
  if(which==V4L2_SUBDEV_FORMAT_TRY)assert(!memcmp(&saved,&d->mode,sizeof(saved)) && ctrl_calls==calls);
  count+=2;
 }
 d->streaming=false;
 for(int invalid=0;invalid<3;invalid++) {
  struct v4l2_subdev_format req={.which=V4L2_SUBDEV_FORMAT_ACTIVE,.format={.width=640,.height=480}},before;
  struct v4l2_subdev_state *state=&a;
  if(invalid==0)req.pad=1;if(invalid==1)req.which=99;if(invalid==2){req.which=V4L2_SUBDEV_FORMAT_TRY;state=NULL;}
  before=req;saved=d->mode;assert(ov5693_set_fmt(sd,state,&req)==-EINVAL && !memcmp(&req,&before,sizeof(req)));
  assert(ov5693_get_fmt(sd,state,&req)==-EINVAL && !memcmp(&req,&before,sizeof(req)));
  assert(!memcmp(&saved,&d->mode,sizeof(saved)));count+=2;
 }
}
static void t4_checks(struct t4ka3_data *d,struct v4l2_subdev_state *active,struct mutex *lock) {
 const int positions[]={INT_MIN,-1,0,1,17,2463,2464,3279,3280,INT_MAX};
 const unsigned sizes[]={0,1,2,3,16,2464,3280,UINT_MAX-1,UINT_MAX};
 for(unsigned which=0;which<2;which++)for(unsigned x=0;x<10;x++)for(unsigned y=0;y<10;y++)for(unsigned z=0;z<9;z++) {
  struct v4l2_subdev_state trial=*active;struct v4l2_subdev_state *state=which==V4L2_SUBDEV_FORMAT_ACTIVE?active:&trial;
  struct v4l2_subdev_selection sel={.which=which,.target=V4L2_SEL_TGT_CROP,.r={positions[x],positions[y],sizes[z],sizes[8-z]}};
  mutex_lock(lock);d->streaming=0;__typeof__(d->mode) old=d->mode;
  assert(!t4ka3_set_selection(&d->sd,state,&sel));
  assert(sel.r.left>=0 && sel.r.top>=0 && sel.r.width>=2 && sel.r.height>=2 && !(sel.r.width&1) && !(sel.r.height&1));
  assert((uint64_t)sel.r.left+sel.r.width<=3280 && (uint64_t)sel.r.top+sel.r.height<=2464);
  struct v4l2_subdev_format req={.which=which,.format={.width=UINT_MAX,.height=UINT_MAX}};
  assert(!t4ka3_set_pad_format(&d->sd,state,&req));assert(req.format.width==sel.r.width && req.format.height==sel.r.height);
  if(which==V4L2_SUBDEV_FORMAT_TRY)assert(!memcmp(&old,&d->mode,sizeof(old)));
  mutex_unlock(lock);count+=2;
 }
 mutex_lock(lock);
 active->crop=(struct v4l2_rect){.left=0,.top=0,.width=2000,.height=1200};active->format.width=1000;active->format.height=600;
 struct v4l2_subdev_selection moved={.which=V4L2_SUBDEV_FORMAT_ACTIVE,.target=V4L2_SEL_TGT_CROP,.r={100,80,2000,1200}};
 assert(!t4ka3_set_selection(&d->sd,active,&moved));assert(d->mode.binning==2 && d->mode.win_x==50 && d->mode.win_y==40);count++;
 struct v4l2_subdev_format req={.which=V4L2_SUBDEV_FORMAT_ACTIVE,.format={.width=4,.height=4}},before=req;
 __typeof__(d->mode) mode=d->mode;struct v4l2_subdev_state saved=*active;unsigned calls=ctrl_calls;d->streaming=1;
 assert(t4ka3_set_pad_format(&d->sd,active,&req)==-EBUSY && !memcmp(&req,&before,sizeof(req)));
 struct v4l2_subdev_selection sel={.which=V4L2_SUBDEV_FORMAT_ACTIVE,.target=V4L2_SEL_TGT_CROP,.r={400,200,100,100}},orig=sel;
 assert(t4ka3_set_selection(&d->sd,active,&sel)==-EBUSY && !memcmp(&sel,&orig,sizeof(sel)));
 assert(!memcmp(&saved,active,sizeof(saved)) && !memcmp(&mode,&d->mode,sizeof(mode)) && ctrl_calls==calls);count+=2;
 struct v4l2_subdev_state trial=*active;sel.which=V4L2_SUBDEV_FORMAT_TRY;assert(!t4ka3_set_selection(&d->sd,&trial,&sel));assert(!memcmp(&saved,active,sizeof(saved)) && !memcmp(&mode,&d->mode,sizeof(mode)));count++;
 mutex_unlock(lock);
}
static struct ov5693_device concurrent;
static struct v4l2_subdev concurrent_sd;
static void *writer(void *unused) {
 (void)unused;
 for(unsigned i=0;i<50000;i++) {
  struct v4l2_subdev_format f={.which=V4L2_SUBDEV_FORMAT_ACTIVE,.format={.width=i&1?1296:648,.height=i&1?972:486}};
  assert(!ov5693_set_fmt(&concurrent_sd,NULL,&f));
 }
 return NULL;
}
static void *reader(void *unused) {
 (void)unused;
 for(unsigned i=0;i<50000;i++) {
  struct v4l2_subdev_format f={.which=V4L2_SUBDEV_FORMAT_ACTIVE};assert(!ov5693_get_fmt(&concurrent_sd,NULL,&f));
  assert((f.format.width==1296 && f.format.height==972)||(f.format.width==648 && f.format.height==486));
  struct v4l2_subdev_frame_size_enum e={.which=V4L2_SUBDEV_FORMAT_ACTIVE,.code=0x3007};assert(!ov5693_enum_frame_size(&concurrent_sd,NULL,&e));assert(e.min_width==1296 && e.min_height==972);
 }
 return NULL;
}
int main(void) {
 struct control vb={0},hb={0};struct ov5693_device ov={.pixel_rate=160000000,.mipad2=true,.ctrls={&vb,&hb}};
 mutex_init(&ov.lock);vb.lock=hb.lock=&ov.lock;ov.mode.crop=(struct v4l2_rect){.width=1296,.height=972};ov.mode.format=(struct v4l2_mbus_framefmt){.width=1296,.height=972,.code=0x3007};
 struct v4l2_subdev sd={.sensor=&ov};ov_checks(&ov,&sd);
 struct mutex shared={0};mutex_init(&shared);struct control tv={.lock=&shared},th={.lock=&shared};
 struct t4ka3_data t4={.ctrls={&tv,&th}};t4.sd.sensor=&t4;t4.sd.state_lock=&shared;
 struct v4l2_subdev_state active={.crop={.width=3280,.height=2464},.format={.width=3280,.height=2464,.code=0x300a}};t4_checks(&t4,&active,&shared);
 struct control cv={0},ch={0};concurrent.pixel_rate=160000000;concurrent.mipad2=true;concurrent.ctrls.vblank=&cv;concurrent.ctrls.hblank=&ch;
 mutex_init(&concurrent.lock);cv.lock=ch.lock=&concurrent.lock;concurrent.mode.crop=(struct v4l2_rect){.width=1296,.height=972};concurrent.mode.format=(struct v4l2_mbus_framefmt){.width=1296,.height=972};concurrent_sd.sensor=&concurrent;
 pthread_t a,b;assert(!pthread_create(&a,NULL,writer,NULL));assert(!pthread_create(&b,NULL,reader,NULL));assert(!pthread_join(a,NULL));assert(!pthread_join(b,NULL));
 printf("PASS %u actual geometry/TRY/busy/edge/window cases and150000 concurrent callback operations; pthread/control/state stubs, no DMA/I2C/full rollback proof\n",count);
}
'''
with tempfile.TemporaryDirectory(prefix='mipad2-geometry-lock-') as temp:
 p=Path(temp);c=p/'test.c';c.write_text(base+'\n'.join(defs)+'\n'+''.join(parts[n] for n in ovnames+t4names)+cases)
 subprocess.run(['gcc','-O1','-g','-Wall','-Wextra','-Werror','-Wno-sign-compare','-Wno-misleading-indentation','-Wno-unused-parameter',
  '-fsanitize=address,undefined','-fno-omit-frame-pointer','-no-pie','-pthread',str(c),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True,timeout=30)
