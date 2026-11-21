#!/usr/bin/env python3
"""Test the production TFA register guards and DSP start with a fake I2C bus."""

import hashlib
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import zlib

root = Path(__file__).resolve().parents[2]
codec = root / "sound/soc/codecs/tfa98xx-xiaomi"
dsp = (codec / "tfa_dsp.c").read_text()
i2c = (codec / "tfa98xx.c").read_text()
container = (codec / "tfa_container.h").read_text()


def function(source, name):
    match = re.search(r"^(?:static )?(?:int|bool) " + name + r"\(", source, re.M)
    if not match:
        raise RuntimeError(f"missing production function {name}")
    end = source.index("\n}", match.end()) + 2
    return source[match.start():end]


def descriptor(name):
    start = container.index(f"struct {name} {{")
    return container[start:container.index(";", container.index("}", start)) + 1]


if not re.search(r"\.writeable_reg\s*=\s*tfa98xx_writeable_reg,", i2c):
    raise RuntimeError("regmap does not enforce the production write guard")

preamble = r"""
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;
typedef uint16_t u16;
#include "tfa98xx-regs.h"

#define U16_MAX UINT16_MAX
#define GENMASK(h, l) (((2U << (h)) - 1) & ~((1U << (l)) - 1))
#define TFA98XX_DSP_INIT_RECOVER 9
#define TFA98XX_MAX_I2C_SIZE 252
#define CFSTABLE_TRIES 4
#define REV_TFA9890 0x80
#define pr_debug(...) ((void)0)
#define pr_warn(...) ((void)0)
#define pr_err(...) ((void)0)
#define dev_err_ratelimited(...) ((void)0)
#define dev_warn(...) ((void)0)
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "line %d: %s\n", __LINE__, #x); exit(1); } } while (0)

struct device { int unused; };
struct regmap { unsigned int status, mtp, shadow, error_reg; int error; };
struct i2c_client { struct device dev; };
struct profile { int vsteps; };
struct tfa98xx {
    struct regmap *regmap;
    struct i2c_client *i2c;
    struct snd_soc_component *component;
    struct profile *profiles;
    int rev, profile_count, profile_current, vstep_current, dsp_init;
    bool needs_full_init;
};
struct snd_soc_component { struct tfa98xx *data; };
static int coldboot, hw_cold, hw_pwdn, power_error, configure_error;
static int patch_calls, config_calls, unmute_calls, cleanup_calls, sends;
static int inject_stage, settle_calls;
static unsigned int reset_ops;
static int gate_off_error, reset_error, gate_on_error;
static unsigned int last_reg, last_mask, last_value;
static bool tfa98xx_writeable_reg(struct device *dev, unsigned int reg);
static struct tfa98xx *snd_soc_component_get_drvdata(struct snd_soc_component *comp)
{ return comp->data; }
static int i2c_master_send(struct i2c_client *i2c, const u8 *bytes, u8 count)
{ (void)i2c; (void)bytes; sends++; return count; }
static int regmap_read(struct regmap *map, unsigned int reg, unsigned int *out)
{
    if (map->error && map->error_reg == reg)
        return map->error;
    if (reg == TFA98XX_STATUSREG)
        *out = map->status;
    else if (reg == TFA98XX_MTP)
        *out = map->mtp;
    else {
        CHECK(reg == 0x84);
        *out = map->shadow;
    }
    return 0;
}
static int regmap_write_bits(struct regmap *map, unsigned int reg,
                             unsigned int mask, unsigned int val)
{
    (void)map;
    if (!tfa98xx_writeable_reg(NULL, reg))
        return -EACCES;
    last_reg = reg; last_mask = mask; last_value = val & mask;
    if (reg == TFA98XX_CURRENTSENSE4 &&
        mask == TFA98XX_CURRENTSENSE4_CTRL_CLKGATECFOFF) {
        reset_ops = reset_ops * 10 + (val ? 1 : 3);
        return val ? gate_off_error : gate_on_error;
    }
    if (reg == TFA98XX_CF_CONTROLS && mask == TFA98XX_CF_CONTROLS_RST_MSK) {
        reset_ops = reset_ops * 10 + (val ? 2 : 4);
        return reset_error;
    }
    if (reg == TFA98XX_SYS_CTRL && mask == TFA98XX_SYS_CTRL_SBSL_MSK) {
        config_calls++;
        if (inject_stage == 2)
            map->error = -EREMOTEIO;
        return configure_error;
    }
    return 0;
}
static int tfa98xx_startup(struct tfa98xx *tfa) { (void)tfa; return 0; }
static int tfa98xx_coldboot(struct tfa98xx *tfa, int on) { (void)tfa; return on != 1; }
static int tfa98xx_is_coldboot(struct tfa98xx *tfa) { (void)tfa; return hw_cold; }
static int tfa98xx_is_pwdn(struct tfa98xx *tfa) { (void)tfa; return hw_pwdn; }
static int tfa98xx_aec_output(struct tfa98xx *tfa, int on) { (void)tfa; return on != 1; }
static int tfaContWritePatch(struct tfa98xx *tfa) { (void)tfa; patch_calls++; return 0; }
static int tfa98xx_dsp_write_tables(struct tfa98xx *tfa) { (void)tfa; return 0; }
enum { Tfa98xx_Mute_Digital = 1 };
static int tfa98xx_set_mute(struct tfa98xx *tfa, int mute)
{ (void)tfa; return mute != Tfa98xx_Mute_Digital; }
static int tfaContWriteFiles(struct tfa98xx *tfa) { (void)tfa; return 0; }
static int tfaContWriteFilesProf(struct tfa98xx *tfa, int p, int v)
{
    (void)p; (void)v;
    if (inject_stage == 1)
        tfa->regmap->mtp = TFA98XX_MTP_MTPOTC;
    return 0;
}
static void msleep(unsigned int ms) { CHECK(ms == 5); settle_calls++; }
static int tfa98xx_powerdown(struct tfa98xx *tfa, int on)
{ (void)tfa; CHECK(!on); return power_error; }
static int tfaContWriteProfile(struct tfa98xx *tfa, int p, int v)
{ (void)tfa; (void)p; (void)v; return 0; }
static int tfaContWriteFilesVstep(struct tfa98xx *tfa, int p, int v)
{ (void)tfa; (void)p; (void)v; return 0; }
static int tfa98xx_dsp_stop(struct tfa98xx *tfa) { (void)tfa; cleanup_calls++; return 0; }
static int tfa98xx_unmute(struct tfa98xx *tfa) { (void)tfa; unmute_calls++; return 0; }
"""

