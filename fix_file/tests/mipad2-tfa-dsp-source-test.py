#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Guard TFA DSP bring-up against known deadlock and error-masking regressions."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
CODEC = ROOT / "sound/soc/codecs/tfa98xx-xiaomi/tfa98xx.c"
DSP = ROOT / "sound/soc/codecs/tfa98xx-xiaomi/tfa_dsp.c"


def function_body(source: str, name: str) -> str:
    signature = re.search(
        rf"(?m)^\s*(?:static\s+)?(?:int|void)\s+{re.escape(name)}\s*\([^;]*?\)\s*\{{",
        source,
    )
    if not signature:
        raise AssertionError(f"missing function {name}")
    opening = source.index("{", signature.start())
    depth = 0
    for pos in range(opening, len(source)):
        if source[pos] == "{":
            depth += 1
        elif source[pos] == "}":
            depth -= 1
            if depth == 0:
                return source[opening + 1:pos]
    raise AssertionError(f"unterminated function {name}")


codec = CODEC.read_text()
dsp = DSP.read_text()
container_source = (CODEC.parent / "tfa_container.c").read_text()


def strip_c_comments(source: str) -> str:
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)


codec = strip_c_comments(codec)
dsp = strip_c_comments(dsp)

mute = function_body(codec, "tfa98xx_digital_mute")
cancel = mute.index("cancel_delayed_work_sync")
lock = mute.index("mutex_lock(&tfa98xx->dsp_init_lock)")
assert cancel < lock, "monitor cancellation must happen outside dsp_init_lock"
assert "tfa98xx_dsp_stop(tfa98xx)" in mute
assert "tfa98xx->desired_running = false;" in mute
assert "tfa98xx->desired_running = true;" in mute
assert ".mute_stream\t= tfa98xx_mute_stream" in codec

startup = function_body(dsp, "tfa98xx_startup")
for operation in (
    "tfa98xx_init",
    "tfaContWriteRegsDev",
    "tfaContWriteRegsProf",
    "tfa98xx_powerdown",
):
    match = re.search(
        rf"ret\s*=\s*{operation}\([^;]*\);\s*if\s*\(ret\)\s*return\s+ret;",
        startup,
        re.S,
    )
    assert match, f"{operation} error must abort DSP startup"
assert "if (!(status & TFA98XX_STATUSREG_AREFS_MSK))\n\t\treturn -ETIMEDOUT;" in startup
assert "if (ret)\n\t\t\treturn ret;" in startup

calibrate = function_body(dsp, "tfaRunSetCalibrateOnce")
assert "goto lock_mtp;" in calibrate
assert "lock_err = snd_soc_component_write(component, 0x0b, 0x0);" in calibrate

speaker_boost = function_body(dsp, "tfaRunSpeakerBoost")
for operation in (
    "tfaRunStartDSP",
    "tfaRunSetCalibrateOnce",
    "tfaContWriteFilesProf",
    "tfa98xx_wait_calibration",
):
    assert re.search(
        rf"ret\s*=\s*{operation}\([^;]*\);\s*(?:if\s*\(ret[^)]*\)|if\s*\(ret\s*&&[^)]*\))",
        speaker_boost,
        re.S,
    ), f"{operation} result must be checked"

start = function_body(dsp, "tfa98xx_dsp_start")
assert "goto rollback_state;" in start
assert "rollback_state:" in start
assert "tfa98xx->profile_current = active_profile;" in start
assert "tfa98xx->vstep_current = active_vstep;" in start
assert "next_profile >= tfa98xx->profile_count" in start
assert "vstep >= tfa98xx->profiles[next_profile].vsteps" in start

profile_ctl = function_body(codec, "tfa98xx_set_profile_ctl")
assert "profile < 0 || profile >= tfa98xx->profile_count" in profile_ctl
assert "if (!prof_old->vsteps || !prof_new->vsteps)" in profile_ctl
volume_ctl = function_body(codec, "tfa98xx_set_vol_ctl")
assert "requested < 0 || requested >= prof->vsteps" in volume_ctl

assert "devm_kmemdup(component->dev" in container_source
assert "data->size != size - 14" in container_source
assert "invalid container size/index table" in container_source
assert "tfa_container_device_valid(base, size" in container_source
assert "tfa_container_file_valid(base, total" in container_source
assert "file->size < sizeof(struct nxpTfaHeader)" in container_source
assert "tfa98xx_unmute" not in speaker_boost
assert "tfa98xx_unmute(tfa98xx)" in start

print("TFA DSP deadlock/error-path source checks passed")
