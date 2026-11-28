#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Compile the live link template and verify per-probe RT5659 link identities."""
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
source = (root / "sound/soc/intel/boards/cht_bsw_rt5659.c").read_text()


def one(pattern):
    matches = re.findall(pattern, source, re.M | re.S)
    if len(matches) != 1:
        raise SystemExit(f"expected one production fragment: {pattern}")
    return matches[0]


templates = one(r"^SND_SOC_DAILINK_DEF\(dummy,.*?^\};\n\n^enum \{.*?^\};\n\n"
                r"^static struct snd_soc_dai_link cht_dailink\[\] = \{.*?^\};")
configure = one(r"^static void cht_rt5659_configure_links\([^;{}]*?^\{\n.*?^\}")
probe = one(r"^static int snd_cht_mc_probe\([^;{}]*?^\{\n.*?^\}")
if not (0 <= probe.find("cht_rt5659_find_codec(") <
        probe.find("cht_rt5659_configure_links(") <
        probe.find("devm_snd_soc_register_card(")):
    raise SystemExit("the live codec must be resolved and linked before card registration")

shim = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>

struct snd_soc_dai_link_component { const char *name, *dai_name; };
struct snd_soc_pcm_stream {
    unsigned int formats, rate_min, rate_max, channels_min, channels_max, rates, sig_bits;
};
struct snd_soc_dai_link {
    const char *name, *stream_name;
    unsigned int id, nonatomic, dynamic, playback_only, no_pcm, ignore_suspend, ignore_pmdown_time;
    const void *init, *exit, *be_hw_params_fixup;
    const int *ops;
    struct snd_soc_dai_link_component *cpus, *codecs, *platforms;
    unsigned int num_cpus, num_codecs, num_platforms, dai_fmt, num_c2c_params;
    const struct snd_soc_pcm_stream *c2c_params;
};
struct snd_soc_card { struct snd_soc_dai_link *dai_link; int num_links; };
struct cht_mc_private {
    char codec_name[32];
    bool use_ssp0;
    struct snd_soc_dai_link_component ssp_cpu, ssp_codec, speaker_cpu, dsp_platform;
};

#define ARRAY_SIZE(a) (sizeof(a) / sizeof(*(a)))
#define DAILINK_COMP_ARRAY(...) __VA_ARGS__
#define SND_SOC_DAILINK_DEF(name, ...) static struct snd_soc_dai_link_component name[] = { __VA_ARGS__ }
#define COMP_DUMMY()
#define COMP_CPU(d) { .dai_name = d }
#define COMP_CODEC(n, d) { .name = n, .dai_name = d }
#define COMP_PLATFORM(n) { .name = n }
#define CHOOSE_LINK(_1, _2, _3, NAME, ...) NAME
#define LINK2(cpu, codec) LINK3(cpu, codec, no_platform)
#define LINK3(cpu, codec, platform) \
    .cpus = cpu, .num_cpus = ARRAY_SIZE(cpu), .codecs = codec, .num_codecs = ARRAY_SIZE(codec), \
    .platforms = platform, .num_platforms = ARRAY_SIZE(platform)
#define SND_SOC_DAILINK_REG(...) CHOOSE_LINK(__VA_ARGS__, LINK3, LINK2)(__VA_ARGS__)
#define for_each_card_prelinks(card, i, link) \
    for ((i) = 0; (i) < (card)->num_links && ((link) = &(card)->dai_link[i]); (i)++)