oracle = r"""
int main(void)
{
    struct regmap map = { .shadow = 1 };
    struct i2c_client bus = {};
    struct profile profiles[] = {{2}, {2}};
    struct tfa98xx tfa = { .regmap = &map, .i2c = &bus, .profiles = profiles,
                          .profile_count = 2, .rev = REV_TFA9890 };
    struct snd_soc_component component = { .data = &tfa };
    const unsigned good = TFA98XX_MTP_MTPOTC | TFA98XX_MTP_MTPEX;
    int ready;

    tfa.component = &component;
    for (unsigned int r = 0; r <= 256; ++r) {
        const bool allowed = r < 0x80 && r != 0x0b && (r < 0x60 || r > 0x62);
        const u8 raw[] = { r, 0, 1 };
        struct nxpTfaRegpatch patch = { .address = r, .mask = 0xffff, .value = 1 };
        struct nxpTfaBitfield bf = { .value = 3, .field = (r << 8) | 0x10 };
        CHECK(tfa98xx_writeable_reg(NULL, r) == allowed);
        if (r > 255)
            continue;
        CHECK(tfa98xx_raw_writeable(raw, sizeof(raw)) == allowed);
        CHECK(tfaRunWriteRegister(&tfa, &patch) == (allowed ? 0 : -EACCES));
        CHECK(tfaRunWriteBitfield(&tfa, bf) == (allowed ? 0 : -EACCES));
        if (allowed)
            CHECK(last_reg == r && last_mask == 2 && last_value == 2);
    }
    const u8 cf_rpc[] = { 0x70, 0, 2, 0, 1, 0, 0x81, 0x85 };
    const u8 touches_guard[] = { 0x5f, 0, 0, 0, 0 };
    const u8 partial_word[] = {0x04, 0};
    const u8 valid_chunk[] = {3, 0, 0x04, 0, 0};
    const u8 denied_chunk[] = {5, 0, 0x5f, 0, 0, 0, 0};
    CHECK(tfa98xx_bulk_write_raw(&component, cf_rpc, sizeof(cf_rpc)) == 0);
    CHECK(tfa98xx_bulk_write_raw(&component, touches_guard, sizeof(touches_guard)) == -EACCES);
    CHECK(tfa98xx_bulk_write_raw(&component, partial_word, sizeof(partial_word)) == -EACCES);
    CHECK(tfa98xx_process_patch_file(&tfa, sizeof(valid_chunk), valid_chunk) == 0);
    CHECK(tfa98xx_process_patch_file(&tfa, sizeof(denied_chunk), denied_chunk) == -EACCES);
    CHECK(tfa98xx_process_patch_file(&tfa, 1, valid_chunk) == -EINVAL);
    CHECK(tfa98xx_process_patch_file(&tfa, 4, valid_chunk) == -EINVAL);
    CHECK(sends == 2);

    /* Keep the first failure and restore clock gating even on transport error. */
    reset_ops = 0;
    CHECK(tfa98xx_dsp_reset(&tfa, 1) == 0 && reset_ops == 123);
    reset_ops = 0;
    CHECK(tfa98xx_dsp_reset(&tfa, 0) == 0 && reset_ops == 143);
    gate_off_error = -ENXIO;
    gate_on_error = -EIO;
    reset_ops = 0;
    CHECK(tfa98xx_dsp_reset(&tfa, 1) == -ENXIO && reset_ops == 13);
    gate_off_error = 0;
    reset_error = -EREMOTEIO;
    reset_ops = 0;
    CHECK(tfa98xx_dsp_reset(&tfa, 1) == -EREMOTEIO && reset_ops == 123);
    reset_error = 0;
    reset_ops = 0;
    CHECK(tfa98xx_dsp_reset(&tfa, 1) == -EIO && reset_ops == 123);
    tfa.rev = 0x91;
    reset_ops = 0;
    CHECK(tfa98xx_dsp_reset(&tfa, 1) == 0 && reset_ops == 2);
    tfa.rev = REV_TFA9890;
    gate_on_error = 0;

    for (unsigned int mtp = 0; mtp <= 0xffff; mtp++) {
        map.mtp = mtp;
        CHECK(tfa98xx_require_calibration(&tfa) ==
              (((mtp & good) == good && mtp != U16_MAX) ? 0 : -ENODATA));
    }
    map.mtp = good;
    map.status = TFA98XX_STATUSREG_MTPB_MSK;
    CHECK(tfa98xx_require_calibration(&tfa) == -EBUSY);
    map.status = TFA98XX_STATUSREG_AREFS_MSK | TFA98XX_STATUSREG_CLKS_MSK;
    CHECK(tfa98xx_dsp_system_stable(&tfa, &ready) == 0 && ready);
    map.shadow = 0;
    CHECK(tfa98xx_dsp_system_stable(&tfa, &ready) == 0 && !ready);
    map.error = -EREMOTEIO;
    map.error_reg = 0x84;
    CHECK(tfa98xx_dsp_system_stable(&tfa, &ready) == -EREMOTEIO && !ready);
    map.error_reg = TFA98XX_STATUSREG;
    CHECK(tfa98xx_dsp_system_stable(&tfa, &ready) == -EREMOTEIO && !ready);
    CHECK(tfa98xx_require_calibration(&tfa) == -EREMOTEIO);
    map.error = 0;
    map.error_reg = TFA98XX_MTP;
    map.shadow = 1;

    /* Forced start, ACS cold start and warm transitions share the gate. */
    for (int mode = 0; mode < 5; mode++) {
        tfa.needs_full_init = mode == 0;
        hw_cold = mode == 1; hw_pwdn = mode == 2;
        tfa.profile_current = 0;
        map.mtp = 0;
        patch_calls = config_calls = unmute_calls = cleanup_calls = 0;
        CHECK(tfa98xx_dsp_start(&tfa, mode == 3, mode == 4) == -ENODATA);
        CHECK(!patch_calls && !config_calls && !unmute_calls && cleanup_calls == 1);
        CHECK(tfa.needs_full_init && !tfa.profile_current && !tfa.vstep_current);
        tfa.needs_full_init = mode == 0;
        map.mtp = good;
        CHECK(tfa98xx_dsp_start(&tfa, mode == 3, mode == 4) == 0);
        CHECK(patch_calls == (mode < 2) && config_calls == (mode < 2) && unmute_calls == 1);
        CHECK(!tfa.needs_full_init && tfa.profile_current == (mode == 3));
        tfa.vstep_current = 0;
    }
    CHECK(settle_calls == 2);
    hw_cold = 0; hw_pwdn = 1; power_error = -ETIMEDOUT;
    tfa.profile_current = 0;
    CHECK(tfa98xx_dsp_start(&tfa, 0, 0) == -ETIMEDOUT);
    power_error = 0;
    for (inject_stage = 1; inject_stage <= 2; inject_stage++) {
        map.mtp = good;
        map.error = 0;
        patch_calls = config_calls = unmute_calls = cleanup_calls = 0;
        CHECK(tfa98xx_dsp_start(&tfa, 0, 0) == (inject_stage == 1 ? -ENODATA : -EREMOTEIO));
        CHECK(patch_calls == 1 && config_calls == (inject_stage == 2) && !unmute_calls);
        CHECK(cleanup_calls == 1 && tfa.needs_full_init);
    }
    map.error = 0;
    configure_error = -EIO;
    patch_calls = config_calls = unmute_calls = cleanup_calls = 0;
    CHECK(tfa98xx_dsp_start(&tfa, 0, 0) == -EIO);
    CHECK(patch_calls == 1 && config_calls == 1 && !unmute_calls && cleanup_calls == 1);
    verify_factory_blob(&tfa);
    puts("PASS: 65536 MTP values, 257 register guards, transport, six DSP reset and five start/rollback paths");
    return 0;
}
"""

