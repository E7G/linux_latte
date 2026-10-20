#!/usr/bin/env python3
"""Compile exact DWC3 suspend functions with ordered PM/error-injection stubs.

This is a host control-flow contract, not USB hardware or S0I3 validation.
"""
from pathlib import Path
import argparse, hashlib, json, os, re, subprocess, tempfile

parser=argparse.ArgumentParser()
parser.add_argument('--baseline-commit')
args=parser.parse_args()
root=Path(os.environ.get('MIPAD2_KERNEL_SOURCE',Path(__file__).resolve().parents[2]))
out=Path(os.environ.get('MIPAD2_TEST_OUTPUT',tempfile.gettempdir()))
out.mkdir(parents=True,exist_ok=True)
result=out/'mipad2-dwc3-suspend-error-host.json'
if result.exists():raise RuntimeError('Exclusive output already exists')

def extract(s,name):
    m=re.search(r'^(?:static )?int\s+'+name+r'\s*\(',s,re.M)
    if not m:raise RuntimeError('Missing exact function '+name)
    pos=s.index('{',m.end());depth=1;end=pos+1
    while depth:
        if s[end]=='{':depth+=1
        elif s[end]=='}':depth-=1
        end+=1
    return s[m.start():end]

PRE=r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
typedef uint32_t u32;
typedef int pm_message_t;
#define PMSG_IS_AUTO(msg) (msg)
#define DWC3_GCTL_PRTCAP_DEVICE 1
#define DWC3_GCTL_PRTCAP_HOST 2
#define DWC3_GCTL_PRTCAP_OTG 3
#define DWC3_OTG_ROLE_DEVICE 1
#define DWC3_OTG_ROLE_HOST 2
#define DWC3_GUSB2PHYCFG(n) (10+(n))
#define DWC3_GUSB3PIPECTL(n) (20+(n))
#define DWC3_GUSB2PHYCFG_SUSPHY 1u
#define DWC3_GUSB3PIPECTL_SUSPHY 1u
#define DWC3_GUSB2PHYCFG_ENBLSLPM 2u
struct device { bool suspended,wakeup; };
struct dwc3 { struct device *dev; int current_dr_role,current_otg_role;
 int irq_gadget,lock,num_usb2_ports,num_usb3_ports; bool softconnect;
 bool gadget_driver,susphy_state,dis_u2_susphy_quirk,dis_enblslpm_quirk;
 void *regs; int usb2_generic_phy[2],usb3_generic_phy[2]; };
