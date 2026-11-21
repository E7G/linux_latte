#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Exercise real RT5659 jack workers against injected register I/O errors."""

import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile


def function(text, name):
    start = re.search(rf"^static \w+ {name}\(", text, re.M)
    if not start:
        raise RuntimeError(f"missing {name}")
    end = text.index("\n}", start.start()) + 2
    return text[start.start():end]


root = Path(__file__).resolve().parents[2]
codec = (root / "sound/soc/codecs/rt5659.c").read_text()
functions = [
    "rt5659_headset_detect", "rt5659_button_detect",
    "rt5659_jack_detect_work", "rt5659_jack_detect_intel_hd_header",
]

mock = r"""
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>

#define ARRAY_SIZE(array) (sizeof(array) / sizeof((array)[0]))
#define container_of(ptr, type, member) ((type *)((char *)(ptr) - offsetof(type, member)))
#define dev_dbg(...) ((void)0)
#define dev_err(...) ((void)0)
#define dev_err_ratelimited(...) ((void)0)
#define SND_JACK_HEADPHONE 1
#define SND_JACK_MICROPHONE 2
#define SND_JACK_HEADSET (SND_JACK_HEADPHONE | SND_JACK_MICROPHONE)
#define SND_JACK_BTN_0 4
#define SND_JACK_BTN_1 8
#define SND_JACK_BTN_2 16
#define SND_JACK_BTN_3 32

enum {
	RT5659_PWR_ANLG_1, RT5659_EJD_CTRL_1, RT5659_EJD_CTRL_2,
	RT5659_INT_ST_1, RT5659_4BTN_IL_CMD_1, RT5659_GPIO_STA,
	RT5659_IRQ_CTRL_1, RT5659_IRQ_CTRL_2, REGISTER_COUNT,
};
enum { RT5659_PWR_VREF2 = 0x400, RT5659_PWR_MB = 0x100, RT5659_PWR_FV2 = 0x8 };

struct work_struct { int unused; };
struct regmap {
	unsigned int reg[REGISTER_COUNT];
	unsigned int next_classification;
	int transfers;
	int fail_on;
	int button_reads;
	int button_acks;
};
struct snd_soc_dapm_context { bool mic_det; };
struct snd_soc_component {
	struct rt5659_priv *priv;
	struct snd_soc_dapm_context dapm;
};
struct snd_soc_jack { int count; int status; };
struct rt5659_priv {
	struct { struct work_struct work; } jack_detect_work;
	struct snd_soc_component *component;
	struct regmap *regmap;
	struct snd_soc_jack *hs_jack;
	int jack_type;
	bool hda_hp_plugged, hda_mic_plugged;
	int button_irq_state;
};

static int fault(struct regmap *map)
{
	return ++map->transfers == map->fail_on ? -EIO : 0;
}

static int regmap_read(struct regmap *map, unsigned int reg, unsigned int *val)
{
	int ret = fault(map);

	if (reg == RT5659_4BTN_IL_CMD_1)
		map->button_reads++;
	if (ret)
		return ret;
	*val = reg == RT5659_EJD_CTRL_2 ? map->next_classification : map->reg[reg];
	return 0;
}

static int regmap_write(struct regmap *map, unsigned int reg, unsigned int val)
{
	int ret = fault(map);

	if (ret)
		return ret;
	if (reg == RT5659_4BTN_IL_CMD_1)
		map->button_acks++;
	map->reg[reg] = val;
	return 0;
}

static int regmap_update_bits(struct regmap *map, unsigned int reg,
			      unsigned int mask, unsigned int val)
{
	int ret = fault(map);

	if (ret)
		return ret;
	map->reg[reg] = (map->reg[reg] & ~mask) | (val & mask);
	return 0;
}

/* The old unsigned ASoC interface passes through a negative errno. */
static unsigned int snd_soc_component_read(struct snd_soc_component *component,
					   unsigned int reg)
{
	unsigned int val;
	int ret = regmap_read(component->priv->regmap, reg, &val);

	return ret < 0 ? (unsigned int)ret : val;
}

#define snd_soc_component_get_drvdata(component) ((component)->priv)
#define snd_soc_component_to_dapm(component) (&(component)->dapm)
#define snd_soc_component_write(component, reg, val) \
	regmap_write((component)->priv->regmap, reg, val)
#define snd_soc_component_update_bits(component, reg, mask, val) \
	regmap_update_bits((component)->priv->regmap, reg, mask, val)

static int snd_soc_dapm_force_enable_pin(struct snd_soc_dapm_context *dapm, const char *pin)
{
	dapm->mic_det = true;
	return 0;
}

static int snd_soc_dapm_disable_pin(struct snd_soc_dapm_context *dapm, const char *pin)
{
	dapm->mic_det = false;
	return 0;
}

static int snd_soc_dapm_sync(struct snd_soc_dapm_context *dapm) { return 0; }
static void msleep(unsigned int delay) {}

static void rt5659_enable_push_button_irq(struct snd_soc_component *component, bool enable)
{
	component->priv->button_irq_state = enable;
}

static void snd_soc_jack_report(struct snd_soc_jack *jack, int report, int mask)
{
	jack->count++;
	jack->status = (jack->status & ~mask) | (report & mask);
}
"""

