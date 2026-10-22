#!/usr/bin/env python3
"""Compile the real board late-probe callback against a DAPM ordering model.

No hardware I/O. Models route sampling before link init, control creation,
same-value puts, and error propagation; hardware/acoustic tests stay separate.
"""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
source = (root / 'sound/soc/intel/boards/cht_bsw_rt5659.c').read_text()
start = source.index('static int cht_late_probe(')
brace = source.index('{', start)
depth, end = 1, brace + 1
while depth:
    depth += (source[end] == '{') - (source[end] == '}')
    end += 1
callback = source[start:end]
link_init = source[source.index('static int cht_audio_init('):source.index('static int cht_codec_fixup(')]
assert 'RT5659_DIG_INF23_DATA' not in link_init, 'raw mux write desynchronizes existing DAPM paths'
assert '.late_probe = cht_late_probe' in source

mock = r'''
#include <assert.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#define GFP_KERNEL 0
struct snd_ctl_elem_value { struct { struct { unsigned int item[2]; } enumerated; } value; };
struct snd_soc_card;
struct snd_kcontrol { struct snd_soc_card *card; };
struct snd_soc_card {
    unsigned int hw, path, control, widget_calls, puts;
    int widgets_ret, put_ret;
    int missing_control, created;
    struct snd_kcontrol mux;
};
static int alloc_fail;
static void *kzalloc(size_t bytes, int flags)
{ (void)flags; return alloc_fail ? NULL : calloc(1, bytes); }
static void kfree(void *p) { free(p); }
static int snd_soc_dapm_new_widgets(struct snd_soc_card *c)
{
    c->widget_calls++;
    if (c->widgets_ret) return c->widgets_ret;
    if (!c->created) { c->control = c->hw; c->created = 1; }
    return 0;
}
static struct snd_kcontrol *snd_soc_card_get_kcontrol(struct snd_soc_card *c, const char *name)
{
    assert(!strcmp(name, "IF2 ADC Mux") && c->created);
    c->mux.card = c;
    return c->missing_control ? NULL : &c->mux;
}
static int snd_soc_dapm_put_enum_double(struct snd_kcontrol *k, struct snd_ctl_elem_value *v)
{
    struct snd_soc_card *c = k->card;
    unsigned int value = v->value.enumerated.item[0];
    int change = c->control != value || c->hw != value;
    c->puts++;
    if (c->put_ret) return c->put_ret;
    assert(value < 4);
    if (change) { c->hw = value; c->control = value; c->path = value; }
    return change;
}
'''
tests = r'''
int main(void)
{
    unsigned int initial;
    int errors[] = { -EIO, -ETIMEDOUT, -EREMOTEIO };
    struct snd_soc_card c;
    struct snd_ctl_elem_value v = { .value.enumerated.item = {2, 0} };

    /* Old order: routes sample reset=1; raw link-init write makes hw=2;
     * new control samples 2, so an ordinary same-value put cannot fix paths.
     */
    c = (struct snd_soc_card){ .hw=1, .path=1 };
    c.hw = 2;
    assert(!snd_soc_dapm_new_widgets(&c));
    assert(snd_soc_card_get_kcontrol(&c, "IF2 ADC Mux"));
    assert(!snd_soc_dapm_put_enum_double(&c.mux, &v));
    assert(c.hw == 2 && c.control == 2 && c.path == 1);

    /* New order keeps hw/path consistent until the real late-probe put. */
    for (initial=0; initial<4; initial++) {
        c = (struct snd_soc_card){ .hw=initial, .path=initial };
        assert(!cht_late_probe(&c));
        assert(c.hw == 2 && c.control == 2 && c.path == 2);
        assert(c.widget_calls == 1 && c.puts == 1);
        assert(!cht_late_probe(&c)); /* already-correct warm registration */
        assert(c.hw == 2 && c.control == 2 && c.path == 2);
    }
    for (unsigned int i=0; i<sizeof(errors)/sizeof(errors[0]); i++) {
        c = (struct snd_soc_card){ .hw=1, .path=1, .widgets_ret=errors[i] };
        assert(cht_late_probe(&c) == errors[i] && !c.puts && c.path == 1);
        c = (struct snd_soc_card){ .hw=1, .path=1, .put_ret=errors[i] };
        assert(cht_late_probe(&c) == errors[i] && c.path == 1);
    }
    c = (struct snd_soc_card){ .hw=1, .path=1, .missing_control=1 };
    assert(cht_late_probe(&c) == -ENODEV && !c.puts);
    c = (struct snd_soc_card){ .hw=1, .path=1 };
    alloc_fail = 1;
    assert(cht_late_probe(&c) == -ENOMEM && !c.puts);
    puts("PASS actual late-probe callback: DAPM cold/warm ordering and fault propagation; no hardware claim");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='mipad2-dapm-init-') as temp:
    cfile, binary = Path(temp)/'test.c', Path(temp)/'test'
    cfile.write_text(mock + callback + tests)
    subprocess.run(shlex.split(os.environ.get('CC', 'clang')) +
                   ['-std=c11','-Wall','-Wextra','-Werror',str(cfile),'-o',str(binary)],check=True)
    subprocess.run([str(binary)],check=True)
