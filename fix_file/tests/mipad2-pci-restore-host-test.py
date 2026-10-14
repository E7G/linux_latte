from pathlib import Path
import re, subprocess, tempfile, json, hashlib
import os
r = Path(os.environ.get('MIPAD2_KERNEL_SOURCE', Path(__file__).resolve().parents[2]))
rel = 'drivers/staging/media/atomisp/pci/atomisp_v4l2.c'
out = Path(tempfile.mkdtemp(prefix='mipad2-pci-restore-report-'))

def extract(s, name):
    m = re.search(r'^[\w\s*]+\b' + name + r'\([^;]*?\)\n\{', s, re.M)
    assert m, name
    i = s.index('{', m.start()) + 1; depth = 1
    while depth:
        depth += (s[i] == '{') - (s[i] == '}'); i += 1
    return s[m.start():i]

pci = (r / 'include/linux/pci.h').read_text()
translator = extract(pci, 'pcibios_err_to_errno')
defs = '\n'.join(re.findall(r'^#define PCIBIOS_.*$', pci, re.M))
source = (r / rel).read_text()
functions = '\n'.join(extract(source, n) for n in ['atomisp_restore_iunit_reg', 'atomisp_power_on'])
fields = sorted(set(re.findall(r'isp->saved_regs\.(\w+)', functions)))
constants = sorted(set(re.findall(r'\b(?:PCI_[A-Z_0-9]+|MRFLD_[A-Z_0-9]+|ATOMISP_DFS_MODE_LOW)\b', functions)))
header = r'''
#include <stdio.h>
#include <stdbool.h>
#include <stdint.h>
#include <errno.h>
#include <string.h>
typedef uint32_t u32;
struct pci_dev { int ignored; };
struct atomisp_device;
struct device { struct atomisp_device *owner; struct pci_dev pci; };
struct atomisp_device { struct device *dev; bool pm_only; int pm_qos,max_isr_latency; struct { FIELDS } saved_regs; };
static int fail_index,fail_code,pci_calls,mmio_calls,power_calls,restore_calls,qos_calls,dfs_calls,css_calls,power_result,css_result;
static unsigned long trace_value;
#define dev_dbg(...) ((void)0)
#define dev_err(...) ((void)0)
static struct atomisp_device *dev_get_drvdata(struct device *d){return d->owner;}
static struct pci_dev *to_pci_dev(struct device *d){return &d->pci;}
static int write_config(struct pci_dev *p,int reg,unsigned long val,int width){
 (void)p;pci_calls++;trace_value=trace_value*31+reg+val+width;
 return pci_calls==fail_index?fail_code:0;
}
static int pci_write_config_byte(struct pci_dev *p,int r,unsigned long v){return write_config(p,r,v,1);}
static int pci_write_config_word(struct pci_dev *p,int r,unsigned long v){return write_config(p,r,v,2);}
static int pci_write_config_dword(struct pci_dev *p,int r,unsigned long v){return write_config(p,r,v,4);}
static void atomisp_css2_hw_store_32(int reg,int val){trace_value=trace_value*31+reg+val;mmio_calls++;}
static int atomisp_mrfld_power(struct atomisp_device *i,bool on){(void)i;(void)on;power_calls++;return power_result;}
static void pci_restore_state(struct pci_dev *p){(void)p;restore_calls++;}
static void cpu_latency_qos_update_request(int *q,int val){(void)q;(void)val;qos_calls++;}
static int atomisp_freq_scaling(struct atomisp_device *i,int m,bool f){(void)i;(void)m;(void)f;dfs_calls++;return 0;}
static int atomisp_css_init(struct atomisp_device *i){(void)i;css_calls++;return css_result;}
'''.replace('FIELDS', ';'.join('unsigned long ' + f for f in fields) + ';')
header += '\n' + '\n'.join('#define ' + name + ' ' + str(i+1) for i, name in enumerate(constants)) + '\n' + defs + '\n' + translator + '\n'
main = r'''
static void reset(void){pci_calls=mmio_calls=power_calls=restore_calls=qos_calls=dfs_calls=css_calls=0;trace_value=0;power_result=css_result=0;}
int main(void){
 struct device dev={0};struct atomisp_device isp={.dev=&dev};dev.owner=&isp;
 int codes[]={PCIBIOS_FUNC_NOT_SUPPORTED,PCIBIOS_BAD_VENDOR_ID,PCIBIOS_DEVICE_NOT_FOUND,PCIBIOS_BAD_REGISTER_NUMBER,PCIBIOS_SET_FAILED,PCIBIOS_BUFFER_TOO_SMALL,0x90,-EIO,-ENOMEM};
 for(int caller=0;caller<2;caller++)for(int index=0;index<=16;index++)for(unsigned c=0;c<(index?sizeof(codes)/sizeof(codes[0]):1);c++){
  reset();memset(&isp.saved_regs,0x01,sizeof(isp.saved_regs));isp.pm_only=false;fail_index=index;fail_code=codes[c];
  int ret=caller?atomisp_power_on(&dev):atomisp_restore_iunit_reg(&isp);
  bool ok=index?(ret==pcibios_err_to_errno(fail_code)&&pci_calls==index&&mmio_calls==0&&css_calls==0&&dfs_calls==0):
    (ret==0&&pci_calls==16&&mmio_calls==1&&css_calls==caller&&dfs_calls==caller);
  printf("{\"caller\":%d,\"index\":%d,\"pci_status\":%d,\"ret\":%d,\"pci_calls\":%d,\"mmio\":%d,\"css_init\":%d,\"trace\":%lu,\"passed\":%s}\n",caller,index,index?fail_code:0,ret,pci_calls,mmio_calls,css_calls,trace_value,ok?"true":"false");
 }
 for(int test=0;test<4;test++){
  reset();fail_index=0;isp.pm_only=test==0;memset(&isp.saved_regs,test==1?0:1,sizeof(isp.saved_regs));
  if(test==2)power_result=-EBUSY;
  if(test==3)css_result=-ENOMEM;
  int ret=atomisp_power_on(&dev);bool ok;
  if(test==0)ok=ret==0&&!pci_calls&&!mmio_calls&&!css_calls&&!dfs_calls&&restore_calls==1&&qos_calls==1;
  else if(test==1)ok=ret==0&&!pci_calls&&!mmio_calls&&css_calls==1&&dfs_calls==1;
  else if(test==2)ok=ret==-EBUSY&&!pci_calls&&!mmio_calls&&!css_calls&&!dfs_calls&&!restore_calls&&!qos_calls;
  else ok=ret==-ENOMEM&&pci_calls==16&&mmio_calls==1&&css_calls==1&&dfs_calls==1;
  printf("{\"special_case\":%d,\"ret\":%d,\"passed\":%s}\n",test,ret,ok?"true":"false");
 }
 return 0;
}
'''
reports = {}
with tempfile.TemporaryDirectory(prefix='r21-pci-restore-test-') as d:
    for label in ['current']:
        data = (r / rel).read_text()
        functions = '\n'.join(extract(data, n) for n in ['atomisp_restore_iunit_reg', 'atomisp_power_on'])
        p = Path(d) / (label + '.c'); p.write_text(header + functions + main)
        exe = Path(d) / label
        q = subprocess.run(['cc', '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', str(p), '-o', str(exe)], capture_output=True, text=True)
        assert q.returncode == 0, q.stderr
        q = subprocess.run([str(exe)], capture_output=True, text=True); assert q.returncode == 0, q.stderr
        cases = [json.loads(l) for l in q.stdout.splitlines()]
        failed = [x for x in cases if not x['passed']]
        reports[label] = dict(source_sha256=hashlib.sha256(data.encode()).hexdigest(), cases=cases, total=len(cases), failed=len(failed))
        print(label, len(cases), 'cases,', len(failed), 'failed')
        assert len(cases) == 294
        assert len(failed) == 0
        target = out / ('mipad2-r21-pci-restore-' + label + '-host.json'); assert not target.exists()
        target.write_text(json.dumps(dict(**reports[label], physical_fault_injected=False, production_source_changed=False,
            scope='Exact source PCI restore + power_on, actual PCI errno translator, explicit PCI/PM/MMIO/CSS stubs. No hardware/DMA safety proof.'), indent=2) + '\n')
print('First-error propagation, positive PCI status translation, no later register writes/MMIO/CSS init on failure; normal traces identical. Fixture does not change source or touch hardware.')
