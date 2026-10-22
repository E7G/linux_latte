#!/usr/bin/env python3
"""Actual AtomISP start callback with mocked CSS/media/buffers; no HW claim."""
from pathlib import Path
import os,re,subprocess,tempfile
r=Path(os.environ.get('MIPAD2_KERNEL_SOURCE',str(Path(__file__).resolve().parents[2])))
file='drivers/staging/media/atomisp/pci/atomisp_ioctl.c';rev=os.environ.get('MIPAD2_START_UNWIND_BASELINE')
s=subprocess.check_output(['git','show',rev+':'+file],cwd=r,text=True) if rev else (r/file).read_text()
m=re.search(r'^int atomisp_start_streaming\([^;{}]*\)\s*\{',s,re.M);assert m
end=m.end();depth=1
while depth:depth+=(s[end]=='{')-(s[end]=='}');end+=1
fn=s[m.start():end]
# 7.2 factors rollback and normal stop into this shared helper.
helper=''
if 'static void atomisp_stop_stream(' in s:
    m=re.search(r'^static void atomisp_stop_stream\([^;{}]*\)\s*\{',s,re.M);assert m
    end=m.end();depth=1
    while depth:depth+=(s[end]=='{')-(s[end]=='}');end+=1
    helper=s[m.start():end]
