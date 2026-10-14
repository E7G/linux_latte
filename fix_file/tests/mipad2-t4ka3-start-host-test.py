"""Extract complete T4KA3 enable callback; stub hardware primitives only."""
from pathlib import Path
import re,subprocess,tempfile,json,hashlib,os
r=Path(os.environ.get('MIPAD2_KERNEL_SOURCE',str(Path(__file__).resolve().parents[2])));src=r/'drivers/media/i2c/t4ka3.c';s=src.read_text()
m=re.search(r'^static int t4ka3_enable_stream\([^;{}]*\)\s*\{',s,re.M);assert m
end=m.end();depth=1
while depth:depth+=(s[end]=='{')-(s[end]=='}');end+=1
fn=s[m.start():end]
c=r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
typedef uint32_t u32; typedef uint64_t u64;
struct v4l2_subdev {void *dev,*owner;};struct v4l2_subdev_state {int unused;};
struct t4ka3_data {struct v4l2_subdev sd;void *dev,*regmap;struct {int handler;} ctrls;int streaming;};
static const int t4ka3_init_config[]={0},t4ka3_pre_mode_set_regs[]={1},t4ka3_post_mode_set_regs[]={2};
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define T4KA3_REG_STREAM 0x100
#define T4KA3_REG_PARAM_HOLD 0x104
#define dev_err(...) ((void)0)
static int refs,pm_result,fault_stage,stage,puts_count,errno_value,standby_count;
static struct t4ka3_data *to_t4ka3_sensor(struct v4l2_subdev *s) {return s->owner;}
static int pm_runtime_get_sync(void *dev) {(void)dev;refs++;return pm_result;}
static void pm_runtime_put(void *dev) {(void)dev;assert(refs>0);refs--;puts_count++;}
static int step(int *error) {
 if(error && *error)return *error;
 stage++;int ret=stage==fault_stage?errno_value:0;if(error)*error=ret;return ret;
}
static int cci_write(void *map,int reg,int value,int *error) {
 (void)map;
 if(stage==0){assert(reg==T4KA3_REG_STREAM && value==0 && !error);standby_count++;}
 else assert(reg==T4KA3_REG_STREAM || reg==T4KA3_REG_PARAM_HOLD);
 return step(error);
}
static int cci_multi_reg_write(void *map,const int *data,unsigned count,int *error) {
 (void)map;(void)data;assert(count==1 && standby_count==1);return step(error);
}
static int t4ka3_set_mode(struct t4ka3_data *t,struct v4l2_subdev_state *state) {(void)t;(void)state;return step(NULL);}
static int __v4l2_ctrl_handler_setup(int *handler) {(void)handler;return step(NULL);}
'''
cases=r'''
int main(void) {
 unsigned n=0;const int faults[]={-EIO,-EREMOTEIO,-ETIMEDOUT,-ENXIO};
 for(unsigned extra=0;extra<2;extra++)for(unsigned positive=0;positive<2;positive++)for(unsigned err=0;err<4;err++)for(unsigned fail=0;fail<=9;fail++) {
  struct t4ka3_data t={0};t.sd.owner=&t;refs=extra;pm_result=positive;errno_value=faults[err];fault_stage=fail;stage=puts_count=standby_count=0;
  int ret=t4ka3_enable_stream(&t.sd,NULL,0,1);
  assert(standby_count==1 && "Standby must precede all configuration writes");
  if(fail)assert(ret==errno_value && !t.streaming && refs==(int)extra && puts_count==1 && stage==(int)fail);
  else assert(ret==0 && t.streaming && refs==(int)extra+1 && puts_count==0 && stage==9);
  n++;
 }
 for(unsigned extra=0;extra<2;extra++)for(unsigned err=0;err<4;err++) {
  struct t4ka3_data t={0};t.sd.owner=&t;refs=extra;pm_result=faults[err];stage=puts_count=standby_count=0;
  assert(t4ka3_enable_stream(&t.sd,NULL,0,1)==pm_result && !t.streaming && refs==(int)extra && puts_count==1 && stage==0 && standby_count==0);n++;
 }
 printf("PASS %u complete extracted T4KA3 enable/positive-PM/bus/control/error-unwind cases; hardware primitives mocked\n",n);
}
'''
with tempfile.TemporaryDirectory(prefix='mipad2-r19-t4-enable-') as temp:
 p=Path(temp);(p/'test.c').write_text(c+fn+cases)
 subprocess.run(['gcc','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-fsanitize=address,undefined','-fno-omit-frame-pointer','-no-pie',str(p/'test.c'),'-o',str(p/'test')],check=True)
 q=subprocess.run([str(p/'test')],capture_output=True,text=True)
 print(q.stdout+q.stderr);assert q.returncode==0
