from pathlib import Path
import ast,re,subprocess,tempfile,json,hashlib,sys,os
r=Path(os.environ.get('MIPAD2_KERNEL_SOURCE',str(Path(__file__).resolve().parents[2])))
mode='current'
report_temp=tempfile.TemporaryDirectory(prefix='mipad2-stream-stop-report-')
out=Path(report_temp.name)

def extract(s,name):
 m=re.search(r'^(?:static )?(?:void|int) '+name+r'\([^;]*?\)\n\{',s,re.M);assert m,name
 i=s.index('{',m.start())+1;depth=1
 while depth:depth+=(s[i]=='{')-(s[i]=='}');i+=1
 return s[m.start():i]

ioctl=(r/'drivers/staging/media/atomisp/pci/atomisp_ioctl.c').read_text();compat=(r/'drivers/staging/media/atomisp/pci/atomisp_compat_css20.c').read_text()
tree=ast.parse((r/'fix_file/tests/mipad2-stream-start-unwind-host-test.py').read_text())
base=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='base' for t in n.targets))
base=base.replace('struct atomisp_video_pipe {','struct atomisp_video_pipe;struct vb2_queue {struct atomisp_video_pipe *owner;int done_wq;};\nstruct atomisp_video_pipe {struct vb2_queue vb_queue;bool stopping;')
base=base.replace('struct vb2_queue {struct atomisp_video_pipe *owner;};','')
base=base.replace('assert(on==1);','assert(on==0);')
base=base.replace('static bool css_started', 'static int drains,firmware_frames,queued_at_stop,resets_at_flush,flush_warning;static struct atomisp_device *current;\nstatic bool css_started')
base=base.replace('assert(css_started);css_started=false;', 'queued_at_stop=firmware_frames;css_started=false;')
base=base.replace('(void)p;assert(wake);css_owned=0;', '(void)p;resets_at_flush=resets;flush_warning=wake;css_owned=0;')
base=base.replace('static void cancel_work_sync(int *work) {(void)work;}', 'static void cancel_work_sync(int *work) {(void)work;assert(!current->mutex.locked);}')
base+='''
#define HZ 1000
#define READ_ONCE(x) (x)
static int atomisp_buffers_in_css(struct atomisp_video_pipe *p){(void)p;return css_owned;}
#define wait_event_timeout(q,condition,t) ((void)(q),(void)(condition),(void)(t),drains++,firmware_frames=0,css_owned=0,1)
'''
main=r'''
int main(void){int cases=0;
for(int fatal=0;fatal<2;fatal++)for(int reset=0;reset<2;reset++)for(int create=0;create<2;create++)for(int queued=0;queued<2;queued++)for(int ann=0;ann<2;ann++){
 struct atomisp_device d={0};current=&d;struct atomisp_video_pipe *p=&d.asd.video_out;p->asd=&d.asd;d.asd.isp=&d;p->vb_queue.owner=p;d.asd.streaming=true;d.isp_fatal_error=fatal;d.media_dev.hw_revision=ann?33:0;
 sensor_error=0;reset_error=reset?-EIO:0;create_error=create?-ENOMEM:0;mc_refs=1;css_owned=firmware_frames=queued?2:0;css_started=true;pipes_ready=true;irq_enabled=true;csi_enabled=ann;
 drains=flushes=resets=recreates=css_stops=dfs_low=sensor_calls=queued_at_stop=resets_at_flush=0;flush_warning=-1;
 atomisp_stop_streaming(&p->vb_queue);
 bool gate=drains==0&&queued_at_stop==(queued?2:0)&&resets_at_flush==1&&flush_warning==0&&!d.mutex.locked&&!p->stopping&&!d.asd.streaming&&mc_refs==0&&css_owned==0&&flushes==1&&resets==1&&recreates==!reset&&d.isp_fatal_error==(bool)(fatal||reset||create);
 printf("{\"suite\":\"stop_order\",\"case\":%d,\"queued\":%d,\"reset_failed\":%d,\"drains\":%d,\"queued_at_css_stop\":%d,\"resets_at_flush\":%d,\"passed\":%s,\"failed_reset_dma_safety_unresolved\":%s}\n",cases++,queued,reset,drains,queued_at_stop,resets_at_flush,gate?"true":"false",reset?"true":"false");
}return 0;}
'''
waitbase=r'''
#include <stdio.h>
#include <stdbool.h>
#include <errno.h>
#include <assert.h>
#include <limits.h>
struct atomisp_device {void *dev;};
struct atomisp_sub_device {struct atomisp_device *isp;};
struct atomisp_stream_env {void *stream;int stream_state;};
enum {CSS_STREAM_STARTED=1,CSS_STREAM_STOPPED=2,CSS_STREAM_UNINIT=3};
static unsigned long jiffies;static int pending,period,stops,destroys;static bool acknowledged;
#define dev_err(dev,...) ((void)(dev))
#define dev_warn(dev,...) ((void)(dev))
#define msecs_to_jiffies(x) (x)
#define time_after(a,b) ((a)>(b))
static void usleep_range(int a,int b){(void)a;(void)b;jiffies++;}
static int ia_css_stream_stop(void *s){(void)s;stops++;return 0;}
static bool ia_css_stream_has_stopped(void *s){(void)s;if(pending&&jiffies>=(unsigned)period)acknowledged=true;return acknowledged;}
static int ia_css_stream_destroy(void *s){(void)s;destroys++;return 0;}
'''
waitmain=r'''
int main(void){int periods[]={10,33,40,41,66,67,100,125,199,200,250,INT_MAX};
for(int q=0;q<2;q++)for(unsigned i=0;i<sizeof(periods)/sizeof(periods[0]);i++){
 struct atomisp_device d={0};struct atomisp_sub_device a={.isp=&d};struct atomisp_stream_env e={.stream=&e,.stream_state=CSS_STREAM_STARTED};
 pending=q;period=periods[i];jiffies=0;stops=destroys=0;acknowledged=false;
 int ret=__destroy_stream(&a,&e);bool nominal=q&&period<=200;
 bool gate=!nominal||(ret==0&&acknowledged&&destroys==1&&jiffies>=(unsigned)period);
 printf("{\"suite\":\"last_frame_wait\",\"pending\":%d,\"frame_period_ms\":%d,\"waited_ms\":%lu,\"nominal\":%s,\"acknowledged\":%s,\"destroyed_without_ack_unresolved\":%s,\"passed\":%s}\n",q,period,jiffies,nominal?"true":"false",acknowledged?"true":"false",destroys&&!acknowledged?"true":"false",gate?"true":"false");
}return 0;}
'''
rows=[]
with tempfile.TemporaryDirectory(prefix='r22-stop-model-') as d:
 for name,code in [('order',base+extract(ioctl,'atomisp_stop_streaming')+main),('wait',waitbase+extract(compat,'__destroy_stream')+waitmain)]:
  p=Path(d)/(name+'.c');exe=Path(d)/name;p.write_text(code)
  c=subprocess.run(['cc','-std=gnu11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-parameter',str(p),'-o',str(exe)],capture_output=True,text=True);assert c.returncode==0,c.stderr
  c=subprocess.run([str(exe)],capture_output=True,text=True);assert c.returncode==0,c.stderr
  rows.extend(json.loads(l) for l in c.stdout.splitlines())
failed=[x for x in rows if not x['passed']];assert len(rows)==56
if mode=='original':assert len(failed)==38,(len(failed),failed)
else:assert not failed,failed
report=dict(mode=mode,cases=rows,total=56,failed=len(failed),original_or_candidate_source_hashes=[hashlib.sha256(s.encode()).hexdigest() for s in [ioctl,compat]],
 scope='Exact stop/stream-destroy functions with explicit CSS/VB2/PM/clock stubs. No-drain, queued-last-frame, flush-after-reset-attempt ordering and 200ms nominal period checks; NOT physical timing/DMA/unknown-power safety proof.',
 unsafe_timeout_destroy_cases=sum(bool(x.get('destroyed_without_ack_unresolved')) for x in rows),failed_reset_return_cases=sum(bool(x.get('failed_reset_dma_safety_unresolved')) for x in rows),hardware_tested=False,physical_fault_injected=False)
p=out/('mipad2-r22-stream-stop-'+mode+'-host.json');assert not p.exists();p.write_text(json.dumps(report,indent=2)+'\n')
print(mode, '56cases, failed',len(failed),'; unresolved timeout destroys',report['unsafe_timeout_destroy_cases'],'; known failed-reset buffer-return gap retained, not a DMA safety fix.')