cases = r"""
int main(void)
{
	struct regmap map;
	struct snd_soc_component component;
	struct snd_soc_jack jack;
	struct rt5659_priv priv;
	struct work_struct *work = &priv.jack_detect_work.work;

#define RESET(type) do { \
	map = (struct regmap) { .reg = {[RT5659_PWR_ANLG_1] = 0x10}, \
				.next_classification = 2 }; \
	jack = (struct snd_soc_jack) { .status = (type) }; \
	component = (struct snd_soc_component) { .priv = &priv }; \
	priv = (struct rt5659_priv) { .component = &component, .regmap = &map, \
				    .hs_jack = &jack, .jack_type = (type) }; \
} while (0)

	RESET(SND_JACK_HEADSET);
	map.fail_on = 1;
	rt5659_jack_detect_work(work);
	assert(jack.count == 0 && priv.jack_type == SND_JACK_HEADSET);

	/* Presence, power snapshot, setup, sample, and analogue restore. */
	for (int fail = 1; fail <= 9; fail++) {
		RESET(0);
		map.fail_on = fail;
		rt5659_jack_detect_work(work);
		assert(jack.count == 0 && priv.jack_type == 0);
		assert(!component.dapm.mic_det && !priv.button_irq_state);
		if (fail < 9)
			assert(map.reg[RT5659_PWR_ANLG_1] == 0x10);
	}

	RESET(0);
	rt5659_jack_detect_work(work);
	assert(jack.count == 1 && jack.status == SND_JACK_HEADPHONE);
	assert(!component.dapm.mic_det && map.reg[RT5659_PWR_ANLG_1] == 0x10);
	map.reg[RT5659_4BTN_IL_CMD_1] = 0x8000;
	rt5659_jack_detect_work(work);
	assert(jack.count == 1 && map.button_reads == 0);

	RESET(0);
	map.next_classification = 1;
	rt5659_jack_detect_work(work);
	assert(jack.status == SND_JACK_HEADSET && priv.button_irq_state);

	for (int fail = 2; fail <= 3; fail++) {
		RESET(SND_JACK_HEADSET);
		map.reg[RT5659_4BTN_IL_CMD_1] = 0x8200;
		map.fail_on = fail;
		rt5659_jack_detect_work(work);
		assert(!jack.count && !map.button_acks);
	}

	const unsigned int keys[][3] = {
		{0x8000, 0x4000, 0x2000}, {0x1000, 0x0800, 0x0400},
		{0x0200, 0x0100, 0x0080}, {0x0040, 0x0020, 0x0010},
	};

	RESET(SND_JACK_HEADSET);
	for (size_t button = 0; button < ARRAY_SIZE(keys); button++) {
		for (size_t variant = 0; variant < ARRAY_SIZE(keys[button]); variant++) {
			map.reg[RT5659_4BTN_IL_CMD_1] = keys[button][variant];
			rt5659_jack_detect_work(work);
			assert(jack.status == (SND_JACK_HEADSET | (SND_JACK_BTN_0 << button)));
		}
	}
	assert(map.button_acks == 12);
	map.reg[RT5659_4BTN_IL_CMD_1] = 0;
	rt5659_jack_detect_work(work);
	assert(jack.status == SND_JACK_HEADSET);
	map.reg[RT5659_INT_ST_1] = 0x80;
	rt5659_jack_detect_work(work);
	assert(jack.status == 0 && priv.jack_type == 0 && !priv.button_irq_state);

	RESET(0);
	map.fail_on = 1;
	map.reg[RT5659_4BTN_IL_CMD_1] = 0x2000;
	rt5659_jack_detect_intel_hd_header(work);
	assert(jack.count == 1 && jack.status == SND_JACK_MICROPHONE);
	assert(!priv.hda_hp_plugged && priv.hda_mic_plugged);

	for (int fail = 3; fail <= 4; fail++) {
		RESET(0);
		map.fail_on = fail;
		map.reg[RT5659_4BTN_IL_CMD_1] = 0x2000;
		rt5659_jack_detect_intel_hd_header(work);
		assert(jack.count == 1 && jack.status == SND_JACK_HEADPHONE);
		assert(priv.hda_hp_plugged && !priv.hda_mic_plugged && !map.button_acks);
	}
}
"""

with tempfile.TemporaryDirectory(prefix="mipad2-rt5659-jack-io-") as tmp:
    source = Path(tmp) / "fixture.c"
    binary = Path(tmp) / "fixture"
    source.write_text("\n".join([mock, *(function(codec, name) for name in functions), cases]))
    cc = shlex.split(os.environ.get("CC", "cc"))
    subprocess.run([*cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
                    "-Wno-unused-function", "-Wno-unused-parameter",
                    str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
print("PASS: RT5659 presence, accessory classification, button and HDA I/O failures")
