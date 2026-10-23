#!/usr/bin/env python3
"""Execute production output event/worker scheduling; check actual DAPM order.

No device access, actual BCLK measurement, DSP execution or acoustic claim.
"""
from pathlib import Path
import argparse, os, re, shlex, subprocess, tempfile

parser = argparse.ArgumentParser()
parser.add_argument('--codec-source', type=Path)
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
source = (args.codec_source or root/'sound/soc/codecs/tfa98xx-xiaomi/tfa98xx.c').read_text()
core = (root/'sound/soc/soc-dapm.c').read_text()
board = (root/'sound/soc/intel/boards/cht_bsw_rt5659.c').read_text()

def require(ok, message):
    if not ok:
        raise RuntimeError(message)

def function(name):
    m = re.search(r'static int '+name+r'\([^;]*?\)\s*\{', source, re.S)
    require(m is not None, 'Missing production callback: '+name)
    start = m.start(); end = source.index('{', start)+1; depth = 1
    while depth:
        depth += (source[end] == '{')-(source[end] == '}'); end += 1
    return source[start:end]

require(re.search(r'SND_SOC_DAPM_MIXER_E\("NXP Output Mixer",\s*SND_SOC_NOPM,\s*0,\s*0,\s*NULL,\s*0,\s*tfa98xx_output_event,\s*SND_SOC_DAPM_POST_PMU\s*\|\s*SND_SOC_DAPM_PRE_PMD\)', source),
        'Output widget has no lifecycle callback with the required events')
for direction in ('up', 'down'):
    table = re.search(r'static int dapm_'+direction+r'_seq\[\] = \{(.*?)\};', core, re.S)
    require(table is not None, 'Missing actual core sequence table')
    seq = {name: int(value) for name, value in re.findall(r'\[snd_soc_dapm_(\w+)\]\s*=\s*(\d+)', table[1])}
    for clock in ('dai_in', 'dai_out', 'aif_in', 'aif_out', 'dai_link', 'supply', 'clock_supply'):
        require((seq[clock] < seq['mixer']) if direction == 'up' else (seq['mixer'] < seq[clock]),
                direction+' mixer/clock ordering changed: '+clock)
for side in ('L', 'R'):
    link = re.search(r'\.name = "Dummy-TFA989x Speaker '+side+r'",(.*?)SND_SOC_DAILINK_REG', board, re.S)
    require(link is not None and '.no_pcm = 1' in link[1] and 'c2c_params' not in link[1],
            'Machine amp link no longer uses the tested graph-only topology')

shim = r'''
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#define CHECK(x) do { if (!(x)) { fprintf(stderr,"CHECK failed: %s line %d\n",#x,__LINE__); exit(89); } } while (0)
#define WRITE_ONCE(x,v) ((x)=(v))
#define SND_SOC_DAPM_POST_PMU 2
#define SND_SOC_DAPM_PRE_PMD 4
#define TFA98XX_DSP_INIT_PENDING 0
struct mutex { bool held; };
struct work_struct { int unused; };
struct delayed_work { int unused; };
struct tfa98xx {
    struct mutex dsp_init_lock;
    struct work_struct init_work;
    struct delayed_work delay_work;
    bool desired_running;
    int monitor_status, dsp_init;
    void *tfa98xx_wq;
};
struct snd_soc_component { struct tfa98xx *data; };
struct snd_soc_dapm_context { struct snd_soc_component *component; };
struct snd_soc_dapm_widget { struct snd_soc_dapm_context *dapm; };
struct snd_kcontrol { int unused; };
static bool defer_dsp_start, queued, clocks;
static struct tfa98xx *amp;
static int stop_error, stops, cancels, queues;
static struct snd_soc_component *snd_soc_dapm_to_component(struct snd_soc_dapm_context *d) { return d->component; }
static struct tfa98xx *snd_soc_component_get_drvdata(struct snd_soc_component *c) { return c->data; }
static void mutex_lock(struct mutex *m) { CHECK(!m->held); m->held=true; }
static void mutex_unlock(struct mutex *m) { CHECK(m->held); m->held=false; }
static void cancel_delayed_work_sync(struct delayed_work *w) {
    CHECK(w==&amp->delay_work && !amp->dsp_init_lock.held); queued=false; cancels++;
}
static void cancel_work_sync(struct work_struct *w) {
    CHECK(w==&amp->init_work && !amp->dsp_init_lock.held); cancels++;
}
static void mod_delayed_work(void *q, struct delayed_work *w, unsigned int delay) {
    (void)q;CHECK(w==&amp->delay_work && !delay && clocks);
    CHECK(amp->desired_running && amp->monitor_status && amp->dsp_init_lock.held);
    queued=true; queues++;
}
static int tfa98xx_dsp_stop(struct tfa98xx *t) {
    CHECK(t==amp && clocks && t->dsp_init_lock.held && !queued);
    CHECK(!t->desired_running && !t->monitor_status); stops++;return stop_error;
}
'''

main = r'''
int main(void) {
    struct tfa98xx a={0};amp=&a;
    struct snd_soc_component c={.data=&a};
    struct snd_soc_dapm_context d={.component=&c};
    struct snd_soc_dapm_widget w={.dapm=&d};
    /* Safe probe: neither power edge performs register/workqueue operations. */
    defer_dsp_start=true;clocks=false;
    CHECK(!tfa98xx_output_event(&w,NULL,SND_SOC_DAPM_POST_PMU));
    CHECK(!tfa98xx_output_event(&w,NULL,SND_SOC_DAPM_PRE_PMD));
    CHECK(!stops && !cancels && !queues && !a.desired_running);
    defer_dsp_start=false;clocks=true;
    /* Short playback may stop before the asynchronous worker ever runs. */
    CHECK(!tfa98xx_output_event(&w,NULL,SND_SOC_DAPM_POST_PMU));
    CHECK(queued && a.desired_running && a.monitor_status && queues==1);
    CHECK(!tfa98xx_output_event(&w,NULL,SND_SOC_DAPM_PRE_PMD));
    CHECK(!queued && !a.desired_running && !a.monitor_status && stops==1 && cancels==2);
    /* Resume/reopen schedules work again; stop errors are not swallowed. */
    CHECK(!tfa98xx_output_event(&w,NULL,SND_SOC_DAPM_POST_PMU));
    CHECK(queued && queues==2); stop_error=-EIO;
    CHECK(tfa98xx_output_event(&w,NULL,SND_SOC_DAPM_PRE_PMD)==-EIO);
    CHECK(!queued && stops==2 && cancels==4 && !a.desired_running);
    CHECK(tfa98xx_output_event(&w,NULL,999)==-EINVAL);
    CHECK(stops==2 && queues==2 && cancels==4 && !a.dsp_init_lock.held);
    puts("PASS: production DAPM events, passive probe, rapid stop, reopen, error propagation; actual core order checked");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='mipad2-tfa-dapm-') as tmp:
    p = Path(tmp); c = p/'test.c'; binary = p/'test'
    c.write_text(shim+function('tfa98xx_set_running')+'\n'+function('tfa98xx_output_event')+main)
    cmd = shlex.split(os.environ.get('CC', 'clang'))+['-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-parameter',
            '-fsanitize=address,undefined','-fno-omit-frame-pointer','-g',str(c),'-o',str(binary)]
    subprocess.run(cmd, check=True)
    subprocess.run([str(binary)], check=True)