enum { MERR_DPCM_AUDIO, MERR_DPCM_DEEP_BUFFER };
enum { SNDRV_PCM_FMTBIT_S16_LE = 1, SNDRV_PCM_RATE_48000 = 1 };
enum { SND_SOC_DAIFMT_I2S = 1, SND_SOC_DAIFMT_NB_NF = 2, SND_SOC_DAIFMT_CBC_CFC = 4 };
static struct snd_soc_dai_link_component no_platform[0];
static const int cht_aif1_ops, cht_be_ssp2_ops;
#define cht_codec_init NULL
#define cht_codec_exit NULL
#define cht_codec_fixup NULL
"""

cases = r"""
int main(void)
{
    struct snd_soc_dai_link links1[ARRAY_SIZE(cht_dailink)], links2[ARRAY_SIZE(cht_dailink)];
    struct snd_soc_card a = { .dai_link = links1, .num_links = ARRAY_SIZE(links1) };
    struct snd_soc_card b = { .dai_link = links2, .num_links = ARRAY_SIZE(links2) };
    struct cht_mc_private a_priv = { .codec_name = "i2c-10EC5659:00", .use_ssp0 = true };
    struct cht_mc_private b_priv = { .codec_name = "i2c-10EC5659:01", .use_ssp0 = false };

    memcpy(links1, cht_dailink, sizeof(links1));
    memcpy(links2, cht_dailink, sizeof(links2));
    cht_rt5659_configure_links(&a, &a_priv, "custom-dsp");
    cht_rt5659_configure_links(&b, &b_priv, NULL);
    for (int i = 0; i < a.num_links; ++i) {
        if (i == CHT_LINK_AIF2_SPK) {
            assert(!links1[i].num_platforms && !links2[i].num_platforms);
            assert(links1[i].platforms == no_platform && links2[i].platforms == no_platform);
        } else {
            assert(links1[i].num_platforms == 1 && links2[i].num_platforms == 1);
            assert(links1[i].platforms == &a_priv.dsp_platform);
            assert(links2[i].platforms == &b_priv.dsp_platform);
            assert(!strcmp(links1[i].platforms->name, "custom-dsp"));
            assert(!strcmp(links2[i].platforms->name, "sst-mfld-platform"));
        }
    }
    assert(links1[CHT_LINK_SSP].codecs->name == a_priv.codec_name);
    assert(links1[CHT_LINK_AIF2_SPK].cpus->name == a_priv.codec_name);
    assert(links2[CHT_LINK_SSP].codecs->name == b_priv.codec_name);
    assert(links2[CHT_LINK_AIF2_SPK].cpus->name == b_priv.codec_name);
    assert(!strcmp(links1[CHT_LINK_SSP].cpus->dai_name, "ssp0-port"));
    assert(!strcmp(links2[CHT_LINK_SSP].cpus->dai_name, "ssp2-port"));
    assert(!strcmp(links1[CHT_LINK_SSP].codecs->dai_name, "rt5659-aif1"));
    assert(!strcmp(links2[CHT_LINK_AIF2_SPK].cpus->dai_name, "rt5659-aif2"));
    assert(links2[CHT_LINK_AIF2_SPK].num_codecs == 2);
    assert(!strcmp(links2[CHT_LINK_AIF2_SPK].codecs[0].name, "i2c-tfa9890:00"));
    assert(!strcmp(links2[CHT_LINK_AIF2_SPK].codecs[1].name, "i2c-tfa9890:01"));
    assert(links2[CHT_LINK_AIF2_SPK].num_c2c_params == 1);
    assert(!cht_dailink[CHT_LINK_SSP].codecs->name);
    assert(!cht_dailink[CHT_LINK_AIF2_SPK].cpus->name);
    assert(!strcmp(cht_dailink[CHT_LINK_SSP].cpus->dai_name, "ssp2-port"));
    puts("PASS: live RT5659 :00/:01 identities, SSP selection and platform-less AIF2 link");
    return 0;
}
"""

with tempfile.TemporaryDirectory(prefix="mipad2-rt5659-links-") as temp:
    test, exe = Path(temp) / "test.c", Path(temp) / "test"
    test.write_text("\n".join((shim, templates, configure, cases)))
    cc = shlex.split(os.environ.get("CC", "cc"))
    subprocess.run([*cc, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                    str(test), "-o", str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
