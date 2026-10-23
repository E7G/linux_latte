#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Compile the exact AtomISP DDR/power and IOSF RMW functions with explicit stubs.

Only the PCI mailbox endpoint, clock and logging are synthetic. No physical
fault injection, power residency, DMA fence, sensor or optical proof is implied.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile


def extract(text, name):
    match = re.search(r'^[\w *]+\b'+name+r'\([^;]*?\)\n\{', text, re.M)
    assert match, name
    end = text.index('{', match.start()) + 1
    depth = 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[match.start():end]


HEADER = r"""
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <errno.h>
#include <string.h>
typedef uint8_t u8;
typedef uint32_t u32;
#define BT_MBI_UNIT_PMC 0x04
#define BT_MBI_UNIT_GFX 0x06
#define MBI_REG_READ 0x10
#define MBI_REG_WRITE 0x11
#define MBI_MASK_LO 0xff
#define MBI_MASK_HI 0xffffff00U
#define MBI_RD_MASK 0xfeffffffU
#define MBI_WR_MASK 0x01000000U
#define MRFLD_BIT0 1U
#define MRFLD_BIT1 2U
#define MRFLD_ISPSSDVFS 0x36
#define MRFLD_ISPSSPM0 0x39
#define MRFLD_ISPSSPM0_IUNIT_POWER_ON 0
#define MRFLD_ISPSSPM0_IUNIT_POWER_OFF 3
#define MRFLD_ISPSSPM0_ISPSSC_MASK 3
#define MRFLD_ISPSSPM0_ISPSSS_OFFSET 24
#define PCI_D0 0
#define PCI_D3cold 4
#define msecs_to_jiffies(n) (n)
#define time_after(a,b) ((long)((b)-(a))<0)
#define IS_CHT cherrytrail
#define to_pci_dev(p) ((struct pci_dev *)(p))
#define WARN_ON(x) ((void)(x))
#define dev_dbg(...) ((void)0)
#define str_on_off(b) ((b)?"on":"off")
struct pci_dev {int current_state;};
struct atomisp_device {void *dev;bool pm_only;};
static bool cherrytrail, mutate_on_read_unlock, mutation_applied;
static unsigned long jiffies;
static int iosf_mbi_lock,lock_depth,lock_errors,locks,unlocks;
static int ddr_reads,ddr_writes,power_reads,power_writes;
static int fail_reg,fail_write,fail_nth,fault_errno;
static int errors,warnings,trace_calls,sleep_calls;
static bool request_sent,requested_on,ack_seen,timeout_mode,last_read_only;
static u32 ddr_reg,ddr_written;
static int status_pending_reads;
static char order[64];static unsigned order_len;
static void event(char c){if(order_len+1<sizeof(order)){order[order_len++]=c;order[order_len]=0;}}
#define dev_err(...) do{errors++;event('E');}while(0)
#define dev_warn(...) do{warnings++;event('W');}while(0)
static void lock(void){if(lock_depth++)lock_errors++;locks++;last_read_only=false;}
static void unlock(void){
 if(--lock_depth)lock_errors++;
 unlocks++;
 /* Model a second mailbox client updating an unrelated bit between calls. */
 if(mutate_on_read_unlock&&ddr_reads==1&&!mutation_applied){ddr_reg|=0x80000000U;mutation_applied=true;}
}
#define spin_lock_irqsave(l,f) do{(void)(l);(f)=0;lock();}while(0)
#define spin_unlock_irqrestore(l,f) do{(void)(l);(void)(f);unlock();}while(0)
static u32 iosf_mbi_form_mcr(u8 opcode,u8 port,u32 offset){
 return ((u32)opcode<<24)|((u32)port<<16)|(offset<<8)|0xf0;
}
static bool failed(int reg,bool write,int nth){return fault_errno&&fail_reg==reg&&fail_write==write&&fail_nth==nth;}
static int iosf_mbi_pci_read_mdr(u32 mcrx,u32 mcr,u32 *value){
 (void)mcrx;int reg=(mcr>>8)&0xff;
 if(lock_depth!=1)lock_errors++;
 if(reg==MRFLD_ISPSSDVFS){
  ddr_reads++;event('r');*value=ddr_reg;last_read_only=true;
  if(failed(reg,false,ddr_reads)){*value=0xdeadbeefU;return fault_errno;}
 }else if(reg==MRFLD_ISPSSPM0){
  power_reads++;event('s');*value=requested_on?0:3;
  if(failed(reg,false,power_reads))return fault_errno;
  if(request_sent){
   bool ready=!timeout_mode&&power_reads>status_pending_reads;
   *value=(ready?(requested_on?0U:3U):(requested_on?3U:0U))<<24;
   if(ready)ack_seen=true;
  }
 }else return -EINVAL;
 return 0;
}
static int iosf_mbi_pci_write_mdr(u32 mcrx,u32 mcr,u32 value){
 (void)mcrx;int reg=(mcr>>8)&0xff;last_read_only=false;
 if(lock_depth!=1)lock_errors++;
 if(reg==MRFLD_ISPSSDVFS){
  ddr_writes++;ddr_written=value;event('w');
  if(failed(reg,true,ddr_writes))return fault_errno;
  ddr_reg=value;
 }else if(reg==MRFLD_ISPSSPM0){
  power_writes++;event('p');
  if(failed(reg,true,power_writes))return fault_errno;
  request_sent=true;requested_on=(value&3)==0;
 }else return -EINVAL;
 return 0;
}
static void msleep(int n){if(n!=20)lock_errors++;sleep_calls++;event('d');}
static void usleep_range(int a,int b){(void)a;(void)b;jiffies++;}
static void trace_ipu_cstate(bool on){(void)on;trace_calls++;event('A');if(!ack_seen)lock_errors++;}
static void reset(void){
 jiffies=0;lock_depth=lock_errors=locks=unlocks=0;
 ddr_reads=ddr_writes=power_reads=power_writes=0;
 fail_reg=fail_write=fail_nth=0;fault_errno=0;
 errors=warnings=trace_calls=sleep_calls=0;
 request_sent=requested_on=ack_seen=timeout_mode=last_read_only=false;
 mutate_on_read_unlock=mutation_applied=false;ddr_reg=ddr_written=0;status_pending_reads=2;
 order_len=0;order[0]=0;cherrytrail=true;
}
"""