static int injected,phybits;static char trace[8192];static size_t used;
static void ev(const char *s){size_t n=strlen(s);if(used+n+1>=sizeof(trace))abort();memcpy(trace+used,s,n);used+=n;trace[used]=0;}
static bool pm_runtime_suspended(struct device *d){return d->suspended;}
static bool device_may_wakeup(struct device *d){return d->wakeup;}
static u32 dwc3_readl(void *p,int n){(void)p;return n<20?(u32)(phybits&1):(u32)((phybits>>1)&1);}
static void dwc3_writel(void *p,int n,u32 v){(void)p;(void)n;(void)v;ev("write;");}
static void dwc3_enable_susphy(struct dwc3 *d,bool b){(void)d;if(!b)abort();ev("susphy;");}
static int dwc3_gadget_soft_disconnect(struct dwc3 *d){(void)d;ev("halt;");return injected;}
static void dwc3_gadget_soft_connect(struct dwc3 *d){(void)d;ev("connect;");}
#define spin_lock_irqsave(lock,flags) do {(void)(lock);(flags)=0;ev("lock;");} while(0)
#define spin_unlock_irqrestore(lock,flags) do {(void)(lock);(void)(flags);ev("unlock;");} while(0)
static void dwc3_disconnect_gadget(struct dwc3 *d){(void)d;ev("disconnect;");}
static void synchronize_irq(int irq){(void)irq;ev("sync;");}
static void dwc3_core_exit(struct dwc3 *d){(void)d;ev("core-exit;");}
static void dwc3_otg_exit(struct dwc3 *d){(void)d;ev("otg-exit;");}
static void phy_pm_runtime_put_sync(int p){if(p<10)ev("phy2-put;");else ev("phy3-put;");}
static void usleep_range(int a,int b){if(a!=5000||b!=6000)abort();ev("delay;");}
'''

POST=r'''
static char expected[8192];
static void want(const char *s){if(strlen(expected)+strlen(s)+1>=sizeof(expected))abort();strcat(expected,s);}
/* Independent ordered oracle, not the source function rewritten with stubs. */
static int golden(struct dwc3 *d,int auto_pm){
 int abort_code=0;
 expected[0]=0;
 if(!d->dev->suspended&&!auto_pm&&!phybits)want("susphy;");
 bool gadget=(d->current_dr_role==1&&!d->dev->suspended)||
             (d->current_dr_role==3&&!auto_pm&&d->current_otg_role==1);
 if(gadget){
  want("halt;");
  if(injected&&d->softconnect){want("connect;");abort_code=-EAGAIN;}
  else{want("lock;");if(d->gadget_driver)want("disconnect;");want("unlock;sync;");}
 }
 if(abort_code)return abort_code;
 if(d->current_dr_role==1){if(!d->dev->suspended)want("core-exit;");}
 if(d->current_dr_role==3&&!auto_pm)want("otg-exit;core-exit;");
 if(d->current_dr_role==2){
  if(!auto_pm&&!d->dev->wakeup)want("core-exit;");
  else{
   if(d->dis_u2_susphy_quirk||d->dis_enblslpm_quirk){for(int i=0;i<d->num_usb2_ports;i++)want("write;");want("delay;");}
   for(int i=0;i<d->num_usb2_ports;i++)want("phy2-put;");
   for(int i=0;i<d->num_usb3_ports;i++)want("phy3-put;");
  }
 }
 return 0;
}
int main(void){
 unsigned cases=0,failed=0,error_abort_cases=0;
 int errs[]={0,-ETIMEDOUT,-EBUSY,-EIO};
 for(int role=1;role<=4;role++)for(int otg=1;otg<=2;otg++)
 for(int suspended=0;suspended<2;suspended++)for(int auto_pm=0;auto_pm<2;auto_pm++)
 for(int wake=0;wake<2;wake++)for(int soft=0;soft<2;soft++)
 for(int driver=0;driver<2;driver++)for(int bits=0;bits<4;bits++)
 for(int quirk=0;quirk<4;quirk++)for(int ports=0;ports<3;ports++)for(int e=0;e<4;e++){
  struct device dev={suspended,wake};
  struct dwc3 d={.dev=&dev,.current_dr_role=role,.current_otg_role=otg,
   .softconnect=soft,.gadget_driver=driver,.num_usb2_ports=ports,.num_usb3_ports=ports,
   .dis_u2_susphy_quirk=quirk&1,.dis_enblslpm_quirk=quirk&2,
   .usb2_generic_phy={0,1},.usb3_generic_phy={10,11}};
  injected=errs[e];phybits=bits;used=0;trace[0]=0;
  int expected_code=golden(&d,auto_pm);int actual=dwc3_suspend_common(&d,auto_pm);
  cases++;if(expected_code==-EAGAIN)error_abort_cases++;
  if(actual!=expected_code||strcmp(trace,expected)){
   failed++;if(failed<=2)fprintf(stderr,"case=%u role=%d soft=%d err=%d got=%d expected=%d trace=%s expected_trace=%s\n",cases,role,soft,injected,actual,expected_code,trace,expected);
  }
 }
 printf("{\"cases\":%u,\"failed\":%u,\"error_abort_cases\":%u}\n",cases,failed,error_abort_cases);
 return 0;
}
'''

def exercise(directory,label,commit=None):
    functions=[];hashes={}
    for f,name in [('drivers/usb/dwc3/gadget.c','dwc3_gadget_suspend'),('drivers/usb/dwc3/core.c','dwc3_suspend_common')]:
        data=subprocess.check_output(['git','-C',str(root),'show',commit+':'+f]) if commit else (root/f).read_bytes()
        text=data.decode();func=extract(text,name);functions.append(func)
        hashes[f]=dict(source_sha256=hashlib.sha256(data).hexdigest(),function_sha256=hashlib.sha256(func.encode()).hexdigest())
    source=directory/(label+'.c');binary=directory/label
    source.write_text(PRE+'\n'+'\n'.join(functions)+'\n'+POST)
    build=['clang','-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(source),'-o',str(binary)]
    q=subprocess.run(build,capture_output=True,text=True)
    if q.returncode:raise RuntimeError(q.stderr)
    q=subprocess.run([str(binary)],capture_output=True,text=True,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=1:halt_on_error=1',UBSAN_OPTIONS='halt_on_error=1'))
    if q.returncode:raise RuntimeError(q.stderr)
    data=json.loads(q.stdout);data.update(hashes=hashes,sanitizers='ASan/UBSan/leak detection; exit0',binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest())
    (out/(label+'.stderr')).write_text(q.stderr)
    return data

with tempfile.TemporaryDirectory(prefix='mipad2-dwc3-suspend-') as td:
    directory=Path(td);report=dict(scope='Exact two DWC3 C functions; synthetic ordered stubs, NOT USB hardware/S0I3 proof',current=exercise(directory,'current'))
    if args.baseline_commit:report['baseline']=exercise(directory,'baseline',args.baseline_commit)
    result.write_text(json.dumps(report,indent=2)+'\n')
    if report['current']['failed']!=0:raise RuntimeError('Current DWC3 suspend contract failed: '+str(report['current']['failed']))
    if args.baseline_commit and report['baseline']['failed']==0:raise RuntimeError('Baseline did not expose the missing upstream error handling')
    print(json.dumps(report,indent=2))
