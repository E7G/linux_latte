#!/usr/bin/env python3
"""Execute the real factory probe/stream initializer with narrow ASoC stubs.

Uses actual codec widget declarations and current machine prefix/route ABI.
No hardware, DSP firmware execution, real DAPM power or UCM acceptance claimed.
"""
from pathlib import Path
import argparse,os,re,subprocess,tempfile,shlex,json

parser=argparse.ArgumentParser()
parser.add_argument('--codec-source',type=Path)
parser.add_argument('--expect-topology-failure',action='store_true')
args=parser.parse_args()
root=Path(__file__).resolve().parents[2]
source=(args.codec_source or root/'sound/soc/codecs/tfa98xx-xiaomi/tfa98xx.c').read_text()
board=(root/'sound/soc/intel/boards/cht_bsw_rt5659.c').read_text()
def require(ok,msg):
    if not ok:raise RuntimeError(msg)
def block(start):
    opening=source.index('{',start);depth=1;end=opening+1
    while depth:
        depth+=(source[end]=='{')-(source[end]=='}');end+=1
    return source[start:end]
probe=block(source.index('static int tfa98xx_probe('))
control_match=re.search(r'static (?:const )?struct snd_kcontrol_new tfa98xx_controls\[\] =',source)
require(control_match is not None,'Production control template missing')
controls=block(control_match.start())+';'
callbacks=set(re.findall(r'\.(?:info|get|put)\s*=\s*(\w+)',controls))

widgets=[]
for m in re.finditer(r'static const struct snd_soc_dapm_widget tfa98xx_\w*dapm_widgets\[\] =',source):
    widgets.append(block(m.start())+';')
require(widgets,'Production widget declarations missing')
i2c_probe=block(source.index('static int tfa98xx_i2c_probe('))
stream=re.search(r'(?:strscpy|scnprintf)\(tfa98xx->playback_stream_name,.*?;',i2c_probe,re.S)
require(stream is not None,'Production stream initializer missing')
for prefix in ('Left','Right'):
    require(f'.name_prefix = "{prefix}"' in board,'Machine prefix changed')
    require(f'{{"Ext Spk", NULL, "{prefix} OUT"}}' in board,'Machine output ABI changed')
require('SND_SOC_DAILINK_REG(rt5659_aif2_cpu, spk_codecs)' in board,
        'Machine must use the physical AIF2-to-amplifier C2C link')
require('COMP_CPU("rt5659-aif2")' in board and 'SND_SOC_DAIFMT_CBC_CFC' in board,
        'Amplifiers must consume clocks from the AIF2 transmitter')
for index in ('00', '01'):
    require(f'COMP_CODEC("i2c-tfa9890:{index}", "tfa989x-hifi")' in board,
            'Both actual amplifier receivers must participate in the C2C link')