MAIN = r"""
int main(void){
 unsigned helper_cases=0,helper_failed=0,power_cases=0,power_failed=0;
 int codes[]={0,-EIO,-ENODEV,-EAGAIN,-EBUSY,-ENOMEM};
 for(int enable=0;enable<2;enable++)for(int mutation=0;mutation<2;mutation++)
 for(unsigned input=0;input<4096;input++)for(int stage=0;stage<2;stage++)
 for(unsigned e=0;e<sizeof(codes)/sizeof(codes[0]);e++){
  reset();u32 original=(input*0x9e3779b9U)^(input<<16);ddr_reg=original;
  mutate_on_read_unlock=mutation;fail_reg=MRFLD_ISPSSDVFS;
  fail_write=stage;fail_nth=1;fault_errno=codes[e];
  int ret=invoke_ddr(enable);int expected=codes[e];
  u32 wanted=(original&~3U)|(enable?0U:2U);
  bool success=ret==expected&&!lock_errors&&!lock_depth&&locks==unlocks;
  success=success&&ddr_reads==1&&ddr_writes==(expected&&stage==0?0:1);
  if(!expected)success=success&&ddr_reg==(wanted|(mutation?0x80000000U:0));
  helper_cases++;if(!success)helper_failed++;
 }
 /* Real power function + real mailbox RMW: every power direction/platform gate. */
 for(int cht=0;cht<2;cht++)for(int only=0;only<2;only++)for(int on=0;on<2;on++)
 for(int stage=0;stage<7;stage++)for(unsigned e=1;e<sizeof(codes)/sizeof(codes[0]);e++){
  reset();cherrytrail=cht;timeout_mode=stage==6;
  if(stage==1||stage==2){fail_reg=MRFLD_ISPSSDVFS;fail_write=stage==2;fail_nth=1;}
  if(stage==3||stage==4){fail_reg=MRFLD_ISPSSPM0;fail_write=stage==4;fail_nth=1;}
  if(stage==5){fail_reg=MRFLD_ISPSSPM0;fail_write=0;fail_nth=3;}
  fault_errno=codes[e];ddr_reg=0x12345679U;
  struct pci_dev pci={77};struct atomisp_device isp={.dev=&pci,.pm_only=only};
  int ret=atomisp_mrfld_power(&isp,on);bool dvfs=cht&&!only;
  bool dvfs_fault=dvfs&&(stage==1||stage==2);
  int expected=(dvfs_fault&&on)||stage==3||stage==4||stage==5?codes[e]:stage==6?-EBUSY:0;
  bool early=dvfs_fault&&on;
  bool success=ret==expected&&!lock_errors&&!lock_depth&&locks==unlocks;
  success=success&&(early?(!power_reads&&!power_writes&&!sleep_calls):true);
  success=success&&(expected?(pci.current_state==77&&!trace_calls):
                     (ack_seen&&trace_calls==1&&pci.current_state==(on?PCI_D0:PCI_D3cold)));
  success=success&&warnings==(dvfs_fault&&!on?1:0);
  if(!dvfs)success=success&&!ddr_reads&&!ddr_writes&&!sleep_calls;
  if(dvfs&&on&&!early)success=success&&sleep_calls==1&&order[0]=='r'&&order[1]=='w'&&order[2]=='d';
  if(dvfs&&!on&&stage!=3&&stage!=4){
   char *p=strchr(order,'p'),*r=strchr(order,'r');success=success&&p&&r&&p<r;
  }
  power_cases++;if(!success){
   power_failed++;
   if(power_failed<=5)fprintf(stderr,"power mismatch cht=%d only=%d on=%d stage=%d errno=%d ret=%d expected=%d order=%s warnings=%d state=%d\n",cht,only,on,stage,codes[e],ret,expected,order,warnings,pci.current_state);
  }
 }
 printf("{\"helper_cases\":%u,\"helper_failed\":%u,\"power_cases\":%u,\"power_failed\":%u}\n",helper_cases,helper_failed,power_cases,power_failed);
 return (helper_failed||power_failed)?1:0;
}
"""


