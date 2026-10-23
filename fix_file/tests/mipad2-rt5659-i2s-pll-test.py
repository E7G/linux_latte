#!/usr/bin/env python3
"""Execute the production PLL selector and require direct serial-clock routes.

This checks source topology/predicate, not actual kernel DAPM or physical clocks.
"""
from pathlib import Path
import argparse,os,re,shlex,subprocess,tempfile
p=argparse.ArgumentParser();p.add_argument('--codec-source',type=Path);a=p.parse_args()
r=Path(__file__).resolve().parents[2]
s=(a.codec_source or r/'sound/soc/codecs/rt5659.c').read_text()
def require(ok,msg):
 if not ok:raise RuntimeError(msg)
for port in ['I2S1','I2S2','I2S3']:
 require(len(re.findall(r'\{ "'+port+r'", NULL, "PLL", is_sys_clk_from_pll \}',s))==1,
         'Missing unique direct conditional PLL dependency for '+port)
m=re.search(r'static int is_sys_clk_from_pll\([^;]*?\)\s*\{',s,re.S)
require(m is not None,'Missing production selector')
start=m.start();end=s.index('{',start)+1;depth=1
while depth:depth+=(s[end]=='{')-(s[end]=='}');end+=1
function=s[start:end]
header=(r/'sound/soc/codecs/rt5659.h').read_text()
constants=[]
for name in ['RT5659_GLB_CLK','RT5659_SCLK_SRC_MASK','RT5659_SCLK_SRC_PLL1']:
 m=re.search(r'^#define '+name+r'\s+([^\n]+)',header,re.M);require(m is not None,'Missing header constant '+name);constants.append('#define '+name+' '+m[1])
shim=r'''
#include <stdio.h>
#include <stdlib.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"CHECK failed: %s\n",#x); exit(89); } } while(0)
struct snd_soc_component { unsigned int value; };
struct snd_soc_dapm_context { struct snd_soc_component *component; };
struct snd_soc_dapm_widget { struct snd_soc_dapm_context *dapm; };
static struct snd_soc_component *snd_soc_dapm_to_component(struct snd_soc_dapm_context *d) { return d->component; }
static unsigned int snd_soc_component_read(struct snd_soc_component *c,unsigned int reg) { CHECK(reg==RT5659_GLB_CLK);return c->value; }
'''
main=r'''
int main(void) {
 struct snd_soc_component c={0};struct snd_soc_dapm_context d={.component=&c};
 struct snd_soc_dapm_widget w={.dapm=&d};
 for(unsigned int source=0;source<4;source++) {
  for(unsigned int other=0;other<32;other++) {
   c.value=(source<<14)|(other*509);
   CHECK(is_sys_clk_from_pll(&w,NULL)==(source==1));
  }
 }
 puts("PASS: 3 direct I2S/PLL dependencies; 128 actual-selector cases; filters not required by source routes");
 return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='mipad2-pll-test-') as tmp:
 d=Path(tmp);src=d/'test.c';binary=d/'test';src.write_text('\n'.join(constants)+shim+function+main)
 subprocess.run(shlex.split(os.environ.get('CC','clang'))+['-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-fsanitize=address,undefined','-g',str(src),'-o',str(binary)],check=True)
 subprocess.run([str(binary)],check=True)
