#!/usr/bin/env python3
"""Compile OV5693 streaming and T4KA3 stop callbacks with the V4L2 wrappers.

Runtime PM, register delivery and sensor programming use host stubs.
This checks lifecycle and refcounts, not hardware powerdown or full AtomISP.
"""
from pathlib import Path
import os,re,subprocess,tempfile
r=Path(os.environ.get('MIPAD2_KERNEL_SOURCE',str(Path(__file__).resolve().parents[2])))
if not (r/'drivers/media/i2c/ov5693.c').is_file():
 raise RuntimeError('Use MIPAD2_KERNEL_SOURCE or run from fix_file/tests in kernel tree')
revision=os.environ.get('MIPAD2_STREAM_STOP_BASELINE')
def extract(file,fn):
 s=subprocess.check_output(['git','show',revision+':'+file],cwd=r,text=True) if revision else (r/file).read_text()
 m=re.search(r'^(?:static )?(?:int|void) '+fn+r'\([^;{}]*\)\s*\{',s,re.M);assert m,fn
 pos=m.end();depth=1
 while depth:depth+=(s[pos]=='{')-(s[pos]=='}');pos+=1
 return s[m.start():pos]
base=r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32;typedef uint64_t u64;
#define BITS_PER_BYTE 8
#define BIT_ULL(n) (1ULL<<(n))
#define MEDIA_PAD_FL_SOURCE 1
struct device {int unused;};struct mutex {int locked;};
struct v4l2_subdev_state {int locked;};struct v4l2_subdev;
struct video_ops {int (*s_stream)(struct v4l2_subdev *,int);};
struct pad_ops {int (*disable_streams)(struct v4l2_subdev *,struct v4l2_subdev_state *,u32,u64);};
struct ops {struct video_ops *video;struct pad_ops *pad;};
struct media_device {struct device *dev;};struct pad {unsigned flags;};
struct v4l2_subdev {void *owner;struct device *dev;struct ops *ops;bool s_stream_enabled,privacy;u64 enabled_pads;
 struct {unsigned num_pads;struct pad *pads;struct {struct media_device *mdev;} graph_obj;} entity;
 struct v4l2_subdev_state state;};
