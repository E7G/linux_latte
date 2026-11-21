#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Exercise the RT5659 jack work gate and detach ordering without hardware."""

from pathlib import Path
import os
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
CODEC = ROOT / "sound/soc/codecs/rt5659.c"
BOARD = ROOT / "sound/soc/intel/boards/cht_bsw_rt5659.c"


def function(text, name, optional=False):
    start = re.search(rf"^(?:static )?\w+ {name}\(", text, re.M)
    if not start and optional:
        return ""
    if not start:
        raise RuntimeError(f"missing {name}")
    end = text.index("\n}", start.start()) + 2
    return text[start.start():end]


source = CODEC.read_text()
board = BOARD.read_text()
irq = function(source, "rt5659_irq")
set_jack = function(source, "rt5659_set_jack_detect")
has_jack = function(source, "rt5659_has_jack_detect", optional=True)

# Run the real probe gate between the mode-specific work initialization
# and IRQ registration. Neither the regmap nor the IRQ controller is mocked.
probe = function(source, "rt5659_i2c_probe")
marker = "if (rt5659_has_jack_detect(rt5659))\n\t\tdisable_delayed_work"
begin = probe.find(marker)
if begin >= 0:
    end = probe.index(";", begin) + 1
    gate = probe[begin:end]
else:
    gate = ""

mock = r"""
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>

enum { RT5659_JD_NULL, RT5659_JD3, RT5659_JD_HDA_HEADER };
enum { IRQ_HANDLED = 1 };
typedef int irqreturn_t;
struct snd_soc_jack { int id; };
struct delayed_work {
	int disabled;
	int pending;
	int reports;
	struct { int entry; void *func; } work;
};
struct rt5659_priv {
	struct { int jd_src; } pdata;
	struct delayed_work jack_detect_work;
	struct snd_soc_jack *hs_jack;
	int jack_type;
	bool hda_hp_plugged, hda_mic_plugged;
};
struct snd_soc_component { struct rt5659_priv *priv; };

#define snd_soc_component_get_drvdata(dev) ((dev)->priv)
#define system_power_efficient_wq 1
#define msecs_to_jiffies(ms) (ms)
#define list_empty(entry) true
#define printk(...) ((void)0)

static irqreturn_t rt5659_irq(int irq, void *data);
static struct rt5659_priv *device;
static struct snd_soc_jack *expected_at_drain;

static bool queue_delayed_work(int queue, struct delayed_work *work, int delay)
{
	assert(queue == 1 && delay == 250);
	if (work->disabled || work->pending)
		return false;
	work->pending = 1;
	work->reports++;
	return true;
}

static void disable_delayed_work(struct delayed_work *work)
{
	work->disabled++;
	work->pending = 0;
}

static void disable_delayed_work_sync(struct delayed_work *work)
{
	assert(device->hs_jack == expected_at_drain);
	disable_delayed_work(work);
	rt5659_irq(0, device);
	assert(!work->pending);
}

static void enable_delayed_work(struct delayed_work *work)
{
	assert(work->disabled == 1);
	work->disabled--;
}
"""

cases = r"""
int main(void)
{
	struct snd_soc_jack a = {1}, b = {2};
	const int modes[] = {RT5659_JD3, RT5659_JD_HDA_HEADER, RT5659_JD_NULL, 99};

	for (size_t i = 0; i < sizeof(modes) / sizeof(modes[0]); i++) {
		struct rt5659_priv state = { .pdata.jd_src = modes[i] };
		struct snd_soc_component component = { .priv = &state };
		struct delayed_work *work = &state.jack_detect_work;
		bool supported = modes[i] == RT5659_JD3 || modes[i] == RT5659_JD_HDA_HEADER;

		device = &state;
		init_gate(device);
		assert(rt5659_irq(0, device) == IRQ_HANDLED && !work->pending);
		assert(!rt5659_set_jack_detect(&component, &a));
		if (!supported) {
			assert(!state.hs_jack && !work->reports);
			continue;
		}
		assert(state.hs_jack == &a && !work->disabled && work->pending);
		assert(work->reports == 1);
		assert(!rt5659_set_jack_detect(&component, &a) && work->reports == 1);

		state.jack_type = 9;
		state.hda_hp_plugged = state.hda_mic_plugged = true;
		expected_at_drain = &a;
		assert(!rt5659_set_jack_detect(&component, &b));
		assert(state.hs_jack == &b && !work->disabled && work->pending);
		assert(!state.jack_type && !state.hda_hp_plugged && !state.hda_mic_plugged);

		expected_at_drain = &b;
		assert(!rt5659_set_jack_detect(&component, NULL));
		assert(!state.hs_jack && work->disabled == 1 && !work->pending);
		rt5659_irq(0, device);
		assert(work->reports == 2);
		assert(!rt5659_set_jack_detect(&component, NULL) && work->disabled == 1);
		assert(!rt5659_set_jack_detect(&component, &a));
		assert(state.hs_jack == &a && work->reports == 3 && work->pending);
	}
}
"""

init = "static void init_gate(struct rt5659_priv *rt5659){" + gate + "}"
with tempfile.TemporaryDirectory(prefix="mipad2-rt5659-jack-") as tmp:
    test = Path(tmp) / "fixture.c"
    binary = Path(tmp) / "fixture"
    test.write_text("\n".join((mock, has_jack, irq, set_jack, init, cases)))
    command = shlex.split(os.environ.get("CC", "cc"))
    subprocess.run([*command, "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-Wno-unused-parameter", "-Wno-unused-function",
                    str(test), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)

# Ensure the machine removes the callback before its notifier and the
# codec drains the work before writing its reset register.
exit_cb = function(board, "cht_codec_exit")
if not (exit_cb.index("rt5659_set_jack_detect(component, NULL);")
        < exit_cb.index("snd_soc_jack_notifier_unregister(")):
    raise RuntimeError("card detached the notifier before draining reports")
link = ".exit = cht_codec_exit,"
remove = function(source, "rt5659_remove")
if link not in board or not (remove.index("rt5659_set_jack_detect(component, NULL);")
                              < remove.index("RT5659_RESET")):
    raise RuntimeError("jack teardown missing from link or codec")
print("PASS: RT5659 jack mode, pre-bind IRQ, replacement, teardown and rebind")