base=r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
struct mutex {int locked;};struct pad {int unused;};struct entity {struct pad pads[1];};
struct atomisp_device;struct atomisp_sub_device;
struct atomisp_video_pipe {struct atomisp_sub_device *asd;struct {struct entity entity;} vdev;int pipe,irq_lock;bool stopping;bool use_sof_sequence;unsigned sequence;};
struct vb2_queue {struct atomisp_video_pipe *owner;};
struct params {bool css_update_params_needed;struct {struct {int dz_config;} update_flag;int dz_config;} css_param;struct {void *dz_config;} config;void *dvs_6axis;bool dis_proj_data_valid;};
struct atomisp_parameters {int dz_config;};
struct atomisp_sub_device {struct atomisp_device *isp;struct atomisp_video_pipe video_out;struct params params;bool streaming;int sof_count,sequence,sequence_temp,input_curr,latest_preview_exp_id,postview_exp_id,preview_exp_id;};
struct atomisp_device {int assert_recovery_work;void *dev;struct mutex mutex;int lock;struct {struct mutex graph_mutex;unsigned hw_revision;} media_dev;struct {unsigned csi_control,i_control;} saved_regs;struct {void *csi_remote_source;} inputs[1];struct atomisp_sub_device asd;bool isp_fatal_error;};
struct pci_dev {int unused;};static struct pci_dev pci;
enum vb2_buffer_state {VB2_BUF_STATE_QUEUED=1,VB2_BUF_STATE_ERROR=2};
enum {IA_CSS_IRQ_INFO_CSS_RECEIVER_SOF=1,ATOMISP_DFS_MODE_AUTO=1,ATOMISP_DFS_MODE_LOW=2,ATOMISP_HW_REVISION_ISP2401=2,ATOMISP_HW_REVISION_SHIFT=4,ATOMISP_HW_STEPPING_B0=1,MRFLD_PCI_CSI_CONTROL=1,PCI_I_CONTROL=2,MRFLD_PCI_I_CONTROL_SRSE_RESET_MASK=4,MRFLD_PCI_CSI_CONTROL_CSI_READY=1};
static int pipe_error,frame_error,media_error,css_error,sensor_error,create_error,reset_error,mc_refs,css_owned,flushes,flush_state,sensor_calls,resets,recreates,css_stops,dfs_low;
static bool css_started,pipes_ready,irq_enabled,csi_enabled;
static struct atomisp_video_pipe *vq_to_pipe(struct vb2_queue *q) {return q->owner;}
static struct pci_dev *to_pci_dev(void *d) {(void)d;return &pci;}
static void mutex_lock(struct mutex *m) {assert(!m->locked);m->locked=1;}
static void mutex_unlock(struct mutex *m) {assert(m->locked);m->locked=0;}
#define spin_lock_irqsave(lock,flags) ((void)(lock),(flags)=0)
#define spin_unlock_irqrestore(lock,flags) ((void)(lock),(void)(flags))
#define dev_dbg(...) ((void)0)
#define dev_err(...) ((void)0)
#define dev_warn(...) ((void)0)
#define atomic_set(p,v) (*(p)=(v))
static int atomisp_pipe_check(struct atomisp_video_pipe *p,bool change) {assert(p->asd->isp->mutex.locked && !change);return p->asd->isp->isp_fatal_error?-EIO:pipe_error;}
static int atomisp_validate_frame_info(struct atomisp_video_pipe *p) {(void)p;return frame_error;}
static void atomisp_setup_input_links(struct atomisp_device *d) {assert(d->media_dev.graph_mutex.locked);}
static int __media_pipeline_start(struct pad *p,int *stream) {(void)p;(void)stream;if(!media_error){assert(mc_refs==0);mc_refs=1;}return media_error;}
static void media_pipeline_stop(struct pad *p) {(void)p;assert(mc_refs==1);mc_refs=0;}
static void atomisp_dma_burst_len_cfg(struct atomisp_sub_device *a) {(void)a;}
static void wbinvd(void) {}
static void atomisp_apply_css_parameters(struct atomisp_sub_device *a,void *p) {(void)a;(void)p;}
static void atomisp_css_update_isp_params(struct atomisp_sub_device *a) {(void)a;}
static int atomisp_css_start(struct atomisp_sub_device *a) {(void)a;assert(pipes_ready);if(!css_error)css_started=true;return css_error;}
static bool atomisp_css_valid_sof(struct atomisp_device *d) {(void)d;return true;}
static void atomisp_handle_parameter_and_buffer(struct atomisp_video_pipe *p) {(void)p;}
static void atomisp_qbuffers_to_css(struct atomisp_sub_device *a) {(void)a;assert(css_started);css_owned=2;}
static void atomisp_css_irq_enable(struct atomisp_device *d,int what,bool on) {(void)d;assert(what==1);irq_enabled=on;}
static void atomisp_csi2_configure(struct atomisp_sub_device *a) {(void)a;}
static int atomisp_freq_scaling(struct atomisp_device *d,int mode,bool force) {(void)d;(void)force;if(mode==ATOMISP_DFS_MODE_LOW)dfs_low++;return 0;}
static int pci_write_config_word(struct pci_dev *p,int reg,unsigned val) {(void)p;assert(reg==MRFLD_PCI_CSI_CONTROL);csi_enabled=!!(val&1);return 0;}
static int pci_write_config_dword(struct pci_dev *p,int reg,unsigned val) {(void)p;(void)val;assert(reg==PCI_I_CONTROL);return 0;}
static int sensor_start(void *camera,int on) {(void)camera;assert(on==1);sensor_calls++;return sensor_error;}
#define v4l2_subdev_call(camera,kind,fn,on) sensor_start(camera,on)
static void atomisp_clear_css_buffer_counters(struct atomisp_sub_device *a) {(void)a;css_owned=0;}
static void atomisp_css_stop_preserve_config(struct atomisp_sub_device *a) {(void)a;assert(css_started);css_started=false;pipes_ready=false;css_stops++;}
static void atomisp_flush_video_pipe(struct atomisp_video_pipe *p,int state,bool wake) {(void)p;assert(wake);css_owned=0;flushes++;flush_state=state;}
static void atomisp_subdev_cleanup_pending_events(struct atomisp_sub_device *a) {(void)a;}
static int atomisp_reset(struct atomisp_device *d) {assert(d->mutex.locked);resets++;return reset_error;}
static void cancel_work_sync(int *work) {(void)work;}
static int atomisp_create_pipes_stream(struct atomisp_sub_device *a) {(void)a;recreates++;pipes_ready=!create_error;return create_error;}
'''
cases=r'''
static void init(struct atomisp_device *d,struct atomisp_video_pipe *p,struct vb2_queue *q,bool modern) {
 memset(d,0,sizeof(*d));memset(p,0,sizeof(*p));p->asd=&d->asd;d->asd.isp=d;q->owner=p;
 d->media_dev.hw_revision=modern?((ATOMISP_HW_REVISION_ISP2401<<ATOMISP_HW_REVISION_SHIFT)|ATOMISP_HW_STEPPING_B0):0;
 pipe_error=frame_error=media_error=css_error=sensor_error=create_error=reset_error=mc_refs=css_owned=flushes=sensor_calls=resets=recreates=css_stops=dfs_low=0;
 css_started=irq_enabled=csi_enabled=false;pipes_ready=true;
}
int main(void) {
 unsigned count=0;const int faults[]={-EIO,-EREMOTEIO,-ETIMEDOUT,-ENXIO};
 for(unsigned modern=0;modern<2;modern++)for(unsigned f=0;f<4;f++)for(unsigned broken=0;broken<3;broken++) {
  struct atomisp_device d;struct atomisp_video_pipe p;struct vb2_queue q;init(&d,&p,&q,modern);
  sensor_error=faults[f];create_error=broken==1?-ENOMEM:0;reset_error=broken==2?-ETIMEDOUT:0;
  int ret=atomisp_start_streaming(&q,2);
  assert(!d.asd.streaming && !css_started && mc_refs==0 && css_owned==0 && !irq_enabled && !csi_enabled && "Sensor-start failure must unwind CSS, buffers, CSI and media pipeline");
  assert(ret==sensor_error && flushes==1 && flush_state==VB2_BUF_STATE_QUEUED && css_stops==1 && resets==1 && recreates==(broken==2?0:1) && dfs_low==1);
  assert(!d.mutex.locked && !d.media_dev.graph_mutex.locked);
  assert(d.isp_fatal_error==!!broken && pipes_ready==!broken);
  sensor_error=0;create_error=reset_error=0;
  ret=atomisp_start_streaming(&q,2);
  if(broken)assert(ret==-EIO && !css_started && mc_refs==0);
  else assert(ret==0 && d.asd.streaming && css_started && mc_refs==1 && sensor_calls==2);
  count++;
 }
 for(unsigned stage=0;stage<4;stage++) {
  struct atomisp_device d;struct atomisp_video_pipe p;struct vb2_queue q;init(&d,&p,&q,true);
  if(stage==0)pipe_error=-EINVAL;if(stage==1)frame_error=-ENOSPC;if(stage==2)media_error=-EBUSY;if(stage==3)css_error=-EIO;
  assert(atomisp_start_streaming(&q,2)<0);assert(!d.asd.streaming && !css_started && !mc_refs && !css_owned && flushes==1 && flush_state==VB2_BUF_STATE_QUEUED && !sensor_calls && !css_stops && !resets);
  count++;
 }
 printf("PASS %u extracted AtomISP start/unwind/retry/fatal-recreate/pre-start cases; mocked media/CSS/hardware\n",count);
}
'''
with tempfile.TemporaryDirectory(prefix='mipad2-start-unwind-') as tmp:
 p=Path(tmp);(p/'test.c').write_text(base+helper+fn+cases)
 subprocess.run(['gcc','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-parameter','-Wno-misleading-indentation','-fsanitize=address,undefined','-fno-omit-frame-pointer','-no-pie',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
