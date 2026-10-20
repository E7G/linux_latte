#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Compile exact driver functions with explicit PCI/MMIO/PM stubs, not hardware."""
from pathlib import Path
import hashlib, json, os, re, subprocess, sys, tempfile

r = Path(os.environ.get('MIPAD2_KERNEL_SOURCE', Path(__file__).resolve().parents[2]))
prototype = False
base = r  # Prototype mode disabled in the public current-source regression.
out = Path(os.environ.get('MIPAD2_TEST_OUTPUT', tempfile.mkdtemp(prefix='mipad2-pci-poweroff-report-')))
out.mkdir(parents=True, exist_ok=True)
paths = ['drivers/staging/media/atomisp/pci/atomisp_cmd.c', 'drivers/staging/media/atomisp/pci/atomisp_v4l2.c']

def extract(s, name):
    m = re.search(r'^[\w *]+\b' + name + r'\([^;]*?\)\n\{', s, re.M)
    assert m, name
    i = s.index('{', m.start()) + 1
    depth = 1
    while depth:
        depth += (s[i] == '{') - (s[i] == '}')
        i += 1
    return s[m.start():i]

pci = (r/'include/linux/pci.h').read_text()
translator = extract(pci, 'pcibios_err_to_errno')
defs = '\n'.join(re.findall(r'^#define PCIBIOS_.*$', pci, re.M))
header = r'''
#include <stdio.h>
#include <stdbool.h>
#include <stdint.h>
#include <errno.h>
#include <string.h>
typedef uint32_t u32;
typedef uint16_t u16;
struct pci_dev { int ignored; };
struct atomisp_device;
struct device { struct atomisp_device *owner; struct pci_dev pci; };
struct atomisp_device { struct device *dev; bool pm_only; int lock,pm_qos; };
#define dev_err(...) ((void)0)
#define dev_warn(...) ((void)0)
#define BIT(b) (1U << (b))
#define PCI_INTERRUPT_CTRL 1
#define PCI_MSI_CAPID 2
#define PCI_COMMAND 3
#define MRFLD_PCI_CSI_CONTROL 4
#define MRFLD_INTR_CLEAR_REG 5
#define MRFLD_INTR_STATUS_REG 6
#define MRFLD_INTR_ENABLE_REG 7
#define INTR_IIR 3
#define INTR_IER 4
#define MSI_ENABLE_BIT 5
#define PCI_COMMAND_MASTER 4
#define MRFLD_ALL_CSI_PORTS_OFF_MASK 0x700
#define ATOMISP_DFS_MODE_LOW 1
#define PM_QOS_DEFAULT_VALUE (-1)
static int fail_index,fail_code,pci_calls,irq_reads,mode,save_result,power_result;
static int mmio_calls,power_calls,save_calls,qos_calls,dfs_calls,css_calls;
static int lock_depth,locks,unlocks,lock_error,failed,post_failure_ops,qos_after_power;
static char trace[2048];static unsigned length;
static void event(char c,int a,unsigned b){
 if(failed&&c!='U')post_failure_ops++;
 length+=(unsigned)snprintf(trace+length,sizeof(trace)-length,"%c:%d:%u;",c,a,b);
}
static struct atomisp_device *dev_get_drvdata(struct device*d){return d->owner;}
static struct pci_dev *to_pci_dev(struct device*d){return &d->pci;}
#define spin_lock_irqsave(l,f) do{(void)(l);(f)=0;event('L',0,0);locks++;if(lock_depth++)lock_error++;}while(0)
#define spin_unlock_irqrestore(l,f) do{(void)(l);(void)(f);event('U',0,0);unlocks++;if(--lock_depth)lock_error++;}while(0)
static int read_config(int reg,void *ptr,int width){
 pci_calls++;event('R',reg,(unsigned)width);
 int ret=pci_calls==fail_index?fail_code:0;
 u32 value=0;
 if(reg==PCI_INTERRUPT_CTRL){irq_reads++;value=(mode&&!(mode==1&&irq_reads>=4))?BIT(INTR_IIR):0;}
 else if(reg==PCI_MSI_CAPID)value=0xabcdef;
 else if(reg==PCI_COMMAND)value=0x15;
 else if(reg==MRFLD_PCI_CSI_CONTROL)value=0xabcdef12;
 /* Deterministic poison on failed reads: caller must never consume it. */
 if(ret)value=0xdeadbeef;
 if(width==2)*(u16*)ptr=(u16)value;else *(u32*)ptr=value;
 if(ret)failed=1;
 return ret;
}
static int write_config(int reg,unsigned value,int width){
 pci_calls++;event('W',reg,value^(unsigned)(width<<24));
 int ret=pci_calls==fail_index?fail_code:0;if(ret)failed=1;return ret;
}
static int pci_read_config_dword(struct pci_dev*p,int r,u32*v){(void)p;return read_config(r,v,4);}
static int pci_read_config_word(struct pci_dev*p,int r,u16*v){(void)p;return read_config(r,v,2);}
static int pci_write_config_dword(struct pci_dev*p,int r,u32 v){(void)p;return write_config(r,v,4);}
static int pci_write_config_word(struct pci_dev*p,int r,u16 v){(void)p;return write_config(r,v,2);}
static void atomisp_css2_hw_store_32(int r,u32 v){event('M',r,v);mmio_calls++;}
static void atomisp_load_uint32(int r,u32*v){event('m',r,0);mmio_calls++;*v=mode==2?1:0;}
static int atomisp_freq_scaling(struct atomisp_device*i,int m,bool f){(void)i;event('D',m,f);dfs_calls++;return 0;}
static void atomisp_css_uninit(struct atomisp_device*i){(void)i;event('C',0,0);css_calls++;}
static int pci_save_state(struct pci_dev*p){(void)p;event('S',0,0);save_calls++;if(save_result)failed=1;return save_result;}
static int atomisp_mrfld_power(struct atomisp_device*i,bool on){(void)i;event('P',on,0);power_calls++;if(power_result)failed=1;return power_result;}
static void cpu_latency_qos_update_request(int*q,int v){event('Q',v,0);qos_calls++;qos_after_power=power_calls==1&&!power_result;*q=v;}
'''
main = r'''
static void reset(void){
 pci_calls=irq_reads=mmio_calls=power_calls=save_calls=qos_calls=dfs_calls=css_calls=0;
 lock_depth=locks=unlocks=lock_error=failed=post_failure_ops=qos_after_power=0;
 fail_index=fail_code=save_result=power_result=0;trace[0]=0;length=0;
}
static int invoke(struct device*d,struct atomisp_device*i,int caller){
 if(caller==0)return msi_test(i);
 if(caller==1)return atomisp_mrfld_pre_power_down(i);
 return atomisp_power_off(d);
}
int main(void){
 struct device dev={0};struct atomisp_device isp={.dev=&dev};dev.owner=&isp;
 int codes[]={PCIBIOS_FUNC_NOT_SUPPORTED,PCIBIOS_BAD_VENDOR_ID,PCIBIOS_DEVICE_NOT_FOUND,PCIBIOS_BAD_REGISTER_NUMBER,PCIBIOS_SET_FAILED,PCIBIOS_BUFFER_TOO_SMALL,0x90,-EIO,-ENOMEM};
 int callers[]={0,1,1,2,2,2},modes[]={0,0,1,0,1,0},totals[]={5,10,13,12,15,3};
 for(int kind=0;kind<6;kind++)for(int index=0;index<=totals[kind];index++)for(unsigned e=0;e<(index?sizeof(codes)/sizeof(codes[0]):1);e++){
  reset();mode=modes[kind];isp.pm_only=kind==5;isp.pm_qos=42;fail_index=index;fail_code=codes[e];
  int ret=invoke(&dev,&isp,callers[kind]);
  bool balance=!lock_error&&!lock_depth&&locks==unlocks&&locks==(callers[kind]!=0&&kind!=5);
  bool ok=balance&&(index?(ret==pcibios_err_to_errno(fail_code)&&pci_calls==index&&!post_failure_ops&&isp.pm_qos==42):
    (ret==0&&pci_calls==totals[kind]&&qos_calls==(callers[kind]==2)&&save_calls==(callers[kind]==2)&&power_calls==(callers[kind]==2)&&css_calls==(callers[kind]==2&&kind!=5)&&dfs_calls==(callers[kind]!=0&&kind!=5)&&mmio_calls==(mode==1?3:0)&&(callers[kind]!=2||(qos_after_power&&isp.pm_qos==PM_QOS_DEFAULT_VALUE))));
  printf("{\"kind\":%d,\"index\":%d,\"status\":%d,\"ret\":%d,\"pci_calls\":%d,\"post_failure_ops\":%d,\"locks\":%d,\"unlocks\":%d,\"trace\":\"%s\",\"passed\":%s}\n",kind,index,index?fail_code:0,ret,pci_calls,post_failure_ops,locks,unlocks,trace,ok?"true":"false");
 }
 for(int only=0;only<2;only++)for(int irqmode=0;irqmode<(only?1:2);irqmode++)for(int stage=0;stage<2;stage++)for(int e=0;e<2;e++){
  reset();mode=irqmode;isp.pm_only=only;isp.pm_qos=42;
  int expected=stage?(e?-EBUSY:-ENODEV):(e?-ENOMEM:-EIO);
  if(stage)power_result=expected;else save_result=expected;
  int ret=atomisp_power_off(&dev);
  bool ok=ret==expected&&!post_failure_ops&&!qos_calls&&isp.pm_qos==42&&save_calls==1&&power_calls==stage&&!lock_depth&&!lock_error&&locks==unlocks;
  printf("{\"special\":\"late-error\",\"only\":%d,\"mode\":%d,\"stage\":%d,\"ret\":%d,\"trace\":\"%s\",\"passed\":%s}\n",only,irqmode,stage,ret,trace,ok?"true":"false");
 }
 for(int caller=1;caller<=2;caller++)for(int m=2;m<=3;m++){
  reset();mode=m;isp.pm_only=false;isp.pm_qos=42;
  int ret=invoke(&dev,&isp,caller);
  bool ok=ret==-EAGAIN&&pci_calls==(m==2?3:6)&&mmio_calls==2&&!dfs_calls&&!save_calls&&!power_calls&&!qos_calls&&isp.pm_qos==42&&!lock_depth&&!lock_error&&locks==1&&unlocks==1;
  printf("{\"special\":\"pending-irq\",\"caller\":%d,\"mode\":%d,\"ret\":%d,\"trace\":\"%s\",\"passed\":%s}\n",caller,m,ret,trace,ok?"true":"false");
 }
 return 0;
}
'''
reports = {}
with tempfile.TemporaryDirectory(prefix='mipad2-poweroff-compile-') as d:
    for label in (['original', 'candidate'] if prototype else ['current']):
        root = base/label if prototype else r
        sources = {p: (root/p).read_text() for p in paths}
        msi = extract(sources[paths[0]], 'atomisp_msi_irq_uninit')
        wrapper = '\nstatic int msi_test(struct atomisp_device*i){' + ('atomisp_msi_irq_uninit(i);return 0;' if msi.startswith('void ') else 'return atomisp_msi_irq_uninit(i);') + '}\n'
        funcs = msi + wrapper + '\n'.join(extract(sources[paths[1]], n) for n in ['atomisp_mrfld_pre_power_down', 'atomisp_power_off'])
        p = Path(d)/(label+'.c')
        p.write_text(header+'\n'+defs+'\n'+translator+'\n'+funcs+'\n'+main)
        exe = Path(d)/label
        q = subprocess.run(['cc', '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', str(p), '-o', str(exe)], text=True, capture_output=True)
        assert q.returncode == 0, q.stderr
        q = subprocess.run([str(exe)], text=True, capture_output=True)
        assert q.returncode == 0 and not q.stderr, q.stderr
        rows = [json.loads(l) for l in q.stdout.splitlines()]
        failed_rows = [x for x in rows if not x['passed']]
        report = dict(label=label, total=len(rows), failed=len(failed_rows), source_sha256={p: hashlib.sha256(v.encode()).hexdigest() for p,v in sources.items()}, physical_fault_injected=False,
                      scope='Exact driver functions and kernel PCI errno translator; PCI/IRQ/MMIO/QoS/CSS/PUNIT stubs. Not DMA fencing, PCI core internals or hardware validation.', cases=rows)
        dest = out/('mipad2-r23-pci-poweroff-'+label+'-host.json')
        assert not dest.exists()
        dest.write_text(json.dumps(report, indent=2)+'\n')
        reports[label] = report
        print(label, 'cases', len(rows), 'failed', len(failed_rows), flush=True)
        assert len(rows) == 544, len(rows)
        assert len(failed_rows) > 500 if label == 'original' else not failed_rows
    if prototype:
        for kind in range(6):
            a = next(x for x in reports['original']['cases'] if x.get('kind') == kind and x.get('index') == 0)
            b = next(x for x in reports['candidate']['cases'] if x.get('kind') == kind and x.get('index') == 0)
            trim = lambda t: ';'.join(x for x in t.split(';') if not x.startswith('Q:'))
            assert trim(a['trace']) == trim(b['trace']), (kind, a, b)
        print('Successful PCI/MMIO/CSS/DFS order matches; QoS intentionally follows acknowledged power-off.')
print('Completed. No hardware access or canonical source mutation.')
