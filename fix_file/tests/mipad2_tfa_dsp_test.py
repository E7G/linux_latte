#!/usr/bin/env python3
"""Gate, stage, and run a reversible 6.14 TFA DSP/playback smoke test."""

import io
import hashlib
import math
import os
import pathlib
import re
import struct
import sys
import wave

import paramiko


HOST = os.environ.get("MIPAD2_HOST")
USER = os.environ.get("MIPAD2_USER")
PASSWORD = os.environ.get("MIPAD2_PASSWORD")
if len(sys.argv) != 2:
    raise SystemExit(f"Usage: {pathlib.Path(sys.argv[0]).name} CANDIDATE.ko")
MODULE = pathlib.Path(sys.argv[1])
remote_script = pathlib.Path(__file__).with_name("mipad2_tfa_dsp_test_remote.sh")
log_checker = pathlib.Path(__file__).with_name("mipad2_tfa_dsp_log_check.py")
if not remote_script.is_file():
    raise SystemExit(f"Remote test script missing: {remote_script}")
if not log_checker.is_file():
    raise SystemExit(f"DSP log checker missing: {log_checker}")
test_mode = os.environ.get("MIPAD2_TFA_TEST_MODE", "silent")
if test_mode not in ("silent", "audible"):
    raise SystemExit("MIPAD2_TFA_TEST_MODE must be silent or audible")

match = re.search(r"(?m)^expected_sha=([0-9a-f]{64})$",
                  remote_script.read_text(encoding="utf-8"))
if not match:
    raise SystemExit(f"Pinned candidate SHA-256 missing from {remote_script}")
expected_sha = match.group(1)
REMOTE_MODULE = "/tmp/codex-mipad2-tfa-dsp.ko"
REMOTE_TONE = "/tmp/codex-mipad2-low-tone.wav"
REMOTE_SCRIPT = "/tmp/codex-mipad2-tfa-dsp-test.sh"

if not HOST or not USER or not PASSWORD:
    raise SystemExit("Set MIPAD2_HOST, MIPAD2_USER, and MIPAD2_PASSWORD in the environment.")
if not MODULE.is_file():
    raise SystemExit(f"Candidate module missing: {MODULE}")

digest = hashlib.sha256(MODULE.read_bytes()).hexdigest()
if digest != expected_sha:
    raise SystemExit(f"Candidate hash mismatch: {digest}")

sample_rate = 48_000
frames = 96_000  # Two-second burst; play twice with a one-second gap.
amplitude = 12_000
if test_mode == "silent":
    frames, amplitude = 288_000, 0  # Six seconds to observe bounded DSP startup.
tone_bytes = io.BytesIO()
with wave.open(tone_bytes, "wb") as tone:
    tone.setnchannels(2)
    tone.setsampwidth(2)
    tone.setframerate(sample_rate)
    pcm = bytearray()
    for index in range(frames):
        value = int(amplitude * math.sin(2 * math.pi * 440 * index / sample_rate))
        pcm.extend(struct.pack("<hh", value, value))
    tone.writeframes(pcm)

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(
    HOST,
    username=USER,
    password=PASSWORD,
    timeout=10,
    banner_timeout=10,
    auth_timeout=10,
    look_for_keys=False,
    allow_agent=False,
)


def run(command: str, *, sudo: bool = False, timeout: int = 30):
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    if sudo:
        stdin.write(PASSWORD + "\n")
        stdin.flush()
        stdin.channel.shutdown_write()
    out = stdout.read().decode(errors="replace")
    err = stderr.read().decode(errors="replace")
    status = stdout.channel.recv_exit_status()
    return status, out, err


try:
    status, gate, err = run(
        "mp2-test-no-idle status; uname -r; systemctl is-system-running; "
        "printf 'SINK_INPUTS\\n'; env "
        "XDG_RUNTIME_DIR=/run/user/1000 "
        "PULSE_SERVER=unix:/run/user/1000/pulse/native "
        "pactl list short sink-inputs",
        timeout=20,
    )
    print("=== preflight ===")
    print(gate, end="")
    if err:
        print(err, file=sys.stderr, end="")
    if status:
        raise SystemExit(f"No test: preflight failed ({status}).")
    if "PASS anti-idle inhibitor active" not in gate:
        raise SystemExit("No test: anti-idle gate did not PASS.")
    if "6.14.0-mipad2-cachyos" not in gate.splitlines():
        raise SystemExit("No test: integrated 6.14 is not running.")
    if "running" not in gate:
        raise SystemExit("No test: systemd is not healthy.")
    sink_tail = gate.partition("SINK_INPUTS\n")[2].strip()
    if sink_tail:
        raise SystemExit("No test: PulseAudio/PipeWire already has active sink inputs.")

    with client.open_sftp() as sftp:
        sftp.put(str(MODULE), REMOTE_MODULE)
        sftp.put(str(log_checker), "/tmp/mipad2_tfa_dsp_log_check.py")
        with sftp.open(REMOTE_TONE, "wb") as remote_tone:
            remote_tone.write(tone_bytes.getvalue())
        with sftp.open(REMOTE_SCRIPT, "wb") as remote_shell:
            remote_shell.write(remote_script.read_bytes().replace(b"\r\n", b"\n"))
        sftp.chmod(REMOTE_MODULE, 0o644)
        sftp.chmod(REMOTE_TONE, 0o644)
        sftp.chmod(REMOTE_SCRIPT, 0o755)

    status, out, err = run(
        f"sudo -S -p '' env MIPAD2_TFA_TEST_MODE={test_mode} bash {REMOTE_SCRIPT}",
        sudo=True, timeout=120
    )
    print("=== temporary TFA DSP/playback test ===")
    print(out, end="")
    if err:
        print(err, file=sys.stderr, end="")
    print(f"EXIT={status}")
    if status:
        raise SystemExit(status)
    if "DSP_TEST_BODY_COMPLETE" not in out:
        raise SystemExit("Test did not reach DSP_TEST_BODY_COMPLETE.")
    if "RESTORED i2c-tfa9890:00=tfa989x" not in out or \
            "RESTORED i2c-tfa9890:01=tfa989x" not in out:
        raise SystemExit("Stock driver restoration was not verified.")
    if "PASS anti-idle inhibitor active" not in out or \
            "6.14.0-mipad2-cachyos" not in out:
        raise SystemExit("Post-test health gate was not verified.")
    if "AUDIO_RESTORED=yes" not in out:
        raise SystemExit("Original PipeWire speaker route was not verified after cleanup.")
finally:
    try:
        run(f"rm -f {REMOTE_MODULE} {REMOTE_TONE} {REMOTE_SCRIPT} /tmp/mipad2_tfa_dsp_log_check.py", timeout=10)
    except Exception:
        pass
    client.close()