struct handler {int unused;};
struct ov5693_device {struct mutex lock;struct device *dev;struct {struct handler handler;} ctrls;bool streaming,needs_reinit;};
struct t4ka3_data {struct v4l2_subdev sd;struct device *dev;void *regmap;int streaming;};
static int refs,pm_puts,sync_puts,writes,stop_error,pm_error,start_error,mode_error,setup_error,init_error,inits,suspend_error;
static int modes,setups,start_writes,stop_writes;
static bool powered=true,wire_streaming,start_lands_on_error;
static struct ov5693_device *to_ov5693_sensor(struct v4l2_subdev *sd) {return sd->owner;}
static struct t4ka3_data *to_t4ka3_sensor(struct v4l2_subdev *sd) {return sd->owner;}
static void mutex_lock(struct mutex *m) {assert(!m->locked);m->locked=1;}
static void mutex_unlock(struct mutex *m) {assert(m->locked);m->locked=0;}
static int pm_runtime_resume_and_get(void *d) {
#ifdef TEST_OV
 struct ov5693_device *o=d;assert(!o->lock.locked && "Runtime resume may take sensor mutex");
#else
 (void)d;
#endif
 if(pm_error)return pm_error;
 refs++;powered=true;return 0;
}
static void pm_runtime_put(void *d) {(void)d;assert(refs>0);refs--;pm_puts++;}
static int pm_runtime_put_sync_suspend(void *d) {
 struct ov5693_device *o=d;
#ifdef TEST_OV
 assert(!o->lock.locked && "Runtime suspend may take sensor mutex");
#else
 (void)o;
#endif
 assert(refs>0);refs--;pm_puts++;sync_puts++;
 if(refs)return -EBUSY;
 if(suspend_error)return suspend_error;
 powered=false;wire_streaming=false;return 0;
}
static int ov5693_mode_configure(struct ov5693_device *o) {
 assert(o->lock.locked && powered && !wire_streaming);modes++;return mode_error;
}
static int ov5693_sensor_init(struct ov5693_device *o) {
 assert(o->lock.locked && powered);inits++;if(!init_error)wire_streaming=false;return init_error;
}
static int __v4l2_ctrl_handler_setup(struct handler *h) {
 (void)h;assert(!wire_streaming);setups++;return setup_error;
}
static int ov5693_enable_streaming(struct ov5693_device *o,bool on) {
 assert(o->lock.locked && powered);writes++;
 if(on) {
  assert(!wire_streaming);start_writes++;
  if(!start_error || start_lands_on_error)wire_streaming=true;
  return start_error;
 }
 stop_writes++;
 if(!stop_error)wire_streaming=false;
 return stop_error;
}
#define T4KA3_REG_STREAM 0x0100
static int cci_write(void *m,unsigned reg,int v,void *err) {(void)m;assert(reg==T4KA3_REG_STREAM && v==0 && !err);writes++;return stop_error;}
#define dev_err(...) ((void)0)
#define dev_warn(...) ((void)0)
#define dev_dbg(...) ((void)0)
#define WARN_ON(x) (!!(x))
static void v4l2_subdev_enable_privacy_led(struct v4l2_subdev *s) {s->privacy=true;}
static void v4l2_subdev_disable_privacy_led(struct v4l2_subdev *s) {s->privacy=false;}
static bool v4l2_subdev_is_streaming(struct v4l2_subdev *s) {return s->enabled_pads!=0;}
#define v4l2_subdev_has_op(sd,type,fn) ((sd)->ops->type && (sd)->ops->type->fn)
#define v4l2_subdev_call(sd,type,fn,...) ((sd)->ops->type->fn(sd,__VA_ARGS__))
static struct v4l2_subdev_state *v4l2_subdev_lock_and_get_active_state(struct v4l2_subdev *s) {assert(!s->state.locked);s->state.locked=1;return &s->state;}
static void v4l2_subdev_unlock_state(struct v4l2_subdev_state *s) {assert(s->locked);s->locked=0;}
static void v4l2_subdev_collect_streams(struct v4l2_subdev *s,struct v4l2_subdev_state *st,u32 pad,u64 mask,u64 *found,u64 *enabled) {
 (void)pad;assert(st->locked && mask==1);*found=1;*enabled=s->enabled_pads?1:0;
}
static void v4l2_subdev_set_streams_enabled(struct v4l2_subdev *s,struct v4l2_subdev_state *st,u32 p,u64 mask,bool on) {
 assert(st->locked && p==0 && mask==1);s->enabled_pads=on?1:0;
}
'''
cases=r'''
static int t4_bridge(struct v4l2_subdev *sd,int enable) {
 if(!enable)return v4l2_subdev_disable_streams(sd,0,1);
 /* Enable is a PM/flag stub; stop and both core wrappers are extracted. */
 struct t4ka3_data *t=sd->owner;assert(!sd->enabled_pads);refs++;powered=true;t->streaming=1;sd->enabled_pads=1;return 0;
}
#ifdef TEST_OV
static void test_ov_start_recovery(void)
{
 enum { PM, INIT, MODE, SETUP, START };
 const int failures[]={-EIO,-EREMOTEIO,-ETIMEDOUT,-ENXIO};
 const int standby_failures[]={0,-EAGAIN,-EREMOTEIO};
 unsigned int cases=0;

 for(int phase=PM;phase<=START;phase++)
 for(int stale=0;stale<=1;stale++) {
  if((phase==INIT && !stale) || (phase==MODE && stale))continue;
  for(unsigned int first=0;first<sizeof(failures)/sizeof(*failures);first++)
  for(unsigned int stop=0;stop<sizeof(standby_failures)/sizeof(*standby_failures);stop++)
  for(int extra=0;extra<=1;extra++)
  for(int suspend_fails=0;suspend_fails<=1;suspend_fails++)
  for(int landed=0;landed<=1;landed++) {
   struct ov5693_device sensor={.needs_reinit=stale};
   struct video_ops video={.s_stream=ov5693_s_stream};
   struct ops ops={.video=&video};
   struct v4l2_subdev sd={.owner=&sensor,.ops=&ops};
   int error=failures[first];
   bool suspend_requested=phase!=PM && stop;
   bool suspended=suspend_requested && !extra && !suspend_fails;

   sensor.dev=(void*)&sensor;
   refs=extra;pm_puts=sync_puts=writes=inits=modes=setups=start_writes=stop_writes=0;
   powered=true;wire_streaming=stale;start_lands_on_error=landed;
   pm_error=phase==PM?error:0;init_error=phase==INIT?error:0;
   mode_error=phase==MODE?error:0;setup_error=phase==SETUP?error:0;
   start_error=phase==START?error:0;stop_error=standby_failures[stop];
   suspend_error=suspend_fails?-ENXIO:0;

   assert(call_s_stream(&sd,1)==error && refs==extra);
   assert(!sd.s_stream_enabled && !sd.privacy && !sensor.streaming && !sensor.lock.locked);
   assert(pm_puts==(phase!=PM) && sync_puts==suspend_requested);
   assert(sensor.needs_reinit==(phase!=PM || stale));
   assert(inits==(phase!=PM && stale) && modes==(phase!=PM && !stale));
   assert(setups==(phase==SETUP || phase==START));
   assert(start_writes==(phase==START) && stop_writes==(phase!=PM));
   assert(powered==!suspended);
   if(suspended || (phase!=PM && !stop))assert(!wire_streaming);
   int before=writes;
   assert(call_s_stream(&sd,0)==0 && writes==before && refs==extra);

   /* An extra PM owner is allowed: next start still runs full initialization. */
   bool reinit_on_retry=sensor.needs_reinit;
   int old_inits=inits;
   pm_error=init_error=mode_error=setup_error=start_error=stop_error=suspend_error=0;
   assert(call_s_stream(&sd,1)==0 && sensor.streaming && wire_streaming);
   assert(sd.s_stream_enabled && sd.privacy && refs==extra+1 && !sensor.needs_reinit);
   assert(inits==old_inits+reinit_on_retry);
   assert(call_s_stream(&sd,0)==0 && refs==extra && !wire_streaming);
   cases++;
  }
 }
 printf("PASS %u extracted OV5693 start/unwind and V4L2 ownership cases\n",cases);
}
#endif
int main(void) {
 const int faults[]={0,-EIO,-EREMOTEIO,-ETIMEDOUT,-ENXIO};unsigned cases=0;
 for(unsigned e=0;e<5;e++)for(unsigned extra=0;extra<2;extra++)for(unsigned repeat=1;repeat<=8;repeat++) {
  refs=extra;pm_puts=sync_puts=writes=inits=0;stop_error=faults[e];powered=true;suspend_error=0;
  wire_streaming=false;
  struct device d={0};struct media_device md={.dev=&d};struct pad pad={.flags=MEDIA_PAD_FL_SOURCE};
  struct video_ops video={0};struct pad_ops pads={0};struct ops ops={.video=&video,.pad=&pads};
#ifdef TEST_OV
  struct ov5693_device sensor={0};sensor.dev=(void*)&sensor;
  struct v4l2_subdev sd={.owner=&sensor,.dev=&d,.ops=&ops};video.s_stream=ov5693_s_stream;
#else
  struct t4ka3_data sensor={0};sensor.sd.dev=&d;sensor.dev=&d;
  struct v4l2_subdev sd={.owner=&sensor,.dev=&d,.ops=&ops};video.s_stream=t4_bridge;pads.disable_streams=t4ka3_disable_stream;
#endif
  sd.entity.num_pads=1;sd.entity.pads=&pad;sd.entity.graph_obj.mdev=&md;
  assert(call_s_stream(&sd,1)==0 && sensor.streaming && sd.s_stream_enabled && sd.privacy && refs==(int)extra+1);
  int before=writes;
  assert(call_s_stream(&sd,0)==0);
  assert(!sd.s_stream_enabled && !sd.privacy);
  assert(!sensor.streaming && refs==(int)extra && pm_puts==1 && "Core stop completion must release the stream's own PM reference");
#ifndef TEST_OV
  assert(sd.enabled_pads==0 && !sd.state.locked && "Pad and legacy state must both complete stop");
#endif
  assert(writes==before+1);
  assert(sync_puts==(e!=0) && "Failed stop requests synchronous powerdown, not an orphaned ref");
  if(e && !extra)assert(!powered);
  before=writes;
  for(unsigned j=0;j<repeat;j++)assert(call_s_stream(&sd,0)==0);
  assert(refs==(int)extra && pm_puts==1 && writes==before);
  stop_error=0;
  assert(call_s_stream(&sd,1)==0 && sensor.streaming && refs==(int)extra+1);
#ifdef TEST_OV
  if(e)assert(!sensor.needs_reinit && inits==1 && "Reinitialize unknown hardware state on next start even while power stayed on");
#endif
  assert(call_s_stream(&sd,0)==0 && refs==(int)extra && pm_puts==2);cases++;
 }
 printf("PASS %u extracted callback/core stop, PM, idle and restart cases; mocked bus/power/enable infrastructure, not hardware proof\n",cases);
#ifdef TEST_OV
 test_ov_start_recovery();
#endif
}
'''
core=extract('drivers/media/v4l2-core/v4l2-subdev.c','call_s_stream')
disable=extract('drivers/media/v4l2-core/v4l2-subdev.c','v4l2_subdev_disable_streams')
for sensor,file,fn in [('ov5693','drivers/media/i2c/ov5693.c','ov5693_s_stream'),('t4ka3','drivers/media/i2c/t4ka3.c','t4ka3_disable_stream')]:
 if os.environ.get('MIPAD2_STREAM_STOP_SENSOR','both') not in ('both',sensor):continue
 with tempfile.TemporaryDirectory(prefix='mipad2-core-stop-') as temp:
  p=Path(temp);code=base+extract(file,fn)+disable+core+cases;(p/'test.c').write_text(code)
  args=['gcc','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-parameter','-Wno-unused-variable','-fsanitize=address,undefined','-fno-omit-frame-pointer','-no-pie']
  if sensor=='ov5693':args+=['-DTEST_OV']
  subprocess.run(args+[str(p/'test.c'),'-o',str(p/'test')],check=True);print(sensor,flush=True);subprocess.run([str(p/'test')],check=True)
