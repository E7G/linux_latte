#!/usr/bin/env python3
"""Execute the real TFA989x set_fmt callback with mocked regmap fault injection.

No hardware access. Does not establish clock waveforms or audible output.
Requires Python 3 and a C compiler (CC, default clang).
"""
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / "sound/soc/codecs/tfa989x.c").read_text()
start = source.index("static int tfa989x_set_dai_fmt(")
brace = source.index("{", start)
depth = 1
end = brace + 1
while depth:
    depth += (source[end] == "{") - (source[end] == "}")
    end += 1
callback = source[start:end]

# Resolve constants from this checkout, rather than duplicating DAIFMT values.
texts = [source, (ROOT / "include/sound/soc-dai.h").read_text(),
         (ROOT / "include/uapi/sound/asoc.h").read_text()]
macros = {}
for text in texts:
    for line in text.splitlines():
        match = re.match(r"#define\s+(\w+)\s+(.+)", line)
        if match:
            macros[match[1]] = re.split(r"/\*|//", match[2])[0].strip()

needed = set(re.findall(r"\b(?:SND_SOC_DAIFMT|TFA98XX|TFA989X)_\w+", callback))
needed.update("SND_SOC_DAIFMT_" + suffix for suffix in (
    "DSP_A", "DSP_B", "NB_IF", "IB_NF", "IB_IF", "CBS_CFM", "CBM_CFS"))
defines = []
seen = set()


def define(name):
    if name in seen:
        return
    seen.add(name)
    value = macros[name]
    for dependency in re.findall(r"\b[A-Z][A-Z_0-9]+\b", value):
        define(dependency)
    defines.append(f"#define {name} {value}\n")


for name in sorted(needed):
    define(name)

mock = r"""
#include <assert.h>
#include <errno.h>
#include <stdio.h>
struct regmap { unsigned int value, writes, reads; int read_ret, write_ret; };
struct snd_soc_component { struct regmap *regmap; void *dev; };
struct snd_soc_dai { struct snd_soc_component *component; };
#define pr_debug(...) ((void)0)
#define pr_err(...) ((void)0)
#define dev_dbg(...) ((void)0)
static int regmap_read(struct regmap *map, unsigned int reg, unsigned int *val)
{
    assert(reg == TFA989X_I2SREG);
    map->reads++;
    if (map->read_ret) return map->read_ret;
    *val = map->value;
    return 0;
}
static int regmap_write(struct regmap *map, unsigned int reg, unsigned int val)
{
    assert(reg == TFA989X_I2SREG);
    map->writes++;
    if (map->write_ret) return map->write_ret;
    map->value = val;
    return 0;
}
"""
harness = r"""
int main(void)
{
    const unsigned int base = SND_SOC_DAIFMT_CBS_CFS | SND_SOC_DAIFMT_NB_NF;
    const unsigned int formats[] = {
        SND_SOC_DAIFMT_I2S, SND_SOC_DAIFMT_RIGHT_J, SND_SOC_DAIFMT_LEFT_J
    };
    const unsigned int invalid[] = {
        SND_SOC_DAIFMT_CBM_CFM | SND_SOC_DAIFMT_I2S,
        SND_SOC_DAIFMT_CBS_CFM | SND_SOC_DAIFMT_I2S,
        SND_SOC_DAIFMT_CBM_CFS | SND_SOC_DAIFMT_I2S,
        SND_SOC_DAIFMT_I2S,
        base | SND_SOC_DAIFMT_NB_IF | SND_SOC_DAIFMT_I2S,
        base | SND_SOC_DAIFMT_IB_NF | SND_SOC_DAIFMT_I2S,
        base | SND_SOC_DAIFMT_IB_IF | SND_SOC_DAIFMT_I2S,
        base | SND_SOC_DAIFMT_DSP_A,
        base | SND_SOC_DAIFMT_DSP_B,
        base,
        base | SND_SOC_DAIFMT_FORMAT_MASK
    };
    struct regmap map;
    struct snd_soc_component component = { .regmap = &map };
    struct snd_soc_dai dai = { .component = &component };
    unsigned int i, input, expected, cases = 0;
    int errors[] = { -EIO, -ETIMEDOUT, -EREMOTEIO };

    for (i = 0; i < sizeof(invalid)/sizeof(invalid[0]); i++) {
        map = (struct regmap){ .value = 0x884b };
        assert(tfa989x_set_dai_fmt(&dai, invalid[i]) == -EINVAL);
        assert(map.reads == 0 && map.writes == 0 && map.value == 0x884b);
        cases++;
    }
    for (i = 0; i < sizeof(formats)/sizeof(formats[0]); i++) {
        /* Exercise both OEM channels and a non-default upper-bit pattern. */
        const unsigned int inputs[] = { 0x880b, 0x884b, 0xa5ff };
        unsigned int j;
        for (j = 0; j < sizeof(inputs)/sizeof(inputs[0]); j++) {
            input = inputs[j];
            expected = input;
            if (formats[i] == SND_SOC_DAIFMT_RIGHT_J)
                expected = (input & ~TFA98XX_FORMAT_MASK) | TFA98XX_FORMAT_LSB;
            if (formats[i] == SND_SOC_DAIFMT_LEFT_J)
                expected = (input & ~TFA98XX_FORMAT_MASK) | TFA98XX_FORMAT_MSB;
            map = (struct regmap){ .value = input };
            assert(tfa989x_set_dai_fmt(&dai, base | formats[i]) == 0);
            assert(map.value == expected && map.reads == 1 && map.writes == 1);
            cases++;
        }
        for (j = 0; j < sizeof(errors)/sizeof(errors[0]); j++) {
            map = (struct regmap){ .value = 0x884b, .read_ret = errors[j] };
            assert(tfa989x_set_dai_fmt(&dai, base | formats[i]) == errors[j]);
            assert(map.value == 0x884b && map.reads == 1 && map.writes == 0);
            cases++;
            map = (struct regmap){ .value = 0x884b, .write_ret = errors[j] };
            assert(tfa989x_set_dai_fmt(&dai, base | formats[i]) == errors[j]);
            assert(map.value == 0x884b && map.reads == 1 && map.writes == 1);
            cases++;
        }
    }
    printf("PASS: %u real-callback format/error/preservation cases\n", cases);
    return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="mipad2-tfa-format-") as temp:
    cfile = Path(temp) / "test.c"
    binary = Path(temp) / "test"
    cfile.write_text("".join(defines) + mock + callback + harness)
    subprocess.run(shlex.split(os.environ.get("CC", "clang")) + [
        "-std=c11", "-Wall", "-Wextra", "-Werror", str(cfile), "-o", str(binary)
    ], check=True)
    subprocess.run([str(binary)], check=True)