def run(root, expect_red=False, mutation=None):
    path = 'drivers/staging/media/atomisp/pci/atomisp_v4l2.c'
    iosf_path = 'arch/x86/platform/intel/iosf_mbi.c'
    driver = (root/path).read_text()
    iosf = (root/iosf_path).read_text()
    helper = extract(driver, 'punit_ddr_dvfs_enable')
    power = extract(driver, 'atomisp_mrfld_power')
    if mutation == 'swallow-on-error':
        old = '\t\t\treturn ret;\n\t\t}\n\t\tmsleep(20);'
        assert power.count(old) == 1
        power = power.replace(old, '\t\t\tret = 0;\n\t\t}\n\t\tmsleep(20);')
    if mutation == 'split-rmw':
        helper = """static int punit_ddr_dvfs_enable(bool enable)
{
 u32 value;
 int ret=iosf_mbi_read(BT_MBI_UNIT_PMC,MBI_REG_READ,MRFLD_ISPSSDVFS,&value);
 if(ret)return ret;
 value=(value&~(MRFLD_BIT0|MRFLD_BIT1))|(enable?0:MRFLD_BIT1);
 return iosf_mbi_write(BT_MBI_UNIT_PMC,MBI_REG_WRITE,MRFLD_ISPSSDVFS,value);
}"""
    if mutation == 'abandon-off-ack':
        old = '\t\tif (ret)\n\t\t\tdev_warn(isp->dev, "Failed to enable DDR DVFS: %d\\n", ret);'
        assert power.count(old) == 1
        power = power.replace(old, '\t\tif (ret) {\n\t\t\tdev_warn(isp->dev, "Failed to enable DDR DVFS: %d\\n", ret);\n\t\t\treturn ret;\n\t\t}')
    core = '\n'.join(extract(iosf,n) for n in ['iosf_mbi_read','iosf_mbi_write','iosf_mbi_modify'])
    # Baseline helper returns void: wrap it only to observe its legacy behavior.
    body = 'punit_ddr_dvfs_enable(enable);return 0;' if helper.startswith('static void ') else 'return punit_ddr_dvfs_enable(enable);'
    wrapper = '\nstatic int invoke_ddr(bool enable){'+body+'}\n'
    with tempfile.TemporaryDirectory(prefix='mipad2-ddr-rmw-') as directory:
        c = Path(directory)/'test.c';binary=Path(directory)/'test'
        c.write_text(HEADER+'\n'+core+'\n'+helper+wrapper+'\n'+power+'\n'+MAIN)
        build = subprocess.run(['cc','-std=gnu11','-O2','-Wall','-Wextra','-Werror',
                                '-Wno-unused-function',*(['-Wno-pointer-sign'] if helper.startswith('static void ') else []),str(c),'-o',str(binary)],capture_output=True,text=True)
        assert build.returncode == 0, build.stderr
        probe = subprocess.run([str(binary)],capture_output=True,text=True,timeout=30)
        record = json.loads(probe.stdout)
    record.update(source_sha256={path:hashlib.sha256(driver.encode()).hexdigest(),
                                 iosf_path:hashlib.sha256(iosf.encode()).hexdigest()},
                  exact_functions=['punit_ddr_dvfs_enable','atomisp_mrfld_power',
                                   'iosf_mbi_read','iosf_mbi_write','iosf_mbi_modify'],
                  mutation=mutation, passed=probe.returncode==0,
                  scope='Exact driver/IOSF functions, synthetic mailbox endpoint, lock interleaving and clock. No physical DDR/power/DMA or OEM-parity proof.')
    print(json.dumps(record,indent=2))
    if probe.stderr:
        print(probe.stderr,end='',file=__import__('sys').stderr)
    assert (not record['passed']) if expect_red else record['passed'], record
    return record


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expect-red',action='store_true')
    parser.add_argument('--mutation',choices=['swallow-on-error','split-rmw','abandon-off-ack'])
    args=parser.parse_args()
    run(Path(os.environ.get('MIPAD2_KERNEL_SOURCE',Path(__file__).resolve().parents[2])),args.expect_red,args.mutation)
