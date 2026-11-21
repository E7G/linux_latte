#!/usr/bin/env python3
"""Run production factory mixer callbacks against the Linux control UAPI."""

import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

root = Path(os.environ.get("MIPAD2_KERNEL_SOURCE", Path(__file__).resolve().parents[2]))
codec = root / "sound/soc/codecs/tfa98xx-xiaomi"
c = (codec / "tfa98xx.c").read_text()
dsp = (codec / "tfa_dsp.c").read_text()
core = (codec / "tfa98xx-core.h").read_text()
header = (codec / "include/sound/tfa98xx.h").read_text()


def callback(source, name):
    start = re.search(r"^(?:static )?int " + name + r"\(", source, re.M)
    if not start:
        raise RuntimeError(f"missing callback: {name}")
    end = source.index("\n}", start.end()) + 2
    return source[start.start():end]


preamble = r"""
#include <stdbool.h>
#include <errno.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
/* Source-tree UAPI annotations that headers_install normally translates. */
#define __user
#define __force
#define __packed __attribute__((packed))
#include "asound.h"
typedef uint16_t u16;
#include "tfa98xx-regs.h"

#define READ_ONCE(x) (x)
#define pr_debug(...) ((void)0)
#define pr_err(...) ((void)0)
#define CHECK(expr) do { if (!(expr)) { \
    fprintf(stderr, "%d: %s\n", __LINE__, #expr); exit(1); \
} } while (0)
"""
defs = "\n".join(re.findall(r"^#define TFA98XX_DSP_INIT_.*$", core, re.M))
spec = re.search(r"struct tfaprofile \{.*?\n\};", header, re.S)
if not spec:
    raise RuntimeError("could not extract production profile state")

fixture = r"""
struct mutex { bool held; };
static struct mutex *lock(struct mutex *mutex)
{ CHECK(!mutex->held); mutex->held = true; return mutex; }
static void unlock(struct mutex **mutex)
{ CHECK((*mutex)->held); (*mutex)->held = false; }
#define guard(mutex) struct mutex *held __attribute__((cleanup(unlock))) = lock
#define lockdep_assert_held(mutex) CHECK((mutex)->held)
struct regmap { int error; unsigned int status; unsigned int reads; };
struct tfa98xx {
    struct regmap *regmap;
    struct snd_soc_component *component;
    struct mutex dsp_init_lock;
    int dsp_init, profile_count, profile_ctl, profile_current, vstep_ctl;
    bool desired_running, monitor_status;
    int starts, start_error, requested_profile, requested_step;
};
struct snd_soc_component { struct tfa98xx *amp; };
struct snd_kcontrol { struct snd_soc_component *comp; uintptr_t private_value; };
static bool defer_dsp_start;
static struct snd_soc_component *snd_kcontrol_chip(struct snd_kcontrol *ctl)
{ return ctl->comp; }
static struct tfa98xx *snd_soc_component_get_drvdata(struct snd_soc_component *comp)
{ return comp->amp; }
static int regmap_read(struct regmap *map, unsigned int reg, unsigned int *val)
{
    CHECK(reg == TFA98XX_STATUSREG);
    map->reads++;
    if (map->error)
        return map->error;
    *val = map->status;
    return 0;
}
static unsigned int __attribute__((unused))
snd_soc_component_read(struct snd_soc_component *comp, unsigned int reg)
{
    unsigned int value;
    int result = regmap_read(comp->amp->regmap, reg, &value);

    return result ? (unsigned int)result : value;
}
static int tfa98xx_dsp_start(struct tfa98xx *amp, int profile, int vstep)
{
    CHECK(amp->dsp_init_lock.held);
    amp->starts++;
    amp->requested_profile = profile;
    amp->requested_step = vstep;
    if (!amp->start_error)
        amp->profile_current = profile;
    return amp->start_error;
}
static void strscpy(char *dst, const char *src, size_t len)
{ snprintf(dst, len, "%s", src); }
"""

