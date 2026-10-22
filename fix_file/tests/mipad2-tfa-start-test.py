#!/usr/bin/env python3
"""Execute real tfa98xx_dsp_start with mocked DSP/profile operations.

Regresses a fresh driver accepting a warm ACS latch left by a bypass driver.
Does not access hardware or establish acoustic/protection behavior.
"""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
source = (ROOT / "sound/soc/codecs/tfa98xx-xiaomi/tfa_dsp.c").read_text()
start = source.index("int tfa98xx_dsp_start(")
brace = source.index("{", start)
depth, end = 1, brace + 1
while depth:
    depth += (source[end] == "{") - (source[end] == "}")
    end += 1
callback = source[start:end]
mock = r"""
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
#include <stdio.h>
#define TFA98XX_DSP_INIT_RECOVER 9
#define pr_warn(...) ((void)0)
#define pr_debug(...) ((void)0)
#define dev_warn(...) ((void)0)
struct tfaprofile { int vsteps; };
struct tfa98xx {
    int profile_count, profile_current, vstep_current, dsp_init;
    struct tfaprofile *profiles;
    bool needs_full_init;
};
static int coldboot, hw_cold, hw_pwdn, fulls, forced, aecs, stops, unmutes;
static int boost_error, profile_error, volume_error, unmute_error, aec_error;
static int tfa98xx_is_coldboot(struct tfa98xx *tfa) { (void)tfa; return hw_cold; }
static int tfa98xx_is_pwdn(struct tfa98xx *tfa) { (void)tfa; return hw_pwdn; }
static int tfa98xx_aec_output(struct tfa98xx *tfa, int on)
{ (void)tfa; assert(on == 1); aecs++; return aec_error; }
static int tfaRunSpeakerBoost(struct tfa98xx *tfa, int force)
{
    (void)tfa;
    forced += force;
    fulls += !!(force || hw_cold);
    if (!boost_error) hw_pwdn = 0;
    return boost_error;
}
static int tfaContWriteProfile(struct tfa98xx *tfa, int profile, int step)
{ (void)tfa; (void)profile; (void)step; return profile_error; }
static int tfaContWriteFilesVstep(struct tfa98xx *tfa, int profile, int step)
{ (void)tfa; (void)profile; (void)step; return volume_error; }
static int tfa98xx_unmute(struct tfa98xx *tfa)
{ (void)tfa; unmutes++; return unmute_error; }
static int tfa98xx_dsp_stop(struct tfa98xx *tfa)
{ (void)tfa; stops++; hw_pwdn = 1; return 0; }
"""
harness = r"""
int main(void)
{
    struct tfaprofile profiles[] = { {3}, {3} };
    struct tfa98xx tfa = { .profile_count = 2, .profiles = profiles,
                           .needs_full_init = true };
    int before;
    /* ACS is clear, but a prior generic driver bypassed/disabled DSP. */
    hw_cold = 0; hw_pwdn = 0;
    assert(tfa98xx_dsp_start(&tfa, 0, 0) == 0);
    assert(fulls == 1 && forced == 1 && aecs == 1 && !tfa.needs_full_init);
    before = fulls;
    assert(tfa98xx_dsp_start(&tfa, 0, 0) == 0 && fulls == before);
    /* Normal warm idle restart must remain a warm restart, not reflash. */
    hw_pwdn = 1;
    assert(tfa98xx_dsp_start(&tfa, 0, 0) == 0 && fulls == before && !hw_pwdn);
    /* Partial profile writes invalidate ownership even if state is rolled back. */
    profile_error = -EIO;
    assert(tfa98xx_dsp_start(&tfa, 1, 0) == -EIO);
    assert(tfa.profile_current == 0 && tfa.needs_full_init && stops == 1);
    profile_error = 0;
    assert(tfa98xx_dsp_start(&tfa, 1, 0) == 0 && fulls == before + 1);
    assert(tfa.profile_current == 1 && !tfa.needs_full_init);
    volume_error = -EREMOTEIO;
    assert(tfa98xx_dsp_start(&tfa, 1, 1) == -EREMOTEIO);
    assert(tfa.vstep_current == 0 && tfa.needs_full_init);
    volume_error = 0;
    boost_error = -ETIMEDOUT;
    assert(tfa98xx_dsp_start(&tfa, 1, 1) == -ETIMEDOUT);
    assert(tfa.vstep_current == 0 && tfa.needs_full_init);
    boost_error = 0;
    unmute_error = -EIO;
    assert(tfa98xx_dsp_start(&tfa, 1, 1) == -EIO && tfa.needs_full_init);
    unmute_error = 0;
    assert(tfa98xx_dsp_start(&tfa, 1, 1) == 0 && !tfa.needs_full_init);
    tfa.dsp_init = TFA98XX_DSP_INIT_RECOVER;
    before = fulls;
    assert(tfa98xx_dsp_start(&tfa, 1, 1) == 0 && fulls == before + 1);
    tfa.dsp_init = 0;
    coldboot = 1;
    assert(tfa98xx_dsp_start(&tfa, 1, 1) == 0 && fulls == before + 2);
    coldboot = 0;
    hw_cold = 1;
    assert(tfa98xx_dsp_start(&tfa, 1, 1) == 0 && fulls == before + 3);
    hw_cold = 0;
    before = unmutes;
    assert(tfa98xx_dsp_start(&tfa, -1, 0) == -EINVAL);
    assert(tfa98xx_dsp_start(&tfa, 2, 0) == -EINVAL);
    assert(tfa98xx_dsp_start(&tfa, 0, -1) == -EINVAL);
    assert(tfa98xx_dsp_start(&tfa, 0, 3) == -EINVAL);
    assert(unmutes == before && !tfa.needs_full_init);
    puts("PASS: real DSP start callback; fresh warm latch, warm restart, recovery, rollback/errors, invalid params");
    return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="mipad2-tfa-start-") as temp:
    cfile, binary = Path(temp) / "test.c", Path(temp) / "test"
    cfile.write_text(mock + callback + harness)
    subprocess.run(shlex.split(os.environ.get("CC", "clang")) + [
        "-std=c11", "-Wall", "-Wextra", "-Werror", str(cfile), "-o", str(binary)
    ], check=True)
    subprocess.run([str(binary)], check=True)
