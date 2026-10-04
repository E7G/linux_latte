#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Guard TFA DSP bring-up against known deadlock and error-masking regressions."""

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
CODEC = ROOT / "sound/soc/codecs/tfa98xx-xiaomi/tfa98xx.c"
DSP = ROOT / "sound/soc/codecs/tfa98xx-xiaomi/tfa_dsp.c"
LIVE_TEST = ROOT / "fix_file/tests/mipad2_tfa_dsp_test_remote.sh"
LIVE_RUNNER = ROOT / "fix_file/tests/mipad2_tfa_dsp_test.py"


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
live_test = LIVE_TEST.read_text()
live_runner = LIVE_RUNNER.read_text()


def strip_c_comments(source: str) -> str:
    return re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)


codec = strip_c_comments(codec)
dsp = strip_c_comments(dsp)

mute = function_body(codec, "tfa98xx_digital_mute")
cancel = mute.index("cancel_delayed_work_sync")
lock = mute.index("mutex_lock(&tfa98xx->dsp_init_lock)")
assert cancel < lock, "monitor cancellation must happen outside dsp_init_lock"
assert mute.index("cancel_work_sync(&tfa98xx->init_work)") < lock, \
    "init cancellation must also happen outside dsp_init_lock"
worker = function_body(codec, "tfa98xx_dsp_init")
assert worker.index("if (!tfa98xx->desired_running)") < worker.index("tfa98xx_dsp_start("), \
    "a stale queued init must not power up an already-muted stream"
assert "tfa98xx_dsp_stop(tfa98xx)" in mute
assert "tfa98xx->desired_running = false;" in mute
assert "tfa98xx->desired_running = true;" in mute
assert ".mute_stream\t= tfa98xx_mute_stream" in codec

# Each physical amp must expose the machine driver's board-facing output pin;
# an unconnected mixer can bind successfully while silently powering no path.
assert 'SND_SOC_DAPM_OUTPUT("OUT Left")' in codec
assert 'SND_SOC_DAPM_OUTPUT("OUT Right")' in codec
probe = function_body(codec, "tfa98xx_probe")
assert "tfa98xx->i2c->addr == 0x37" in probe
assert "tfa98xx->i2c->addr == 0x34" in probe
assert 'output_name = "OUT Right"' in probe
assert 'output_name = "OUT Left"' in probe
assert "dapm_routes[0].source = tfa98xx->playback_stream_name;" in probe
assert 'dapm_routes[1].source = "NXP Output Mixer";' in probe
assert "if (ret)\n\t\treturn ret;" in probe
i2c_probe = function_body(codec, "tfa98xx_i2c_probe")
assert "dai_drv->playback.stream_name = tfa98xx->playback_stream_name;" in i2c_probe

monitor = function_body(codec, "tfa98xx_monitor")
assert monitor.count("READ_ONCE(tfa98xx->monitor_status)") == 2, \
    "monitor stop flag must be read atomically before and after work"

remove = function_body(codec, "tfa98xx_i2c_remove")
disable_monitor = remove.index("WRITE_ONCE(tfa98xx->monitor_status, 0)")
cancel_monitor = remove.index("cancel_delayed_work_sync(&tfa98xx->delay_work)")
cancel_init = remove.index("cancel_work_sync(&tfa98xx->init_work)")
destroy_queue = remove.index("destroy_workqueue(tfa98xx->tfa98xx_wq)")
assert disable_monitor < cancel_monitor < cancel_init < destroy_queue, \
    "remove must stop and drain self-rearming work before destroying its queue"

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

init = function_body(dsp, "tfa98xx_init")
rev_91 = re.search(r"case\s+0x91\s*:(.*?)(?=case\s+0x97\s*:)", init, re.S)
assert rev_91 and re.search(r"\bret\s*=\s*0\s*;", rev_91.group(1)), \
    "TFA9890B init path must return deterministic success"
mode = function_body(dsp, "tfa98xx_select_mode")
assert "temp_value == -1" not in mode
assert "temp_value > 0xffff" in mode and "bat_volt > 0xffff" in mode, \
    "unsigned register-read errors must be caught before narrowing"

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
assert re.search(
    r"data->size\s*!=\s*size\s*-\s*14\s*&&\s*data->size\s*!=\s*size",
    container_source,
), "accept both post-CRC and stock total-file-size container conventions"
assert "invalid container size/index table" in container_source
assert "tfa_container_device_valid(base, size" in container_source
assert "tfa_container_file_valid(base, total" in container_source
assert "file->size < sizeof(struct nxpTfaHeader)" in container_source
assert "tfa98xx_unmute" not in speaker_boost
assert "tfa98xx_unmute(tfa98xx)" in start
assert "coldboot || tfa98xx->needs_full_init" in start
assert "tfa98xx->needs_full_init = false;" in start
assert "tfa98xx->needs_full_init = true;" in start[start.index("rollback_state:"):]
assert "tfa98xx->needs_full_init = true;" in probe

assert "fuser -s /dev/snd/*" in live_test, \
    "live driver unbind must verify all ALSA control and PCM handles are closed"
assert "stop_desktop_audio" in live_test and "audio_control stop" in live_test
assert "refusing driver unbind" in live_test, \
    "live cleanup must fail closed if ALSA handles remain open"
assert "timeout --signal=TERM --kill-after=3s 8s runuser" in live_test
assert 'paplay "$tone"' in live_test, \
    "live playback must use the configured PipeWire/UCM route"
assert "save_test_audio_levels\nstop_desktop_audio" in live_test, \
    "save speaker levels before stopping the user audio services"
assert "restore_desktop_audio\n\trestore_test_audio_levels" in live_test, \
    "restore original speaker levels after the user audio stack is back"
assert "set_test_audio_levels" in live_test and \
    "capture_active_playback_state" in live_test, \
    "bounded playback must use a known audible level and sample live DAPM/TFA state"
assert "amplitude = 12_000" in live_runner and "frames = 96_000" in live_runner, \
    "test stimulus must be a two-second non-negligible PCM tone"
assert "aplay -q -D hw:0,0" not in live_test, \
    "raw front-end playback can bypass the configured HiFi route"
assert "not in gate.splitlines()" in live_runner, \
    "host runner must reject fallback kernel suffixes, not substring-match them"
assert "^expected_sha=([0-9a-f]{64})$" in live_runner, \
    "host and remote module hash must share one pinned value"
assert "192.168.1.147" not in live_runner, \
    "test runner must not hard-code a private device address"
assert 'MIPAD2_TFA_TEST_MODE:-silent' in live_test
assert 'if [[ "$test_mode" == audible ]]; then set_test_audio_levels; fi' in live_test
assert "assert not any(pcm.readframes" in live_test, \
    "silent tests must reject nonzero PCM before touching audio drivers"
assert 'printf \'%s\\n\' "$log_marker" > /dev/kmsg' in live_test
assert '"$log_marker" --containers-only' in live_test
assert 'python3 "$log_checker" "$log_raw" "$log_marker";' in live_test, \
    "require both amplifiers in this run, not a historical ret=0"
assert 'dmesg | grep -F \'factory DSP init ret=0\'' not in live_test
assert "MIPAD2_TFA_TEST_MODE={test_mode}" in live_runner

print("TFA DSP deadlock/error-path and live-test safety checks passed")
