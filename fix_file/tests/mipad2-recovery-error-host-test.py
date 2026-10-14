#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
from pathlib import Path
import subprocess,tempfile,json,hashlib,os
r=Path(os.environ.get('MIPAD2_KERNEL_SOURCE',str(Path(__file__).resolve().parents[2])))
report_temp=tempfile.TemporaryDirectory(prefix='mipad2-public-recovery-');out=Path(report_temp.name)
p=r/'drivers/staging/media/atomisp/pci/atomisp_cmd.c'
prefix='\n#include <stdio.h>\n#include <stdbool.h>\n#include <stddef.h>\n#include <string.h>\n#define container_of(p,t,m) ((t*)((char*)(p)-offsetof(t,m)))\n#define to_pci_dev(p) ((struct pci_dev*)(p))\n#define dev_warn(...) ((void)0)\n#define dev_dbg(...) ((void)0)\n#define dev_err(...) ((void)0)\n#define spin_lock_irqsave(l,f) do{(void)(l);(f)=0;}while(0)\n#define spin_unlock_irqrestore(l,f) do{(void)(l);(void)(f);}while(0)\n#define v4l2_subdev_call(sd,o,f,on) sensor_stream(sd,on)\n#define IA_CSS_IRQ_INFO_CSS_RECEIVER_SOF 1\n#define IA_CSS_INPUT_MODE_BUFFERED_SENSOR 2\n#define hrt_isp_css_irq_sp 3\n#define PCI_I_CONTROL 4\n#define MRFLD_PCI_I_CONTROL_SRSE_RESET_MASK 3\n#define ATOMISP_DFS_MODE_AUTO 5\n#define ATOMISP_DFS_MODE_LOW 6\n#define ATOMISP_HW_REVISION_ISP2401 2\n#define ATOMISP_HW_REVISION_SHIFT 4\n#define ATOMISP_HW_STEPPING_B0 1\n#define MRFLD_PCI_CSI_CONTROL 7\n#define MRFLD_PCI_CSI_CONTROL_CSI_READY 1\n#define VB2_BUF_STATE_ERROR 6\nstruct work_struct{int unused;};struct pci_dev{int unused;};\nstruct atomisp_video_pipe{int vb_queue;bool stopping;};\nstruct atomisp_sub_device{bool streaming;unsigned input_curr;int preview_exp_id,postview_exp_id;struct atomisp_video_pipe video_out;};\nstruct atomisp_device{struct work_struct assert_recovery_work;void*dev;int mutex,lock;struct atomisp_sub_device asd;struct{void*camera;}inputs[2];struct{unsigned hw_revision;}media_dev;struct{int i_control,csi_control;}saved_regs;bool isp_fatal_error;};\nstatic int fault,reset_calls,create_calls,css_start_calls,sensor_start_calls,sensor_stop_calls,queue_errors,flush_calls,lock_depth;static bool sof,csi_ready;static int mc_stops,unsafe_mmio;\nstatic void mutex_lock(int*p){(void)p;lock_depth++;}static void mutex_unlock(int*p){(void)p;lock_depth--;}\nstatic int sensor_stream(void*p,int on){(void)p;if(on){sensor_start_calls++;return fault==4?-5:0;}sensor_stop_calls++;return 0;}\nstatic void atomisp_css_irq_enable(struct atomisp_device*p,int i,bool b){(void)p;(void)i;if(fault==1 && reset_calls)unsafe_mmio++;sof=b;}\nstatic void atomisp_clear_css_buffer_counters(struct atomisp_sub_device*p){(void)p;}\nstatic void atomisp_css_stop(struct atomisp_sub_device*p,bool b){(void)p;(void)b;}\nstatic void atomisp_reset_event(struct atomisp_sub_device*p){(void)p;}\nstatic void disable_isp_irq(int i){(void)i;}static void clear_isp_irq(int i){(void)i;}\nstatic void pci_write_config_dword(struct pci_dev*p,int i,int v){(void)p;(void)i;(void)v;}\nstatic int atomisp_reset(struct atomisp_device*p){(void)p;reset_calls++;return fault==1?-5:0;}\nstatic void atomisp_css_input_set_mode(struct atomisp_sub_device*p,int i){(void)p;(void)i;}\nstatic int atomisp_create_pipes_stream(struct atomisp_sub_device*p){(void)p;create_calls++;return fault==2?-5:0;}\nstatic void wbinvd(void){}\nstatic int atomisp_css_start(struct atomisp_sub_device*p){(void)p;css_start_calls++;return fault==3?-5:0;}\nstatic void atomisp_csi2_configure(struct atomisp_sub_device*p){(void)p;}\nstatic bool atomisp_css_valid_sof(struct atomisp_device*p){(void)p;return true;}\nstatic int atomisp_freq_scaling(struct atomisp_device*p,int i,bool b){(void)p;(void)i;(void)b;return 0;}\nstatic void atomisp_flush_video_pipe(struct atomisp_video_pipe*p,int i,bool b){(void)p;(void)i;(void)b;flush_calls++;}\nstatic void atomisp_recover_params_queue(struct atomisp_video_pipe*p){(void)p;}\nstatic void __attribute__((unused)) vb2_queue_error(int*p){(void)p;queue_errors++;}\n\nstatic void pci_write_config_word(struct pci_dev*p,int reg,int val){(void)p;(void)reg;csi_ready=(val&1)!=0;}\nstatic void __attribute__((unused)) media_pipeline_stop(void*p){(void)p;mc_stops++;}\n'
s=p.read_text();start=s.index('void atomisp_assert_recovery_work(');brace=s.index('{',start);depth=1;i=brace+1
while depth:
 if s[i]=='{':depth+=1
 elif s[i]=='}':depth-=1
 i+=1
