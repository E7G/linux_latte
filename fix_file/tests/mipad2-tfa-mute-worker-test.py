#!/usr/bin/env python3
"""Execute real TFA mute/init callbacks against a controllable worker schedule.

Models queued init arriving after mute; cancellation must never hold init lock.
No hardware access; this is not a kernel workqueue stress or acoustic test.
"""
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / "sound/soc/codecs/tfa98xx-xiaomi/tfa98xx.c").read_text()


def callback(name):
    match = re.search(rf"static (?:int|void) {name}\([^;]*?\)\s*\{{", source, re.S)
    if not match:
        raise ValueError(name)
    start = match.start()
    brace = source.index("{", start)
    depth, end = 1, brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


mock = r"""
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <errno.h>
#include <stdio.h>
typedef unsigned short u16;
#define HZ 100
#define TFA98XX_DSP_INIT_DONE 1
#define TFA98XX_DSP_INIT_FAIL 2
#define TFA98XX_DSP_INIT_PENDING 0
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x, v) ((x) = (v))
#define TFA98XX_STATUSREG 0
#define TFA98XX_SYS_CTRL 9
#define TFA98XX_CF_STATUS 0x73
#define container_of(ptr, type, member) ((type *)((char *)(ptr) - offsetof(type, member)))
static void test_log(const char *fmt, ...) { (void)fmt; }
#define dev_info(dev, ...) test_log(__VA_ARGS__)
#define pr_debug(...) test_log(__VA_ARGS__)
struct work_struct { int unused; };
struct delayed_work { struct work_struct work; };
struct mutex { int held; };
struct tfa98xx {
    struct work_struct init_work;
    struct delayed_work delay_work;
    struct mutex dsp_init_lock;
    bool desired_running;
    void *tfa98xx_wq, *component;
    int profile_ctl, vstep_ctl, dsp_init, monitor_status;
};
struct snd_soc_component { struct tfa98xx *priv; };
struct snd_soc_dai { struct snd_soc_component *component; };
struct snd_kcontrol { struct snd_soc_component *component; };
struct snd_ctl_elem_value { struct { struct { long value[1]; } integer; } value; };
static bool defer_dsp_start;
static struct tfa98xx *amp;
static int starts, stops, cancel_monitor, cancel_init, queued_monitor;
static int start_error, stop_error, powered;
static void *snd_soc_component_get_drvdata(struct snd_soc_component *c) { return c->priv; }
static struct snd_soc_component *snd_soc_kcontrol_component(struct snd_kcontrol *k)
{ return k->component; }
static void mutex_lock(struct mutex *lock) { assert(!lock->held); lock->held = 1; }
static void mutex_unlock(struct mutex *lock) { assert(lock->held); lock->held = 0; }
static int cancel_delayed_work_sync(struct delayed_work *work)
{
    assert(work == &amp->delay_work && !amp->dsp_init_lock.held);
    cancel_monitor++; queued_monitor = 0; return 1;
}
static int cancel_work_sync(struct work_struct *work) __attribute__((unused));
static int cancel_work_sync(struct work_struct *work)
{
    assert(work == &amp->init_work && !amp->dsp_init_lock.held);
    cancel_init++; return 1;
}
static int queue_delayed_work(void *wq, struct delayed_work *work, unsigned int delay)
    __attribute__((unused));
static int queue_delayed_work(void *wq, struct delayed_work *work, unsigned int delay)
{
    (void)wq;
    assert(work == &amp->delay_work && delay == HZ);
    queued_monitor++; return 1;
}
static int mod_delayed_work(void *wq, struct delayed_work *work, unsigned int delay)
    __attribute__((unused));
static int mod_delayed_work(void *wq, struct delayed_work *work, unsigned int delay)
{
    (void)wq;
    assert(work == &amp->delay_work && delay == 0);
    assert(amp->desired_running && amp->monitor_status);
    queued_monitor = 1; return 1;
}
static int tfa98xx_is_pwdn(struct tfa98xx *tfa) __attribute__((unused));
static int tfa98xx_is_pwdn(struct tfa98xx *tfa) { assert(tfa == amp); return !powered; }
static int tfa98xx_dsp_start(struct tfa98xx *tfa, int profile, int step)
{
    assert(tfa == amp && tfa->dsp_init_lock.held);
    assert(profile == tfa->profile_ctl && step == tfa->vstep_ctl);
    starts++; if (!start_error) powered = 1; return start_error;
}
static int tfa98xx_dsp_stop(struct tfa98xx *tfa)
{
    assert(tfa == amp && tfa->dsp_init_lock.held);
    stops++; powered = 0; return stop_error;
}
static unsigned int snd_soc_component_read(void *component, unsigned int reg)
{ (void)component; (void)reg; return 0; }
"""
harness = r"""
int main(void)
{
    struct tfa98xx tfa = { .desired_running = true, .monitor_status = 1 };
    struct snd_soc_component c = { .priv = &tfa };
    struct snd_soc_dai dai = { .component = &c };
    struct snd_kcontrol control = { .component = &c };
    struct snd_ctl_elem_value value = { .value.integer.value = {1} };
    amp = &tfa;
    /* Model queued init which arrives after an earlier mute request. */
    assert(tfa98xx_digital_mute(&dai, 1) == 0 && !tfa.desired_running);
    tfa98xx_dsp_init(&tfa.init_work);
    assert(starts == 0 && powered == 0 && !tfa.dsp_init_lock.held);
    assert(cancel_monitor == 1 && cancel_init == 1);
    assert(tfa98xx_digital_mute(&dai, 0) == 0 && tfa.desired_running);
    assert(queued_monitor == 1);
    tfa98xx_dsp_init(&tfa.init_work);
    assert(starts == 1 && powered && tfa.dsp_init == TFA98XX_DSP_INIT_DONE);
    stop_error = -EIO;
    assert(tfa98xx_digital_mute(&dai, 1) == -EIO);
    assert(!powered && !tfa.desired_running && !tfa.dsp_init_lock.held);
    tfa98xx_dsp_init(&tfa.init_work);
    assert(starts == 1 && !powered);
    stop_error = 0;
    assert(tfa98xx_digital_mute(&dai, 0) == 0);
    start_error = -ETIMEDOUT;
    tfa98xx_dsp_init(&tfa.init_work);
    assert(starts == 2 && tfa.dsp_init == TFA98XX_DSP_INIT_FAIL);
    assert(!tfa.dsp_init_lock.held);
    assert(tfa98xx_digital_mute(&dai, 1) == 0);
    defer_dsp_start = true;
    assert(tfa98xx_digital_mute(&dai, 0) == 0 && !tfa.desired_running);
    tfa98xx_dsp_init(&tfa.init_work);
    assert(starts == 2 && !powered && !tfa.dsp_init_lock.held);
    assert(cancel_monitor == 3 && cancel_init == 3);
    defer_dsp_start = false;
    assert(tfa98xx_digital_mute(&dai, 0) == 0);
    tfa98xx_dsp_init(&tfa.init_work);
    start_error = 0;
    assert(tfa98xx_set_stop_ctl(&control, &value) == 1);
    assert(cancel_monitor == 4 && cancel_init == 4);
    assert(!tfa.desired_running && !tfa.monitor_status && !powered);
    tfa98xx_dsp_init(&tfa.init_work);
    assert(starts == 3 && !powered);
    /* A subsequent C2C unmute must restore monitoring after explicit stop. */
    assert(tfa98xx_digital_mute(&dai, 0) == 0);
    assert(tfa.desired_running && tfa.monitor_status && queued_monitor == 1);
    assert(tfa.dsp_init == TFA98XX_DSP_INIT_PENDING);
    tfa98xx_dsp_init(&tfa.init_work);
    assert(powered && starts == 4);
    value.value.integer.value[0] = 1;
    stop_error = -EIO;
    assert(tfa98xx_set_stop_ctl(&control, &value) == -EIO);
    assert(!tfa.desired_running && !powered && !tfa.dsp_init_lock.held);
    stop_error = 0;
    value.value.integer.value[0] = 0;
    assert(tfa98xx_set_stop_ctl(&control, &value) == 1);
    assert(tfa.desired_running && tfa.monitor_status && queued_monitor == 1);
    value.value.integer.value[0] = 2;
    assert(tfa98xx_set_stop_ctl(&control, &value) == -EINVAL);
    puts("PASS: real mute/stop/init callbacks; both workers drained outside lock, immediate monitor, stop-to-playback restart, invalid control and error paths");
    return 0;
}
"""
callbacks = callback("tfa98xx_dsp_init") + "\n" + callback("tfa98xx_set_running") + "\n" + callback("tfa98xx_digital_mute") + "\n" + callback("tfa98xx_set_stop_ctl")
with tempfile.TemporaryDirectory(prefix="mipad2-tfa-mute-worker-") as temp:
    cfile, binary = Path(temp) / "test.c", Path(temp) / "test"
    cfile.write_text(mock + callbacks + harness)
    subprocess.run(shlex.split(os.environ.get("CC", "clang")) + [
        "-std=c11", "-Wall", "-Wextra", "-Werror", str(cfile), "-o", str(binary)
    ], check=True)
    subprocess.run([str(binary)], check=True)