shim=r"""
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint16_t u16;
#define GFP_KERNEL 0
#define MAX_CONTROL_NAME 32
#define TFA98XX_REVISIONNUMBER 3
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define SND_SOC_NOPM 0
#define dev_info(...) ((void)0)
#define dev_dbg(...) ((void)0)
#define dev_err(...) ((void)0)
#define scnprintf snprintf
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"CHECK failed: %s line %d\n",#x,__LINE__); exit(89); } } while (0)
struct device { const char *name; };
struct i2c_client { int addr; struct device dev; };
struct snd_soc_component;
struct snd_soc_dapm_context { struct snd_soc_component *component; };
struct tfaprofile { int placeholder; };
struct tfa98xx {
    struct snd_soc_component *component;
    struct i2c_client *i2c;
    bool needs_full_init;
    unsigned int rev,subrev;
    struct { const char *name; } fw;
    int profile_count,profile_current,vstep_current,profile_ctl,vstep_ctl;
    struct tfaprofile *profiles;
    char playback_stream_name[32];
};
struct snd_soc_component { struct device *dev; struct tfa98xx *data; const char *prefix; struct snd_soc_dapm_context dapm; };
struct snd_soc_dapm_widget { const char *name; };
struct snd_soc_dapm_route { const char *sink,*control,*source; };
struct snd_kcontrol_new { int iface; const char *name; void *info,*get,*put; unsigned long private_value; };
#define SNDRV_CTL_ELEM_IFACE_MIXER 1
#define SND_SOC_DAPM_MIXER(n,...) { .name=(n) }
#define SND_SOC_DAPM_MIXER_E(n,...) { .name=(n) }
#define SND_SOC_DAPM_OUTPUT(n) { .name=(n) }
static char prof_name[32],vol_name[32],stop_name[32];
static struct snd_kcontrol_new control_copies[8][3];static int allocation_count,allocation_error;
static unsigned long registered_values[2];
static int load_error,widget_error,route_error,control_error;
static int widget_calls,route_calls,control_calls;
static char graph[32][80];static size_t graph_count;
static const char *dev_name(struct device *d) { return d->name; }
static struct tfa98xx *snd_soc_component_get_drvdata(struct snd_soc_component *c) { return c->data; }
static unsigned int snd_soc_component_read(struct snd_soc_component *c,unsigned int reg) { (void)c;(void)reg;return 0x1280; }
static int tfa98xx_cnt_loadfile(struct tfa98xx *t,int n) { (void)t;(void)n;return load_error; }
static struct snd_soc_dapm_context *snd_soc_component_to_dapm(struct snd_soc_component *c) { c->dapm.component=c;return &c->dapm; }
static void add(const char *name) { CHECK(graph_count<32);snprintf(graph[graph_count++],80,"%s",name); }
static bool has(const char *name) { for(size_t i=0;i<graph_count;i++)if(!strcmp(graph[i],name))return true;return false; }
static void qualify(char *dst,struct snd_soc_dapm_context *d,const char *name) { snprintf(dst,80,"%s %s",d->component->prefix,name); }
static int snd_soc_dapm_new_controls(struct snd_soc_dapm_context *d,const struct snd_soc_dapm_widget *w,unsigned int n) {
    widget_calls++;if(widget_error)return widget_error;
    for(unsigned int i=0;i<n;i++){char name[80];qualify(name,d,w[i].name);add(name);}return 0;
}
static int snd_soc_dapm_add_routes(struct snd_soc_dapm_context *d,const struct snd_soc_dapm_route *r,unsigned int n) {
    route_calls++;if(route_error)return route_error;
    for(unsigned int i=0;i<n;i++){char a[80],b[80];qualify(a,d,r[i].sink);qualify(b,d,r[i].source);if(!has(a)||!has(b))return -ENODEV;}return 0;
}
static int snd_soc_add_component_controls(struct snd_soc_component *c,const struct snd_kcontrol_new *k,unsigned int n) { CHECK(n==3);CHECK(k[0].private_value==(unsigned long)c->data->profiles);CHECK(k[1].private_value==k[0].private_value);CHECK(!strcmp(k[0].name,"Profile"));CHECK(!strcmp(k[1].name,"Master Volume"));CHECK(!strcmp(k[2].name,"Stop"));registered_values[!strcmp(c->prefix,"Right")]=k[0].private_value;control_calls++;return control_error; }
static __attribute__((unused)) void *devm_kmemdup(struct device *d,const void *src,size_t n,int flags) { (void)d;(void)flags;if(allocation_error)return NULL;CHECK(n==sizeof(control_copies[0]));CHECK(allocation_count<8);void *dst=control_copies[allocation_count++];memcpy(dst,src,n);return dst; }
static void reset(void) { allocation_error=allocation_count=0;registered_values[0]=registered_values[1]=0;graph_count=0;load_error=widget_error=route_error=control_error=0;widget_calls=route_calls=control_calls=0;add("Left HiFi Playback");add("Right HiFi Playback"); }
static void strscpy(char *d,const char *s,size_t n) { snprintf(d,n,"%s",s); }
"""
# A helper may be unused only in the baseline before stream API migration.
if 'static char prof_name[' not in source:
    shim=shim.replace('static char prof_name[32],vol_name[32],stop_name[32];','')
