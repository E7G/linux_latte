#!/usr/bin/env python3
"""Run actual RT5659 component callbacks against a mocked persistent regmap.

Tests sound-card rebind after hardware reset and propagating sync failures.
No hardware access; this does not establish acoustic output.
"""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / "sound/soc/codecs/rt5659.c").read_text()


def callback(declaration):
    start = source.index(declaration)
    brace = source.index("{", start)
    depth, end = 1, brace + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


mock = r"""
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
#include <stdio.h>
#define RT5659_RESET 0
#define RT5659_JD_HDA_HEADER 123
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define dev_err(...) ((void)0)
struct regmap {
    unsigned int cached_aif2, hw_aif2, cached_pll, hw_pll;
    unsigned int syncs, resets, dirty_calls, controls;
    bool dirty, cache_only;
    int sync_ret, reset_ret, controls_ret;
};
struct snd_soc_component;
struct rt5659_priv {
    struct regmap *regmap;
    struct snd_soc_component *component;
    struct { int jd_src; } pdata;
};
struct snd_soc_dapm_context { struct regmap *map; };
struct snd_soc_component {
    struct rt5659_priv *priv;
    struct snd_soc_dapm_context dapm;
    void *dev;
};
static const int rt5659_particular_dapm_widgets[] = { 1 };
static struct rt5659_priv *snd_soc_component_get_drvdata(struct snd_soc_component *c)
{ return c->priv; }
static struct snd_soc_dapm_context *snd_soc_component_get_dapm(struct snd_soc_component *c)
{ return &c->dapm; }
static void regcache_mark_dirty(struct regmap *map)
{ map->dirty = true; map->dirty_calls++; }
static void regcache_cache_only(struct regmap *map, bool only)
{ map->cache_only = only; }
static int regcache_sync(struct regmap *map)
{
    map->syncs++;
    if (map->sync_ret) return map->sync_ret;
    if (map->dirty) {
        assert(!map->cache_only);
        map->hw_aif2 = map->cached_aif2;
        map->hw_pll = map->cached_pll;
        map->dirty = false;
    }
    return 0;
}
static int regmap_write(struct regmap *map, unsigned int reg, unsigned int value)
{
    assert(reg == RT5659_RESET && value == 0);
    map->resets++;
    if (map->reset_ret) return map->reset_ret;
    map->hw_aif2 = 0x8000;
    map->hw_pll = 0;
    return 0;
}
static int snd_soc_dapm_new_controls(struct snd_soc_dapm_context *dapm,
                                    const int *widgets, unsigned int count)
{
    assert(widgets == rt5659_particular_dapm_widgets && count == 1);
    dapm->map->controls++;
    return dapm->map->controls_ret;
}
"""
harness = r"""
int main(void)
{
    struct regmap map = { .cached_aif2 = 0, .hw_aif2 = 0,
                         .cached_pll = 0x0f03, .hw_pll = 0x0f03 };
    struct rt5659_priv priv = { .regmap = &map };
    struct snd_soc_component c = { .priv = &priv, .dapm = { .map = &map } };
    unsigned int before;
    int errors[] = { -EIO, -ETIMEDOUT, -EREMOTEIO };
    unsigned int i;

    assert(rt5659_probe(&c) == 0 && priv.component == &c);
    assert(map.syncs == 1 && map.controls == 1);
    rt5659_remove(&c);
    assert(map.resets == 1 && map.dirty && map.dirty_calls == 1);
    assert(map.hw_aif2 == 0x8000 && map.cached_aif2 == 0);
    assert(map.hw_pll == 0 && map.cached_pll == 0x0f03);
    assert(rt5659_probe(&c) == 0);
    assert(map.hw_aif2 == map.cached_aif2 && map.hw_pll == map.cached_pll);
    assert(!map.dirty);

    for (i = 0; i < sizeof(errors)/sizeof(errors[0]); i++) {
        rt5659_remove(&c);
        map.sync_ret = errors[i];
        before = map.controls;
        assert(rt5659_probe(&c) == errors[i]);
        assert(map.controls == before && map.dirty);
        map.sync_ret = 0;
        assert(rt5659_probe(&c) == 0 && !map.dirty);

        map.reset_ret = errors[i];
        rt5659_remove(&c);
        assert(map.dirty); /* Partial/failed reset must not leave cache clean. */
        map.reset_ret = 0;
        assert(rt5659_probe(&c) == 0 && !map.dirty);
    }
    priv.pdata.jd_src = RT5659_JD_HDA_HEADER;
    before = map.controls;
    rt5659_remove(&c);
    assert(rt5659_probe(&c) == 0 && map.controls == before && !map.dirty);
    priv.pdata.jd_src = 0;
    map.controls_ret = -ENOMEM;
    assert(rt5659_probe(&c) == -ENOMEM);
    map.controls_ret = 0;

    assert(rt5659_suspend(&c) == 0 && map.cache_only && map.dirty);
    map.hw_pll = 0;
    assert(rt5659_resume(&c) == 0 && !map.cache_only && !map.dirty);
    assert(map.hw_pll == map.cached_pll);
    for (i = 0; i < sizeof(errors)/sizeof(errors[0]); i++) {
        assert(rt5659_suspend(&c) == 0);
        map.sync_ret = errors[i];
        assert(rt5659_resume(&c) == errors[i] && !map.cache_only && map.dirty);
        map.sync_ret = 0;
        assert(rt5659_resume(&c) == 0 && !map.dirty);
    }
    puts("PASS: actual RT5659 probe/remove/suspend/resume callbacks; reset/rebind, sync/reset/control errors");
    return 0;
}
"""
callbacks = "\n".join(callback(decl) for decl in (
    "static int rt5659_probe(", "static void rt5659_remove(",
    "static int rt5659_suspend(", "static int rt5659_resume("))
with tempfile.TemporaryDirectory(prefix="mipad2-rt5659-rebind-") as temp:
    cfile = Path(temp) / "test.c"
    binary = Path(temp) / "test"
    cfile.write_text(mock + callbacks + harness)
    subprocess.run(shlex.split(os.environ.get("CC", "clang")) + [
        "-std=c11", "-Wall", "-Wextra", "-Werror", str(cfile), "-o", str(binary)
    ], check=True)
    subprocess.run([str(binary)], check=True)