function=s[start:i]
suffix=r'''
int main(void){
 for(int stopping=0;stopping<2;stopping++)for(int active=0;active<2;active++)for(int ann=0;ann<2;ann++)for(int f=0;f<=4;f++){
  struct atomisp_device isp={0};struct pci_dev dev={0};isp.dev=&dev;isp.asd.streaming=active;isp.asd.video_out.stopping=stopping;isp.media_dev.hw_revision=ann?33:0;
  fault=f;reset_calls=create_calls=css_start_calls=sensor_start_calls=sensor_stop_calls=queue_errors=flush_calls=lock_depth=mc_stops=unsafe_mmio=0;sof=false;csi_ready=false;
  atomisp_assert_recovery_work(&isp.assert_recovery_work);
  bool short_circuit=f!=1||(!create_calls&&!css_start_calls&&!sensor_start_calls);
  short_circuit=short_circuit&&(f!=2||(!css_start_calls&&!sensor_start_calls))&&(f!=3||!sensor_start_calls);
  bool fail_closed=f==0?(isp.asd.streaming&&sensor_start_calls==1&&sof&&csi_ready==(bool)ann):(isp.isp_fatal_error&&!isp.asd.streaming&&queue_errors==1&&!sof&&!csi_ready);
  bool buffers=flush_calls==((f==0||f==4)?1:0);
  bool gate=(active&&!stopping)?(short_circuit&&fail_closed&&buffers):(reset_calls==0&&create_calls==0&&css_start_calls==0&&sensor_start_calls==0&&queue_errors==0&&flush_calls==0);
  gate=gate&&lock_depth==0&&mc_stops==0&&unsafe_mmio==0;
  printf("{\"active\":%d,\"ann\":%d,\"fault\":%d,\"reset\":%d,\"create\":%d,\"css_start\":%d,\"sensor_start\":%d,\"flush\":%d,\"queue_errors\":%d,\"mc_stops\":%d,\"unsafe_mmio\":%d,\"passed\":%s}\n",active,ann,f,reset_calls,create_calls,css_start_calls,sensor_start_calls,flush_calls,queue_errors,mc_stops,unsafe_mmio,gate?"true":"false");
 }return 0;
}
'''
dest=out/'mipad2-r20-recovery-green-v2-host.json';log=dest.with_suffix('.log');assert not dest.exists() and not log.exists()
with tempfile.TemporaryDirectory(prefix='r20-recovery-green-') as d:
 f=Path(d)/'probe.c';f.write_text(prefix+function+suffix);binary=Path(d)/'test';q=subprocess.run(['cc','-std=gnu11','-O2','-Wall','-Wextra','-Werror',str(f),'-o',str(binary)],capture_output=True,text=True);assert q.returncode==0,q.stderr
 q=subprocess.run([str(binary)],capture_output=True,text=True);assert q.returncode==0,q.stderr;log.write_text(q.stdout+q.stderr);cases=[json.loads(x) for x in q.stdout.splitlines()]
 record=dict(source_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),function_sha256=hashlib.sha256(function.encode()).hexdigest(),cases=cases,passed=all(c['passed'] for c in cases),scope='Exact callback/40 stopping-active-idle legacy-ANN fault combinations; explicit C hardware/CSS/VB2 stubs. Checks failfast, flags/SOF/CSI, no reset-failure MMIO, no premature old-frame flush and no MCstop in worker. NOT real hardware, SP/DMA quiescence or VB2 STREAMOFF cleanup proof.')
 dest.write_text(json.dumps(record,indent=2)+'\n');print('Recovery branch cases',len(cases),'failed',sum(not c['passed'] for c in cases));print([c for c in cases if not c['passed']]);assert record['passed']