shim+='\n'+''.join('#define '+name+' NULL\n' for name in sorted(callbacks))
shim=shim.replace('static const char *dev_name','static __attribute__((unused)) const char *dev_name').replace('static void strscpy','static __attribute__((unused)) void strscpy')
init='static void init_stream(struct tfa98xx *tfa98xx,struct i2c_client *i2c) { (void)i2c; '+stream[0]+' }\n'
main=r"""
int main(void) {
 struct tfaprofile profiles[2]={{0},{0}};
 struct i2c_client left={.addr=0x34,.dev={.name="i2c-tfa9890:00"}},right={.addr=0x37,.dev={.name="i2c-tfa9890:01"}};
 struct tfa98xx a={.i2c=&left,.fw={.name="left"},.profiles=profiles,.profile_count=1},b={.i2c=&right,.fw={.name="right"},.profiles=profiles+1,.profile_count=1};
 struct snd_soc_component ca={.dev=&left.dev,.data=&a,.prefix="Left"},cb={.dev=&right.dev,.data=&b,.prefix="Right"};
 init_stream(&a,&left);init_stream(&b,&right);reset();
 CHECK(tfa98xx_probe(&ca)==0);CHECK(tfa98xx_probe(&cb)==0);
 CHECK(has("Left OUT")&&has("Right OUT"));CHECK(!has("Left OUT Left")&&!has("Right OUT Right"));
 CHECK(control_calls==2&&a.needs_full_init&&b.needs_full_init);CHECK(registered_values[0]==(unsigned long)profiles&&registered_values[1]==(unsigned long)(profiles+1));CHECK(tfa98xx_controls[0].private_value==0&&tfa98xx_controls[1].private_value==0);
 reset();load_error=-ENOENT;CHECK(tfa98xx_probe(&ca)==-ENOENT);CHECK(widget_calls==0&&control_calls==0);
 reset();left.addr=0x36;CHECK(tfa98xx_probe(&ca)==-EINVAL);CHECK(widget_calls==0);left.addr=0x34;
 reset();widget_error=-ENOMEM;CHECK(tfa98xx_probe(&ca)==-ENOMEM);CHECK(route_calls==0&&control_calls==0);
 reset();route_error=-EIO;CHECK(tfa98xx_probe(&ca)==-EIO);CHECK(control_calls==0);
 reset();allocation_error=1;CHECK(tfa98xx_probe(&ca)==-ENOMEM);CHECK(control_calls==0);
 reset();control_error=-ENOMEM;CHECK(tfa98xx_probe(&ca)==-ENOMEM);CHECK(control_calls==1);
 puts("actual-probe ABI and six error paths passed");return 0;
}
"""
code=shim+'\n'+controls+'\n'+'\n'.join(widgets)+'\n'+probe+'\n'+init+main
with tempfile.TemporaryDirectory(prefix='mipad2-tfa-probe-') as d:
    c=Path(d)/'probe.c';exe=Path(d)/'probe';c.write_text(code)
    cmd=shlex.split(os.environ.get('CC','clang'))+['-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(c),'-o',str(exe)]
    built=subprocess.run(cmd,capture_output=True,text=True);require(built.returncode==0,built.stderr)
    result=subprocess.run([str(exe)],capture_output=True,text=True)
    if args.expect_topology_failure:
        require(result.returncode==89 and 'tfa98xx_probe(&ca)==0' in result.stderr,'Baseline did not fail at the intended board-ABI gate')
        print(json.dumps(dict(state='baseline-board-ABI-mismatch-detected',hardware_tested=False)))
    else:
        require(result.returncode==0,result.stdout+result.stderr)
        print(json.dumps(dict(state='actual-probe-board-ABI-and-error-paths-pass',two_prefixed_instances=True,error_paths=6,asan_ubsan=True,hardware_tested=False,real_DAPM_power_or_DSP_tested=False)))
