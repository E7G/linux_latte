#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Execute extracted kernel endpoint walk/C2C direction/parameter code in a graph fixture.

This is not a substitute for a full kernel boot or acoustic/power measurement.
"""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,tempfile

def require(ok,msg):
 if not ok:raise RuntimeError(msg)
def function(text,name):
 m=re.search(r'^(?:static\s+)?(?:__always_inline\s+)?(?:int|void)\s+'+re.escape(name)+r'\s*\(',text,re.M)
 require(m is not None,'Missing function '+name)
 begin=text.index('{',m.start());depth=1;i=begin+1
 while depth:
  require(i<len(text),'Unbalanced function '+name)
  depth+=(text[i]=='{')-(text[i]=='}');i+=1
 return text[m.start():i]

ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2]);ap.add_argument('--machine-source',type=Path);a=ap.parse_args()
root=a.root;machine=(a.machine_source or root/'sound/soc/intel/boards/cht_bsw_rt5659.c').read_text()
dapm=(root/'sound/soc/soc-dapm.c').read_text();core=(root/'sound/soc/soc-core.c').read_text();codec=(root/'sound/soc/codecs/rt5659.c').read_text()
require('c2c_params = nxp_tfa989x_params' in machine,'Missing fixed amp params')
for field,value in [('formats','SNDRV_PCM_FMTBIT_S16_LE'),('rate_min','48000'),('rate_max','48000'),('channels_min','2'),('channels_max','2')]:
 block=machine[machine.index('static const struct snd_soc_pcm_stream nxp_tfa989x_params'):machine.index('static struct snd_soc_dai_link cht_dailink')]
 require(re.search(r'\.'+field+r'\s*=\s*'+value+r'\b',block),'Wrong amp '+field)
require('SNDRV_PCM_FORMAT_S24_LE' in machine and 'SND_SOC_DAILINK_REG(ssp2_port, ssp2_codec, platform)' in machine,'SSP/AIF1 transport changed')
require('{"Platform Clock", NULL, "PLL"}' in machine,'Permanent PLL dependency removed')
physical='SND_SOC_DAILINK_REG(rt5659_aif2_cpu, spk_codecs)' in machine
if physical:
 require('SND_SOC_DAIFMT_CBC_CFC' in machine and '.playback_only = 1' in machine,'Wrong amp clock/direction')
 require(all(x in machine for x in ['COMP_CPU("rt5659-aif2")','COMP_CODEC("i2c-tfa9890:00", "tfa989x-hifi")','COMP_CODEC("i2c-tfa9890:01", "tfa989x-hifi")']),'Wrong physical components')
 require(not any(x in machine for x in ['COMP_CPU("rt5659-aif1")','"Codec AIF2 Port"','{"Left HiFi Playback", NULL, "AIF2 Playback"}']),'Old synthetic paths remain')
else:require('SND_SOC_DAILINK_REG(rt5659_aif1_cpu, rt5659_aif2_codec)' in machine,'Unknown transport model')
path=['AIF1 Playback','AIF1RX','IF1 DAC1','IF1 DAC1 L','DAC L1 Mux','DAC1 MIXL','DAC_REF','IF2 ADC Mux','IF2 ADC','IF2 ADC Swap Mux','AIF2TX','AIF2 Capture']
for source,sink in zip(path[1:],path[2:]):
 if (source,sink)==('AIF2TX','AIF2 Capture'):continue
 require(re.search(r'\{\s*"'+re.escape(sink)+r'"\s*,[^\n]*"'+re.escape(source)+r'"\s*\}',codec),'Observed signal edge missing '+source+' -> '+sink)
require('"IF2 ADC Mux"' in machine and 'item[0] = 2' in machine,'DAC_REF mux initialization missing')
extracted={name:function(dapm,name) for name in ['dapm_is_connected_ep','dapm_is_connected_output_ep','dapm_is_connected_input_ep','dapm_generic_check_power','dapm_dai_link_event_pre_pmu']}
extracted['snd_soc_get_stream_cpu']=function(core,'snd_soc_get_stream_cpu')
prefix=r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <errno.h>
#define CHECK(x) do {if (!(x)) {fprintf(stderr,"CHECK failed line %d: %s\n",__LINE__,#x);exit(70);}} while(0)
#undef __always_inline
#define __always_inline inline __attribute__((always_inline))
#define __free(x) __attribute__((cleanup(freep)))
static void freep(void *p) {free(*(void **)p);}
#define kzalloc_obj(x) calloc(1,sizeof(x))
#define DAPM_UPDATE_STAT(w,s) ((void)(w))
#define trace_snd_soc_dapm_path(w,d,p) ((void)(w))
#define DAPM_DIR_REVERSE(d) ((enum snd_soc_dapm_direction)((d)^1))
#define SND_SOC_DAPM_DIR_TO_EP(d) (1U<<(d))
#define SNDRV_PCM_STREAM_PLAYBACK 0
#define SNDRV_PCM_STREAM_CAPTURE 1
#define SNDRV_PCM_HW_PARAM_FORMAT 0
#define SNDRV_PCM_HW_PARAM_RATE 0
#define SNDRV_PCM_HW_PARAM_CHANNELS 1
enum snd_soc_dapm_direction {SND_SOC_DAPM_DIR_IN,SND_SOC_DAPM_DIR_OUT};
struct list_head {int unused;};
static void list_add_tail(struct list_head *a,struct list_head *b){(void)a;(void)b;}
struct device {int unused;};
struct snd_soc_dapm_path;
struct snd_soc_dapm_widget {const char *name;int endpoints[2];unsigned is_ep;bool connected;struct list_head work_list;
 struct snd_soc_dapm_path *edges[2][64];unsigned count[2];void *priv,*dapm;};
struct snd_soc_dapm_path {union {struct {struct snd_soc_dapm_widget *source,*sink;};struct snd_soc_dapm_widget *node[2];};bool is_supply,walking,connect;};
#define snd_soc_dapm_widget_for_each_path(w,d,p) for(unsigned _j=0;_j<(w)->count[d] && ((p)=(w)->edges[d][_j],true);_j++)
#define snd_soc_dapm_widget_for_each_source_path(w,p) snd_soc_dapm_widget_for_each_path(w,1,p)
#define snd_soc_dapm_widget_for_each_sink_path(w,p) snd_soc_dapm_widget_for_each_path(w,0,p)
static int dapm_suspend_check(struct snd_soc_dapm_widget *w){return w->connected;}
struct snd_soc_pcm_stream {unsigned formats,rate_min,rate_max,channels_min,channels_max;};
struct snd_soc_dai_link {const struct snd_soc_pcm_stream *c2c_params;};
struct snd_soc_pcm_runtime {struct snd_soc_dai_link *dai_link;unsigned c2c_params_select;};
struct snd_pcm_runtime {unsigned format,subformat,channels,rate;};
struct snd_pcm_substream {struct snd_pcm_runtime *runtime;int stream,hw_opened;struct snd_soc_pcm_runtime *rtd;};
struct snd_mask {unsigned value;};struct snd_interval {unsigned min,max;};
struct snd_pcm_hw_params {struct snd_mask format;struct snd_interval intervals[2];};
#define hw_param_mask(p,i) (&(p)->format)
#define hw_param_interval(p,i) (&(p)->intervals[i])
static void snd_mask_set(struct snd_mask *m,unsigned x){m->value=x;}
static unsigned params_format(struct snd_pcm_hw_params *p){return p->format.value;}
static unsigned params_subformat(struct snd_pcm_hw_params *p){(void)p;return 0;}
static unsigned params_channels(struct snd_pcm_hw_params *p){return p->intervals[1].min;}
static unsigned params_rate(struct snd_pcm_hw_params *p){return p->intervals[0].min;}
struct snd_soc_dai {const char *name;int startup,activate,hw_params,stream;};
static struct snd_soc_pcm_runtime *snd_soc_substream_to_rtd(struct snd_pcm_substream *s){return s->rtd;}
static struct device *snd_soc_dapm_to_dev(void *p){(void)p;return NULL;}
#define dev_err(dev,...) ((void)(dev))
#define dev_warn(dev,...) ((void)(dev))
static int snd_soc_dai_startup(struct snd_soc_dai *d,struct snd_pcm_substream *s){d->startup++;d->stream=s->stream;return 0;}
static void snd_soc_dai_activate(struct snd_soc_dai *d,int stream){d->activate++;d->stream=stream;}
static int snd_soc_dai_hw_params(struct snd_soc_dai *d,struct snd_pcm_substream *s,struct snd_pcm_hw_params *p){
 CHECK(p->format.value==2 && params_rate(p)==48000 && params_channels(p)==2);d->hw_params++;d->stream=s->stream;return 0;}
static void dapm_update_dai_unlocked(struct snd_pcm_substream *s,struct snd_pcm_hw_params *p,struct snd_soc_dai *d){(void)s;(void)p;(void)d;}
'''
model=r'''
static struct snd_soc_dapm_widget nodes[64];static struct snd_soc_dapm_path paths[128];static unsigned nn,np;
static struct snd_soc_dai dais[5];
static struct snd_soc_dapm_widget *node(const char *name){
 for(unsigned i=0;i<nn;i++)if(!strcmp(nodes[i].name,name))return &nodes[i];
 CHECK(nn<64);struct snd_soc_dapm_widget *w=&nodes[nn++];w->name=name;w->connected=true;return w;
}
static void edge(const char *a,const char *b){
 CHECK(np<128);struct snd_soc_dapm_path *p=&paths[np++];p->source=node(a);p->sink=node(b);p->connect=true;
 CHECK(p->source->count[0]<64 && p->sink->count[1]<64);
 p->source->edges[0][p->source->count[0]++]=p;p->sink->edges[1][p->sink->count[1]++]=p;
}
static void reset(void){for(unsigned i=0;i<nn;i++)nodes[i].endpoints[0]=nodes[i].endpoints[1]=-1;for(unsigned i=0;i<np;i++)CHECK(!paths[i].walking);}
static void stream(const char *n,unsigned ep){node(n)->is_ep=ep;reset();}
static int power(const char *n){return dapm_generic_check_power(node(n));}
static void build(bool physical){
 memset(nodes,0,sizeof(nodes));memset(paths,0,sizeof(paths));memset(dais,0,sizeof(dais));nn=np=0;
 for(unsigned i=1;i<sizeof(signal)/sizeof(signal[0]);i++)edge(signal[i-1],signal[i]);
 edge("Int Mic","ADC");edge("ADC","AIF1 Capture");node("Int Mic")->is_ep=1;
 edge("Left HiFi Playback","Left OUT");edge("Right HiFi Playback","Right OUT");edge("Left OUT","Ext Spk");edge("Right OUT","Ext Spk");node("Ext Spk")->is_ep=2;
 edge("DAC1 MIXL","Headphone");node("Headphone")->is_ep=2;node("Headphone")->connected=false;
 struct snd_soc_dai_link l={.c2c_params=(void *)1};
 if(physical){
  CHECK(snd_soc_get_stream_cpu(&l,0)==1);
  /* Core dapm_connect_dai_pair adds the shared source edge per codec. */
  edge("AIF2 Capture","Physical-playback");edge("Physical-playback","Left HiFi Playback");
  edge("AIF2 Capture","Physical-playback");edge("Physical-playback","Right HiFi Playback");
 }else{
  CHECK(snd_soc_get_stream_cpu(&l,0)==1 && snd_soc_get_stream_cpu(&l,1)==0);
  edge("AIF1 Capture","Legacy-playback");edge("Legacy-playback","AIF2 Playback");
  edge("AIF2 Capture","Legacy-capture");edge("Legacy-capture","AIF1 Playback");
  edge("AIF2 Playback","Left HiFi Playback");edge("AIF2 Playback","Right HiFi Playback");
 }
 reset();
}
static void params_check(void){
 build(true);const char *names[]={"AIF2 Capture","Left HiFi Playback","Right HiFi Playback"};
 for(unsigned i=0;i<3;i++){dais[i].name=names[i];node(names[i])->priv=&dais[i];}
 struct snd_soc_pcm_stream fixed={.formats=1U<<2,.rate_min=48000,.rate_max=48000,.channels_min=2,.channels_max=2};
 struct snd_soc_dai_link link={.c2c_params=&fixed};struct snd_soc_pcm_runtime rtd={.dai_link=&link};struct snd_pcm_substream s={.rtd=&rtd};
 CHECK(dapm_dai_link_event_pre_pmu(node("Physical-playback"),&s)==0 && s.hw_opened);
 CHECK(dais[0].startup==2 && dais[0].activate==2 && dais[0].hw_params==2 && dais[0].stream==1);
 for(unsigned i=1;i<3;i++)CHECK(dais[i].startup==1 && dais[i].activate==1 && dais[i].hw_params==1 && dais[i].stream==0);
 CHECK(s.runtime->format==2 && s.runtime->rate==48000 && s.runtime->channels==2);free(s.runtime);
}
int main(void){
 struct snd_soc_dai_link normal={0},c2c={.c2c_params=(void *)1};
 CHECK(snd_soc_get_stream_cpu(&normal,0)==0 && snd_soc_get_stream_cpu(&normal,1)==1);
 CHECK(snd_soc_get_stream_cpu(&c2c,0)==1 && snd_soc_get_stream_cpu(&c2c,1)==0);
 build(false);node("Int Mic")->connected=false;reset();CHECK(power("AIF1 Playback") && power("AIF2 Capture"));
 node("Int Mic")->connected=true;reset();CHECK(power("Left HiFi Playback"));
 build(PHYSICAL);node("Int Mic")->connected=false;reset();
 if(power("AIF1 Playback") || power("Left HiFi Playback")){fputs("unexpected-idle-cycle-power\n",stderr);return 71;}
 for(unsigned pass=0;pass<100;pass++){
  stream("AIF1 Playback",1);CHECK(power("Left HiFi Playback") && power("Right HiFi Playback"));
  node("Int Mic")->connected=true;stream("AIF1 Capture",2);CHECK(power("ADC") && power("Left HiFi Playback"));
  stream("AIF1 Playback",0);CHECK(power("ADC") && !power("Left HiFi Playback") && !power("AIF2 Capture"));
  stream("AIF1 Capture",0);CHECK(!power("ADC") && !power("Left HiFi Playback"));
 }
 node("Headphone")->connected=true;node("Ext Spk")->connected=false;stream("AIF1 Playback",1);CHECK(power("Headphone") && !power("Left HiFi Playback"));
 stream("AIF1 Playback",0);CHECK(!power("Headphone"));
 params_check();puts("production-core-cycle/direction/100-duplex-walks/multicodec-params PASS");return 0;
}
'''
source=prefix+'\n'+''.join(extracted[n]+'\n' for n in ['dapm_is_connected_ep','dapm_is_connected_output_ep','dapm_is_connected_input_ep','dapm_generic_check_power','snd_soc_get_stream_cpu','dapm_dai_link_event_pre_pmu'])+'\nstatic const char *signal[]='+json.dumps(path).replace('[','{').replace(']','}')+';\n#define PHYSICAL '+('1' if physical else '0')+'\n'+model
with tempfile.TemporaryDirectory(prefix='mp2-aif2-test-') as d:
 d=Path(d);c=d/'test.c';c.write_text(source);exe=d/'test'
 p=subprocess.run(['cc','-std=gnu11','-O1','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer','-no-pie',str(c),'-o',str(exe)],capture_output=True,text=True,timeout=40)
 require(p.returncode==0,p.stdout+p.stderr)
 p=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30)
 require(p.returncode==0,p.stdout+p.stderr)
 print(json.dumps(dict(state='actual-core-minimal-graph-pass',physical_aif2_to_two_amps=physical,duplex_walks=100,multicodec_hwparams_callbacks_verified=True,source_functions_sha256={k:hashlib.sha256(v.encode()).hexdigest() for k,v in extracted.items()},scope='Extracted production functions in minimal signal graph, not full scheduler/codec hardware or cold-boot proof.')))