oracle = r"""
int main(void)
{
    struct tfaprofile left[] = {{.vsteps = 2, .vstep = 1, .name = "musicL"},
                                {.vsteps = 4, .name = "speechL"},
                                {.vsteps = 8, .name = "testL"},
                                {.vsteps = 0, .name = "bypassL"}};
    struct tfaprofile right[] = {{.vsteps = 1, .name = "musicR"},
                                 {.vsteps = 1, .name = "speechR"}};
    struct regmap map = {.status = TFA98XX_STATUSREG_SWS_MSK};
    struct regmap other_map = {.status = TFA98XX_STATUSREG_SWS_MSK};
    struct tfa98xx first = {.regmap = &map, .profile_count = 4, .vstep_ctl = 1};
    struct tfa98xx second = {.regmap = &other_map, .profile_count = 2};
    struct snd_soc_component lcomp = { .amp = &first }, rcomp = { .amp = &second };
    struct snd_kcontrol lctl = {.comp = &lcomp, .private_value = (uintptr_t)left};
    struct snd_kcontrol rctl = {.comp = &rcomp, .private_value = (uintptr_t)right};
    struct snd_ctl_elem_value val = {};
    struct snd_ctl_elem_info info = {};

    first.component = &lcomp;
    second.component = &rcomp;
    /* The single enum item is four bytes, not an LP64 long. */
    val.value.enumerated.item[1] = UINT_MAX;
    CHECK(tfa98xx_get_profile_ctl(&lctl, &val) == 0);
    CHECK(val.value.enumerated.item[0] == 0 && val.value.enumerated.item[1] == UINT_MAX);
    val.value.enumerated.item[0] = 1;
    CHECK(tfa98xx_set_profile_ctl(&lctl, &val) == 1);
    CHECK(first.profile_ctl == 1 && first.vstep_ctl == 2 && first.profile_current == 0);
    CHECK(tfa98xx_set_profile_ctl(&lctl, &val) == 0);

    /* A second staged change is relative to the selected, not the active profile. */
    val.value.enumerated.item[0] = 2;
    CHECK(tfa98xx_set_profile_ctl(&lctl, &val) == 1);
    CHECK(first.profile_ctl == 2 && first.vstep_ctl == 4 && first.profile_current == 0);
    CHECK(first.starts == 0 && map.reads == 0 && !first.dsp_init_lock.held);
    CHECK(tfa98xx_info_vol_ctl(&lctl, &info) == 0 && info.value.integer.max == 7);
    CHECK(tfa98xx_get_vol_ctl(&lctl, &val) == 0 && val.value.integer.value[0] == 3);
    val.value.integer.value[0] = 5;
    CHECK(tfa98xx_set_vol_ctl(&lctl, &val) == 1 && first.vstep_ctl == 2);
    CHECK(tfa98xx_get_vol_ctl(&lctl, &val) == 0 && val.value.integer.value[0] == 5);

    /* Single-step factory volume, enum notifications and channel isolation. */
    val.value.enumerated.item[0] = 1;
    CHECK(tfa98xx_set_profile_ctl(&rctl, &val) == 1 && second.profile_ctl == 1);
    CHECK(first.profile_ctl == 2 && !other_map.reads);
    CHECK(tfa98xx_info_vol_ctl(&rctl, &info) == 0 && info.value.integer.max == 0);
    val.value.integer.value[0] = 0;
    CHECK(tfa98xx_set_vol_ctl(&rctl, &val) == 0);
    val.value.integer.value[0] = 1;
    CHECK(tfa98xx_set_vol_ctl(&rctl, &val) == -EINVAL);
    info.value.enumerated.item = 1;
    CHECK(tfa98xx_info_profile_ctl(&rctl, &info) == 0);
    CHECK(info.type == SNDRV_CTL_ELEM_TYPE_ENUMERATED && info.count == 1);
    CHECK(!strcmp(info.value.enumerated.name, "speechR"));
    CHECK(!first.dsp_init_lock.held && !second.dsp_init_lock.held);

    val.value.enumerated.item[0] = 3;
    CHECK(tfa98xx_set_profile_ctl(&lctl, &val) == -EINVAL);
    val.value.enumerated.item[0] = UINT_MAX;
    CHECK(tfa98xx_set_profile_ctl(&lctl, &val) == -EINVAL);
    CHECK(!first.dsp_init_lock.held && first.profile_ctl == 2 && first.vstep_ctl == 2);

    /* Only a fully running route can do a live hardware transaction. */
    for (unsigned int bits = 0; bits < 32; bits++) {
        first.profile_ctl = 0; first.profile_current = 0; first.vstep_ctl = 1;
        first.starts = 0; map.reads = 0;
        defer_dsp_start = !!(bits & 1);
        first.desired_running = !!(bits & 2);
        first.monitor_status = !!(bits & 4);
        first.dsp_init = (bits & 8) ? TFA98XX_DSP_INIT_DONE : TFA98XX_DSP_INIT_PENDING;
        map.status = (bits & 16) ? TFA98XX_STATUSREG_SWS_MSK : 0;
        val.value.enumerated.item[0] = 1;
        CHECK(tfa98xx_set_profile_ctl(&lctl, &val) == 1);
        CHECK(first.starts == (bits == 30) && first.profile_ctl == 1);
        CHECK(map.reads == (bits == 14 || bits == 30));
        CHECK(!first.dsp_init_lock.held);
    }
    defer_dsp_start = false;
    first.desired_running = first.monitor_status = true;
    first.dsp_init = TFA98XX_DSP_INIT_DONE;
    map.status = TFA98XX_STATUSREG_SWS_MSK;
    val.value.enumerated.item[0] = 2;
    map.error = -EREMOTEIO;
    CHECK(tfa98xx_set_profile_ctl(&lctl, &val) == -EREMOTEIO);
    CHECK(first.profile_ctl == 1 && first.starts == 0);
    map.error = 0;
    first.start_error = -ENODATA;
    CHECK(tfa98xx_set_profile_ctl(&lctl, &val) == -ENODATA);
    CHECK(first.profile_ctl == 1 && first.starts == 1);
    CHECK(first.dsp_init == TFA98XX_DSP_INIT_NO_CALIBRATION && !first.dsp_init_lock.held);
    first.dsp_init = TFA98XX_DSP_INIT_DONE;
    first.start_error = -EIO;
    val.value.integer.value[0] = 0;
    CHECK(tfa98xx_set_vol_ctl(&lctl, &val) == -EIO);
    CHECK(first.vstep_ctl == 2 && first.starts == 2 && first.dsp_init == TFA98XX_DSP_INIT_FAIL);
    first.dsp_init = TFA98XX_DSP_INIT_DONE;
    first.start_error = 0;
    CHECK(tfa98xx_set_vol_ctl(&lctl, &val) == 1);
    CHECK(first.vstep_ctl == 3 && first.starts == 3 && first.requested_profile == 1 &&
          first.requested_step == 3 && !first.dsp_init_lock.held);
    puts("PASS: actual ALSA UAPI enum/volume, 32 live-route cases, staged profiles, isolation and error rollback");
    return 0;
}
"""

callbacks = [
    callback(dsp, "tfa98xx_is_amp_running"),
    *(callback(c, name) for name in (
        "tfa98xx_apply_live_control", "tfa98xx_get_profile_ctl",
        "tfa98xx_set_profile_ctl", "tfa98xx_info_profile_ctl", "tfa98xx_get_vol_ctl",
        "tfa98xx_set_vol_ctl", "tfa98xx_info_vol_ctl")),
]
with tempfile.TemporaryDirectory(prefix="mipad2-tfa-control-") as tmp:
    source, test = Path(tmp) / "test.c", Path(tmp) / "test"
    source.write_text("\n".join([preamble, defs, spec.group(), fixture, *callbacks, oracle]))
    subprocess.run(shlex.split(os.getenv("CC", "cc")) + [
        "-std=gnu11", "-Wall", "-Wextra", "-Werror",
        "-I", str(root / "include/uapi/sound"), "-I", str(codec),
        "-fsanitize=undefined", "-fsanitize-undefined-trap-on-error",
        str(source), "-o", str(test),
    ], check=True)
    subprocess.run([str(test)], check=True)
