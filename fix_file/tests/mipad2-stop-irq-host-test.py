#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
from pathlib import Path
import ast,subprocess,tempfile,json,hashlib,os
r=Path(os.environ.get('MIPAD2_KERNEL_SOURCE',str(Path(__file__).resolve().parents[2])));report_temp=tempfile.TemporaryDirectory(prefix='mipad2-public-host-');out=Path(report_temp.name)
def fn(path,signature):
 s=(r/path).read_text();a=s.index(signature);i=s.index('{',a)+1;depth=1
 while depth:
  depth+=(s[i]=='{')-(s[i]=='}');i+=1
 return s[a:i]
test=r/'fix_file/tests/mipad2-stream-start-unwind-host-test.py';tree=ast.parse(test.read_text());base=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='base' for t in n.targets))
base=base.replace('struct atomisp_video_pipe {','struct atomisp_video_pipe;struct vb2_queue {struct atomisp_video_pipe *owner;int done_wq;};\nstruct atomisp_video_pipe {struct vb2_queue vb_queue;bool stopping;')
base=base.replace('struct vb2_queue {struct atomisp_video_pipe *owner;};','')
base=base.replace('static void cancel_work_sync(int *work) {(void)work;}', 'static struct atomisp_device *current;static int cancellations,drain_queries;\nstatic void cancel_work_sync(int *work) {(void)work;assert(!current->mutex.locked);cancellations++;}')
base=base.replace('assert(on==1);','assert(on==0);')
base=base.replace('assert(css_started);css_started=false;', 'css_started=false;')
base+='''
#define HZ 100
#define READ_ONCE(x) (x)
#define wait_event_timeout(wq,condition,t) ((void)(wq),(void)(t),(condition)?1:0)
static int atomisp_buffers_in_css(struct atomisp_video_pipe*p){(void)p;drain_queries++;return css_owned;}
'''
stop=fn('drivers/staging/media/atomisp/pci/atomisp_ioctl.c','void atomisp_stop_streaming(')
main=r'''
int main(void){int cases=0;
 for(int ann=0;ann<2;ann++)for(int fatal=0;fatal<2;fatal++)for(int reset=0;reset<2;reset++)for(int create=0;create<2;create++)for(int in_css=0;in_css<2;in_css++){
  struct atomisp_device d={0};current=&d;struct atomisp_video_pipe *p=&d.asd.video_out;p->asd=&d.asd;d.asd.isp=&d;p->vb_queue.owner=p;d.asd.streaming=true;d.isp_fatal_error=fatal;d.media_dev.hw_revision=ann?33:0;
  sensor_error=0;reset_error=reset?-EIO:0;create_error=create?-ENOMEM:0;mc_refs=1;css_owned=in_css?2:0;css_started=true;pipes_ready=true;irq_enabled=true;csi_enabled=ann;
  flushes=resets=recreates=css_stops=dfs_low=sensor_calls=cancellations=drain_queries=0;
  atomisp_stop_streaming(&p->vb_queue);
  bool passed=!d.mutex.locked&&!d.asd.streaming&&!p->stopping&&mc_refs==0&&css_owned==0&&!css_started&&!irq_enabled&&!csi_enabled&&sensor_calls==1&&flushes==1&&flush_state==VB2_BUF_STATE_ERROR&&resets==1&&recreates==!reset&&d.isp_fatal_error==(bool)(fatal||reset||create)&&cancellations==1;
  printf("{\"suite\":\"stop\",\"case\":%d,\"ann\":%d,\"prior_fatal\":%d,\"reset_error\":%d,\"create_error\":%d,\"in_css\":%d,\"passed\":%s}\n",cases++,ann,fatal,reset,create,in_css,passed?"true":"false");
 }return 0;
}
'''
irq=fn('drivers/staging/media/atomisp/pci/atomisp_cmd.c','irqreturn_t atomisp_isr_thread(')
irqbase=r'''
#include <stdio.h>
#include <stdbool.h>
#include <assert.h>
typedef int irqreturn_t;
#define IRQ_HANDLED 1
struct atomisp_device{int lock,mutex;struct{bool streaming;}asd;};
static struct atomisp_device *current;static bool stop_during_wait;static int mutex_calls,css_calls,depth;
#define spin_lock_irqsave(l,f) do{(void)(l);(f)=0;}while(0)
#define spin_unlock_irqrestore(l,f) do{(void)(l);(void)(f);}while(0)
static void mutex_lock(int*p){(void)p;assert(!depth);depth++;mutex_calls++;if(stop_during_wait)current->asd.streaming=false;}
static void mutex_unlock(int*p){(void)p;assert(depth==1);depth--;}
static void atomisp_css_isr_thread(struct atomisp_device*p){assert(depth==1&&p->asd.streaming);css_calls++;}
'''
irqmain=r'''
int main(void){for(int active=0;active<2;active++)for(int stop=0;stop<2;stop++){
 struct atomisp_device d={0};current=&d;d.asd.streaming=active;stop_during_wait=stop;depth=mutex_calls=css_calls=0;
 int ret=atomisp_isr_thread(0,&d);bool passed=ret==IRQ_HANDLED&&!depth&&mutex_calls==active&&css_calls==(active&&!stop);
 printf("{\"suite\":\"irq_recheck\",\"active\":%d,\"stop_during_wait\":%d,\"passed\":%s}\n",active,stop,passed?"true":"false");
}return 0;}
'''
dest=out/'mipad2-r20-stop-irq-host.json';log=dest.with_suffix('.log');assert not dest.exists() and not log.exists();rows=[];logs=[]
with tempfile.TemporaryDirectory(prefix='r20-stop-irq-') as d:
 for name,code in [('stop',base+stop+main),('irq',irqbase+irq+irqmain)]:
  p=Path(d)/(name+'.c');p.write_text(code);binary=Path(d)/name;q=subprocess.run(['cc','-std=gnu11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-parameter',str(p),'-o',str(binary)],capture_output=True,text=True);assert q.returncode==0,q.stderr
  q=subprocess.run([str(binary)],capture_output=True,text=True);assert q.returncode==0,q.stderr;logs.append(q.stdout);rows.extend(json.loads(x) for x in q.stdout.splitlines())
log.write_text('\n'.join(logs));record=dict(passed=all(x['passed'] for x in rows),cases=rows,scope='Exact normal-stop and threaded-IRQ callbacks with explicit state/PM/CSS/VB2 stubs and deterministic stop-during-IRQ-mutex-wait interleaving; NOT SP idle, DMA quiescence, actual queued-work cancellation scheduling or hardware fault proof',source_sha256={f:hashlib.sha256((r/f).read_bytes()).hexdigest() for f in ['drivers/staging/media/atomisp/pci/atomisp_ioctl.c','drivers/staging/media/atomisp/pci/atomisp_cmd.c']})
dest.write_text(json.dumps(record,indent=2)+'\n');print('Stop/IRQ cases',len(rows),'failed',sum(not x['passed'] for x in rows));print([x for x in rows if not x['passed']]);assert record['passed']