production = [
    *(descriptor(name) for name in ("nxpTfaBitfield", "nxpTfaBfEnum", "nxpTfaRegpatch")),
    *(function(i2c, name) for name in ("tfa98xx_writeable_reg", "tfa98xx_raw_writeable",
                                       "tfa98xx_bulk_write_raw")),
    *(function(dsp, name) for name in ("tfaRunWriteBitfield", "tfaRunWriteRegister",
                                       "tfa98xx_process_patch_file", "tfa98xx_dsp_system_stable",
                                       "tfa98xx_clockgating", "tfa98xx_dsp_reset",
                                       "tfa98xx_dsp_power_up", "tfa98xx_set_configured",
                                       "tfa98xx_require_calibration", "tfaRunStartDSP",
                                       "tfaRunColdStartup", "tfaRunSpeakerBoost", "tfa98xx_dsp_start")),
]


def factory_blob_test(path):
    if not path:
        return "static void verify_factory_blob(struct tfa98xx *tfa) { (void)tfa; }"

    blob = Path(path).read_bytes()
    digest = "83709da84f22b5c0ff1f7568478b3ecbfc1c1c29bc3814a8be8a64426f3c2c2a"
    if len(blob) != 5133 or hashlib.sha256(blob).hexdigest() != digest:
        raise ValueError("not the pinned Mi Pad 2 factory container")

    def le(offset, size=2):
        value = blob[offset:offset + size]
        if len(value) != size or offset < 0:
            raise ValueError("truncated factory container")
        return int.from_bytes(value, "little")

    if zlib.crc32(blob[14:]) != le(10, 4) or (le(40), le(42)) != (2, 6):
        raise ValueError("invalid factory CRC or topology")

    fields = []
    patches = set()

    def parse_list(offset, count):
        for i in range(count):
            value = le(offset + i * 4, 4)
            kind, at = value >> 24, value & 0xffffff
            if kind == 1:
                parse_list(at + 8, blob[at] - 1)
            elif kind == 2:
                fields.append(
                    f"CHECK(tfaRunWriteRegister(tfa, &(struct nxpTfaRegpatch){{"
                    f"{blob[at]}, {le(at+1)}, {le(at+3)}}}) == 0);")
            elif kind >= 0x80:
                fields.append(
                    f"CHECK(tfaRunWriteBitfield(tfa, (struct nxpTfaBitfield){{"
                    f"{value & 0xffff}, {(value >> 16) & 0x7fff}}}) == 0);")
            elif kind == 5:
                if blob[at+8:at+10] != b"PA" or le(at+4, 4) != le(at+14):
                    raise ValueError("invalid embedded factory patch header")
                patches.add(blob[at + 8 + 36 + 6:at + 8 + le(at+14)])

    for i, addr in enumerate((0x34, 0x37)):
        at = le(44 + 4 * i, 4)
        if at > 0xffffff or blob[at+1:at+3] != bytes((1, addr)):
            raise ValueError("unexpected factory device descriptor")
        parse_list(at + 12, blob[at])
    if len(patches) != 1 or not fields:
        raise ValueError("factory stereo patch or register fields missing")

    payload = next(iter(patches))
    # The old patch is shared by both channels; replay through the real
    # production transport parser and fake bus using both channel contexts.
    format_bytes = lambda value: ",".join(str(n) for n in value)
    return "\n".join([
        "static void verify_factory_blob(struct tfa98xx *tfa) {",
        f"const u8 patch[] = {{{format_bytes(payload)}}};",
        *fields,
        "int before = sends;",
        "CHECK(tfa98xx_process_patch_file(tfa, sizeof(patch), patch) == 0);",
        "CHECK(tfa98xx_process_patch_file(tfa, sizeof(patch), patch) == 0);",
        "CHECK(sends - before == 44);",
        f'puts("PASS: pinned Android container, {len(fields)} device/profile '
        'register descriptors and 44 guarded patch transactions");',
        "}",
    ])


with tempfile.TemporaryDirectory(prefix="mipad2-tfa-calibration-") as temp:
    source, binary = Path(temp) / "test.c", Path(temp) / "test"
    fixture = factory_blob_test(os.environ.get("MIPAD2_FACTORY_CNT"))
    source.write_text("\n".join([preamble, *production, fixture, oracle]))
    subprocess.run(shlex.split(os.getenv("CC", "cc")) + [
        "-std=gnu11", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
        "-fsanitize=undefined", "-fsanitize-undefined-trap-on-error",
        "-I", str(codec), str(source), "-o", str(binary),
    ], check=True)
    subprocess.run([str(binary)], check=True)
