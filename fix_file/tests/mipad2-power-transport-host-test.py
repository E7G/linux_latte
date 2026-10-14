#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
from pathlib import Path
import subprocess,tempfile,json,hashlib,sys,os
r=Path(os.environ.get('MIPAD2_KERNEL_SOURCE',str(Path(__file__).resolve().parents[2])));report_temp=tempfile.TemporaryDirectory(prefix='mipad2-public-host-');out=Path(report_temp.name);phase=sys.argv[1] if len(sys.argv)>1 else 'green';assert phase in ['red','green']
def extract(path,name):
 s=(r/path).read_text();pos=s.index(name+'(');start=s.rfind('\n',0,pos)+1
 # Preserve preceding return-type line if function uses split signature.
 if s[start:pos].strip()=='':start=s.rfind('\n',0,start-1)+1
 brace=s.index('{',pos);depth=1;i=brace+1
 while depth:
  if s[i]=='{':depth+=1
  elif s[i]=='}':depth-=1
  i+=1
 return s[start:i]
iosf='arch/x86/platform/intel/iosf_mbi.c';cmd='drivers/staging/media/atomisp/pci/atomisp_cmd.c';v4l='drivers/staging/media/atomisp/pci/atomisp_v4l2.c'
common=r'''
#include <stdio.h>
#include <stdbool.h>
#include <stdint.h>
#include <errno.h>
#define dev_err(...) ((void)0)
#define dev_dbg(...) ((void)0)
typedef uint32_t u32;
struct pci_dev{int current_state;};
#define PCIBIOS_SUCCESSFUL 0
#define PCIBIOS_FUNC_NOT_SUPPORTED 0x81
#define PCIBIOS_BAD_VENDOR_ID 0x83
#define PCIBIOS_DEVICE_NOT_FOUND 0x86
#define PCIBIOS_BAD_REGISTER_NUMBER 0x87
#define PCIBIOS_SET_FAILED 0x88
#define PCIBIOS_BUFFER_TOO_SMALL 0x89
'''+extract('include/linux/pci.h','pcibios_err_to_errno')
transport=common+r'''
#define MBI_MCRX_OFFSET 1
#define MBI_MCR_OFFSET 2
#define MBI_MDR_OFFSET 3
static struct pci_dev device,*mbi_pdev=&device;
static int calls,fail_at,error;
static int pci_write_config_dword(struct pci_dev*p,int reg,u32 value){(void)p;(void)reg;(void)value;return ++calls==fail_at?error:0;}
static int pci_read_config_dword(struct pci_dev*p,int reg,u32*v){(void)p;(void)reg;int e=++calls==fail_at?error:0;if(!e)*v=0x12345678;return e;}
'''+extract(iosf,'iosf_mbi_pci_read_mdr')+'\n'+extract(iosf,'iosf_mbi_pci_write_mdr')+r'''
int main(void){int case_no=0;
 for(int write=0;write<2;write++)for(int extended=0;extended<2;extended++){
  int total=extended?3:2;
  for(int fail=0;fail<=total;fail++)for(int eidx=0;eidx<5;eidx++){
   int errors[]={-EIO,-ENODEV,PCIBIOS_DEVICE_NOT_FOUND,PCIBIOS_BAD_REGISTER_NUMBER,PCIBIOS_SET_FAILED};
   calls=0;fail_at=fail;error=errors[eidx];u32 output=0xaabbccdd;
   int ret=write?iosf_mbi_pci_write_mdr(extended,7,9):iosf_mbi_pci_read_mdr(extended,7,&output);
   int expected=fail?pcibios_err_to_errno(error):0;
   bool passed=ret==expected&&calls==(fail?fail:total)&&(!(!write&&fail)||output==0xaabbccdd);
   printf("{\"suite\":\"iosf\",\"case\":%d,\"write\":%d,\"extended\":%d,\"fail_at\":%d,\"raw_error\":%d,\"returned\":%d,\"calls\":%d,\"passed\":%s}\n",case_no++,write,extended,fail,error,ret,calls,passed?"true":"false");
  }
 }
 mbi_pdev=NULL;calls=0;u32 value=77;int ret=iosf_mbi_pci_read_mdr(1,7,&value);bool gate=ret==-ENODEV&&!calls&&value==77;printf("{\"suite\":\"iosf_absent\",\"passed\":%s}\n",gate?"true":"false");
 calls=0;ret=iosf_mbi_pci_write_mdr(1,7,9);gate=ret==-ENODEV&&!calls;printf("{\"suite\":\"iosf_absent\",\"passed\":%s}\n",gate?"true":"false");return 0;
}
'''
power=common+r'''
#define to_pci_dev(p) ((struct pci_dev*)(p))
#define IS_CHT 1
#define MRFLD_ISPSSPM0_IUNIT_POWER_ON 0
#define MRFLD_ISPSSPM0_IUNIT_POWER_OFF 3
#define MRFLD_ISPSSPM0_ISPSSC_MASK 3
#define MRFLD_ISPSSPM0_ISPSSS_OFFSET 24
#define MRFLD_ISPSSPM0 8
#define BT_MBI_UNIT_PMC 9
#define MBI_REG_READ 10
#define PCI_D0 0
#define PCI_D3cold 4
#define msecs_to_jiffies(n) (n)
#define time_after(a,b) ((long)((b)-(a))<0)
static unsigned long jiffies;static int modify_error,read_error,read_fail_at,reads,writes,ready_at,trace_calls,dvfs_calls,off_error,on_error,off_calls,on_calls;static u32 requested;
struct atomisp_device{void*dev;bool pm_only,isp_fatal_error;};
static void punit_ddr_dvfs_enable(bool b){(void)b;dvfs_calls++;}
static void msleep(int n){(void)n;}
static void usleep_range(int a,int b){(void)a;(void)b;jiffies++;}
#define trace_ipu_cstate(b) do{(void)(b);trace_calls++;}while(0)
static int iosf_mbi_modify(int a,int b,int c,u32 val,int mask){(void)a;(void)b;(void)c;(void)mask;writes++;requested=val;return modify_error;}
static int iosf_mbi_read(int a,int b,int c,u32*v){(void)a;(void)b;(void)c;reads++;*v=(reads>=ready_at?requested:(requested^3))<<24;return reads==read_fail_at?read_error:0;}
static int atomisp_power_off(void*p){(void)p;off_calls++;return off_error;}
static int atomisp_power_on(void*p){(void)p;on_calls++;return on_error;}
'''+extract(v4l,'atomisp_mrfld_power')+'\n'+extract(cmd,'atomisp_reset')+r'''
int main(void){
 for(int enable=0;enable<2;enable++)for(int only=0;only<2;only++)for(int f=0;f<4;f++){
  struct pci_dev pci={77};struct atomisp_device isp={.dev=&pci,.pm_only=only};jiffies=0;reads=writes=trace_calls=dvfs_calls=0;modify_error=f==1?-ENODEV:0;read_error=-EIO;read_fail_at=f==2?1:0;ready_at=f==3?1000:2;
  int ret=atomisp_mrfld_power(&isp,enable);int expected=f==0?0:f==1?-ENODEV:f==2?-EIO:-EBUSY;
  bool gate=ret==expected&&(f==0?pci.current_state==(enable?PCI_D0:PCI_D3cold)&&trace_calls==1:pci.current_state==77&&trace_calls==0)&&(f!=1||reads==0);
  printf("{\"suite\":\"power\",\"enable\":%d,\"pm_only\":%d,\"fault\":%d,\"returned\":%d,\"reads\":%d,\"state\":%d,\"passed\":%s}\n",enable,only,f,ret,reads,pci.current_state,gate?"true":"false");
 }
 int errors[]={0,-EIO,-ENODEV,-EAGAIN};
 for(int off=0;off<4;off++)for(int on=0;on<4;on++){
  struct atomisp_device isp={0};off_error=errors[off];on_error=errors[on];off_calls=on_calls=0;int ret=atomisp_reset(&isp);int expected=off_error?off_error:on_error;
  bool gate=ret==expected&&off_calls==1&&on_calls==(off_error?0:1)&&isp.isp_fatal_error==(expected!=0);
  printf("{\"suite\":\"reset\",\"off_error\":%d,\"on_error\":%d,\"returned\":%d,\"on_calls\":%d,\"fatal\":%s,\"passed\":%s}\n",off_error,on_error,ret,on_calls,isp.isp_fatal_error?"true":"false",gate?"true":"false");
 }return 0;
}
'''
dest=out/f'mipad2-r20-power-transport-{phase}.json';log=dest.with_suffix('.log');assert not dest.exists() and not log.exists();rows=[];outputs=[]
with tempfile.TemporaryDirectory(prefix='r20-power-') as d:
 for name,code in [('transport',transport),('power',power)]:
  p=Path(d)/(name+'.c');p.write_text(code);binary=Path(d)/name;q=subprocess.run(['cc','-std=gnu11','-O2','-Wall','-Wextra','-Werror',str(p),'-o',str(binary)],capture_output=True,text=True);assert q.returncode==0,q.stderr
  q=subprocess.run([str(binary)],capture_output=True,text=True);assert q.returncode==0,q.stderr;outputs.append(q.stdout);rows.extend(json.loads(x) for x in q.stdout.splitlines())
log.write_text('\n'.join(outputs));failed=[x for x in rows if not x['passed']]
record=dict(phase=phase,cases=len(rows),failed=len(failed),all_passed=not failed,source_sha256={p:hashlib.sha256((r/p).read_bytes()).hexdigest() for p in [iosf,cmd,v4l]},scope='Exact PCI mailbox helper/PCI errno translator, ISP power poll and reset functions compiled with explicit PCI/IOSF/clock/PM stubs; NOT physical hardware faults, SP idle/DMA or recovery ownership safety',results=rows)
dest.write_text(json.dumps(record,indent=2)+'\n');print('Power/transport cases',len(rows),'failed',len(failed));print(json.dumps(failed[:6]))
assert (not failed if phase=='green' else len(failed)>0 and any(x['suite']=='iosf' for x in failed) and any(x['suite']=='reset' for x in failed) and any(x['suite']=='power' for x in failed))
