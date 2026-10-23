#!/usr/bin/env python3
"""Exercise production supply traversal/PLL predicate with a minimal graph.

This is a host fixture, not a full DAPM scheduler or hardware qualification.
"""
from pathlib import Path
import argparse, os, re, shlex, subprocess, tempfile

p=argparse.ArgumentParser()
p.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
p.add_argument('--machine-source', type=Path)
a=p.parse_args();root=a.root
machine=(a.machine_source or root/'sound/soc/intel/boards/cht_bsw_rt5659.c').read_text()
codec=(root/'sound/soc/codecs/rt5659.c').read_text()
core=(root/'sound/soc/soc-dapm.c').read_text()
header=(root/'sound/soc/codecs/rt5659.h').read_text()
def require(ok,msg):
    if not ok:raise RuntimeError(msg)
def function(text,name):
    m=re.search(r'static int '+name+r'\([^;]*?\)\s*\{',text,re.S)
    require(m is not None,'Function missing: '+name)
    end=text.index('{',m.start())+1;depth=1
    while depth:depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[m.start():end]
require(len(re.findall(r'\{\s*"Platform Clock",\s*NULL,\s*"PLL"\s*\}',machine))==1,
        'Missing unique unconditional board PLL supply dependency')
for endpoint in ['Ext Spk','Headphone','Headset Mic','Int Mic']:
    require(re.search(r'\{\s*"'+endpoint+r'",\s*NULL,\s*"Platform Clock"\s*\}',machine),
            'Missing board clock consumer: '+endpoint)
require('SND_SOC_DAPM_PRE_PMU |\n\t\t\tSND_SOC_DAPM_POST_PMD' in machine,'Unexpected clock event phases')
constants=[]
for name in ['RT5659_GLB_CLK','RT5659_SCLK_SRC_MASK','RT5659_SCLK_SRC_PLL1']:
    m=re.search(r'^#define '+name+r'\s+([^\n]+)',header,re.M)
    require(m is not None,'Missing '+name);constants.append('#define '+name+' '+m[1])
shim=r'''
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#define CHECK(x) do {if (!(x)) {fprintf(stderr,"CHECK failed: %s\n",#x);exit(89);}} while(0)
struct snd_soc_component {unsigned int value;};
struct snd_soc_dapm_context {struct snd_soc_component *component;};
struct snd_soc_dapm_widget;
struct snd_soc_dapm_path {
 struct snd_soc_dapm_widget *source,*sink;
 int (*connected)(struct snd_soc_dapm_widget *,struct snd_soc_dapm_widget *);
 struct snd_soc_dapm_path *next;
};
struct snd_soc_dapm_widget {
 struct snd_soc_dapm_context *dapm;
 bool power_checked,force;
 int new_power,endpoint;
 int (*power_check)(struct snd_soc_dapm_widget *);
 struct snd_soc_dapm_path *paths;
};
#define DAPM_UPDATE_STAT(w,s) do {} while(0)
#define snd_soc_dapm_widget_for_each_sink_path(w,p) for ((p)=(w)->paths;(p);(p)=(p)->next)
static struct snd_soc_component *snd_soc_dapm_to_component(struct snd_soc_dapm_context *d) {return d->component;}
static unsigned int snd_soc_component_read(struct snd_soc_component *c,unsigned int reg) {CHECK(reg==RT5659_GLB_CLK);return c->value;}
static int endpoint_power(struct snd_soc_dapm_widget *w) {return w->endpoint;}
'''
main=r'''
int main(void) {
 struct snd_soc_component c={0};struct snd_soc_dapm_context d={.component=&c};
 struct snd_soc_dapm_widget platform={.dapm=&d,.power_check=endpoint_power};
 struct snd_soc_dapm_widget i2s={.dapm=&d,.power_check=endpoint_power};
 struct snd_soc_dapm_widget pll={.dapm=&d,.power_check=dapm_supply_check_power};
 struct snd_soc_dapm_path conditional={.source=&pll,.sink=&i2s,.connected=is_sys_clk_from_pll};
 struct snd_soc_dapm_path board={.source=&pll,.sink=&platform,.next=&conditional};
 for (unsigned int source=0;source<4;source++) {
  for(int active=0;active<2;active++) {
   c.value=source<<14;platform.endpoint=i2s.endpoint=active;
   pll.power_checked=platform.power_checked=i2s.power_checked=false;
   pll.paths=&conditional;
   CHECK(dapm_widget_power_check(&pll)==(active && source==1));
   pll.power_checked=platform.power_checked=i2s.power_checked=false;
   pll.paths=&board;
   CHECK(dapm_widget_power_check(&pll)==active);
  }
 }
 /* Reproduce the resume ordering: power walk before PRE_PMU changes SYSCLK. */
 c.value=2<<14;platform.endpoint=i2s.endpoint=1;
 pll.power_checked=platform.power_checked=i2s.power_checked=false;
 pll.paths=&conditional;CHECK(dapm_widget_power_check(&pll)==0);
 c.value=1<<14;CHECK(dapm_widget_power_check(&pll)==0); /* already checked */
 c.value=2<<14;pll.power_checked=platform.power_checked=i2s.power_checked=false;
 pll.paths=&board;CHECK(dapm_widget_power_check(&pll)==1);
 c.value=1<<14;CHECK(dapm_widget_power_check(&pll)==1);
 /* Suspend/endpoint shutdown must not force the supply to stay on. */
 for(int n=0;n<100;n++) {
  platform.endpoint=i2s.endpoint=0;c.value=2<<14;
  pll.power_checked=platform.power_checked=i2s.power_checked=false;
  CHECK(dapm_widget_power_check(&pll)==0);
  platform.endpoint=i2s.endpoint=1;
  pll.power_checked=platform.power_checked=i2s.power_checked=false;
  CHECK(dapm_widget_power_check(&pll)==1);
 }
 puts("PASS: actual supply traversal and PLL predicate; RC-before-PRE_PMU regression; 100 off/on walks; 4 endpoint routes");
 return 0;
}
'''
source='\n'.join(constants)+shim+function(codec,'is_sys_clk_from_pll')+function(core,'dapm_widget_power_check')+function(core,'dapm_supply_check_power')+main
with tempfile.TemporaryDirectory(prefix='mipad2-board-pll-pm-') as temp:
    d=Path(temp);src=d/'test.c';binary=d/'test';src.write_text(source)
    subprocess.run(shlex.split(os.environ.get('CC','clang'))+['-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-fsanitize=address,undefined','-g',str(src),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
